# PicGen 双模式 UX 验收报告

验收开始：2026-07-11
当前记录时间：2026-07-11T09:22:18Z
实施规格：`TASK-UX-MASTER.md`、`TASK-UX-IMPLEMENT.md`、`TASK-UX-ACCEPTANCE.md`

## 第 1 关：静态检查

最终一轮（所有发布阻断修复完成后）：

- `uv run --with coverage coverage run -m pytest -q`：381 passed，1 个来自 Starlette TestClient 的弃用警告，耗时 130.30 秒。
- `uv run ruff check .`：通过。
- `uv run mypy src`：22 个源文件通过。
- `node --check static/app.js`：通过。
- `git diff --check`：通过。
- `uv run --with coverage coverage report --include='src/picgen/*'`：源码覆盖率 88%，超过 80% 门槛；含测试文件的完整快照覆盖率为 93%。
- `uvx pip-audit`：无已知依赖漏洞。
- Python 包、静态资源戳、Compose、构建脚本和 README 已统一为 `0.1.55`。

本关发现并修复：

1. 偏好 PUT 曾被改成全字段 PATCH，破坏旧客户端的全量替换契约；模式切换又不能复用完整 PUT，否则会覆盖并发更新。
   - RED：`test_preferences_put_replaces_fields_but_mode_patch_is_isolated` 复现旧值错误保留。
   - 修复：恢复 `PUT /api/preferences` 全量替换；仅缺失 `ui_mode` 和新增清单字段时保留；模式和清单分别使用窄 PATCH。
   - GREEN：完整设置替换、`1792x1792` 外部尺寸保留、模式往返和清单持久化均通过。
2. 自助注册可选择任意组织并读取历史群数据，输出文件也只校验“已登录”。
   - RED：匿名组织枚举、伪造注册组织、跨用户已知 URL、未归属文件和跨群 URL 均被专门回归复现。
   - 修复：生产默认关闭注册；显式开放时新用户未分配且群空间按用户隔离；组织只能管理员分配；输出按 owner/分享/群资产/admin 授权并以 404 拒绝越权。
   - GREEN：owner、分享接收人、同群成员和管理员可读；其它用户与未归属文件均拒绝；重启后未分配状态不回填。
3. Logo 派生文件名截断后可能碰撞，最终成品 metadata 会覆盖上游尺寸/重试审计信息。
   - RED：两个 80 字符共同前缀源文件得到相同 `-logo.png`；最终替换后 `upstream_actual_size` 丢失。
   - 修复：长源名保留稳定路径摘要；metadata 按结构化字典合并。
   - GREEN：派生路径唯一，原始尺寸、重试和 Logo 字段同时保留。
4. SMTP 失败时通用管理员通知仍可能收到重置 token；成功生图通知会外发提示词和文件路径。
   - 修复：所有管理员兜底通知先清除 token；成功通知仅保留任务 ID、模型、尺寸、计数和耗时。
   - GREEN：SMTP 故障回归确认 `reset_token == ""`，通知文本不含提示词或文件 URL。
5. 动态输入框同时处于 hover/focus 时，hover 选择器 specificity 更高，导致聚焦后仍为灰底且无品牌绿 ring。
   - RED：新增三类输入控件 focus specificity 契约测试。
   - 修复：focus 选择器统一为 `:focus:not(:disabled)`。
   - GREEN：计算样式为白底 `rgb(255,255,255)`、品牌绿边框 `rgb(0,149,104)`、2px 浅绿 ring。
6. 旧式分享请求省略 `generated_image_id` 时曾信任客户端 URL，可伪造已知的他人输出路径；生产库中的历史无 ID 分享也可能继续授权。
   - RED：发送者引用受害者 URL 后，接收者错误获得文件读取权限。
   - 修复：新无 ID 分享必须解析到发送者自己的生成记录；schema v15 仅回填发送者自有的合法历史分享、规范化字段并删除无效记录；运行时分享和群资产授权只认结构化图片关联。
   - GREEN：合法历史分享迁移后保留，伪造历史分享删除；伪造路径、无 ID 群资产均拒绝，既有 owner/分享/同群/admin 回归通过。
7. 上传区最初缺少可达的 active、disabled 和 loading 状态，随后终审又发现多入口并发读取由“最后完成者”覆盖“最后选择者”。
   - RED：静态契约和真实 busy 浏览器状态检查复现缺口。
   - 修复：上传区补齐 active/disabled/loading；五类文件通道统一使用序列、用户代次和唯一 busy 所有者，清空、模式切换、部门资产、最新结果和账号切换均会使旧读取失效；专业 click/keyboard/drop 真正遵守 busy。
   - GREEN：真实浏览器故意延迟首个文件，简洁场景卡、表单、专业编辑图、mask、风格图和素材图均由后选文件生效；旧失败不写错误，旧 finally 不解锁新请求，生成结束后专业控件恢复。

## 第 2 关：Playwright 界面走查

实例：匿名 `127.0.0.1:8779`；鉴权 `127.0.0.1:8780`，独立临时数据库和 dummy key。浏览器为无头 Google Chrome/Chromium。

最终结果：

- 5 张场景卡顺序、封面、标题和副标题完整；hover 为 `translateY(-2px)`、Shadow 2、primary-4 描边。
- 5 个场景均进入对应动态表单；改图卡直接进入上传；375px 全程无横向溢出。
- 简洁模式隐藏模型、通道、质量、格式、压缩、连接设置、调试信息和原始响应。
- 海报提示词正确拼装，两条亮点和多选氛围不互相覆盖；确认勾选前提交禁用。
- 自由创作 `original_prompt` 逐字等价且不带 recipe；隐藏参考图不串场景。
- 行程日期标题不再生成伪站点；站点仅为乌鲁木齐、布尔津、喀纳斯、禾木、乌鲁木齐。
- 草稿在返回卡片页及简洁/专业往返后保留；专业模式不残留简洁专用隐藏 recipe。
- admin 切到简洁后退出重登仍为简洁；旧客户端 PUT 不带 `ui_mode` 不重置模式；模式往返不覆盖外部更新尺寸。
- 强制注销 admin 并在旧请求返回前登录 alice，alice 的提示词、结果、忙碌态和工作区均为空，无跨用户迟到响应污染。
- 有 1 张历史作品的老用户默认专业且不显示清单；零历史新用户默认简洁，清单可关闭且刷新后不再出现；完成下载后步骤 `[1,2,3]` 永久完成。
- 首单完成同时写入用户作用域 localStorage 与 `simple_checklist_completed` 服务端偏好；600ms 延迟回调捕获用户代次和存储键，切换账号不会写入新用户。
- 等待态 Skeleton 可见，结果区为下载主按钮、改图/同款/分享三个次按钮及更多菜单；375px 五个按钮高度均为 44px。
- Arco 专项：Primary/Secondary、Input、上传区、卡片、Radio、Steps、Alert、Skeleton、Empty、Message 的 default/hover/active/focus/disabled/loading 均有 token 规则；真实 busy 时按钮、表单和上传区 `aria-busy=true`，文字输入 `readOnly`，上传区原生 disabled，官方 loading icon 可见，radio 原生 disabled、Skeleton 为 grid。
- 发布阻断浏览器回归：注册关闭时 375px 页面无注册入口；显式开放后新用户资料显示只读“未分配”；海报参考图粘贴仍停留“竖版海报”；874x1800 源图提交的 edit payload 为 `874x1800`；登出后旧 gallery/share DOM 标记均消失。
- 文件竞态浏览器回归：慢首选/快后选覆盖简洁场景卡、简洁表单、专业编辑图、mask、风格图和素材图；后选均获胜。清空与模式切换拦截迟到读取，busy drop 被阻止，生成结束后专业上传控件从 disabled/aria-busy 完整恢复。
- 页面 JS error 为 0。鉴权脚本登录前探测 `/api/me` 以及主动销毁会话场景出现的预期 HTTP 401 单独记录，不是 JS 运行错误。

专业模式像素回归：

- 375x812：仅模式按钮掩码内有差异，掩码外 0 像素。
- 1440x900：掩码外 18 个抗锯齿边缘像素，最大单通道差值 1；布局、尺寸和文本位置无移动。
- 821、900、960、1040px 登录态顶栏无品牌/模式按钮重叠，均无横向溢出。

本关额外修复：

- 移动端新手清单原先被强制扩至近乎全宽；改为最大 304px、12px 外边距与内边距，保留右下浮动和可点击关闭按钮。

截图证据：

- `acceptance-shots/arco-style-tile.png`
- `acceptance-shots/simple-home-1440x900.png`
- `acceptance-shots/simple-poster-form-1440x900.png`
- `acceptance-shots/simple-home-375x812.png`
- `acceptance-shots/simple-ranking-form-375x812.png`
- `acceptance-shots/simple-waiting-1440x900.png`
- `acceptance-shots/simple-result-1440x900.png`
- `acceptance-shots/simple-result-375x812.png`
- `acceptance-shots/auth-simple-1440x900.png`
- `acceptance-shots/auth-simple-375x812.png`
- `acceptance-shots/final-security-simple-1440x900.png`
- `acceptance-shots/final-login-closed-375x812.png`
- `acceptance-shots/professional-before-1440x900.png`
- `acceptance-shots/professional-after-1440x900.png`
- `acceptance-shots/professional-before-375x812.png`
- `acceptance-shots/professional-after-375x812.png`

## 第 3 关：真实生成实测

实例：`127.0.0.1:8781`，`PICGEN_AUTH_ENABLED=false`，默认加载仓库 `.env`。全部由 Playwright 操作真实页面；没有 mock、curl 代替 UI 或本地合成生成图。报告不记录 Key。

### 1. 简洁模式竖版海报

- 输入：主标题“金秋北疆·喀纳斯”、副标题“禾木晨雾 · 湖畔木屋”、亮点“晨雾中的木屋 / 湖畔轻徒步”、氛围仅“山野度假”、手机全屏 1088x2240、Logo 开启。
- 路径：Responses API，`gpt-5.6-sol`，reasoning `xhigh`。
- 耗时：151.2 秒；HTTP 200；无重试。
- 服务端原图：`data/outputs/20260711/generate-052320-3d929658.png`。
- 完整性：PNG/RGB，1088x2240，3,664,016 bytes；requested/actual 都是 1088x2240。
- 验图：主标题、副标题和两条亮点逐字正确；场景、层级和留白完整。Logo 由产品既有浏览器最终成品流程叠加，位于扩大安全区后的标准左上位置，透明背景贴合且不压文字。
- UI：`acceptance-shots/real-poster-result-1440x900.png`。
- 3 倍像素裁剪：`real-poster-title-3x.png`、`real-poster-subtitle-3x.png`、`real-poster-highlights-3x.png`、`real-poster-logo-3x.png`。

### 2. 简洁模式改图

- 源图：上一项服务端原图。
- 指令：“只把主标题文字改为：初雪喀纳斯，其余内容全部保持不变”。
- 路径：既有 Images Edit API，`gpt-image-2`。
- 耗时：58.9 秒；HTTP 200；首轮通过，未重试。
- 服务端原图：`data/outputs/20260711/edit-052923-54b7a89d.png`。
- 下载成品：`acceptance-shots/real-edit-final-with-logo.png`。
- 完整性：原图 PNG/RGB、下载 PNG/RGBA；均为 874x1800。上游保持纵横比但从 1088x2240 等比缩小；本地没有强拉伸。
- 验图：主标题逐字变为“初雪喀纳斯”；副标题、两条亮点和 Logo 均逐字/逐项正确。主体构图保持，存在模型级轻微纹理重绘与等比重采样。
- UI：`acceptance-shots/real-edit-result-1440x900.png`。
- 3 倍像素裁剪：`real-edit-title-3x.png`、`real-edit-subtitle-3x.png`、`real-edit-highlights-3x.png`、`real-edit-logo-3x.png`。

### 3. 简洁模式行程路线图

- 输入：标题“北疆秋日之旅”、日期“9/5 - 9/12”；D1 乌鲁木齐→布尔津，D2 布尔津→喀纳斯，D3 喀纳斯→禾木，D4 禾木→乌鲁木齐。
- 请求站点没有日期伪站点；D1 起终点展开为两个节点，顺序完整。
- 路径：`gpt-5.6-sol` 生成背景，程序 SVG 叠加精确标题、节点和路线。上游 `/v1/files` 返回 404 后自动回退内联参考图并成功完成。
- 耗时：279.7 秒；HTTP 200。
- 服务端 SVG：`data/outputs/20260711/itinerary-map-053943-a9a5268a.svg`，12,563,780 bytes，非空且含全部精确文本。
- 下载成品：`acceptance-shots/real-itinerary-final-with-logo.png`，PNG/RGBA，1792x1792，7,166,718 bytes。
- 验图：4 天地点和顺序正确；喀纳斯/禾木在北、乌鲁木齐在南；标题日期正确；Logo 位于左上安全留白，路线和标签不遮挡。
- UI：`acceptance-shots/real-itinerary-result-1440x900.png`。
- 3 倍像素裁剪：`real-itinerary-title-date-3x.png`、`real-itinerary-north-stops-3x.png`、`real-itinerary-south-stops-3x.png`、`real-itinerary-logo-3x.png`。

### 4. 专业模式回归

- 从简洁模式切换进入旧工作台，提示词“宁静的北疆湖畔木屋，清晨薄雾，远山倒影，真实旅行摄影风格，无文字”，可见尺寸卡选择 1024x1024。
- 路径：既有 Images Generate API，`gpt-image-2`，transport `images-generate`。
- 耗时：48.3 秒；HTTP 200。
- 服务端原图：`data/outputs/20260711/generate-054957-b3e087d8.png`。
- 下载成品：`acceptance-shots/real-professional-final-with-logo.png`。
- 完整性：原图 PNG/RGB、下载 PNG/RGBA；均为 1535x1024。
- 上游无视 1024x1024 返回 1535x1024。本地遵循不失真策略保留原尺寸，页面参数摘要和底部红色提示均明确显示实际 1535x1024、未缩放。
- 旧结果区、参数摘要、耗时、本地落盘、Logo 下载、版权/文字检查均正常；UI 证据：`acceptance-shots/real-professional-result-1440x900.png`。

## 第 4 关：回归复跑

通过。

- 第 3 关之后的独立 correctness/security/UX 审查发现注册组织越权、文件对象授权、Logo 名称碰撞、偏好契约和跨账号迟到回写等发布阻断，均先加 RED 测试再修复。
- 最终代码快照执行完整第 1 关：381 tests、88% 源码覆盖率、Ruff、mypy、Node、diff check 和依赖审计全部通过；此后仅更新验收文档。
- 最终快照重跑真实浏览器受影响流程：注册门控、组织只读、跨账号清屏、清单双端持久化、场景粘贴、Arco busy 六态和编辑尺寸请求，全部通过且 JS error 为 0。
- 四项真实生成文件仍来自第 3 关同一生成核心；后续唯一影响上游 payload 的修复是简洁改图尺寸由固定正方形改为源图尺寸，最终浏览器已截获并确认 874x1800 payload。按所有者此前“先别继续生成”的要求，没有为该参数修复额外产生一次付费改图。

## 第 5 关：发版、发布、部署

通过。

- 发布分支 `release/0.1.55-simple-mode` 经 PR #27 合并到受保护的 `main`；必需检查 `validate` 通过，合并提交为 `e5755598cc9ad769328d301b17f983ef8dad6607`。合并后已确认 `main` 仍启用严格分支保护、必需检查、1 人审批和管理员约束。
- 从上述合并提交构建并发布 `minorli/picgen:0.1.55`。多架构索引摘要为 `sha256:f6e0365e067e0b68901327d08b3e585e4c2e01722749b9e93e85cf0253a67e03`，amd64 manifest 摘要为 `sha256:2569efb5323fa6d29e66a2f390b1466fdc3e54a02f59bd742c05392b7c214e13`。
- 部署前生产 SQLite 已备份到 `/vol1/data1/picgen/backups/auth-20260711-pre-0.1.55.sqlite3`；大小 3,780,608 bytes，`quick_check=ok`，SHA256 为 `be91eb6d7ace9a854f06514f85184295a15a2ae438c3316f2f68c7b4bc73bd4f`。
- fnfarm Compose 仅把镜像标签从 `0.1.53` 改为 `0.1.55`；原文件和部署后文件 SHA256 分别为 `dbd53744f4711cf207d305af2e3173b315ab9df3bc9ea1a8a22acc53896ca4c5`、`57302dc2b392f6a8a04adaa4da36cda3f2d4882b96285d515f3991b98adc641d`，原文件备份为 `/vol1/data1/picgen/docker-compose.yml.bak-0.1.53`。
- 部署后容器持续 `running/healthy`、重启数为 0；`/api/ready` 返回版本 `0.1.55`、存储可写、上游客户端就绪。静态资源戳均为 `0.1.55`，数据库 `quick_check=ok` 并完成 schema v15，既有用户数保持 15。
- 生产真实冒烟通过：一次性账号向 `/api/image-jobs` 请求 1024x1024、单图、无 Logo；`images-generate` / `gpt-image-2` 在 26.21 秒返回 HTTP 200。上游原始像素为 1254x1254，本地按同宽高比 Lanczos 缩小，最终文件与数据库记录均为真实 1024x1024 PNG，767,088 bytes。
- 冒烟结束后测试图片、生成任务、会话和用户全部删除；复核对应任务/图片/用户计数均为 0、总用户数恢复为 15。随后连续观察五分钟，容器未重启，错误级日志、Traceback 和 HTTP 5xx 计数均为 0。

## 已知限制

1. 上游 Images API 可能不遵守请求尺寸。差异较大时本地不强行拉伸，保留上游原图并给出人话提示；这避免失真，但成品尺寸可能与选择值不同。
2. `gpt-image-2` 局部改图可对非目标区域产生轻微纹理重绘，并可能等比缩小；本次目标文字和保留文字均通过，无需重试。
3. 当前上游不提供 `/v1/files`，路线图会记录一次 404 warning 并自动回退内联参考图；本次回退成功，不影响最终结果。
4. 无鉴权验收实例没有生成图片数据库 ID，Logo 最终成品层在浏览器完成；鉴权生产实例会通过既有 final-image API 持久化最终版本。
