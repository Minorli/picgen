# PicGen 双模式 UX 实施记录

## 范围

本文件记录 `TASK-UX-IMPLEMENT.md` 对应的简洁/专业双模式改造。工作区中同时存在上一轮可靠性修复；这些修复独立于本次 UX 范围，不在此重复描述。

硬约束落实情况：

- 专业模式保留原 DOM 和工作台布局，仅增加右上模式切换按钮；1440x900 与 375x812 已和阶段 0 基线做像素差分。
- 生图、改图、路线图仍分别调用既有 `submitGenerate`、`submitEdit`、`submitAIItineraryMap`，没有新增提交 API。
- 没有新增前端框架、npm 依赖、运行时包或构建步骤。
- 新界面只使用 `--ux-*` token 和 `static/icons.svg`；用户/服务端文本通过 DOM `textContent`、`value` 或既有 `escapeHTML` 路径写入。

## 文件改动

### 设计资产

- `ARCO-STYLE-NOTES.md`
  - 固化色彩、排印、图标、渐变、圆角/阴影、间距、组件、状态、动效和明确不采用项十个维度。
  - 记录 Arco Design 与 Arco Color 的固定源码版本和具体 px/hex/ms/bezier 值。
- `static/icons.svg`
  - 收录 30 个 Arco MIT 描边图标 symbol，统一 `currentColor`、48x48 viewBox、4px stroke。
- `static/scene-poster.jpg`、`scene-itinerary.jpg`、`scene-ranking.jpg`、`scene-edit.jpg`、`scene-free.jpg`
  - 五个场景的 16:9 实际成品封面，均为 640x360 JPEG。
- `acceptance-shots/arco-style-tile.png`
  - 阶段 0 十维 style tile，1440x2700。

### 后端元数据与偏好

- `src/picgen/recipes.py`
  - 新增冻结数据结构 `SceneOption`、`SceneField`、`SceneCard`。
  - 保留既有 recipe 字段，按需追加 `scene_card`。
  - 提供竖版海报、行程路线图、清单/榜单、改一张图、自由创作五个场景。
- `src/picgen/schemas.py`
  - `UserPreferencesRequest.ui_mode` 仅允许 `simple` / `professional`；追加首单清单完成偏好请求。
- `src/picgen/auth.py`
  - `user_preferences` 增加可空且带 CHECK 的 `ui_mode`、`simple_checklist_completed` 和旧库迁移。
  - 原 `PUT /api/preferences` 保持全量替换语义；缺少 `ui_mode` 或新增清单字段时保留现值。
  - 未分配组织用户使用用户级独立群空间，重启不会被旧迁移自动加入默认部门。
  - schema v15 回填发送者自有的合法历史分享并删除无效记录；文件授权只认规范化图片关联。
- `src/picgen/routes.py`
  - 增加 `/api/preferences/ui-mode`、`/api/preferences/simple-checklist` 两个窄 PATCH，避免模式切换覆盖其它偏好。
  - `/api/recipes` 响应保持向后兼容，仅追加场景元数据。
  - 自助注册默认关闭；显式开放时新用户保持未分配，个人资料不能修改组织。
  - `/files/outputs/*` 增加 owner、显式分享、当前群资产或管理员对象级授权。

### 前端

- `static/index.html`
  - 顶栏增加模式切换按钮。
  - 增加三步流程、五场景容器、动态表单、最近作品、Empty、Skeleton、首单清单。
  - 简洁结果区增加分享和“更多”菜单；既有专业动作节点保留。
- `static/app.js`
  - 新增独立 `uiMode`，不复用 `activeMode` 或 `promptMode`。
  - 新用户默认简洁、有历史用户默认专业；登录用户存服务端偏好，匿名模式存 localStorage。
  - 按 recipes 元数据动态创建字段、校验必填项、组装最终提示词并进入既有确认弹窗。
  - 简洁草稿和当前视图写入既有 IndexedDB workspace；返回场景页、模式往返、刷新均不丢草稿。
  - 简洁场景隔离隐藏参考图：自由创作/榜单不会误带海报参考图；自由创作保持精确提示词，不追加 recipe suffix。
  - 行程模板标题/日期行不会进入站点解析。
  - 结果动作收敛为下载、改图、同款、分享、更多；改图进入可见的简洁表单，同款走既有重跑流程。
  - 等待显示近期成功任务耗时中位数；无数据时显示 1-3 分钟，超过 5 分钟显示排队提示。
  - 匿名模式把本次结果加入最近作品，不依赖登录态 gallery API。
  - 用户上下文代次阻止旧账号的请求、检查和 IndexedDB 回调写入新账号；模式偏好按调用顺序串行提交。
  - 账号切换会取消旧偏好请求、重置队列和首单清单延迟回调，并同步清空作品库与分享 DOM。
  - 简洁改图从上传源图读取宽高并提交原画幅，不再固定为正方形；海报参考图粘贴留在当前场景。
  - 五类图片读取按通道维护最新序列、用户代次和 busy 所有者；后选文件获胜，清空、模式切换、部门资产和最新结果会使旧读取失效。
  - 首单清单同时写用户作用域 localStorage 和服务端偏好，跨浏览器也不会重新出现。
- `static/styles.css`
  - 顶部增加完整 `--ux-*` token 层。
  - 新增简洁模式作用域样式、六态控件、场景卡、Steps、Alert、Message、Skeleton、Empty、结果菜单和首单清单。
  - 375px 无横向滚动；821-1040px 登录态顶栏改为两行工具布局，避免模式按钮与品牌重叠。
  - 简洁结果预览固定 480px，竖图使用 contain，不再随图片原始比例撑高页面。

### 测试

- `tests/test_api.py`
  - 校验五场景顺序、字段、模板、封面、尺寸和 submit 元数据。
- `tests/test_regressions.py`
  - 校验 `ui_mode` 缺失保留、非法值拒绝、旧表迁移、Logo 文件名唯一性和元数据合并。
- `tests/test_release_blockers.py`
  - 校验注册安全默认、组织隔离、文件对象授权、历史分享迁移、偏好 PUT/PATCH、清单持久化及密码重置 token 脱敏。
- `tests/test_static_assets.py`
  - 校验模式 DOM、既有提交路径、图标/封面资产、token 纯度、用户上下文隔离、文件读取竞态和行程伪站点回归。
- Playwright 验收脚本（临时目录，不进仓库）
  - 覆盖 1440x900、375x812、821/900/960/1040。
  - 覆盖确认弹窗、动态列表/chips、草稿往返、跨场景图片隔离、等待/结果动作、匿名作品、偏好记忆和跨用户迟到响应。
  - 最终发布回归额外验证注册关闭门控、组织只读、海报场景粘贴、874x1800 编辑请求、五通道上传竞态、loading 可达性和登出清屏。

## Token 清单

新增 token 均位于 `:root`，按用途分组：

- 品牌色：`--ux-primary-1` 至 `--ux-primary-10`、`--ux-primary-gradient-end`
- 中性色：`--ux-neutral-1` 至 `--ux-neutral-10`
- 语义映射：`--ux-text-*`、`--ux-fill-*`、`--ux-border-*`、`--ux-bg-*`
- 功能色：`--ux-success-*`、`--ux-warning-*`、`--ux-danger-*`、`--ux-link-*`
- 排印：`--ux-font-family`、`--ux-font-mono`、`--ux-font-size-*`、`--ux-line-height-*`、`--ux-font-weight-*`
- 圆角/描边：`--ux-radius-*`、`--ux-border-width`、`--ux-border-style`
- 间距：`--ux-space-0` 至 `--ux-space-30`
- 控件/图标：`--ux-control-*`、`--ux-button-padding-x`、`--ux-card-padding`、`--ux-icon-size-*`
- 阴影/焦点：`--ux-shadow-*`、`--ux-focus-ring-*`、`--ux-badge-edge`
- 动效：`--ux-duration-*`、`--ux-ease-*`、`--ux-transition-*`
- 渐变：`--ux-gradient-primary`、`--ux-gradient-progress`、`--ux-gradient-cover-protection`、`--ux-gradient-skeleton`、`--ux-gradient-page-wash`
- 布局：`--ux-simple-panel-width`、`--ux-simple-content-width`、`--ux-result-min-height`、`--ux-result-preview-max-height`、`--ux-textarea-min-height`、`--ux-dropzone-min-height`、`--ux-menu-width`、`--ux-checklist-width`

## 场景数据结构

```json
{
  "scene_card": {
    "order": 1,
    "title": "竖版海报",
    "cover": "scene-poster.jpg",
    "subtitle": "朋友圈/群发宣传图",
    "fields": [
      {
        "name": "title",
        "label": "主标题",
        "kind": "text",
        "required": true,
        "placeholder": "例如：金秋北疆·喀纳斯"
      }
    ],
    "template": "主标题：{{title}}",
    "default_size": "1088x2240",
    "submit": {
      "kind": "generate",
      "label": "生成海报"
    }
  }
}
```

字段 `kind` 取值为 `text`、`textarea`、`list`、`chips`、`image`、`size`；`placeholder`、`max_items`、`options` 仅在适用时下发。`submit.kind` 取值为 `generate`、`edit`、`itinerary`，前端只把数据投影到既有提交函数。
