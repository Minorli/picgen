# PicGen Console

一个面向 OpenAI 图像生成 / 编辑接口的本地工作台，**0.9.2** 起整体重写为企业级架构。它把
`/v1/images/generations`、`/v1/images/edits` 与 `/v1/responses`（含 `image_generation` 工具）
包装成统一可观测的代理，前端是一套零依赖的 Web 控制台。

适合场景：

- 本地图像 / 编辑日常实验
- 私有部署，对接兼容 OpenAI 协议的国内/自建上游
- 嵌入企业内部工具链，作为带审计、限流、健康检查的接口网关

## 界面预览

![PicGen Console 主程序界面](demo1.png)

## 0.9.2 主要特性

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
- **原子化落盘**：图片与 sidecar JSON 用临时文件 + rename 写入，崩溃不留半截文件，并可按
  `PICGEN_STORAGE_RETENTION_DAYS` 自动按天清理。
- **健康分级**：`/api/health` 仅看进程存活；`/api/ready` 联动客户端、磁盘可写性、版本号。
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
docker build -t picgen:0.9.2 .
docker run --rm -p 8000:8000 \
  -e PICGEN_DEFAULT_API_KEY=sk-... \
  -v $(pwd)/data:/app/data \
  picgen:0.9.2
```

或：

```bash
docker compose up -d
```

容器内置 `HEALTHCHECK` 探测 `/api/health`，以非 root 用户 `picgen` 运行。

## 配置

所有配置走 `Pydantic Settings`，可通过环境变量或 `.env` 文件提供。完整模板见
[`.env.example`](.env.example)。常用项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PICGEN_DEFAULT_API_KEY` | 服务端默认上游 key（浏览器留空即用此值） | 空 |
| `PICGEN_DEFAULT_GENERATE_URL` / `PICGEN_DEFAULT_EDIT_URL` / `PICGEN_DEFAULT_RESPONSES_URL` | 上游接口 URL | OpenAI 官方 |
| `PICGEN_DEFAULT_MODEL` / `PICGEN_DEFAULT_RESPONSES_MODEL` | 默认模型 | `gpt-image-2` / `gpt-5.5` |
| `PICGEN_UPSTREAM_TIMEOUT_SECONDS` | 单次上游请求总超时 | 1200 |
| `PICGEN_UPSTREAM_MAX_RETRIES` | 5xx / 网络瞬时错误重试次数 | 2 |
| `PICGEN_UPSTREAM_MAX_CONNECTIONS` | 连接池上限 | 64 |
| `PICGEN_RATE_LIMIT_PER_MINUTE` / `PICGEN_RATE_LIMIT_BURST` | 限流配额 | 120 / 20 |
| `PICGEN_MAX_REQUEST_BODY_BYTES` / `PICGEN_MAX_IMAGE_BYTES` | 请求与图片大小上限 | 64 MB / 32 MB |
| `PICGEN_CORS_ALLOW_ORIGINS` | 允许跨域来源（逗号分隔，空=禁用 CORS） | 空 |
| `PICGEN_PROXY_AUTH_TOKEN` | 可选 Bearer 鉴权 token；未设置则不校验 | 空 |
| `PICGEN_TRUST_FORWARDED_FOR` | 反向代理后启用，用 `X-Forwarded-For` 作为客户端 IP | `false` |
| `PICGEN_STORAGE_RETENTION_DAYS` | 输出按天清理（0=保留） | 0 |
| `PICGEN_LOG_LEVEL` / `PICGEN_LOG_FORMAT` | 日志等级 / `console`\|`json` | `INFO` / `console` |

随时可以查看运行时实际配置：

```bash
uv run picgen --print-config
```

输出会自动脱敏 `default_api_key` 与 `proxy_auth_token`。

## 图像通道

PicGen 0.9.2 默认把所有图像操作收敛到 **OpenAI Images API + `gpt-image-2`**：

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
  "size": "1024x1024",
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
  "tools": [{"type": "image_generation", "size": "1024x1024", "quality": "auto"}]
}
```

`/v1/files` 失败时，可通过请求里的 `allow_inline_fallback` 开关决定是否退回内联 Base64。

## 落盘位置

```text
data/outputs/YYYYMMDD/<mode>-<HHMMSS>-<uuid>.png
data/outputs/YYYYMMDD/<mode>-<HHMMSS>-<uuid>.json   # sidecar 元数据
```

落盘走临时文件 + `os.replace`，崩溃不会留下半截文件。开启 `PICGEN_STORAGE_RETENTION_DAYS`
后可使用一次性清理：

```bash
uv run picgen --prune-now
```

## 安全建议

- 本地使用建议保持 `PICGEN_HOST=127.0.0.1`。
- 对外部署务必：
  - 设置 `PICGEN_PROXY_AUTH_TOKEN`，前端通过 `Authorization: Bearer <token>` 或
    `X-Proxy-Token: <token>` 调用 `/api/*`。
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
