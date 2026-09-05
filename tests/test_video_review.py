import gzip
import io
import unittest

import requests
from urllib3.response import HTTPResponse
from urllib3.exceptions import ReadTimeoutError

from tests.test_video import FakeCrawler, FakeRequestSession, FakeResponse, MASTER_URL, player_html
from video import VideoService, UpstreamError, UpstreamTimeout


class ReviewRegressionTests(unittest.TestCase):
    def make_service(self, response):
        crawler = FakeCrawler()
        embed = crawler.index['posts']['demo slug']['videos'][0]['embed']
        calls = []
        responses = {embed: FakeResponse(player_html()), MASTER_URL: response}
        service = VideoService(crawler, session_factory=lambda: FakeRequestSession(responses, calls))
        session, resource = service.create_video_session('demo slug', 0).split('/')[2:]
        return service, session, resource, calls

    def test_manifest_range_is_ignored_and_all_uris_stay_local(self):
        service, session, resource, calls = self.make_service(FakeResponse(
            b'#EXTM3U\nhttps://hls-cdn.cossora.stream/segment.png\n',
            headers={'Content-Type': 'application/vnd.apple.mpegurl'}))
        response = service.open_resource(session, resource, 'GET', 'bytes=0-', '')
        try:
            self.assertNotIn('Range', calls[-1][2]['headers'])
            self.assertEqual(200, response.status)
            self.assertNotIn(b'https://', b''.join(response.iter_body()))
        finally:
            response.close()

    def test_unrequested_partial_manifest_is_rejected(self):
        service, session, resource, calls = self.make_service(FakeResponse(
            b'#EXTM3U\nhttps://hls-cdn.cossora.stream/segment.png\n', status=206,
            headers={'Content-Type': 'application/vnd.apple.mpegurl'}))
        with self.assertRaises(UpstreamError):
            service.open_resource(session, resource, 'GET', 'bytes=0-', '')

    def test_gzip_media_preserves_wire_bytes_and_encoding(self):
        wire = gzip.compress(b'media data ' * 600)
        upstream = requests.Response()
        upstream.status_code = 200
        upstream.headers.update({'Content-Encoding': 'gzip', 'Content-Length': str(len(wire))})
        upstream.raw = HTTPResponse(body=io.BytesIO(wire), headers=upstream.headers, preload_content=False)
        response = VideoService._stream_response(upstream, FakeRequestSession({}, []), 200)
        try:
            body = b''.join(response.iter_body())
            self.assertEqual(wire, body)
            self.assertEqual(str(len(body)), response.headers['Content-Length'])
            self.assertEqual('gzip', response.headers['Content-Encoding'])
        finally:
            response.close()

    def test_read_timeout_wrapped_by_requests_becomes_504(self):
        class TimedOut(FakeResponse):
            def iter_content(self, chunk_size):
                raise requests.ConnectionError(ReadTimeoutError(None, '/', 'read timed out'))
        with self.assertRaises(UpstreamTimeout):
            VideoService._read_limited(TimedOut(), 1024)

    def test_other_body_transport_error_becomes_502(self):
        class Failed(FakeResponse):
            def iter_content(self, chunk_size):
                raise requests.ConnectionError('connection reset')
        with self.assertRaises(UpstreamError):
            VideoService._read_limited(Failed(), 1024)


if __name__ == '__main__':
    unittest.main()
