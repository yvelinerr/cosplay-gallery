# -*- coding: utf-8 -*-
"""受控的 cossora HLS 解析与按需转发。"""
import base64
import binascii
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from urllib3.exceptions import TimeoutError as UrllibTimeout


ALLOWED_HOSTS = frozenset(("cossora.stream", "hls-cdn.cossora.stream"))
HTML_LIMIT = 2 * 1024 * 1024
MANIFEST_LIMIT = 4 * 1024 * 1024
STREAM_LIMIT = 128 * 1024 * 1024
REQUEST_TIMEOUT = (8, 25)
MAX_REDIRECTS = 4
MAX_RESOURCES = 2048
RANGE_RE = re.compile(r"^bytes=(?:\d+-\d*|-\d+)$")
VIDEO_URL_RE = re.compile(
    r"\b(?:const|let|var)\s+videoURL\s*=\s*(['\"])([A-Za-z0-9+/=]+)\1")
DECRYPT_KEY_RE = re.compile(
    r"\bdecryptLink\s*\(\s*videoURL\s*,\s*(['\"])([^'\"]+)\1\s*\)")
URI_ATTRIBUTE_RE = re.compile(r"(?i)(\bURI\s*=\s*)(['\"])(.*?)\2")


class VideoError(Exception):
    status = 500


class InvalidVideoSource(VideoError):
    status = 400


class ResourceNotFound(VideoError):
    status = 404


class UpstreamError(VideoError):
    status = 502


class UpstreamTimeout(VideoError):
    status = 504


def _read_error(exc):
    pending, seen = [exc], set()
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(error, (requests.Timeout, UrllibTimeout, TimeoutError)):
            return UpstreamTimeout("上游视频读取超时")
        pending.extend(value for value in
                       (error.__cause__, error.__context__) + error.args
                       if isinstance(value, BaseException))
    return UpstreamError("上游视频读取失败")


def validate_upstream_url(url: str) -> str:
    """只允许无凭据、标准端口的固定 HTTPS 上游。"""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise InvalidVideoSource("视频来源 URL 不合法") from exc
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or not parsed.path.startswith("/")):
        raise InvalidVideoSource("不支持的视频来源")
    return url


def extract_encrypted_video(html_text: str) -> Tuple[str, str]:
    """静态提取密文和 decryptLink 的字面量密钥，不执行页面脚本。"""
    video_match = VIDEO_URL_RE.search(html_text)
    key_match = DECRYPT_KEY_RE.search(html_text)
    if not video_match or not key_match:
        raise UpstreamError("播放器页面缺少视频地址")
    return video_match.group(2), key_match.group(2)


def decrypt_video_url(encoded: str, key_text: str) -> str:
    """解开 IV 前置的 AES-256-CBC/PKCS7 播放地址。"""
    key = key_text.encode("utf-8")
    if len(key) != 32:
        raise UpstreamError("播放器密钥长度不合法")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) <= 16 or (len(raw) - 16) % 16:
            raise ValueError("invalid encrypted length")
        decryptor = Cipher(algorithms.AES(key), modes.CBC(raw[:16])).decryptor()
        padded = decryptor.update(raw[16:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        url = plaintext.decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise UpstreamError("播放器视频地址解密失败") from exc
    return validate_upstream_url(url)


def _valid_range(value: str) -> bool:
    value = value.strip()
    if not RANGE_RE.fullmatch(value):
        return False
    bounds = value[len("bytes="):]
    start, end = bounds.split("-", 1)
    if not start:
        return int(end) > 0
    return not end or int(start) <= int(end)


@dataclass
class _Resource:
    url: str
    referer: str


@dataclass
class _PlaybackSession:
    slug: str
    video_index: int
    embed: str
    touched_at: float
    resources: Dict[str, _Resource] = field(default_factory=dict)
    resource_ids: Dict[Tuple[str, str], str] = field(default_factory=dict)


class VideoResponse:
    """HTTP 层可消费并显式关闭的上游响应。"""

    def __init__(self, status: int, headers: Dict[str, str], body: Optional[bytes] = None,
                 upstream=None, request_session=None, max_bytes: int = STREAM_LIMIT):
        self.status = status
        self.headers = headers
        self._body = body
        self._upstream = upstream
        self._request_session = request_session
        self._max_bytes = max_bytes
        self._closed = False

    def iter_body(self) -> Iterator[bytes]:
        if self._body is not None:
            if self._body:
                yield self._body
            return
        if self._upstream is None:
            return
        total = 0
        # Preserve the wire representation when forwarding encoding and length.
        if self.headers.get("Content-Encoding", "identity").lower() != "identity":
            chunks = self._upstream.raw.stream(65536, decode_content=False)
        else:
            chunks = self._upstream.iter_content(65536)
        for chunk in chunks:
            if not chunk:
                continue
            total += len(chunk)
            if total > self._max_bytes:
                raise UpstreamError("上游媒体响应超过大小限制")
            yield chunk

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._upstream is not None:
            self._upstream.close()
        if self._request_session is not None:
            self._request_session.close()


class VideoService:
    def __init__(self, crawler, session_factory: Callable = requests.Session,
                 max_sessions: int = 64, idle_ttl: float = 15 * 60,
                 clock: Callable[[], float] = time.monotonic):
        self.crawler = crawler
        self.session_factory = session_factory
        self.max_sessions = max(1, max_sessions)
        self.idle_ttl = max(1.0, idle_ttl)
        self.clock = clock
        self._lock = threading.RLock()
        self._sessions = OrderedDict()

    def _article_snapshot(self, slug: str, video_index: int):
        with self.crawler._lock:
            post = self.crawler.index.get("posts", {}).get(slug)
            if not post:
                raise ResourceNotFound("文章不存在")
            videos = post.get("videos", [])
            if video_index < 0 or video_index >= len(videos):
                raise ResourceNotFound("视频不存在")
            embed = videos[video_index].get("embed", "")
            article_url = post.get("url", "")
            proxy = self.crawler.proxy
        return embed, article_url, proxy

    def _proxy_snapshot(self):
        with self.crawler._lock:
            proxy = self.crawler.proxy
        if not proxy:
            return None
        return {"http": proxy, "https": proxy}

    def _purge_locked(self, now: float):
        expired = [key for key, value in self._sessions.items()
                   if now - value.touched_at > self.idle_ttl]
        for key in expired:
            self._sessions.pop(key, None)

    def _register_resource_locked(self, session_id: str, session: _PlaybackSession,
                                  url: str, referer: str) -> str:
        validate_upstream_url(url)
        key = (url, referer)
        existing = session.resource_ids.get(key)
        if existing:
            return existing
        if len(session.resources) >= MAX_RESOURCES:
            raise UpstreamError("播放清单资源过多")
        resource_id = secrets.token_urlsafe(18)
        session.resources[resource_id] = _Resource(url=url, referer=referer)
        session.resource_ids[key] = resource_id
        return resource_id

    @staticmethod
    def _source_referer(article_url: str) -> str:
        parsed = urlparse(article_url)
        if parsed.scheme == "https" and parsed.hostname == "cosplaytele.com":
            return "https://cosplaytele.com/"
        raise InvalidVideoSource("文章来源不受支持")

    def create_video_session(self, slug: str, video_index: int) -> str:
        embed, article_url, proxy = self._article_snapshot(slug, video_index)
        validate_upstream_url(embed)
        parsed_embed = urlparse(embed)
        if not parsed_embed.path.startswith("/embed/"):
            raise InvalidVideoSource("不支持的视频来源")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response, request_session, _final_url = self._open_upstream(
            "GET", embed, self._source_referer(article_url), None, proxies)
        try:
            body = self._read_limited(response, HTML_LIMIT)
        finally:
            response.close()
            request_session.close()
        ciphertext, key = extract_encrypted_video(body.decode("utf-8", errors="replace"))
        master_url = decrypt_video_url(ciphertext, key)

        now = self.clock()
        session_id = secrets.token_urlsafe(18)
        playback = _PlaybackSession(slug, video_index, embed, now)
        with self._lock:
            self._purge_locked(now)
            while len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)
            self._sessions[session_id] = playback
            resource_id = self._register_resource_locked(
                session_id, playback, master_url, embed)
        return "/video/{}/{}".format(session_id, resource_id)

    def _lookup_resource(self, session_id: str, resource_id: str):
        now = self.clock()
        with self._lock:
            self._purge_locked(now)
            session = self._sessions.get(session_id)
            if not session:
                raise ResourceNotFound("播放会话不存在或已过期")
            resource = session.resources.get(resource_id)
            if not resource:
                raise ResourceNotFound("播放资源不存在")
            session.touched_at = now
            self._sessions.move_to_end(session_id)
            identity = (session.slug, session.video_index, session.embed)
        try:
            current_embed, _article_url, _proxy = self._article_snapshot(
                identity[0], identity[1])
        except ResourceNotFound:
            with self._lock:
                self._sessions.pop(session_id, None)
            raise
        if current_embed != identity[2]:
            with self._lock:
                self._sessions.pop(session_id, None)
            raise ResourceNotFound("视频来源已变更")
        return session, resource

    def open_resource(self, session_id: str, resource_id: str, method: str,
                      range_header: Optional[str], access_token: str) -> VideoResponse:
        if method not in ("GET", "HEAD"):
            raise InvalidVideoSource("不支持的请求方法")
        if range_header and not _valid_range(range_header):
            raise InvalidVideoSource("Range 请求不合法")
        session, resource = self._lookup_resource(session_id, resource_id)
        known_manifest = urlparse(resource.url).path.lower().endswith(".m3u8")
        extra_headers = ({"Range": range_header.strip()}
                         if range_header and not known_manifest else None)
        response, request_session, final_url = self._open_upstream(
            "GET" if known_manifest else method,
            resource.url, resource.referer, extra_headers,
            self._proxy_snapshot())
        status = response.status_code
        if status == 416:
            return self._stream_response(response, request_session, status)
        if status < 200 or status >= 300:
            response.close()
            request_session.close()
            raise UpstreamError("上游媒体请求失败")

        content_type = response.headers.get("Content-Type", "")
        is_manifest = (urlparse(final_url).path.lower().endswith(".m3u8")
                       or "mpegurl" in content_type.lower())
        if is_manifest:
            # A partial upstream playlist cannot be safely rewritten.
            if not known_manifest and (method == "HEAD" or range_header):
                response.close()
                request_session.close()
                response, request_session, final_url = self._open_upstream(
                    "GET", resource.url, resource.referer, None, self._proxy_snapshot())
                status = response.status_code
            if status != 200:
                response.close()
                request_session.close()
                raise UpstreamError("上游未返回完整播放清单")
            try:
                body = self._read_limited(response, MANIFEST_LIMIT)
            finally:
                response.close()
                request_session.close()
            if not body.lstrip().startswith(b"#EXTM3U"):
                raise UpstreamError("上游播放清单格式错误")
            rewritten = self._rewrite_manifest(
                session_id, session, final_url,
                body.decode("utf-8", errors="replace"), access_token)
            data = rewritten.encode("utf-8")
            return VideoResponse(200, {
                "Content-Type": "application/vnd.apple.mpegurl",
                "Content-Length": str(len(data)),
            }, body=b"" if method == "HEAD" else data)
        return self._stream_response(response, request_session, status,
                                     empty_body=(method == "HEAD"))

    def _rewrite_manifest(self, session_id: str, session: _PlaybackSession,
                          manifest_url: str, text: str, access_token: str) -> str:
        def local_url(uri: str) -> str:
            absolute = urljoin(manifest_url, uri)
            validate_upstream_url(absolute)
            with self._lock:
                current = self._sessions.get(session_id)
                if current is not session:
                    raise ResourceNotFound("播放会话不存在或已过期")
                resource_id = self._register_resource_locked(
                    session_id, session, absolute, manifest_url)
            value = "/video/{}/{}".format(session_id, resource_id)
            if access_token:
                value += "?token=" + quote(access_token, safe="")
            return value

        output = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                prefix = line[:len(line) - len(line.lstrip())]
                suffix = line[len(line.rstrip()):]
                line = prefix + local_url(stripped) + suffix
            elif stripped.startswith("#") and "URI" in line.upper():
                line = URI_ATTRIBUTE_RE.sub(
                    lambda match: match.group(1) + match.group(2)
                    + local_url(match.group(3)) + match.group(2), line)
            output.append(line)
        result = "\n".join(output)
        if text.endswith(("\n", "\r")):
            result += "\n"
        return result

    def _open_upstream(self, method: str, url: str, referer: str,
                       extra_headers: Optional[Dict[str, str]], proxies):
        current = validate_upstream_url(url)
        request_session = self.session_factory()
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0 Safari/537.36"),
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Referer": referer,
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            for _redirect in range(MAX_REDIRECTS + 1):
                try:
                    response = request_session.request(
                        method, current, headers=headers, proxies=proxies,
                        timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=False)
                except requests.Timeout as exc:
                    raise UpstreamTimeout("上游视频请求超时") from exc
                except requests.RequestException as exc:
                    raise UpstreamError("上游视频请求失败") from exc
                if response.status_code not in (301, 302, 303, 307, 308):
                    return response, request_session, current
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise UpstreamError("上游重定向缺少地址")
                current = validate_upstream_url(urljoin(current, location))
            raise UpstreamError("上游重定向次数过多")
        except Exception:
            request_session.close()
            raise

    @staticmethod
    def _read_limited(response, limit: int) -> bytes:
        try:
            declared = int(response.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            declared = 0
        if declared > limit:
            raise UpstreamError("上游响应超过大小限制")
        data = bytearray()
        try:
            for chunk in response.iter_content(65536):
                if not chunk:
                    continue
                data.extend(chunk)
                if len(data) > limit:
                    raise UpstreamError("上游响应超过大小限制")
        except requests.RequestException as exc:
            raise _read_error(exc) from exc
        return bytes(data)

    @staticmethod
    def _stream_response(response, request_session, status: int,
                         empty_body: bool = False) -> VideoResponse:
        headers = {}
        for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges",
                     "Content-Encoding"):
            value = response.headers.get(name)
            if value is not None:
                headers[name] = value
        try:
            declared = int(headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            declared = 0
        if declared > STREAM_LIMIT:
            response.close()
            request_session.close()
            raise UpstreamError("上游媒体响应超过大小限制")
        return VideoResponse(status, headers, body=b"" if empty_body else None,
                             upstream=response, request_session=request_session)
