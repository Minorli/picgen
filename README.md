# PicGen Console

一个本地 Web 应用，用来把 OpenAI 图片生成/编辑接口包装成可交互的工作台。

特点：

- 支持“生成图片”和“编辑现有图片”两种模式
- 支持把最新输出直接接到下一轮编辑，做连续修改
- 支持“全新开题”和“基于当前结果延展”两种生成逻辑，解决“换个风格但仍保持主体”的需求
- 切到编辑模式时，会优先自动带入最新生成/编辑结果作为下一轮输入
- 本地代理转发上游请求，避免浏览器跨域问题
- 提示词按原文直发上游，不在前端或代理层做改写
- 对齐 OpenAI Images API 的常用参数：模型、尺寸、质量、背景、输出格式、压缩、审核严格度
- 支持从很小尺寸到 4K 的预设尺寸，也支持自定义宽高
- 支持拖拽上传、粘贴图片、可选编辑 mask、单张放大预览、编辑前后对比、下载结果、复制本次提示词
- 浏览器本地保存接口 URL / API Key / 最近操作记录
- 当前工作区会保存在浏览器本地，刷新页面后会恢复最近一次的图和输入状态
- 每次生成/编辑成功后，输出图片会落盘到本地目录，并生成对应的元数据 JSON
- 界面带有工作流进度、提示词快捷片段和键盘切换，减少来回找控件
- 使用 `uv` 管理 Python 依赖和启动命令，后端基于 FastAPI / Uvicorn

## 启动

```bash
./scripts/bootstrap.sh
./scripts/start.sh
```

默认启动在 `http://127.0.0.1:8000`。

也可以指定地址和端口：

```bash
PICGEN_HOST=0.0.0.0 PICGEN_PORT=8080 ./scripts/start.sh
```

开发模式支持自动重载：

```bash
./scripts/dev.sh
```

运行测试和检查：

```bash
./scripts/test.sh
./scripts/check.sh
```

## 可选环境变量

如果你不想每次在界面里输入默认值，可以先导出这些环境变量：

```bash
export PICGEN_DEFAULT_API_KEY="sk-..."
export PICGEN_DEFAULT_GENERATE_URL="https://api.openai.com/v1/images/generations"
export PICGEN_DEFAULT_EDIT_URL="https://api.openai.com/v1/images/edits"
export PICGEN_DEFAULT_MODEL="gpt-image-2"
export PICGEN_DEFAULT_SIZE="auto"
export PICGEN_UPSTREAM_USER_AGENT="Mozilla/5.0 ..."
./scripts/start.sh
```

说明：

- `PICGEN_DEFAULT_API_KEY` 只作为服务端默认值，不会写入仓库
- 如果服务端已设置默认 key，页面里的 API Key 可以留空
- 默认生成接口 URL 和编辑接口 URL 指向 OpenAI 官方 Images API；也可以分别配置，适配兼容 OpenAI 格式的上游域名
- `PICGEN_UPSTREAM_USER_AGENT` 可覆盖本地代理访问上游接口时使用的 User-Agent。遇到 Cloudflare `Error 1010: browser_signature_banned` 时，可以用它和上游要求的请求头保持一致

## 落盘位置

输出图片会保存到：

```text
data/outputs/YYYYMMDD/
```

示例：

```text
data/outputs/20260425/generate-003243-a5152a7e.png
data/outputs/20260425/generate-003243-a5152a7e.json
```

说明：

- 图片文件是实际输出图
- 同名 `.json` 是 sidecar 元数据，记录模式、提示词、模型、尺寸、接口地址等信息
- 页面里的下载按钮会优先指向落盘后的本地文件路由 `/files/...`

## 上游接口格式

生成接口走 JSON：

```json
{
  "model": "gpt-image-2",
  "prompt": "生成一张图，一个人站在那里没有戴护士帽",
  "size": "auto",
  "quality": "auto",
  "background": "auto",
  "output_format": "png",
  "output_compression": 100,
  "moderation": "auto"
}
```

编辑接口走 `multipart/form-data`，程序会把上传图片转成 multipart 转发给上游。为避免把生成区的隐藏状态误带到编辑请求里，编辑模式默认只发送这些字段：

- `model`
- `prompt`
- `image[]`
- `mask`（可选）

## 使用方式

1. 启动 `./scripts/bootstrap.sh && ./scripts/start.sh`
2. 打开浏览器访问 `http://127.0.0.1:8000`
3. 在左侧填好 API Key、生成接口 URL、编辑接口 URL
4. 在“生成图片”里填提示词和模型，直接出图
5. 如果只是想“换个风格 / 换灯光 / 换质感”，在生成工作台切到“基于当前结果延展”，会用上一张图做参考而不是完全重开
6. 生成完成后，如果切到“编辑图片”，程序会自动把最新结果当作编辑输入
7. 如果想改别的图，再在编辑区点击或拖拽替换图片
8. 如果想继续改刚出的那张图，也可以直接点结果区的“继续编辑当前结果”或“换风格保持主体”

快捷操作：

- `Cmd/Ctrl + Enter` 直接提交当前模式
- `Alt + 1` 切到生成模式，`Alt + 2` 切到编辑模式
- `/` 聚焦到当前模式的提示词输入框
- 编辑模式支持拖拽文件
- 编辑模式支持直接粘贴剪贴板里的图片
- 点击结果区里的任意图片可以在页面内放大预览
- 编辑完成后，可以点“前后对比预览”查看编辑前和编辑后

## 当前限制

- 历史记录列表本身只保存参数摘要，不是完整图册；但当前工作区会保留最近一次图像和页面状态
- 页面当前固定请求单张输出；如果后续要支持多图，需要补结果画廊和多图继续编辑链路
- 如果你使用的不是 OpenAI 官方接口，需要确认它兼容 OpenAI Images API 的字段名

## 常见上游错误

### Cloudflare Error 1010

如果原始响应里出现 `Error 1010: Access denied`、`browser_signature_banned` 或 `owner_action_required: true`，说明请求被上游站点的 Cloudflare 规则按浏览器签名拦截了。这通常不是提示词、API Key 或本地页面的问题，也不建议自动重试。

可先尝试用 `PICGEN_UPSTREAM_USER_AGENT` 调整本地代理访问上游时使用的 User-Agent；如果仍然被拒绝，需要联系上游站点/API 服务方放行当前访问方式，或换用他们认可的接口域名/代理通道。

## 协作与开源

- 仓库面向公开协作，任何人都可以 fork 后提交 Pull Request
- 贡献说明见 `CONTRIBUTING.md`
- 审核、合并和维护规则见 `GOVERNANCE.md`
- 社区行为预期见 `CODE_OF_CONDUCT.md`
- 开源许可采用 `MIT License`
