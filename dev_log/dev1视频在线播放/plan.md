---
type: action
title: "视频在线播放实施规划"
status: complete
updated: 2026-09-06
tags: [video, development]
---

# 目标与范围

用户点击在线观看后可在本项目页面内观看视频。严格遵守 AGENT.md，开发中实时维护任务日志和 Index.md；所有不确定事项先询问用户再开发。
备用方向：用户允许在在线播放无法实现时考虑下载至本地服务器播放。当前媒体链路已证明可取得，继续先验收按需转发；不会把“API 返回成功”当作用户目标完成。

# 阶段

1. 阅读约定、索引、源码及截图，确认当前链路。
2. 获取截图对应文章 URL，确认原站能否播放，复现错误并确定原因。
3. 向用户说明播放方案、影响文件、依赖和验收方式，确认不确定事项后实施。
4. 分项实现并实时记录进展，同步接口索引与用户说明。
5. 使用临时数据验证相关 Python、HTTP 和前端流程，验证实际视频播放。

# 方案与依赖

用户已同意：现有 Python 后端适配来源信息、前端在详情内播放、不预下载完整视频。当前先验证媒体链路，新增依赖或方案变化先询问。不能仅删除 no-referrer，因为本项目 Referer 同样被拒绝。不要直接将含第三方脚本的远程 HTML 放到图库同源执行。

调查进展：原文 https://cosplaytele.com/artoria-lancer-2/ 已恢复访问，已取得播放器并验证 Referer 校验。之前网络连接失败为历史记录，不再作为当前阻塞。

分工：主 agent 统筹需求、方案确认、日志、HTTP 接口和验收；media_feasibility 子 agent 验证媒体入口、地址处理和请求条件，完成后给出证据与依赖建议。实现范围明确后分配开发和独立审查。

下一阶段接口约束：播放请求使用已入库文章和视频序号定位来源，不接受任意上游 URL；沿用 ACCESS_TOKEN 鉴权；网络请求不持有索引锁，不复用爬虫停止信号；媒体按需加载并支持拖动，关闭详情释放播放资源。最终接口和测试细节由媒体验证结果确定，不提前编造可行性。

新增依赖已获用户同意：cryptography 解析 AES 加密地址，hls.js 随项目本地提供以支持 Chrome HLS。禁止手写 AES 或执行远程混淆 JavaScript；调查用 Node 不成为应用运行依赖。

# 实施任务与接口

## 1. 后端播放服务及 HTTP 回归

文件：新增 video.py、tests/test_video.py、tests/test_video_http.py，修改 server.py。视频解析和资源会话集中于 video.py，避免在现有 HTTP 路由内混合远程解析、缓存、URI 重写和流式生命周期。继续使用 requests 和标准库 HTTP 服务。

- GET /api/videos/<slug>/<index>：沿用令牌鉴权，slug URL 解码，index 为从 0 起的非负整数。按已入库文章 videos 定位；返回 {url:"/video/<session>/<resource>",type:"hls"}，不返回签名上游 URL 或 AES 密钥。参数错误 400，文章/视频不存在 404，不支持来源 400，上游错误 502，超时 504。
- GET/HEAD /video/<session>/<resource>：同样鉴权，仅请求服务端已登记的资源。会话有容量上限与空闲过期，丢失或过期 404；重试播放可创建新会话。访问时确认文章仍存在且来源未变，删除后禁止继续读取。
- 静态提取 videoURL 和 decryptLink 第二实参，用 cryptography AES-CBC/PKCS7 解码；只解析字段，不执行原站脚本。
- 固定允许 HTTPS 的 cossora.stream 和 hls-cdn.cossora.stream；每次请求及重定向均验证，禁止任意 URL 代理、凭据 URL、非标准端口和外部主机。
- 清单中相对/绝对 URI 与 URI 属性全部改为会话资源地址；按传入 token 查询参数继续传递以支持原生 HLS，hls.js 也可用请求头鉴权。密钥和分片不进入业务索引或磁盘。
- 分片按块流式读取，转发合法单 Range、206/416/Content-Range/Accept-Ranges，客户端断开关闭上游。不得按 .png 扩展名或 image/png 判断不是视频，真实来源使用此形式。
- requests 独立于爬虫停止标志；采用当前 crawler.proxy 快照；不在索引锁内联网，限制清单/HTML 大小与请求超时。
- 先写测试并确认缺失行为失败，再实现。测试使用临时 Crawler 与受控上游替身，检查鉴权、参数、资源缺失、AES 解析、清单重写、URL 约束、Range、流式断开和删除后访问；不得导入时写用户 data。

## 2. 前端播放与生命周期

文件：static/index.html，必要的前端测试位于 tests/。

- 本地脚本地址 /static/vendor/hls.min.js，由后端精确白名单公开提供，不公开整个文件系统。
- 视频入口调用 GET /api/videos/<encodeURIComponent(slug)>/<index>；native HLS 或 Hls.js 使用返回的同源 URL。通过现有 token 机制保护全部媒体请求，不向外站发令牌。
- MSE 可用时优先 HLS.js，其他支持原生 HLS 的浏览器回退原生播放器。使用默认分片加载；progressive 在真实加密来源上触发解析错误，不启用。
- 使用原生 video controls、playsinline、稳定容器尺寸，保持现有详情布局；提供加载、失败、重试和收起状态，来源链接改指文章 URL 并准确命名。
- 收起、关闭详情、切换文章时销毁 Hls、停止 video 并清空 src；中途关闭或快速切换时迟到响应不能重新启动播放。以当前详情/会话身份判定响应是否仍有效。
- 播放成功以真实 loaded metadata、媒体时间推进和帧输出验证，不能仅看 API 或按钮状态；拖动、音量、全屏用浏览器原生控件。

## 3. 依赖、文档与最终验收

主 agent 提供固定 hls.js 1.7.2 发布产物与 Apache-2.0 LICENSE，保留供应来源和校验信息；新增 requirements.txt 明确 requests 和 cryptography。同步 README.md 与 Index.md 的文件结构、启动方式、全部新路由及限制。

- 运行 Python 语法检查及新增 unittest 测试；前端使用隔离临时数据和本机服务验证桌面/移动布局、真实 HLS 播放、拖动、关闭释放、401/失败/重试。
- 子 agent 独立审查实现契约与代码质量；主 agent 核验修改并处理发现，再同步每项日志。
- 实际工作目录保持 D:/project/cosplay-gallery 的现有 codex/video 功能分支；已有未跟踪约定与日志保留，不自动提交、推送或切换用户分支。

任务交叉检查：后端产出 /api/videos 与 /video，前端消费完全相同路由；主 agent 提供的 /static/vendor/hls.min.js 由后端精确映射。后端 agent 只改 video.py/server.py/后端测试，前端 agent 只改 static/index.html/前端测试，主 agent 统一日志、依赖和文档，避免共享文件写入冲突。

# 验收标准

2026-09-06 交付：已实现并验证按需 HLS 播放、生命周期、鉴权和错误恢复；具体测试与网络等待限制见 task.md。备用整部视频下载未启用。原生 Safari/iOS 和公网环境保留为未实测范围。

- 已确认的有效视频在项目内可实际播放，不能仅以按钮展开或 iframe 加载作为通过依据。
- 按实现影响验证关闭/切换视频、失败反馈、桌面与移动布局及令牌行为。
- 保持现有数据边界、锁与原子写入约束；测试不修改用户图库。
- 三份任务文档和 Index.md 与实际结果一致，未验证部分明确列出。
