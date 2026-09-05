import base64
import time
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from video import (
    InvalidVideoSource,
    ResourceNotFound,
    UpstreamError,
    VideoService,
    decrypt_video_url,
    extract_encrypted_video,
    validate_upstream_url,
)


KEY = "0123456789abcdef0123456789abcdef"
IV = b"0123456789abcdef"
MASTER_URL = "https://cossora.stream/api-embed/example/index.m3u8?token=upstream"


def encrypted_url(url=MASTER_URL):
    padder = padding.PKCS7(128).padder()
    padded = padder.update(url.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY.encode("utf-8")), modes.CBC(IV)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(IV + ciphertext).decode("ascii")


class FakeResponse:
    def __init__(self, body=b"", status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size=65536):
        if self._chunks is not None:
            yield from self._chunks
        elif self._body:
            for pos in range(0, len(self._body), chunk_size):
                yield self._body[pos:pos + chunk_size]

    def close(self):
        self.closed = True


class FakeRequestSession:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


class FakeCrawler:
    def __init__(self):
        import threading
        self._lock = threading.RLock()
        self.proxy = "http://127.0.0.1:7890"
        self.index = {
            "posts": {
                "demo slug": {
                    "slug": "demo slug",
                    "url": "https://cosplaytele.com/demo/",
                    "videos": [{
                        "id": "de0d5fb2-1267-4d8b-be55-26f16ea82c31",
                        "embed": "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31",
                    }],
                }
            }
        }


def player_html():
    return ("<script>const videoURL = '" + encrypted_url() + "';"
            "const result = decryptLink(videoURL, '" + KEY + "');</script>").encode("utf-8")


class VideoParsingTests(unittest.TestCase):
    def test_extracts_static_ciphertext_and_key_without_executing_script(self):
        ciphertext, key = extract_encrypted_video(player_html().decode("utf-8"))
        self.assertEqual(encrypted_url(), ciphertext)
        self.assertEqual(KEY, key)

    def test_decrypts_iv_prefixed_aes_256_cbc_value(self):
        self.assertEqual(MASTER_URL, decrypt_video_url(encrypted_url(), KEY))

    def test_rejects_non_allowlisted_urls_and_redirect_tricks(self):
        invalid = [
            "http://cossora.stream/a.m3u8",
            "https://evil.example/a.m3u8",
            "https://cossora.stream.evil.example/a.m3u8",
            "https://user@cossora.stream/a.m3u8",
            "https://cossora.stream:444/a.m3u8",
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(InvalidVideoSource):
                validate_upstream_url(value)


class VideoServiceTests(unittest.TestCase):
    def make_service(self, responses, **kwargs):
        calls = []

        def factory():
            return FakeRequestSession(responses, calls)

        service = VideoService(FakeCrawler(), session_factory=factory, **kwargs)
        return service, calls

    def test_creates_hls_session_from_registered_article_video(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        service, calls = self.make_service({embed: FakeResponse(player_html())})

        local_url = service.create_video_session("demo slug", 0)

        self.assertRegex(local_url, r"^/video/[^/]+/[^/]+$")
        method, url, options = calls[0]
        self.assertEqual(("GET", embed), (method, url))
        self.assertEqual("https://cosplaytele.com/", options["headers"]["Referer"])
        self.assertEqual({"http": "http://127.0.0.1:7890",
                          "https": "http://127.0.0.1:7890"}, options["proxies"])

    def test_missing_article_or_video_is_not_a_proxy_target(self):
        service, calls = self.make_service({})

        for slug, index in (("missing", 0), ("demo slug", 1)):
            with self.subTest(slug=slug, index=index), self.assertRaises(ResourceNotFound):
                service.create_video_session(slug, index)
        self.assertEqual([], calls)

    def test_rewrites_manifest_lines_and_uri_attributes_to_registered_resources(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        manifest = (b"#EXTM3U\n"
                    b"#EXT-X-KEY:METHOD=AES-128,URI=\"master_m3u8.key\"\n"
                    b"#EXT-X-MAP:URI='init.mp4'\n"
                    b"https://hls-cdn.cossora.stream/media/segment0001.png\n")
        responses = {
            embed: FakeResponse(player_html()),
            MASTER_URL: FakeResponse(manifest, headers={"Content-Type": "application/vnd.apple.mpegurl"}),
        }
        service, _calls = self.make_service(responses)
        root = service.create_video_session("demo slug", 0)
        session_id, resource_id = root.split("/")[2:4]

        response = service.open_resource(session_id, resource_id, "GET", None, "browser token")
        body = b"".join(response.iter_body()).decode("utf-8")
        response.close()

        self.assertNotIn("master_m3u8.key", body)
        self.assertNotIn("hls-cdn.cossora.stream", body)
        rewritten = [line for line in body.splitlines() if line.startswith("/video/")][0]
        self.assertEqual(["browser token"], parse_qs(urlparse(rewritten).query)["token"])
        self.assertRegex(body, r'URI="/video/[^?]+\?token=browser%20token"')
        self.assertRegex(body, r"URI='/video/[^?]+\?token=browser%20token'")

    def test_streams_image_png_segment_and_forwards_single_range(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        segment_url = "https://hls-cdn.cossora.stream/media/segment0001.png"
        manifest = ("#EXTM3U\n" + segment_url + "\n").encode("utf-8")
        segment = FakeResponse(status=206,
                               headers={"Content-Type": "image/png",
                                        "Content-Length": "6",
                                        "Content-Range": "bytes 4-9/20",
                                        "Accept-Ranges": "bytes"},
                               chunks=[b"abc", b"def"])
        responses = {
            embed: FakeResponse(player_html()),
            MASTER_URL: FakeResponse(manifest, headers={"Content-Type": "application/vnd.apple.mpegurl"}),
            segment_url: segment,
        }
        service, calls = self.make_service(responses)
        root = service.create_video_session("demo slug", 0)
        session_id, root_id = root.split("/")[2:4]
        manifest_response = service.open_resource(session_id, root_id, "GET", None, "")
        local_segment = [line for line in b"".join(manifest_response.iter_body()).decode().splitlines()
                         if line.startswith("/video/")][0]
        segment_id = urlparse(local_segment).path.split("/")[3]

        response = service.open_resource(session_id, segment_id, "GET", "bytes=4-9", "")
        self.assertEqual(206, response.status)
        self.assertEqual("image/png", response.headers["Content-Type"])
        self.assertEqual(b"abcdef", b"".join(response.iter_body()))
        response.close()

        self.assertEqual("bytes=4-9", calls[-1][2]["headers"]["Range"])
        self.assertTrue(segment.closed)

    def test_forwards_unsatisfied_range_status_and_content_range(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        unsatisfied = FakeResponse(
            status=416, headers={"Content-Range": "bytes */20", "Content-Length": "0"})
        responses = {embed: FakeResponse(player_html()), MASTER_URL: unsatisfied}
        service, _calls = self.make_service(responses)
        root = service.create_video_session("demo slug", 0)
        session_id, resource_id = root.split("/")[2:4]

        response = service.open_resource(
            session_id, resource_id, "GET", "bytes=100-200", "")

        self.assertEqual(416, response.status)
        self.assertEqual("bytes */20", response.headers["Content-Range"])
        response.close()
        self.assertTrue(unsatisfied.closed)

    def test_rejects_reversed_or_multiple_ranges_before_upstream_request(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        service, calls = self.make_service({embed: FakeResponse(player_html())})
        root = service.create_video_session("demo slug", 0)
        session_id, resource_id = root.split("/")[2:4]
        initial_calls = len(calls)

        for range_value in ("bytes=10-5", "bytes=0-1,4-5", "bytes=-0"):
            with self.subTest(range_value=range_value), self.assertRaises(InvalidVideoSource):
                service.open_resource(
                    session_id, resource_id, "GET", range_value, "")
        self.assertEqual(initial_calls, len(calls))

    def test_closes_upstream_when_client_stops_consuming_stream(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        segment_url = "https://hls-cdn.cossora.stream/media/segment0001.png"
        manifest = ("#EXTM3U\n" + segment_url + "\n").encode("utf-8")
        segment = FakeResponse(headers={"Content-Type": "image/png"}, chunks=[b"a", b"b"])
        responses = {
            embed: FakeResponse(player_html()),
            MASTER_URL: FakeResponse(manifest, headers={"Content-Type": "application/vnd.apple.mpegurl"}),
            segment_url: segment,
        }
        service, _calls = self.make_service(responses)
        root = service.create_video_session("demo slug", 0)
        session_id, root_id = root.split("/")[2:4]
        manifest_response = service.open_resource(session_id, root_id, "GET", None, "")
        local_segment = [line for line in b"".join(manifest_response.iter_body()).decode().splitlines()
                         if line.startswith("/video/")][0]
        segment_id = urlparse(local_segment).path.split("/")[3]

        response = service.open_resource(session_id, segment_id, "GET", None, "")
        iterator = response.iter_body()
        self.assertEqual(b"a", next(iterator))
        response.close()

        self.assertTrue(segment.closed)

    def test_rejects_resource_after_article_video_source_changes(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        service, _calls = self.make_service({embed: FakeResponse(player_html())})
        root = service.create_video_session("demo slug", 0)
        session_id, resource_id = root.split("/")[2:4]
        service.crawler.index["posts"]["demo slug"]["videos"][0]["embed"] = (
            "https://cossora.stream/embed/changed")

        with self.assertRaises(ResourceNotFound):
            service.open_resource(session_id, resource_id, "GET", None, "")

    def test_expires_idle_sessions_and_bounds_cache(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        now = [100.0]
        service, _calls = self.make_service({embed: FakeResponse(player_html())},
                                            max_sessions=1, idle_ttl=5,
                                            clock=lambda: now[0])
        first = service.create_video_session("demo slug", 0)
        first_session = first.split("/")[2]
        now[0] += 6

        with self.assertRaises(ResourceNotFound):
            service.open_resource(first_session, first.split("/")[3], "GET", None, "")

    def test_reading_at_capacity_does_not_evict_an_existing_session(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        responses = {
            embed: FakeResponse(player_html()),
            MASTER_URL: FakeResponse(b"#EXTM3U\n", headers={
                "Content-Type": "application/vnd.apple.mpegurl",
            }),
        }
        service, _calls = self.make_service(responses, max_sessions=2)
        first = service.create_video_session("demo slug", 0)
        service.create_video_session("demo slug", 0)
        first_session, first_resource = first.split("/")[2:4]

        response = service.open_resource(
            first_session, first_resource, "GET", None, "")
        self.assertEqual(b"#EXTM3U\n", b"".join(response.iter_body()))

    def test_validates_every_redirect_before_following_it(self):
        embed = "https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31"
        responses = {
            embed: FakeResponse(status=302, headers={"Location": "https://evil.example/player"}),
        }
        service, calls = self.make_service(responses)

        with self.assertRaises(InvalidVideoSource):
            service.create_video_session("demo slug", 0)
        self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
