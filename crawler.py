# -*- coding: utf-8 -*-
"""
cosplaytele.com 图片爬虫模块（零第三方依赖，仅 requests）

功能：
- 遍历列表页（首页 / page/N），解析文章卡片链接
- 抓取文章详情页正文图片（attachment-full 大图）
- 并发下载图片到本地 data/images/<slug>/ 目录
- 断点续爬：索引记录已完成文章，重启后跳过
- 支持代理（默认 http://127.0.0.1:7890）
"""
import html as html_mod
import json
import os
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DEFAULT_PROXY = "http://127.0.0.1:7890"
SITE = "https://cosplaytele.com"

# 正文图片：WordPress attachment-full 大图（不含 wp-post-image 相关文章缩略图）
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
# 列表页卡片主链接（封面 <a> 带 class="plain"，导航链接无此特征）
CARD_LINK_RE = re.compile(r'href="(https://cosplaytele\.com/[^"/]+/)"\s+class="plain"', re.I)
TITLE_RE = re.compile(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', re.S | re.I)
ARIA_TITLE_RE = re.compile(r'aria-label="([^"]+)"')
VIDEO_HINT_RE = re.compile(r'"(\d+)\s*(?:photos?|pics|images?)\s*(?:and|&amp;)?\s*"?(\d+)?\s*videos?', re.I)
# 标签/分类链接：/tag/<slug>/ 与 /category/<slug>/
TAG_LINK_RE = re.compile(
    r'href="https://cosplaytele\.com/tag/([^"/]+)/"[^>]*>([^<]+)<', re.I)
CAT_LINK_RE = re.compile(
    r'href="https://cosplaytele\.com/category/([^"/]+)/"[^>]*>([^<]+)<', re.I)
# 正文 blockquote 中的字段（部分文章为纯文本，无链接）
BLOCK_ITEM_RE = re.compile(
    r"<strong>(Character|Appear In|Cosplayer):\s*(.*?)</strong>", re.S | re.I)
BLOCKQUOTE_RE = re.compile(r"<blockquote>(.*?)</blockquote>", re.S | re.I)
# 视频 iframe（cossora 播放器）
VIDEO_IFRAME_RE = re.compile(
    r'<iframe\b[^>]*src="(https://cossora\.stream/embed/[^"]+)"', re.I)


def sanitize_filename(name: str) -> str:
    """清洗文件名，去掉 Windows 非法字符。"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "image"


def slugify(slug: str) -> str:
    """生成标签/目录 slug：保留 Unicode 字母数字，空白转连字符。"""
    slug = re.sub(r"[\s_]+", "-", str(slug).strip())
    slug = re.sub(r"[^\w\-]+", "", slug, flags=re.UNICODE)
    slug = slug.strip("-").lower()
    return slug or "post"


class Crawler:
    """cosplaytele.com 爬虫。"""

    def __init__(self, data_dir: str, proxy: str = DEFAULT_PROXY,
                 concurrency: int = 4, delay: float = 0.35):
        self.data_dir = data_dir
        self.images_dir = os.path.join(data_dir, "images")
        self.index_path = os.path.join(data_dir, "index.json")
        os.makedirs(self.images_dir, exist_ok=True)

        self.proxy = proxy or None
        self.concurrency = concurrency
        self.delay = delay

        self.session = requests.Session()
        retry = Retry(total=3, connect=3, read=3, backoff_factor=1.5,
                      status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

        self._lock = threading.RLock()     # 索引与状态写锁（可重入，防嵌套死锁）
        self._stop = threading.Event()
        self.meta_busy = False                 # 标签补全任务进行中标记
        self.status = "idle"                   # idle | running | stopping | done | error
        self.log_lines = []
        self._disk_total = 0                  # 磁盘占用（增量维护，避免全盘遍历）
        self._disk_ready = False
        self._disk_lock = threading.Lock()
        self.progress = {
            "list_page": 0, "list_total": 0,
            "posts_found": 0, "posts_done": 0, "posts_skipped": 0,
            "images_total": 0, "images_done": 0,
            "current_url": "", "errors": 0,
            "started_at": None, "finished_at": None,
        }

        self.index = {"version": 1, "posts": {}, "order": []}
        self._load_index()

    # ---------- 基础工具 ----------
    def _headers(self, referer: str = None):
        h = {"User-Agent": UA, "Accept": "*/*"}
        if referer:
            h["Referer"] = referer
        return h

    def log(self, msg: str):
        line = time.strftime("%H:%M:%S") + " " + msg
        with self._lock:
            self.log_lines.append(line)
            if len(self.log_lines) > 500:
                self.log_lines = self.log_lines[-500:]

    def fetch(self, url: str, referer: str = None, timeout=(15, 60)):
        """带重试的 GET，返回 response（流式读取，可及时响应停止信号）。
        timeout 为 (连接超时, 读取超时)。"""
        if self._stop.is_set():
            raise InterruptedError("已停止")
        resp = self.session.get(url, headers=self._headers(referer),
                                proxies=self._proxies(), timeout=timeout,
                                stream=True)
        resp.raise_for_status()
        buf = bytearray()
        try:
            for chunk in resp.iter_content(65536):
                if self._stop.is_set():
                    raise InterruptedError("已停止")
                buf.extend(chunk)
        except InterruptedError:
            resp.close()
            raise
        resp._content = bytes(buf)  # 供 resp.text / resp.content 使用
        return resp

    def _proxies(self):
        if self.proxy:
            return {"http": self.proxy, "https": self.proxy}
        return None

    # ---------- 索引 ----------
    def _load_index(self):
        try:
            with open(self.index_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") == 1 and "posts" in data:
                self.index = data
        except Exception:
            self.index = {"version": 1, "posts": {}, "order": []}

    def _save_index(self):
        tmp = self.index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.index_path)

    def _disk_usage(self):
        """磁盘占用：惰性全量初始化一次，之后通过 add/remove 增量维护（O(1)）。"""
        if not self._disk_ready:
            with self._disk_lock:
                if not self._disk_ready:
                    total = 0
                    try:
                        for root, _dirs, files in os.walk(self.images_dir):
                            for fn in files:
                                try:
                                    total += os.path.getsize(os.path.join(root, fn))
                                except OSError:
                                    pass
                    except OSError:
                        pass
                    self._disk_total = total
                    self._disk_ready = True
        return self._disk_total

    def _add_disk(self, size):
        with self._disk_lock:
            self._disk_ready = True
            self._disk_total += size

    def _remove_disk(self, size):
        with self._disk_lock:
            self._disk_total = max(0, self._disk_total - size)

    def _dir_size(self, path):
        total = 0
        for root, _dirs, files in os.walk(path):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        return total

    def get_stats(self):
        posts = self.index["posts"]
        total = sum(p.get("count", 0) for p in posts.values())
        disk = self._disk_usage()
        return {
            "status": self.status,
            "meta_busy": self.meta_busy,
            "posts": len(posts),
            "images": total,
            "deleted": len(self.index.get("deleted", [])),
            "disk_usage": disk,
            "progress": dict(self.progress),
            "log": list(self.log_lines[-200:]),
        }

    # ---------- 解析 ----------
    def parse_list(self, html_text: str):
        """解析列表页，返回文章 URL 列表（保持页面顺序、去重）。"""
        urls = CARD_LINK_RE.findall(html_text)
        return list(dict.fromkeys(urls))

    @staticmethod
    def max_page(html_text: str):
        """解析分页最大页码。"""
        nums = [int(n) for n in re.findall(r'page/(\d+)/', html_text)]
        return max(nums) if nums else 1

    def parse_post(self, html_text: str, url: str):
        """解析文章页，返回 dict(title, images[urls], cover, tags, categories)。"""
        # 标题
        title = None
        m = TITLE_RE.search(html_text)
        if m:
            title = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if not title:
            m = re.search(r"<title>(.*?)</title>", html_text, re.S)
            if m:
                title = html_mod.unescape(m.group(1)).strip()
        if not title:
            title = url.rstrip("/").rsplit("/", 1)[-1]

        # 正文区域：entry-content 到 comments-area
        start = html_text.find('class="entry-content single-page"')
        end = html_text.find("comments-area", start if start > 0 else 0)
        region = html_text[start:end] if start > 0 and end > start else html_text

        images = []
        for tag in IMG_TAG_RE.findall(region):
            cls = (re.search(r'class="([^"]*)"', tag) or [None, ""])[1]
            if "attachment-full" not in cls and "size-full" not in cls:
                continue
            if "wp-post-image" in cls:
                continue
            m = re.search(r'src="([^"]+)"', tag)
            if m and m.group(1).startswith("http"):
                images.append(m.group(1))
        # 去重保序
        seen, uniq = set(), []
        for u in images:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        cover = uniq[0] if uniq else None

        # 标签与分类（正文中的 Character/Appear In 及文章尾部均为此形式）
        def _links(pat):
            out = []
            for m in pat.finditer(html_text):
                pair = (m.group(1), html_mod.unescape(m.group(2)).strip())
                if pair not in out:
                    out.append(pair)
            return out

        all_categories = _links(CAT_LINK_RE)
        tags = _links(TAG_LINK_RE)

        # Coser：正文 blockquote 中 Cosplayer 字段（链接或纯文本），
        # 与"分类"分开，便于单独筛选。
        cosers = []
        block = BLOCKQUOTE_RE.search(html_text)
        if block:
            bq = block.group(1)
            m = re.search(r"<strong>Cosplayer:\s*(.*?)</strong>", bq, re.S | re.I)
            if m:
                content = m.group(1)
                text = html_mod.unescape(re.sub(r"<[^>]+>", "", content)).strip()
                if text:
                    lm = re.search(
                        r'href="https://cosplaytele\.com/category/([^"/]+)/"', content)
                    slug = lm.group(1) if lm else slugify(text)
                    cosers.append((slug, text))

        coser_slugs = {s for s, _ in cosers}
        # 分类：排除 Coser 链接后剩余的文章分类
        categories = [(s, n) for s, n in all_categories if s not in coser_slugs]

        # 部分文章的 Character/Appear In 是纯文本（无链接），
        # 此时把字段值也作为标签，方便按角色/出处筛选。
        if block:
            known = ({n for _, n in tags} | {n for _, n in categories}
                     | {n for _, n in cosers})
            for m in BLOCK_ITEM_RE.finditer(block.group(1)):
                content = re.sub(r"<[^>]+>", "", m.group(2))
                value = html_mod.unescape(content).strip()
                if not value or value in known:
                    continue
                tags.append((slugify(value), value))
                known.add(value)

        # 视频：文章正文中的 cossora 播放器 iframe
        videos = []
        for m in VIDEO_IFRAME_RE.finditer(region):
            vid = m.group(1).rstrip("/").rsplit("/", 1)[-1]
            videos.append({"id": vid, "embed": m.group(1)})
        # 去重
        seen_v, uniq_v = set(), []
        for v in videos:
            if v["id"] not in seen_v:
                seen_v.add(v["id"])
                uniq_v.append(v)
        videos = uniq_v

        return {"title": title, "images": uniq, "cover": cover,
                "tags": tags, "categories": categories, "cosers": cosers,
                "videos": videos}

    # ---------- 下载 ----------
    def download_image(self, img_url: str, dest: str, referer: str = None):
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return True
        resp = self.session.get(img_url, headers=self._headers(referer),
                                proxies=self._proxies(), timeout=(15, 90),
                                stream=True)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "text" in ctype or "html" in ctype:
            raise RuntimeError(f"非图片响应: {ctype}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(65536):
                if self._stop.is_set():
                    raise InterruptedError("已停止")
                f.write(chunk)
        os.replace(tmp, dest)
        return True

    def _ext_from_url(self, url: str) -> str:
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
            return ext
        return ".webp"

    def crawl_post(self, post_url: str):
        """爬取单篇文章：解析 + 下载全部正文图。
        已在索引中的文章与已删除的文章都会被跳过，不会重复下载。"""
        slug = post_url.rstrip("/").rsplit("/", 1)[-1]
        slug = slugify(slug)
        with self._lock:
            if slug in self.index["posts"]:
                self.progress["posts_skipped"] += 1
                return None
            deleted_slugs = {d.get("slug") for d in self.index.get("deleted", [])}
        if slug in deleted_slugs:
            with self._lock:
                self.progress["posts_skipped"] += 1
            self.log(f"跳过（用户已删除）: {post_url}")
            return None

        html_text = self.fetch(post_url, referer=SITE).text
        info = self.parse_post(html_text, post_url)
        if not info["images"]:
            self.log(f"跳过（无图片）: {post_url}")
            return {"slug": slug, "count": 0}

        post_dir = os.path.join(self.images_dir, slug)
        os.makedirs(post_dir, exist_ok=True)
        base = sanitize_filename(info["title"])[:80]

        local_images = []
        total = len(info["images"])
        with self._lock:
            self.progress["images_total"] += total

        def one(idx_url):
            idx, img_url = idx_url
            ext = self._ext_from_url(img_url)
            fname = f"{idx:04d}_{base}{ext}"
            dest = os.path.join(post_dir, fname)
            try:
                self.download_image(img_url, dest, referer=post_url)
                try:
                    self._add_disk(os.path.getsize(dest))
                except OSError:
                    pass
                return os.path.relpath(dest, self.data_dir).replace("\\", "/"), True, None
            except InterruptedError:
                raise
            except Exception as e:
                return None, False, f"{img_url}: {e}"

        ok = 0
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futs = [pool.submit(one, (i, u)) for i, u in enumerate(info["images"], 1)]
            for fut in as_completed(futs):
                if self._stop.is_set():
                    for f2 in futs:
                        f2.cancel()
                    raise InterruptedError("已停止")
                rel, good, err = fut.result()
                if good and rel:
                    local_images.append(rel)
                    ok += 1
                    with self._lock:
                        self.progress["images_done"] += 1
                elif err:
                    with self._lock:
                        self.progress["errors"] += 1
                    self.log("下载失败 " + err)

        # 只保留成功下载的，按序号排序
        local_images.sort()

        record = {
            "slug": slug,
            "url": post_url,
            "title": info["title"],
            "cover": local_images[0] if local_images else None,
            "count": len(local_images),
            "images": local_images,
            "tags": [{"slug": s, "name": n} for s, n in info["tags"]],
            "categories": [{"slug": s, "name": n} for s, n in info["categories"]],
            "cosers": [{"slug": s, "name": n} for s, n in info["cosers"]],
            "videos": info["videos"],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._lock:
            self.index["posts"][slug] = record
            self.index["order"].insert(0, slug)  # 新文章在前
            self.progress["posts_done"] += 1
            self._save_index()
        self.log(f"完成: {info['title'][:40]} 共 {len(local_images)} 张")
        return record

    def refresh_meta_all(self):
        """遍历索引中已有文章，重新抓取页面补全/更新标签与分类（不重下图片）。"""
        with self._lock:
            slugs = list(self.index["posts"].keys())
        done, failed = 0, 0
        self.log(f"开始补全标签元数据，共 {len(slugs)} 篇…")
        for slug in slugs:
            if self._stop.is_set():
                break
            rec = self.index["posts"].get(slug)
            if not rec:
                continue
            try:
                html_text = self.fetch(rec["url"], referer=SITE).text
                info = self.parse_post(html_text, rec["url"])
                with self._lock:
                    rec["tags"] = [{"slug": s, "name": n} for s, n in info["tags"]]
                    rec["categories"] = [{"slug": s, "name": n} for s, n in info["categories"]]
                    rec["cosers"] = [{"slug": s, "name": n} for s, n in info["cosers"]]
                    rec["videos"] = info["videos"]
                done += 1
                time.sleep(self.delay)
            except InterruptedError:
                break
            except Exception as e:
                failed += 1
                self.log(f"补全标签失败 {rec['url']}: {e}")
        with self._lock:
            self._save_index()
        self.log(f"标签补全结束：成功 {done} 篇，失败 {failed} 篇")
        return done, failed

    # ---------- 删除 / 恢复 ----------
    def delete_post(self, slug: str) -> bool:
        """删除文章：从索引移除并删除本地图片，slug 记入已删除列表，
        后续爬取到同一篇文章时会跳过，不会重新下载。"""
        with self._lock:
            rec = self.index["posts"].get(slug)
            if not rec:
                return False
            # 记入已删除（先去重再追加）
            deleted = [d for d in self.index.get("deleted", [])
                       if d.get("slug") != slug]
            deleted.append({
                "slug": slug,
                "url": rec["url"],
                "title": rec["title"],
                "deleted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            self.index["deleted"] = deleted
            del self.index["posts"][slug]
            if slug in self.index["order"]:
                self.index["order"].remove(slug)
            self._save_index()
        # 删除本地图片目录（IO 慢，放锁外），并从磁盘统计中扣除
        post_dir = os.path.join(self.images_dir, slug)
        if os.path.isdir(post_dir):
            removed = self._dir_size(post_dir)
            shutil.rmtree(post_dir, ignore_errors=True)
            self._remove_disk(removed)
        self.log(f"已删除图集: {rec.get('title', slug)[:40]}")
        return True

    def restore_post(self, slug: str) -> bool:
        """恢复已删除的文章（仅从已删除列表移除；下次爬取会重新下载）。"""
        with self._lock:
            deleted = self.index.get("deleted", [])
            newd = [d for d in deleted if d.get("slug") != slug]
            if len(newd) == len(deleted):
                return False
            self.index["deleted"] = newd
            self._save_index()
        self.log(f"已恢复（下次爬取会重新下载）: {slug}")
        return True

    def get_deleted(self):
        """返回已删除文章列表。"""
        with self._lock:
            return list(self.index.get("deleted", []))

    # ---------- 主流程 ----------
    def run(self, entry_url: str = SITE, start_page: int = 1,
            end_page: int = None, stop_event: threading.Event = None):
        """开始爬取。entry_url 为入口列表页（首页或分类页）。"""
        if self.status == "running":
            return
        self._stop.clear()
        if stop_event:
            self._stop = stop_event
        else:
            self._stop = threading.Event()
        self.status = "running"
        self.progress.update({
            "list_page": 0, "list_total": 0,
            "posts_found": 0, "posts_done": 0, "posts_skipped": 0,
            "images_total": 0, "images_done": 0,
            "current_url": "", "errors": 0,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "finished_at": None,
        })
        self.log(f"开始爬取: {entry_url}")
        try:
            # 计算总页数
            base = entry_url
            if not base.endswith("/"):
                base += "/"
            first = self.fetch(entry_url).text
            total_pages = self.max_page(first)
            if end_page and end_page < total_pages:
                total_pages = end_page
            self.progress["list_total"] = total_pages

            start_page = max(1, start_page)
            for page_no in range(start_page, total_pages + 1):
                if self._stop.is_set():
                    self.log("收到停止信号，正在收尾…")
                    break
                page_url = entry_url if page_no == 1 else f"{base}page/{page_no}/"
                self.progress["list_page"] = page_no
                self.progress["current_url"] = page_url
                self.log(f"[{page_no}/{total_pages}] 解析列表: {page_url}")

                html_text = self.fetch(page_url).text
                post_urls = self.parse_list(html_text)
                if not post_urls:
                    self.log(f"列表页 {page_url} 未解析到文章")
                self.progress["posts_found"] += len(post_urls)

                for pu in post_urls:
                    if self._stop.is_set():
                        break
                    self.progress["current_url"] = pu
                    try:
                        self.crawl_post(pu)
                    except InterruptedError:
                        break
                    except Exception as e:
                        with self._lock:
                            self.progress["errors"] += 1
                        self.log(f"文章失败 {pu}: {e}")
                    time.sleep(self.delay)  # 礼貌限速

            self.status = "done" if not self._stop.is_set() else "stopping"
            self.progress["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log("爬取结束。"
                     f" 完成文章 {self.progress['posts_done']}，"
                     f"图片 {self.progress['images_done']}/{self.progress['images_total']}，"
                     f"跳过 {self.progress['posts_skipped']}，错误 {self.progress['errors']}")
        except InterruptedError:
            self.status = "stopping"
            self.progress["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log("已停止。")
        except Exception as e:
            self.status = "error"
            self.progress["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log(f"爬取出错: {e}")
        finally:
            if self.status == "stopping":
                self.status = "idle"
            elif self.status == "done":
                self.status = "idle"
            with self._lock:
                self._save_index()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse

    ap = argparse.ArgumentParser(description="爬取 cosplaytele.com 图片")
    ap.add_argument("--pages", type=int, default=None, help="爬取列表页数（默认全部）")
    ap.add_argument("--start", type=int, default=1, help="起始列表页")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help="代理地址，空为直连")
    ap.add_argument("--data", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
                    help="数据目录")
    ap.add_argument("--url", default=SITE, help="入口列表 URL（首页或分类页）")
    args = ap.parse_args()

    c = Crawler(data_dir=args.data, proxy=args.proxy or None)
    c.run(entry_url=args.url, start_page=args.start, end_page=args.pages)
    s = c.get_stats()
    print(json.dumps(s, ensure_ascii=False, indent=1))
