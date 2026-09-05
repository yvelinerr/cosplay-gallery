---
type: task_state
title: "视频在线播放任务状态"
status: complete
updated: 2026-09-06
tags: [video, development]
---

# 任务清单

- [x] 阅读 AGENT.md、Index.md、README.md 和日志目录说明。
- [x] 静态核对视频解析、详情输出与前端展开逻辑，查看用户截图。
- [x] 子 agent 独立只读审查视频链路，记录确定行为及待验证假设。
- [x] 根据用户提供的完整标题定位原始文章 https://cosplaytele.com/artoria-lancer-2/。
- [x] 从原文 DOM 获取实际播放器 URL，并用 Referer 对照复现 Unknown Error xD。
- [x] 确认复现文章及原站播放情况，通过 Referer 对照查明播放器页面错误原因。
- [x] 用户确认后端适配来源校验、项目内播放、不预下载完整视频的方案方向。
- [x] 验证媒体地址处理和实际请求条件；用户已同意 cryptography 与本地 hls.js。
- [x] 实现后端解析、受控清单/媒体转发及 HTTP 测试。
- [x] 后端新增测试先运行 RED：缺少 video.py、新路由 404、HEAD 501、vendor 未公开，均为目标行为缺失。
- [x] 后端首轮实现通过 21 项 Python 测试和语法检查，独立审查发现异常分支缺口。
- [x] 独立审查完成，确认 4 项需修复问题：重试按钮隐藏、压缩长度不一致、206 清单未重写、读取超时未映射。
- [x] 修复独立审查问题并完成针对性复核。
- [x] 4 项审查发现完成修复：新增 5 项 Python 回归先失败后通过，前端重试可见性断言先失败后通过。
- [x] 实现前端 HLS 播放、错误重试及关闭释放。
- [x] 前端新增行为测试先运行 RED：8 项失败，覆盖缺失生命周期、迟到详情响应和旧 iframe 流程。
- [x] 前端实现通过 9 项 Node 行为测试和语法检查，进入独立审查与浏览器实测。
- [x] 固定依赖与本地 HLS 产物，更新安装和接口说明。
- [x] requirements.txt 与 HLS.js 1.7.2 本地产物、许可证落盘，npm tarball SHA-512 核验一致。
- [x] 实现已确认的播放方案，逐项同步日志。
- [x] 完成相关行为与实际播放验证，更新 README.md、Index.md。
- [x] 核验文档链接、git diff --check 和最终变更范围。

# 当前状态

最终状态：已完成项目内按需在线播放。Python 26/26、Node 10/10 和语法检查通过；独立审查问题已修复并复审。真实视频已播放，画面及时间推进、120 秒跳转、失败重试、收起/关闭释放和移动布局均取得成功证据。默认入口复测同样成功播放，但该轮 seek 下载超过 90 秒测试窗口；保留上游网络慢的限制，不宣称每次跳转都能快速完成。

文档本地链接 45 项有效，git diff --check 通过，依赖产物 SHA-256 与记录一致；data/index.json 仍不存在，未修改用户图库。样例预览 http://127.0.0.1:28695 保留运行，测试浏览器均关闭。Safari/iOS 原生 HLS、完整长时间观看和公网共享未实测；未实现整部视频本地下载，当前在线播放方案可用。下面保留实施历史。

只读源码复核已完成；已安排 media_feasibility 子 agent 调查媒体链路，主 agent 核对接口、鉴权和日志。业务实现尚未开始。

当前步骤：用户已确认 cryptography 与本地 hls.js，媒体可行性验证结束；开始按 plan.md 接口分工实施后端、前端和依赖。
当前实施状态：后端/前端首轮测试完成，修复 4 项独立审查发现；同时在临时图库 http://127.0.0.1:14556 上运行真实 HLS 浏览器验证。该服务使用 Temp 下的内存样例索引，不写用户 data。
用户补充：在线播放无法实现时，可考虑下载到本地服务器；已作为备用方向记录，当前尚未切换方案。
下一步：根据验证结果确定实现和测试细节；若资源链路或依赖存在新决策，先询问用户。
已澄清：“来源链接”实际为播放器地址，用户无法据此判断原始文章的视频状态；无需用户先证明原站能播放。
尚未验证：本项目真实端到端播放和运行时错误恢复；上游签名 URL 不作永久缓存。
历史暂停已解除：用户补充原文播放截图并同意后端适配方向，本轮继续原任务。

# 核验结果

- 最终：默认入口视频 duration=1238.966667，1080x1920，readyState=4；画面采样 unique=242、68 帧，首段约 61 秒。最后 seek 第二个所需分片未在 90 秒窗口完成，测试退出并释放浏览器；前一全流程已通过 SEEK=121.010881、COLLAPSE_OK、ERROR_RETRY_VISIBLE、RETRY_OK、MOBILE_CLOSE_OK。1440px/390px 长标题布局另行检查通过；桌面/移动截图已人工查看，无越界或叠压。

- 2026-09-06：video_review 独立复审确认上轮 4 项已修复，未发现新的确定缺陷；额外受控验证无后缀清单 Range 重取、清单 HEAD 长度及空正文通过。README 与 Index 已同步最终接口、依赖和首帧等待限制，接下来完成默认入口浏览器及文档最终检查。

- 2026-09-06：HLS.js 优先级回归 10/10；progressive 实测触发 fragParsingError，已移除该选项，使用已通过全流程的默认分片加载。保留 MSE 支持时优先 HLS.js、原生 HLS 回退，继续默认入口复测；首帧可能因上游大分片等待较久，不承诺秒开。

- 2026-09-06：分片前 1 MiB 按 Range 取得并用 HLS key 解密，TS 同步字节每 188 字节均为 0x47；内容有效。HLS.js 浏览器对照实际播放成功：duration=1238.966667，1080x1920，readyState=4，已输出 68 帧，32x32 像素采样 242 个不同通道值。首段下载约 76 秒，正验证 seek/重试/关闭并调查首帧延迟；不能据此宣称全部验收完成。

- tests/test_video_review.py 首轮 5 项全失败（3 failure、2 error），修复后 5/5；清单 Range 不再向上游透传，完整重写后返回 200，意外部分清单拒绝；压缩媒体保留原始编码字节和对应头，读取错误映射 502/504。
- 前端重试用显式 inline-flex 显示，两项断言修复前失败，修复后 Node 9/9。测试服务已重启至 http://127.0.0.1:28695，继续实际播放验证。

- 真实浏览器首轮等待媒体 90 秒超时；诊断复测显示 prepare API 200，但浏览器对 master 请求得到 206，命中独立审查的“部分清单未重写”问题。此为真实播放阻塞，须先修复再复测，不能以单元测试 GREEN 交付。

- backend_video 首轮最终：python -m unittest discover -s tests 21 tests OK；compileall 通过。
- video_review 独立审查：真实 gzip Response 内存 probe 显示压缩长度 49 与实际解压输出 6000 不一致；Range 清单 206 绕过重写；iter_content 读超时未映射 VideoError；前端 CSS .vretry display:none 与失败内联空值冲突。以上进入修复，不标记交付完成。

- frontend_video 最终 GREEN：node --test tests/test_frontend_video.js 9/9；node --check tests/test_frontend_video.js 成功。真实播放与桌面/移动布局尚未验证，前端最终交付项保持未完成。
- backend_video 核心测试 18 项已通过；发现并补测修复会话容量达到上限后读取误淘汰，继续补齐错误/Range 覆盖。

- frontend_video：node --test tests/test_frontend_video.js 初始 0/8；实现后首轮 7/8，剩余为测试对 URLSearchParams 空格编码的过度限定，正修正为语义断言后复测，尚未标记前端完成。

- static/vendor/hls.min.js 原样提取官方 npm 1.7.2 包，SHA-256 afcde07437ec84b072fe8782e772ceb5046eac751b2719f73ae0d83d763bc3f5；来源与完整性见 vendor/README.md。Node/npm 仅用于获取产物，不是应用运行依赖。

- backend_video：新增 tests/__init__.py、tests/test_video.py、tests/test_video_http.py；python -m unittest tests.test_video tests.test_video_http 确认 RED，开始业务实现。
- 主 agent：新增 requirements.txt（requests>=2.31,<3；cryptography>=46.0.6,<47），hls.js 1.7.2 本地产物获取进行中。

- media_feasibility 完成：变体 83 段、总长 1238.966667 秒，AES-128 key 实取 16 字节；首段 bytes=0-15 请求返回 206 和正确 Content-Range，仅读取 16 字节。清单/key 无跨域 ACAO，片段有 ACAO=*，因此后端统一按需转发。
- 实际分片为 hls-cdn.cossora.stream 的 .png 路径，响应 image/png，内容为加密媒体，不能按图片 MIME 拒绝。
- hls.js 官方发布与 npm registry 核验版本 1.7.2；当前 Python 已有 cryptography 46.0.6。部署依赖仍需明确列入 requirements。

- media_feasibility 已静态提取加密 videoURL 与 decryptLink 的密钥实参，使用 Node 原生 crypto 验证 AES-256-CBC 解码成功（IV 为前 16 字节，PKCS7），无需执行远程混淆脚本。
- 解码结果为 cossora.stream/api-embed/.../index.m3u8 的 HLS master，存在 1080x1920 variant；媒体下级清单和请求条件仍在核验。签名 URL 和密钥不写入日志。

- 新截图显示原文播放器已播放到 00:14 / 20:38，菜单标识 JW Player 8.30.0；这是用户侧播放证据，本项目播放仍未实现或验证。
- 本轮 Chrome 新建后台页成功读取原文 DOM，视频 iframe 为 https://cossora.stream/embed/de0d5fb2-1267-4d8b-be55-26f16ea82c31；正文只有一个该来源 iframe，另有广告 iframe。
- 同一 embed：无 Referer 返回 Unknown Error xD；Referer=https://cosplaytele.com/ 返回标题匹配的播放器 HTML；Referer=http://127.0.0.1:8765/ 仍返回同一错误。原站 Referer 成功重复验证。
- 播放器 HTML 使用 JW Player 和 CryptoJS，存在经过混淆的播放地址处理；尚未确认媒体 URL 的访问条件，不能将 HTML 返回成功当作项目内播放成功。

- 搜索结果的文章标题与用户提供内容完全匹配，原文地址为 https://cosplaytele.com/artoria-lancer-2/；搜索快照出现 iframe 文本但没有播放器地址。
- PowerShell Invoke-WebRequest、curl 直连及显式 127.0.0.1:7890 代理请求均失败（unexpected EOF / TLS handshake）；Chrome 后台页返回 ERR_CONNECTION_CLOSED；web open 也未取得正文。
- Jina 替代读取同样 TLS 失败。已关闭本次新建的 Chrome 后台页，未操作用户已有标签页。
- 标题的 22 videos 可能指下载合集数量，项目显示 1 个播放器尚不能证明漏抓。未验证真实视频可播放。
- 用户确认原始文章在其浏览器同样 ERR_CONNECTION_CLOSED。对照检查 https://example.com 返回 200，https://cosplaytele.com 首页仍 TLS handshake failure；不能归因为所有 HTTPS 不可用，也不能据此证明视频已删除。

- static/index.html 的 openPost 创建 cossora iframe，toggleVideo 在展开时设置 src。
- 用户截图显示 iframe 内返回 Unknown Error xD，尚不能确定原因。
- 未修改业务代码；已取得具体播放器 URL，尚未验证本项目内实际播放。
- 初始 Git 状态：AGENT.md、AGENTS.md、Index.md、dev_log/ 为既有未跟踪文件，须保留。
- 独立审查：收起/退出详情不卸载 iframe；含 HTML 实体的 embed 地址未解码；纯视频文章因无图片提前返回。均未被证实为截图错误根因，纯视频入库是否纳入范围待确认。
- 本轮 git diff --check 无输出；三份索引引用的任务文档均存在。文档仍为未跟踪状态，git diff 检查不覆盖其全部内容，不能作为业务验证结果。
