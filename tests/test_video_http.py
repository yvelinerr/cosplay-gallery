import http.client
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib.parse import quote

from video import InvalidVideoSource, ResourceNotFound, UpstreamError, UpstreamTimeout


class StubCrawler:
    def __init__(self, *args, **kwargs):
        self.data_dir = os.path.join(tempfile.gettempdir(), "cosplay-gallery-test-unused")
        self.proxy = None
        self.status = "idle"
        self.meta_busy = False
        self._lock = threading.RLock()
        self.index = {"posts": {}, "order": []}

    def get_stats(self):
        return {"progress": {}}


class StubVideoResponse:
    status = 206
    headers = {"Content-Type": "image/png", "Content-Length": "3",
               "Content-Range": "bytes 0-2/10", "Accept-Ranges": "bytes"}

    def __init__(self):
        self.closed = False

    def iter_body(self):
        yield b"abc"

    def close(self):
        self.closed = True


class StubVideoService:
    def __init__(self):
        self.created = []
        self.opened = []
        self.response = StubVideoResponse()
        self.create_error = None

    def create_video_session(self, slug, index):
        if self.create_error is not None:
            raise self.create_error
        self.created.append((slug, index))
        return "/video/session/root"

    def open_resource(self, session, resource, method, range_header, access_token):
        self.opened.append((session, resource, method, range_header, access_token))
        return self.response


class VideoHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import crawler as crawler_module
        with mock.patch.object(crawler_module, "Crawler", StubCrawler):
            sys.modules.pop("server", None)
            cls.server_module = importlib.import_module("server")
        cls.old_token = cls.server_module.ACCESS_TOKEN
        cls.server_module.ACCESS_TOKEN = "secret"
        cls.video_service = StubVideoService()
        cls.server_module.video_service = cls.video_service
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.server_module.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.server_module.ACCESS_TOKEN = cls.old_token

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        headers_out = dict(response.getheaders())
        conn.close()
        return response.status, headers_out, body

    def test_video_api_decodes_slug_and_returns_hls_contract(self):
        status, _headers, body = self.request(
            "GET", "/api/videos/" + quote("demo slug") + "/0?token=secret")

        self.assertEqual(200, status)
        self.assertEqual({"url": "/video/session/root", "type": "hls"},
                         json.loads(body.decode("utf-8")))
        self.assertEqual(("demo slug", 0), self.video_service.created[-1])

    def test_video_api_rejects_negative_or_non_integer_indexes(self):
        for index in ("-1", "nope"):
            with self.subTest(index=index):
                status, _headers, _body = self.request(
                    "GET", "/api/videos/demo/" + index + "?token=secret")
                self.assertEqual(400, status)

    def test_video_api_maps_service_failures_to_contract_statuses(self):
        cases = (
            (ResourceNotFound("missing"), 404),
            (InvalidVideoSource("unsupported"), 400),
            (UpstreamError("failed"), 502),
            (UpstreamTimeout("timeout"), 504),
        )
        try:
            for error, expected in cases:
                with self.subTest(error=type(error).__name__):
                    self.video_service.create_error = error
                    status, _headers, _body = self.request(
                        "GET", "/api/videos/demo/0?token=secret")
                    self.assertEqual(expected, status)
        finally:
            self.video_service.create_error = None

    def test_video_routes_inherit_authentication(self):
        for path in ("/api/videos/demo/0", "/video/session/root"):
            with self.subTest(path=path):
                status, _headers, body = self.request("GET", path)
                self.assertEqual(401, status)
                self.assertEqual("unauthorized", json.loads(body.decode("utf-8"))["error"])

    def test_video_resource_forwards_range_and_query_token(self):
        status, headers, body = self.request(
            "GET", "/video/session/resource?token=secret",
            {"Range": "bytes=0-2"})

        self.assertEqual(206, status)
        self.assertEqual(b"abc", body)
        self.assertEqual("bytes 0-2/10", headers["Content-Range"])
        self.assertEqual(("session", "resource", "GET", "bytes=0-2", "secret"),
                         self.video_service.opened[-1])
        self.assertTrue(self.video_service.response.closed)

    def test_head_video_resource_has_headers_without_body(self):
        status, headers, body = self.request(
            "HEAD", "/video/session/resource?token=secret")

        self.assertEqual(206, status)
        self.assertEqual("3", headers["Content-Length"])
        self.assertEqual(b"", body)
        self.assertEqual("HEAD", self.video_service.opened[-1][2])

    def test_only_exact_vendored_hls_path_is_public(self):
        old_static_dir = self.server_module.STATIC_DIR
        try:
            with tempfile.TemporaryDirectory() as static_dir:
                self.server_module.STATIC_DIR = static_dir
                vendor_dir = os.path.join(static_dir, "vendor")
                os.makedirs(vendor_dir)
                vendor_path = os.path.join(vendor_dir, "hls.min.js")
                with open(vendor_path, "wb") as stream:
                    stream.write(b"window.Hls={};")
                status, _headers, body = self.request("GET", "/static/vendor/hls.min.js")
                self.assertEqual(200, status)
                self.assertEqual(b"window.Hls={};", body)
                status, _headers, _body = self.request("GET", "/static/index.html")
                self.assertEqual(401, status)
        finally:
            self.server_module.STATIC_DIR = old_static_dir


if __name__ == "__main__":
    unittest.main()
