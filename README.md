# CosplayTele Gallery — cosplaytele.com 图集爬取与本地浏览

一个**零依赖**（仅 `requests`）的本地图集工具：自动爬取 [cosplaytele.com](https://cosplaytele.com) 各图集的全部高清图片到本地，通过本地网页浏览阅读；支持标签 / 分类 / Coser 筛选、图集删除与恢复、视频来源链接、可选访问令牌，可共享给局域网或经内网穿透分享给远程访客。

```
爬取 cosplaytele.com ──▶ 本地磁盘 (data/images/<slug>/) ──▶ 本地 Web 图库 http://127.0.0.1:8765
                                                            (浏览 / 筛选 / 删除 / 共享)
```

## ✨ 特性

- **自动爬取**：遍历全站列表页（或指定分类页），解析每篇文章正文全部高清大图并下载
- **断点续爬 / 增量更新**：已下载与已删除的文章自动跳过，重复运行不重复下载
- **礼貌爬取**：请求限速、自动重试、可随时停止（秒级响应）
- **本地图库 Web**：响应式单页，图集网格 → 详情 → 灯箱浏览（键盘翻页）
- **多维筛选**：📁 分类（单选）、👤 Coser（单选）、🏷 标签（多选 AND），可与标题搜索组合
- **删除 / 恢复**：删除图集（含本地文件）后记入黑名单，后续爬取永不重下；可随时恢复
- **视频支持**：自动识别文章内视频并给出**来源链接**（原站加密防盗链，无法下载直链，见下）
- **可选访问令牌**：设置 `ACCESS_TOKEN` 后所有请求需令牌，适合共享/公网部署
- **单文件后端**：Web 服务器为 Python 标准库 `http.server` 实现，无框架依赖

## 📋 环境要求

- Python 3.8+（Windows 验证于 3.11 / macOS / Linux 应可用）
- 第三方依赖：仅 `requests`（`pip install requests`，一般环境自带）
- 访问 cosplaytele.com 可能需要代理（视网络环境），通过页面设置或 `--proxy` 传入

## 🚀 快速开始

```bash
git clone <本仓库地址>
cd cosplay-gallery
pip install requests            # 如未安装
python server.py                # Windows 也可双击 start.bat
```

浏览器自动打开 `http://127.0.0.1:8765`，点击右上角 **⚙ 爬取设置**：

| 字段 | 说明 |
| --- | --- |
| 入口列表 URL | 首页或分类页，如 `https://cosplaytele.com/category/cosplay/` |
| 代理 | 留空直连；需要代理填 `http://127.0.0.1:7890` 之类 |
| 起始/结束页 | 只爬部分列表页时使用（结束页留空 = 全部） |

点 **▶ 开始爬取**，实时进度与日志可见；停止后进度保留。

## 🖥 界面速览

- 顶部：状态徽章、文章/图片/磁盘统计、爬取设置、已删除管理
- 📁 👤 🏷 筛选栏：点击筛选，再点取消；可与搜索框叠加
- 图集卡片：悬停显示 🗑 删除；详情页可看全部图片、分类/Coser/标签、视频来源
- 图片灯箱：点击放大，`←/→` 翻页，`Esc` 关闭

## ⚙️ 配置（环境变量）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | 监听地址；`0.0.0.0` 允许局域网/公网访问 |
| `PORT` | `8765` | 端口 |
| `ACCESS_TOKEN` | 空 | 非空时启用访问令牌：API/图片请求需带 `X-Access-Token: <token>` 请求头或 `?token=` 参数；页面打开时输入令牌 |

**共享给他人**：Windows 直接双击 `start-share.bat`（自动生成随机令牌、监听 0.0.0.0、尝试放行防火墙）。跨平台手动：
```bash
HOST=0.0.0.0 ACCESS_TOKEN=你的随机令牌 python server.py   # Linux/macOS
set HOST=0.0.0.0 && set ACCESS_TOKEN=你的随机令牌 && python server.py   # Windows cmd
```

## 📁 目录结构

```
cosplay-gallery/
├── server.py          # Web 服务器 + REST API（标准库）
├── crawler.py         # 爬虫（解析 / 下载 / 索引 / 删除）
├── static/index.html  # 前端单页（原生 JS）
├── data/              # 运行后生成：index.json 索引 + images/<slug>/ 图片（勿提交 git）
├── start.bat          # Windows 本机启动
├── start-share.bat    # Windows 共享启动（0.0.0.0 + 令牌 + 防火墙）
└── README.md
```

## 🔧 命令行爬取（可选）

```bash
python crawler.py --pages 5 --proxy http://127.0.0.1:7890
```

| 参数 | 说明 |
| --- | --- |
| `--pages N` | 爬取前 N 个列表页（默认全部） |
| `--start N` | 从第 N 页开始 |
| `--url URL` | 入口列表地址（首页或分类页） |
| `--proxy URL` | 代理；传空串直连 |
| `--data DIR` | 数据目录（默认 `./data`） |

## 📡 HTTP API（节选）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/stats` | 状态：文章数/图片数/磁盘/进度/日志 |
| GET | `/api/posts?page=&per_page=&q=&tag=a,b&cat=&coser=` | 图集列表（标签多选 AND） |
| GET | `/api/posts/<slug>` | 图集详情（图片/标签/分类/Coser/视频） |
| GET | `/api/tags` · `/api/categories` · `/api/cosers` | 筛选聚合数据 |
| GET | `/api/deleted` | 已删除图集（可恢复） |
| POST | `/api/crawl/start` · `/api/crawl/stop` · `/api/meta/refresh` | 爬取控制 / 元数据补全 |
| POST | `/api/posts/<slug>/restore` | 恢复已删除图集 |
| DELETE | `/api/posts/<slug>` | 删除图集（本地文件 + 黑名单） |

启用令牌时：除 `/` 外所有接口需 `X-Access-Token` 或 `?token=`。

## 🌐 远程共享（互联网访客）

先以共享模式启动（带 `ACCESS_TOKEN`），再任选一种内网穿透：

| 方案 | 特点 | 大致步骤 |
| --- | --- | --- |
| **ngrok** | 免费、免安装对方端，URL 每次重启会变 | `ngrok http 8765` → 把 `https://xxx.ngrok-free.dev` + 令牌发给对方 |
| **Tailscale** | 免费、加密、URL 固定，双方装客户端 | 双方同账号登录 → 访问 `http://<你的100.x IP>:8765` |
| **Cloudflare Tunnel** | 可固定域名（需自备域名） | `cloudflared tunnel --url http://127.0.0.1:8765` |
| **frp** | 需公网服务器 | frps + frpc 映射 8765 |

> ⚠️ 公网暴露必须设置 `ACCESS_TOKEN`（有令牌者可删除图集 / 触发爬取）。

## ⚠️ 已知限制

- **视频不能下载到本地**：站点视频托管于 cossora 并做加密防盗链（混淆 JS + AES，无法自动获取直链）。程序会识别视频并展示**来源链接**（点击跳原站观看），也可在页面内展开在线播放。
- **站点结构依赖正则解析**：cosplaytele 为 WordPress；若其改版，解析规则集中在 `crawler.py` 顶部正则常量，易定位调整。
- **目标站访问需代理时**：所有网络请求（含 API 触发的爬取）都会使用设置中的代理；请勿在无代理且无法直连的环境下大批量爬取（会大量超时重试）。

## 🧩 开发者备注（重要，改动前阅读）

- 线程锁使用**可重入锁 `RLock`**：曾在嵌套加锁处死锁（`threading.Lock` 不可重入），勿改回。
- **磁盘统计为 O(1) 增量维护**：全量 `os.walk` 在上万图片时单次 10s+，禁止在请求路径做全盘遍历。
- 图片仅抓正文大图（WordPress `attachment-full`），自动排除"相关文章"缩略图。
- 标签 / 分类 / Coser 从文章正文 `blockquote` 的 Character / Appear In / Cosplayer 字段解析（支持链接与纯文本两种形式），解析逻辑见 `crawler.parse_post`。
- 索引 `data/index.json` 是唯一权威数据，每篇文章完成即原子落盘；恢复/备份需连同 `data/images/` 一起。

## 📄 License

MIT
