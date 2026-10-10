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

## 0.1.66 收尾与发布记录

记录时间：2026-07-12T08:25:00Z

### 交付内容

- A 组：空 `param` 恢复候选数降级；PNG-8 palette + `tRNS` mask 恢复逐像素合成；编辑结果按源画布到结果画布的宽度比例缩放官方 Logo 检测区域，并补齐分享/历史来源缺失的画布尺寸。
- B 组：结构化错误遍历限制为 8 层，真实深层上游 400 不再触发递归 500；字体子集失败继续尝试候选目录且不清空其它缓存；两个路线图 SVG 渲染入口移到工作线程；重复 `http.disconnect` 维持断连语义；Logo 保留诊断记录匹配率、像素数、阈值、依据和候选关联；Responses 少图时显示请求数与返回数。
- C 组：入口和说明统一为“我的收藏”，可见共享图片支持 per-viewer 收藏；取消收藏筛选同步隐藏说明；行程确认只要求核对真实提交的标题、日期和地点顺序并删除死代码；配置默认 Responses 模型携带 reasoning；团队聊天只在消息变化时重绘，并隔离乱序响应、跨房间发送和旧已读回调；简洁模式壳层使用既有 Arco token；长标题/副标题分档缩小并截断。
- 独立终审追加修复：Pillow 对 TIFF 等预检未识别格式抛出的 `DecompressionBombError` 转成受控 `ValueError`；旧聊天已读完成不再清除新请求错误。
- 版本、Compose、构建脚本、README、页脚和四个静态资源缓存戳统一为 `0.1.66`；没有新增运行时依赖。
- 清单开头描述的 `/tmp/picgen-0.1.65-mode-toggle` 和 `fix/0.1.65-mode-toggle` 在本轮开始时已不存在，因为 0.1.65 已通过 PR #38 发布部署。其绿色模式按钮改动已存在于基线，本轮保留并纳入 C6 验收，没有重复发版或伪造接管记录。

### 自动化与浏览器验证

- 最终提交快照运行 `./scripts/check.sh`：442 passed，Ruff 通过，Mypy 22 个源文件通过；唯一警告为既有 Starlette TestClient 弃用提示。
- 覆盖率快照在终审新增 3 条回归前为 439 passed、源码覆盖率 88%；新增回归随后全部纳入最终 442 项全量测试并通过。
- `node --check` 对 `static/app.js`、`static/logo-placement.mjs`、`static/responses-settings.mjs` 全部通过；`git diff --check` 和 `uv lock --check` 通过；`uvx pip-audit` 未发现已知漏洞。
- Playwright 在 1440、1040、900、821、375px 检查简洁模式顶栏，无重叠或横向溢出；模式按钮默认/hover/active 分别为 primary-8/7/9，白色图文，键盘 focus 为 primary-2 2px ring。
- B6 mock 请求 3 张、Responses 返回 1 张，页面精确显示“本次请求 3 张，上游返回 1 张”。C2 行程确认文案精确为“请核对标题、日期和每天的地点顺序。”
- C5 在等价 7.5 秒的五次轮询后，滚动位置、文字选区和消息 DOM 节点均未变化；延迟私聊发送后切回群聊，响应未串入当前房间且未推进当前房间已读。后续终审补充了旧已读回调与新错误竞态的 Node 行为回归。
- C7 真实 SVG 长标题为 52px、宽 624/1088，副标题为 21px、宽 630/1088，均未越界或重叠；不可达的 `_dense_index_labels` 及其 `width-480` 常量已删除。
- 专业模式差分：隐藏模式按钮后，剩余变化精确落在 C1 强制改名“我的收藏”区域；再掩码该区域后，桌面和移动端 changed pixels 均为 0。C1 与“只有模式按钮可变”的原文字面要求冲突，因此报告把 C1 文案列为第二个明确、不可避免的需求例外。

### A3 真实生成与编辑

- 隔离实例加载真实生产同源上游配置、关闭登录；版权与文字审查请求在浏览器侧 mock，未产生无关付费调用。生成和编辑均通过真实页面操作，尺寸均选择 1088x2240、Logo 开启。
- 真实生成走 Responses、`gpt-5.6-sol`、reasoning `xhigh`，上游流耗时 52.75 秒，无重试；服务端保存 RGB 1088x2240 原图，3,474,728 bytes。
- 首次浏览器证据脚本在生成成功后用 `fetch(data:)` 导出本地 Logo 图时报错；这是测试工具错误，未重发付费生成。随后把同一已付费原图回放到同一 UI 状态，完成 Logo 合成并点击“改这张图”。
- 真实编辑仍走 Responses、`gpt-5.6-sol`、reasoning `xhigh`；同源 `/v1/files` 返回 404 后按既有逻辑回退内联 Base64，上游流耗时 54.72 秒，无重试。上游原始图 874x1799，服务端按现有严格尺寸策略归一化为 RGB 1088x2240，3,480,859 bytes。
- PIL 只读像素验收：生成/编辑成品均为 1088x2240；原始底图三个候选位置的官方 Logo 匹配率全部为 0；最终生成/编辑标准左上位置匹配率分别为 0.9534/0.9507，每张恰好 1 个大于等于 0.9 的高置信 Logo。原图到成品的变化仅位于 `(42,42)` 起的 174x54 官方 Logo 区域，裁剪检查无重影、无第二枚 Logo。

### 发版与部署

- 发布 PR [#39](https://github.com/Minorli/picgen/pull/39) 的 `validate` 检查通过（2 分 22 秒），2026-07-12T08:02:03Z squash 合并；合并提交为 `71e022b0826a97d8c3b5d16d5b57f2dc281e23f5`。
- 合并时仅临时摘除 `enforce_admins`；合并后立即恢复并复核：strict checks=true、必需检查 `validate`、审批数 1、enforce_admins=true。
- 从合并后的 `main` 构建并推送 `minorli/picgen:0.1.66`。OCI 索引 digest 为 `sha256:fed95949d884b62d1120d94360d60b700a57ae1416391fb45777db69e7bd76f2`，amd64 manifest 为 `sha256:df9f2684dd4a04017fa858f6f6c81bf384464cdfa3dd2953e1a669a163e06732`。
- 部署前使用运行中容器内的 SQLite backup API 做在线备份，最终文件为 `/vol1/data1/picgen/backups/auth-20260712-pre-0.1.66.sqlite3`，3,956,736 bytes，`quick_check=ok`，SHA256 `5149ee15ad48250f8321b024a7ea4a47bdd4ab763a925a1d1fb1ede99f1dee68`。
- 原 Compose 备份为 `/vol1/data1/picgen/docker-compose.yml.bak-0.1.65`；只用 `sed` 把镜像标签从 0.1.65 改为 0.1.66。原/新 SHA256 分别为 `d5adae4915825f5da2a7c88e33d6c8bfb7cf84055b58a8ece0a65d0dcfa6991c` / `a6f4c956c2f8ae92a72d6dab4314bfc57812e31d8f5b85ee68d00aa77c7fd4ba`，`diff -u` 仅一行镜像标签变化。
- 生产容器于 2026-07-12T08:13:33Z 启动；`/api/ready` 返回 `ok:true`、版本 0.1.66、存储可写、上游客户端就绪。首页 CSS/App、App 内两个模块和页脚版本均为 0.1.66；容器持续 running/healthy、重启数 0；生产 DB `quick_check=ok`。
- 生产冒烟首次在创建用户前因测试脚本把真实部门 `PD & OPS` 写成 `PD&OPS` 而被组织校验拒绝；没有创建用户、没有上游调用、没有业务数据变化。只读核对启用组织后按清单允许的上限重试一次，第二次通过，未再重试。
- 成功冒烟使用随机临时用户/会话真实请求 1024x1024、单图、无 Logo；`images-generate` / `gpt-image-2` 在 52.16 秒返回 HTTP 200。上游原图 1254x1254，最终 PIL 实测 RGB 1024x1024、911,801 bytes、候选数 1。
- 冒烟后临时用户、会话、job、image 行、输出图、空目录和远端临时脚本全部删除；脚本内复核 users/jobs/images 均为 0，生产复核 `smoke0166%` 用户为 0。
- 从容器启动到 2026-07-12T08:25:00Z 连续观察 687.1 秒：100 条结构化记录中 ERROR=0、Traceback=0、HTTP 5xx=0、warning=0；容器未重启。

### 已知限制

1. 当前上游仍没有同源 `/v1/files`，Responses 参考图/编辑会先记录一次已处理的 404，再回退内联 Base64；A3 实测回退成功，但会增加请求体积。
2. 上游可能返回低于请求尺寸的同比例图片。PicGen 会用 Lanczos 归一化到严格画布，尺寸契约可满足，但放大不能补回原生细节；A3 编辑的真实上游尺寸为 874x1799。
3. A3 使用关闭登录的隔离实例，因无数据库图片 ID，官方 Logo 最终层只在浏览器生成；生产鉴权实例仍通过既有 final-image API 持久化。
4. 专业模式像素不变存在两个需求明确例外：模式切换按钮配色，以及 C1 的“我的收藏”可见文案；其它区域差分为零。

## 0.1.67 数据库存储就绪与发布记录

记录时间：2026-07-18T08:48:37Z

### 故障与修复

- 2026-07-18T06:06:50Z，同盘 PostgreSQL 临时写入把 `/vol1` 推到 ENOSPC，生产 PicGen 随后出现 `sqlite3.OperationalError: database or disk is full`；不是 PicGen SQLite 自身异常膨胀。旧容器仍以 `/api/health` 判定为 healthy，形成数据库不可写但容器假健康的窗口。处置后 `/vol1` 恢复到约 99 GB 可用、77% 使用率，生产数据库 `quick_check=ok`，没有损坏证据。
- `/api/health` 继续只表示进程存活；`/api/ready` 新增输出盘与 SQLite 所在盘的相邻临时文件 write、flush、fsync、unlink 探针，并以 HTTP 503 表示任一依赖未就绪。
- SQLite 探针使用 0.25 秒只读连接、`quick_check(1)`、schema v15 与 `users` 表校验；完整性成功结果按数据库文件签名缓存最长 5 分钟，存储组合结果缓存 5 秒。
- readiness 使用独立 `CapacityLimiter(1)`，并发探针等待不占业务共享 worker；Dockerfile 与示例 Compose 的健康检查均改为 `/api/ready`。
- 包版本、锁文件、镜像/Compose、README、静态页脚和四个静态资源缓存戳统一为 `0.1.67`；没有新增运行时依赖。

### 自动化与评审

- 最终提交快照执行 `./scripts/check.sh`：457 passed，Ruff 通过，Mypy 23 个源文件通过；唯一警告为既有 Starlette TestClient 弃用提示。
- `node --check` 对 `static/app.js`、`static/logo-placement.mjs`、`static/responses-settings.mjs` 全部通过；`uv lock --check`、`git diff --check` 通过；`uvx pip-audit` 未发现已知漏洞。
- 回归覆盖正常/损坏/未初始化 SQLite、业务表页损坏、数据库与输出盘不可写、fsync 失败清理、探针缓存、auth-enabled 健康路径、liveness 不触盘、HTTP 503 与 Docker 契约。
- 独立 correctness/security 终审在修正真实写入证明、WAL/完整性语义和并发 worker 风险后复查通过，最终无阻断发布的 HIGH/MEDIUM。

### 发版与部署

- 发布 PR [#41](https://github.com/Minorli/picgen/pull/41) 的 `validate` 检查通过（2 分 14 秒），2026-07-18T08:29:22Z squash 合并；合并提交为 `034f27ec8ac1575969461c8ab04e43d3966a3ac4`。
- 合并时仅临时摘除 `enforce_admins`；合并后立即恢复并复核：strict checks=true、必需检查 `validate`、审批数 1、enforce_admins=true、required conversation resolution=true。
- 从合并后的 `main` 构建并推送 `minorli/picgen:0.1.67`。OCI 索引 digest 为 `sha256:9658389acaf8493c80df68bc7acb5c5b32d2df4bf09079399b17426abbcf0eb4`，amd64 manifest 为 `sha256:f7100730dd4f070743c3b1e1cbbb3bf9a1ca20adacb8025e8815830dda5ab5a3`。
- 部署前使用运行中容器内的 SQLite backup API 做在线备份：`/vol1/data1/picgen/backups/auth-20260718-pre-0.1.67.sqlite3`，3,956,736 bytes，权限 600，`quick_check=ok`、schema 15、用户 15，SHA256 `18d5e5bc42287b1117924e0ebb61034125967ea80f03cce4c549bc949926f781`。
- 原 Compose 备份为 `/vol1/data1/picgen/docker-compose.yml.bak-0.1.66`，SHA256 `a6f4c956c2f8ae92a72d6dab4314bfc57812e31d8f5b85ee68d00aa77c7fd4ba`。生产 Compose 最终只变更镜像 `0.1.66 -> 0.1.67` 与显式 healthcheck `/api/health -> /api/ready` 两行，新 SHA256 为 `799d46b64b05d2185050457cf8f113c268be81b7fd30509c70017408392f6f89`。
- 最终容器于 2026-07-18T08:42:42Z 启动；持续观察至 08:48:37Z（355 秒），状态始终 running/healthy、重启数 0。Docker 每 30 秒实际请求 `/api/ready` 且全部 HTTP 200；最终响应为 `ok=true`、输出存储可写、数据库可写、上游客户端就绪、版本 0.1.67。
- 首页 CSS/App、App 内两个模块与页脚缓存戳均为 0.1.67；生产数据库保持 `quick_check=ok`、schema 15、用户 15；两个挂载点没有遗留 readiness 临时文件。观察期日志无 ERROR/CRITICAL、Traceback 或 HTTP 5xx。
- 本次修复不改变生图业务路径，部署验证没有调用付费上游；观察期内真实登录用户的配置、偏好、图库、任务、分享、聊天和历史图片读取均正常。

## 0.1.68 空结果提示与诊断发布记录

记录时间：2026-07-31T14:56:46Z

### 故障与修复

- 生产 job 449（request ID `de557b9d3dd7`）的 Responses 流在约 148 秒后结束，共解析 13 个事件，但没有图片或文字，PicGen 按预期记录为 HTTP 502 / `upstream_no_image`；容器没有崩溃、重启或 OOM，磁盘与数据库均正常。
- 全局错误映射此前把所有 `upstream_no_image` 都改写为“路线图 AI 底图这次没有生成成功”，导致普通 `/api/image-jobs` 海报任务收到误导文案。0.1.68 改为通用的“图片生成服务这次没有返回图片”，继续保留错误码和 request ID。
- Responses 流日志新增最多 20 个去重事件类型、终态与上游错误码；三个上游可控字段先遮蔽 Key、token、组织 ID 等敏感内容再限长。只有真正没有图片和文字的流记为 WARNING，失败的 image tool 对象不再误判为文字输出。
- 非幂等付费生图仍保持单次请求，不对空结果、HTTP 502、网络错误或超时自动重发，避免用户未确认时重复计费。
- 版本、锁文件、镜像/Compose、README、静态页脚和四个静态资源缓存戳统一为 `0.1.68`；没有新增运行时依赖或数据库迁移。

### 自动化与评审

- 最终代码快照执行 `./scripts/check.sh`：459 passed，Ruff 通过，Mypy 23 个源文件通过；唯一警告为既有 Starlette TestClient 弃用提示。
- `coverage` 对 `src/picgen` 的全量 459 项测试覆盖率为 88%，高于 80% 门槛；`responses.py` 覆盖率为 87%。
- `node --check` 对 `static/app.js`、`static/logo-placement.mjs`、`static/responses-settings.mjs` 全部通过；`uv lock --check`、`git diff --check` 通过；`uvx pip-audit` 未发现已知漏洞。
- 新增回归覆盖普通海报空结果的通用文案、request ID、单次上游调用、失败 job 与零图片记录，以及 SSE 终态、空流 WARNING、失败 tool 非文字判定和结构化 JSON 日志脱敏。
- 独立代码审查发现并推动修正两个边界：结构化字段原先只截断未脱敏，以及失败 `image_generation_call` 可能误记 `has_text=true`；修正后无阻断 correctness/security 问题。
- 本地正式镜像构建成功，以非 root `picgen` 用户启动；`/api/ready` 返回存储、数据库与上游客户端就绪，版本为 0.1.68，首页 CSS/App 缓存戳为 0.1.68。

### 发版与部署

- 发布 PR [#43](https://github.com/Minorli/picgen/pull/43) 的 `validate` 检查通过（2 分 12 秒），2026-07-31T14:46:06Z squash 合并；合并提交为 `729786270eee620a2976466cd4282e227406061c`。
- 合并时仅临时关闭 `enforce_admins`；合并后立即恢复并复核：strict checks=true、必需检查 `validate`、审批数 1、enforce_admins=true、required conversation resolution=true。
- 从合并后的 `main` 构建并推送 `minorli/picgen:0.1.68`。OCI 索引 digest 为 `sha256:b8999323010fdd81c205bacf39b8618de17b7f5fdbfb5cee36709a6a71cd9e08`，amd64 manifest 为 `sha256:355de2b1acb84ad84ddf8e7cc30f3dd61d7207c2c114b07f3cc7a86f3ebc42f8`。
- 部署前使用 SQLite backup API 创建在线一致性备份 `/vol1/data1/picgen/backups/auth-20260731-pre-0.1.68.sqlite3`，4,198,400 bytes，权限 600，SHA256 为 `95eb2385cd7b342541e24a660ebad647653c41ebcb759967bd1f0cffe9f63f83`；`quick_check=ok`、schema 15、用户 15、任务 368、图片 359，与源库一致。
- 原 Compose 备份为 `/vol1/data1/picgen/docker-compose.yml.bak-0.1.67`，SHA256 为 `799d46b64b05d2185050457cf8f113c268be81b7fd30509c70017408392f6f89`。生产 Compose 仅把镜像标签 `0.1.67 -> 0.1.68`，新 SHA256 为 `fb9fd2224245ef4bda5675eacaff85ecdada8bb59139033896a4ae7a1209bbf6`。
- fnfarm 两次从 Docker Hub 拉取新镜像均在分层 image configuration 阶段因 EOF 失败，旧容器在此期间持续 healthy。改用已验收 amd64 镜像导出 tar 后经内网传输，源端与目标端 tar SHA256 均为 `fbdb15cf91897e2b99ec46d4a86b438e844ce35d94bfc66f5082f3ee20864824`；`docker load` 成功后才切换 Compose，临时 tar 已从两端清理。
- 生产容器于 2026-07-31T14:53:39Z 启动，观察至 14:56:46Z（约 187 秒）：始终 running/healthy，重启数 0、OOM=false；Docker 每 30 秒请求 `/api/ready` 均为 HTTP 200，最终响应版本 0.1.68，输出存储、数据库写入与上游客户端全部就绪。
- 生产数据库部署后仍为 `quick_check=ok`、schema 15、用户 15、任务 368、图片 359；日志无 ERROR/CRITICAL、Traceback 或 HTTP 5xx，`/vol1` 剩余约 72 GB，`/vol2` 剩余约 333 GB。
- 生产无付费生图冒烟：本次修复覆盖错误提示与诊断日志，自动化、容器内函数验收和 readiness 足以验证交付；为避免无业务价值的额外扣费，没有重放 job 449，也没有创建临时用户或业务数据。

## 2026-09-11 线上故障调查与本地修复（待发布）

### 生产证据

- 调查范围：北京时间 2026-09-11 00:00 至约 23:31；通过 fnfarm 的 Docker 日志和只读 SQLite 查询交叉核对，共 4 次生图，3 次成功、1 次失败。

| 任务 | 开始时间（北京时间） | 结果 | 耗时 | Request ID |
| --- | --- | --- | --- | --- |
| 465 | 15:53:50 | 失败，`upstream_timeout` | 15.1 秒 | `a6054b6f301c` |
| 466 | 15:57:30 | 成功，1 张 | 146.3 秒 | `210ca852ee50` |
| 467 | 16:03:08 | 成功，1 张 | 141.6 秒 | `323b9629885a` |
| 468 | 16:05:22 | 成功，1 张 | 102.1 秒 | `6f0d9d1331aa` |

- 四次任务均为 Responses、`gpt-6-astra`、`1088x2240`。失败任务的日志明确为 `ConnectTimeout`，实际约 15 秒；没有收到上游 HTTP 错误或 SSE 结果。相同用户随后提交的任务 466 成功。
- 三次成功任务均收到 `response.completed` 和图片，保存尺寸均为 `1088x2240`，数据库记录图片已送达浏览器。后续 `has_image=false, has_text=true` 的调用是成功后的文字检查，不是失败生图。
- 生产仍为 `minorli/picgen:0.1.69`，容器自 2026-09-10T01:09:56Z 启动后重启数为 0；`/api/ready` 的存储、数据库与客户端检查均通过。
- 当前配置为读写等待 1200 秒、建连/连接池等待 15 秒、最大额外重试 2 次、退避 0.75 秒、尺寸重生 0 次。旧代码的 POST 路径实际完全没有连接重试，并把连接超时日志的 `timeout_s` 错记成 1200。
- 调查时在生产容器内对上游站点做 3 次无鉴权 GET 探测，均为 HTTP 200，耗时 0.48–0.54 秒。现有证据支持当时发生短暂建连故障，无法进一步确认 TCP、DNS、TLS 或上游入口中的具体环节；没有重新调用付费生图。

### 本地修复范围

- 生成、编辑、Files 上传和 Responses 共用初始连接重试；仅捕获 `ConnectTimeout` / `ConnectError`，复用现有次数及退避配置。默认最多 3 次建连尝试，配置为 0 时禁用重试。
- 使用 HTTPX 原始 Request 对象身份确认失败发生在首次连接。重定向后的连接失败（包括跳回同 URL）不重发原始 POST；读写错误、连接池超时、协议错误、HTTP 错误与响应体读取失败均不自动重放生图。
- 保留原有 HTTPX 环境代理、连接池及 HTTP/2 配置；读取响应体在重试范围之外，成功和失败路径都关闭响应流。
- 连接超时提示改为“连接图片生成服务超时”，`upstream_timeout` 错误码保持不变；连接/连接池超时日志记录实际 15 秒阈值，重试日志包含 `retry_phase=connect`。
- 已对照 [HTTPX 连接重试文档](https://www.python-httpx.org/advanced/transports/) 与本地 HTTPX 源码核实连接异常语义。此补丁缓解短暂建连失败，不能保证持续网络故障或上游生图故障自行恢复。
- 当前仅修改本地代码、测试与说明；尚未提交、发布镜像或部署到 fnfarm。

后续交付状态：上述 9 月 11 日的连接重试补丁已于 2026-10-10 纳入 0.1.70 发布，并随最终版本 0.1.71 部署；以下为原始本地验证记录。

### 验证结果

- 新增 60 项参数化回归，覆盖连接失败后恢复、重试耗尽/关闭、读写与 HTTP 错误不重放、重定向（含同 URL）后不重放、响应体读取失败及流关闭；更新旧连接超时测试，验证 15 秒日志阈值与准确提示。
- `./scripts/check.sh` 全部通过：Ruff 通过、Mypy 23 个源文件通过、pytest **520 passed**（93.25 秒）；唯一警告为既有 Starlette TestClient 弃用提示。`git diff --check` 通过。
- 独立代码审查未发现阻断问题。生产访问均为只读诊断与站点 GET 探测，未修改生产配置或创建任务。

## 0.1.70 平台运行审计与修复验收（2026-10-10）

### 生产基线与历史数据

- fnfarm 运行 `minorli/picgen:0.1.69`，健康检查通过，重启数 0、无 OOM；审计时内存约 86 MiB，`/vol1` 剩余 132 GB、`/vol2` 剩余 180 GB。
- SQLite `integrity_check=ok`：16 个用户、389 个任务、379 条图片记录。366 次成功、23 次失败，无进行中/悬挂任务，任务图片计数全部匹配，无孤儿图片记录。
- 历史失败分类：18 次上游通用错误、2 次空图、1 次尺寸不符、1 次连接超时、1 次旧版未翻译的断流错误。最近一次失败仍为 9 月 11 日的连接超时；9 月 28 日最近 4 次生图全部成功。历史错误保留原始事实，不重放付费任务。
- 对全部图片路径核验：378 个文件存在且 Pillow 验证通过，实际尺寸均与数据库一致。图片 ID 158（任务 160，2026-06-10）的成品及源图缺失；当前图片目录和旧数据目录均无副本，已有备份是数据库备份，无法从中恢复图片内容。本次保留记录，不伪造图片或将历史成功改成失败。
- 当天已按用户要求在生产 Compose 显式开启 `PICGEN_SELF_REGISTRATION_ENABLED=true`。注册按钮、注册接口均已开放；本次发布继续保留。Telegram token/chat 配置存在；当前容器日志无通知失败，但旧版未记录发送成功，不能据此证明历史每条通知均已送达。

### 审查范围、问题与处理

审查覆盖上游 HTTP/SSE、路由和任务记录、账号认证/密码重置、权限与数据隔离、存储/就绪检查、通知、前端登录/任务/历史/结果工作流，以及依赖和发布配置。按实际证据修复，未对整库做无关重构。

| 优先级 | 已确认问题 | 0.1.70 处理 |
| --- | --- | --- |
| 高 | 显式 Responses 失败可能被部分预览图掩盖，或丢失限流等错误分类 | SSE/JSON 在提取结果前检查终态，失败不作为成功；保留旧版仅 partial 流兼容 |
| 高 | 主动改密后旧找回链接仍可覆盖新密码；并发消费重置令牌未串行化 | 同事务作废旧令牌；跨 worker 写事务内验证/消费；管理员配置密码变更撤销旧会话 |
| 高 | 内部异常写入历史或返回浏览器；成功响应调试字段可能回显凭据 | 内部错误公共详情隐藏、任务历史使用安全提示、告警脱敏；调试数据递归脱敏并限制深度 |
| 高 | 打开历史/分享作品后残留另一个结果的重跑参数 | 切换外部结果清除重跑快照，避免重跑错误任务 |
| 中 | 首次建连失败直接终止，连接超时误记 1200 秒 | 纳入 9 月 11 日待发布补丁；仅原始请求建连失败有界重试，日志记录实际 15 秒 |
| 中 | 次要统计写入失败会把已保存、已计费的成功任务标成失败 | 独立记录统计错误，继续交付已保存结果 |
| 中 | 启动异步加载跨账号完成、旧任务响应覆盖新列表 | 每个异步阶段校验用户上下文；任务请求序号保护；账号切换立即清空旧任务 |
| 中 | 任务界面只展示最近 8 条，无法浏览完整任务历史 | 新增按用户隔离的 `before_id` 游标分页及“加载更早任务”；失败可重试且不清空已有列表 |
| 中 | TG 未检查 JSON `ok`，429 不遵循等待时间，成功无日志 | 明确 `ok=true` 才记录成功；短时限流遵循 `retry_after`，长等待受控退出；增加脱敏投递日志 |
| 中 | 超深 JSON/SSE 可产生内部错误，JSON 失败先记成功日志 | 统一归类 `upstream_invalid_response`；校验后才记录成功 |

- 运行依赖扫描发现旧锁定 AnyIO 4.13.0 的两项已知漏洞；最低约束及锁文件更新到 4.14.2，并重新扫描。依据：[TLS 域名校验公告](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6)、[进程池阻塞公告](https://github.com/agronholm/anyio/security/advisories/GHSA-5p39-cfhj-2xmp)。
- 不对已发送的生图请求、HTTP 错误、读写超时、断流或重定向后建连失败增加重放。模型继续使用 `gpt-6-astra` / `gpt-image-2.5-sunburst`，无需数据库迁移或新增运行时依赖。

### 本地验证

- 独立审查互检了认证事务、上游重试和终态、统计故障处理、前端账号隔离；审查发现的问题均补回归后修复。
- 真实生图在隔离本地数据库执行 1 次，未创建生产业务任务或发送真实 TG：HTTP 200，约 48.17 秒，Responses `completed`，PNG `1088×2240`，无尺寸偏差，人工检查画面及文件解码正常。
- Playwright 真实浏览器验证：注册按钮可见；本地注册自动登录；旧任务从 20 条加载到 26 条，末页按钮隐藏；从历史打开真实成品并验证像素尺寸；退出并注册另一账号后旧任务立即清空，新账号列表为 0。
- 首轮完整检查 609 项通过；复审补充边界回归后，冻结代码执行 `./scripts/check.sh`：**612 passed**（139.39 秒），Ruff 和 Mypy 23 个源文件全部通过。唯一警告为既有 Starlette TestClient 弃用提示。
- JS 语法、锁文件一致性和差异检查通过；运行依赖 `pip-audit` 在升级后未发现已知漏洞。

### 后续改进建议（未纳入本次小版本）

1. 图片与数据库做成套备份，并定期核对文件存在性。优先解决已查实的历史图片缺失可发现性，增加界面“文件不可用”状态，而不是自动删除历史记录。
2. 在保持开放注册的前提下，增加每用户生成额度和并发限制，使管理员能管理共享上游成本。
3. 如果需要证明每次 TG 的投递结果，增加持久化通知记录和补发队列；当前日志只提供本次版本之后的发送观测，重启前未完成的后台通知仍可能丢失。
4. 会话 `last_seen` 写入按时间节流，降低高频只读接口的 SQLite 写锁争用；长期运行任务中断恢复需带 worker 归属或租约，避免简单启动清理误伤其他 worker。
5. 为图库增加日期/状态筛选与分页；逐步拆分前端认证、任务和结果模块，沿用本轮新增的可执行 JS 行为回归，避免一次性重写。

### 备份与发布准备

- 已完成在线 SQLite 备份 `/vol1/data1/picgen/backups/auth-20261010T031717Z-pre-0.1.70.sqlite3`，`quick_check=ok`，用户/任务/图片计数分别为 16/389/379；SHA256 `8e85055abc41ec592f7ce984f6edec63d2fb1382298a0461a405122e2796edb2`。
- 0.1.70 已从提交 `ddca3eaa993e0d136f1b5909223eb2807986dd6e` 构建发布，[GitHub CI](https://github.com/Minorli/picgen/actions/runs/38020238440) 全部通过，[Release](https://github.com/Minorli/picgen/releases/tag/v0.1.70) 与 Docker Hub 均已发布。镜像摘要 `sha256:a193d186170dcdd1fa4ef0d7f42c2ce4b325e74781f3f3823ae1a08e5b3378f4`，fnfarm 拉取摘要一致。
- 切换前再次在线备份到 `/vol1/data1/picgen/backups/auth-20261010T032419Z-pre-0.1.70.sqlite3`（SHA256 与上述备份一致）；Compose 备份为 `/vol1/data1/picgen/docker-compose.yml.bak-20261010T032419Z-pre-0.1.70`。
- 生产 0.1.70 于 `2026-10-10T03:24:20Z` 启动，healthy、重启数 0。部署后数据库仍为 16/389/379，`quick_check=ok`，注册开启，Astra/Sunburst 与 TG 配置保留；未认证任务请求为 401，注册空请求进入参数校验（400）而非关闭注册（403），日志无 WARNING/ERROR。
- [PR #46](https://github.com/Minorli/picgen/pull/46) 保留待独立审核：主分支要求 1 人批准，未修改或绕过保护。正式镜像和标签对应已经通过本地检查、独立代码审查及 GitHub CI 的提交。

## 0.1.71 部署验收发现的首页缓存修复（2026-10-10）

- 0.1.70 部署验收时复现：后端 `/api/ready`、容器 HTML 和无缓存 HTTP 请求均为 0.1.70，但浏览器普通导航仍拿到缓存中的 0.1.69 首页及旧资源 URL；手动刷新后立即恢复。原因是入口 HTML 没有明确缓存策略，浏览器会进行启发式缓存。
- 为避免改写已发布的 0.1.70 标签/镜像，另出 0.1.71，仅增加 `/` 与 `/index.html` 的 `Cache-Control: no-cache`（包含 304），同步版本戳。API 的 no-store、版本化静态资源和鉴权图片缓存策略保持原状。
- 新增 3 项回归：两个入口的 200/304 必须重新验证，以及 API/JS 策略不被改变；独立前端审查通过。首次使用此前已缓存旧 HTML 的浏览器仍需刷新一次，服务端新响应头无法追溯修改已经保存的旧缓存。
- 0.1.71 包含 0.1.70 的全部平台修复。最终冻结代码执行 `./scripts/check.sh`：**615 passed**（110.69 秒），Ruff、Mypy 23 个文件、JS 语法、锁文件检查全部通过；运行依赖再次 `pip-audit` 无已知漏洞。生产 TG 的只读 `getMe`/`getChat` 检查均为 HTTP 200 / `ok=true`，未发送测试消息。
- 最终发布提交：`24821d896216ed609e7022b880c99898bd141394`；[GitHub CI](https://github.com/Minorli/picgen/actions/runs/38020802633) 全部通过；[Release v0.1.71](https://github.com/Minorli/picgen/releases/tag/v0.1.71) 和 Docker Hub `minorli/picgen:0.1.71` 已发布。镜像摘要 `sha256:5626a8d94a53fa7ae4652565e41bb4d38ed6f48772523148c0e92417cae2ec1c`，生产拉取摘要一致。
- 最终切换前 SQLite 备份：`/vol1/data1/picgen/backups/auth-20261010T033345Z-pre-0.1.71.sqlite3`，`quick_check=ok`，SHA256 `938389673c2aa5eeee37445aaeb35a8fda7d4f7d928eae2c5a19dc317373a326`；Compose 备份 `/vol1/data1/picgen/docker-compose.yml.bak-20261010T033345Z-pre-0.1.71`。保留原有 0.1.69/0.1.70 镜像、全部数据挂载、环境配置及开启的注册开关。
- fnfarm 于 `2026-10-10T03:33:46Z` 启动 0.1.71，running/healthy、重启数 0、OOM=false；数据库 `quick_check=ok`，用户/任务/图片仍为 16/389/379，进行中任务 0；容器内 AnyIO 确认为 4.14.2。
- 本地容器及生产均验证入口 200 与条件请求 304 返回 `Cache-Control: no-cache`；本地容器 HEAD 也正确。生产真实浏览器刷新后页脚与脚本均为 0.1.71，注册按钮可见，配置中注册/TG 开启，模型仍为 Astra/Sunburst。
- 本次生产验证未创建测试账号或生成新任务，未发送 TG 测试消息；账号工作流和实际生图在隔离本地/验收容器验证，生产执行健康、配置、鉴权拒绝、注册参数校验、数据库与文件核对。临时本地服务器和验收容器已停止并清理，原有用户未跟踪文件保持不变。
- PR #46 已更新为最终 0.1.71 范围，待一位独立审核人批准后合并；主分支保护保持启用，发布标签和部署产物已完成，不将未合并描述为已合并。
