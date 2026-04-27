# PicGen Console

一个本地 Web 应用，用来把上游图片生成/编辑接口包装成可交互的工作台。

特点：

- 支持“生成图片”和“编辑现有图片”两种模式
- 支持把最新输出直接接到下一轮编辑，做连续修改
- 支持“全新开题”和“基于当前结果延展”两种生成逻辑，解决“换个风格但仍保持主体”的需求
- 切到编辑模式时，会优先自动带入最新生成/编辑结果作为下一轮输入
- 本地代理转发上游请求，避免浏览器跨域问题
- 提示词按原文直发上游，不在前端或代理层做改写
- 支持从很小尺寸到 4K 的预设尺寸，也支持自定义宽高
- 支持拖拽上传、粘贴图片、单张放大预览、编辑前后对比、下载结果、复制本次提示词
- 浏览器本地保存接口 URL / API Key / 最近操作记录
- 当前工作区会保存在浏览器本地，刷新页面后会恢复最近一次的图和输入状态
- 每次生成/编辑成功后，输出图片会落盘到本地目录，并生成对应的元数据 JSON
- 界面带有工作流进度、提示词快捷片段和键盘切换，减少来回找控件
- 只依赖 Python 3 标准库，开箱即可运行

## 启动

```bash
python3 app.py
```

默认启动在 `http://127.0.0.1:8000`。

也可以指定地址和端口：

```bash
python3 app.py --host 0.0.0.0 --port 8080
```

## 可选环境变量

如果你不想每次在界面里输入默认值，可以先导出这些环境变量：

```bash
export PICGEN_DEFAULT_API_KEY="sk-..."
export PICGEN_DEFAULT_GENERATE_URL="https://example.com/v1/images/generations"
export PICGEN_DEFAULT_EDIT_URL="https://sub.tidba.com/v1/images/edits"
export PICGEN_DEFAULT_MODEL="gpt-image-2"
export PICGEN_DEFAULT_SIZE="1024x1024"
python3 app.py
```

说明：

- `PICGEN_DEFAULT_API_KEY` 只作为服务端默认值，不会写入仓库
- 如果服务端已设置默认 key，页面里的 API Key 可以留空
- 生成接口 URL 和编辑接口 URL 可以分别配置，适配不同上游域名

## 落盘位置

输出图片会保存到：

```text
/home/minorli/picgen/data/outputs/YYYYMMDD/
```

示例：

```text
/home/minorli/picgen/data/outputs/20260425/generate-003243-a5152a7e.png
/home/minorli/picgen/data/outputs/20260425/generate-003243-a5152a7e.json
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
  "size": "1024x1024",
  "n": 1
}
```

编辑接口走 `multipart/form-data`，程序会把上传图片转成 multipart 转发给上游：

- `model`
- `prompt`
- `image`

如果后续上游支持 `mask`，后端代码已经预留了解析入口，前端再加一个上传控件即可。

## 使用方式

1. 启动 `python3 app.py`
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
- 前端默认只上传一张原图，不带 mask
- 如果你的生成接口域名不是示例值，需要在页面里填入真实 URL

## 协作与开源

- 仓库面向公开协作，任何人都可以 fork 后提交 Pull Request
- 贡献说明见 `CONTRIBUTING.md`
- 审核、合并和维护规则见 `GOVERNANCE.md`
- 社区行为预期见 `CODE_OF_CONDUCT.md`
- 开源许可采用 `MIT License`
