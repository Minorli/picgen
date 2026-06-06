# PicGen Console

一个面向 OpenAI 兼容图像生成 / 编辑接口的本地工作台，当前版本 **0.1.17**。它把
`/v1/images/generations`、`/v1/images/edits` 与 `/v1/responses`（含 `image_generation` 工具）
包装成统一可观测的代理，前端是一套零依赖的 Web 控制台。

适合场景：

- 本地图像 / 编辑日常实验
- 私有部署，对接兼容 OpenAI 协议的国内/自建上游
- 嵌入企业内部工具链，作为带审计、限流、健康检查的接口网关

## 界面预览

![PicGen Console 主程序界面](demo1.png)

## 0.1.17 主要特性

- **异步 + 连接池**：底层用 `httpx.AsyncClient`，含连接池、分段超时、指数退避重试。
- **类型化校验**：所有请求/响应走 Pydantic v2 模型，参数错误统一以中文报错返回。
- **结构化日志**：`logging` + 自定义格式（console / json 双模式），所有日志自动带 `request_id`，
  并对 `api_key / authorization / proxy_auth_token` 等敏感字段自动脱敏。
- **请求中间件**：
  - `RequestIdMiddleware` — 生成或透传 `X-Request-ID`
  - `SecurityHeadersMiddleware` — `X-Content-Type-Options / X-Frame-Options / Referrer-Policy / Permissions-Policy / Cache-Control`
  - `BodySizeLimitMiddleware` — 拒绝超大请求（默认 64 MB）
  - `RateLimitMiddleware` — 滑动窗口限流（默认 120 req/min + 20 burst/5s）
  - `ProxyAuthMiddleware` — 可选 Bearer / `X-Proxy-Token` 鉴权
  - `CORSMiddleware` — 配置化跨域
- **原子化落盘**：图片与 sidecar JSON 用临时文件 + rename 写入，崩溃不留半截文件；核心生成、
  反馈、分享和取图送达数据会进入 SQLite，便于管理员后续审计。
- **健康分级**：`/api/health` 仅看进程存活；`/api/ready` 联动客户端、磁盘可写性、版本号。
- **Telegram 通知**：可配置 Telegram Bot 接收后台/上游异常告警，也会在用户成功生成图片后发送详细摘要。
- **账号自助维护**：普通用户可登录后自助修改密码；忘记密码申请会通知管理员且对外保持枚举安全。
- **交付一致性**：请求集成 6 人游 LOGO 时，成品保存完成前下载按钮会进入处理中状态，避免误下无 LOGO 底图。
- **私有文件缓存**：鉴权后的 `/files/...` 图片使用 private cache 指令，避免共享代理缓存私有交付物。
- **会话清理**：后台保留循环会定期清理过期登录会话，避免 sessions 表长期只增不减。
- **OpenAPI**：默认开启 `/api/docs`（Swagger）与 `/api/openapi.json`。
- **生产级 CLI**：支持 `--workers / --log-level / --log-format / --reload / --prune-now / --print-config`。
- **容器化**：`Dockerfile` 多层缓存 + 非 root 用户 + healthcheck；`docker-compose.yml` 直接可跑。

## 启动

### 本地（开发）

```bash
./scripts/bootstrap.sh          # uv sync
./scripts/dev.sh                # 自动重载
```

默认监听 `http://127.0.0.1:8000`，OpenAPI 文档在 `http://127.0.0.1:8000/api/docs`。

### 本地（生产单机）

```bash
./scripts/serve.sh              # 多 worker、JSON 日志
```

可通过环境变量覆盖：

```bash
PICGEN_HOST=0.0.0.0 \
PICGEN_PORT=8080 \
PICGEN_WORKERS=4 \
PICGEN_LOG_FORMAT=json \
./scripts/serve.sh
```

### Docker

```bash
docker build -t minorli/picgen:0.1.17 .
docker run --rm -p 8000:8000 \
  -v picgen-data:/app/data \
  minorli/picgen:0.1.17
```

或：

```bash
docker compose up -d
```

发布镜像按 `openai-shelf` 的 Docker Hub 命名方式：

```bash
./scripts/docker-build-push.sh
```

默认会构建并推送 `minorli/picgen:0.1.17`。也可以覆盖：

```bash
IMAGE=minorli/picgen VERSION=0.1.17 PLATFORM=linux/amd64 ./scripts/docker-build-push.sh
```

镜像不会包含 `.env`、本地用户库或历史图片。容器内置 `HEALTHCHECK` 探测 `/api/health`，以非 root
用户 `picgen` 运行。`docker-compose.yml` 使用 `picgen-data` volume 保存 `/app/data`，因此注册用户、
用量统计和落盘结果会在容器重启后继续保留。

容器内默认固定三条上游 URL：

- `https://sub.tidba.com/v1/images/generations`
- `https://sub.tidba.com/v1/images/edits`
- `https://sub.tidba.com/v1/responses`

用户首次登录后只需要在页面里填写 API Key。该 Key 按登录用户保存在当前浏览器本地存储，容器重启不会清除；
如果需要全站共用一个服务端默认 Key，可在运行容器时设置 `PICGEN_DEFAULT_API_KEY`，或在持久化 volume 里创建
`/app/data/.env` 写入该变量。

## 配置

所有配置走 `Pydantic Settings`，可通过环境变量或 `.env` 文件提供。完整模板见
[`.env.example`](.env.example)。容器镜像把 `PICGEN_ENV_FILE` 指向 `/app/data/.env`，便于把运行期配置
放在持久化 volume 中；源码目录里的 `.env` 不会被打进镜像。常用项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PICGEN_DEFAULT_API_KEY` | 服务端默认上游 key（浏览器留空即用此值） | 空 |
| `PICGEN_DEFAULT_GENERATE_URL` / `PICGEN_DEFAULT_EDIT_URL` / `PICGEN_DEFAULT_RESPONSES_URL` | 上游接口 URL | Tidb 兼容代理 |
| `PICGEN_DEFAULT_MODEL` / `PICGEN_DEFAULT_RESPONSES_MODEL` | 默认模型 | `gpt-image-2` / `gpt-5.5` |
| `PICGEN_DEFAULT_SIZE` | 默认生图尺寸；当前按 6 人游主场景设置 | `1088x2240` |
| `PICGEN_UPSTREAM_TIMEOUT_SECONDS` | 单次上游请求总超时 | 1200 |
| `PICGEN_UPSTREAM_MAX_RETRIES` | 5xx / 网络瞬时错误重试次数 | 2 |
| `PICGEN_UPSTREAM_MAX_CONNECTIONS` | 连接池上限 | 64 |
| `PICGEN_RATE_LIMIT_PER_MINUTE` / `PICGEN_RATE_LIMIT_BURST` | 限流配额 | 120 / 20 |
| `PICGEN_MAX_REQUEST_BODY_BYTES` / `PICGEN_MAX_IMAGE_BYTES` | 请求与图片大小上限 | 64 MB / 32 MB |
| `PICGEN_CORS_ALLOW_ORIGINS` | 允许跨域来源（逗号分隔，空=禁用 CORS） | 空 |
| `PICGEN_PROXY_AUTH_TOKEN` | 可选 Bearer 鉴权 token；未设置则不校验 | 空 |
| `PICGEN_AUTH_ENABLED` | 启用应用内账号登录 | `true` |
| `PICGEN_ADMIN_USERNAME` / `PICGEN_ADMIN_PASSWORD` | 内置管理员账号；生产环境必须设置管理员密码 | `admin` / 空 |
| `PICGEN_BUG_REPORT_WEBHOOK_URL` | Bug 反馈通知 webhook；空则只落库 | 空 |
| `PICGEN_BUG_REPORT_WEBHOOK_KIND` | webhook 类型：`wecom` / `serverchan` / `generic` | `wecom` |
| `PICGEN_ERROR_ALERT_TELEGRAM_BOT_TOKEN` / `PICGEN_ERROR_ALERT_TELEGRAM_CHAT_ID` | 后台/上游异常 Telegram 告警；空则关闭 | 空 |
| `PICGEN_TRUST_FORWARDED_FOR` | 反向代理后启用，用 `X-Forwarded-For` 作为客户端 IP | `false` |
| `PICGEN_STORAGE_RETENTION_DAYS` | 输出按天清理（0=保留） | 0 |
| `PICGEN_LOG_LEVEL` / `PICGEN_LOG_FORMAT` | 日志等级 / `console`\|`json` | `INFO` / `console` |

随时可以查看运行时实际配置：

```bash
uv run picgen --print-config
```

输出会自动脱敏 `default_api_key`、`proxy_auth_token` 与 Bug 反馈 webhook URL。

应用内注册默认开放。启用认证时，新用户可以自助注册普通账号；系统同时内置
`PICGEN_ADMIN_USERNAME` 对应的管理员账号，`PICGEN_ADMIN_PASSWORD` 设置后会在启动时创建或更新该
管理员密码。普通用户只能查看自己的用量；管理员可以查看所有用户用量、结果满意度反馈、Bug 反馈，
并维护用户。

Bug 反馈会先写入本地认证库，再按配置尝试发送 webhook。需要微信提醒时，推荐使用企业微信机器人
webhook（`PICGEN_BUG_REPORT_WEBHOOK_KIND=wecom`）；不配置 webhook 时反馈不会丢失，管理员仍可在后台查看。
运行期通知使用 Telegram Bot：同时配置 `PICGEN_ERROR_ALERT_TELEGRAM_BOT_TOKEN` 和
`PICGEN_ERROR_ALERT_TELEGRAM_CHAT_ID` 后，上游限流/超时/异常响应、后端未预期错误和成功生图摘要都会发送到
该 chat；登录失败、参数校验、提示词为空等用户可修正错误不会刷屏。告警正文、成功摘要和返回给用户的技术
详情都会脱敏。
用户对结果选择“满意”后，可以把图片链接、提示词、模型和备注分享给站内其他用户，接收方会在左侧
“收到分享”里看到。

## 图像通道

PicGen 0.1.17 默认把所有图像操作收敛到 **OpenAI Images API + `gpt-image-2`**：

| 用户操作 | 默认接口 | 默认模型 |
| --- | --- | --- |
| 全新生成（无参考图） | `/api/generate` → `/v1/images/generations` | `gpt-image-2` |
| 参考图生成 | `/api/edit` → `/v1/images/edits`（`mode: "reference"`） | `gpt-image-2` |
| 基于结果延展 | `/api/edit` → `/v1/images/edits`（`mode: "variant"`） | `gpt-image-2` |
| 编辑现有图 | `/api/edit` → `/v1/images/edits`（`mode: "edit"`） | `gpt-image-2` |

页面"连接设置"里可一键切换为 **Responses API + `gpt-5.5`** 兜底通道，用于无法直接调
Images Edit 的兼容代理（例如 sub2api ChatGPT OAuth）。Responses 通道开启后，编辑 / 参考图 /
延展会改走 `/api/responses-image` + 流式 `image_generation` 工具，并优先把参考图上传到
同源 `/v1/files` 拿 `file_id`，必要时回退到内联 Base64。

## 接口概览

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/config` | GET | 返回前端用的配置（不含 key 明文） |
| `/api/health` | GET | 进程健康 |
| `/api/ready` | GET | 联动健康（磁盘、HTTP 客户端、版本） |
| `/api/generate` | POST | 调上游 Images 生成接口（默认通道） |
| `/api/edit` | POST | 调上游 Images 编辑接口（默认通道，含参考图 / 延展 / 编辑） |
| `/api/responses-image` | POST | 调上游 Responses + `image_generation` 工具，含 SSE 流解析（兜底通道） |
| `/files/{relative_path}` | GET | 服务本地落盘图片（防路径穿越） |
| `/api/usage` | GET | 登录用户用量；管理员返回全员汇总 |
| `/api/admin/users` | GET/POST | 管理员查看/创建用户 |
| `/api/admin/users/{user_id}` | DELETE | 管理员删除用户 |
| `/api/feedback` | POST | 登录用户提交生成结果满意度 |
| `/api/feedback/summary` | GET | 管理员查看满意度汇总 |
| `/api/bug-reports` | POST/GET | 登录用户提交 Bug；管理员查看 Bug 列表 |
| `/api/users` | GET | 登录用户获取可分享对象 |
| `/api/shares` | POST | 登录用户分享满意结果给站内用户 |
| `/api/shares/inbox` | GET | 登录用户查看收到的分享 |
| `/api/docs` | GET | Swagger UI |
| `/api/openapi.json` | GET | OpenAPI schema |

错误统一返回：

```json
{
  "error": "缺少 API Key",
  "details": null,
  "code": "bad_request",
  "request_id": "1f8e3a92b40c"
}
```

所有响应都带 `X-Request-ID` 响应头，便于和上游日志拼接。

## 上游接口契约

生成接口（默认）：

```json
{
  "model": "gpt-image-2",
  "prompt": "...",
  "size": "1088x2240",
  "quality": "auto",
  "background": "auto",
  "output_format": "png",
  "output_compression": 100,
  "moderation": "auto"
}
```

编辑接口（默认，multipart）会发送 `model / prompt / image / mask / size / quality / background /
output_format / output_compression / moderation`。本机校验后透传给 `/v1/images/edits`，避免把生成区
的隐藏字段误带入；同时把业务模式（`edit / variant / reference`）写进 sidecar 元数据。

Responses 兜底通道默认 `stream: true`，并优先把参考图上传到同源 `/v1/files` 获取 `file_id`：

```json
{
  "model": "gpt-5.5",
  "stream": true,
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "把背景改成纯白"},
        {"type": "input_image", "file_id": "file-..."}
      ]
    }
  ],
  "tools": [{"type": "image_generation", "size": "1088x2240", "quality": "auto"}]
}
```

`/v1/files` 失败时，可通过请求里的 `allow_inline_fallback` 开关决定是否退回内联 Base64。

## 落盘与用户数据

```text
data/outputs/YYYYMMDD/<username>-<mode>-<HHMMSS>-<uuid>.png
data/outputs/YYYYMMDD/<username>-<mode>-<HHMMSS>-<uuid>.json   # sidecar 元数据
```

登录用户的新图会在文件名里带安全化用户名作为前缀，旧文件名保持兼容。图片仍按日期目录分组；
sidecar JSON 保留在图片旁边，主要用于排障、人工取证和离线导出。系统事实数据以 SQLite 为准：

- `users / sessions`：账号、角色、登录与活跃时间。
- `user_preferences`：用户默认模型、尺寸、格式、通道和 LOGO/版权检查开关；不保存 API Key。
- `generation_jobs / generated_images`：每次生成请求、每张结果图、文件路径、字节数、是否请求 LOGO。
- `image_delivery_events`：图片是否通过 `/files/...` 成功返回给用户。
- `result_feedback / shared_results / bug_reports`：满意度、站内分享和 Bug 反馈。

当前下载格式跟随上游 Images API：`png / jpeg / webp`。PSD 是 Photoshop 的分层工程格式，单张 AI
生成结果本身是扁平位图，不能无损还原成可编辑图层；如需后期微调，建议下载 PNG 或透明 PNG 进入 PS
编辑。未来可另做“PSD 导出包”，但那需要服务端显式生成图层结构，而不是简单改扩展名。

落盘走临时文件 + `os.replace`，崩溃不会留下半截文件。设置 `PICGEN_STORAGE_RETENTION_DAYS>0`
后，服务运行期间会有后台任务定期（每 6 小时）清理过期日期目录；也可随时手动跑一次性清理：

```bash
uv run picgen --prune-now
```

## 安全建议

- 本地使用建议保持 `PICGEN_HOST=127.0.0.1`。
- 对外部署务必：
  - 设置 `PICGEN_PROXY_AUTH_TOKEN`，前端通过 `Authorization: Bearer <token>` 或
    `X-Proxy-Token: <token>` 调用 `/api/*`。
  - 设置强随机 `PICGEN_ADMIN_PASSWORD`，不要使用空密码启动对外服务。
  - 通过反代终止 TLS，并设置 `PICGEN_TRUST_FORWARDED_FOR=true`。
  - 按需配置 `PICGEN_CORS_ALLOW_ORIGINS`。
  - 收紧 `PICGEN_MAX_REQUEST_BODY_BYTES` / `PICGEN_MAX_IMAGE_BYTES` 以降低 DoS 面积。

`/api/health` 与 `/api/ready` 默认绕过鉴权与限流，便于探针。

## 可观测性

- 控制台日志（默认）人类可读，每行带 `request_id`，便于本地调试。
- 生产部署建议 `PICGEN_LOG_FORMAT=json`，JSON 直接喂日志聚合系统。
- 关键事件覆盖：`http_request`、`upstream_*_start/ok/http_error/timeout/retry`、
  `rate_limited`、`proxy_auth_failed`、`storage_saved`、`storage_pruned` 等。
- 敏感字段（api_key / authorization / token）自动脱敏，不会泄漏到日志或 `--print-config` 中。

## 开发与测试

```bash
./scripts/test.sh        # pytest
./scripts/check.sh       # ruff + mypy + pytest
```

测试覆盖：

- 路由：生成 / 编辑 / Responses 全链路，含错误与回退分支
- 中间件：请求 ID、安全头、限流、Body 上限、Bearer 鉴权
- httpx 客户端：5xx 重试、超时翻译、SSE 解析、远端图下载
- 存储：原子落盘、路径穿越防御、保留期清理

## 使用方式

1. `./scripts/bootstrap.sh && ./scripts/dev.sh`
2. 浏览器访问 `http://127.0.0.1:8000`
3. 在"连接设置"里填 API Key、生成接口 URL、编辑接口 URL
   - 默认通道（Images API）只需要 `生成接口 URL` 与 `编辑接口 URL`
   - 切到 Responses 兜底通道时再填 `Responses 图像接口 URL` 与 `Responses 主模型`
4. "生成图片"模式直接出图（走 `/v1/images/generations` + gpt-image-2）
5. "编辑图片"模式拖入图片或粘贴剪贴板，提交后走 `/v1/images/edits`
6. 想"换风格保持主体"切到生成区的"基于当前结果延展"，自动以最新结果为参考图调 `/v1/images/edits`
7. 兼容代理不支持 Images Edit 时，把"图像通道"切到 Responses

快捷操作：

- `Cmd/Ctrl + Enter` 提交当前模式
- `Alt + 1 / Alt + 2` 切换生成 / 编辑
- `/` 聚焦提示词输入框

## 常见上游错误

### Cloudflare Error 1010

返回中带 `Error 1010 / browser_signature_banned` 表示上游 CDN 按浏览器签名拦截。可调
`PICGEN_UPSTREAM_USER_AGENT` 与上游约定的 UA 对齐；若仍被拒绝需要联系上游放行。
PicGen 不会自动重试这类错误，以免触发更严格的封锁。

### sub2api Images API 返回 502

`/v1/images/edits` + `gpt-image-2` 在某些 OAuth 池兼容代理上可能在 ~3 分钟后 502。
在"连接设置 → 图像通道"切到 Responses，把 Responses 接口 URL 配为相同站点的
`/v1/responses`、模型用上游已验证的 `gpt-5.5`，编辑 / 参考图 / 延展会自动改走流式
`image_generation` 工具。带参考图时 PicGen 会先上传到 `/v1/files` 再用 `file_id` 调用。

## 协作与开源

- 公开协作，欢迎 fork + PR；贡献流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
- 治理规则见 [`GOVERNANCE.md`](GOVERNANCE.md)，社区行为预期见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。
- 协议：MIT，详见 [`LICENSE`](LICENSE)。
