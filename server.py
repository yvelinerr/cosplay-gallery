# -*- coding: utf-8 -*-
"""
本地图库 Web 服务器（Python 标准库实现，零依赖）

功能：
- GET  /                 前端单页
- GET  /img/<path>       本地图片文件
- GET  /api/stats        统计信息
- GET  /api/posts        文章列表（分页/搜索）
- GET  /api/posts/<slug> 文章详情
- GET  /api/crawl/status 爬取进度
- POST /api/crawl/start  开始爬取 {url,start_page,end_page,proxy}
- POST /api/crawl/stop   停止爬取
"""
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from crawler import Crawler, SITE, DEFAULT_PROXY
from video import VideoError, VideoService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
# HOST=0.0.0.0 时允许局域网/公网（经内网穿透）访问；默认仅本机
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
# ACCESS_TOKEN 非空时启用访问令牌：所有 API/图片请求需携带
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "").strip()

crawler = Crawler(data_dir=DATA_DIR, proxy=DEFAULT_PROXY)
video_service = VideoService(crawler)

# 补充常见图片 MIME
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("image/jxl", ".jxl")


def _lan_ip():
    """获取本机局域网 IP（用于提示他人访问地址）。"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    server_version = "CosplayGallery/1.0"

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):
        pass  # 静默访问日志

    def _send(self, code, body: bytes, ctype="text/plain; charset=utf-8", extra=None,
              head_only=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            if not head_only and self.command != "HEAD":
                self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _authorized(self):
        """ACCESS_TOKEN 非空时校验请求令牌（header X-Access-Token 或 ?token=）。"""
        if not ACCESS_TOKEN:
            return True
        tok = self.headers.get("X-Access-Token", "")
        if not tok:
            qs = parse_qs(urlparse(self.path).query)
            tok = qs.get("token", [""])[0]
        return tok == ACCESS_TOKEN

    def _require_auth(self):
        """未授权则发送 401 并返回 False。"""
        if self._authorized():
            return True
        self._json({"error": "unauthorized", "need_token": True}, 401)
        return False

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---------- 静态与图片 ----------
    def _serve_file(self, path: str, head_only=False):
        if not os.path.isfile(path):
            return False
        ctype, _ = mimetypes.guess_type(path)
        ctype = ctype or "application/octet-stream"
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return False
        self._send(200, data, ctype,
                   {"Cache-Control": "max-age=86400"}, head_only=head_only)
        return True

    def _safe_img_path(self, rel: str):
        """把 /img/<rel> 映射到本地文件，防目录穿越。
        rel 形如 images/<slug>/<file>（相对数据目录）。"""
        rel = unquote(rel).replace("\\", "/")
        rel = os.path.normpath(rel)
        if rel.startswith("..") or os.path.isabs(rel):
            return None
        return os.path.join(crawler.data_dir, rel)

    # ---------- 路由 ----------
    def do_GET(self):
        self._do_get("GET")

    def do_HEAD(self):
        self._do_get("HEAD")

    def _do_get(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/static/vendor/hls.min.js":
            fp = os.path.join(STATIC_DIR, "vendor", "hls.min.js")
            if not self._serve_file(fp, head_only=(method == "HEAD")):
                self._json({"error": "not found"}, 404)
            return

        if path in ("/", "/index.html"):
            # 页面本身可访问，由前端负责令牌门控
            idx = os.path.join(STATIC_DIR, "index.html")
            if os.path.isfile(idx):
                with open(idx, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8",
                               head_only=(method == "HEAD"))
            else:
                self._json({"error": "缺少前端页面 static/index.html"}, 500)
            return
        if not self._require_auth():
            return
        if path.startswith("/img/"):
            fp = self._safe_img_path(path[len("/img/"):])
            if not fp or not self._serve_file(fp, head_only=(method == "HEAD")):
                self._json({"error": "not found"}, 404)
        elif path.startswith("/api/videos/"):
            self._api_video(path)
        elif path.startswith("/video/"):
            self._video_resource(path, method, qs)
        elif path == "/api/stats":
            self._json(crawler.get_stats())
        elif path == "/api/crawl/status":
            self._json(crawler.get_stats()["progress"])
        elif path == "/api/tags":
            self._api_tags()
        elif path == "/api/categories":
            self._api_categories()
        elif path == "/api/cosers":
            self._api_cosers()
        elif path == "/api/deleted":
            self._json({"deleted": crawler.get_deleted()})
        elif path == "/api/posts":
            self._api_posts(qs)
        elif path.startswith("/api/posts/"):
            slug = path[len("/api/posts/"):]
            if slug.endswith("/restore"):
                self._json({"error": "restore 需要 POST"}, 405)
            self._api_post_detail(slug)
        else:
            self._json({"error": "not found"}, 404)

    def _video_error(self, error):
        self._json({"error": str(error)}, error.status)

    def _api_video(self, path):
        tail = path[len("/api/videos/"):]
        try:
            encoded_slug, raw_index = tail.rsplit("/", 1)
            if not encoded_slug:
                raise ValueError
            index = int(raw_index)
            if index < 0:
                raise ValueError
        except ValueError:
            self._json({"error": "视频参数不合法"}, 400)
            return
        try:
            url = video_service.create_video_session(unquote(encoded_slug), index)
        except VideoError as exc:
            self._video_error(exc)
            return
        self._json({"url": url, "type": "hls"})

    def _video_resource(self, path, method, qs):
        parts = path[len("/video/"):].split("/")
        if len(parts) != 2 or not all(parts):
            self._json({"error": "not found"}, 404)
            return
        token = self.headers.get("X-Access-Token", "")
        if not token:
            token = qs.get("token", [""])[0]
        try:
            response = video_service.open_resource(
                parts[0], parts[1], method, self.headers.get("Range"), token)
        except VideoError as exc:
            self._video_error(exc)
            return
        try:
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if method != "HEAD":
                for chunk in response.iter_body():
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError, VideoError):
            pass
        finally:
            response.close()

    def do_DELETE(self):
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/posts/"):
            slug = path[len("/api/posts/"):].rstrip("/")
            self._api_post_delete(slug)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/crawl/start":
            self._api_crawl_start(self._read_body())
        elif path == "/api/crawl/stop":
            self._api_crawl_stop()
        elif path == "/api/meta/refresh":
            self._api_meta_refresh()
        elif path.startswith("/api/posts/") and path.endswith("/restore"):
            slug = path[len("/api/posts/"):-len("/restore")]
            self._api_post_restore(slug)
        else:
            self._json({"error": "not found"}, 404)

    # ---------- API 实现 ----------
    def _api_posts(self, qs):
        try:
            page = max(1, int(qs.get("page", ["1"])[0]))
        except ValueError:
            page = 1
        try:
            per_page = min(200, max(1, int(qs.get("per_page", ["48"])[0])))
        except ValueError:
            per_page = 48
        q = (qs.get("q", [""])[0] or "").strip().lower()
        # 标签多选：?tag=a,b,c （AND 语义：文章须同时包含全部选中标签）
        tag_param = (qs.get("tag", [""])[0] or "").strip()
        want_tags = [t for t in tag_param.split(",") if t] if tag_param else []
        # 分类单选：?cat=<slug>
        cat = (qs.get("cat", [""])[0] or "").strip()
        # Coser 单选：?coser=<slug>
        coser = (qs.get("coser", [""])[0] or "").strip()

        posts = crawler.index["posts"]
        order = crawler.index.get("order", [])
        items = []
        for slug in order:
            p = posts.get(slug)
            if not p:
                continue
            if q and q not in p["title"].lower() and q not in slug:
                continue
            if want_tags:
                p_tags = {t.get("slug") for t in p.get("tags", [])}
                if not all(t in p_tags for t in want_tags):
                    continue
            if cat:
                p_cats = {c.get("slug") for c in p.get("categories", [])}
                if cat not in p_cats:
                    continue
            if coser:
                p_cosers = {c.get("slug") for c in p.get("cosers", [])}
                if coser not in p_cosers:
                    continue
            items.append({
                "slug": slug, "title": p["title"],
                "cover": p.get("cover"), "count": p.get("count", 0),
                "video_count": len(p.get("videos", [])),
                "created_at": p.get("created_at", ""),
            })
        total = len(items)
        start = (page - 1) * per_page
        items = items[start:start + per_page]
        self._json({"page": page, "per_page": per_page, "total": total,
                    "items": items})

    def _api_tags(self):
        """聚合所有文章的标签，返回 [{slug, name, count}] 按数量降序（按文章去重）。"""
        counter = {}
        for p in crawler.index["posts"].values():
            seen = set()
            for t in p.get("tags", []):
                key = t.get("slug")
                if not key or key in seen:
                    continue
                seen.add(key)
                if key not in counter:
                    counter[key] = {"slug": key,
                                    "name": t.get("name") or key, "count": 0}
                counter[key]["count"] += 1
        tags = sorted(counter.values(), key=lambda x: (-x["count"], x["name"].lower()))
        self._json({"tags": tags})

    def _api_categories(self):
        """聚合所有文章的分类，返回 [{slug, name, count}] 按数量降序（按文章去重）。"""
        counter = {}
        for p in crawler.index["posts"].values():
            seen = set()
            for c in p.get("categories", []):
                key = c.get("slug")
                if not key or key in seen:
                    continue
                seen.add(key)
                if key not in counter:
                    counter[key] = {"slug": key,
                                    "name": c.get("name") or key, "count": 0}
                counter[key]["count"] += 1
        cats = sorted(counter.values(), key=lambda x: (-x["count"], x["name"].lower()))
        self._json({"categories": cats})

    def _api_cosers(self):
        """聚合所有文章的 Coser，返回 [{slug, name, count}] 按数量降序（按文章去重）。"""
        counter = {}
        for p in crawler.index["posts"].values():
            seen = set()
            for c in p.get("cosers", []):
                key = c.get("slug")
                if not key or key in seen:
                    continue
                seen.add(key)
                if key not in counter:
                    counter[key] = {"slug": key,
                                    "name": c.get("name") or key, "count": 0}
                counter[key]["count"] += 1
        cosers = sorted(counter.values(), key=lambda x: (-x["count"], x["name"].lower()))
        self._json({"cosers": cosers})

    def _api_post_delete(self, slug):
        if crawler.delete_post(slug):
            self._json({"ok": True, "message": f"已删除 {slug}"})
        else:
            self._json({"error": "文章不存在"}, 404)

    def _api_post_restore(self, slug):
        if crawler.restore_post(slug):
            self._json({"ok": True, "message": f"已恢复 {slug}，下次爬取会重新下载"})
        else:
            self._json({"error": "该文章不在已删除列表中"}, 404)

    def _api_post_detail(self, slug):
        p = crawler.index["posts"].get(slug)
        if not p:
            self._json({"error": "not found"}, 404)
        self._json({"slug": p["slug"], "title": p["title"], "url": p["url"],
                    "count": p.get("count", 0), "cover": p.get("cover"),
                    "images": p.get("images", []),
                    "tags": p.get("tags", []),
                    "categories": p.get("categories", []),
                    "cosers": p.get("cosers", []),
                    "videos": p.get("videos", []),
                    "created_at": p.get("created_at", "")})

    def _api_crawl_start(self, body):
        if crawler.status == "running":
            self._json({"error": "爬取正在进行中"}, 409)
            return
        url = (body.get("url") or SITE).strip()
        if not url.startswith("http"):
            self._json({"error": "入口 URL 不合法"}, 400)
            return
        proxy = (body.get("proxy") or "").strip() or None
        try:
            start_page = max(1, int(body.get("start_page", 1)))
        except (TypeError, ValueError):
            start_page = 1
        end_page = body.get("end_page")
        try:
            end_page = int(end_page) if end_page not in (None, "") else None
        except (TypeError, ValueError):
            end_page = None

        crawler.proxy = proxy or None
        t = threading.Thread(target=crawler.run,
                             kwargs={"entry_url": url, "start_page": start_page,
                                     "end_page": end_page}, daemon=True)
        t.start()
        self._json({"ok": True, "message": "已开始爬取"})

    def _api_crawl_stop(self):
        crawler._stop.set()
        self._json({"ok": True, "message": "已请求停止"})

    def _api_meta_refresh(self):
        """后台线程为已有文章补全标签/分类元数据。"""
        if crawler.meta_busy:
            self._json({"error": "标签补全正在进行中"}, 409)
            return
        crawler.meta_busy = True

        def worker():
            try:
                crawler.refresh_meta_all()
            finally:
                crawler.meta_busy = False

        threading.Thread(target=worker, daemon=True).start()
        self._json({"ok": True, "message": "已开始补全标签"})


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not os.path.isdir(STATIC_DIR):
        os.makedirs(STATIC_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{PORT}"
    print(f"图库服务器已启动: {url}")
    print(f"数据目录: {DATA_DIR}")
    if HOST == "0.0.0.0":
        print(f"局域网访问: http://{_lan_ip()}:{PORT}  （对方需与你同一网络）")
        print("如需公网访问，请使用内网穿透（见 README「远程访问」）。")
    if ACCESS_TOKEN:
        print(f"已启用访问令牌: {ACCESS_TOKEN}")
        print("他人访问页面时会要求输入该令牌。")
    else:
        print("注意: 未设置 ACCESS_TOKEN，任何能访问到本端口的人均可操作图库。")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
