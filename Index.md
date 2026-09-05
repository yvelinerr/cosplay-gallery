---
type: synthesis
title: "项目结构与接口索引"
summary: "按源码定位文件职责、HTTP API、爬虫方法、持久化契约和前端交互。"
tags: [index, architecture, api]
created: 2026-09-05
updated: 2026-09-06
source_count: 18
related: ["[[AGENT]]"]
status: active
question: "开发者应到哪里查找和修改项目行为？"
modules_covered: ["crawler.py", "server.py", "video.py", "static/index.html"]
---

# 项目结构与接口索引

本索引依据本地源码维护。dev1 已用临时图库验证 cossora 样例真实播放；其他来源和共享部署未作此次验收。后续每次项目变更必须按 [AGENT.md](AGENT.md) 同步更新本文件。

## 快速定位

| 开发目标 | 源码入口 / 符号 |
| --- | --- |
| HTTP 路由、鉴权、响应 | [server.py](server.py)：`Handler.do_GET/do_POST/do_DELETE`、`_authorized`、`_json` |
| 列表分页、搜索与筛选 | [server.py](server.py)：`_api_posts`；[前端](static/index.html)：`loadPosts`、`setTag/setCat/setCoser` |
| 站点列表、正文与元数据解析 | [crawler.py](crawler.py)：正则常量、`parse_list`、`max_page`、`parse_post` |
| 下载、重试、停止、增量跳过 | [crawler.py](crawler.py)：`fetch`、`download_image`、`crawl_post`、`run` |
| 索引读写、删除与恢复 | [crawler.py](crawler.py)：`_load_index/_save_index`、`delete_post/restore_post` |
| 详情、视频、灯箱与样式 | [static/index.html](static/index.html)：内联 CSS、`openPost`、`toggleVideo`、`openLb/lbStep` |
| 视频解析、清单重写、流式转发 | [video.py](video.py)：`VideoService`、`VideoResponse`；[server.py](server.py)：`_api_video`、`_video_resource` |
| 视频自动回归 | [Python 核心](tests/test_video.py)、[HTTP](tests/test_video_http.py)、[异常回归](tests/test_video_review.py)、[前端](tests/test_frontend_video.js) |
| 启动、代理、共享 | [server.py](server.py)：模块常量和 `main`；[start.bat](start.bat)；[start-share.bat](start-share.bat) |
| 用户使用 / 开发规则 | [README.md](README.md) / [AGENT.md](AGENT.md)；代理入口 [AGENTS.md](AGENTS.md) |
| 开发日志 / 断联恢复 | [dev_log/README.md](dev_log/README.md)；每个任务目录内的 plan.md、task.md、context.md |

## 文件结构

```text
cosplay-gallery/
  .gitignore             数据、令牌、日志、Python 缓存与编辑器文件排除规则
  AGENTS.md              开发代理发现入口，转到 AGENT.md
  AGENT.md               开发约定和索引同步要求
  Index.md               本文件：开发导航与接口契约
  README.md              安装、启动、用户功能和共享说明
  crawler.py             解析、下载、索引、统计、删除恢复和 CLI
  server.py              HTTP 服务、鉴权、路由、后台任务入口
  video.py               cossora 静态解密、播放会话、清单重写与媒体流
  requirements.txt       requests 与 cryptography 安装约束
  start.bat              Windows 本机启动脚本
  start-share.bat        Windows 共享启动、令牌与防火墙配置
  static/
    index.html           单页 UI，内联 CSS 和 JavaScript
    vendor/
      hls.min.js         本地固定版本 HLS.js 1.7.2
      hls.LICENSE.txt    上游版权和许可声明
      Apache-2.0.txt     许可证全文
      README.md         供应来源、版本与校验摘要
  dev_log/
    README.md            开发日志目录说明
    dev1视频在线播放/     视频播放任务：plan.md、task.md、context.md
  tests/
    __init__.py           标准库 unittest 测试包
    test_video.py         视频解析/清单/资源会话回归
    test_video_http.py    播放 HTTP 契约回归
    test_video_review.py  清单 Range、压缩字节和读取错误回归
    test_frontend_video.js 前端播放、取消和详情竞态行为回归
  data/                  运行时生成，Git 忽略；本次检查时不存在
    index.json           权威业务索引，version=1
    index.json.tmp       索引原子替换临时文件
    token.txt            共享脚本生成的访问令牌
    images/<slug>/       图集图片，文件名为序号加清洗后的标题
      *.part             图片下载中的临时文件
```

`.git/` 是版本控制元数据，不纳入业务文件清单。依赖列于 requirements.txt：requests、cryptography；代码同时使用 requests 的依赖 urllib3。tests/ 使用标准库 unittest 和 Node 内置测试运行器；Node 仅用于开发测试。无 pyproject.toml、package.json 或 CI 配置。

## 开发日志索引

每次新开发任务创建 `dev_log/dev数字任务名称/`，包含 `plan.md`（整体规划）、`task.md`（细分任务完成情况）、`context.md`（恢复开发所需上下文）。编号从 1 递增；同一任务恢复时复用目录。task.md 每完成一项立即更新一次，并同步本索引相关记录。完整规则见 [AGENT.md](AGENT.md) 和 [目录说明](dev_log/README.md)。

| 编号 | 任务 | 文档 | 状态 | 更新日期 |
| --- | --- | --- | --- | --- |
| dev1 | 视频在线播放 | [规划](dev_log/dev1视频在线播放/plan.md)、[任务](dev_log/dev1视频在线播放/task.md)、[上下文](dev_log/dev1视频在线播放/context.md) | 已完成；真实播放与回归通过，上游慢速加载限制已记录 | 2026-09-06 |

## 调用与数据流

1. `server.main` 启动 `ThreadingHTTPServer`，提供 `static/index.html`。
2. 前端 `api()` 调用 `Handler`，后者读取全局 `crawler` 的索引、状态，或启动后台线程。
3. `Crawler.run` 顺序遍历列表页与文章，单篇图片通过 `ThreadPoolExecutor` 并发下载。
4. 图片写入 `data/images/<slug>/`，单篇完成后保存 `index.json`；前端将相对图片路径转换为 `/img/<rel>`。
5. 元数据补全独立后台运行，仅重新获取 tags/categories/cosers/videos；删除写入屏蔽名单并移除本地目录，恢复只移出名单。
6. 视频点击时按文章和序号创建内存会话，静态解密来源地址；前端从本地 `/video/` 读取重写后的 HLS 清单、密钥和分片，不保存完整视频或改变业务索引。

## HTTP 接口

实现均位于 [server.py](server.py) 的 `Handler`。JSON 响应使用 UTF-8；常规成功为 HTTP 200，错误通常为 `{error: string}`。启动任务成功只表示已启动，不代表后台完成。

### 鉴权与文件

`ACCESS_TOKEN` 去除首尾空白后非空即启用鉴权。先取 `X-Access-Token`，仅当请求头为空时回退到查询参数 `token`。失败返回 401 `{error:"unauthorized", need_token:true}`。页面与固定 HLS 脚本公开，其余 GET/HEAD 及全部 POST/DELETE 均先鉴权；未识别路由在鉴权通过后为 404。HEAD 复用 GET 路由但不发送响应体。

| 方法 | 路径 | 行为 / 返回 | 实现 |
| --- | --- | --- | --- |
| GET | `/`、`/index.html` | HTML，无需令牌；前端文件缺失为 500 | `do_GET` |
| GET | `/img/<rel>` | 文件字节；rel 相对 `data/`，如 `images/<slug>/<file>`；路径校验失败或文件不存在为 404 | `_safe_img_path`、`_serve_file` |
| GET/HEAD | `/static/vendor/hls.min.js` | 固定本地脚本，无需令牌；不存在为 404，不开放其他 vendor 路径 | `_do_get` |

图片路径处理进行 URL 解码、反斜杠转换、`normpath`，拒绝 `..` 前缀和绝对路径；当前并未强制限制为 `images/` 子目录，也未做符号链接解析后的边界检查。

### 查询接口

| 方法 | 路径 | 成功响应 / 行为 | 实现 |
| --- | --- | --- | --- |
| GET | `/api/stats` | `{status,meta_busy,posts,images,deleted,disk_usage,progress,log}`；计数、字节数、最近 200 行日志 | `Crawler.get_stats` |
| GET | `/api/crawl/status` | 直接返回 `progress`，不包含顶层 status | `do_GET` |
| GET | `/api/posts` | `{page,per_page,total,items:[{slug,title,cover,count,video_count,created_at}]}` | `_api_posts` |
| GET | `/api/posts/<slug>` | `{slug,title,url,count,cover,images,tags,categories,cosers,videos,created_at}`；不存在发出 404，另见限制 | `_api_post_detail` |
| GET | `/api/tags` | `{tags:[{slug,name,count}]}` | `_api_tags` |
| GET | `/api/categories` | `{categories:[{slug,name,count}]}` | `_api_categories` |
| GET | `/api/cosers` | `{cosers:[{slug,name,count}]}` | `_api_cosers` |
| GET | `/api/deleted` | `{deleted:[{slug,url,title,deleted_at}]}`，按删除记录顺序 | `Crawler.get_deleted` |

三个聚合接口均统计全部现存文章，不受当前筛选影响；单篇按 slug 去重，按 count 降序、name 小写升序排列。

`GET /api/posts` 查询参数：

| 参数 | 默认与约束 | 语义 |
| --- | --- | --- |
| `page` | 默认 1，最小 1；非整数回退 1 | 页码；超出范围返回空 items |
| `per_page` | 默认 48，范围 1..200；非整数回退 48 | 每页数量 |
| `q` | 默认空，去首尾空白并转小写 | 标题或 slug 子串搜索 |
| `tag` | 默认空；逗号分隔 slug | 多标签 AND，每个标签都必须匹配 |
| `cat` | 默认空 | 分类 slug 单选 |
| `coser` | 默认空 | Coser slug 单选 |

筛选条件彼此 AND；先过滤再分页，顺序来自 `index.order`，新入库文章插在最前。slug 应使用列表返回值，路由层没有对文章 slug 做统一 URL 解码。

### 视频接口

| 方法 | 路径 | 参数 / 成功响应 | 失败 / 副作用 |
| --- | --- | --- | --- |
| GET | `/api/videos/<slug>/<index>` | slug URL 解码；index 从 0 起非负整数，必填；返回 `{url:"/video/<session>/<resource>",type:"hls"}` | 400 参数或来源不支持；404 文章/视频缺失；502 上游失败；504 请求/清单读取超时。创建有界内存会话，不写磁盘 |
| GET/HEAD | `/video/<session>/<resource>` | 仅允许已登记资源；令牌查询参数随清单子资源传递；媒体支持单 `Range` 和 206/416，清单忽略 Range、完整读取重写后返回 200；HEAD 无正文 | 400 无效 Range/来源；404 会话/资源缺失或过期/文章已删/来源改变；502/504 上游错误。已发送响应头后的中断关闭连接，由播放器处理失败 |

视频实现位于 `VideoService.create_video_session/open_resource`，HTTP 入口为 `_api_video/_video_resource`。前端 `startVideo/mediaUrl` 消费上述接口。全部媒体响应 `Cache-Control: no-store`；不向浏览器提供上游签名 URL。HEAD 调用准备接口也会执行对应解析及会话创建，因此客户端应按上表使用 GET 准备、GET/HEAD 读取资源。

### 写入和任务接口

| 方法 | 路径 | 请求体 | 成功响应与副作用 | 失败 |
| --- | --- | --- | --- | --- |
| POST | `/api/crawl/start` | JSON 对象，字段见下 | `{ok:true,message}`；设置代理，后台调用 `Crawler.run` | 正在 running 为 409；URL 不以 `http` 开头为 400 |
| POST | `/api/crawl/stop` | 不需要 | `{ok:true,message}`；设置 `_stop` 事件，异步退出 | 无专门的空闲错误 |
| POST | `/api/meta/refresh` | 不需要 | `{ok:true,message}`；设置 meta_busy，后台补全，finally 清除标志 | meta_busy 为 true 时 409 |
| DELETE | `/api/posts/<slug>` | 不需要 | `{ok:true,message}`；移除索引与图片目录，加入 deleted | 无此文章为 404 |
| POST | `/api/posts/<slug>/restore` | 不需要 | `{ok:true,message}`；移出 deleted，下次遇到文章时重新下载 | 不在 deleted 中为 404 |

爬取启动字段：`url` 默认 `https://cosplaytele.com`；`proxy` 缺省/空白转为 `None`；`start_page` 默认 1、最小 1、转换失败回退 1；`end_page` 缺省/空串/转换失败为 `None`，否则转整数，未限制正数或校验起止关系。URL 当前只检查字符串前缀，不是严格的域名或协议校验。

`_read_body` 对空体或 JSON 解析失败返回 `{}`，但合法 JSON 非对象、错误字段类型没有统一校验；不能假定所有非法输入都有规范的 400 响应。

## 爬虫内部接口

以下符号均在 [crawler.py](crawler.py)，可用 `rg -n "def 方法名" crawler.py` 定位。

| 符号 | 输入 / 输出与职责 |
| --- | --- |
| `sanitize_filename(name)`、`slugify(slug)` | 分别清理 Windows 文件名非法字符、规范化 slug（保留 Unicode 字母数字） |
| `Crawler(data_dir, proxy=DEFAULT_PROXY, concurrency=4, delay=0.35)` | 创建图片目录、Session、可重入锁、停止事件、进度；加载索引 |
| `fetch(url, referer=None, timeout=(15,60))` | GET，重试并分块检查停止事件；返回内容已读取的 Response，失败抛异常 |
| `parse_list(html_text)`、`max_page(html_text)` | 列表文章 URL 保序去重；推断最大页码（未发现分页则 1） |
| `parse_post(html_text, url)` | 提取 title、远程 images/cover、tags/categories/cosers 二元组列表、videos |
| `download_image(img_url, dest, referer=None)` | 已有文件大于 0 字节时复用；否则写 `.part` 并替换目标文件；拒绝 Content-Type 含 text 或 html 的响应 |
| `crawl_post(post_url)` | 已存在/屏蔽时返回 None；无图片返回 `{slug,count:0}` 且不入库；否则下载并保存文章记录 |
| `run(entry_url=SITE,start_page=1,end_page=None,stop_event=None)` | 列表与文章主循环，重置进度，支持外部停止事件，最终保存索引 |
| `refresh_meta_all()` | 更新已有文章元数据，不下载图片；返回 `(done,failed)`，结尾保存索引 |
| `delete_post(slug)`、`restore_post(slug)` | 返回 bool；删除及解除删除屏蔽 |
| `get_deleted()`、`get_stats()` | 返回删除列表浅拷贝及统计对象 |
| `_load_index()`、`_save_index()` | version=1 索引加载；写临时 JSON 后 `os.replace` |
| `_disk_usage()`、`_add_disk(size)`、`_remove_disk(size)`、`_dir_size(path)` | 惰性首次扫描、后续增减与待删除目录计量 |
| `_headers()`、`_proxies()`、`_ext_from_url()`、`log()` | 请求头、代理、扩展名与最多 500 行内存日志 |

正文图片依赖 `attachment-full` 并排除 `wp-post-image`；标签等优先从 blockquote 的 Character / Appear In / Cosplayer 字段解析，兼容链接及纯文本。视频只提取 cossora iframe 地址，保存来源元数据。

## 视频内部接口

实现见 [video.py](video.py)。固定 HTTPS 上游为 `cossora.stream`、`hls-cdn.cossora.stream`，每次重定向重新验证；不接受任意 URL 代理。来源页采用原站 Referer，静态提取密文和字面量密钥，用 cryptography 解密，不执行第三方脚本。

- `VideoService`：最多 64 个内存会话，按闲置 900 秒和容量淘汰；每会话最多 2048 个资源。读取资源前核对原文章及 embed，删除或来源变化后失效。
- `_rewrite_manifest`：处理非注释 URI 行及带引号 URI 属性，登记为不可预测的本地资源路径；相对路径按当前清单地址解析。
- `_open_upstream/_read_limited`：独立 requests Session，当前爬虫代理快照，联网不持有索引锁且不依赖爬虫停止标志；连接/读取超时为 8/25 秒，重定向最多 4 次。
- `VideoResponse.iter_body/close`：64 KiB 分块，媒体上限 128 MiB/请求，HTML 2 MiB、清单 4 MiB；保留压缩媒体的编码字节及头，客户端断开后关闭上游。密钥和分片仅按需转发，不落盘。

## 业务数据契约

| 对象 / 字段 | 结构与含义 |
| --- | --- |
| 索引顶层 | `{version:1, posts:{slug: Post}, order:[slug], deleted?:[DeletedPost]}`；deleted 首次删除时创建 |
| `Post` | `slug,url,title,cover,count,images,tags,categories,cosers,videos,created_at` |
| `cover`、`images` | 相对 data 的正斜杠路径；cover 为首张成功图片或 null；images 为按序号排序的成功图片列表 |
| `count` | 成功保存的图片数量，不保证等于远程图片总数 |
| `tags/categories/cosers` | `[{slug,name}]`；解析阶段二元组在持久化时转换为对象 |
| `videos` | `[{id,embed}]`；id 取 iframe 地址末段，embed 是原站播放器 URL，按 id 去重 |
| `DeletedPost` | `{slug,url,title,deleted_at}`，不保存原图片列表和文件 |
| 时间 | created_at/deleted_at/started_at/finished_at 为本地时间字符串 `YYYY-MM-DD HH:MM:SS`；未开始/结束时进度时间为 null |
| `progress` | `list_page,list_total,posts_found,posts_done,posts_skipped,images_total,images_done,current_url,errors,started_at,finished_at` |

状态：初始 `idle`，运行中 `running`，结束临时进入 `done` 或 `stopping`，finally 回到 `idle`；主流程异常保留 `error`。`meta_busy` 是独立标志，不应由 status 推断元数据任务是否完成。

## 前端接口与状态

所有入口位于 [static/index.html](static/index.html)，没有模块打包或前端路由框架。

| 功能 | 函数 / 状态 | 对接接口 |
| --- | --- | --- |
| 鉴权与图片 URL | `api`、`imgUrl`、`showTokenGate/saveToken`；localStorage 键 `gt_token` | API 请求头带令牌，图片 URL 查询参数带令牌；401 打开门控 |
| 统计、日志、进度 | `refreshStats`、`setBadge`、`renderLog` | `/api/stats` |
| 列表与筛选 | `loadPosts/loadFilters`、`setTag/setCat/setCoser/clearFilters`；page/perPage、activeTags/activeCat/activeCoser | posts、tags、categories、cosers；每页 48，搜索防抖 350ms |
| 详情与图片灯箱 | `openPost/closePost`、`openLb/lbStep/closeLb`；curPost/curImgs/lbIdx | 详情 API 与 `/img/`；左右键循环、Esc 退出 |
| 详情筛选 | `detailTag/detailCat/detailCoser` | 切换筛选 |
| 视频 | `startVideo/toggleVideo/retryVideo/stopVideo/stopAllVideos`、`mediaUrl`；`videoPlayers`、`detailVersion` | `/api/videos/`、`/video/`；MSE 可用优先本地 HLS.js，否则原生 HLS 回退；加载/失败/重试状态，收起/返回/切换停止并释放，忽略迟到响应 |
| 删除与恢复 | `deletePost/restorePost/openDelPanel` | DELETE、restore、deleted；删除前弹出确认 |
| 爬取与补全 | `startCrawl/stopCrawl/refreshMeta` | 三个任务 POST 接口 |
| 轮询 | `startPolling` 为 1500ms，`initPolling` 为 3000ms；共用 polling | stats；按 status 停止，未将 meta_busy 纳入继续条件 |

## 配置与启动

| 入口 / 配置 | 当前值与行为 |
| --- | --- |
| Python | 3.8+；`python -m pip install -r requirements.txt`，requests>=2.31,<3，cryptography>=46.0.6,<47；本次实测 Python 3.12.13，其他版本未实测 |
| `python server.py` | 使用脚本目录下 data/static；自动打开本机浏览器 |
| `HOST` / `PORT` | 环境变量，默认 `127.0.0.1` / `8765`，导入 server 时读取 |
| `ACCESS_TOKEN` | 默认空；非空时保护 API、图片和视频；启动时会打印令牌 |
| `DEFAULT_PROXY` | crawler 常量 `http://127.0.0.1:7890`；HTTP 启动请求不传 proxy 则覆盖为 None；页面代理输入也有默认值 |
| `--url` | CLI 入口，默认 SITE |
| `--start` / `--pages` | CLI 起始页默认 1；pages 默认 None，实际传给 end_page，表示结束页码而非页数 |
| `--proxy` / `--data` | CLI 默认代理常量 / 脚本目录下 data；空代理转 None；requests 仍可能读取环境代理 |
| `start.bat` | 按脚本硬编码位置探测 Python，最终回退 python；在项目目录运行 server.py |
| `start-share.bat` | 从 data/token.txt 生成/复用令牌，设 HOST=0.0.0.0 和 ACCESS_TOKEN；尝试调整 TCP 8765 防火墙规则，未设置 PORT |

CLI 示例：`python crawler.py --start 3 --pages 5` 实际处理第 3 至第 5 页，受站点最大页数限制。该命令会访问外部站点并写入数据。

## 已知限制与待验证点

以下是静态源码观察，记录现状，不代表已在本次修复：

- `_api_post_detail` 在不存在文章时发出 404 后缺少 return，继续访问空对象；GET restore 分支发出 405 后也继续调用详情，可能重复响应或抛异常。
- 图片服务基于 data 根目录映射，未仅允许 images；有令牌者可请求该目录下其他已知文件路径。
- 首次运行共享脚本时，生成 token 前没有创建 data 目录，重定向可能失败；防火墙固定 8765，与外部设置的 PORT 可能不一致。
- 部分图片下载失败仍将文章入库，下次普通爬取会跳过整篇，不会自动补齐缺图；纯视频或无图片文章不会入库。
- 索引加载异常会回退空索引，未建立损坏文件恢复机制；删除文件失败被忽略，成功响应不能证明磁盘目录已完全移除。
- 多线程共享索引的读取、状态检查和任务启动并非全部受锁保护；不能宣称多任务或多进程写入安全。
- 元数据任务复用 `_stop`，不会独立清除停止信号；后端只检查 meta_busy，未禁止它与爬取同时运行。前端轮询只看 status，可能在补全完成前停止刷新。
- 磁盘缓存首次扫描存在延迟；已存在文件复用时仍增加计数，首次扫描前下载也会把缓存标记为已就绪，不能保证所有执行顺序下统计准确。
- 前端 `api()` 在 401 时返回 error 对象，列表和聚合调用仍直接使用数组字段，可能出现额外 JavaScript 异常。
- 视频依赖上游可访问和当前 cossora 页面格式；样例首次分片约 19 MB，实际首帧等待曾约 76 秒。progressive 实测分片解析失败，采用默认加载。未实测 Safari/iOS 原生回退、长时间完整观看或公网共享；不提供离线视频。

## 同步维护记录

| 日期 | 变更 | 核验 |
| --- | --- | --- |
| 2026-09-05 | 首次建立文件结构、HTTP/内部接口、数据契约与前端索引；新增 AGENT.md 约定和 AGENTS.md 入口 | 对照当前源码静态梳理；未运行外部爬取或共享脚本 |
| 2026-09-05 | 新增 dev_log 开发日志约束、目录说明及索引入口；要求 task.md 每完成一项立即更新，断联后复用任务目录 | 本次按用户要求免建任务日志；业务结构与接口无变化 |
| 2026-09-05 | 建立 dev1视频在线播放 三文档，记录静态核对结果及待确认事项 | 已检查，业务结构/接口无变化；截图显示外部 iframe 错误，根因待复现 |
| 2026-09-05 | dev1 记录用户授权的子 agent 分工，安排只读源码复核 | 仍等待复现链接和原站播放情况；业务结构/接口无变化 |
| 2026-09-05 | dev1 完成独立只读审查，记录 iframe 生命周期、URL 实体解码及纯视频入库限制 | 均未证实为截图错误根因；业务结构/接口无变化，待用户补充来源样例 |
| 2026-09-05 | dev1 因持续缺少复现信息暂停，保存恢复入口 | 工作区仍无 data/index.json；遵守用户先确认要求，业务开发未开始 |
| 2026-09-05 | dev1 记录用户确认直接打开来源链接也报错，明确来源按钮指向播放器而非文章 | 不再要求用户先确认原站可播放；等待具体 URL 或图集标题定位来源 |
| 2026-09-05 | dev1 根据完整标题定位 artoria-lancer-2 原文，记录直连、代理和浏览器连接失败证据 | 尚未取得播放器地址；不将标题中的视频数量视为 iframe 数量；业务结构/接口无变化 |
| 2026-09-05 | dev1 记录用户侧原文连接失败及 HTTPS 对照检查，下一步改查独立播放器入口 | example.com 为 200，文章站点首页 TLS 失败；具体原因未明，业务结构/接口无变化 |
| 2026-09-05 | dev1 原文访问恢复，取得实际播放器并完成 Referer 对照；记录用户 JW Player 播放截图 | 原站来源返回播放器 HTML，本地/无来源返回 Unknown Error xD；媒体链路待验证，业务结构/接口无变化 |
| 2026-09-05 | dev1 记录用户方案确认，恢复媒体可行性调查并明确后端鉴权与流式播放约束 | 实现尚未开始；不预下载完整视频，新增依赖或方案变化仍先确认 |
| 2026-09-05 | dev1 调查确认 AES 加密地址指向 HLS，询问 cryptography 与本地 hls.js 依赖 | 静态提取并验证 master/variant；媒体下级请求仍在调查，未实施依赖变更 |
| 2026-09-05 | dev1 记录依赖同意及完整媒体调查，细化受控转发、前端生命周期和测试方案 | 83 段/1238.97 秒，key 和首片 Range 验证成功；开始实施，接口现状待实现后同步 |
| 2026-09-05 | dev1 增加 requirements.txt 与视频后端测试入口，完成 RED 基线 | 视频模块/路由尚未实现时测试按预期失败；继续实现 |
| 2026-09-05 | dev1 提供本地 HLS.js 1.7.2、上游声明/许可证和供应来源 | npm tarball SHA-512 核验一致，脚本 SHA-256 已记录；前后端仍在实施 |
| 2026-09-05 | dev1 前端行为测试完成 RED，播放生命周期实现进入复测 | 初始 8 项失败符合缺失行为；实现首轮 7/8，继续核验 |
| 2026-09-05 | dev1 记录用户允许本地下载作为在线播放失败时的备用方向 | 当前继续已确认的按需 HLS 转发，等待真实端到端验证 |
| 2026-09-05 | dev1 前端 9 项行为测试 GREEN，后端核心测试通过并补充异常验证 | 准备独立审查和临时图库真实播放验收，尚未宣称实现完成 |
| 2026-09-05 | dev1 独立审查发现 4 项异常处理缺口，进入修复；启动临时图库真实播放验证 | 后端首轮 21 项测试通过，但重试显示、压缩长度、206 清单和读取超时需补测修复 |
| 2026-09-05 | dev1 真实浏览器触发 master 清单 Range/206，定位首轮播放超时 | API 200 不代表可播放，先修复清单重写后复测 |
| 2026-09-05 | dev1 修复 4 项独立审查问题并加入回归，重新启动真实播放测试 | 新增 Python 5 项先失败后通过，前端 9 项再次通过；真实浏览器验证进行中 |
| 2026-09-06 | dev1 在临时图库使用 HLS.js 播出真实视频，继续验证拖动和错误恢复 | 1080x1920、1238.97 秒、已输出视频帧；首段约 76 秒，继续检查加载体验 |
| 2026-09-06 | dev1 真实播放全流程通过，调整 HLS.js 优先级与渐进加载 | 拖动、收起、失败重试、移动端和关闭已通过；新增优先级回归已确认 RED，继续默认路径复验 |
| 2026-09-06 | dev1 移除真实来源不兼容的 progressive 选项，保留 HLS.js 优先和原生回退 | 浏览器实测渐进解密出现 fragParsingError；恢复已验证的默认分片加载，首帧速度受上游影响 |
| 2026-09-06 | dev1 同步实际视频模块、API、配置、前端生命周期与限制，完成修复复审 | 独立复审未发现新确定问题，确认上轮 4 项修复；默认入口浏览器复测进行中 |
| 2026-09-06 | dev1 更新恢复摘要与最终回归结果，检查移动端截图 | Python 26/26、Node 10/10 和语法检查通过；真实默认路径可播放，移动布局无溢出，继续最后验收 |
| 2026-09-06 | dev1 完成按需在线播放交付，保留临时样例预览并记录真实网络限制 | 26 项 Python、10 项 Node、语法、45 个文档链接及 diff 检查通过；已实播/跳转/重试/释放，最后复测 seek 超过 90 秒窗口；无用户数据变更 |

## Related

- [[AGENT]]：开发约定和索引同步要求；普通 Markdown 入口见 [AGENT.md](AGENT.md)。
- [README.md](README.md)：安装与用户使用说明。
