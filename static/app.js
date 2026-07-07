const STORAGE_KEY = "picgen-console-settings-v2"
const LEGACY_STORAGE_KEY = "picgen-console-settings-v1"
const HISTORY_KEY = "picgen-console-history-v1"
const TEAM_CHAT_RECENT_DM_KEY = "picgen-team-chat-recent-dms-v1"
const COMPANY_LOGO_URL = "6renyou.png"
const COMPANY_LOGO_NAME = "6renyou.png"
const COMPANY_LOGO_MIME = "image/png"
const COMPANY_LOGO_WIDTH_RATIO = 0.16
const COMPANY_LOGO_MIN_WIDTH = 86
const COMPANY_LOGO_MAX_WIDTH = 220
const COMPANY_LOGO_MARGIN_RATIO = 0.04
const COMPANY_LOGO_MIN_MARGIN = 16
const COMPANY_LOGO_MAX_MARGIN = 42
const COMPANY_LOGO_LAYOUT_PROMPT = [
  "LOGO 布局要求：请在画面左上角为 6 人游 LOGO 预留自然干净的留白，避免人物、文字、建筑边缘、产品主体或高对比元素与 LOGO 位置发生重合。",
  "最终 LOGO 将使用官方透明 PNG 原样贴入，图标、字体、颜色和比例均不得改动。",
  "LOGO 位置附近保留自然干净背景，背景尽量简单；不要绘制 LOGO 占位框、边框、描边、白色底板、贴纸底座或任何临时标识。",
].join("\n")
const EDIT_PRESERVE_PROMPT = [
  "编辑保护要求：只修改用户明确要求修改的部分。",
  "用户没有明确要求删除或替换的元素必须保留，包括主体构图、路线、地点、日期标签、距离标注、交通工具图标、人物/景物、文字层级、色彩气质和已有品牌安全区。",
  "如果输入图包含或预留 6 人游 LOGO，不能重绘、改造、遮挡或删除 LOGO；最终 LOGO 会由程序使用官方透明 PNG 原样贴入。",
].join("\n")
const TEXT_RENDERING_FIDELITY_PROMPT = [
  "文字渲染分层要求：画面中出现的标题、地名、日期、序号、说明正文、贴士和所有可读文字，必须逐字使用用户提供的文字。",
  "不得改写、翻译、替换、增删或自行纠错用户文字；不得把相近字、同音字、繁简字、英文或拼音替换进画面。",
  "主标题/核心标题：在逐字准确和高识别度前提下，允许使用高识别度商业美术字、手写标题、立体描边、金属或笔刷字效、适度阴影和版式装饰；标题要有视觉记忆点，不能被压成普通正文印刷字。",
  "正文/地名/日期/序号/说明/贴士：继续严格清晰逐字，优先保证可读性、层级和排版秩序；不要为了装饰牺牲正文准确性。",
].join("\n")
const VISIBLE_TEXT_CONTRACT_HEADING = "可见文字合同（必须逐字验收）："
const TEXT_CONTRACT_MAX_ITEMS = 48
const TEXT_CONTRACT_LABEL_RE = /(?:主标题|副标题|标题|地区|代表名菜|日期|天数|文案|口号|小标题|行程|目的地|服务|亮点)\s*[:：]\s*([^\n]+)/giu
const TEXT_REPLACEMENT_RE = /把\s*[“"']?([^“”"'，,；;\n]{1,80})[”"']?\s*(?:改成|替换成|换成|改为|变成)\s*[“"']?([^“”"'，,；;\n]{1,120})[”"']?/giu
const TEAM_CHAT_MAX_MESSAGE_LENGTH = 4000
const TEAM_CHAT_FAST_POLL_LIMIT = 8
const TEAM_CHAT_MAX_RECENT_DMS = 8
const MAX_HISTORY_ITEMS = 12
const WORKSPACE_DB_NAME = "picgen-console-workspace"
const WORKSPACE_STORE_NAME = "snapshots"
const WORKSPACE_KEY = "current-workspace"
const WORKSPACE_VERSION = 1
const REQUEST_TIMEOUT_MS = 20 * 60 * 1000 + 30 * 1000
const DEPRECATED_RESPONSES_MODELS = new Set(["gpt-5.4"])
const DEPRECATED_RESPONSES_URLS = new Set(["https://api.openai.com/v1/responses"])
const STYLE_TRANSFER_SAMPLE_COUNT = 3
const CLIENT_IMAGE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
const UPSTREAM_RETRY_HINT = "等待上游响应中。后台如遇临时错误会自动重试；后台如遇临时 502/503/504 会自动重试。第几次重试以最终错误详情或服务端日志为准。"
const IMAGES_API_EXACT_SIZES = new Set(["auto", "1024x1024", "1024x1536", "1536x1024"])
const DEFAULT_ITINERARY_TITLE = "定制旅行路线图"
const DEFAULT_ITINERARY_SUBTITLE = ""
const SANITIZED_ITINERARY_EXAMPLE_TITLE = "全球旅行路线图"
const SANITIZED_ITINERARY_EXAMPLE_SUBTITLE = "示例日期范围"
const AI_ITINERARY_EXAMPLE = [
  "D1：抵达城市 A；交通：飞机；入住：酒店 A；当天重点：抵达、休整、城市初印象。",
  "D2：城市 A → 景区 B；交通：包车/自驾；入住：酒店 B；当天重点：自然风光、观景点、轻徒步。",
  "D3：景区 B → 小镇 C；交通：地面转场；入住：精品民宿 C；当天重点：小镇街区、当地餐食、人文体验。",
  "D4：小镇 C → 城市 D；交通：火车/包车；入住：酒店 D；当天重点：博物馆、历史街区、夜景。",
  "D5：城市 D 周边活动；交通：步行/短途车；入住：酒店 D；当天重点：自由活动、亲子或小团体验。",
  "D6：城市 D → 机场/车站；交通：飞机/火车；当天重点：返程或下一段旅程。",
].join("\n")
const DETAILED_ITINERARY_TEMPLATE = [
  "行程基础信息：",
  "- 目的地/主题：请替换为本次路线目的地（例如：伊比利亚半岛亲子游 / 北欧峡湾自驾 / 日本关西赏枫）",
  "- 出行日期：请替换为本次真实日期范围（例如：5/12 - 5/24）",
  "- 客户偏好：请替换为真实偏好（例如：高端定制、小众自然风光、亲子友好、酒店质感、人文街区）",
  "- 地图标题建议：请替换为客户可见标题（例如：伊比利亚半岛旅行地图 / 北欧峡湾自驾路线）",
  "",
  "逐日行程：",
  "- 日期：城市/地点 A → 城市/地点 B；交通：请写明包车/自驾/火车/飞机/步行；入住：酒店名；当天重点：请写明 1-3 个核心活动。",
  "- 日期：城市/地点 B → 景区/街区 C；交通：请写明；入住：酒店名；当天重点：请写明。",
  "- 日期：景区/街区 C → 城市/地点 D；交通：请写明；入住：酒店名；当天重点：请写明。",
  "- 按真实行程继续补齐每一天；不要保留示例地名，不要省略中间日期。",
  "",
  "程序坐标（用于准确落点，至少填写两个）：",
  "- @坐标: D1,城市/地点 A,纬度,经度,交通方式",
  "- @坐标: D2,城市/地点 B,纬度,经度,交通方式",
  "- @坐标: D3,城市/地点 C,纬度,经度,交通方式",
  "",
  "地点与地理校验（请按本次目的地改写）：",
  "- 必须保持真实相对位置：请列出本次路线中容易画错的城市、景区、海岸、山脉、湖泊、岛屿或边境关系。",
  "- 如果路线跨国家/大区，请明确哪些是飞行或长距离转场，哪些是地面路线；不要把远距离城市画成相邻小镇。",
  "- 每两个连续地点之间都要有路线连接，并标注合理的距离或转场方式；不确定精确距离时写“约 xx km”或“飞行转场”。",
  "- 每段路线中间放一个很小的交通工具图标：包车/自驾用小车，火车用列车，飞行转场用飞机，活动/步行用脚印或点线。",
  "",
  "画面要求：",
  "- 水彩漫画路线图，不要像手机导航截图或低质 PPT。",
  "- 日期必须逐日出现，不能漏任何一天；地点、交通、酒店和核心活动必须按用户原文保留。",
  "- 左上角预留自然干净的 6 人游 LOGO 留白；不要让 AI 绘制 LOGO，不要画 LOGO 占位框，不要画边框，不要画白底底板，程序会用官方透明 PNG 原样贴入。",
  "- 风格：水彩漫画路线图，使用柔和水彩底色、红色粗路线、圆点站位、地标小插画、手写感标题和清晰日期标签。",
  "- 漫画风格不能牺牲地理真实性；日期、距离、交通方式、酒店和核心景区不能省略，信息丰富但不拥挤。",
].join("\n")

const ITINERARY_GEOGRAPHY_GUARD = [
  "地图准确性保护：路线图必须优先服从真实地图坐标、用户提供的地图参考和明确的地理关系，不能只按画面美观重排地点。",
  "- 如果用户提供了经纬度、导航距离、地点清单里的东西南北关系或转场方式，以这些资料为硬约束。",
  "- 不要凭想象补地图；不确定地点准确落位时，不要把它画到看起来顺眼的位置，改用编号点、局部放大框、侧边行程表或“待核对位置”备注。",
  "- 使用测绘式真实地图框架：默认北上南下、西左东右，城市、景区、湖泊、山脉、海岸、岛屿和边境的相对方位不能为了构图改变。",
  "- 跨大区或跨国家转场必须使用总览图、局部放大框或飞行连接；不要把远距离城市压缩成相邻景点，也不要把南北或东西关系画反。",
  "- 地点名相近或景区层级复杂时，先按用户给出的地理校验逐项落位，再画路线；缺少把握时保守表达为示意路线，不得伪装成精确地图。",
].join("\n")

const SIZE_PRESETS = [
  "auto",
  "128x128",
  "256x256",
  "512x512",
  "768x768",
  "1024x1024",
  "1536x1024",
  "1024x1536",
  "1088x2240",
  "2048x2048",
  "3840x2160",
  "2160x3840",
]

const state = {
  activeMode: "generate",
  generateIntent: "fresh",
  serverConfig: null,
  currentUser: null,
  authMode: "login",
  passwordResetToken: "",
  appReady: false,
  lastReadyUserId: null,
  editImage: null,
  editMaskImage: null,
  generateReferenceImage: null,
  styleReferenceImage: null,
  materialReferenceImage: null,
  displayedSourceImage: null,
  history: [],
  lastResultPrompt: "",
  lastResultImage: null,
  lastResultModel: "",
  lastResultMode: null,
  currentComparisonSource: null,
  resultPreview: null,
  resultGenerationSeq: 0,
  resultCandidates: [],
  selectedCandidateIndex: 0,
  progressTimer: null,
  progressStartedAt: 0,
  progressPhase: "idle",
  progressLabel: "",
  progressExpectedCount: 1,
  progressEstimatedSecondsPerImage: 210,
  activeRequestController: null,
  activeRequestCancelled: false,
  pendingResultSnapshot: null,
  preview: {
    mode: "single",
    target: "result",
  },
  previewZoom: {
    scale: 1,
    x: 0,
    y: 0,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    startX: 0,
    startY: 0,
  },
  copyrightRisk: {
    status: "等待检查",
    text: "生成完成后自动检查。",
    hidden: true,
  },
  copyrightRiskRequestSeq: 0,
  textFidelity: {
    status: "等待检查",
    text: "生成完成后自动检查用户文案。",
    hidden: true,
  },
  textFidelityRequestSeq: 0,
  rawResponsePreview: null,
  debugLines: [],
  persistTimer: null,
  toastTimer: null,
  persistenceReady: false,
  isBusy: false,
  companyLogoCanvas: null,
  lastFeedbackPayload: null,
  lastFeedbackRating: null,
  lastRegenerationRequest: null,
  shareRecipients: [],
  shareSelectedRecipientIds: new Set(),
  sharedResults: [],
  galleryItems: [],
  gallerySearch: "",
  galleryFavoriteOnly: false,
  gallerySearchTimer: null,
  generationJobs: [],
  currentGalleryMeta: {
    generatedImageId: null,
    isFavorite: false,
    tags: [],
  },
  userPreferences: null,
  teamChatMembers: [],
  teamChatHumanMembers: [],
  teamChatBot: null,
  teamChatRecentDms: [],
  teamChatMessages: [],
  teamChatRoom: {
    type: "team",
    recipientUserId: null,
    title: "部门群",
    meta: "部门群",
  },
  teamChatGroup: {
    company: "6renyou",
    department: "PD & OPS",
    roomKey: "",
    title: "PD & OPS",
    subtitle: "6renyou · 部门群",
    memberCount: 0,
  },
  teamChatGroupContextExpanded: false,
  teamChatLastMessageId: 0,
  teamChatLocalMessageSeq: 0,
  teamChatUnreadTotal: 0,
  teamChatPollTimer: null,
  teamChatFastPollRemaining: 0,
  teamChatUnreadTimer: null,
  teamChatQuotedMessage: null,
  teamChatOpenMenuId: null,
  teamChatSending: false,
  adminOrgUnits: [],
  orgUnits: [],
  promptMode: "free",
  promptRecipes: [],
  selectedRecipeId: "",
}

const refs = {
  authOverlay: document.querySelector("#authOverlay"),
  authForm: document.querySelector("#authForm"),
  authTitle: document.querySelector("#authTitle"),
  authSubtitle: document.querySelector("#authSubtitle"),
  authUsernameInput: document.querySelector("#authUsernameInput"),
  authPasswordInput: document.querySelector("#authPasswordInput"),
  authOrgFields: document.querySelector("#authOrgFields"),
  authCompanyInput: document.querySelector("#authCompanyInput"),
  authDepartmentInput: document.querySelector("#authDepartmentInput"),
  authError: document.querySelector("#authError"),
  loginAuthButton: document.querySelector("#loginAuthButton"),
  registerAuthButton: document.querySelector("#registerAuthButton"),
  forgotPasswordButton: document.querySelector("#forgotPasswordButton"),
  passwordResetRequestForm: document.querySelector("#passwordResetRequestForm"),
  passwordResetUsernameInput: document.querySelector("#passwordResetUsernameInput"),
  passwordResetRequestStatus: document.querySelector("#passwordResetRequestStatus"),
  submitPasswordResetRequestButton: document.querySelector("#submitPasswordResetRequestButton"),
  cancelPasswordResetRequestButton: document.querySelector("#cancelPasswordResetRequestButton"),
  passwordResetConfirmForm: document.querySelector("#passwordResetConfirmForm"),
  passwordResetNewPasswordInput: document.querySelector("#passwordResetNewPasswordInput"),
  passwordResetConfirmPasswordInput: document.querySelector("#passwordResetConfirmPasswordInput"),
  passwordResetConfirmStatus: document.querySelector("#passwordResetConfirmStatus"),
  submitPasswordResetConfirmButton: document.querySelector("#submitPasswordResetConfirmButton"),
  cancelPasswordResetConfirmButton: document.querySelector("#cancelPasswordResetConfirmButton"),
  bugReportButton: document.querySelector("#bugReportButton"),
  changePasswordButton: document.querySelector("#changePasswordButton"),
  teamChatButton: document.querySelector("#teamChatButton"),
  teamChatUnreadBadge: document.querySelector("#teamChatUnreadBadge"),
  logoutButton: document.querySelector("#logoutButton"),
  openProfileButton: document.querySelector("#openProfileButton"),
  currentUsername: document.querySelector("#currentUsername"),
  userAvatar: document.querySelector("#userAvatar"),
  userImageStats: document.querySelector("#userImageStats"),
  userUsageSummary: document.querySelector("#userUsageSummary"),
  adminPanel: document.querySelector("#adminPanel"),
  adminPasswordResetPanel: document.querySelector("#adminPasswordResetPanel"),
  passwordResetRequestsList: document.querySelector("#passwordResetRequestsList"),
  refreshPasswordResetRequestsButton: document.querySelector("#refreshPasswordResetRequestsButton"),
  adminCreateUserForm: document.querySelector("#adminCreateUserForm"),
  adminNewUsernameInput: document.querySelector("#adminNewUsernameInput"),
  adminNewPasswordInput: document.querySelector("#adminNewPasswordInput"),
  adminNewRoleSelect: document.querySelector("#adminNewRoleSelect"),
  adminCreateUserButton: document.querySelector("#adminCreateUserButton"),
  adminUserError: document.querySelector("#adminUserError"),
  adminUsersList: document.querySelector("#adminUsersList"),
  refreshAdminUsersButton: document.querySelector("#refreshAdminUsersButton"),
  adminOrgPanel: document.querySelector("#adminOrgPanel"),
  adminOrgCreateForm: document.querySelector("#adminOrgCreateForm"),
  adminOrgCompanyInput: document.querySelector("#adminOrgCompanyInput"),
  adminOrgDepartmentInput: document.querySelector("#adminOrgDepartmentInput"),
  adminUserOrgForm: document.querySelector("#adminUserOrgForm"),
  adminOrgUserIdInput: document.querySelector("#adminOrgUserIdInput"),
  adminOrgUnitSelect: document.querySelector("#adminOrgUnitSelect"),
  adminOrgReasonInput: document.querySelector("#adminOrgReasonInput"),
  adminGroupAnnouncementForm: document.querySelector("#adminGroupAnnouncementForm"),
  adminAnnouncementOrgSelect: document.querySelector("#adminAnnouncementOrgSelect"),
  adminAnnouncementContentInput: document.querySelector("#adminAnnouncementContentInput"),
  adminOrgStatus: document.querySelector("#adminOrgStatus"),
  adminOrgStatsList: document.querySelector("#adminOrgStatsList"),
  adminOrgUnitsList: document.querySelector("#adminOrgUnitsList"),
  adminOrgAuditList: document.querySelector("#adminOrgAuditList"),
  refreshAdminOrgButton: document.querySelector("#refreshAdminOrgButton"),
  adminFeedbackSummary: document.querySelector("#adminFeedbackSummary"),
  adminBugReportsPanel: document.querySelector("#adminBugReportsPanel"),
  refreshFeedbackSummaryButton: document.querySelector("#refreshFeedbackSummaryButton"),
  refreshBugReportsButton: document.querySelector("#refreshBugReportsButton"),
  feedbackGoodCount: document.querySelector("#feedbackGoodCount"),
  feedbackOkCount: document.querySelector("#feedbackOkCount"),
  feedbackBadCount: document.querySelector("#feedbackBadCount"),
  feedbackSummaryRate: document.querySelector("#feedbackSummaryRate"),
  feedbackRecentList: document.querySelector("#feedbackRecentList"),
  bugReportsList: document.querySelector("#bugReportsList"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  generateUrlInput: document.querySelector("#generateUrlInput"),
  editUrlInput: document.querySelector("#editUrlInput"),
  responsesUrlInput: document.querySelector("#responsesUrlInput"),
  responsesModelInput: document.querySelector("#responsesModelInput"),
  imageTransportInputs: Array.from(document.querySelectorAll('input[name="imageTransport"]')),
  imageTransportHint: document.querySelector("#imageTransportHint"),
  settingsHint: document.querySelector("#settingsHint"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  clearHistoryButton: document.querySelector("#clearHistoryButton"),
  newTaskButton: document.querySelector("#newTaskButton"),
  navModeButtons: Array.from(document.querySelectorAll(".nav-link[data-mode]")),
  historyList: document.querySelector("#historyList"),
  historyEmpty: document.querySelector("#historyEmpty"),
  sharedResultsList: document.querySelector("#sharedResultsList"),
  sharedResultsEmpty: document.querySelector("#sharedResultsEmpty"),
  refreshSharedResultsButton: document.querySelector("#refreshSharedResultsButton"),
  railToggleButtons: Array.from(document.querySelectorAll("[data-rail-toggle]")),
  teamInspirationFeedButton: document.querySelector("#teamInspirationFeedButton"),
  teamInspirationFeed: document.querySelector("#teamInspirationFeed"),
  galleryList: document.querySelector("#galleryList"),
  galleryEmpty: document.querySelector("#galleryEmpty"),
  refreshGalleryButton: document.querySelector("#refreshGalleryButton"),
  refreshJobsButton: document.querySelector("#refreshJobsButton"),
  jobCenterList: document.querySelector("#jobCenterList"),
  jobCenterEmpty: document.querySelector("#jobCenterEmpty"),
  gallerySearchInput: document.querySelector("#gallerySearchInput"),
  galleryFavoriteOnlyInput: document.querySelector("#galleryFavoriteOnlyInput"),
  clearGalleryFiltersButton: document.querySelector("#clearGalleryFiltersButton"),
  requestStatus: document.querySelector("#requestStatus"),
  requestBadge: document.querySelector("#requestBadge"),
  generateTab: document.querySelector("#generateTab"),
  editTab: document.querySelector("#editTab"),
  itineraryTab: document.querySelector("#itineraryTab"),
  generatePanel: document.querySelector("#generatePanel"),
  editPanel: document.querySelector("#editPanel"),
  itineraryPanel: document.querySelector("#itineraryPanel"),
  itineraryTitleInput: document.querySelector("#itineraryTitleInput"),
  itinerarySubtitleInput: document.querySelector("#itinerarySubtitleInput"),
  itinerarySizeSelect: document.querySelector("#itinerarySizeSelect"),
  itineraryThemeSelect: document.querySelector("#itineraryThemeSelect"),
  itineraryDescriptionInput: document.querySelector("#itineraryDescriptionInput"),
  itineraryLogoEnabled: document.querySelector("#itineraryLogoEnabled"),
  renderItineraryMapButton: document.querySelector("#renderItineraryMapButton"),
  clearItineraryMapButton: document.querySelector("#clearItineraryMapButton"),
  copyItineraryTemplateButton: document.querySelector("#copyItineraryTemplateButton"),
  applyItineraryTemplateButton: document.querySelector("#applyItineraryTemplateButton"),
  freshGenerateMode: document.querySelector("#freshGenerateMode"),
  variantGenerateMode: document.querySelector("#variantGenerateMode"),
  generateIntentHint: document.querySelector("#generateIntentHint"),
  variantSourceCard: document.querySelector("#variantSourceCard"),
  variantSourceName: document.querySelector("#variantSourceName"),
  variantSourceHint: document.querySelector("#variantSourceHint"),
  variantSuggestion: document.querySelector("#variantSuggestion"),
  styleReferenceDropzone: document.querySelector("#styleReferenceDropzone"),
  styleReferenceInput: document.querySelector("#styleReferenceInput"),
  styleReferenceTitle: document.querySelector("#styleReferenceTitle"),
  styleReferenceMeta: document.querySelector("#styleReferenceMeta"),
  materialReferenceDropzone: document.querySelector("#materialReferenceDropzone"),
  materialReferenceInput: document.querySelector("#materialReferenceInput"),
  materialReferenceTitle: document.querySelector("#materialReferenceTitle"),
  materialReferenceMeta: document.querySelector("#materialReferenceMeta"),
  generateReferenceMeta: document.querySelector("#generateReferenceMeta"),
  clearGenerateReferenceButton: document.querySelector("#clearGenerateReferenceButton"),
  generatePromptInput: document.querySelector("#generatePromptInput"),
  generatePromptCount: document.querySelector("#generatePromptCount"),
  promptModeInputs: Array.from(document.querySelectorAll('input[name="promptMode"]')),
  recipeAssistPanel: document.querySelector("#recipeAssistPanel"),
  promptRecipeSelect: document.querySelector("#promptRecipeSelect"),
  promptRecipeCards: document.querySelector("#promptRecipeCards"),
  applyPromptRecipeButton: document.querySelector("#applyPromptRecipeButton"),
  promptRecipeSummary: document.querySelector("#promptRecipeSummary"),
  effectivePromptPreview: document.querySelector("#effectivePromptPreview"),
  generateModelInput: document.querySelector("#generateModelInput"),
  generateSizePreset: document.querySelector("#generateSizePreset"),
  generateWidthInput: document.querySelector("#generateWidthInput"),
  generateHeightInput: document.querySelector("#generateHeightInput"),
  qualitySelect: document.querySelector("#qualitySelect"),
  backgroundSelect: document.querySelector("#backgroundSelect"),
  outputFormatSelect: document.querySelector("#outputFormatSelect"),
  outputCompressionInput: document.querySelector("#outputCompressionInput"),
  moderationSelect: document.querySelector("#moderationSelect"),
  generateSampleCountInput: document.querySelector("#generateSampleCountInput"),
  creativeBriefPanel: document.querySelector("#creativeBriefPanel"),
  creativeBriefDestinationInput: document.querySelector("#creativeBriefDestinationInput"),
  creativeBriefAudienceInput: document.querySelector("#creativeBriefAudienceInput"),
  creativeBriefChannelInput: document.querySelector("#creativeBriefChannelInput"),
  creativeBriefMoodInput: document.querySelector("#creativeBriefMoodInput"),
  creativeBriefMustHaveInput: document.querySelector("#creativeBriefMustHaveInput"),
  creativeBriefAvoidInput: document.querySelector("#creativeBriefAvoidInput"),
  applyCreativeBriefButton: document.querySelector("#applyCreativeBriefButton"),
  askBotCreativeBriefButton: document.querySelector("#askBotCreativeBriefButton"),
  visualSizeInputs: Array.from(document.querySelectorAll('input[name="visualSize"]')),
  clearGenerateButton: document.querySelector("#clearGenerateButton"),
  generateButton: document.querySelector("#generateButton"),
  cancelRequestButton: document.querySelector("#cancelRequestButton"),
  imageDropzone: document.querySelector("#imageDropzone"),
  imageDropzoneTitle: document.querySelector("#imageDropzoneTitle"),
  imageDropzoneSubtitle: document.querySelector("#imageDropzoneSubtitle"),
  editImageInput: document.querySelector("#editImageInput"),
  editImageMeta: document.querySelector("#editImageMeta"),
  maskDropzone: document.querySelector("#maskDropzone"),
  editMaskInput: document.querySelector("#editMaskInput"),
  maskDropzoneTitle: document.querySelector("#maskDropzoneTitle"),
  maskDropzoneSubtitle: document.querySelector("#maskDropzoneSubtitle"),
  editMaskMeta: document.querySelector("#editMaskMeta"),
  clearEditMaskButton: document.querySelector("#clearEditMaskButton"),
  editPromptInput: document.querySelector("#editPromptInput"),
  editPromptCount: document.querySelector("#editPromptCount"),
  editModelInput: document.querySelector("#editModelInput"),
  clearEditButton: document.querySelector("#clearEditButton"),
  editButton: document.querySelector("#editButton"),
  comparisonGrid: document.querySelector("#comparisonGrid"),
  sourcePreviewCard: document.querySelector("#sourcePreviewCard"),
  sourcePreviewLabel: document.querySelector("#sourcePreviewLabel"),
  sourcePreviewTrigger: document.querySelector("#sourcePreviewTrigger"),
  sourcePreviewImage: document.querySelector("#sourcePreviewImage"),
  sourcePreviewEmpty: document.querySelector("#sourcePreviewEmpty"),
  resultPreviewCard: document.querySelector("#resultPreviewCard"),
  resultPreviewLabel: document.querySelector("#resultPreviewLabel"),
  resultPreviewTrigger: document.querySelector("#resultPreviewTrigger"),
  resultImage: document.querySelector("#resultImage"),
  resultPreviewEmpty: document.querySelector("#resultPreviewEmpty"),
  resultHoverActions: document.querySelector("#resultHoverActions"),
  resultActions: document.querySelector("#resultActions"),
  resultCandidateStrip: document.querySelector("#resultCandidateStrip"),
  generationOverlay: document.querySelector("#generationOverlay"),
  generationOrbit: document.querySelector(".generation-orbit"),
  generationOverlayTitle: document.querySelector("#generationOverlayTitle"),
  generationOverlaySubtitle: document.querySelector("#generationOverlaySubtitle"),
  generationOverlaySteps: document.querySelector("#generationOverlaySteps"),
  resultPrompt: document.querySelector("#resultPrompt"),
  resultMeta: document.querySelector("#resultMeta"),
  resultTiming: document.querySelector("#resultTiming"),
  progressInspectorItem: document.querySelector("#progressInspectorItem"),
  progressStageLabel: document.querySelector("#progressStageLabel"),
  progressElapsed: document.querySelector("#progressElapsed"),
  requestProgressFill: document.querySelector("#requestProgressFill"),
  progressHint: document.querySelector("#progressHint"),
  resultStorage: document.querySelector("#resultStorage"),
  copyrightRiskPanel: document.querySelector("#copyrightRiskPanel"),
  copyrightRiskStatus: document.querySelector("#copyrightRiskStatus"),
  copyrightRiskText: document.querySelector("#copyrightRiskText"),
  textFidelityPanel: document.querySelector("#textFidelityPanel"),
  textFidelityStatus: document.querySelector("#textFidelityStatus"),
  textFidelityText: document.querySelector("#textFidelityText"),
  logoOverlayEnabled: document.querySelector("#logoOverlayEnabled"),
  logoComposeStatus: document.querySelector("#logoComposeStatus"),
  itineraryIdEnabled: document.querySelector("#itineraryIdEnabled"),
  itineraryIdInput: document.querySelector("#itineraryIdInput"),
  generateSampleCountHint: document.querySelector("#generateSampleCountHint"),
  downloadButton: document.querySelector("#downloadButton"),
  downloadOriginalButton: document.querySelector("#downloadOriginalButton"),
  continueEditButton: document.querySelector("#continueEditButton"),
  startVariantButton: document.querySelector("#startVariantButton"),
  previewCompareButton: document.querySelector("#previewCompareButton"),
  showVersionsButton: document.querySelector("#showVersionsButton"),
  hoverContinueEditButton: document.querySelector("#hoverContinueEditButton"),
  hoverVariantButton: document.querySelector("#hoverVariantButton"),
  inspectLongImageButton: document.querySelector("#inspectLongImageButton"),
  hoverShareButton: document.querySelector("#hoverShareButton"),
  saveGroupAssetButton: document.querySelector("#saveGroupAssetButton"),
  copyPromptButton: document.querySelector("#copyPromptButton"),
  errorMessage: document.querySelector("#errorMessage"),
  toastMessage: document.querySelector("#toastMessage"),
  errorDetails: document.querySelector("#errorDetails"),
  errorDetailsText: document.querySelector("#errorDetailsText"),
  debugOutput: document.querySelector("#debugOutput"),
  rawResponseOutput: document.querySelector("#rawResponseOutput"),
  previewModal: document.querySelector("#previewModal"),
  previewModalBackdrop: document.querySelector("#previewModalBackdrop"),
  previewModalTitle: document.querySelector("#previewModalTitle"),
  previewModalMeta: document.querySelector("#previewModalMeta"),
  previewSingleModeButton: document.querySelector("#previewSingleModeButton"),
  previewCompareModeButton: document.querySelector("#previewCompareModeButton"),
  previewZoomOutButton: document.querySelector("#previewZoomOutButton"),
  previewZoomResetButton: document.querySelector("#previewZoomResetButton"),
  previewZoomInButton: document.querySelector("#previewZoomInButton"),
  closePreviewButton: document.querySelector("#closePreviewButton"),
  previewSinglePane: document.querySelector("#previewSinglePane"),
  previewComparePane: document.querySelector("#previewComparePane"),
  previewSingleImage: document.querySelector("#previewSingleImage"),
  previewCompareSourceImage: document.querySelector("#previewCompareSourceImage"),
  previewCompareResultImage: document.querySelector("#previewCompareResultImage"),
  promptChips: Array.from(document.querySelectorAll(".prompt-chip")),
  feedbackStatus: document.querySelector("#feedbackStatus"),
  resultFeedbackPanel: document.querySelector("#resultFeedbackPanel"),
  feedbackRatingButtons: Array.from(document.querySelectorAll(".feedback-rating-button")),
  feedbackReasonPanel: document.querySelector("#feedbackReasonPanel"),
  feedbackReasonInput: document.querySelector("#feedbackReasonInput"),
  submitBadFeedbackButton: document.querySelector("#submitBadFeedbackButton"),
  regenerateFromBadFeedbackButton: document.querySelector("#regenerateFromBadFeedbackButton"),
  shareResultPanel: document.querySelector("#shareResultPanel"),
  shareResultStatus: document.querySelector("#shareResultStatus"),
  shareRecipientsList: document.querySelector("#shareRecipientsList"),
  shareRecipientSearchInput: document.querySelector("#shareRecipientSearchInput"),
  shareResultNoteInput: document.querySelector("#shareResultNoteInput"),
  submitShareResultButton: document.querySelector("#submitShareResultButton"),
  galleryEditorPanel: document.querySelector("#galleryEditorPanel"),
  galleryEditorStatus: document.querySelector("#galleryEditorStatus"),
  galleryFavoriteInput: document.querySelector("#galleryFavoriteInput"),
  galleryTagsInput: document.querySelector("#galleryTagsInput"),
  saveGalleryMetaButton: document.querySelector("#saveGalleryMetaButton"),
  versionHistoryPanel: document.querySelector("#versionHistoryPanel"),
  versionHistoryList: document.querySelector("#versionHistoryList"),
  versionHistoryStatus: document.querySelector("#versionHistoryStatus"),
  changePasswordModal: document.querySelector("#changePasswordModal"),
  changePasswordBackdrop: document.querySelector("#changePasswordBackdrop"),
  changePasswordForm: document.querySelector("#changePasswordForm"),
  currentPasswordInput: document.querySelector("#currentPasswordInput"),
  newPasswordInput: document.querySelector("#newPasswordInput"),
  changePasswordStatus: document.querySelector("#changePasswordStatus"),
  submitChangePasswordButton: document.querySelector("#submitChangePasswordButton"),
  closeChangePasswordButton: document.querySelector("#closeChangePasswordButton"),
  profileModal: document.querySelector("#profileModal"),
  profileBackdrop: document.querySelector("#profileBackdrop"),
  profileForm: document.querySelector("#profileForm"),
  closeProfileButton: document.querySelector("#closeProfileButton"),
  profileAvatarPreview: document.querySelector("#profileAvatarPreview"),
  profileAvatarInput: document.querySelector("#profileAvatarInput"),
  profileUsernameInput: document.querySelector("#profileUsernameInput"),
  profileDisplayNameInput: document.querySelector("#profileDisplayNameInput"),
  profileWechatInput: document.querySelector("#profileWechatInput"),
  profileEmailInput: document.querySelector("#profileEmailInput"),
  profilePhoneCountryCodeInput: document.querySelector("#profilePhoneCountryCodeInput"),
  profilePhoneInput: document.querySelector("#profilePhoneInput"),
  profileCompanyInput: document.querySelector("#profileCompanyInput"),
  profileDepartmentInput: document.querySelector("#profileDepartmentInput"),
  profileTeamInput: document.querySelector("#profileTeamInput"),
  profileJobTitleInput: document.querySelector("#profileJobTitleInput"),
  profileNoteInput: document.querySelector("#profileNoteInput"),
  profileCurrentPasswordLabel: document.querySelector("#profileCurrentPasswordLabel"),
  profileCurrentPasswordInput: document.querySelector("#profileCurrentPasswordInput"),
  profileStatus: document.querySelector("#profileStatus"),
  submitProfileButton: document.querySelector("#submitProfileButton"),
  teamChatModal: document.querySelector("#teamChatModal"),
  teamChatBackdrop: document.querySelector("#teamChatBackdrop"),
  closeTeamChatButton: document.querySelector("#closeTeamChatButton"),
  teamChatMembers: document.querySelector("#teamChatMembers"),
  teamChatTeamRoomButton: document.querySelector("#teamChatTeamRoomButton"),
  teamChatTeamRoomName: document.querySelector("#teamChatTeamRoomName"),
  teamChatTeamRoomMeta: document.querySelector("#teamChatTeamRoomMeta"),
  teamChatMain: document.querySelector("#teamChatMain"),
  teamChatRoomTitle: document.querySelector("#teamChatRoomTitle"),
  teamChatRoomMeta: document.querySelector("#teamChatRoomMeta"),
  teamChatGroupContext: document.querySelector("#teamChatGroupContext"),
  teamChatGroupContextToggle: document.querySelector("#teamChatGroupContextToggle"),
  teamChatGroupContextBody: document.querySelector("#teamChatGroupContextBody"),
  teamChatAnnouncement: document.querySelector("#teamChatAnnouncement"),
  teamChatGroupMemberPanel: document.querySelector("#teamChatGroupMemberPanel"),
  teamChatGroupMembers: document.querySelector("#teamChatGroupMembers"),
  teamChatGroupMemberCount: document.querySelector("#teamChatGroupMemberCount"),
  teamChatGroupStats: document.querySelector("#teamChatGroupStats"),
  teamChatGroupSummary: document.querySelector("#teamChatGroupSummary"),
  teamChatGroupAssets: document.querySelector("#teamChatGroupAssets"),
  teamChatMessages: document.querySelector("#teamChatMessages"),
  teamChatForm: document.querySelector("#teamChatForm"),
  teamChatMessageInput: document.querySelector("#teamChatMessageInput"),
  teamChatQuotePreview: document.querySelector("#teamChatQuotePreview"),
  teamChatQuoteAuthor: document.querySelector("#teamChatQuoteAuthor"),
  teamChatQuoteText: document.querySelector("#teamChatQuoteText"),
  clearTeamChatQuoteButton: document.querySelector("#clearTeamChatQuoteButton"),
  teamChatStatus: document.querySelector("#teamChatStatus"),
  refreshTeamChatButton: document.querySelector("#refreshTeamChatButton"),
  sendTeamChatButton: document.querySelector("#sendTeamChatButton"),
  bugReportModal: document.querySelector("#bugReportModal"),
  bugReportBackdrop: document.querySelector("#bugReportBackdrop"),
  bugReportForm: document.querySelector("#bugReportForm"),
  bugReportTitleInput: document.querySelector("#bugReportTitleInput"),
  bugReportDescriptionInput: document.querySelector("#bugReportDescriptionInput"),
  bugReportContactInput: document.querySelector("#bugReportContactInput"),
  bugReportStatus: document.querySelector("#bugReportStatus"),
  submitBugReportButton: document.querySelector("#submitBugReportButton"),
  closeBugReportButton: document.querySelector("#closeBugReportButton"),
  promptConfirmModal: document.querySelector("#promptConfirmModal"),
  promptConfirmBackdrop: document.querySelector("#promptConfirmBackdrop"),
  promptConfirmTitle: document.querySelector("#promptConfirmTitle"),
  promptConfirmDescription: document.querySelector("#promptConfirmDescription"),
  promptConfirmTextInput: document.querySelector("#promptConfirmTextInput"),
  promptConfirmCheckbox: document.querySelector("#promptConfirmCheckbox"),
  submitPromptConfirmButton: document.querySelector("#submitPromptConfirmButton"),
  cancelPromptConfirmButton: document.querySelector("#cancelPromptConfirmButton"),
  closePromptConfirmButton: document.querySelector("#closePromptConfirmButton"),
}

function loadJSON(key, fallbackValue) {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) {
      return fallbackValue
    }
    return JSON.parse(raw)
  } catch {
    return fallbackValue
  }
}

function saveJSON(key, value) {
  window.localStorage.setItem(key, JSON.stringify(value))
}

function escapeHTML(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function scopedStorageKey(baseKey) {
  return state.currentUser?.id ? `${baseKey}:user:${state.currentUser.id}` : baseKey
}

function settingsStorageKey() {
  return scopedStorageKey(STORAGE_KEY)
}

function legacySettingsStorageKey() {
  return state.currentUser?.id ? scopedStorageKey(LEGACY_STORAGE_KEY) : LEGACY_STORAGE_KEY
}

function historyStorageKey() {
  return scopedStorageKey(HISTORY_KEY)
}

function teamChatRecentDmStorageKey() {
  return scopedStorageKey(TEAM_CHAT_RECENT_DM_KEY)
}

function workspaceStorageKey() {
  return scopedStorageKey(WORKSPACE_KEY)
}

// 部署方启用 PICGEN_PROXY_AUTH_TOKEN 时，在浏览器控制台执行
// localStorage.setItem("picgen-proxy-token", "<token>") 后刷新即可。
// 不设置则不发送该头，行为与之前完全一致。
function proxyTokenHeaders() {
  try {
    const token = window.localStorage.getItem("picgen-proxy-token") || ""
    return token ? { "X-Proxy-Token": token } : {}
  } catch {
    return {}
  }
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...proxyTokenHeaders(),
      ...(options.headers || {}),
    },
  })
  let data = {}
  try {
    data = await response.json()
  } catch {
    data = {}
  }
  if (response.status === 401) {
    state.appReady = false
    state.persistenceReady = false
    state.lastReadyUserId = null
    stopTeamChatPolling()
    enterAuthGate("login", "登录已过期，请重新登录。")
  }
  return { response, data }
}

function enterAuthGate(mode = state.authMode || "login", message = "") {
  state.authMode = mode === "register" ? "register" : "login"
  // 会话过期常发生在聊天/资料弹窗打开时；这些弹窗是 .desktop-shell 的
  // 兄弟节点，不随 auth-gate 隐藏，不关掉会盖在登录表单上面。
  ;[
    refs.teamChatModal,
    refs.profileModal,
    refs.bugReportModal,
    refs.changePasswordModal,
    refs.promptConfirmModal,
  ].forEach((modal) => {
    if (modal && !modal.classList.contains("hidden")) {
      modal.classList.add("hidden")
      modal.setAttribute("aria-hidden", "true")
    }
  })
  document.body.classList.remove("modal-open", "chat-open")
  document.body.classList.add("auth-gate")
  document.body.classList.remove("app-shell")
  refs.authOverlay?.setAttribute("aria-hidden", "false")
  refs.authForm?.classList.remove("hidden")
  refs.passwordResetRequestForm?.classList.add("hidden")
  refs.passwordResetConfirmForm?.classList.add("hidden")
  if (refs.authTitle) {
    refs.authTitle.textContent = state.authMode === "register" ? "注册 PicGen" : "登录 PicGen"
  }
  if (refs.authSubtitle) {
    refs.authSubtitle.textContent = state.authMode === "register"
      ? "填写用户名、密码、公司和部门即可创建账号。"
      : "已有账号可直接登录；新用户可以注册后进入图像工作台。"
  }
  if (refs.loginAuthButton) {
    refs.loginAuthButton.textContent = state.authMode === "register" ? "创建账号" : "登录"
  }
  if (refs.registerAuthButton) {
    refs.registerAuthButton.classList.remove("hidden")
    refs.registerAuthButton.removeAttribute("aria-hidden")
    refs.registerAuthButton.tabIndex = 0
    refs.registerAuthButton.textContent = state.authMode === "register" ? "已有账号，去登录" : "注册"
  }
  if (refs.authPasswordInput) {
    refs.authPasswordInput.autocomplete = state.authMode === "register" ? "new-password" : "current-password"
  }
  refs.authOrgFields?.classList.toggle("hidden", state.authMode !== "register")
  if (refs.authError) {
    refs.authError.textContent = message
  }
  if (refs.passwordResetRequestStatus) {
    refs.passwordResetRequestStatus.textContent = ""
    refs.passwordResetRequestStatus.classList.remove("is-error")
  }
  if (refs.passwordResetConfirmStatus) {
    refs.passwordResetConfirmStatus.textContent = ""
    refs.passwordResetConfirmStatus.classList.remove("is-error")
  }
  window.setTimeout(() => refs.authUsernameInput?.focus(), 0)
}

function enterAppShell() {
  document.body.classList.remove("auth-gate")
  document.body.classList.add("app-shell")
  refs.authOverlay?.setAttribute("aria-hidden", "true")
  if (refs.authError) {
    refs.authError.textContent = ""
  }
}

function enterPasswordResetRequest() {
  state.passwordResetToken = ""
  refs.authForm?.classList.add("hidden")
  refs.passwordResetRequestForm?.classList.remove("hidden")
  refs.passwordResetConfirmForm?.classList.add("hidden")
  if (refs.authTitle) {
    refs.authTitle.textContent = "找回密码"
  }
  if (refs.authSubtitle) {
    refs.authSubtitle.textContent = "优先发送邮箱重置链接；没有邮箱时管理员会看到申请。"
  }
  if (refs.passwordResetUsernameInput && refs.authUsernameInput) {
    refs.passwordResetUsernameInput.value = refs.authUsernameInput.value.trim()
  }
  if (refs.passwordResetRequestStatus) {
    refs.passwordResetRequestStatus.textContent = ""
    refs.passwordResetRequestStatus.classList.remove("is-error")
  }
  window.setTimeout(() => refs.passwordResetUsernameInput?.focus(), 0)
}

function leavePasswordResetRequest() {
  if (refs.authUsernameInput && refs.passwordResetUsernameInput?.value.trim()) {
    refs.authUsernameInput.value = refs.passwordResetUsernameInput.value.trim()
  }
  enterAuthGate("login")
}

function getPasswordResetTokenFromUrl() {
  try {
    return new URL(window.location.href).searchParams.get("reset_token")?.trim() || ""
  } catch {
    return ""
  }
}

function enterPasswordResetConfirm(token) {
  state.passwordResetToken = token || ""
  refs.authForm?.classList.add("hidden")
  refs.passwordResetRequestForm?.classList.add("hidden")
  refs.passwordResetConfirmForm?.classList.remove("hidden")
  document.body.classList.add("auth-gate")
  document.body.classList.remove("app-shell")
  refs.authOverlay?.setAttribute("aria-hidden", "false")
  if (refs.authTitle) {
    refs.authTitle.textContent = "设置新密码"
  }
  if (refs.authSubtitle) {
    refs.authSubtitle.textContent = "请输入新密码完成自助重置。"
  }
  if (refs.passwordResetNewPasswordInput) {
    refs.passwordResetNewPasswordInput.value = ""
  }
  if (refs.passwordResetConfirmPasswordInput) {
    refs.passwordResetConfirmPasswordInput.value = ""
  }
  if (refs.passwordResetConfirmStatus) {
    refs.passwordResetConfirmStatus.textContent = ""
    refs.passwordResetConfirmStatus.classList.remove("is-error")
  }
  window.setTimeout(() => refs.passwordResetNewPasswordInput?.focus(), 0)
}

function setCurrentUser(user) {
  state.currentUser = user || null
  if (!state.currentUser) {
    resetTeamChatState()
  }
  const username = state.currentUser?.username || "未登录"
  const displayName = state.currentUser?.display_name || username
  const roleLabel = state.currentUser?.is_admin || state.currentUser?.role === "admin" ? "管理员" : "用户"
  if (refs.currentUsername) {
    refs.currentUsername.textContent = state.currentUser ? `${displayName} · ${roleLabel}` : username
  }
  if (refs.userAvatar) {
    renderAvatarElement(refs.userAvatar, state.currentUser, "user-avatar")
  }
  updateAdminPanelVisibility()
}

function renderAvatarElement(element, user, imageClassName = "") {
  if (!element) {
    return
  }
  element.replaceChildren()
  if (user?.avatar_url) {
    const image = document.createElement("img")
    image.src = user.avatar_url
    image.alt = ""
    if (imageClassName) {
      image.className = imageClassName
    }
    element.append(image)
    return
  }
  const label = user?.display_name || user?.username || "?"
  element.textContent = label.slice(0, 1).toUpperCase()
}

async function checkAuthSession({ showLogin = true } = {}) {
  if (state.serverConfig?.auth_enabled === false) {
    setCurrentUser(null)
    enterAppShell()
    return true
  }
  let response
  let data
  try {
    ;({ response, data } = await fetchJSON("/api/me", { cache: "no-store" }))
  } catch {
    // 启动时服务不可达不能变成未处理的 rejection 把 init() 打断；
    // 先落到登录页，手动登录仍然可用。
    setCurrentUser(null)
    if (showLogin) {
      enterAuthGate("login", "暂时连不上服务器，请稍后重试登录。")
    }
    return false
  }
  if (!response.ok) {
    setCurrentUser(null)
    if (showLogin) {
      enterAuthGate("login")
    }
    return false
  }
  setCurrentUser(data.user)
  enterAppShell()
  return true
}

async function refreshUsageSummary() {
  if (state.serverConfig?.auth_enabled === false || !refs.userUsageSummary) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/usage", { cache: "no-store" })
    if (!response.ok) {
      refs.userUsageSummary.textContent = "登录后自动统计。"
      return
    }
    const currentUserId = state.currentUser?.id
    const row = Array.isArray(data.users)
      ? data.users.find((item) => item.id === currentUserId)
      : null
    if (!row) {
      refs.userUsageSummary.textContent = "当前用户暂无生成记录。"
      return
    }
    const megabytes = row.saved_bytes ? (row.saved_bytes / 1024 / 1024).toFixed(1) : "0.0"
    refs.userUsageSummary.textContent = `${row.request_count} 次请求 · ${row.image_count} 张图 · ${megabytes} MB`
  } catch {
    refs.userUsageSummary.textContent = "用量统计暂时不可用。"
  }
  await refreshAdminUsers()
  await refreshAdminOrgContext()
  await refreshFeedbackSummary()
  await refreshBugReports()
  await refreshPasswordResetRequests()
  await refreshSharedResults()
  await refreshShareRecipients()
  await refreshGallery()
}

async function refreshImageStats() {
  if (state.serverConfig?.auth_enabled === false || !refs.userImageStats || !state.currentUser) {
    refs.userImageStats?.classList.add("hidden")
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/image-stats", { cache: "no-store" })
    if (!response.ok || !data.stats) {
      refs.userImageStats.classList.add("hidden")
      return
    }
    const mine = Number(data.stats.current_user_generated_image_count || 0)
    const platform = Number(data.stats.platform_generated_image_count || 0)
    refs.userImageStats.textContent = `我的 ${mine} 张 · 平台 ${platform} 张`
    refs.userImageStats.classList.remove("hidden")
  } catch {
    refs.userImageStats.classList.add("hidden")
  }
}

function updateAdminPanelVisibility() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  refs.adminPanel?.classList.toggle("hidden", !isAdmin)
  if (!isAdmin && refs.adminUsersList) {
    refs.adminUsersList.innerHTML = ""
  }
  if (!isAdmin && refs.feedbackRecentList) {
    refs.feedbackRecentList.innerHTML = ""
  }
  if (!isAdmin && refs.adminUserError) {
    refs.adminUserError.textContent = ""
  }
  if (!isAdmin && refs.passwordResetRequestsList) {
    refs.passwordResetRequestsList.innerHTML = ""
  }
}

function formatAdminBytes(bytes) {
  if (!bytes) {
    return "0.0 MB"
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function renderAdminUsers(users) {
  if (!refs.adminUsersList) {
    return
  }
  if (!Array.isArray(users) || users.length === 0) {
    refs.adminUsersList.innerHTML = '<p class="admin-empty">暂无用户。</p>'
    return
  }
  refs.adminUsersList.innerHTML = users.map((user) => {
    const roleLabel = user.role === "admin" ? "管理员" : "普通用户"
    const disabled = user.id === state.currentUser?.id ? "disabled" : ""
    const activeLabel = user.is_active ? "启用" : "停用"
    return `
      <article class="admin-user-row">
        <div>
          <strong>${escapeHTML(user.username || "")}</strong>
          <span>ID ${Number(user.id || 0)} · ${roleLabel} · ${activeLabel}</span>
          <span>${escapeHTML(user.company || "未分配")} · ${escapeHTML(user.department || "未分配")}</span>
        </div>
        <div class="admin-user-usage">
          <span>${Number(user.request_count || 0)} 次</span>
          <span>${Number(user.image_count || 0)} 张</span>
          <span>${formatAdminBytes(Number(user.saved_bytes || 0))}</span>
        </div>
        <button class="ghost-button admin-delete-user-button" type="button" data-user-id="${user.id}" ${disabled}>删除</button>
      </article>
    `
  }).join("")
}

function renderAdminOrgUnits(units) {
  state.adminOrgUnits = Array.isArray(units) ? units : []
  if (refs.adminOrgUnitSelect) {
    refs.adminOrgUnitSelect.replaceChildren()
    state.adminOrgUnits.forEach((unit) => {
      const option = document.createElement("option")
      option.value = `${unit.company}\n${unit.department}`
      option.textContent = `${unit.company} · ${unit.department}`
      refs.adminOrgUnitSelect.append(option)
    })
  }
  if (refs.adminOrgUnitsList) {
    if (!state.adminOrgUnits.length) {
      refs.adminOrgUnitsList.innerHTML = '<p class="admin-empty">暂无组织。</p>'
    } else {
      refs.adminOrgUnitsList.innerHTML = state.adminOrgUnits.map((unit) => `
        <article class="feedback-recent-row">
          <div>
            <strong>${escapeHTML(unit.company)} · ${escapeHTML(unit.department)}</strong>
            <span>${unit.is_active ? "启用" : "停用"} · ${escapeHTML(unit.updated_at || "")}</span>
          </div>
        </article>
      `).join("")
    }
  }
}

function renderOrgUnitSelect(select, units, { includeNewlineValue = false } = {}) {
  if (!select) {
    return
  }
  const currentValue = select.value
  select.replaceChildren()
  const source = Array.isArray(units) && units.length
    ? units
    : [{ company: "6renyou", department: "PD & OPS" }]
  source.forEach((unit) => {
    const option = document.createElement("option")
    option.value = includeNewlineValue ? `${unit.company}\n${unit.department}` : unit.company
    option.dataset.company = unit.company
    option.dataset.department = unit.department
    option.textContent = includeNewlineValue ? `${unit.company} · ${unit.department}` : unit.company
    select.append(option)
  })
  if (currentValue && Array.from(select.options).some((option) => option.value === currentValue)) {
    select.value = currentValue
  }
}

function renderDepartmentSelect(select, units, selectedCompany) {
  if (!select) {
    return
  }
  const currentValue = select.value
  const departments = (Array.isArray(units) ? units : [])
    .filter((unit) => unit.company === selectedCompany)
    .map((unit) => unit.department)
  const source = departments.length ? departments : ["PD & OPS"]
  select.replaceChildren()
  Array.from(new Set(source)).forEach((department) => {
    const option = document.createElement("option")
    option.value = department
    option.textContent = department
    select.append(option)
  })
  if (currentValue && source.includes(currentValue)) {
    select.value = currentValue
  }
}

function renderOrgUnitControls() {
  renderOrgUnitSelect(refs.authCompanyInput, state.orgUnits)
  renderDepartmentSelect(refs.authDepartmentInput, state.orgUnits, refs.authCompanyInput?.value || "6renyou")
  renderOrgUnitSelect(refs.profileCompanyInput, state.orgUnits)
  renderDepartmentSelect(refs.profileDepartmentInput, state.orgUnits, refs.profileCompanyInput?.value || "6renyou")
  renderOrgUnitSelect(refs.adminOrgUnitSelect, state.orgUnits, { includeNewlineValue: true })
  renderOrgUnitSelect(refs.adminAnnouncementOrgSelect, state.orgUnits, { includeNewlineValue: true })
}

async function refreshOrgUnits() {
  try {
    const { response, data } = await fetchJSON("/api/org-units", { cache: "no-store" })
    if (response.ok && Array.isArray(data.org_units)) {
      state.orgUnits = data.org_units
      renderOrgUnitControls()
    }
  } catch {
    renderOrgUnitControls()
  }
}

function renderAdminOrgAudit(events) {
  if (!refs.adminOrgAuditList) {
    return
  }
  const rows = Array.isArray(events) ? events : []
  if (!rows.length) {
    refs.adminOrgAuditList.innerHTML = '<p class="admin-empty">暂无组织调整记录。</p>'
    return
  }
  refs.adminOrgAuditList.innerHTML = rows.slice(0, 8).map((event) => `
    <article class="feedback-recent-row">
      <div>
        <strong>${escapeHTML(event.target_username || `用户 ${event.target_user_id}`)}</strong>
        <span>${escapeHTML(event.actor_username || "系统")} · ${escapeHTML(event.created_at || "")}</span>
      </div>
      <p>${escapeHTML(event.old_company || "未分配")} · ${escapeHTML(event.old_department || "未分配")} → ${escapeHTML(event.new_company || "未分配")} · ${escapeHTML(event.new_department || "未分配")}</p>
      <p>${escapeHTML(event.reason || "未填写原因")}</p>
    </article>
  `).join("")
}

function renderAdminOrgStats(items) {
  if (!refs.adminOrgStatsList) {
    return
  }
  const rows = Array.isArray(items) ? items : []
  if (!rows.length) {
    refs.adminOrgStatsList.innerHTML = '<p class="admin-empty">暂无组织统计。</p>'
    return
  }
  refs.adminOrgStatsList.innerHTML = rows.map((item) => `
    <article class="feedback-recent-row">
      <div>
        <strong>${escapeHTML(item.group?.title || "未命名组织")}</strong>
        <span>${Number(item.users?.member_count || 0)} 人 · ${Number(item.usage?.generated_image_count || 0)} 张图 · ${Number(item.assets?.asset_count || 0)} 个资产</span>
      </div>
      <p>满意 ${Number(item.feedback?.totals?.good || 0)} · 一般 ${Number(item.feedback?.totals?.ok || 0)} · 不好 ${Number(item.feedback?.totals?.bad || 0)}</p>
    </article>
  `).join("")
}

async function refreshAdminOrgContext() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  if (!isAdmin || !refs.adminOrgPanel) {
    return
  }
  if (refs.adminOrgStatus) {
    refs.adminOrgStatus.textContent = ""
  }
  try {
    const [orgResponse, auditResponse, statsResponse] = await Promise.all([
      fetchJSON("/api/admin/org-units", { cache: "no-store" }),
      fetchJSON("/api/admin/org-audit", { cache: "no-store" }),
      fetchJSON("/api/admin/org-stats", { cache: "no-store" }),
    ])
    if (orgResponse.response.ok) {
      renderAdminOrgUnits(orgResponse.data.org_units)
      state.orgUnits = Array.isArray(orgResponse.data.org_units) ? orgResponse.data.org_units : state.orgUnits
      renderOrgUnitControls()
    }
    if (auditResponse.response.ok) {
      renderAdminOrgAudit(auditResponse.data.events)
    }
    if (statsResponse.response.ok) {
      renderAdminOrgStats(statsResponse.data.org_stats)
    }
  } catch {
    if (refs.adminOrgStatus) {
      refs.adminOrgStatus.textContent = "组织信息暂时不可用。"
    }
  }
}

async function submitAdminOrgUnit(event) {
  event.preventDefault()
  if (!refs.adminOrgCompanyInput || !refs.adminOrgDepartmentInput) {
    return
  }
  const company = refs.adminOrgCompanyInput.value.trim()
  const department = refs.adminOrgDepartmentInput.value.trim()
  if (!company || !department) {
    refs.adminOrgStatus.textContent = "请填写公司和部门。"
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/admin/org-units", {
      method: "POST",
      body: JSON.stringify({ company, department }),
    })
    if (!response.ok) {
      refs.adminOrgStatus.textContent = data.error || "组织创建失败"
      return
    }
    refs.adminOrgStatus.textContent = "组织已更新。"
    refs.adminOrgDepartmentInput.value = ""
    await refreshAdminOrgContext()
  } catch {
    refs.adminOrgStatus.textContent = "组织创建失败。"
  }
}

async function submitAdminUserOrg(event) {
  event.preventDefault()
  const userId = Number(refs.adminOrgUserIdInput?.value || 0)
  const selected = refs.adminOrgUnitSelect?.value || ""
  const [company = "", department = ""] = selected.split("\n")
  if (!userId || !company || !department) {
    refs.adminOrgStatus.textContent = "请选择用户和组织。"
    return
  }
  try {
    const { response, data } = await fetchJSON(`/api/admin/users/${userId}/org`, {
      method: "PUT",
      body: JSON.stringify({
        company,
        department,
        reason: refs.adminOrgReasonInput?.value.trim() || "",
      }),
    })
    if (!response.ok) {
      refs.adminOrgStatus.textContent = data.error || "组织调整失败"
      return
    }
    refs.adminOrgStatus.textContent = "用户组织已调整。"
    if (refs.adminOrgReasonInput) {
      refs.adminOrgReasonInput.value = ""
    }
    await Promise.all([refreshAdminOrgContext(), refreshAdminUsers()])
  } catch {
    refs.adminOrgStatus.textContent = "组织调整失败。"
  }
}

async function submitAdminGroupAnnouncement(event) {
  event.preventDefault()
  const selected = refs.adminAnnouncementOrgSelect?.value || ""
  const [company = "", department = ""] = selected.split("\n")
  const content = refs.adminAnnouncementContentInput?.value.trim() || ""
  if (!company || !department) {
    refs.adminOrgStatus.textContent = "请选择公告组织。"
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/team-chat/group-announcement", {
      method: "PUT",
      body: JSON.stringify({ company, department, content }),
    })
    if (!response.ok) {
      refs.adminOrgStatus.textContent = data.error || "群公告保存失败"
      return
    }
    refs.adminOrgStatus.textContent = content ? "群公告已保存。" : "群公告已清空。"
    if (state.teamChatRoom.type === "team") {
      await refreshTeamChatGroupContext()
    }
  } catch {
    refs.adminOrgStatus.textContent = "群公告保存失败。"
  }
}

async function refreshAdminUsers() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  if (!isAdmin || !refs.adminPanel) {
    return
  }
  if (refs.adminUserError) {
    refs.adminUserError.textContent = ""
  }
  try {
    const { response, data } = await fetchJSON("/api/admin/users", { cache: "no-store" })
    if (!response.ok) {
      if (refs.adminUserError) {
        refs.adminUserError.textContent = data.error || "无法读取用户列表"
      }
      return
    }
    renderAdminUsers(data.users)
  } catch {
    if (refs.adminUserError) {
      refs.adminUserError.textContent = "用户列表暂时不可用。"
    }
  }
}

function renderFeedbackSummary(summary) {
  const totals = summary?.totals || {}
  if (refs.feedbackGoodCount) {
    refs.feedbackGoodCount.textContent = String(totals.good || 0)
  }
  if (refs.feedbackOkCount) {
    refs.feedbackOkCount.textContent = String(totals.ok || 0)
  }
  if (refs.feedbackBadCount) {
    refs.feedbackBadCount.textContent = String(totals.bad || 0)
  }
  if (refs.feedbackSummaryRate) {
    const totalCount = Number(summary?.total_count || 0)
    refs.feedbackSummaryRate.textContent = totalCount
      ? `满意率 ${(Number(summary.satisfaction_rate || 0) * 100).toFixed(1)}% · 共 ${totalCount} 条反馈`
      : "暂无反馈。"
  }
  if (!refs.feedbackRecentList) {
    return
  }
  const recent = Array.isArray(summary?.recent) ? summary.recent : []
  if (!recent.length) {
    refs.feedbackRecentList.innerHTML = '<p class="admin-empty">暂无近期反馈。</p>'
    return
  }
  refs.feedbackRecentList.innerHTML = recent.slice(0, 6).map((item) => {
    const label = item.rating === "good" ? "满意" : item.rating === "ok" ? "一般" : "不好"
    const reason = item.reason || "未填写原因"
    return `
      <article class="feedback-recent-row">
        <div>
          <strong>${escapeHTML(label)} · ${escapeHTML(item.username || "")}</strong>
          <span>${escapeHTML(item.mode || "生成")} · ${escapeHTML(item.model || "")}</span>
        </div>
        <p>${escapeHTML(reason)}</p>
      </article>
    `
  }).join("")
}

async function refreshFeedbackSummary() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  if (!isAdmin || !refs.adminFeedbackSummary) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/feedback/summary", { cache: "no-store" })
    if (response.ok) {
      renderFeedbackSummary(data)
    }
  } catch {
    if (refs.feedbackSummaryRate) {
      refs.feedbackSummaryRate.textContent = "满意度统计暂时不可用。"
    }
  }
}

function renderBugReports(reports) {
  if (!refs.bugReportsList) {
    return
  }
  if (!Array.isArray(reports) || !reports.length) {
    refs.bugReportsList.innerHTML = '<p class="admin-empty">暂无 Bug 反馈。</p>'
    return
  }
  refs.bugReportsList.innerHTML = reports.slice(0, 8).map((report) => `
    <article class="feedback-recent-row">
      <div>
        <strong>${escapeHTML(report.title || "Bug 反馈")} · ${escapeHTML(report.username || "")}</strong>
        <span>${escapeHTML(report.notification_status || "not_configured")} · ${escapeHTML(report.created_at || "")}</span>
      </div>
      <p>${escapeHTML(report.description || "")}</p>
    </article>
  `).join("")
}

async function refreshBugReports() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  if (!isAdmin || !refs.bugReportsList) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/bug-reports", { cache: "no-store" })
    if (response.ok) {
      renderBugReports(data.reports)
    }
  } catch {
    refs.bugReportsList.innerHTML = '<p class="admin-empty">Bug 反馈暂时不可用。</p>'
  }
}

function createPasswordResetRequestRow(item) {
  const row = document.createElement("article")
  row.className = "password-reset-row"

  const header = document.createElement("div")
  header.className = "password-reset-row-main"

  const title = document.createElement("strong")
  title.textContent = item.matched_user
    ? `${item.matched_username || item.username} 申请找回密码`
    : `${item.username || item.username_normalized} 未匹配到账号`

  const meta = document.createElement("span")
  const timeText = item.created_at ? ` · ${item.created_at}` : ""
  const emailText = item.email_available
    ? `邮箱 ${item.email_masked || "已填写"}${item.email_sent_at ? " · 已发邮件" : ""}`
    : "无邮箱，需管理员兜底"
  meta.textContent = item.matched_user
    ? `${emailText}${timeText}`
    : `请先核对用户名${timeText}`

  header.append(title, meta)
  row.append(header)

  if (!item.matched_user || !item.user_id) {
    const hint = document.createElement("p")
    hint.className = "password-reset-hint"
    hint.textContent = "该申请没有匹配到现有账号，可能是用户输错了用户名。"
    row.append(hint)
    return row
  }

  const form = document.createElement("form")
  form.className = "password-reset-admin-form"
  form.dataset.userId = String(item.user_id)

  const input = document.createElement("input")
  input.type = "password"
  input.name = "password"
  input.autocomplete = "new-password"
  input.minLength = 8
  input.maxLength = 256
  input.placeholder = "输入新密码"
  input.required = true

  const button = document.createElement("button")
  button.className = "ghost-button"
  button.type = "submit"
  button.textContent = "重置"

  form.append(input, button)
  row.append(form)
  return row
}

function renderPasswordResetRequests(requests) {
  if (!refs.passwordResetRequestsList) {
    return
  }
  refs.passwordResetRequestsList.replaceChildren()
  if (!Array.isArray(requests) || !requests.length) {
    const empty = document.createElement("p")
    empty.className = "admin-empty"
    empty.textContent = "暂无待处理找回申请。"
    refs.passwordResetRequestsList.append(empty)
    return
  }
  const fragment = document.createDocumentFragment()
  requests.forEach((item) => {
    fragment.append(createPasswordResetRequestRow(item))
  })
  refs.passwordResetRequestsList.append(fragment)
}

async function refreshPasswordResetRequests() {
  const isAdmin = state.currentUser?.is_admin || state.currentUser?.role === "admin"
  if (!isAdmin || !refs.passwordResetRequestsList) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/admin/password-reset-requests", { cache: "no-store" })
    if (response.ok) {
      renderPasswordResetRequests(data.requests)
    }
  } catch {
    refs.passwordResetRequestsList.innerHTML = '<p class="admin-empty">密码找回申请暂时不可用。</p>'
  }
}

async function submitPasswordResetAdminForm(form) {
  const userId = form?.dataset?.userId
  const input = form?.querySelector('input[name="password"]')
  const button = form?.querySelector("button")
  const password = input?.value || ""
  if (!userId || password.length < 8) {
    setStatusMessage("请输入至少 8 位新密码。")
    return
  }
  if (button) {
    button.disabled = true
  }
  try {
    const { response, data } = await fetchJSON(`/api/admin/users/${encodeURIComponent(userId)}/password`, {
      method: "PUT",
      body: JSON.stringify({ password }),
    })
    if (!response.ok) {
      setError(data.error || "重置密码失败")
      return
    }
    if (input) {
      input.value = ""
    }
    setStatusMessage("密码已重置，用户旧会话已失效。")
    await refreshPasswordResetRequests()
    await refreshAdminUsers()
  } catch {
    setError("重置密码时网络连接错误")
  } finally {
    if (button) {
      button.disabled = false
    }
  }
}

async function submitAdminCreateUser(event) {
  event.preventDefault()
  const username = refs.adminNewUsernameInput?.value.trim() || ""
  const password = refs.adminNewPasswordInput?.value || ""
  const role = refs.adminNewRoleSelect?.value || "user"
  if (refs.adminUserError) {
    refs.adminUserError.textContent = ""
  }
  if (!username || password.length < 8) {
    if (refs.adminUserError) {
      refs.adminUserError.textContent = "请填写用户名和至少 8 位密码。"
    }
    return
  }
  if (refs.adminCreateUserButton) {
    refs.adminCreateUserButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    })
    if (!response.ok) {
      if (refs.adminUserError) {
        refs.adminUserError.textContent = data.error || "创建用户失败"
      }
      return
    }
    if (refs.adminNewUsernameInput) {
      refs.adminNewUsernameInput.value = ""
    }
    if (refs.adminNewPasswordInput) {
      refs.adminNewPasswordInput.value = ""
    }
    if (refs.adminNewRoleSelect) {
      refs.adminNewRoleSelect.value = "user"
    }
    await refreshAdminUsers()
    await refreshUsageSummary()
  } catch {
    if (refs.adminUserError) {
      refs.adminUserError.textContent = "网络连接错误"
    }
  } finally {
    if (refs.adminCreateUserButton) {
      refs.adminCreateUserButton.disabled = false
    }
  }
}

async function deleteAdminUser(userId) {
  if (!userId) {
    return
  }
  if (refs.adminUserError) {
    refs.adminUserError.textContent = ""
  }
  try {
    const { response, data } = await fetchJSON(`/api/admin/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    })
    if (!response.ok) {
      if (refs.adminUserError) {
        refs.adminUserError.textContent = data.error || "删除用户失败"
      }
      return
    }
    await refreshAdminUsers()
    await refreshUsageSummary()
  } catch {
    if (refs.adminUserError) {
      refs.adminUserError.textContent = "网络连接错误"
    }
  }
}

function updateFeedbackPanelVisibility() {
  const hasResult = Boolean(state.resultPreview?.src)
  refs.resultFeedbackPanel?.classList.toggle("hidden", !hasResult)
  if (!hasResult) {
    refs.feedbackReasonPanel?.classList.add("hidden")
    refs.shareResultPanel?.classList.add("hidden")
  }
}

function buildFeedbackPayload(rating, reason = "") {
  const candidate = state.resultCandidates[state.selectedCandidateIndex] || {}
  return {
    rating,
    reason,
    prompt: state.lastResultPrompt || "",
    mode: state.lastResultMode || "",
    model: state.lastResultModel || "",
    generated_image_id: candidate.generated_image_id || state.lastResultImage?.generatedImageId || null,
    saved_image_path: candidate.saved_image_path || state.lastResultImage?.savedPath || "",
    saved_image_url: serverShareableImageUrl(candidate),
  }
}

function selectedGeneratedImageId() {
  const candidate = state.resultCandidates[state.selectedCandidateIndex] || {}
  return candidate.generated_image_id || state.lastResultImage?.generatedImageId || null
}

function selectedPromptRecipe() {
  const recipeId = refs.promptRecipeSelect?.value || state.selectedRecipeId || ""
  return state.promptRecipes.find((recipe) => recipe.id === recipeId) || null
}

function promptRecipeAppendText(recipe = selectedPromptRecipe()) {
  if (!recipe?.prompt_suffix) {
    return ""
  }
  return [
    `配方辅助（${recipe.title} · ${recipe.version || "v1"}，只追加质量要求，不覆盖原提示词）：`,
    recipe.prompt_suffix,
  ].join("\n")
}

function buildEffectiveGeneratePrompt() {
  const originalPrompt = refs.generatePromptInput.value.trim()
  const recipe = selectedPromptRecipe()
  const promptMode = state.promptMode === "recipe" && recipe ? "recipe" : "free"
  const recipeText = promptMode === "recipe" ? promptRecipeAppendText(recipe) : ""
  const effectivePrompt = [originalPrompt, recipeText].filter(Boolean).join("\n\n")
  return {
    originalPrompt,
    effectivePrompt,
    promptMode,
    recipe,
  }
}

function isLegacyProgramLayoutBackgroundPrompt(value) {
  const normalized = String(value || "").replace(/\s+/g, "")
  if (!normalized) {
    return false
  }
  const hasBackgroundIntent = ["无文字背景底图", "无字背景底图", "生成背景底图"].some((marker) => normalized.includes(marker))
  const hasProgramLayoutIntent = ["后续程序排版", "用于程序排版", "程序排版中文", "程序覆盖", "中文由程序"].some((marker) => normalized.includes(marker))
  const forbidsText = ["不生成任何可读文字", "不要生成文字内容", "不生成文字内容", "不要生成任何可读文字"].some((marker) => normalized.includes(marker))
  return hasBackgroundIntent && hasProgramLayoutIntent && forbidsText
}

function legacyProgramLayoutPromptMessage() {
  return "检测到旧程序排版背景底图提示词：它会要求 AI 生成空背景。请改成包含标题、榜单正文和全部可见文案的最终海报提示词。"
}

function rejectLegacyProgramLayoutBackgroundPrompt(prompt) {
  if (!isLegacyProgramLayoutBackgroundPrompt(prompt)) {
    return false
  }
  appendDebugLine("参数校验失败：旧程序排版背景底图提示词", { code: "legacy_layout_background_prompt" })
  setError(legacyProgramLayoutPromptMessage())
  refs.generatePromptInput.focus()
  return true
}

function normalizeTextContractItem(value) {
  return String(value || "")
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[：:，,；;、.\s]+|[：:，,；;、.\s]+$/g, "")
}

function addTextContractItem(items, value) {
  const cleaned = normalizeTextContractItem(value)
  if (!cleaned || cleaned.length < 2 || cleaned.length > 160) {
    return
  }
  if (!items.includes(cleaned)) {
    items.push(cleaned)
  }
}

function extractTextReplacementPairs(prompt) {
  const text = String(prompt || "")
  const pairs = []
  const seen = new Set()
  const addPair = (fromValue, toValue) => {
    const from = normalizeTextContractItem(fromValue)
    const to = normalizeTextContractItem(toValue)
    if (!from || !to || from === to) {
      return
    }
    const key = `${from}\u0000${to}`
    if (!seen.has(key)) {
      pairs.push({ from, to })
      seen.add(key)
    }
  }

  const quotedPattern = /把\s*[“"']\s*([^”"']{1,200}?)\s*[”"']\s*(?:改成|替换成|换成|改为|变成)\s*[“"']\s*([^”"']{1,200}?)\s*[”"']/giu
  for (const match of text.matchAll(quotedPattern)) {
    addPair(match[1], match[2])
  }

  for (const line of text.split(/\n+/)) {
    for (const match of line.matchAll(TEXT_REPLACEMENT_RE)) {
      addPair(match[1], match[2])
    }
  }
  return pairs
}

function extractLabeledVisibleText(prompt) {
  const text = String(prompt || "")
  const items = []
  for (const match of text.matchAll(TEXT_CONTRACT_LABEL_RE)) {
    const value = normalizeTextContractItem(match[1])
    value
      .split(/\s*[|｜]\s*|\s{2,}/)
      .forEach((part) => addTextContractItem(items, part))
  }
  return items
}

function extractQuotedVisibleText(prompt) {
  const items = []
  for (const match of String(prompt || "").matchAll(/[“"']([^”"'\n]{2,120})[”"']/gu)) {
    addTextContractItem(items, match[1])
  }
  return items
}

function buildVisibleTextContract(prompt) {
  const required = []
  const forbidden = []
  const replacements = extractTextReplacementPairs(prompt)
  replacements.forEach((pair) => {
    addTextContractItem(forbidden, pair.from)
    addTextContractItem(required, pair.to)
  })
  ;[...extractLabeledVisibleText(prompt), ...extractQuotedVisibleText(prompt)].forEach((item) => {
    if (!forbidden.includes(item)) {
      addTextContractItem(required, item)
    }
  })
  return {
    required: required.slice(0, TEXT_CONTRACT_MAX_ITEMS),
    forbidden: forbidden.slice(0, TEXT_CONTRACT_MAX_ITEMS),
    replacements,
  }
}

function formatVisibleTextContractPrompt(contract) {
  const required = Array.isArray(contract?.required) ? contract.required : []
  const forbidden = Array.isArray(contract?.forbidden) ? contract.forbidden : []
  if (!required.length && !forbidden.length) {
    return ""
  }
  const lines = [
    VISIBLE_TEXT_CONTRACT_HEADING,
    "必须出现以下文字，逐字一致；主标题/核心标题可以使用高识别度商业美术字、手写标题、立体描边、金属或笔刷字效，但不能换字、漏字、增字或改顺序；正文、地名、日期、序号、说明和贴士必须清晰可读。",
    ...required.map((item) => `- ${item}`),
  ]
  if (forbidden.length) {
    lines.push("旧文字不得继续出现；如果输入图里存在这些旧字，必须替换或清除：")
    lines.push(...forbidden.map((item) => `- ${item}`))
  }
  lines.push("验收标准：成图中任一必需短语缺失、错字、同音替换、繁简误换、数字符号错误或旧文字残留，都视为失败。")
  return lines.join("\n")
}

function updatePromptModeUI() {
  state.promptMode = refs.promptModeInputs.find((input) => input.checked)?.value || "free"
  refs.recipeAssistPanel?.classList.toggle("hidden", state.promptMode !== "recipe")
  updatePromptRecipeSummary()
  updateEffectivePromptPreview()
}

function updatePromptRecipeSummary() {
  const recipe = selectedPromptRecipe()
  if (!refs.promptRecipeSummary) {
    return
  }
  if (state.promptMode !== "recipe") {
    refs.promptRecipeSummary.textContent = "精确提示词模式会把你写的提示词作为主输入原样发送。"
    return
  }
  if (!recipe) {
    refs.promptRecipeSummary.textContent = "选择一个配方后，可查看和追加最终发送提示词；配方不会自动覆盖你的意图。"
    return
  }
  refs.promptRecipeSummary.textContent = `${recipe.summary || ""} ${recipe.guidance || ""}`.trim()
}

function updateEffectivePromptPreview() {
  if (!refs.effectivePromptPreview) {
    return
  }
  const { effectivePrompt, originalPrompt } = buildEffectiveGeneratePrompt()
  refs.effectivePromptPreview.textContent = effectivePrompt || originalPrompt || "先输入提示词。"
}

function renderPromptRecipes() {
  if (!refs.promptRecipeSelect) {
    return
  }
  refs.promptRecipeSelect.replaceChildren()
  const placeholder = document.createElement("option")
  placeholder.value = ""
  placeholder.textContent = "选择配方"
  refs.promptRecipeSelect.append(placeholder)
  state.promptRecipes
    .filter((recipe) => recipe.mode === "generate")
    .forEach((recipe) => {
      const option = document.createElement("option")
      option.value = recipe.id
      option.textContent = recipe.title
      refs.promptRecipeSelect.append(option)
    })
  if (state.selectedRecipeId) {
    refs.promptRecipeSelect.value = state.selectedRecipeId
  }
  updatePromptRecipeSummary()
  updateEffectivePromptPreview()
  renderPromptRecipeCards()
}

async function loadPromptRecipes() {
  try {
    const { response, data } = await fetchJSON("api/recipes", { cache: "no-store" })
    if (!response.ok) {
      state.promptRecipes = []
      renderPromptRecipes()
      return
    }
    state.promptRecipes = Array.isArray(data.recipes) ? data.recipes : []
    renderPromptRecipes()
  } catch {
    state.promptRecipes = []
    renderPromptRecipes()
  }
}

function renderPromptRecipeCards() {
  if (!refs.promptRecipeCards) {
    return
  }
  refs.promptRecipeCards.replaceChildren()
  const recipes = state.promptRecipes.filter((recipe) => recipe.mode === "generate")
  if (!recipes.length) {
    const empty = document.createElement("p")
    empty.className = "helper-text"
    empty.textContent = "配方库暂时不可用；你仍然可以使用精确提示词生成。"
    refs.promptRecipeCards.append(empty)
    return
  }
  recipes.forEach((recipe) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "prompt-recipe-card"
    button.classList.toggle("active", recipe.id === (refs.promptRecipeSelect?.value || state.selectedRecipeId))
    button.dataset.recipeId = recipe.id

    const title = document.createElement("strong")
    title.textContent = recipe.title
    const category = document.createElement("span")
    category.textContent = recipe.category || "创作配方"
    const summary = document.createElement("p")
    summary.textContent = recipe.summary || recipe.guidance || ""
    const keywords = document.createElement("small")
    keywords.textContent = Array.isArray(recipe.recommended_keywords)
      ? recipe.recommended_keywords.join(" / ")
      : ""

    button.append(title, category, summary, keywords)
    button.addEventListener("click", () => selectPromptRecipe(recipe.id, { enableRecipeMode: true }))
    refs.promptRecipeCards.append(button)
  })
}

function selectPromptRecipe(recipeId, { enableRecipeMode = false } = {}) {
  state.selectedRecipeId = recipeId || ""
  if (refs.promptRecipeSelect) {
    refs.promptRecipeSelect.value = state.selectedRecipeId
  }
  if (enableRecipeMode) {
    state.promptMode = "recipe"
    refs.promptModeInputs.forEach((input) => {
      input.checked = input.value === "recipe"
    })
  }
  updatePromptModeUI()
  renderPromptRecipeCards()
  scheduleWorkspacePersist()
}

function applyPromptRecipeToPrompt() {
  const recipe = selectedPromptRecipe()
  if (!recipe) {
    setStatusMessage("请先选择一个创作配方。")
    return
  }
  const snippet = promptRecipeAppendText(recipe)
  const current = refs.generatePromptInput.value.trimEnd()
  if (current.includes(`配方辅助（${recipe.title}`)) {
    setStatusMessage("提示词里已经包含这个配方要求。")
    return
  }
  refs.generatePromptInput.value = current ? `${current}\n\n${snippet}` : snippet
  updatePromptCounters()
  updateEffectivePromptPreview()
  scheduleWorkspacePersist()
  setStatusMessage("已把配方要求追加到提示词。")
  refs.generatePromptInput.focus()
}

function creativeBriefFields() {
  return [
    ["destination", refs.creativeBriefDestinationInput],
    ["audience", refs.creativeBriefAudienceInput],
    ["channel", refs.creativeBriefChannelInput],
    ["mood", refs.creativeBriefMoodInput],
    ["mustHave", refs.creativeBriefMustHaveInput],
    ["avoid", refs.creativeBriefAvoidInput],
  ]
}

function creativeBriefSnapshot() {
  return Object.fromEntries(
    creativeBriefFields().map(([key, input]) => [key, input?.value.trim() || ""])
  )
}

function restoreCreativeBrief(snapshot = {}) {
  creativeBriefFields().forEach(([key, input]) => {
    if (input) {
      input.value = snapshot?.[key] || ""
    }
  })
}

function buildCreativeBriefSnippet() {
  const brief = creativeBriefSnapshot()
  const lines = [
    ["目的地/产品", brief.destination],
    ["目标人群", brief.audience],
    ["投放渠道", brief.channel],
    ["气质方向", brief.mood],
    ["必须保留", brief.mustHave],
    ["避免出现", brief.avoid],
  ].filter(([, value]) => value)

  if (!lines.length) {
    return ""
  }

  return [
    "补充创作 brief（只作为辅助上下文，不要抹平原提示词的个性）：",
    ...lines.map(([label, value]) => `${label}：${value}`),
  ].join("\n")
}

function applyCreativeBriefToPrompt() {
  const snippet = buildCreativeBriefSnippet()
  if (!snippet) {
    setStatusMessage("先填写至少一项创意辅助信息。")
    return
  }
  const current = refs.generatePromptInput.value.trimEnd()
  if (current.includes("补充创作 brief（只作为辅助上下文")) {
    setStatusMessage("提示词里已经包含创意辅助 brief。")
    return
  }
  refs.generatePromptInput.value = current ? `${current}\n\n${snippet}` : snippet
  updatePromptCounters()
  scheduleWorkspacePersist()
  setStatusMessage("已把创意辅助补充到提示词。")
  refs.generatePromptInput.focus()
}

async function askBotWithCreativeBrief() {
  const basePrompt = refs.generatePromptInput.value.trim()
  const snippet = buildCreativeBriefSnippet()
  if (!basePrompt && !snippet) {
    setStatusMessage("先写提示词，或填写一点创意辅助信息。")
    return
  }
  await openTeamChatModal()
  const message = [
    "@GPT-BOT 请从高端旅行视觉质量角度帮我审一下这次生图需求。",
    "请给出：1）是否足够高级；2）构图/光影/质感建议；3）可直接追加到提示词的 3-5 条短句。",
    "注意：不要把我的原提示词改成统一模板，只把可选 brief 作为补充上下文。",
    basePrompt ? `\n原提示词：\n${basePrompt}` : "",
    snippet ? `\n${snippet}` : "",
  ].filter(Boolean).join("\n")
  if (refs.teamChatMessageInput) {
    refs.teamChatMessageInput.value = message.slice(0, TEAM_CHAT_MAX_MESSAGE_LENGTH)
    refs.teamChatMessageInput.focus()
  }
}

function parseItinerarySize() {
  const selectedSize = refs.itinerarySizeSelect?.value || "auto"
  if (selectedSize === "auto") {
    return "auto"
  }
  const [widthText, heightText] = selectedSize.split("x")
  const width = Number.parseInt(widthText, 10)
  const height = Number.parseInt(heightText, 10)
  if (!Number.isInteger(width) || !Number.isInteger(height)) {
    throw new Error("行程地图尺寸无效。")
  }
  if (width % 16 !== 0 || height % 16 !== 0) {
    throw new Error("行程地图尺寸的宽高都必须是 16 的倍数。")
  }
  return formatSizeValue(width, height)
}

function itineraryThemePrompt() {
  const theme = refs.itineraryThemeSelect?.value || "comic"
  if (theme === "comic") {
    return "水彩漫画路线图：柔和浅蓝/浅黄水彩底、清晰地图轮廓、红色粗路线、白心红点或圆点站位、手写感中文标题、地标小插画、车辆/飞机/火车/脚印小图标；画面亲切有旅行手帐感，但漫画风格不能牺牲地理真实性，地点相对位置、路线顺序、日期、距离、交通方式、酒店和核心景区不能省略。"
  }
  if (theme === "dark") {
    return "深色高级手绘地形地图，午夜蓝与暖金路线，低饱和、高对比，适合高端旅行海报；保留真实山脉、湖泊、沙漠和城市层级，路线像精品旅行地图而不是导航截图。"
  }
  if (theme === "classic") {
    return "复古高级手绘地形地图，羊皮纸、金色路线、轻微等高线和克制指南针元素，保持现代高级旅行质感；不要生成路线图例或线型说明框，地点落位仍必须服从真实地理。"
  }
  return "高级水彩漫画路线图，保留旅行定制海报的高级感，色彩克制、山野度假质感、路线清楚但画面不拥挤；使用红色粗路线、圆点站位和地标小插画；真实地貌、山脉、湖泊、海岸、岛屿、沙漠、城市和边境层级必须准确。"
}

function drawItineraryLogoSafeArea() {
  return "左上角预留自然干净的 LOGO 留白；不要让 AI 绘制或改造 6 人游 LOGO，不要画 LOGO 占位框，不要画边框，不要画白底底板，不要画贴纸底座或任何临时标识；最终由程序使用官方透明 PNG 原样贴入。"
}

function stripCodeFence(value) {
  const text = String(value || "").trim()
  const match = text.match(/^```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```$/)
  return (match ? match[1] : text).trim()
}

function isCompleteItineraryPrompt(value) {
  const text = stripCodeFence(value)
  // 用户粘贴完整行程地图 prompt 时不再二次包裹，避免重复标题和要求。
  return text.includes("客户行程原文如下")
    && text.includes("画面与信息要求")
    && text.includes("地理正确性硬性要求")
}

function normalizeCompleteItineraryPrompt(value) {
  let text = stripCodeFence(value)
  const legacyLogoSafeArea = ["左上角预留干净白底", "LOGO 安全区"].join(" ")
  text = text
    .replaceAll(`${legacyLogoSafeArea}；不要让 AI 绘制或改造 6 人游 LOGO，最终由程序使用官方透明 PNG 原样贴入。`, drawItineraryLogoSafeArea())
    .replaceAll(legacyLogoSafeArea, "左上角预留自然干净的 LOGO 留白")
    .replaceAll(
      "LOGO 位置附近保留干净留白，背景尽量简单，避免图片元素和 LOGO 少量重合。",
      "LOGO 位置附近保留自然干净背景，背景尽量简单；不要绘制 LOGO 占位框、边框、描边、白色底板、贴纸底座或任何临时标识。",
    )
  if (!text.includes("地图准确性保护")) {
    text = `${text}\n\n${ITINERARY_GEOGRAPHY_GUARD}`
  }
  if (!text.includes("不要画 LOGO 占位框")) {
    text = `${text}\n\n- ${drawItineraryLogoSafeArea()}`
  }
  return text
}

function buildAIItineraryMapPrompt({ title, subtitle, description, theme }) {
  const normalizedTitle = String(title || "").trim() || "定制旅行行程地图"
  const normalizedSubtitle = String(subtitle || "").trim() || "准确路线图"
  const normalizedDescription = stripCodeFence(description)
  if (isCompleteItineraryPrompt(normalizedDescription)) {
    return normalizeCompleteItineraryPrompt(normalizedDescription)
  }
  return [
    "请生成一张漫画风格的高级定制旅行行程路线图海报，不是普通导航截图，也不是纯信息表格。",
    `标题：${normalizedTitle}`,
    `副标题：${normalizedSubtitle}`,
    "",
    "客户行程原文如下，请先理解日期、城市、景区、酒店、交通和活动关系，再转化为清晰的路线地图视觉：",
    normalizedDescription,
    "",
    "画面与信息要求：",
    "- 地理正确性硬性要求：所有地点落位、东西南北关系、前后路线顺序必须以真实地图为准；不能为了画面好看而调整地点相对位置，也不要把城市、景区顺序画反。",
    "- 对任何目的地都要先按真实世界地图理解相对位置：城市、国家/地区边界、山脉、湖泊、海岸线、岛屿、沙漠、峡谷和主要交通走廊不能乱画。",
    ITINERARY_GEOGRAPHY_GUARD,
    "- 必须展示行程原文里的每一个日期，不要漏掉中间日期；日期必须逐日出现，像 5/18 这样的中间日期也必须单独标出；日期标签用小金色日期牌或清晰日程标签呈现。",
    "- 地点层级要有主次；酒店可作为小字备注，不要把所有酒店全文挤满画面，但不能删掉用户明确给出的核心城市、景区、日期和活动。",
    "- 每两个连续地点之间必须有路线连接，并必须标注大致距离或飞行/转场说明；若无法确定精确距离，用“约 xx km”或“飞行转场”这类合理估算，不要空着。",
    "- 自驾/包车路线用实线或柔和路线带，飞机/长距离转场用虚线或飞行弧线，避免路线互相缠绕。",
    "- 在每段连接线中间放一个很小的交通工具图标：自驾/包车用小车图标，飞机转场用飞机图标，步行/活动可用小脚印或点线；图标要小而精致，不遮挡地点和日期。",
    "- 画面需要像高级旅行定制海报，适合发给客户预览；采用水彩漫画路线图表达，地图轮廓清晰、地貌层次准确、地标小插画精致；不要像低质 PPT、不要像手机地图截图。",
    "- 漫画路线图视觉语言：柔和水彩铺底、红色粗路线、圆点站位、手写感标题、地标小插画、海/湖/山地用轻松但清晰的插画表达；但信息密度和真实地理不能下降。",
    `- 视觉风格：${theme || itineraryThemePrompt()}`,
    `- ${drawItineraryLogoSafeArea()}`,
    "- 不要出现 OpenAI、API、debug、水印、二维码、虚构品牌 LOGO。",
  ].join("\n")
}

function parseItineraryCoordinateStops(description) {
  const rows = String(description || "").split(/\r?\n/)
  const stops = []
  const coordinateLine = /^\s*@坐标[:：]\s*(.+?)\s*[,，]\s*(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)(?:\s*[,，]\s*(.*))?\s*$/
  for (const row of rows) {
    const match = row.match(coordinateLine)
    if (!match) {
      continue
    }
    let [, name, latText, lngText, tail] = match
    let date = ""
    const datedName = name.match(/^\s*((?:D\d+)|(?:\d{1,2}[/.月-]\d{1,2}))\s*[,，]\s*(.+)$/)
    if (datedName) {
      date = datedName[1]
      name = datedName[2]
    }
    const lat = Number(latText)
    const lng = Number(lngText)
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      continue
    }
    stops.push({
      date,
      name: name.trim(),
      lat,
      lng,
      transport: tail?.trim() || "",
    })
  }
  return stops
}

function isItineraryInstructionSection(row) {
  return /^(地点与地理校验|地理校验|画面要求|程序坐标|行程基础信息|客户偏好|地图标题建议)[:：]?/.test(row)
}

function isItineraryInstructionRow(row) {
  return /^(必须|不要|请|如果|每两个|每段|左上角|日期必须|风格|画面|程序|地图准确性|交通工具)/.test(
    row.replace(/^[-*]\s*/, ""),
  )
}

function cleanItineraryStopName(value) {
  return String(value || "")
    .replace(/入住[:：]?.*$/, "")
    .replace(/交通[:：]?.*$/, "")
    .replace(/当天重点[:：]?.*$/, "")
    .replace(/重点[:：]?.*$/, "")
    .replace(/活动[:：]?.*$/, "")
    .replace(/酒店[:：]?.*$/, "")
    .replace(/^[-*]\s*/, "")
    .trim()
}

function parseItineraryTextStops(description) {
  const stops = []
  let previousKey = ""
  let inDailySection = false
  for (const rawRow of String(description || "").split(/\r?\n/)) {
    const row = rawRow.trim()
    if (!row || row.startsWith("@坐标")) {
      continue
    }
    if (/^逐日行程[:：]?$/.test(row)) {
      inDailySection = true
      continue
    }
    if (isItineraryInstructionSection(row)) {
      if (inDailySection) {
        break
      }
      continue
    }
    const hasDate = /(?:^|[：:\s])((?:D\d+)|(?:\d{1,2}[/.月-]\d{1,2})|(?:\d{1,2}月\d{1,2}?日?))/.test(row)
    if (!inDailySection && !hasDate) {
      continue
    }
    if (isItineraryInstructionRow(row)) {
      continue
    }
    const dateMatch = row.match(/(?:D\d+)|(?:\d{1,2}\s*[/.月-]\s*\d{1,2}\s*日?)|(?:\d{1,2}\s*月)/)
    const date = dateMatch ? dateMatch[0].replace(/\s+/g, "") : ""
    const withoutNotes = row
      .replace(/（[^）]*）/g, "")
      .replace(/\([^)]*\)/g, "")
      // A hyphen between two CJK characters is a route arrow ("巴黎-里昂"); leave
      // hyphenated Latin names ("Aix-en-Provence") intact.
      .replace(/([一-鿿])\s*[-—]\s*([一-鿿])/g, "$1→$2")
    // Pick the ；-segment that actually contains a route ("交通：火车；巴黎 → 里昂"),
    // not blindly the first segment.
    const routeSeparator = /→|->|—|，|,|、|到|前往/
    const segments = withoutNotes.split(/[；;]/)
    let routePart = segments.find((seg) => routeSeparator.test(seg)) || segments[0] || ""
    // Strip a leading note label ("交通：…"), then the date token and any arrival verb
    // glued to the first city ("5/12 抵达东京" → "东京", "D1：前往巴黎" → "巴黎").
    routePart = routePart.replace(/^[^：:]{0,12}[：:]/, "")
    if (date && dateMatch) {
      routePart = routePart.replace(dateMatch[0], " ")
    }
    routePart = routePart
      .replace(/^[\s　·.、,，-]+/, "")
      .replace(/^(?:抵达|到达|出发|前往|返回|入住|游览|游玩|打卡)\s*/, "")
    const names = routePart
      .split(/→|->|—|，|,|、|到|前往|\s+-\s+/)
      .map((item) => item.trim().replace(/(?:出发|启程|返程|出行)$/, "").trim())
      .filter(Boolean)
      .map(cleanItineraryStopName)
      .filter((item) => item.length >= 2 && item.length <= 80 && !isItineraryInstructionRow(item))
    for (const name of names) {
      const key = name.toLocaleLowerCase()
      // Collapse only consecutive repeats (including the row-boundary case where a
      // day ends and the next begins at the same city). A city that recurs later —
      // e.g. a return leg back to the start — must still be drawn as its own stop.
      if (key === previousKey) {
        continue
      }
      previousKey = key
      stops.push({ date, name, transport: "" })
    }
  }
  return stops.slice(0, 80)
}

function itineraryCoordinateHelpText() {
  return [
    "系统没能确认部分地点的位置，请把地点写得更完整。",
    "建议补充城市/国家/景区全称，例如“巴黎 卢浮宫”“日本 东京站”“西班牙 巴塞罗那”。",
    "如果是小众民宿或非标准地点，请在行程里写出它所在的城市或区域。",
  ].join("\n")
}

async function submitAIItineraryMap() {
  if (state.isBusy) {
    return
  }
  try {
    resetDebugLog("点击行程路线：程序生成")
    const startedAt = performance.now()
    const title = refs.itineraryTitleInput?.value.trim() || "定制旅行行程地图"
    const subtitle = refs.itinerarySubtitleInput?.value.trim() || ""
    let description = refs.itineraryDescriptionInput?.value.trim() || ""
    const logoRequested = refs.itineraryLogoEnabled?.checked !== false

    if (!subtitle) {
      setError("请填写副标题日期，例如：5/12 - 5/24。")
      refs.itinerarySubtitleInput?.focus()
      return
    }

    if (!description) {
      setError("行程描述不能为空。")
      refs.itineraryDescriptionInput?.focus()
      return
    }

    let size
    try {
      size = parseItinerarySize()
    } catch (error) {
      appendDebugLine("参数校验失败：行程地图参数无效", { error: error.message })
      setError(error.message, error.details)
      return
    }

    const confirmedText = await confirmPromptBeforeRun("itinerary", description)
    if (confirmedText === null) {
      appendDebugLine("用户取消路线图提示词确认")
      return
    }
    description = confirmedText
    if (refs.itineraryDescriptionInput) {
      refs.itineraryDescriptionInput.value = confirmedText
    }

    // 站点解析必须在 setBusy/previewPendingResult 之前：一旦占位面板把
    // 当前结果清掉，这里 return 会让面板永远停在"等待上游返回"。
    const coordinateStops = parseItineraryCoordinateStops(description)
    const routeStops = coordinateStops.length ? coordinateStops : parseItineraryTextStops(description)
    if (!routeStops.length) {
      setError(itineraryCoordinateHelpText())
      refs.itineraryDescriptionInput?.focus()
      return
    }

    const requestSnapshot = currentFormSnapshot()
    saveSettings()
    setError("")
    closePreview()
    setBusy(true, "行程路线生成中", {
      progressLabel: "准备准确路线图",
      expectedCount: 1,
      estimatedSecondsPerImage: 8,
    })
    previewPendingResult({
      mode: "itinerary",
      prompt: description,
      model: "responses-itinerary-artwork",
      size,
    })
    const settings = getSettings()
    const itineraryModel = settings.responsesModel || state.serverConfig?.default_responses_model || "gpt-5.5"
    const result = await postJSON("api/itinerary-map/render", {
      title,
      subtitle,
      route_style: refs.itineraryThemeSelect?.value || "comic",
      stops: routeStops,
      size,
      api_key: settings.apiKey,
      endpoint_url: settings.responsesUrl,
      model: itineraryModel,
      generate_background: true,
      logo_requested: logoRequested,
    }, {
      mode: "itinerary",
      progressLabel: coordinateStops.length ? "生成一体化路线图" : "查询坐标并生成路线图",
      waitingLabel: "生成准确路线图",
    })
    const finalSize = result.size || size
    await setResult({
      ...result,
      mode: "itinerary",
      prompt: title,
      requested_size: result.requested_size || size,
      size: finalSize,
      logo_requested: logoRequested,
    }, performance.now() - startedAt)
    rememberRegenerationRequest("itinerary", requestSnapshot)
    pushHistory({
      mode: "itinerary",
      prompt: title,
      itineraryTitle: title,
      itinerarySubtitle: subtitle,
      itineraryDescription: description,
      itineraryTheme: refs.itineraryThemeSelect?.value || "comic",
      logoRequested,
      size: finalSize,
      requestedSize: result.requested_size || size,
      model: "responses-itinerary-artwork",
      image: result.saved_image_url || result.image_data_url || "",
      savedImageUrl: result.saved_image_url || "",
      generatedImageId: result.generated_image_id || null,
      createdAt: new Date().toISOString(),
    })
    await refreshGallery()
    await refreshGenerationJobs()
    document.querySelector("#resultPanel")?.scrollIntoView({ behavior: "smooth", block: "start" })
  } catch (error) {
    appendDebugLine("行程路线生成失败", { error: error.message })
    if (error.code === "itinerary_coordinates_required") {
      setError(itineraryCoordinateHelpText(), error.details)
    } else {
    if (error.cancelled && restorePendingResultAfterCancellation()) {
      setStatusMessage("已中断行程路线生成，上一张结果已保留。")
    } else {
      setError(error.cancelled ? "已中断行程路线生成，可以修改行程后重新提交。" : error.message, error.details)
    }
    }
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

function resetItineraryMapExample() {
  if (refs.itineraryTitleInput) {
    refs.itineraryTitleInput.value = SANITIZED_ITINERARY_EXAMPLE_TITLE
  }
  if (refs.itinerarySubtitleInput) {
    refs.itinerarySubtitleInput.value = SANITIZED_ITINERARY_EXAMPLE_SUBTITLE
  }
  if (refs.itineraryDescriptionInput) {
    refs.itineraryDescriptionInput.value = AI_ITINERARY_EXAMPLE
  }
  scheduleWorkspacePersist()
}

async function copyDetailedItineraryTemplate() {
  try {
    await navigator.clipboard.writeText(DETAILED_ITINERARY_TEMPLATE)
  } catch {
    setError("浏览器不允许复制到剪贴板。")
    return
  }
  setStatusMessage("精细行程模板已复制。")
}

function applyDetailedItineraryTemplate() {
  if (refs.itineraryDescriptionInput) {
    refs.itineraryDescriptionInput.value = DETAILED_ITINERARY_TEMPLATE
    refs.itineraryDescriptionInput.focus()
  }
  if (refs.itineraryTitleInput && !refs.itineraryTitleInput.value.trim()) {
    refs.itineraryTitleInput.value = DEFAULT_ITINERARY_TITLE
  }
  if (refs.itinerarySubtitleInput && !refs.itinerarySubtitleInput.value.trim()) {
    refs.itinerarySubtitleInput.value = DEFAULT_ITINERARY_SUBTITLE
  }
  scheduleWorkspacePersist()
  setStatusMessage("已套用精细行程模板。")
}

function serverShareableImageUrl(candidate = {}) {
  const candidates = [
    candidate.saved_image_url,
    state.lastResultImage?.savedUrl,
    state.lastResultImage?.fileUrl,
    state.resultPreview?.src,
  ]
  return candidates.find((value) => value && !String(value).startsWith("data:")) || ""
}

async function saveCurrentResultToGroupAssets() {
  const generatedImageId = selectedGeneratedImageId()
  if (!generatedImageId) {
    setStatusMessage("这张图还没有服务端记录，暂时不能存入部门群。")
    return
  }
  if (refs.saveGroupAssetButton) {
    refs.saveGroupAssetButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON("/api/team-chat/group-assets", {
      method: "POST",
      body: JSON.stringify({
        generated_image_id: generatedImageId,
        title: state.lastResultPrompt ? state.lastResultPrompt.slice(0, 80) : "优秀作品",
        note: "用户手动存入部门群优秀资产",
      }),
    })
    if (!response.ok) {
      setStatusMessage(data.error || "存入部门群失败。")
      return
    }
    setStatusMessage("已存入部门群优秀资产。")
    await Promise.all([refreshTeamChatGroupContext(), refreshAdminOrgContext()])
  } catch {
    setStatusMessage("存入部门群失败。")
  } finally {
    if (refs.saveGroupAssetButton) {
      refs.saveGroupAssetButton.disabled = !selectedGeneratedImageId()
    }
  }
}

function setFeedbackStatus(text) {
  if (refs.feedbackStatus) {
    refs.feedbackStatus.textContent = text
  }
}

function buildSharePayload() {
  const candidate = state.resultCandidates[state.selectedCandidateIndex] || {}
  return {
    recipient_ids: Array.from(state.shareSelectedRecipientIds).map((value) => Number(value)).filter(Boolean),
    prompt: state.lastResultPrompt || "",
    mode: state.lastResultMode || "",
    model: state.lastResultModel || "",
    rating: state.lastFeedbackRating || "",
    generated_image_id: candidate.generated_image_id || state.lastResultImage?.generatedImageId || null,
    saved_image_path: candidate.saved_image_path || state.lastResultImage?.savedPath || "",
    saved_image_url: serverShareableImageUrl(candidate),
    note: refs.shareResultNoteInput?.value.trim() || "",
  }
}

function setShareStatus(text) {
  if (refs.shareResultStatus) {
    refs.shareResultStatus.textContent = text
  }
}

function filteredShareRecipients() {
  const query = refs.shareRecipientSearchInput?.value.trim().toLowerCase() || ""
  if (!query) {
    return state.shareRecipients
  }
  return state.shareRecipients.filter((user) => String(user.username || "").toLowerCase().includes(query))
}

function renderShareRecipientOptions() {
  if (!refs.shareRecipientsList) {
    return
  }
  refs.shareRecipientsList.replaceChildren()
  const users = filteredShareRecipients()
  if (!state.shareRecipients.length) {
    const empty = document.createElement("p")
    empty.className = "admin-empty"
    empty.textContent = "暂无可分享用户。"
    refs.shareRecipientsList.appendChild(empty)
    setShareStatus("暂无接收人")
    return
  }
  if (!users.length) {
    const empty = document.createElement("p")
    empty.className = "admin-empty"
    empty.textContent = "没有匹配的用户。"
    refs.shareRecipientsList.appendChild(empty)
    setShareStatus("未找到")
    return
  }
  users.forEach((user) => {
    const userId = Number(user.id || 0)
    const label = document.createElement("label")
    label.className = "share-recipient-option"
    const input = document.createElement("input")
    input.type = "checkbox"
    input.value = String(userId)
    input.checked = state.shareSelectedRecipientIds.has(userId)
    input.addEventListener("change", () => {
      if (input.checked) {
        state.shareSelectedRecipientIds.add(userId)
      } else {
        state.shareSelectedRecipientIds.delete(userId)
      }
      setShareStatus(state.shareSelectedRecipientIds.size ? `已选 ${state.shareSelectedRecipientIds.size} 人` : "选择接收人")
    })
    const name = document.createElement("span")
    name.textContent = user.username || ""
    label.append(input, name)
    refs.shareRecipientsList.appendChild(label)
  })
  setShareStatus(state.shareSelectedRecipientIds.size ? `已选 ${state.shareSelectedRecipientIds.size} 人` : "选择接收人")
}

function renderShareRecipients(users) {
  state.shareRecipients = Array.isArray(users) ? users : []
  renderShareRecipientOptions()
}

async function refreshShareRecipients() {
  if (!state.currentUser || !refs.shareRecipientsList) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/users", { cache: "no-store" })
    if (response.ok) {
      renderShareRecipients(data.users)
      return
    }
  } catch {
    // fall through to local status
  }
  refs.shareRecipientsList.innerHTML = '<p class="admin-empty">用户列表暂时不可用。</p>'
  setShareStatus("读取失败")
}

function showSharePanel() {
  if (!state.resultPreview?.src) {
    return
  }
  refs.shareResultPanel?.classList.remove("hidden")
  state.shareSelectedRecipientIds = new Set()
  if (refs.shareRecipientSearchInput) {
    refs.shareRecipientSearchInput.value = ""
  }
  setShareStatus("选择接收人")
  void refreshShareRecipients()
}

async function submitShareResult() {
  if (!state.resultPreview?.src) {
    setError("当前没有可分享的结果图。")
    return
  }
  const payload = buildSharePayload()
  if (!payload.recipient_ids.length) {
    setShareStatus("请选择接收人")
    return
  }
  if (refs.submitShareResultButton) {
    refs.submitShareResultButton.disabled = true
  }
  setShareStatus("分享中")
  try {
    const { response, data } = await fetchJSON("/api/shares", {
      method: "POST",
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      setShareStatus("分享失败")
      setError(data.error || "分享失败")
      return
    }
    const count = Array.isArray(data.shares) ? data.shares.length : payload.recipient_ids.length
    setShareStatus(`已分享给 ${count} 人`)
    if (refs.shareResultNoteInput) {
      refs.shareResultNoteInput.value = ""
    }
    state.shareSelectedRecipientIds = new Set()
    renderShareRecipientOptions()
  } catch {
    setShareStatus("分享失败")
    setError("分享时网络连接错误")
  } finally {
    if (refs.submitShareResultButton) {
      refs.submitShareResultButton.disabled = false
    }
  }
}

function renderSharedResults(shares) {
  state.sharedResults = Array.isArray(shares) ? shares : []
  if (!refs.sharedResultsList || !refs.sharedResultsEmpty) {
    return
  }
  refs.sharedResultsEmpty.classList.toggle("hidden", state.sharedResults.length > 0)
  if (!state.sharedResults.length) {
    refs.sharedResultsList.innerHTML = ""
    return
  }
  refs.sharedResultsList.innerHTML = state.sharedResults.slice(0, 10).map((share) => {
    const imageUrl = share.saved_image_url || ""
    const sender = share.sender_username || "用户"
    const prompt = share.prompt || "未附提示词"
    return `
      <button class="shared-result-item" type="button" data-share-id="${Number(share.id || 0)}">
        ${imageUrl ? `<img src="${escapeHTML(imageUrl)}" alt="">` : '<span class="shared-result-thumb"></span>'}
        <span class="shared-result-copy">
          <strong>${escapeHTML(sender)}</strong>
          <span>${escapeHTML(share.mode || "生成")} · ${escapeHTML(share.model || "")}</span>
          <p>${escapeHTML(prompt)}</p>
        </span>
      </button>
    `
  }).join("")
}

async function refreshSharedResults() {
  if (!state.currentUser || !refs.sharedResultsList) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/shares/inbox", { cache: "no-store" })
    if (response.ok) {
      renderSharedResults(data.shares)
      return
    }
  } catch {
    // handled below
  }
  refs.sharedResultsList.innerHTML = '<p class="empty-history">收到分享暂时不可用。</p>'
  refs.sharedResultsEmpty?.classList.add("hidden")
}

function openSharedResult(shareId) {
  const share = state.sharedResults.find((item) => Number(item.id) === Number(shareId))
  const asset = shareToAsset(share)
  if (!share || !asset) {
    setError("这条分享没有可打开的图片。")
    return
  }
  state.resultCandidates = [{
    saved_image_url: share.saved_image_url || "",
    saved_image_path: share.saved_image_path || "",
    generated_image_id: share.generated_image_id || null,
    image_url: share.saved_image_url || "",
    asset,
  }]
  state.selectedCandidateIndex = 0
  state.lastResultPrompt = share.prompt || ""
  state.lastResultModel = share.model || ""
  state.lastResultMode = share.mode || "share"
  state.lastResultImage = cloneImageAsset(asset)
  state.resultPreview = { src: getAssetDisplaySrc(asset), mode: state.lastResultMode }
  refs.resultPreviewLabel.textContent = "收到分享"
  refs.resultImage.src = state.resultPreview.src
  refs.resultImage.classList.add("visible")
  refs.resultPreviewEmpty.classList.add("hidden")
  refs.resultPrompt.textContent = state.lastResultPrompt || "未附提示词"
  refs.resultMeta.textContent = `来自 ${share.sender_username || "用户"}`
  refs.resultTiming.textContent = ""
  refs.resultStorage.textContent = share.saved_image_path ? `已落盘到 ${share.saved_image_path}` : ""
  setDownloadAvailable(state.resultPreview.src, asset.name)
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  refs.shareResultPanel?.classList.add("hidden")
  setGalleryEditorMeta(null)
  renderResultCandidates()
  updatePreviewAvailability()
  scheduleWorkspacePersist()
  document.querySelector("#resultPanel")?.scrollIntoView({ behavior: "smooth", block: "start" })
}

function galleryItemToAsset(item) {
  if (!item?.saved_image_url) {
    return null
  }
  const metadata = item.metadata && typeof item.metadata === "object" ? item.metadata : {}
  const originalSavedUrl = item.original_saved_image_url || item.source_saved_image_url || metadata.source_saved_image_url || ""
  const originalSavedPath = item.original_saved_image_path || item.source_saved_image_path || metadata.source_saved_image_path || metadata.source_image_path || ""
  return {
    dataUrl: "",
    file: null,
    name: item.saved_image_name || `gallery-${item.id || Date.now()}.png`,
    type: item.saved_image_mime || "image/png",
    size: Number(item.saved_image_bytes || 0),
    width: item.saved_image_width || null,
    height: item.saved_image_height || null,
    savedUrl: item.saved_image_url || "",
    savedPath: item.saved_image_path || "",
    fileUrl: item.saved_image_url || "",
    src: item.saved_image_url || "",
    originalDataUrl: "",
    originalSavedUrl,
    originalFileUrl: originalSavedUrl,
    originalSavedPath,
    generatedImageId: item.generated_image_id || item.id || null,
    sourceGeneratedImageId: item.source_generated_image_id || null,
    origin: "gallery",
    description: `作品库 · ${item.username || "我的作品"}`,
    logoOverlayApplied: Boolean(item.logo_overlay_applied),
  }
}

function galleryTagsText(tags) {
  return Array.isArray(tags) ? tags.filter(Boolean).join(", ") : ""
}

function setGalleryEditorMeta(item) {
  const generatedImageId = item?.generated_image_id || item?.id || null
  const isFavorite = Boolean(item?.is_favorite)
  const tags = Array.isArray(item?.tags) ? item.tags : []
  state.currentGalleryMeta = { generatedImageId, isFavorite, tags }
  refs.galleryEditorPanel?.classList.toggle("hidden", !generatedImageId)
  if (refs.galleryFavoriteInput) {
    refs.galleryFavoriteInput.checked = isFavorite
  }
  if (refs.galleryTagsInput) {
    refs.galleryTagsInput.value = galleryTagsText(tags)
  }
  if (refs.galleryEditorStatus) {
    refs.galleryEditorStatus.textContent = isFavorite ? "已收藏" : "未收藏"
  }
}

function renderGalleryItems(items = state.galleryItems) {
  state.galleryItems = Array.isArray(items) ? items : []
  if (!refs.galleryList || !refs.galleryEmpty) {
    return
  }
  refs.galleryList.replaceChildren()
  refs.galleryEmpty.classList.toggle("hidden", state.galleryItems.length > 0)
  state.galleryItems.slice(0, 30).forEach((item) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "gallery-item"
    button.dataset.galleryId = String(item.id || item.generated_image_id || "")

    const image = document.createElement("img")
    image.alt = ""
    image.src = item.saved_image_url || ""

    const copy = document.createElement("span")
    copy.className = "gallery-item-copy"

    const top = document.createElement("span")
    top.className = "gallery-item-top"
    const title = document.createElement("strong")
    title.textContent = item.is_favorite ? "★ 收藏作品" : "作品"
    const time = document.createElement("time")
    time.textContent = formatTimestamp(item.created_at)
    top.append(title, time)

    const prompt = document.createElement("span")
    prompt.className = "gallery-item-prompt"
    prompt.textContent = item.prompt || "未记录提示词"

    const meta = document.createElement("span")
    meta.className = "gallery-item-meta"
    const metaParts = [item.mode || "生成", item.model || "", item.logo_overlay_applied ? "LOGO" : ""]
    meta.textContent = metaParts.filter(Boolean).join(" · ")

    const tags = document.createElement("span")
    tags.className = "gallery-item-tags"
    tags.textContent = galleryTagsText(item.tags)

    copy.append(top, prompt, meta)
    if (tags.textContent) {
      copy.append(tags)
    }
    button.append(image, copy)
    button.addEventListener("click", () => openGalleryItem(item.id || item.generated_image_id))
    refs.galleryList.appendChild(button)
  })
}

function toggleRailSection(sectionName, forceExpanded = null) {
  const section = document.querySelector(`[data-rail-section="${sectionName}"]`)
  const toggle = document.querySelector(`[data-rail-toggle="${sectionName}"]`)
  if (!section || !toggle) {
    return
  }
  const shouldExpand = forceExpanded === null
    ? section.classList.contains("collapsed")
    : Boolean(forceExpanded)
  section.classList.toggle("collapsed", !shouldExpand)
  toggle.setAttribute("aria-expanded", String(shouldExpand))
}

function openTeamInspirationFeed() {
  toggleRailSection("gallery", true)
  refs.teamInspirationFeed?.classList.remove("hidden")
  if (refs.galleryFavoriteOnlyInput) {
    refs.galleryFavoriteOnlyInput.checked = true
  }
  state.galleryFavoriteOnly = true
  void refreshGallery()
  refs.gallerySearchInput?.focus()
}

function initializeRailDisclosure() {
  if (!window.matchMedia("(max-width: 820px)").matches) {
    return
  }
  refs.railToggleButtons.forEach((button) => {
    toggleRailSection(button.dataset.railToggle || "", false)
  })
}

async function refreshGallery() {
  if (!state.currentUser || !refs.galleryList) {
    return
  }
  const params = new URLSearchParams()
  // 控件存在时以控件为准（包括“空”）；用 || 合并旧状态会导致清空搜索框、
  // 取消勾选收藏后旧筛选悄悄复活。
  const query = refs.gallerySearchInput ? refs.gallerySearchInput.value.trim() : state.gallerySearch || ""
  const favoriteOnly = refs.galleryFavoriteOnlyInput
    ? refs.galleryFavoriteOnlyInput.checked
    : Boolean(state.galleryFavoriteOnly)
  state.gallerySearch = query
  state.galleryFavoriteOnly = favoriteOnly
  if (query) {
    params.set("q", query)
  }
  if (favoriteOnly) {
    params.set("favorite", "1")
  }
  const url = params.toString() ? `/api/gallery?${params}` : "/api/gallery"
  try {
    const { response, data } = await fetchJSON(url, { cache: "no-store" })
    if (response.ok) {
      renderGalleryItems(data.items)
      return
    }
  } catch {
    // handled below
  }
  refs.galleryList.innerHTML = '<p class="empty-history">作品库暂时不可用。</p>'
  refs.galleryEmpty?.classList.add("hidden")
}

function jobStatusLabel(status) {
  if (status === "succeeded") return "已完成"
  if (status === "failed") return "失败"
  if (status === "started") return "生成中"
  return status || "未知"
}

function renderGenerationJobs(jobs = state.generationJobs) {
  state.generationJobs = Array.isArray(jobs) ? jobs : []
  if (!refs.jobCenterList || !refs.jobCenterEmpty) {
    return
  }
  refs.jobCenterList.replaceChildren()
  refs.jobCenterEmpty.classList.toggle("hidden", state.generationJobs.length > 0)
  state.generationJobs.slice(0, 8).forEach((job) => {
    const item = document.createElement("article")
    item.className = `job-center-item ${job.status === "failed" ? "failed" : ""}`
    const thumb = document.createElement("button")
    thumb.type = "button"
    thumb.className = "job-center-thumb"
    thumb.disabled = !job.first_generated_image_id
    if (job.first_saved_image_url) {
      const image = document.createElement("img")
      image.src = job.first_saved_image_url
      image.alt = ""
      thumb.append(image)
    } else {
      thumb.textContent = job.status === "failed" ? "!" : "…"
    }
    thumb.addEventListener("click", () => {
      if (job.first_generated_image_id) {
        void openGeneratedImageDetail(job.first_generated_image_id)
      }
    })

    const copy = document.createElement("div")
    copy.className = "job-center-copy"
    const top = document.createElement("div")
    top.className = "job-center-top"
    const status = document.createElement("strong")
    status.textContent = jobStatusLabel(job.status)
    const time = document.createElement("time")
    time.textContent = formatTimestamp(job.started_at)
    top.append(status, time)
    const prompt = document.createElement("p")
    prompt.textContent = job.original_prompt || job.prompt || "未记录提示词"
    const meta = document.createElement("span")
    const modeLabel = job.prompt_mode === "recipe" ? "配方辅助" : "精确提示词"
    meta.textContent = [
      job.mode || "生成",
      modeLabel,
      job.recipe_id || "",
      job.size || "",
      `${Number(job.image_count || 0)} 张`,
    ].filter(Boolean).join(" · ")
    copy.append(top, prompt, meta)
    if (job.error_message) {
      const error = document.createElement("small")
      error.textContent = job.error_message
      copy.append(error)
    }
    item.append(thumb, copy)
    refs.jobCenterList.append(item)
  })
}

async function refreshGenerationJobs() {
  if (!state.currentUser || !refs.jobCenterList) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/jobs?limit=20", { cache: "no-store" })
    if (response.ok) {
      renderGenerationJobs(data.jobs)
      return
    }
  } catch {
    // handled below
  }
  refs.jobCenterList.innerHTML = '<p class="empty-history">任务中心暂时不可用。</p>'
  refs.jobCenterEmpty?.classList.add("hidden")
}

async function openGeneratedImageDetail(generatedImageId) {
  if (!generatedImageId) {
    return
  }
  try {
    const { response, data } = await fetchJSON(`/api/generated-images/${encodeURIComponent(generatedImageId)}`, {
      cache: "no-store",
    })
    if (!response.ok || !data.image) {
      setError(data.error || "无法打开这张任务结果。")
      return
    }
    openGalleryLikeImage(data.image, "任务结果")
  } catch {
    setError("打开任务结果时网络连接错误。")
  }
}

function openGalleryLikeImage(item, label = "作品库") {
  const asset = galleryItemToAsset(item)
  if (!item || !asset) {
    setError("这条记录没有可打开的图片。")
    return
  }
  state.resultCandidates = [{
    saved_image_url: item.saved_image_url || "",
    saved_image_path: item.saved_image_path || "",
    saved_image_name: item.saved_image_name || asset.name,
    generated_image_id: item.generated_image_id || item.id || null,
    image_url: item.saved_image_url || "",
    logo_overlay_applied: Boolean(item.logo_overlay_applied),
    source_generated_image_id: item.source_generated_image_id || null,
    asset,
  }]
  state.selectedCandidateIndex = 0
  const lineage = item.lineage || {}
  state.lastResultPrompt = lineage.original_prompt || item.prompt || ""
  state.lastResultModel = item.model || lineage.model || ""
  state.lastResultMode = item.mode || "gallery"
  state.lastResultImage = cloneImageAsset(asset)
  state.resultPreview = { src: getAssetDisplaySrc(asset), mode: state.lastResultMode }
  refs.resultPreviewLabel.textContent = label
  refs.resultImage.src = state.resultPreview.src
  refs.resultImage.classList.add("visible")
  refs.resultPreviewEmpty.classList.add("hidden")
  refs.resultPrompt.textContent = state.lastResultPrompt || "未记录提示词"
  const promptMode = lineage.prompt_mode === "recipe" ? "配方辅助" : ""
  refs.resultMeta.textContent = [item.mode || "生成", item.model || "", promptMode, item.username || ""].filter(Boolean).join(" · ")
  refs.resultTiming.textContent = lineage.elapsed_ms ? `${(Number(lineage.elapsed_ms) / 1000).toFixed(1)}s` : ""
  refs.resultStorage.textContent = item.saved_image_path ? `已落盘到 ${item.saved_image_path}` : ""
  setDownloadAvailable(state.resultPreview.src, asset.name)
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  refs.shareResultPanel?.classList.add("hidden")
  setGalleryEditorMeta(item)
  renderResultCandidates()
  updateFeedbackPanelVisibility()
  updatePreviewAvailability()
  scheduleWorkspacePersist()
  document.querySelector("#resultPanel")?.scrollIntoView({ behavior: "smooth", block: "start" })
}

function openGalleryItem(galleryId) {
  const item = state.galleryItems.find((entry) => Number(entry.id || entry.generated_image_id) === Number(galleryId))
  openGalleryLikeImage(item, "作品库")
}

function imageVersionLabel(item, index) {
  if (!item.source_generated_image_id) {
    return "原始版本"
  }
  if (item.logo_overlay_applied) {
    return "LOGO 成品"
  }
  if (item.mode === "variant") {
    return `延展版本 ${index + 1}`
  }
  if (item.mode === "edit") {
    return `编辑版本 ${index + 1}`
  }
  return `版本 ${index + 1}`
}

function renderImageVersions(versions = [], currentGeneratedImageId = selectedGeneratedImageId()) {
  if (!refs.versionHistoryPanel || !refs.versionHistoryList) {
    return
  }
  refs.versionHistoryList.replaceChildren()
  refs.versionHistoryPanel.classList.toggle("hidden", versions.length === 0)
  if (refs.versionHistoryStatus) {
    refs.versionHistoryStatus.textContent = versions.length > 1 ? `${versions.length} 个版本` : "暂无可回退版本"
  }
  versions.forEach((item, index) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "version-history-item"
    button.classList.toggle(
      "active",
      Number(item.generated_image_id || item.id) === Number(currentGeneratedImageId),
    )

    const image = document.createElement("img")
    image.src = item.saved_image_url || ""
    image.alt = imageVersionLabel(item, index)

    const copy = document.createElement("span")
    copy.className = "version-history-copy"

    const title = document.createElement("strong")
    title.textContent = imageVersionLabel(item, index)

    const meta = document.createElement("span")
    meta.textContent = [
      formatTimestamp(item.created_at),
      item.mode || "",
      item.logo_overlay_applied ? "已集成 LOGO" : "",
    ].filter(Boolean).join(" · ")

    const prompt = document.createElement("span")
    prompt.textContent = item.lineage?.original_prompt || item.prompt || "未记录提示词"

    copy.append(title, meta, prompt)
    button.append(image, copy)
    button.addEventListener("click", () => {
      openGalleryLikeImage(item, "版本记录")
      refs.versionHistoryPanel?.classList.add("hidden")
      setStatusMessage("已找回所选图片版本，可继续编辑或下载。")
    })
    refs.versionHistoryList.appendChild(button)
  })
}

async function showImageVersions() {
  const generatedImageId = selectedGeneratedImageId()
  if (!generatedImageId) {
    setStatusMessage("当前图片还没有服务端版本记录。")
    return
  }
  if (refs.showVersionsButton) {
    refs.showVersionsButton.disabled = true
  }
  if (refs.versionHistoryStatus) {
    refs.versionHistoryStatus.textContent = "读取版本中"
  }
  refs.versionHistoryPanel?.classList.remove("hidden")
  try {
    const { response, data } = await fetchJSON(
      `/api/generated-images/${encodeURIComponent(generatedImageId)}/versions`,
      { method: "GET" },
    )
    if (!response.ok) {
      setStatusMessage(data.error || "版本记录暂时不可用。")
      refs.versionHistoryPanel?.classList.add("hidden")
      return
    }
    renderImageVersions(Array.isArray(data.versions) ? data.versions : [], generatedImageId)
  } catch {
    setStatusMessage("版本记录读取失败。")
    refs.versionHistoryPanel?.classList.add("hidden")
  } finally {
    if (refs.showVersionsButton) {
      refs.showVersionsButton.disabled = !selectedGeneratedImageId()
    }
  }
}

function parseGalleryTagsInput() {
  const raw = refs.galleryTagsInput?.value || ""
  return raw
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
}

async function saveGalleryMeta() {
  const generatedImageId = state.currentGalleryMeta.generatedImageId
  if (!generatedImageId) {
    setStatusMessage("请先打开一张自己的作品。")
    return
  }
  const payload = {
    is_favorite: Boolean(refs.galleryFavoriteInput?.checked),
    tags: parseGalleryTagsInput(),
  }
  if (refs.saveGalleryMetaButton) {
    refs.saveGalleryMetaButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON(`/api/gallery/${generatedImageId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      setError(data.error || "作品整理保存失败")
      return
    }
    setGalleryEditorMeta(data.item)
    state.galleryItems = state.galleryItems.map((item) => (
      Number(item.id || item.generated_image_id) === Number(generatedImageId) ? data.item : item
    ))
    renderGalleryItems()
    setStatusMessage("作品整理已保存。")
  } catch {
    setError("作品整理保存时网络连接错误")
  } finally {
    if (refs.saveGalleryMetaButton) {
      refs.saveGalleryMetaButton.disabled = false
    }
  }
}

function openBugReportModal() {
  refs.bugReportModal?.classList.remove("hidden")
  refs.bugReportModal?.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
  if (refs.bugReportStatus) {
    refs.bugReportStatus.textContent = ""
  }
  window.setTimeout(() => refs.bugReportDescriptionInput?.focus(), 0)
}

function closeBugReportModal() {
  refs.bugReportModal?.classList.add("hidden")
  refs.bugReportModal?.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open")
}

function openChangePasswordModal() {
  refs.changePasswordModal?.classList.remove("hidden")
  refs.changePasswordModal?.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
  refs.changePasswordForm?.reset()
  if (refs.changePasswordStatus) {
    refs.changePasswordStatus.textContent = ""
    refs.changePasswordStatus.classList.remove("is-error")
  }
  window.setTimeout(() => refs.currentPasswordInput?.focus(), 0)
}

function closeChangePasswordModal() {
  refs.changePasswordModal?.classList.add("hidden")
  refs.changePasswordModal?.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open")
}

function fillProfileForm() {
  const user = state.currentUser || {}
  renderOrgUnitControls()
  if (refs.profileUsernameInput) {
    refs.profileUsernameInput.value = user.username || ""
  }
  if (refs.profileDisplayNameInput) {
    refs.profileDisplayNameInput.value = user.display_name || ""
  }
  if (refs.profileWechatInput) {
    refs.profileWechatInput.value = user.wechat || ""
  }
  if (refs.profileEmailInput) {
    refs.profileEmailInput.value = user.email || ""
  }
  if (refs.profilePhoneCountryCodeInput) {
    refs.profilePhoneCountryCodeInput.value = user.phone_country_code || "+86"
  }
  if (refs.profilePhoneInput) {
    refs.profilePhoneInput.value = user.phone || ""
  }
  if (refs.profileCompanyInput) {
    refs.profileCompanyInput.value = user.company || "6renyou"
  }
  renderDepartmentSelect(refs.profileDepartmentInput, state.orgUnits, refs.profileCompanyInput?.value || "6renyou")
  if (refs.profileDepartmentInput) {
    refs.profileDepartmentInput.value = user.department || "PD & OPS"
  }
  if (refs.profileTeamInput) {
    refs.profileTeamInput.value = user.team || ""
  }
  if (refs.profileJobTitleInput) {
    refs.profileJobTitleInput.value = user.job_title || ""
  }
  if (refs.profileNoteInput) {
    refs.profileNoteInput.value = user.note || ""
  }
  if (refs.profileCurrentPasswordInput) {
    refs.profileCurrentPasswordInput.value = ""
  }
  renderAvatarElement(refs.profileAvatarPreview, user, "profile-avatar-image")
  updateProfileUsernamePasswordHint()
}

function updateProfileUsernamePasswordHint() {
  const currentUsername = state.currentUser?.username || ""
  const nextUsername = refs.profileUsernameInput?.value.trim() || ""
  const changed = Boolean(nextUsername && currentUsername && nextUsername !== currentUsername)
  refs.profileCurrentPasswordLabel?.classList.toggle("hidden", !changed)
  if (!changed && refs.profileCurrentPasswordInput) {
    refs.profileCurrentPasswordInput.value = ""
  }
}

function openProfileModal() {
  if (!state.currentUser) {
    return
  }
  refs.profileModal?.classList.remove("hidden")
  refs.profileModal?.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
  fillProfileForm()
  if (refs.profileStatus) {
    refs.profileStatus.textContent = ""
    refs.profileStatus.classList.remove("is-error")
  }
  window.setTimeout(() => refs.profileDisplayNameInput?.focus(), 0)
}

function closeProfileModal() {
  refs.profileModal?.classList.add("hidden")
  refs.profileModal?.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open")
}

async function submitProfile(event) {
  event.preventDefault()
  const username = refs.profileUsernameInput?.value.trim() || ""
  const currentPassword = refs.profileCurrentPasswordInput?.value || ""
  if (!username) {
    refs.profileStatus.textContent = "请填写登录用户名。"
    refs.profileStatus.classList.add("is-error")
    return
  }
  if ((state.currentUser?.username || "") !== username && !currentPassword) {
    refs.profileStatus.textContent = "修改登录用户名需要填写当前密码。"
    refs.profileStatus.classList.add("is-error")
    return
  }
  if (refs.submitProfileButton) {
    refs.submitProfileButton.disabled = true
  }
  refs.profileStatus.textContent = "保存中"
  refs.profileStatus.classList.remove("is-error")
  try {
    const { response, data } = await fetchJSON("/api/me/profile", {
      method: "PUT",
      body: JSON.stringify({
        username,
        current_password: currentPassword,
        display_name: refs.profileDisplayNameInput?.value.trim() || "",
        wechat: refs.profileWechatInput?.value.trim() || "",
        email: refs.profileEmailInput?.value.trim() || "",
        phone_country_code: refs.profilePhoneCountryCodeInput?.value || "+86",
        phone: refs.profilePhoneInput?.value.trim() || "",
        company: refs.profileCompanyInput?.value || "6renyou",
        department: refs.profileDepartmentInput?.value || "PD & OPS",
        team: refs.profileTeamInput?.value.trim() || "",
        job_title: refs.profileJobTitleInput?.value.trim() || "",
        note: refs.profileNoteInput?.value.trim() || "",
      }),
    })
    if (!response.ok) {
      refs.profileStatus.textContent = data.error || "资料保存失败"
      refs.profileStatus.classList.add("is-error")
      return
    }
    setCurrentUser(data.user || state.currentUser)
    fillProfileForm()
    refs.profileStatus.textContent = "资料已保存。"
    refs.profileStatus.classList.remove("is-error")
    setStatusMessage("个人资料已保存。")
  } catch {
    refs.profileStatus.textContent = "网络连接错误"
    refs.profileStatus.classList.add("is-error")
  } finally {
    if (refs.submitProfileButton) {
      refs.submitProfileButton.disabled = false
    }
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ""))
    reader.onerror = () => reject(reader.error || new Error("读取文件失败"))
    reader.readAsDataURL(file)
  })
}

async function uploadProfileAvatar() {
  const file = refs.profileAvatarInput?.files?.[0]
  if (!file) {
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    refs.profileStatus.textContent = "头像文件不能超过 2 MB。"
    refs.profileStatus.classList.add("is-error")
    refs.profileAvatarInput.value = ""
    return
  }
  refs.profileStatus.textContent = "上传头像中"
  refs.profileStatus.classList.remove("is-error")
  try {
    const dataUrl = await readFileAsDataUrl(file)
    const { response, data } = await fetchJSON("/api/me/avatar", {
      method: "POST",
      body: JSON.stringify({
        image: {
          name: file.name,
          type: file.type,
          data_url: dataUrl,
        },
      }),
    })
    if (!response.ok) {
      refs.profileStatus.textContent = data.error || "头像上传失败"
      refs.profileStatus.classList.add("is-error")
      return
    }
    setCurrentUser(data.user || state.currentUser)
    renderAvatarElement(refs.profileAvatarPreview, state.currentUser, "profile-avatar-image")
    refs.profileStatus.textContent = "头像已更新。"
    refs.profileStatus.classList.remove("is-error")
  } catch {
    refs.profileStatus.textContent = "头像上传失败"
    refs.profileStatus.classList.add("is-error")
  } finally {
    refs.profileAvatarInput.value = ""
  }
}

function teamChatRoomParams(room = state.teamChatRoom) {
  const params = new URLSearchParams({ room_type: room.type || "team" })
  if (room.recipientUserId) {
    params.set("recipient_user_id", String(room.recipientUserId))
  }
  return params
}

function teamChatReadPayload(room = state.teamChatRoom, messageId = state.teamChatLastMessageId) {
  return {
    room_type: room.type || "team",
    recipient_user_id: room.recipientUserId || null,
    message_id: Number(messageId || 0),
  }
}

function teamChatSendPayload(content) {
  return {
    room_type: state.teamChatRoom.type || "team",
    recipient_user_id: state.teamChatRoom.recipientUserId || null,
    content,
  }
}

function teamChatDisplayName(member) {
  return member?.display_name || member?.username || "用户"
}

function teamChatAvatarLabel(member) {
  return teamChatDisplayName(member).slice(0, 1).toUpperCase() || "?"
}

function normalizeTeamChatGroup(group = {}) {
  const company = group.company || "6renyou"
  const department = group.department || "PD & OPS"
  return {
    company,
    department,
    roomKey: group.room_key || "",
    title: group.title || department || "部门群",
    subtitle: group.subtitle || `${company} · 部门群`,
    memberCount: Number(group.member_count || 0),
  }
}

function teamChatGroupDisplayTitle() {
  return state.teamChatGroup.title || state.teamChatGroup.department || "部门群"
}

function teamChatGroupDisplayMeta() {
  const count = Number(state.teamChatGroup.memberCount || state.teamChatHumanMembers.length || 0)
  const base = state.teamChatGroup.subtitle || `${state.teamChatGroup.company || "6renyou"} · 部门群`
  return count > 0 ? `${base} · ${count} 位成员` : base
}

function teamChatBotMember() {
  return state.teamChatBot || state.teamChatMembers.find((member) => member.type === "bot") || {
    id: "gpt-bot",
    type: "bot",
    username: "GPT-BOT",
    display_name: "GPT-BOT",
    avatar_url: "",
  }
}

function findTeamChatHumanMember(userId) {
  const targetId = Number(userId || 0)
  return state.teamChatHumanMembers.find((member) => Number(member.id || 0) === targetId) || null
}

function hydrateTeamChatRecentDmsFromMembers() {
  if (!state.teamChatRecentDms.length) {
    return
  }
  state.teamChatRecentDms = state.teamChatRecentDms.map((item) => findTeamChatHumanMember(item.id) || item)
}

function normalizeTeamChatRecentDm(member) {
  if (!member || member.type === "bot") {
    return null
  }
  const id = Number(member.id || 0)
  if (!id) {
    return null
  }
  return {
    id,
    type: "user",
    username: String(member.username || ""),
    display_name: String(member.display_name || ""),
    avatar_url: String(member.avatar_url || ""),
  }
}

function loadTeamChatRecentDms() {
  const rows = loadJSON(teamChatRecentDmStorageKey(), [])
  state.teamChatRecentDms = Array.isArray(rows)
    ? rows.map(normalizeTeamChatRecentDm).filter(Boolean).slice(0, TEAM_CHAT_MAX_RECENT_DMS)
    : []
}

function saveTeamChatRecentDms() {
  saveJSON(teamChatRecentDmStorageKey(), state.teamChatRecentDms.slice(0, TEAM_CHAT_MAX_RECENT_DMS))
}

function rememberTeamChatRecentDm(member, { persist = true } = {}) {
  const normalized = normalizeTeamChatRecentDm(member)
  if (!normalized) {
    return
  }
  state.teamChatRecentDms = [
    normalized,
    ...state.teamChatRecentDms.filter((item) => Number(item.id || 0) !== normalized.id),
  ].slice(0, TEAM_CHAT_MAX_RECENT_DMS)
  if (persist) {
    saveTeamChatRecentDms()
  }
}

function updateTeamChatUnreadBadge(total = state.teamChatUnreadTotal) {
  state.teamChatUnreadTotal = Number(total || 0)
  const hasUnread = state.teamChatUnreadTotal > 0
  refs.teamChatButton?.classList.toggle("has-unread", hasUnread)
  refs.teamChatUnreadBadge?.classList.toggle("hidden", !hasUnread)
  if (refs.teamChatUnreadBadge) {
    refs.teamChatUnreadBadge.textContent = String(Math.min(state.teamChatUnreadTotal, 99))
  }
}

function resetTeamChatState() {
  stopTeamChatPolling()
  state.teamChatMembers = []
  state.teamChatHumanMembers = []
  state.teamChatBot = null
  state.teamChatMessages = []
  state.teamChatRoom = {
    type: "team",
    recipientUserId: null,
    title: "部门群",
    meta: "部门群",
  }
  state.teamChatLastMessageId = 0
  clearTeamChatQuote()
  state.teamChatOpenMenuId = null
  updateTeamChatUnreadBadge(0)
  refs.teamChatModal?.classList.add("hidden")
  refs.teamChatModal?.setAttribute("aria-hidden", "true")
  document.body.classList.remove("chat-open")
}

function renderTeamChatMemberAvatar(container, member) {
  container.replaceChildren()
  if (member?.avatar_url) {
    const image = document.createElement("img")
    image.src = member.avatar_url
    image.alt = ""
    container.append(image)
    return
  }
  container.textContent = teamChatAvatarLabel(member)
}

function renderTeamChatMembers() {
  if (!refs.teamChatMembers) {
    return
  }
  if (refs.teamChatTeamRoomName) {
    refs.teamChatTeamRoomName.textContent = teamChatGroupDisplayTitle()
  }
  if (refs.teamChatTeamRoomMeta) {
    refs.teamChatTeamRoomMeta.textContent = teamChatGroupDisplayMeta()
  }
  refs.teamChatTeamRoomButton?.classList.toggle("active", state.teamChatRoom.type === "team")
  refs.teamChatMembers.replaceChildren()
  const bot = teamChatBotMember()
  const directMember = state.teamChatRoom.type === "dm" ? findTeamChatHumanMember(state.teamChatRoom.recipientUserId) : null
  const recentDms = [...state.teamChatRecentDms]
  if (directMember && !recentDms.some((member) => Number(member.id || 0) === Number(directMember.id || 0))) {
    recentDms.unshift(directMember)
  }
  const conversations = [bot, ...recentDms]
  conversations.forEach((member, index) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "team-chat-member"
    const isBot = member.type === "bot"
    if (!isBot && index > 0) {
      const hasRecentLabel = refs.teamChatMembers.querySelector(".team-chat-recent-dm-label")
      if (!hasRecentLabel) {
        const label = document.createElement("p")
        label.className = "team-chat-conversation-label team-chat-current-dm-label team-chat-recent-dm-label"
        label.textContent = "最近私聊"
        refs.teamChatMembers.append(label)
      }
    }
    const memberId = isBot ? "gpt-bot" : Number(member.id || 0)
    const active = isBot
      ? state.teamChatRoom.type === "bot"
      : state.teamChatRoom.type === "dm" && Number(state.teamChatRoom.recipientUserId) === memberId
    button.classList.toggle("active", active)
    button.classList.toggle("team-chat-current-dm", Boolean(!isBot && active))
    button.dataset.memberType = member.type || "user"
    button.dataset.memberId = String(memberId)
    const avatar = document.createElement("span")
    avatar.className = isBot ? "team-chat-avatar bot" : "team-chat-avatar"
    renderTeamChatMemberAvatar(avatar, member)
    const copy = document.createElement("span")
    const name = document.createElement("strong")
    name.textContent = teamChatDisplayName(member)
    const subtitle = document.createElement("small")
    subtitle.textContent = isBot ? "AI Chat" : `私聊 @${member.username || ""}`
    copy.append(name, subtitle)
    button.append(avatar, copy)
    button.addEventListener("click", () => {
      if (isBot) {
        void switchTeamChatRoom({ type: "bot", recipientUserId: null, title: "GPT-BOT", meta: "AI 创意与图片质量助手。" })
        return
      }
      void switchTeamChatDirectMember(member)
    })
    refs.teamChatMembers.append(button)
  })
}

function renderTeamChatGroupMembers() {
  if (!refs.teamChatGroupMembers) {
    return
  }
  const members = state.teamChatHumanMembers
  refs.teamChatGroupMembers.replaceChildren()
  if (refs.teamChatGroupMemberCount) {
    refs.teamChatGroupMemberCount.textContent = members.length ? `${members.length} 位` : "暂无成员"
  }
  if (!members.length) {
    const empty = document.createElement("p")
    empty.className = "team-chat-empty"
    empty.textContent = "当前部门暂时没有其他成员。"
    refs.teamChatGroupMembers.append(empty)
    return
  }
  members.forEach((member) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "team-chat-group-member"
    const avatar = document.createElement("span")
    avatar.className = "team-chat-avatar"
    renderTeamChatMemberAvatar(avatar, member)
    const copy = document.createElement("span")
    const name = document.createElement("strong")
    name.textContent = teamChatDisplayName(member)
    const subtitle = document.createElement("small")
    subtitle.textContent = `@${member.username || ""}`
    copy.append(name, subtitle)
    button.append(avatar, copy)
    button.addEventListener("click", () => {
      void switchTeamChatDirectMember(member)
    })
    refs.teamChatGroupMembers.append(button)
  })
}

function renderTeamChatAnnouncement(announcement) {
  if (!refs.teamChatAnnouncement) {
    return
  }
  const content = announcement?.content || ""
  refs.teamChatAnnouncement.classList.toggle("hidden", !content)
  refs.teamChatAnnouncement.textContent = content ? `公告：${content}` : ""
}

function renderTeamChatGroupContextDisclosure() {
  const expanded = state.teamChatRoom.type === "team" && state.teamChatGroupContextExpanded
  refs.teamChatGroupContext?.classList.toggle("is-collapsed", !expanded)
  refs.teamChatGroupContextToggle?.setAttribute("aria-expanded", String(expanded))
  refs.teamChatGroupContextBody?.classList.toggle("hidden", !expanded)
}

function renderTeamChatGroupStats(stats) {
  if (!refs.teamChatGroupStats) {
    return
  }
  if (!stats) {
    refs.teamChatGroupStats.innerHTML = '<p>统计暂时不可用。</p>'
    return
  }
  refs.teamChatGroupStats.innerHTML = `
    <h4>部门群统计</h4>
    <p>${Number(stats.users?.member_count || 0)} 位成员 · ${Number(stats.usage?.generated_image_count || 0)} 张图 · ${Number(stats.assets?.asset_count || 0)} 个优秀资产</p>
    <p>满意 ${Number(stats.feedback?.totals?.good || 0)} · 一般 ${Number(stats.feedback?.totals?.ok || 0)} · 不好 ${Number(stats.feedback?.totals?.bad || 0)}</p>
  `
}

function renderTeamChatGroupSummary(summary) {
  if (!refs.teamChatGroupSummary) {
    return
  }
  const text = summary?.text || "暂无周报。"
  refs.teamChatGroupSummary.innerHTML = `
    <h4>部门群周报</h4>
    <p>${escapeHTML(text)}</p>
  `
}

function renderTeamChatGroupAssets(assets) {
  if (!refs.teamChatGroupAssets) {
    return
  }
  const rows = Array.isArray(assets) ? assets.slice(0, 4) : []
  if (!rows.length) {
    refs.teamChatGroupAssets.innerHTML = '<h4>优秀资产</h4><p>满意作品会自动沉淀到这里，仅作可选参考，不会强制融入新提示词。</p>'
    return
  }
  refs.teamChatGroupAssets.innerHTML = `
    <h4>优秀资产</h4>
    <div class="team-chat-asset-list">
      ${rows.map((asset, index) => `
        <article class="team-chat-asset-card" data-asset-index="${index}">
          ${asset.saved_image_url ? `<img src="${escapeHTML(asset.saved_image_url)}" alt="">` : ""}
          <div>
            <strong>${escapeHTML(asset.title || "满意作品")}</strong>
            <p>${escapeHTML(asset.prompt || "未记录提示词")}</p>
            <span>${escapeHTML(asset.username || "")}</span>
            <button class="text-button team-chat-use-asset-button" type="button" data-asset-index="${index}">作为参考</button>
          </div>
        </article>
      `).join("")}
    </div>
  `
  refs.teamChatGroupAssets.querySelectorAll(".team-chat-use-asset-button").forEach((button) => {
    button.addEventListener("click", () => {
      const asset = rows[Number(button.dataset.assetIndex || 0)]
      useGroupAssetAsReference(asset)
    })
  })
}

function useGroupAssetAsReference(asset) {
  if (!asset) {
    return
  }
  setMode("generate", { autoLoadLatest: false })
  setGenerateIntent("fresh")
  if (asset.prompt && !refs.generatePromptInput.value.trim()) {
    refs.generatePromptInput.value = asset.prompt
  }
  if (asset.saved_image_url) {
    const description = `部门群优秀资产 · 仅作可选参考 · ${asset.title || "满意作品"}`
    state.generateReferenceImage = null
    state.materialReferenceImage = null
    state.styleReferenceImage = {
      // dataUrl must stay empty: ensureAssetDataUrl returns it verbatim when
      // truthy, and a "/files/..." URL here would be sent as base64 payload
      // and rejected by the backend. savedUrl drives the fetch-and-convert.
      dataUrl: "",
      file: null,
      name: asset.title || "group-asset.png",
      type: "image/png",
      size: 0,
      description,
      savedUrl: asset.saved_image_url,
      savedPath: asset.saved_image_path || "",
      origin: "group-asset",
    }
    updateGenerateReferenceUI()
  }
  updatePromptCounters()
  scheduleWorkspacePersist()
  setStatusMessage("已把部门群优秀资产作为可选参考。")
  closeTeamChatModal()
  refs.generatePromptInput.focus()
}

async function refreshTeamChatGroupContext() {
  refs.teamChatGroupContext?.classList.toggle("hidden", state.teamChatRoom.type !== "team")
  if (!state.currentUser || !refs.teamChatGroupContext || state.teamChatRoom.type !== "team") {
    renderTeamChatAnnouncement(null)
    renderTeamChatGroupMembers()
    return
  }
  renderTeamChatGroupMembers()
  try {
    const [announcementResponse, statsResponse, summaryResponse, assetsResponse] = await Promise.all([
      fetchJSON("/api/team-chat/group-announcement", { cache: "no-store" }),
      fetchJSON("/api/team-chat/group-stats", { cache: "no-store" }),
      fetchJSON("/api/team-chat/group-summary?days=7", { cache: "no-store" }),
      fetchJSON("/api/team-chat/group-assets", { cache: "no-store" }),
    ])
    renderTeamChatAnnouncement(
      announcementResponse.response.ok ? announcementResponse.data.announcement : null
    )
    renderTeamChatGroupStats(statsResponse.response.ok ? statsResponse.data.stats : null)
    renderTeamChatGroupSummary(summaryResponse.response.ok ? summaryResponse.data.summary : null)
    renderTeamChatGroupAssets(assetsResponse.response.ok ? assetsResponse.data.assets : [])
  } catch {
    renderTeamChatAnnouncement(null)
    renderTeamChatGroupStats(null)
    renderTeamChatGroupSummary(null)
    renderTeamChatGroupAssets([])
  }
}

function updateTeamChatLastMessageId() {
  state.teamChatLastMessageId = state.teamChatMessages.reduce((latest, message) => {
    return Math.max(latest, Number(message.id || 0))
  }, 0)
}

function mergeTeamChatMessages(incomingMessages = [], { replace = false } = {}) {
  const source = replace ? [] : state.teamChatMessages
  const byId = new Map()
  const byClientId = new Map()
  source.forEach((message) => {
    const messageId = Number(message.id || 0)
    if (messageId > 0) {
      byId.set(messageId, message)
    } else if (message.client_id) {
      byClientId.set(message.client_id, message)
    }
  })
  incomingMessages.forEach((message) => {
    const messageId = Number(message.id || 0)
    if (messageId > 0) {
      if (message.client_id) {
        byClientId.delete(message.client_id)
      }
      byId.set(messageId, message)
    } else if (message.client_id) {
      byClientId.set(message.client_id, message)
    }
  })
  state.teamChatMessages = [...Array.from(byId.values()), ...Array.from(byClientId.values())].sort((left, right) => {
    const leftId = Number(left.id || 0)
    const rightId = Number(right.id || 0)
    if (leftId > 0 && rightId > 0) {
      return leftId - rightId
    }
    return String(left.created_at || "").localeCompare(String(right.created_at || ""))
  })
  updateTeamChatLastMessageId()
}

function isOwnTeamChatMessage(message) {
  return Number(message?.sender_user_id || 0) === Number(state.currentUser?.id || 0)
}

function parseTeamChatQuotedContent(content = "") {
  const text = String(content || "")
  const match = text.match(/^引用 ([^：:\n]{1,80})[：:](.*?)(?:\n{2,}([\s\S]*))$/)
  if (!match) {
    return { quoteAuthor: "", quoteText: "", body: text }
  }
  return {
    quoteAuthor: match[1].trim(),
    quoteText: match[2].trim(),
    body: (match[3] || "").trim(),
  }
}

function renderTeamChatBubbleContent(container, message) {
  container.replaceChildren()
  const parsed = parseTeamChatQuotedContent(message.content || "")
  if (parsed.quoteAuthor || parsed.quoteText) {
    const quote = document.createElement("blockquote")
    quote.className = "team-chat-message-quote"
    const author = document.createElement("strong")
    author.textContent = parsed.quoteAuthor ? `引用 ${parsed.quoteAuthor}` : "引用消息"
    const text = document.createElement("span")
    text.textContent = parsed.quoteText || "原消息"
    quote.append(author, text)
    container.append(quote)
  }
  const bodyText = document.createElement("span")
  bodyText.className = "team-chat-message-text"
  bodyText.textContent = parsed.body || message.content || ""
  container.append(bodyText)
}

function renderTeamChatMessages({ scrollToBottom = true } = {}) {
  if (!refs.teamChatMessages) {
    return
  }
  refs.teamChatMessages.replaceChildren()
  if (!state.teamChatMessages.length) {
    const empty = document.createElement("p")
    empty.className = "team-chat-empty"
    empty.textContent = "还没有消息。"
    refs.teamChatMessages.append(empty)
    return
  }
  state.teamChatMessages.forEach((message) => {
    const item = document.createElement("article")
    item.className = "team-chat-message"
    item.classList.toggle("mine", Number(message.sender_user_id || 0) === Number(state.currentUser?.id || 0))
    item.classList.toggle("bot", message.sender_type === "bot")
    item.classList.toggle("pending", Boolean(message.pending))
    const meta = document.createElement("div")
    meta.className = "team-chat-message-meta"
    const sender = document.createElement("strong")
    sender.textContent = message.sender_name || (message.sender_type === "bot" ? "GPT-BOT" : "用户")
    const time = document.createElement("span")
    time.textContent = formatTeamChatTime(message.created_at)
    meta.append(sender, time)
    const body = document.createElement("div")
    body.className = "team-chat-message-body"
    const bubble = document.createElement("div")
    bubble.className = "team-chat-message-bubble"
    renderTeamChatBubbleContent(bubble, message)
    const actions = document.createElement("div")
    actions.className = "team-chat-message-actions"
    const moreButton = document.createElement("button")
    moreButton.className = "team-chat-message-more"
    moreButton.type = "button"
    moreButton.setAttribute("aria-haspopup", "menu")
    moreButton.setAttribute("aria-expanded", String(String(state.teamChatOpenMenuId) === String(message.id)))
    moreButton.setAttribute("aria-label", "更多操作")
    moreButton.textContent = "⋯"
    moreButton.addEventListener("click", (event) => {
      event.stopPropagation()
      openTeamChatMessageMenu(message.id)
    })
    actions.append(moreButton)
    if (String(state.teamChatOpenMenuId) === String(message.id)) {
      actions.append(createTeamChatMessageMenu(message))
    }
    body.append(bubble, actions)
    item.append(meta, body)
    refs.teamChatMessages.append(item)
  })
  if (scrollToBottom) {
    refs.teamChatMessages.scrollTop = refs.teamChatMessages.scrollHeight
  }
}

function createOptimisticTeamChatMessage(content) {
  const displayName = state.currentUser?.display_name || state.currentUser?.username || "我"
  state.teamChatLocalMessageSeq += 1
  return {
    id: -state.teamChatLocalMessageSeq,
    client_id: `local-${Date.now()}-${state.teamChatLocalMessageSeq}`,
    room_key: currentTeamChatRoomKey(),
    room_type: state.teamChatRoom.type,
    sender_user_id: state.currentUser?.id || 0,
    sender_type: "user",
    sender_name: displayName,
    content,
    mentions: [],
    created_at: new Date().toISOString(),
    pending: true,
  }
}

function replaceOptimisticTeamChatMessage(clientId, serverMessages = []) {
  if (!clientId) {
    mergeTeamChatMessages(serverMessages)
    return
  }
  const withoutPending = state.teamChatMessages.filter((message) => message.client_id !== clientId)
  state.teamChatMessages = withoutPending
  mergeTeamChatMessages(serverMessages.map((message) => ({ ...message, client_id: clientId })))
}

function currentTeamChatRoomKey() {
  if (state.teamChatRoom.type === "team") {
    return state.teamChatGroup.roomKey || ""
  }
  if (state.teamChatRoom.type === "bot") {
    return `bot:${state.currentUser?.id || 0}`
  }
  const currentUserId = Number(state.currentUser?.id || 0)
  const recipientId = Number(state.teamChatRoom.recipientUserId || 0)
  const [low, high] = [currentUserId, recipientId].sort((left, right) => left - right)
  return low && high ? `dm:${low}:${high}` : ""
}

function scheduleTeamChatFastPolling() {
  state.teamChatFastPollRemaining = TEAM_CHAT_FAST_POLL_LIMIT
}

function getTeamChatMessageById(messageId) {
  return state.teamChatMessages.find((message) => String(message.id) === String(messageId)) || null
}

function createTeamChatMessageMenu(message) {
  const menu = document.createElement("div")
  menu.className = "team-chat-message-menu"
  menu.setAttribute("role", "menu")
  const actions = [
    ["copy", "复制", () => copyTeamChatMessage(message)],
    ["quote", "引用", () => quoteTeamChatMessage(message)],
  ]
  if (isOwnTeamChatMessage(message)) {
    actions.push(["recall", "撤回", jokeRecallTeamChatMessage])
  }
  actions.forEach(([action, label, handler]) => {
    const button = document.createElement("button")
    button.type = "button"
    button.setAttribute("role", "menuitem")
    button.dataset.action = action
    button.textContent = label
    button.addEventListener("click", (event) => {
      event.stopPropagation()
      closeTeamChatMessageMenu()
      handler()
    })
    menu.append(button)
  })
  return menu
}

function openTeamChatMessageMenu(messageId) {
  if (!getTeamChatMessageById(messageId)) {
    return
  }
  state.teamChatOpenMenuId = String(state.teamChatOpenMenuId) === String(messageId) ? null : messageId
  renderTeamChatMessages({ scrollToBottom: false })
}

function closeTeamChatMessageMenu() {
  if (!state.teamChatOpenMenuId) {
    return
  }
  state.teamChatOpenMenuId = null
  renderTeamChatMessages({ scrollToBottom: false })
}

async function copyTeamChatMessage(message) {
  const content = message?.content || ""
  if (!content) {
    setStatusMessage("这条消息没有可复制的内容。")
    return
  }
  try {
    await navigator.clipboard.writeText(content)
    setStatusMessage("消息已复制。")
  } catch {
    setTeamChatStatus("浏览器不允许复制到剪贴板。", true)
  }
}

function summarizeTeamChatQuote(message) {
  const text = String(message?.content || "").replace(/\s+/g, " ").trim()
  return text.length > 80 ? `${text.slice(0, 80)}...` : text
}

function quoteTeamChatMessage(message) {
  if (!message) {
    return
  }
  state.teamChatQuotedMessage = {
    id: message.id,
    senderName: message.sender_name || (message.sender_type === "bot" ? "GPT-BOT" : "用户"),
    content: summarizeTeamChatQuote(message),
  }
  renderTeamChatQuotePreview()
  setStatusMessage("已引用这条消息。")
  refs.teamChatMessageInput?.focus()
}

function clearTeamChatQuote() {
  state.teamChatQuotedMessage = null
  renderTeamChatQuotePreview()
}

function renderTeamChatQuotePreview() {
  const quoted = state.teamChatQuotedMessage
  refs.teamChatQuotePreview?.classList.toggle("hidden", !quoted)
  if (refs.teamChatQuoteAuthor) {
    refs.teamChatQuoteAuthor.textContent = quoted ? `引用 ${quoted.senderName}` : ""
  }
  if (refs.teamChatQuoteText) {
    refs.teamChatQuoteText.textContent = quoted?.content || ""
  }
}

function formatTeamChatOutgoingContent(content) {
  const quoted = state.teamChatQuotedMessage
  if (!quoted) {
    return content
  }
  return `引用 ${quoted.senderName}：${quoted.content}\n\n${content}`.slice(0, TEAM_CHAT_MAX_MESSAGE_LENGTH)
}

function jokeRecallTeamChatMessage() {
  setTeamChatStatus("逗你的，撤回不了。")
}

function formatTeamChatTime(value) {
  if (!value) {
    return ""
  }
  // Server timestamps are UTC, written either as an ISO offset form
  // ("2026-06-14T10:00:00+00:00") or a legacy naive form ("2026-06-14 10:00:00").
  // Only append "Z" when there is no timezone designator yet — appending it to the
  // offset form produces "...+00:00Z", an Invalid Date (which blanked every timestamp).
  let normalized = String(value).trim().replace(" ", "T")
  if (!/[zZ]$/.test(normalized) && !/[+-]\d\d:?\d\d$/.test(normalized)) {
    normalized = `${normalized}Z`
  }
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return ""
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function teamChatInputPlaceholder() {
  if (state.teamChatRoom.type === "bot") {
    return "向 GPT-BOT 提问，例如：这张海报怎么优化？"
  }
  if (state.teamChatRoom.type === "dm") {
    return `发给 ${state.teamChatRoom.title || "对方"}`
  }
  return "输入群消息，可以 @GPT-BOT"
}

function updateTeamChatRoomHeader() {
  const fallbackTitle = state.teamChatRoom.type === "team" ? teamChatGroupDisplayTitle() : "部门群"
  const fallbackMeta = state.teamChatRoom.type === "team" ? teamChatGroupDisplayMeta() : state.teamChatGroup.subtitle
  if (refs.teamChatRoomTitle) {
    refs.teamChatRoomTitle.textContent = state.teamChatRoom.title || fallbackTitle
  }
  if (refs.teamChatRoomMeta) {
    refs.teamChatRoomMeta.textContent = state.teamChatRoom.meta || fallbackMeta || "部门群"
  }
  if (refs.teamChatMessageInput) {
    refs.teamChatMessageInput.placeholder = teamChatInputPlaceholder()
  }
  renderTeamChatMembers()
  renderTeamChatGroupMembers()
  refs.teamChatGroupMemberPanel?.classList.toggle("hidden", state.teamChatRoom.type !== "team")
  refs.teamChatMain?.classList.toggle("without-member-panel", state.teamChatRoom.type !== "team")
  renderTeamChatGroupContextDisclosure()
}

function setTeamChatStatus(message = "", isError = false) {
  if (!refs.teamChatStatus) {
    return
  }
  refs.teamChatStatus.textContent = message
  refs.teamChatStatus.classList.toggle("is-error", Boolean(isError))
}

function setTeamChatSending(isSending) {
  state.teamChatSending = Boolean(isSending)
  if (refs.sendTeamChatButton) {
    refs.sendTeamChatButton.disabled = isSending
    refs.sendTeamChatButton.textContent = isSending ? "发送中" : "发送"
  }
}

function restoreTeamChatDraft(draftContent, draftQuote) {
  if (refs.teamChatMessageInput && !refs.teamChatMessageInput.value.trim()) {
    refs.teamChatMessageInput.value = draftContent
  }
  if (!state.teamChatQuotedMessage && draftQuote) {
    state.teamChatQuotedMessage = draftQuote
    renderTeamChatQuotePreview()
  }
}

async function refreshTeamChatMembers() {
  if (!state.currentUser || !refs.teamChatMembers) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/team-chat/members", { cache: "no-store" })
    if (!response.ok) {
      setTeamChatStatus(data.error || "成员列表读取失败", true)
      return
    }
    state.teamChatGroup = normalizeTeamChatGroup(data.group || state.teamChatGroup)
    const allMembers = Array.isArray(data.members) ? data.members : []
    state.teamChatBot = data.bot || allMembers.find((member) => member.type === "bot") || null
    state.teamChatHumanMembers = Array.isArray(data.human_members)
      ? data.human_members
      : allMembers.filter((member) => member.type !== "bot")
    state.teamChatMembers = allMembers.length ? allMembers : [state.teamChatBot, ...state.teamChatHumanMembers].filter(Boolean)
    state.teamChatGroup = {
      ...state.teamChatGroup,
      memberCount: Number(data.group?.member_count || state.teamChatHumanMembers.length || 0),
    }
    hydrateTeamChatRecentDmsFromMembers()
    saveTeamChatRecentDms()
    if (state.teamChatRoom.type === "team") {
      state.teamChatRoom = {
        ...state.teamChatRoom,
        title: teamChatGroupDisplayTitle(),
        meta: teamChatGroupDisplayMeta(),
      }
    }
    renderTeamChatMembers()
    renderTeamChatGroupMembers()
  } catch {
    setTeamChatStatus("成员列表暂时不可用", true)
  }
}

async function refreshTeamChatMessages({ append = false } = {}) {
  // 返回是否成功：调用方只有在成功时才清空状态栏，否则这里刚写入的
  // 错误提示会被 0ms 后的 setTeamChatStatus("") 抹掉，失败看起来像空房间。
  if (!state.currentUser || !refs.teamChatMessages) {
    return false
  }
  const requestedRoomKey = currentTeamChatRoomKey()
  const params = teamChatRoomParams()
  if (append && state.teamChatLastMessageId) {
    params.set("after_id", String(state.teamChatLastMessageId))
  }
  try {
    const { response, data } = await fetchJSON(`/api/team-chat/messages?${params.toString()}`, { cache: "no-store" })
    if (requestedRoomKey !== currentTeamChatRoomKey()) {
      return true
    }
    if (!response.ok) {
      setTeamChatStatus(data.error || "消息读取失败", true)
      return false
    }
    const messages = Array.isArray(data.messages)
      ? data.messages.filter((message) => !message.room_key || message.room_key === requestedRoomKey)
      : []
    mergeTeamChatMessages(messages, { replace: !append })
    renderTeamChatMessages({ scrollToBottom: messages.length > 0 || !append })
    if (!refs.teamChatModal?.classList.contains("hidden")) {
      await markCurrentTeamChatRead()
    }
    return true
  } catch {
    setTeamChatStatus("消息读取失败", true)
    return false
  }
}

async function markCurrentTeamChatRead() {
  if (!state.currentUser || !state.teamChatLastMessageId) {
    return
  }
  try {
    await fetchJSON("/api/team-chat/read", {
      method: "POST",
      body: JSON.stringify(teamChatReadPayload()),
    })
    await refreshTeamChatUnread()
  } catch {
    // Best effort only; unread can recover on next poll.
  }
}

async function refreshTeamChatUnread() {
  if (!state.currentUser || !refs.teamChatButton) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/team-chat/unread", { cache: "no-store" })
    if (response.ok) {
      updateTeamChatUnreadBadge(data.unread?.total || 0)
    }
  } catch {
    // Keep the previous badge state.
  }
}

function startTeamChatPolling() {
  stopTeamChatPolling()
  state.teamChatUnreadTimer = window.setInterval(refreshTeamChatUnread, 15000)
  let regularPollTicks = 0
  state.teamChatPollTimer = window.setInterval(() => {
    if (!refs.teamChatModal?.classList.contains("hidden")) {
      if (state.teamChatFastPollRemaining > 0) {
        state.teamChatFastPollRemaining -= 1
        void refreshTeamChatMessages({ append: true })
        return
      }
      regularPollTicks += 1
      if (regularPollTicks >= 5) {
        regularPollTicks = 0
        void refreshTeamChatMessages({ append: true })
      }
    }
  }, 1500)
}

function stopTeamChatPolling() {
  if (state.teamChatUnreadTimer) {
    window.clearInterval(state.teamChatUnreadTimer)
    state.teamChatUnreadTimer = null
  }
  if (state.teamChatPollTimer) {
    window.clearInterval(state.teamChatPollTimer)
    state.teamChatPollTimer = null
  }
}

async function switchTeamChatRoom(nextRoom) {
  state.teamChatRoom = {
    type: nextRoom.type || "team",
    recipientUserId: nextRoom.recipientUserId || null,
    title: nextRoom.title || (nextRoom.type === "team" ? teamChatGroupDisplayTitle() : "部门群"),
    meta: nextRoom.meta || (nextRoom.type === "team" ? teamChatGroupDisplayMeta() : state.teamChatGroup.subtitle) || "部门群",
  }
  state.teamChatMessages = []
  state.teamChatLastMessageId = 0
  clearTeamChatQuote()
  state.teamChatOpenMenuId = null
  updateTeamChatRoomHeader()
  renderTeamChatMessages()
  await refreshTeamChatGroupContext()
  setTeamChatStatus("读取消息中")
  if (await refreshTeamChatMessages()) {
    setTeamChatStatus("")
  }
  refs.teamChatMessageInput?.focus()
}

function switchTeamChatDirectMember(member) {
  if (!member || member.type === "bot") {
    return switchTeamChatRoom({ type: "bot", recipientUserId: null, title: "GPT-BOT", meta: "AI 创意与图片质量助手。" })
  }
  rememberTeamChatRecentDm(member)
  renderTeamChatMembers()
  return switchTeamChatRoom({
    type: "dm",
    recipientUserId: Number(member.id || 0),
    title: teamChatDisplayName(member),
    meta: `私聊 @${member.username || teamChatDisplayName(member)}`,
  })
}

async function openTeamChatModal() {
  if (!state.currentUser) {
    return
  }
  refs.teamChatModal?.classList.remove("hidden")
  refs.teamChatModal?.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open", "chat-open")
  setTeamChatStatus("读取中")
  await refreshTeamChatMembers()
  updateTeamChatRoomHeader()
  await refreshTeamChatGroupContext()
  if (await refreshTeamChatMessages()) {
    setTeamChatStatus("")
  }
  refs.teamChatMessageInput?.focus()
}

function closeTeamChatModal() {
  clearTeamChatQuote()
  state.teamChatOpenMenuId = null
  refs.teamChatModal?.classList.add("hidden")
  refs.teamChatModal?.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open", "chat-open")
  void refreshTeamChatUnread()
}

async function submitTeamChatMessage(event) {
  event.preventDefault()
  if (state.teamChatSending) {
    return
  }
  const content = refs.teamChatMessageInput?.value.trim() || ""
  if (!content) {
    setTeamChatStatus("请输入消息", true)
    return
  }
  const outgoingContent = formatTeamChatOutgoingContent(content)
  const draftContent = refs.teamChatMessageInput?.value || ""
  const draftQuote = state.teamChatQuotedMessage
  if (refs.teamChatMessageInput) {
    refs.teamChatMessageInput.value = ""
  }
  clearTeamChatQuote()
  const optimistic = createOptimisticTeamChatMessage(outgoingContent)
  mergeTeamChatMessages([optimistic])
  renderTeamChatMessages()
  setTeamChatSending(true)
  setTeamChatStatus("发送中")
  try {
    const { response, data } = await fetchJSON("/api/team-chat/messages", {
      method: "POST",
      body: JSON.stringify(teamChatSendPayload(outgoingContent)),
    })
    if (!response.ok) {
      state.teamChatMessages = state.teamChatMessages.filter((message) => message.client_id !== optimistic.client_id)
      renderTeamChatMessages()
      restoreTeamChatDraft(draftContent, draftQuote)
      setTeamChatStatus(data.error || "发送失败", true)
      return
    }
    const messages = Array.isArray(data.messages) ? data.messages : []
    replaceOptimisticTeamChatMessage(optimistic.client_id, messages)
    renderTeamChatMessages()
    await markCurrentTeamChatRead()
    if (data.bot_reply_pending) {
      scheduleTeamChatFastPolling()
      void refreshTeamChatMessages({ append: true })
      setTeamChatStatus("已发送，GPT-BOT 正在思考")
    } else {
      setTeamChatStatus("已发送")
    }
  } catch {
    state.teamChatMessages = state.teamChatMessages.filter((message) => message.client_id !== optimistic.client_id)
    renderTeamChatMessages()
    restoreTeamChatDraft(draftContent, draftQuote)
    setTeamChatStatus("网络连接错误", true)
  } finally {
    setTeamChatSending(false)
    refs.teamChatMessageInput?.focus()
  }
}

async function submitChangePassword(event) {
  event.preventDefault()
  const currentPassword = refs.currentPasswordInput?.value || ""
  const newPassword = refs.newPasswordInput?.value || ""
  if (!currentPassword || !newPassword) {
    if (refs.changePasswordStatus) {
      refs.changePasswordStatus.textContent = "请填写当前密码和新密码。"
      refs.changePasswordStatus.classList.add("is-error")
    }
    return
  }
  if (refs.submitChangePasswordButton) {
    refs.submitChangePasswordButton.disabled = true
  }
  if (refs.changePasswordStatus) {
    refs.changePasswordStatus.textContent = "保存中"
    refs.changePasswordStatus.classList.remove("is-error")
  }
  try {
    const { response, data } = await fetchJSON("/api/me/password", {
      method: "PUT",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    })
    if (!response.ok) {
      refs.changePasswordStatus.textContent = data.error || "密码修改失败"
      refs.changePasswordStatus.classList.add("is-error")
      return
    }
    setCurrentUser(data.user || state.currentUser)
    refs.changePasswordForm?.reset()
    refs.changePasswordStatus.textContent = "密码已更新，其它登录会话已失效。"
    refs.changePasswordStatus.classList.remove("is-error")
    setStatusMessage("密码已更新。")
  } catch {
    refs.changePasswordStatus.textContent = "网络连接错误"
    refs.changePasswordStatus.classList.add("is-error")
  } finally {
    if (refs.submitChangePasswordButton) {
      refs.submitChangePasswordButton.disabled = false
    }
  }
}

async function submitBugReport(event) {
  event.preventDefault()
  const title = refs.bugReportTitleInput?.value.trim() || ""
  const description = refs.bugReportDescriptionInput?.value.trim() || ""
  const contact = refs.bugReportContactInput?.value.trim() || ""
  if (!description) {
    if (refs.bugReportStatus) {
      refs.bugReportStatus.textContent = "请填写问题描述。"
    }
    return
  }
  if (refs.submitBugReportButton) {
    refs.submitBugReportButton.disabled = true
  }
  if (refs.bugReportStatus) {
    refs.bugReportStatus.textContent = "提交中"
  }
  try {
    const { response, data } = await fetchJSON("/api/bug-reports", {
      method: "POST",
      body: JSON.stringify({
        title,
        description,
        contact,
        page_url: window.location.href,
      }),
    })
    if (!response.ok) {
      refs.bugReportStatus.textContent = data.error || "提交失败"
      return
    }
    const notified = data.notification?.sent
    refs.bugReportStatus.textContent = notified ? "已提交，并已发送通知。" : "已提交，管理员可在后台查看。"
    refs.bugReportForm?.reset()
    await refreshBugReports()
  } catch {
    refs.bugReportStatus.textContent = "提交时网络连接错误"
  } finally {
    if (refs.submitBugReportButton) {
      refs.submitBugReportButton.disabled = false
    }
  }
}

function updateFeedbackSelection(rating) {
  state.lastFeedbackRating = rating || null
  refs.feedbackRatingButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.rating === rating)
  })
}

async function submitResultFeedback(rating, { reason = "", showReason = true } = {}) {
  if (!state.resultPreview?.src) {
    setError("当前没有可评价的结果图。")
    return false
  }
  updateFeedbackSelection(rating)
  if (rating === "bad" && showReason) {
    refs.feedbackReasonPanel?.classList.remove("hidden")
    refs.feedbackReasonInput?.focus()
    setFeedbackStatus("可补充原因")
    return false
  }
  const payload = buildFeedbackPayload(rating, reason)
  state.lastFeedbackPayload = payload
  setFeedbackStatus("提交中")
  try {
    const { response, data } = await fetchJSON("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      setFeedbackStatus("提交失败")
      setError(data.error || "反馈提交失败")
      return false
    }
    setFeedbackStatus(rating === "good" ? "已记录满意" : rating === "ok" ? "已记录一般" : "已记录不好")
    if (rating === "good") {
      showSharePanel()
    } else {
      refs.shareResultPanel?.classList.add("hidden")
    }
    await refreshFeedbackSummary()
    return true
  } catch {
    setFeedbackStatus("提交失败")
    setError("反馈提交时网络连接错误")
    return false
  }
}

async function submitBadFeedbackReason() {
  const reason = refs.feedbackReasonInput?.value.trim() || ""
  await submitResultFeedback("bad", { reason, showReason: false })
}

async function regenerateFromBadFeedback() {
  const reason = refs.feedbackReasonInput?.value.trim() || ""
  await submitResultFeedback("bad", { reason, showReason: false })
  await rerunLastGeneration()
}

function validateAuthFormInputs() {
  const username = refs.authUsernameInput?.value.trim() || ""
  const password = refs.authPasswordInput?.value || ""
  if (!username || username.length < 2) {
    if (refs.authError) {
      refs.authError.textContent = "用户名至少需要 2 个字符。"
    }
    refs.authUsernameInput?.focus()
    return false
  }
  if (!password || password.length < 8) {
    if (refs.authError) {
      refs.authError.textContent = "密码至少需要 8 位。"
    }
    refs.authPasswordInput?.focus()
    return false
  }
  if (refs.authError) {
    refs.authError.textContent = ""
  }
  return true
}

async function submitAuthForm(event) {
  event.preventDefault()
  if (!validateAuthFormInputs()) {
    return
  }
  const username = refs.authUsernameInput.value.trim()
  const password = refs.authPasswordInput.value
  const endpoint = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login"
  const authPayload = { username, password }
  if (state.authMode === "register") {
    authPayload.company = refs.authCompanyInput?.value || "6renyou"
    authPayload.department = refs.authDepartmentInput?.value || "PD & OPS"
  }
  refs.authError.textContent = ""
  refs.loginAuthButton.disabled = true
  if (refs.registerAuthButton) {
    refs.registerAuthButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON(endpoint, {
      method: "POST",
      body: JSON.stringify(authPayload),
    })
    if (!response.ok) {
      refs.authError.textContent = data.error || "认证失败"
      return
    }
    setCurrentUser(data.user)
    refs.authPasswordInput.value = ""
    enterAppShell()
    await startAuthenticatedApp()
  } catch {
    refs.authError.textContent = "网络连接错误"
  } finally {
    refs.loginAuthButton.disabled = false
    if (refs.registerAuthButton) {
      refs.registerAuthButton.disabled = false
    }
  }
}

async function submitPasswordResetRequest(event) {
  event.preventDefault()
  const username = refs.passwordResetUsernameInput?.value.trim() || ""
  if (!username) {
    if (refs.passwordResetRequestStatus) {
      refs.passwordResetRequestStatus.textContent = "请输入用户名。"
      refs.passwordResetRequestStatus.classList.add("is-error")
    }
    return
  }
  if (refs.passwordResetRequestStatus) {
    refs.passwordResetRequestStatus.textContent = ""
    refs.passwordResetRequestStatus.classList.remove("is-error")
  }
  if (refs.submitPasswordResetRequestButton) {
    refs.submitPasswordResetRequestButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON("/api/password-reset-requests", {
      method: "POST",
      body: JSON.stringify({ username }),
    })
    if (!response.ok) {
      if (refs.passwordResetRequestStatus) {
        refs.passwordResetRequestStatus.textContent = data.error || "提交失败"
        refs.passwordResetRequestStatus.classList.add("is-error")
      }
      return
    }
    if (refs.passwordResetRequestStatus) {
      refs.passwordResetRequestStatus.textContent = data.message || "如果账号存在且已填写邮箱，会收到重置邮件；否则管理员会看到申请。"
      refs.passwordResetRequestStatus.classList.remove("is-error")
    }
  } catch {
    if (refs.passwordResetRequestStatus) {
      refs.passwordResetRequestStatus.textContent = "网络连接错误"
      refs.passwordResetRequestStatus.classList.add("is-error")
    }
  } finally {
    if (refs.submitPasswordResetRequestButton) {
      refs.submitPasswordResetRequestButton.disabled = false
    }
  }
}

async function submitPasswordResetConfirm(event) {
  event.preventDefault()
  const password = refs.passwordResetNewPasswordInput?.value || ""
  const confirmed = refs.passwordResetConfirmPasswordInput?.value || ""
  if (!state.passwordResetToken) {
    if (refs.passwordResetConfirmStatus) {
      refs.passwordResetConfirmStatus.textContent = "重置链接无效，请重新申请。"
      refs.passwordResetConfirmStatus.classList.add("is-error")
    }
    return
  }
  if (!password || password.length < 8) {
    if (refs.passwordResetConfirmStatus) {
      refs.passwordResetConfirmStatus.textContent = "新密码至少需要 8 位。"
      refs.passwordResetConfirmStatus.classList.add("is-error")
    }
    return
  }
  if (password !== confirmed) {
    if (refs.passwordResetConfirmStatus) {
      refs.passwordResetConfirmStatus.textContent = "两次输入的新密码不一致。"
      refs.passwordResetConfirmStatus.classList.add("is-error")
    }
    return
  }
  if (refs.passwordResetConfirmStatus) {
    refs.passwordResetConfirmStatus.textContent = ""
    refs.passwordResetConfirmStatus.classList.remove("is-error")
  }
  if (refs.submitPasswordResetConfirmButton) {
    refs.submitPasswordResetConfirmButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON("/api/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token: state.passwordResetToken, password }),
    })
    if (!response.ok) {
      if (refs.passwordResetConfirmStatus) {
        refs.passwordResetConfirmStatus.textContent = data.error || "重置链接无效或已过期，请重新申请。"
        refs.passwordResetConfirmStatus.classList.add("is-error")
      }
      return
    }
    state.passwordResetToken = ""
    if (refs.passwordResetConfirmStatus) {
      refs.passwordResetConfirmStatus.textContent = data.message || "密码已重置，请使用新密码登录。"
      refs.passwordResetConfirmStatus.classList.remove("is-error")
    }
    const cleanUrl = new URL(window.location.href)
    cleanUrl.searchParams.delete("reset_token")
    window.history.replaceState(null, "", `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`)
    window.setTimeout(() => enterAuthGate("login", "密码已重置，请使用新密码登录。"), 900)
  } catch {
    if (refs.passwordResetConfirmStatus) {
      refs.passwordResetConfirmStatus.textContent = "网络连接错误"
      refs.passwordResetConfirmStatus.classList.add("is-error")
    }
  } finally {
    if (refs.submitPasswordResetConfirmButton) {
      refs.submitPasswordResetConfirmButton.disabled = false
    }
  }
}

async function logout() {
  try {
    await fetchJSON("/api/auth/logout", { method: "POST" })
  } catch {
    // 网络断开时也要完成本地登出，且不能留下未处理的 rejection。
  } finally {
    window.clearTimeout(state.persistTimer)
    state.persistTimer = null
    state.persistenceReady = false
    state.appReady = false
    state.lastReadyUserId = null
    state.history = []
    state.shareRecipients = []
    state.sharedResults = []
    state.savedApiKey = ""
    clearResult()
    clearGenerateForm()
    clearEditForm()
    setCurrentUser(null)
    enterAuthGate("login")
    if (refs.userUsageSummary) {
      refs.userUsageSummary.textContent = "登录后自动统计。"
    }
    refs.userImageStats?.classList.add("hidden")
    updateAdminPanelVisibility()
  }
}

function openWorkspaceDb() {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(WORKSPACE_DB_NAME, WORKSPACE_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(WORKSPACE_STORE_NAME)) {
        db.createObjectStore(WORKSPACE_STORE_NAME)
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error("打开工作台数据库失败"))
  })
}

async function loadWorkspaceSnapshot() {
  const db = await openWorkspaceDb()

  return await new Promise((resolve, reject) => {
    const tx = db.transaction(WORKSPACE_STORE_NAME, "readonly")
    const store = tx.objectStore(WORKSPACE_STORE_NAME)
    const request = store.get(workspaceStorageKey())

    request.onsuccess = () => resolve(request.result || null)
    request.onerror = () => reject(request.error || new Error("读取工作台快照失败"))
    tx.oncomplete = () => db.close()
    tx.onabort = () => reject(tx.error || new Error("读取工作台快照失败"))
  })
}

async function saveWorkspaceSnapshot(snapshot) {
  const db = await openWorkspaceDb()

  return await new Promise((resolve, reject) => {
    const tx = db.transaction(WORKSPACE_STORE_NAME, "readwrite")
    const store = tx.objectStore(WORKSPACE_STORE_NAME)
    store.put(snapshot, workspaceStorageKey())

    tx.oncomplete = () => {
      db.close()
      resolve()
    }
    tx.onerror = () => reject(tx.error || new Error("保存工作台快照失败"))
    tx.onabort = () => reject(tx.error || new Error("保存工作台快照失败"))
  })
}

function sanitizeRawResponse(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeRawResponse(item))
  }

  if (value && typeof value === "object") {
    const sanitized = {}
    for (const [key, nestedValue] of Object.entries(value)) {
      if (key === "b64_json" && typeof nestedValue === "string") {
        sanitized[key] = `[base64 image omitted, ${Math.round((nestedValue.length * 3) / 4 / 1024)} KB]`
        continue
      }
      sanitized[key] = sanitizeRawResponse(nestedValue)
    }
    return sanitized
  }

  return value
}

function renderRawResponsePreview() {
  refs.rawResponseOutput.textContent = JSON.stringify(state.rawResponsePreview || {}, null, 2)
}

function appendDebugLine(message, fields = {}) {
  const timestamp = new Date().toLocaleTimeString("zh-CN", { hour12: false })
  const fieldText = Object.entries(fields)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${key}=${value}`)
    .join(" ")
  const line = `[${timestamp}] ${message}${fieldText ? ` ${fieldText}` : ""}`
  state.debugLines = [...state.debugLines, line].slice(-80)
  refs.debugOutput.textContent = state.debugLines.join("\n")
}

function resetDebugLog(message = "开始新的请求") {
  state.debugLines = []
  refs.debugOutput.textContent = ""
  appendDebugLine(message)
}

function summarizePayloadForDebug(payload) {
  return {
    endpoint: payload.endpoint_url,
    model: payload.model,
    transport: payload.transport,
    responsesModel: payload.responses_model,
    size: payload.size,
    quality: payload.quality,
    background: payload.background,
    outputFormat: payload.output_format,
    outputCompression: payload.output_compression,
    moderation: payload.moderation,
    sampleCount: payload.sample_count,
    logoRequested: payload.logo_requested,
    promptChars: String(payload.prompt || "").length,
    hasApiKey: Boolean(payload.api_key),
    imageName: payload.image?.name,
    imageType: payload.image?.type,
    imageBytesApprox: payload.image?.data_url ? Math.round((payload.image.data_url.length * 3) / 4) : undefined,
    maskName: payload.mask?.name,
  }
}

window.addEventListener("error", (event) => {
  appendDebugLine("前端脚本错误", {
    message: event.message,
    source: event.filename ? `${event.filename}:${event.lineno}` : "",
  })
})

window.addEventListener("unhandledrejection", (event) => {
  appendDebugLine("前端异步错误", {
    reason: event.reason?.message || event.reason,
  })
})

function createWorkspaceSnapshot() {
  return {
    version: WORKSPACE_VERSION,
    savedAt: new Date().toISOString(),
    activeMode: state.activeMode,
    generateIntent: state.generateIntent,
    forms: {
      generatePrompt: refs.generatePromptInput.value,
      generateModel: refs.generateModelInput.value,
      generateSizePreset: refs.generateSizePreset.value,
      generateWidth: refs.generateWidthInput.value,
      generateHeight: refs.generateHeightInput.value,
      quality: refs.qualitySelect.value,
      background: refs.backgroundSelect.value,
      outputFormat: refs.outputFormatSelect.value,
      outputCompression: refs.outputCompressionInput.value,
      moderation: refs.moderationSelect.value,
      generateSampleCount: refs.generateSampleCountInput.value,
      creativeBrief: creativeBriefSnapshot(),
      itineraryTitle: refs.itineraryTitleInput?.value || "",
      itinerarySubtitle: refs.itinerarySubtitleInput?.value || "",
      itinerarySize: refs.itinerarySizeSelect?.value || "auto",
      itineraryTheme: refs.itineraryThemeSelect?.value || "comic",
      itineraryDescription: refs.itineraryDescriptionInput?.value || "",
      itineraryLogoEnabled: refs.itineraryLogoEnabled?.checked !== false,
      editPrompt: refs.editPromptInput.value,
      editModel: refs.editModelInput.value,
      responsesModel: refs.responsesModelInput.value,
      imageTransport: getImageTransport(),
      logoOverlayEnabled: refs.logoOverlayEnabled.checked,
      itineraryIdEnabled: refs.itineraryIdEnabled?.checked || false,
      itineraryId: refs.itineraryIdInput?.value || "",
    },
    result: {
      promptText: refs.resultPrompt.textContent,
      metaText: refs.resultMeta.textContent,
      timingText: refs.resultTiming.textContent,
      storageText: refs.resultStorage.textContent,
      labelText: refs.resultPreviewLabel.textContent,
      imageSrc: state.resultPreview?.src || refs.resultImage.getAttribute("src") || "",
      lastResultPrompt: state.lastResultPrompt,
      lastResultModel: state.lastResultModel,
      lastResultMode: state.lastResultMode,
      lastResultImage: state.lastResultImage,
      currentComparisonSource: state.currentComparisonSource,
      rawResponsePreview: state.rawResponsePreview,
      copyrightRisk: state.copyrightRisk,
      textFidelity: state.textFidelity,
      resultCandidates: state.resultCandidates,
      selectedCandidateIndex: state.selectedCandidateIndex,
    },
    source: {
      labelText: refs.sourcePreviewLabel.textContent,
      displayedSourceImage: state.displayedSourceImage,
      editImage: state.editImage,
      editMaskImage: state.editMaskImage,
      generateReferenceImage: state.generateReferenceImage,
      styleReferenceImage: state.styleReferenceImage,
      materialReferenceImage: state.materialReferenceImage,
    },
  }
}

function scheduleWorkspacePersist() {
  if (!state.persistenceReady) {
    return
  }

  window.clearTimeout(state.persistTimer)
  state.persistTimer = window.setTimeout(() => {
    saveWorkspaceSnapshot(createWorkspaceSnapshot()).catch((error) => {
      console.error("Persist workspace failed", error)
    })
  }, 180)
}

async function restoreWorkspaceState() {
  let snapshot

  try {
    snapshot = await loadWorkspaceSnapshot()
  } catch (error) {
    console.error("Restore workspace failed", error)
    return false
  }

  if (!snapshot || typeof snapshot !== "object") {
    return false
  }

  const forms = snapshot.forms || {}
  sanitizeLegacyWorkspacePrompt(forms)
  state.generateIntent = snapshot.generateIntent === "variant" ? "variant" : "fresh"
  refs.generatePromptInput.value = forms.generatePrompt || ""
  refs.generateModelInput.value = forms.generateModel || state.serverConfig.default_model || "gpt-image-2"
  refs.generateWidthInput.value = forms.generateWidth || ""
  refs.generateHeightInput.value = forms.generateHeight || ""
  refs.generateSizePreset.value = forms.generateSizePreset || "custom"
  refs.qualitySelect.value = forms.quality || "high"
  refs.backgroundSelect.value = forms.background || "auto"
  refs.outputFormatSelect.value = forms.outputFormat || "png"
  refs.outputCompressionInput.value = forms.outputCompression || "100"
  refs.moderationSelect.value = forms.moderation || "auto"
  refs.generateSampleCountInput.value = forms.generateSampleCount || ""
  restoreCreativeBrief(forms.creativeBrief || {})
  if (refs.itineraryTitleInput) {
    refs.itineraryTitleInput.value = forms.itineraryTitle || refs.itineraryTitleInput.value
  }
  if (refs.itinerarySubtitleInput) {
    refs.itinerarySubtitleInput.value = forms.itinerarySubtitle || refs.itinerarySubtitleInput.value
  }
  if (refs.itinerarySizeSelect) {
    refs.itinerarySizeSelect.value = forms.itinerarySize || "auto"
  }
  if (refs.itineraryThemeSelect) {
    refs.itineraryThemeSelect.value = forms.itineraryTheme || "comic"
  }
  if (refs.itineraryDescriptionInput) {
    refs.itineraryDescriptionInput.value = forms.itineraryDescription || forms.itineraryStops || refs.itineraryDescriptionInput.value || AI_ITINERARY_EXAMPLE
  }
  if (refs.itineraryLogoEnabled) {
    refs.itineraryLogoEnabled.checked = forms.itineraryLogoEnabled !== false
  }
  if (forms.generateSizePreset === "auto" && !refs.generateWidthInput.value && !refs.generateHeightInput.value) {
    // “自动比例”的快照是空宽高 + preset=auto。先跑 syncSizePresetFromInputs
    // 会把空输入判成 custom，再被下面的默认值填成固定 1088x2240 ——
    // 用户选的自动档就这样在每次刷新后被悄悄改掉。
    setGenerateSize("auto")
  } else {
    syncSizePresetFromInputs()
    if (!refs.generateWidthInput.value || !refs.generateHeightInput.value) {
      setGenerateSize(state.serverConfig.default_size || "auto")
    }
  }

  refs.editPromptInput.value = forms.editPrompt || ""
  refs.editModelInput.value = forms.editModel || state.serverConfig.default_model || "gpt-image-2"
  refs.responsesModelInput.value = normalizeResponsesModel(forms.responsesModel || refs.responsesModelInput.value)
  refs.logoOverlayEnabled.checked = forms.logoOverlayEnabled !== false
  if (refs.itineraryIdEnabled) {
    refs.itineraryIdEnabled.checked = Boolean(forms.itineraryIdEnabled)
  }
  if (refs.itineraryIdInput) {
    refs.itineraryIdInput.value = forms.itineraryId || ""
  }
  updateLogoControlUI()
  updateItineraryIdControlUI()
  if (forms.imageTransport) {
    setImageTransport(forms.imageTransport === "responses" ? "responses" : "images")
  }
  updatePromptCounters()

  const result = snapshot.result || {}
  state.lastResultPrompt = result.lastResultPrompt || ""
  state.lastResultModel = result.lastResultModel || ""
  state.lastResultMode = result.lastResultMode || null
  state.lastResultImage = cloneImageAsset(result.lastResultImage)
  state.currentComparisonSource = cloneImageAsset(result.currentComparisonSource)
  state.resultCandidates = Array.isArray(result.resultCandidates) ? result.resultCandidates : []
  state.selectedCandidateIndex = Number.isInteger(result.selectedCandidateIndex) ? result.selectedCandidateIndex : 0
  state.resultPreview = result.imageSrc
    ? {
        src: result.imageSrc,
        mode: result.lastResultMode || null,
      }
    : null
  state.rawResponsePreview = result.rawResponsePreview || null
  if (result.copyrightRisk && typeof result.copyrightRisk === "object") {
    state.copyrightRisk = result.copyrightRisk
  }
  if (result.textFidelity && typeof result.textFidelity === "object") {
    state.textFidelity = result.textFidelity
  }

  if (state.resultPreview?.src) {
    refs.resultPreviewLabel.textContent = result.labelText || "输出"
    refs.resultImage.src = state.resultPreview.src
    refs.resultImage.classList.add("visible")
    refs.resultPreviewEmpty.classList.add("hidden")
    refs.resultPrompt.textContent = result.promptText || "结果已恢复"
    refs.resultMeta.textContent = result.metaText || ""
    refs.resultTiming.textContent = result.timingText || ""
    refs.resultStorage.textContent = result.storageText || ""
    setDownloadAvailable(
      state.resultPreview.src,
      state.lastResultImage?.name || `picgen-${state.lastResultMode || "result"}-restored.png`,
    )
    renderResultCandidates()
    restoreCopyrightRiskPanel()
    restoreTextFidelityPanel()
  }

  const source = snapshot.source || {}
  state.editImage = cloneImageAsset(source.editImage)
  state.editMaskImage = cloneImageAsset(source.editMaskImage)
  state.generateReferenceImage = cloneImageAsset(source.generateReferenceImage)
  state.styleReferenceImage = cloneImageAsset(source.styleReferenceImage)
  state.materialReferenceImage = cloneImageAsset(source.materialReferenceImage)
  if (!state.materialReferenceImage && state.generateReferenceImage) {
    state.materialReferenceImage = cloneImageAsset(state.generateReferenceImage, {
      role: "material",
      origin: "material",
    })
  }
  state.generateReferenceImage = state.materialReferenceImage || state.styleReferenceImage || state.generateReferenceImage

  if (getAssetDisplaySrc(source.displayedSourceImage)) {
    applySourcePreview(source.displayedSourceImage, source.labelText || "输入图")
  } else {
    clearSourcePreview(source.labelText || "原图")
  }

  renderRawResponsePreview()
  renderResultCandidates()
  setMode(snapshot.activeMode || "generate", { autoLoadLatest: false })
  updateGenerateIntentUI()
  updateGenerateReferenceUI()
  updateEditSourceUI()
  updateEditMaskUI()
  updateOpenAIOptionUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  return true
}

function sanitizeLegacyWorkspacePrompt(forms) {
  if (!forms || typeof forms !== "object") {
    return false
  }
  if (!isLegacyProgramLayoutBackgroundPrompt(forms.generatePrompt)) {
    return false
  }
  forms.generatePrompt = ""
  setStatusMessage("已清空旧程序排版背景底图提示词，请输入要直接生成的完整海报文案。")
  return true
}

function cloneImageAsset(asset, overrides = {}) {
  if (!asset) {
    return null
  }
  return { ...asset, ...overrides }
}

function modelInputAssetForLogoWorkflow(asset) {
  if (!asset?.logoOverlayApplied) {
    return asset
  }

  const source = {
    ...asset,
    name: imageDataUrlName(asset.name || "picgen-result.png", "base"),
    dataUrl: asset.originalDataUrl || "",
    savedUrl: asset.originalSavedUrl || "",
    fileUrl: asset.originalFileUrl || "",
    src: asset.originalDataUrl || asset.originalSavedUrl || asset.originalFileUrl || "",
    savedPath: asset.originalSavedPath || asset.savedPath || "",
    generatedImageId: asset.generatedImageId || null,
    sourceGeneratedImageId: asset.sourceGeneratedImageId || null,
    logoOverlayApplied: false,
    description: `未贴 LOGO 的生成主体图 · ${asset.name || "最新结果"}`,
  }
  return getAssetDisplaySrc(source) ? source : asset
}

function getAssetDisplaySrc(asset) {
  return asset?.savedUrl || asset?.dataUrl || asset?.fileUrl || asset?.src || ""
}

function sourceImageIdentityFields(asset) {
  return {
    source_saved_image_url: asset?.savedUrl || asset?.fileUrl || asset?.src || "",
    source_saved_image_path: asset?.savedPath || "",
    source_original_saved_image_url: asset?.originalSavedUrl || "",
    source_original_saved_image_path: asset?.originalSavedPath || "",
  }
}

function shareToAsset(share) {
  const imageSrc = share?.saved_image_url || ""
  if (!imageSrc) {
    return null
  }
  return {
    name: `shared-${share.id || Date.now()}.png`,
    type: "",
    dataUrl: "",
    savedUrl: imageSrc,
    savedPath: share.saved_image_path || "",
    fileUrl: imageSrc,
    origin: "share",
    description: `来自 ${share.sender_username || "用户"} 的分享`,
    src: imageSrc,
  }
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return ""
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }
  return `${Math.round(bytes / 1024)} KB`
}

function formatCharacterCount(text) {
  return `${(text || "").trim().length} 字`
}

function updatePromptCounters() {
  refs.generatePromptCount.textContent = formatCharacterCount(refs.generatePromptInput.value)
  refs.editPromptCount.textContent = formatCharacterCount(refs.editPromptInput.value)
}

function isLikelyVariationPrompt(prompt) {
  const normalized = (prompt || "").trim()
  if (!normalized || !state.lastResultImage) {
    return false
  }

  const compact = normalized.replace(/\s+/g, "")
  const strongPatterns = [
    /换个?风格/,
    /改成.+风格/,
    /保持.+不变/,
    /主体.+不变/,
    /只改/,
    /换一种/,
    /继续.+调整/,
  ]

  if (strongPatterns.some((pattern) => pattern.test(compact))) {
    return true
  }

  if (compact.length <= 24 && /(换|改|调|风格|色调|光线|氛围|材质|背景|镜头|构图)/.test(compact)) {
    return true
  }

  return false
}

function setGenerateIntent(intent) {
  state.generateIntent = intent === "variant" ? "variant" : "fresh"
  updateGenerateIntentUI()
  scheduleWorkspacePersist()
}

function updateGenerateIntentUI() {
  const hasResultAnchor = Boolean(state.lastResultImage)
  const isVariant = state.generateIntent === "variant"
  const hasReference = Boolean(state.generateReferenceImage || state.materialReferenceImage || state.styleReferenceImage)

  refs.freshGenerateMode.classList.toggle("active", !isVariant)
  refs.variantGenerateMode.classList.toggle("active", isVariant)
  refs.variantGenerateMode.disabled = !hasResultAnchor

  if (!hasResultAnchor && isVariant) {
    state.generateIntent = "fresh"
  }

  refs.freshGenerateMode.classList.toggle("active", state.generateIntent === "fresh")
  refs.variantGenerateMode.classList.toggle("active", state.generateIntent === "variant")

  refs.variantSourceCard.classList.toggle("hidden", !(hasResultAnchor && state.generateIntent === "variant"))
  refs.variantSourceName.textContent = hasResultAnchor
    ? `${state.lastResultImage.name || "最新结果"}`
    : "尚未生成结果"

  refs.generateIntentHint.textContent = state.generateIntent === "variant"
    ? "当前会拿最新结果做参考图，适合“换个风格、改灯光、换质感”，尽量保持上一张图的主体关系。"
    : hasReference
      ? "全新开题会带上你添加的参考图，经由编辑接口生成；提示词仍按新主题处理。"
      : "全新开题会忽略当前结果，适合重新换题。若只是想换风格、光线、材质或色调，请用“基于当前结果延展”。"

  refs.variantSuggestion.classList.toggle(
    "hidden",
    !(hasResultAnchor && state.generateIntent === "fresh" && isLikelyVariationPrompt(refs.generatePromptInput.value)),
  )

  refs.generateButton.textContent = state.generateIntent === "variant"
    ? "基于当前结果延展"
    : hasReference
      ? "参考图生成"
      : "开始海报生成"
  updateGenerateSampleCountUI()
}

function generateReferenceImages() {
  if (state.styleReferenceImage || state.materialReferenceImage) {
    return [state.styleReferenceImage, state.materialReferenceImage].filter(Boolean)
  }
  return state.generateReferenceImage ? [state.generateReferenceImage] : []
}

function hasStyleTransferReferences() {
  return Boolean(state.styleReferenceImage && state.materialReferenceImage)
}

function styleTransferPrompt(userPrompt) {
  return [
    "使用第 1 张图片作为风格模板，提取它的视觉风格、材质质感、光影、色调、排版氛围和整体艺术方向。",
    "同时识别第 1 张风格模板中有明确品牌或活动含义的视觉元素，例如 6人游 Logo、2022、冬奥会相关文字、徽章、角标、标题、装饰条和版式结构；请把这些元素放到最终成品中合适且自然的位置。",
    "使用第 2 张图片作为素材主体，保留它的主体结构、人物/物体身份、关键文字、Logo、比例关系和可识别特征。",
    "请把第 2 张素材图转换成第 1 张风格模板的完整视觉效果，让模板里的品牌/活动信息与素材画面融合成一张最终效果图。",
    "不要生成左右对比图，不要把两张参考图并排放入结果。不要机械复制模板里无意义的小噪点；只迁移有设计价值或品牌/活动含义的文字和图形元素。输出完整单张成品图。",
    userPrompt.trim(),
  ].filter(Boolean).join("\n")
}

function updateWorkflowStatus() {
  const hasResult = Boolean(state.resultPreview?.src)
  const hasSource = Boolean(getAssetDisplaySrc(state.displayedSourceImage))
  refs.resultActions?.classList.toggle("hidden", !hasResult)
  refs.resultHoverActions?.classList.toggle("hidden", !hasResult)
  refs.comparisonGrid?.classList.toggle("single-result", !hasSource)
  refs.sourcePreviewCard?.classList.toggle("hidden", !hasSource)
  updateResultActionSurface()
}

function appendPromptSnippet(target, snippet) {
  const input = target === "edit" ? refs.editPromptInput : refs.generatePromptInput
  const currentValue = input.value
  const normalized = currentValue.trim()
  input.value = normalized ? `${currentValue.trimEnd()}，${snippet}` : snippet
  input.focus()
  updatePromptCounters()
  scheduleWorkspacePersist()
}

function focusActivePrompt() {
  const target = state.activeMode === "edit" ? refs.editPromptInput : refs.generatePromptInput
  target.focus()
}

function isTypingElement(element) {
  if (!element) {
    return false
  }

  const tagName = element.tagName?.toLowerCase()
  return tagName === "input" || tagName === "textarea" || element.isContentEditable
}

function saveSettings() {
  const local = loadJSON(settingsStorageKey(), {})
  const legacy = loadJSON(legacySettingsStorageKey(), {})
  const newApiKey = refs.apiKeyInput.value.trim()
  const nextApiKey = newApiKey || local.apiKey || legacy.apiKey || ""
  state.savedApiKey = nextApiKey
  const payload = {
    apiKey: nextApiKey,
    generateUrl: refs.generateUrlInput.value.trim(),
    editUrl: refs.editUrlInput.value.trim(),
    responsesUrl: refs.responsesUrlInput.value.trim(),
    responsesModel: refs.responsesModelInput.value.trim(),
    imageTransport: getImageTransport(),
  }
  saveJSON(settingsStorageKey(), payload)
  refs.apiKeyInput.value = ""
  flashHint(newApiKey ? "新 API Key 已保存在当前浏览器本地；输入框已清空，不会回显 key。" : "设置已保存；API Key 未变更。")
  void syncUserPreferences()
  updateWorkflowStatus()
}

function loadSettings() {
  const local = loadJSON(settingsStorageKey(), {})
  const legacy = loadJSON(legacySettingsStorageKey(), {})
  const prefs = state.userPreferences || {}
  const localResponsesUrl = local.responsesUrl || ""
  const responsesUrl = DEPRECATED_RESPONSES_URLS.has(localResponsesUrl) && state.serverConfig.responses_url
    ? state.serverConfig.responses_url
    : localResponsesUrl || state.serverConfig.responses_url || ""
  state.savedApiKey = local.apiKey || legacy.apiKey || ""
  refs.apiKeyInput.value = ""
  refs.generateUrlInput.value = local.generateUrl || legacy.generateUrl || state.serverConfig.generate_url || ""
  refs.editUrlInput.value = local.editUrl || legacy.editUrl || state.serverConfig.edit_url || ""
  refs.responsesUrlInput.value = responsesUrl
  refs.responsesModelInput.value = normalizeResponsesModel(
    local.responsesModel || prefs.default_responses_model || state.serverConfig.default_responses_model,
  )

  refs.generateModelInput.value = prefs.default_model || state.serverConfig.default_model || "gpt-image-2"
  refs.editModelInput.value = prefs.default_model || state.serverConfig.default_model || "gpt-image-2"
  setGenerateSize(prefs.default_size || state.serverConfig.default_size || "auto")
  if (prefs.default_quality) {
    refs.qualitySelect.value = prefs.default_quality
  }
  if (prefs.default_output_format) {
    refs.outputFormatSelect.value = prefs.default_output_format
  }
  if (typeof prefs.logo_overlay_enabled === "boolean") {
    refs.logoOverlayEnabled.checked = prefs.logo_overlay_enabled
  }
  setImageTransport(local.imageTransport || prefs.default_image_transport || "images")

  if (state.savedApiKey) {
    refs.settingsHint.textContent = "浏览器本地已保存 API Key。输入框只用于填入新 key，不会回显现有 key。"
  } else if (state.serverConfig.has_default_api_key) {
    refs.settingsHint.textContent = "服务端已预设默认 API Key。你可以在这里填入新 key 覆盖。"
  }

  updateWorkflowStatus()
}

function currentUserPreferencesPayload() {
  let size = ""
  try {
    size = getGenerateSize()
  } catch {
    size = getSizeSnapshotValue()
  }
  // 半填状态下快照可能是 "custom" 这类占位字符串；存进服务端偏好后
  // 下次登录会被静默解析成 1024x1024。只持久化合法的尺寸值。
  if (size !== "auto" && !/^\d+x\d+$/.test(size)) {
    size = ""
  }
  return {
    default_model: refs.generateModelInput.value.trim(),
    default_responses_model: normalizeResponsesModel(refs.responsesModelInput.value),
    default_size: size,
    default_quality: refs.qualitySelect.value || "",
    default_output_format: refs.outputFormatSelect.value || "",
    default_image_transport: getImageTransport(),
    logo_overlay_enabled: refs.logoOverlayEnabled.checked,
    auto_copyright_check_enabled: true,
  }
}

async function loadUserPreferences() {
  if (state.serverConfig?.auth_enabled === false || !state.currentUser) {
    state.userPreferences = null
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/preferences", { cache: "no-store" })
    state.userPreferences = response.ok ? data.preferences || null : null
  } catch {
    state.userPreferences = null
  }
}

async function syncUserPreferences({ quiet = true } = {}) {
  if (state.serverConfig?.auth_enabled === false || !state.currentUser) {
    return
  }
  try {
    const { response, data } = await fetchJSON("/api/preferences", {
      method: "PUT",
      body: JSON.stringify(currentUserPreferencesPayload()),
    })
    if (response.ok) {
      state.userPreferences = data.preferences || null
      return
    }
    if (!quiet) {
      flashHint(data.error || "偏好保存失败，本地配置仍已保存。")
    }
  } catch {
    if (!quiet) {
      flashHint("偏好保存暂时不可用，本地配置仍已保存。")
    }
  }
}

function getImageTransport() {
  const checked = refs.imageTransportInputs.find((input) => input.checked)
  return checked?.value === "responses" ? "responses" : "images"
}

function setImageTransport(value) {
  const normalized = value === "responses" ? "responses" : "images"
  refs.imageTransportInputs.forEach((input) => {
    input.checked = input.value === normalized
  })
  updateImageTransportUI()
}

function updateImageTransportUI() {
  const transport = getImageTransport()
  const isResponses = transport === "responses"
  if (refs.imageTransportHint) {
    refs.imageTransportHint.textContent = isResponses
      ? "编辑、参考图、延展会走 Responses + image_generation 工具（默认 gpt-5.5），用于对接不支持 Images Edit 的兼容代理。"
      : "编辑、参考图、延展默认走图像通道 + gpt-image-2，更稳定也更便宜。"
  }
  const editFieldset = refs.responsesUrlInput?.closest("label")
  const modelFieldset = refs.responsesModelInput?.closest("label")
  ;[editFieldset, modelFieldset].forEach((node) => {
    if (!node) return
    node.classList.toggle("is-dimmed", !isResponses)
  })
}

function flashHint(text) {
  refs.settingsHint.textContent = text
  window.clearTimeout(flashHint.timeoutId)
  flashHint.timeoutId = window.setTimeout(() => {
    if (state.savedApiKey) {
      refs.settingsHint.textContent = "浏览器本地已保存 API Key。输入框只用于填入新 key，不会回显现有 key。"
      return
    }
    if (state.serverConfig?.has_default_api_key) {
      refs.settingsHint.textContent = "服务端已预设默认 API Key。你可以在这里填入新 key 覆盖。"
      return
    }
    refs.settingsHint.textContent = "API Key 仅保存在当前浏览器本地存储；输入框只用于填入新 key，不会回显现有 key。"
  }, 2200)
}

function getSettings() {
  return {
    apiKey: refs.apiKeyInput.value.trim() || state.savedApiKey || "",
    generateUrl: refs.generateUrlInput.value.trim(),
    editUrl: refs.editUrlInput.value.trim(),
    responsesUrl: refs.responsesUrlInput.value.trim(),
    responsesModel: normalizeResponsesModel(refs.responsesModelInput.value),
    imageTransport: getImageTransport(),
  }
}

function updateLogoControlUI() {
  refs.logoComposeStatus.textContent = refs.logoOverlayEnabled.checked ? "本地贴图" : "未启用"
  updateGenerateSampleCountUI()
}

function shouldUseCompanyLogo() {
  return Boolean(refs.logoOverlayEnabled?.checked)
}

function updateItineraryIdControlUI() {
  const enabled = Boolean(refs.itineraryIdEnabled?.checked)
  if (refs.itineraryIdInput) {
    refs.itineraryIdInput.disabled = !enabled
  }
}

function getExplicitItineraryId() {
  if (!refs.itineraryIdEnabled?.checked) {
    return ""
  }
  return (refs.itineraryIdInput?.value || "").trim()
}

function withTextRenderingFidelityPrompt(prompt) {
  const basePrompt = String(prompt || "").trim()
  const textContract = buildVisibleTextContract(basePrompt)
  return [
    basePrompt,
    TEXT_RENDERING_FIDELITY_PROMPT,
    formatVisibleTextContractPrompt(textContract),
  ].filter(Boolean).join("\n\n")
}

function withLogoLayoutPrompt(prompt, logoRequested = shouldUseCompanyLogo()) {
  const requestText = String(prompt || "").trim()
  const textLockedPrompt = withTextRenderingFidelityPrompt(requestText)
  return logoRequested ? `${textLockedPrompt}\n\n${COMPANY_LOGO_LAYOUT_PROMPT}` : textLockedPrompt
}

function withEditPreservePrompt(prompt, logoRequested = shouldUseCompanyLogo()) {
  const basePrompt = withTextRenderingFidelityPrompt(prompt)
  const logoInstruction = logoRequested ? COMPANY_LOGO_LAYOUT_PROMPT : ""
  return [basePrompt, EDIT_PRESERVE_PROMPT, logoInstruction].filter(Boolean).join("\n\n")
}

function updatePromptConfirmButtonState() {
  if (!refs.submitPromptConfirmButton) {
    return
  }
  const hasText = Boolean(refs.promptConfirmTextInput?.value.trim())
  refs.submitPromptConfirmButton.disabled = !(refs.promptConfirmCheckbox && refs.promptConfirmCheckbox.checked && hasText)
}

function closePromptConfirmModal() {
  refs.promptConfirmModal?.classList.add("hidden")
  refs.promptConfirmModal?.setAttribute("aria-hidden", "true")
  refs.promptConfirmCheckbox && (refs.promptConfirmCheckbox.checked = false)
  document.body.classList.remove("modal-open")
  updatePromptConfirmButtonState()
}

function openPromptConfirmModal({ title, description, text }) {
  if (!refs.promptConfirmModal || !refs.promptConfirmTextInput) {
    return Promise.resolve(String(text || "").trim())
  }
  refs.promptConfirmTitle.textContent = title || "提交前确认提示词"
  refs.promptConfirmDescription.textContent = description || "请检查标题、地名、日期、正文和标点。"
  refs.promptConfirmTextInput.value = String(text || "").trim()
  if (refs.promptConfirmCheckbox) {
    refs.promptConfirmCheckbox.checked = false
  }
  refs.promptConfirmModal.classList.remove("hidden")
  refs.promptConfirmModal.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
  updatePromptConfirmButtonState()
  refs.promptConfirmTextInput.focus()
  refs.promptConfirmTextInput.setSelectionRange(0, 0)

  return new Promise((resolve) => {
    const cleanup = () => {
      refs.submitPromptConfirmButton?.removeEventListener("click", handleSubmit)
      refs.cancelPromptConfirmButton?.removeEventListener("click", handleCancel)
      refs.closePromptConfirmButton?.removeEventListener("click", handleCancel)
      refs.promptConfirmBackdrop?.removeEventListener("click", handleCancel)
    }
    const handleSubmit = () => {
      const confirmedText = refs.promptConfirmTextInput.value.trim()
      if (!refs.promptConfirmCheckbox?.checked || !confirmedText) {
        updatePromptConfirmButtonState()
        return
      }
      cleanup()
      closePromptConfirmModal()
      resolve(confirmedText)
    }
    const handleCancel = () => {
      cleanup()
      closePromptConfirmModal()
      resolve(null)
    }
    refs.submitPromptConfirmButton?.addEventListener("click", handleSubmit)
    refs.cancelPromptConfirmButton?.addEventListener("click", handleCancel)
    refs.closePromptConfirmButton?.addEventListener("click", handleCancel)
    refs.promptConfirmBackdrop?.addEventListener("click", handleCancel)
  })
}

async function confirmPromptBeforeRun(kind, text) {
  const labels = {
    generate: {
      title: "生成海报前确认提示词",
      description: "请逐字检查海报标题、地名、日期、正文、序号和底部贴士。",
    },
    itinerary: {
      title: "生成路线图前确认提示词",
      description: "请逐字检查行程日期、地点、酒店、交通和每日说明。",
    },
    edit: {
      title: "开始编辑前确认提示词",
      description: "请逐字检查本次要修改的内容；模型会尽量只改这些文字描述的部分。",
    },
  }
  return openPromptConfirmModal({ ...(labels[kind] || labels.generate), text })
}

function updateGenerateSampleCountUI() {
  const hasReference = Boolean(generateReferenceImages().length)
  const isVariant = state.generateIntent === "variant"
  const disabled = hasReference || isVariant
  refs.generateSampleCountInput.disabled = disabled
  refs.generateSampleCountInput.closest("label")?.classList.toggle("is-disabled", disabled)

  if (isVariant) {
    refs.generateSampleCountHint.textContent = "基于当前结果延展固定 1 张。"
  } else if (hasReference) {
    refs.generateSampleCountHint.textContent = hasStyleTransferReferences()
      ? "模板 + 素材图仍按现有逻辑默认 3 张。"
      : "带参考图生成固定 1 张。"
  } else {
    refs.generateSampleCountHint.textContent = "纯文字生图可填 1-3；留空默认 1。"
  }
}

function requireEditSettings(settings, contextLabel) {
  if (!settings.editUrl) {
    appendDebugLine("参数校验失败：编辑接口 URL 为空")
    setError(`${contextLabel}需要填写编辑接口 URL（/v1/images/edits）。`)
    refs.editUrlInput.focus()
    return false
  }
  return true
}

function normalizeResponsesModel(value) {
  const model = String(value || "").trim()
  if (!model || DEPRECATED_RESPONSES_MODELS.has(model)) {
    return state.serverConfig?.default_responses_model || "gpt-5.5"
  }
  return model
}

function requireResponsesSettings(settings, contextLabel) {
  if (!settings.responsesUrl) {
    appendDebugLine("参数校验失败：Responses 图像接口 URL 为空")
    setError(`${contextLabel}需要填写 Responses 图像接口 URL。`)
    refs.responsesUrlInput.focus()
    return false
  }
  if (!settings.responsesModel) {
    appendDebugLine("参数校验失败：Responses 主模型为空")
    setError(`${contextLabel}需要填写 Responses 主模型。`)
    refs.responsesModelInput.focus()
    return false
  }
  return true
}

function formatTimestamp(isoLike) {
  const date = new Date(isoLike)
  if (Number.isNaN(date.getTime())) {
    return ""
  }
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function parseSizeValue(size) {
  const matched = /^(\d+)x(\d+)$/i.exec(String(size || "").trim())
  if (!matched) {
    return null
  }

  const width = Number.parseInt(matched[1], 10)
  const height = Number.parseInt(matched[2], 10)

  if (!Number.isInteger(width) || !Number.isInteger(height)) {
    return null
  }

  return { width, height }
}

function formatSizeValue(width, height) {
  return `${width}x${height}`
}

function formatActualSize(payload) {
  const width = Number(payload.saved_image_width)
  const height = Number(payload.saved_image_height)
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return ""
  }
  return formatSizeValue(width, height)
}

function isSameSize(requestedSize, actualSize) {
  const requested = parseSizeValue(requestedSize)
  const actual = parseSizeValue(actualSize)
  return Boolean(requested && actual && requested.width === actual.width && requested.height === actual.height)
}

function setGenerateSize(size) {
  if (String(size || "").trim() === "auto") {
    refs.generateWidthInput.value = ""
    refs.generateHeightInput.value = ""
    refs.generateSizePreset.value = "auto"
    updateVisualSizePicker("auto")
    return
  }
  const parsed = parseSizeValue(size) || { width: 1024, height: 1024 }
  refs.generateWidthInput.value = String(parsed.width)
  refs.generateHeightInput.value = String(parsed.height)
  refs.generateSizePreset.value = SIZE_PRESETS.includes(formatSizeValue(parsed.width, parsed.height))
    ? formatSizeValue(parsed.width, parsed.height)
    : "custom"
  updateVisualSizePicker(refs.generateSizePreset.value)
}

function syncSizePresetFromInputs() {
  const width = Number.parseInt(refs.generateWidthInput.value, 10)
  const height = Number.parseInt(refs.generateHeightInput.value, 10)
  if (!Number.isInteger(width) || !Number.isInteger(height)) {
    refs.generateSizePreset.value = "custom"
    return
  }
  const value = formatSizeValue(width, height)
  refs.generateSizePreset.value = SIZE_PRESETS.includes(value) ? value : "custom"
  updateVisualSizePicker(refs.generateSizePreset.value === "custom" ? value : refs.generateSizePreset.value)
}

function getGenerateSize() {
  if (refs.generateSizePreset.value === "auto" && !refs.generateWidthInput.value && !refs.generateHeightInput.value) {
    return "auto"
  }

  const width = Number.parseInt(refs.generateWidthInput.value, 10)
  const height = Number.parseInt(refs.generateHeightInput.value, 10)

  if (!Number.isInteger(width) || !Number.isInteger(height)) {
    throw new Error("请填写有效的宽高尺寸。")
  }

  if (width < 64 || height < 64) {
    throw new Error("宽高都不能小于 64。")
  }

  if (width > 3840 || height > 3840) {
    throw new Error("宽高都不能超过 3840。")
  }

  const ratio = Math.max(width, height) / Math.min(width, height)
  if (ratio > 3) {
    throw new Error("宽高比例不能超过 3:1。")
  }

  return formatSizeValue(width, height)
}

function shouldUseResponsesForSelectedSize(size) {
  return !IMAGES_API_EXACT_SIZES.has(String(size || "").trim() || "auto")
}

function updateVisualSizePicker(value) {
  refs.visualSizeInputs.forEach((input) => {
    const selected = input.value === value
    input.checked = selected
    input.closest("label")?.classList.toggle("selected", selected)
  })
}

function getOpenAIImageOptions() {
  const outputFormat = refs.outputFormatSelect.value || "png"

  const options = {
    quality: refs.qualitySelect.value || "high",
    background: refs.backgroundSelect.value || "auto",
    output_format: outputFormat,
    moderation: refs.moderationSelect.value || "auto",
  }

  // 只有 jpeg/webp 才发送压缩质量；png 下该输入框是禁用的，用户清空后
  // 无法再编辑，如果照样校验会把整个生成流程卡死在一个灰色字段上。
  if (["jpeg", "webp"].includes(outputFormat)) {
    const outputCompression = Number.parseInt(refs.outputCompressionInput.value, 10)
    if (!Number.isInteger(outputCompression) || outputCompression < 0 || outputCompression > 100) {
      throw new Error("输出压缩质量必须在 0 到 100 之间。")
    }
    options.output_compression = outputCompression
  }

  return options
}

function currentFormSnapshot() {
  return {
    activeMode: state.activeMode,
    generateIntent: state.generateIntent,
    imageTransport: getImageTransport(),
    promptMode: state.promptMode,
    promptRecipeId: refs.promptRecipeSelect?.value || state.selectedRecipeId || "",
    generatePrompt: refs.generatePromptInput.value,
    generateModel: refs.generateModelInput.value,
    generateSize: getSizeSnapshotValue(),
    quality: refs.qualitySelect.value,
    background: refs.backgroundSelect.value,
    outputFormat: refs.outputFormatSelect.value,
    outputCompression: refs.outputCompressionInput.value,
    moderation: refs.moderationSelect.value,
    generateSampleCount: refs.generateSampleCountInput.value,
    creativeBrief: creativeBriefSnapshot(),
    itineraryTitle: refs.itineraryTitleInput?.value || "",
    itinerarySubtitle: refs.itinerarySubtitleInput?.value || "",
    itinerarySize: refs.itinerarySizeSelect?.value || "auto",
    itineraryTheme: refs.itineraryThemeSelect?.value || "comic",
    itineraryDescription: refs.itineraryDescriptionInput?.value || "",
    itineraryLogoEnabled: refs.itineraryLogoEnabled?.checked !== false,
    logoOverlayEnabled: refs.logoOverlayEnabled.checked,
    itineraryIdEnabled: refs.itineraryIdEnabled?.checked || false,
    itineraryId: refs.itineraryIdInput?.value || "",
    editPrompt: refs.editPromptInput.value,
    editModel: refs.editModelInput.value,
  }
}

function getSizeSnapshotValue() {
  if (refs.generateSizePreset.value === "auto" && !refs.generateWidthInput.value && !refs.generateHeightInput.value) {
    return "auto"
  }
  if (refs.generateWidthInput.value && refs.generateHeightInput.value) {
    return `${refs.generateWidthInput.value}x${refs.generateHeightInput.value}`
  }
  return refs.generateSizePreset.value || "auto"
}

function applyFormSnapshot(snapshot) {
  if (!snapshot) {
    return
  }
  setImageTransport(snapshot.imageTransport || "images")
  state.promptMode = snapshot.promptMode || "free"
  refs.promptModeInputs.forEach((input) => {
    input.checked = input.value === state.promptMode
  })
  state.selectedRecipeId = snapshot.promptRecipeId || ""
  if (refs.promptRecipeSelect) {
    refs.promptRecipeSelect.value = state.selectedRecipeId
  }
  refs.generatePromptInput.value = snapshot.generatePrompt || ""
  refs.generateModelInput.value = snapshot.generateModel || state.serverConfig?.default_model || "gpt-image-2"
  setGenerateSize(snapshot.generateSize || "auto")
  refs.qualitySelect.value = snapshot.quality || "high"
  refs.backgroundSelect.value = snapshot.background || "auto"
  refs.outputFormatSelect.value = snapshot.outputFormat || "png"
  refs.outputCompressionInput.value = snapshot.outputCompression || "100"
  refs.moderationSelect.value = snapshot.moderation || "auto"
  refs.generateSampleCountInput.value = snapshot.generateSampleCount || ""
  restoreCreativeBrief(snapshot.creativeBrief || {})
  if (refs.itineraryTitleInput) {
    refs.itineraryTitleInput.value = snapshot.itineraryTitle || refs.itineraryTitleInput.value
  }
  if (refs.itinerarySubtitleInput) {
    refs.itinerarySubtitleInput.value = snapshot.itinerarySubtitle || refs.itinerarySubtitleInput.value
  }
  if (refs.itinerarySizeSelect) {
    refs.itinerarySizeSelect.value = snapshot.itinerarySize || "auto"
  }
  if (refs.itineraryThemeSelect) {
    refs.itineraryThemeSelect.value = snapshot.itineraryTheme || "comic"
  }
  if (refs.itineraryDescriptionInput) {
    refs.itineraryDescriptionInput.value = snapshot.itineraryDescription || snapshot.itineraryStops || refs.itineraryDescriptionInput.value || AI_ITINERARY_EXAMPLE
  }
  if (refs.itineraryLogoEnabled) {
    refs.itineraryLogoEnabled.checked = snapshot.itineraryLogoEnabled !== false
  }
  refs.logoOverlayEnabled.checked = snapshot.logoOverlayEnabled !== false
  if (refs.itineraryIdEnabled) {
    refs.itineraryIdEnabled.checked = Boolean(snapshot.itineraryIdEnabled)
  }
  if (refs.itineraryIdInput) {
    refs.itineraryIdInput.value = snapshot.itineraryId || ""
  }
  refs.editPromptInput.value = snapshot.editPrompt || ""
  refs.editModelInput.value = snapshot.editModel || state.serverConfig?.default_model || "gpt-image-2"
  setGenerateIntent(snapshot.generateIntent || "fresh")
  setMode(snapshot.activeMode || "generate", { autoLoadLatest: false })
  updateLogoControlUI()
  updateItineraryIdControlUI()
  updatePromptCounters()
  updatePromptModeUI()
}

function rememberRegenerationRequest(kind, snapshot) {
  state.lastRegenerationRequest = {
    kind,
    snapshot: { ...snapshot },
  }
}

async function rerunLastGeneration() {
  if (state.isBusy) {
    return
  }
  if (!state.lastRegenerationRequest) {
    setError("当前没有可复用的生成参数。")
    return
  }
  const currentSnapshot = currentFormSnapshot()
  const { kind, snapshot } = state.lastRegenerationRequest
  try {
    applyFormSnapshot(snapshot)
    if (kind === "edit") {
      await submitEdit()
    } else if (kind === "itinerary") {
      await submitAIItineraryMap()
    } else {
      await submitGenerate()
    }
  } finally {
    applyFormSnapshot(currentSnapshot)
  }
}

function getGenerateSampleCount() {
  const rawValue = refs.generateSampleCountInput.value.trim()
  if (!rawValue) {
    return 1
  }
  const parsed = Number(rawValue)
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 3) {
    throw new Error("生成数量必须在 1 到 3 之间。")
  }
  return parsed
}

function updateOpenAIOptionUI() {
  const supportsCompression = ["jpeg", "webp"].includes(refs.outputFormatSelect.value)
  refs.outputCompressionInput.disabled = !supportsCompression
  refs.outputCompressionInput.closest("label")?.classList.toggle("is-disabled", !supportsCompression)

  const model = refs.generateModelInput.value.trim()
  const isGptImage2 = model === "gpt-image-2"
  if (isGptImage2 && refs.backgroundSelect.value === "transparent") {
    refs.backgroundSelect.value = "auto"
    setError("gpt-image-2 不支持透明背景，已切回 Auto。需要透明 PNG 时请选择支持透明背景的图片模型。")
  }
}

function applyOpenAIOptions(payload) {
  return {
    ...payload,
    ...getOpenAIImageOptions(),
  }
}

function inferMimeFromDataUrl(dataUrl) {
  const matched = /^data:([^;]+);base64,/i.exec(dataUrl || "")
  return matched?.[1] || "image/png"
}

function estimateProgress(elapsedMs, phase) {
  if (phase === "preparing") {
    return Math.min(18, 6 + elapsedMs / 180)
  }
  if (phase === "uploading") {
    return Math.min(34, 18 + elapsedMs / 240)
  }
  if (phase === "waiting") {
    return Math.min(78, 34 + elapsedMs / 1250)
  }
  if (phase === "receiving") {
    return Math.min(92, 78 + elapsedMs / 500)
  }
  return 0
}

function progressHintForPhase(phase, label) {
  const expectedCount = Math.max(1, Number(state.progressExpectedCount) || 1)
  if (phase === "waiting" && expectedCount > 1 && state.progressStartedAt) {
    const elapsedSeconds = Math.max(0, (performance.now() - state.progressStartedAt) / 1000)
    const estimatePerImage = Math.max(60, Number(state.progressEstimatedSecondsPerImage) || 210)
    const estimatedTotal = estimatePerImage * expectedCount
    const currentImage = Math.min(expectedCount, Math.max(1, Math.floor(elapsedSeconds / estimatePerImage) + 1))
    const remainingSeconds = Math.max(0, estimatedTotal - elapsedSeconds)
    return `正在生成第 ${currentImage}/${expectedCount} 张，预计还需要约 ${formatDuration(remainingSeconds)} 完成全部候选。`
  }
  if (phase === "preparing") {
    return "正在整理参数和本地输入。"
  }
  if (phase === "uploading") {
    return "请求已交给本地代理，正在连接上游接口。"
  }
  if (phase === "waiting") {
    return UPSTREAM_RETRY_HINT
  }
  if (phase === "receiving") {
    return "上游已响应，正在解析结果并保存到本地。"
  }
  return label || "等待操作。"
}

function formatDuration(seconds) {
  const safeSeconds = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(safeSeconds / 60)
  const rest = safeSeconds % 60
  if (minutes <= 0) {
    return `${rest} 秒`
  }
  return `${minutes} 分 ${rest} 秒`
}

function renderProgress() {
  if (!state.progressStartedAt) {
    return
  }

  const elapsedMs = performance.now() - state.progressStartedAt
  const progress = estimateProgress(elapsedMs, state.progressPhase)
  const hint = progressHintForPhase(state.progressPhase, state.progressLabel)
  refs.requestProgressFill.style.width = `${progress.toFixed(1)}%`
  refs.progressElapsed.textContent = `${(elapsedMs / 1000).toFixed(1)}s`
  refs.resultTiming.textContent = `请求进行中 ${(elapsedMs / 1000).toFixed(1)}s`
  refs.progressStageLabel.textContent = state.progressLabel || "处理中"
  refs.progressHint.textContent = hint
  if (state.progressPhase === "waiting") {
    refs.resultPreviewEmpty.textContent = hint
  }
  refs.generationOverlayTitle.textContent = state.progressLabel || "处理中"
  refs.generationOverlaySubtitle.textContent = hint
  renderGenerationOverlaySteps(state.progressPhase)
  refs.generationOrbit?.style.setProperty("--progress-degrees", `${(progress * 3.6).toFixed(1)}deg`)
  refs.generationOrbit?.setAttribute("data-progress", `${Math.round(progress)}%`)
}

function renderGenerationOverlaySteps(activePhase = state.progressPhase) {
  const order = ["preparing", "uploading", "waiting", "receiving"]
  const activeIndex = Math.max(0, order.indexOf(activePhase))
  refs.generationOverlaySteps?.querySelectorAll("[data-progress-step]").forEach((item) => {
    const step = item.dataset.progressStep || ""
    const stepIndex = order.indexOf(step)
    item.classList.toggle("active", stepIndex === activeIndex || (step === "waiting" && activePhase === "uploading"))
    item.classList.toggle("done", stepIndex >= 0 && stepIndex < activeIndex)
  })
}

function updateGenerationOverlay(title, subtitle, phase = state.progressPhase) {
  if (refs.generationOverlayTitle) {
    refs.generationOverlayTitle.textContent = title
  }
  if (refs.generationOverlaySubtitle) {
    refs.generationOverlaySubtitle.textContent = subtitle
  }
  renderGenerationOverlaySteps(phase)
}

function setProgressPhase(phase, label) {
  if (!state.isBusy) {
    return
  }
  state.progressPhase = phase
  state.progressLabel = label
  updateGenerationOverlay(label, progressHintForPhase(phase, label), phase)
  renderProgress()
}

function startProgress(label, options = {}) {
  window.clearInterval(state.progressTimer)
  state.progressStartedAt = performance.now()
  state.progressPhase = "preparing"
  state.progressLabel = label
  state.progressExpectedCount = Math.max(1, Number(options.expectedCount) || 1)
  state.progressEstimatedSecondsPerImage = Math.max(60, Number(options.estimatedSecondsPerImage) || 210)
  refs.progressInspectorItem.classList.remove("hidden")
  refs.generationOverlay.classList.remove("hidden")
  refs.resultPreviewTrigger.classList.add("preview-frame-busy")
  refs.requestProgressFill.style.width = "6%"
  refs.generationOrbit?.style.setProperty("--progress-degrees", "21.6deg")
  refs.generationOrbit?.setAttribute("data-progress", "6%")
  refs.progressElapsed.textContent = "0.0s"
  refs.progressStageLabel.textContent = label
  refs.progressHint.textContent = progressHintForPhase("preparing", label)
  updateGenerationOverlay(label, progressHintForPhase("preparing", label), "preparing")
  state.progressTimer = window.setInterval(renderProgress, 100)
}

function setPendingResultFailure(message, details = "") {
  const safeMessage = String(message || "生成失败，请稍后再试。").trim()
  const safeDetails = String(details || "").trim()
  refs.resultPreviewLabel.textContent = "生成失败"
  refs.resultImage.removeAttribute("src")
  refs.resultImage.classList.remove("visible")
  refs.resultPreviewEmpty.classList.remove("hidden")
  refs.resultPreviewEmpty.classList.add("failure")
  refs.resultPreviewEmpty.textContent = safeMessage
  refs.resultTiming.textContent = "已多次尝试仍未成功"
  refs.resultStorage.textContent = safeDetails ? "可展开错误详情查看技术信息。" : ""
  updateGenerationOverlay("生成失败", safeMessage, "receiving")
  refs.requestProgressFill.style.width = "100%"
  refs.generationOrbit?.style.setProperty("--progress-degrees", "360deg")
  refs.generationOrbit?.setAttribute("data-progress", "失败")
}

function stopProgress({ cancelled = false } = {}) {
  window.clearInterval(state.progressTimer)
  state.progressTimer = null
  state.progressStartedAt = 0
  state.progressPhase = "idle"
  state.progressExpectedCount = 1
  refs.requestProgressFill.style.width = cancelled ? "0%" : "100%"
  refs.generationOrbit?.style.setProperty("--progress-degrees", cancelled ? "0deg" : "360deg")
  refs.generationOrbit?.setAttribute("data-progress", cancelled ? "0%" : "100%")
  window.setTimeout(() => {
    if (state.isBusy) {
      return
    }
    refs.progressInspectorItem.classList.add("hidden")
    refs.generationOverlay.classList.add("hidden")
    refs.resultPreviewTrigger.classList.remove("preview-frame-busy")
    refs.requestProgressFill.style.width = "0%"
    refs.generationOrbit?.style.setProperty("--progress-degrees", "0deg")
    refs.generationOrbit?.setAttribute("data-progress", "0%")
    renderGenerationOverlaySteps("idle")
  }, 420)
}

function setBusy(isBusy, label, options = {}) {
  state.isBusy = isBusy
  if (!isBusy) {
    state.activeRequestController = null
    refs.cancelRequestButton.textContent = "中断生成"
  }
  refs.generateButton.disabled = isBusy
  refs.editButton.disabled = isBusy
  refs.generateTab.disabled = isBusy
  refs.editTab.disabled = isBusy
  if (refs.itineraryTab) {
    refs.itineraryTab.disabled = isBusy
  }
  if (refs.renderItineraryMapButton) {
    refs.renderItineraryMapButton.disabled = isBusy
  }
  refs.cancelRequestButton?.classList.toggle("hidden", !isBusy)
  refs.cancelRequestButton.disabled = !isBusy
  refs.requestStatus.textContent = label
  refs.requestBadge.textContent = label
  refs.requestBadge.className = `status-badge ${isBusy ? "working" : "idle"}`
  if (isBusy) {
    state.activeRequestCancelled = false
    startProgress(options.progressLabel || label, options)
  } else {
    stopProgress({ cancelled: options.cancelled === true })
  }
}

function cancelActiveRequest() {
  if (!state.isBusy) {
    return
  }
  state.activeRequestCancelled = true
  appendDebugLine("用户已中断当前生成")
  setProgressPhase("receiving", "正在中断生成")
  refs.cancelRequestButton.disabled = true
  refs.cancelRequestButton.textContent = "正在中断"
  state.activeRequestController?.abort()
}

function ensureRequestNotCancelled() {
  if (!state.activeRequestCancelled) {
    return
  }
  const requestError = new Error("用户已中断当前生成。")
  requestError.cancelled = true
  throw requestError
}

function setError(message = "", details = "") {
  refs.errorMessage.classList.remove("neutral")
  refs.errorMessage.textContent = message
  // Keep the alert to one plain-language sentence; technical details (raw
  // upstream JSON, stack-ish text) go into a collapsed panel so non-technical
  // users aren't faced with a scary wall of text, while a helper can still
  // expand it when needed.
  const hasDetails = Boolean(message && details)
  if (refs.errorDetails) {
    refs.errorDetails.classList.toggle("hidden", !hasDetails)
    if (!hasDetails) {
      refs.errorDetails.open = false
    }
  }
  if (refs.errorDetailsText) {
    refs.errorDetailsText.textContent = hasDetails ? details : ""
  }
}

function errorDetailsWithRequestId(data = {}) {
  const details = data.details || ""
  const requestId = data.request_id || ""
  if (!requestId) {
    return details
  }
  return details ? `${details}\n\nrequest_id: ${requestId}` : `request_id: ${requestId}`
}

function isLocalAuthUnauthorized(response, data) {
  return response.status === 401 && data?.code === "unauthorized"
}

function setStatusMessage(message = "") {
  if (!refs.toastMessage || !message) {
    return
  }
  refs.toastMessage.textContent = message
  refs.toastMessage.classList.remove("hidden")
  window.clearTimeout(state.toastTimer)
  state.toastTimer = window.setTimeout(() => {
    refs.toastMessage?.classList.add("hidden")
  }, 2600)
}

function setRiskPanel(status, text, { hidden = false } = {}) {
  state.copyrightRisk = { status, text, hidden }
  refs.copyrightRiskPanel?.classList.toggle("hidden", hidden)
  if (refs.copyrightRiskStatus) {
    refs.copyrightRiskStatus.textContent = status
  }
  if (refs.copyrightRiskText) {
    refs.copyrightRiskText.textContent = text
  }
  scheduleWorkspacePersist()
}

function setTextFidelityPanel(status, text, { hidden = false } = {}) {
  state.textFidelity = { status, text, hidden }
  refs.textFidelityPanel?.classList.toggle("hidden", hidden)
  if (refs.textFidelityStatus) {
    refs.textFidelityStatus.textContent = status
  }
  if (refs.textFidelityText) {
    refs.textFidelityText.textContent = text
  }
  scheduleWorkspacePersist()
}

function restoreCopyrightRiskPanel() {
  const risk = state.copyrightRisk || {}
  setRiskPanel(
    risk.status || "等待检查",
    risk.text || "生成完成后自动检查。",
    { hidden: risk.hidden !== false },
  )
}

function restoreTextFidelityPanel() {
  const fidelity = state.textFidelity || {}
  setTextFidelityPanel(
    fidelity.status || "等待检查",
    fidelity.text || "生成完成后自动检查用户文案。",
    { hidden: fidelity.hidden !== false },
  )
}

function updateGenerateReferenceUI() {
  const hasStyle = Boolean(state.styleReferenceImage)
  const hasMaterial = Boolean(state.materialReferenceImage)
  const hasReference = Boolean(state.generateReferenceImage || hasStyle || hasMaterial)
  refs.styleReferenceDropzone.classList.toggle("ready", hasStyle)
  refs.materialReferenceDropzone.classList.toggle("ready", hasMaterial)
  refs.clearGenerateReferenceButton.classList.toggle("hidden", !hasReference)

  if (hasStyle) {
    refs.styleReferenceTitle.textContent = "已加载风格模板"
    refs.styleReferenceMeta.textContent = state.styleReferenceImage.description || state.styleReferenceImage.name
  } else {
    refs.styleReferenceTitle.textContent = "左：风格模板"
    refs.styleReferenceMeta.textContent = "取色调、材质、光影和版式氛围。"
  }

  if (hasMaterial) {
    refs.materialReferenceTitle.textContent = "已加载素材图"
    refs.materialReferenceMeta.textContent = state.materialReferenceImage.description || state.materialReferenceImage.name
  } else {
    refs.materialReferenceTitle.textContent = "右：素材图"
    refs.materialReferenceMeta.textContent = "保留主体、结构、文字和可识别信息。"
  }

  if (hasStyle && hasMaterial) {
    refs.generateReferenceMeta.textContent = "将按左图风格处理右图素材，默认返回 3 张候选效果图。"
  } else if (hasStyle || hasMaterial || state.generateReferenceImage) {
    refs.generateReferenceMeta.textContent = "请补齐左右两张图以生成 3 张风格效果图；仅一张图时按单参考图生成。"
  } else {
    refs.generateReferenceMeta.textContent = "两张都上传时默认生成 3 张效果图；仅上传右侧素材时按单参考图生成。"
  }

  updateGenerateIntentUI()
  updateGenerateSampleCountUI()
}

function setGenerateReferenceImage(asset, { showPreview = state.activeMode === "generate" } = {}) {
  state.generateReferenceImage = cloneImageAsset(asset)
  updateGenerateReferenceUI()
  if (showPreview && getAssetDisplaySrc(state.generateReferenceImage)) {
    applySourcePreview(state.generateReferenceImage, "参考图")
  }
  scheduleWorkspacePersist()
}

function setStyleReferenceImage(asset, { showPreview = state.activeMode === "generate" } = {}) {
  state.styleReferenceImage = cloneImageAsset(asset, { role: "style_template" })
  state.generateReferenceImage = state.materialReferenceImage || state.styleReferenceImage
  updateGenerateReferenceUI()
  if (showPreview && getAssetDisplaySrc(state.styleReferenceImage)) {
    applySourcePreview(state.styleReferenceImage, "风格模板")
  }
  scheduleWorkspacePersist()
}

function setMaterialReferenceImage(asset, { showPreview = state.activeMode === "generate" } = {}) {
  state.materialReferenceImage = cloneImageAsset(asset, { role: "material" })
  state.generateReferenceImage = state.materialReferenceImage
  updateGenerateReferenceUI()
  if (showPreview && getAssetDisplaySrc(state.materialReferenceImage)) {
    applySourcePreview(state.materialReferenceImage, "素材图")
  }
  scheduleWorkspacePersist()
}

function clearGenerateReferenceImage({ clearInput = true } = {}) {
  state.generateReferenceImage = null
  state.styleReferenceImage = null
  state.materialReferenceImage = null
  if (clearInput) {
    refs.styleReferenceInput.value = ""
    refs.materialReferenceInput.value = ""
  }
  updateGenerateReferenceUI()
  if (state.activeMode === "generate") {
    clearSourcePreview("原图")
  }
  scheduleWorkspacePersist()
}

function clearSourcePreview(label = state.activeMode === "edit" ? "输入图" : "原图") {
  state.displayedSourceImage = null
  refs.sourcePreviewLabel.textContent = label
  refs.sourcePreviewImage.removeAttribute("src")
  refs.sourcePreviewImage.classList.remove("visible")
  refs.sourcePreviewEmpty.classList.remove("hidden")
  refs.sourcePreviewEmpty.textContent = state.activeMode === "edit"
    ? "当前没有可作为输入的图片。生成成功后切到编辑模式会自动带入；也可以手动上传。"
    : "切到编辑模式并上传图片后，这里会显示原图。"
}

function applySourcePreview(asset, label = "输入图") {
  const previewSrc = getAssetDisplaySrc(asset)
  if (!previewSrc) {
    clearSourcePreview(label)
    updatePreviewAvailability()
    return
  }

  state.displayedSourceImage = cloneImageAsset(asset)
  refs.sourcePreviewLabel.textContent = label
  refs.sourcePreviewImage.src = previewSrc
  refs.sourcePreviewImage.classList.add("visible")
  refs.sourcePreviewEmpty.classList.add("hidden")
  updatePreviewAvailability()
}

function updateEditSourceUI() {
  refs.imageDropzone.classList.toggle("ready", Boolean(state.editImage))

  if (state.editImage) {
    if (state.editImage.origin === "result") {
      refs.imageDropzoneTitle.textContent = "已自动读取最新结果"
      refs.imageDropzoneSubtitle.textContent = "直接输入编辑指令即可；如果要换图，点击这里选择或拖拽替换。"
    } else {
      refs.imageDropzoneTitle.textContent = "已加载待编辑图片"
      refs.imageDropzoneSubtitle.textContent = "现在就能直接编辑；如果要换图，点击这里选择或拖拽替换。"
    }

    refs.editImageMeta.textContent = state.editImage.description || state.editImage.name
    return
  }

  if (state.lastResultImage) {
    refs.imageDropzoneTitle.textContent = "切到编辑模式会自动使用最新结果"
    refs.imageDropzoneSubtitle.textContent = "也可以点击这里选择或拖拽其他图片。"
    refs.editImageMeta.textContent = ""
    return
  }

  refs.imageDropzoneTitle.textContent = "拖拽图片到这里，或点击选择"
  refs.imageDropzoneSubtitle.textContent = "也支持在编辑模式下直接粘贴剪贴板图片"
  refs.editImageMeta.textContent = ""
  updateWorkflowStatus()
}

function updateEditMaskUI() {
  const hasMask = Boolean(state.editMaskImage)
  refs.maskDropzone.classList.toggle("ready", hasMask)
  refs.clearEditMaskButton.classList.toggle("hidden", !hasMask)

  if (hasMask) {
    refs.maskDropzoneTitle.textContent = "已加载编辑 mask"
    refs.maskDropzoneSubtitle.textContent = "透明区域会被重新生成；不透明区域用于约束保留。"
    refs.editMaskMeta.textContent = state.editMaskImage.description || state.editMaskImage.name
    return
  }

  refs.maskDropzoneTitle.textContent = "可选：上传透明区域 mask"
  refs.maskDropzoneSubtitle.textContent = "透明区域会被模型重新生成；留空则按整图编辑。"
  refs.editMaskMeta.textContent = ""
}

function setEditImage(asset, { showPreview = state.activeMode === "edit", previewLabel = "输入图" } = {}) {
  state.editImage = cloneImageAsset(asset)
  updateEditSourceUI()

  if (showPreview) {
    applySourcePreview(state.editImage, previewLabel)
  }

  scheduleWorkspacePersist()
}

function setEditMaskImage(asset) {
  state.editMaskImage = cloneImageAsset(asset)
  updateEditMaskUI()
  scheduleWorkspacePersist()
}

function clearEditMaskImage({ clearInput = true } = {}) {
  state.editMaskImage = null
  if (clearInput) {
    refs.editMaskInput.value = ""
  }
  updateEditMaskUI()
  scheduleWorkspacePersist()
}

function useLastResultAsEditSource({ showPreview = true, focus = false } = {}) {
  if (!state.lastResultImage) {
    return false
  }

  const inputAsset = modelInputAssetForLogoWorkflow(state.lastResultImage)
  const usesBaseImage = inputAsset !== state.lastResultImage
  const asset = cloneImageAsset(inputAsset, {
    origin: "result",
    generatedImageId: state.lastResultImage.generatedImageId,
    sourceGeneratedImageId: state.lastResultImage.sourceGeneratedImageId || null,
    description: usesBaseImage
      ? `自动使用未贴 LOGO 的主体图 · ${inputAsset.name}`
      : `自动使用最新结果 · ${inputAsset.name}`,
  })
  setEditImage(asset, { showPreview, previewLabel: "输入图" })

  if (!refs.editModelInput.value.trim() && state.lastResultModel) {
    refs.editModelInput.value = state.lastResultModel
  }

  if (focus && !refs.editPromptInput.value.trim()) {
    refs.editPromptInput.value = [
      "请基于当前图做精细修改：",
      "- 只修改我接下来明确说明的部分；",
      "- 保留现有构图、路线、地点、日期、距离标注、交通工具图标、文字层级和整体风格；",
      "- 保留 6 人游 LOGO 安全区，最终 LOGO 由程序使用官方 PNG 原样贴入，不要重绘或改造 LOGO。",
      "",
      "需要修改：",
    ].join("\n")
    updatePromptCounters()
  }

  if (focus) {
    refs.editPromptInput.focus()
  }

  setError("")
  return true
}

function setMode(mode, options = {}) {
  const previousMode = state.activeMode
  state.activeMode = mode

  refs.generateTab.classList.toggle("active", mode === "generate")
  refs.editTab.classList.toggle("active", mode === "edit")
  refs.itineraryTab?.classList.toggle("active", mode === "itinerary")
  refs.navModeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode)
  })
  refs.generatePanel.classList.toggle("hidden", mode !== "generate")
  refs.editPanel.classList.toggle("hidden", mode !== "edit")
  refs.itineraryPanel?.classList.toggle("hidden", mode !== "itinerary")
  refs.sourcePreviewCard.classList.toggle("subtle", mode !== "edit")

  if (mode === "edit" && previousMode !== "edit" && options.autoLoadLatest !== false && state.lastResultImage) {
    useLastResultAsEditSource({ showPreview: true })
  } else if (mode === "generate" && getAssetDisplaySrc(state.materialReferenceImage || state.generateReferenceImage || state.styleReferenceImage)) {
    applySourcePreview(state.materialReferenceImage || state.generateReferenceImage || state.styleReferenceImage, state.materialReferenceImage ? "素材图" : "参考图")
  } else if (mode !== "edit" && state.lastResultMode !== "edit") {
    clearSourcePreview("原图")
  }

  if (mode === "edit" && !state.displayedSourceImage && getAssetDisplaySrc(state.editImage)) {
    applySourcePreview(state.editImage, "输入图")
  }
  updateGenerateIntentUI()
  updateEditSourceUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function canComparePreviews() {
  return Boolean(
    ["edit", "variant"].includes(state.lastResultMode) &&
    getAssetDisplaySrc(state.currentComparisonSource) &&
    state.resultPreview?.src,
  )
}

function updatePreviewAvailability() {
  const hasSource = Boolean(getAssetDisplaySrc(state.displayedSourceImage))
  const hasResult = Boolean(state.resultPreview?.src)

  refs.sourcePreviewTrigger.classList.toggle("preview-frame-clickable", hasSource)
  refs.resultPreviewTrigger.classList.toggle("preview-frame-clickable", hasResult)
  refs.previewCompareButton.disabled = !canComparePreviews()
  refs.previewCompareModeButton.disabled = !canComparePreviews()
  refs.continueEditButton.disabled = !state.lastResultImage
  refs.startVariantButton.disabled = !state.lastResultImage
  refs.saveGroupAssetButton.disabled = !selectedGeneratedImageId()
  updateFeedbackPanelVisibility()
  updateWorkflowStatus()
}

function closePreview() {
  refs.previewModal.classList.add("hidden")
  refs.previewModal.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open")
  stopPreviewDrag()
}

function resetPreviewZoom() {
  state.previewZoom = {
    scale: 1,
    x: 0,
    y: 0,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    startX: 0,
    startY: 0,
  }
  applyPreviewZoom()
}

function applyPreviewZoom() {
  const zoom = state.previewZoom
  if (!refs.previewSingleImage) {
    return
  }
  refs.previewSingleImage.style.transform = `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})`
  refs.previewSingleImage.classList.toggle("is-zoomed", zoom.scale > 1.01)
  refs.previewZoomOutButton.disabled = zoom.scale <= 1.01
  refs.previewZoomResetButton.disabled = zoom.scale <= 1.01 && zoom.x === 0 && zoom.y === 0
}

function isLikelyLongImageAsset(asset = state.lastResultImage) {
  const width = Number(asset?.width || asset?.saved_image_width || 0)
  const height = Number(asset?.height || asset?.saved_image_height || 0)
  if (width > 0 && height > 0) {
    return height / width >= 1.45 || width / height >= 1.45
  }
  const name = String(asset?.name || asset?.saved_image_name || "")
  return name.includes("1088x2240") || name.includes("2160x3840")
}

function changePreviewZoom(delta) {
  const nextScale = Math.max(1, Math.min(4, Number((state.previewZoom.scale + delta).toFixed(2))))
  state.previewZoom.scale = nextScale
  if (nextScale <= 1.01) {
    state.previewZoom.x = 0
    state.previewZoom.y = 0
  }
  applyPreviewZoom()
}

function stopPreviewDrag() {
  state.previewZoom.dragging = false
  refs.previewSinglePane?.classList.remove("is-dragging")
}

function startPreviewDrag(event) {
  if (state.preview.mode === "compare" || state.previewZoom.scale <= 1.01 || event.button !== 0) {
    return
  }
  event.preventDefault()
  state.previewZoom.dragging = true
  state.previewZoom.dragStartX = event.clientX
  state.previewZoom.dragStartY = event.clientY
  state.previewZoom.startX = state.previewZoom.x
  state.previewZoom.startY = state.previewZoom.y
  refs.previewSinglePane?.classList.add("is-dragging")
}

function movePreviewDrag(event) {
  if (!state.previewZoom.dragging) {
    return
  }
  event.preventDefault()
  state.previewZoom.x = state.previewZoom.startX + event.clientX - state.previewZoom.dragStartX
  state.previewZoom.y = state.previewZoom.startY + event.clientY - state.previewZoom.dragStartY
  applyPreviewZoom()
}

function handlePreviewWheel(event) {
  if (state.preview.mode === "compare") {
    return
  }
  if (!(event.ctrlKey || event.metaKey)) {
    return
  }
  event.preventDefault()
  changePreviewZoom(event.deltaY < 0 ? 0.2 : -0.2)
}

function getPreviewItem(target) {
  if (target === "source") {
    const sourceSrc = getAssetDisplaySrc(state.displayedSourceImage)
    if (!sourceSrc) {
      return null
    }
    return {
      src: sourceSrc,
      label: refs.sourcePreviewLabel.textContent || "输入图",
      meta: state.displayedSourceImage.description || state.displayedSourceImage.name || "",
    }
  }

  if (!state.resultPreview?.src) {
    return null
  }

  return {
    src: state.resultPreview.src,
    label: refs.resultPreviewLabel.textContent || "输出",
    meta: refs.resultMeta.textContent || "",
  }
}

function renderPreviewModal() {
  const compareEnabled = canComparePreviews()
  const previewMode = state.preview.mode === "compare" && compareEnabled ? "compare" : "single"
  const singleItem = getPreviewItem(state.preview.target) || getPreviewItem("result")

  refs.previewSingleModeButton.classList.toggle("active-toggle", previewMode === "single")
  refs.previewCompareModeButton.classList.toggle("active-toggle", previewMode === "compare")

  refs.previewSinglePane.classList.toggle("hidden", previewMode !== "single")
  refs.previewComparePane.classList.toggle("hidden", previewMode !== "compare")

  if (previewMode === "single" && singleItem) {
    refs.previewModalTitle.textContent = state.preview.mode === "cinema" ? "长图检查" : `${singleItem.label}预览`
    refs.previewModalMeta.textContent = state.preview.mode === "cinema"
      ? `${singleItem.meta || "输出图"} · 可放大、拖拽检查人物、文字和 LOGO 拼接。`
      : singleItem.meta
    refs.previewSingleImage.src = singleItem.src
    applyPreviewZoom()
    return
  }

  refs.previewModalTitle.textContent = "编辑前后对比"
  refs.previewModalMeta.textContent = "左侧是本次编辑前的输入图，右侧是本次输出图。"
  refs.previewCompareSourceImage.src = getAssetDisplaySrc(state.currentComparisonSource)
  refs.previewCompareResultImage.src = state.resultPreview.src
}

function openPreview(target = "result", mode = "single") {
  const previewItem = getPreviewItem(target)
  if (!previewItem) {
    return
  }

  state.preview.target = target
  state.preview.mode = mode
  resetPreviewZoom()
  if (mode === "cinema") {
    state.previewZoom.scale = isLikelyLongImageAsset() ? 1.35 : 1.2
  }
  renderPreviewModal()
  refs.previewModal.classList.remove("hidden")
  refs.previewModal.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
  applyPreviewZoom()
}

function clearResult() {
  refs.resultPreviewLabel.textContent = "输出"
  refs.resultImage.removeAttribute("src")
  refs.resultImage.classList.remove("visible")
  refs.resultPreviewEmpty.classList.remove("hidden")
  refs.resultPreviewEmpty.classList.remove("failure")
  refs.resultPreviewEmpty.textContent = "生成或编辑成功后，这里会显示输出结果。"
  refs.resultPrompt.textContent = "还没有结果。"
  refs.resultMeta.textContent = ""
  refs.resultTiming.textContent = ""
  refs.resultStorage.textContent = ""
  refs.logoComposeStatus.textContent = refs.logoOverlayEnabled?.checked ? "本地贴图" : "未启用"
  refs.rawResponseOutput.textContent = "{}"
  refs.debugOutput.textContent = "等待操作。"
  setRiskPanel("等待检查", "生成完成后自动检查。", { hidden: true })
  setDownloadDisabled()
  refs.feedbackReasonPanel?.classList.add("hidden")
  if (refs.feedbackReasonInput) {
    refs.feedbackReasonInput.value = ""
  }
  refs.shareResultPanel?.classList.add("hidden")
  if (refs.shareResultNoteInput) {
    refs.shareResultNoteInput.value = ""
  }
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")

  state.lastResultPrompt = ""
  state.lastResultImage = null
  state.lastResultModel = ""
  state.lastResultMode = null
  state.currentComparisonSource = null
  state.resultPreview = null
  state.resultGenerationSeq += 1
  state.resultCandidates = []
  state.selectedCandidateIndex = 0
  state.rawResponsePreview = null
  state.lastFeedbackPayload = null
  state.lastFeedbackRating = null
  state.debugLines = []
  state.generateIntent = "fresh"
  setGalleryEditorMeta(null)
  updateOriginalDownloadButton(null)

  closePreview()
  renderRawResponsePreview()
  renderResultCandidates()
  updateGenerateIntentUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function snapshotCurrentResultState() {
  return {
    label: refs.resultPreviewLabel.textContent,
    imageSrc: refs.resultImage.getAttribute("src") || "",
    imageVisible: refs.resultImage.classList.contains("visible"),
    emptyHidden: refs.resultPreviewEmpty.classList.contains("hidden"),
    emptyFailure: refs.resultPreviewEmpty.classList.contains("failure"),
    emptyText: refs.resultPreviewEmpty.textContent,
    prompt: refs.resultPrompt.textContent,
    meta: refs.resultMeta.textContent,
    timing: refs.resultTiming.textContent,
    storage: refs.resultStorage.textContent,
    logoStatus: refs.logoComposeStatus.textContent,
    rawResponse: state.rawResponsePreview,
    debugLines: [...state.debugLines],
    lastResultPrompt: state.lastResultPrompt,
    lastResultImage: cloneImageAsset(state.lastResultImage),
    lastResultModel: state.lastResultModel,
    lastResultMode: state.lastResultMode,
    currentComparisonSource: cloneImageAsset(state.currentComparisonSource),
    resultPreview: state.resultPreview ? { ...state.resultPreview } : null,
    resultGenerationSeq: state.resultGenerationSeq,
    resultCandidates: state.resultCandidates.map((candidate) => ({
      ...candidate,
      asset: cloneImageAsset(candidate.asset),
    })),
    selectedCandidateIndex: state.selectedCandidateIndex,
    rawResponsePreview: state.rawResponsePreview,
    lastFeedbackPayload: state.lastFeedbackPayload ? { ...state.lastFeedbackPayload } : null,
    lastFeedbackRating: state.lastFeedbackRating,
    galleryMeta: state.currentGalleryMeta ? { ...state.currentGalleryMeta } : null,
    copyrightRisk: state.copyrightRisk ? { ...state.copyrightRisk } : null,
    textFidelity: state.textFidelity ? { ...state.textFidelity } : null,
    download: refs.downloadButton
      ? {
          href: refs.downloadButton.getAttribute("href") || "",
          filename: refs.downloadButton.getAttribute("download") || "",
          logoReady: refs.downloadButton.classList.contains("download-ready-logo"),
          label: refs.downloadButton.textContent,
        }
      : null,
  }
}

function restoreResultStateSnapshot(snapshot) {
  if (!snapshot) {
    return
  }
  refs.resultPreviewLabel.textContent = snapshot.label || "输出"
  if (snapshot.imageSrc) {
    refs.resultImage.src = snapshot.imageSrc
  } else {
    refs.resultImage.removeAttribute("src")
  }
  refs.resultImage.classList.toggle("visible", Boolean(snapshot.imageVisible))
  refs.resultPreviewEmpty.classList.toggle("hidden", Boolean(snapshot.emptyHidden))
  refs.resultPreviewEmpty.classList.toggle("failure", Boolean(snapshot.emptyFailure))
  refs.resultPreviewEmpty.textContent = snapshot.emptyText || "生成或编辑成功后，这里会显示输出结果。"
  refs.resultPrompt.textContent = snapshot.prompt || "还没有结果。"
  refs.resultMeta.textContent = snapshot.meta || ""
  refs.resultTiming.textContent = snapshot.timing || ""
  refs.resultStorage.textContent = snapshot.storage || ""
  refs.logoComposeStatus.textContent = snapshot.logoStatus || (refs.logoOverlayEnabled?.checked ? "本地贴图" : "未启用")

  state.lastResultPrompt = snapshot.lastResultPrompt || ""
  state.lastResultImage = cloneImageAsset(snapshot.lastResultImage)
  state.lastResultModel = snapshot.lastResultModel || ""
  state.lastResultMode = snapshot.lastResultMode || null
  state.currentComparisonSource = cloneImageAsset(snapshot.currentComparisonSource)
  state.resultPreview = snapshot.resultPreview ? { ...snapshot.resultPreview } : null
  state.resultGenerationSeq = Number(snapshot.resultGenerationSeq || state.resultGenerationSeq)
  state.resultCandidates = Array.isArray(snapshot.resultCandidates)
    ? snapshot.resultCandidates.map((candidate) => ({
        ...candidate,
        asset: cloneImageAsset(candidate.asset),
      }))
    : []
  state.selectedCandidateIndex = Number(snapshot.selectedCandidateIndex || 0)
  state.rawResponsePreview = snapshot.rawResponsePreview || snapshot.rawResponse || null
  state.lastFeedbackPayload = snapshot.lastFeedbackPayload ? { ...snapshot.lastFeedbackPayload } : null
  state.lastFeedbackRating = snapshot.lastFeedbackRating || null
  state.debugLines = Array.isArray(snapshot.debugLines) ? [...snapshot.debugLines] : []
  state.copyrightRisk = snapshot.copyrightRisk || state.copyrightRisk
  state.textFidelity = snapshot.textFidelity || state.textFidelity
  setGalleryEditorMeta(snapshot.galleryMeta || null)

  renderRawResponsePreview()
  renderResultCandidates()
  restoreCopyrightRiskPanel()
  restoreTextFidelityPanel()
  // 恢复主下载按钮：previewPendingResult 会禁用它，取消生成后如果不
  // 恢复，旧结果虽然回来了但下载按钮永远是死链（单候选时没有候选条，
  // 也就没有任何入口能重新点亮它）。
  if (snapshot.download && snapshot.download.href) {
    setDownloadAvailable(snapshot.download.href, snapshot.download.filename, {
      logoReady: snapshot.download.logoReady,
      candidate: selectedResultCandidate(),
    })
  } else {
    setDownloadDisabled()
    updateOriginalDownloadButton(selectedResultCandidate())
  }
  updatePreviewAvailability()
  updateResultActionSurface()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function restorePendingResultAfterCancellation() {
  if (!state.pendingResultSnapshot) {
    return false
  }
  restoreResultStateSnapshot(state.pendingResultSnapshot)
  state.pendingResultSnapshot = null
  return true
}

function previewPendingResult({ mode, prompt, model, size, sourceName = "" }) {
  const label = mode === "variant"
    ? "延展中"
    : mode === "edit"
      ? "编辑中"
      : mode === "reference"
        ? "参考生成中"
        : mode === "itinerary"
          ? "行程路线生成中"
          : "生成中"
  const metaLabel = mode === "variant"
    ? "延展"
    : mode === "edit"
      ? "编辑"
      : mode === "reference"
        ? "参考生成"
        : mode === "itinerary"
          ? "行程路线"
          : "生成"
  const metaParts = [metaLabel, model]

  if (size) {
    metaParts.push(size)
  }
  if (sourceName) {
    metaParts.push(`参考图 ${sourceName}`)
  }

  state.pendingResultSnapshot = snapshotCurrentResultState()
  refs.resultPreviewLabel.textContent = label
  refs.resultImage.removeAttribute("src")
  refs.resultImage.classList.remove("visible")
  refs.resultPreviewEmpty.classList.remove("hidden")
  refs.resultPreviewEmpty.classList.remove("failure")
  refs.resultPreviewEmpty.textContent = "请求已提交，正在等待上游返回新图。"
  refs.resultPrompt.textContent = prompt || "本次请求已提交。"
  refs.resultMeta.textContent = metaParts.filter(Boolean).join(" · ")
  refs.resultTiming.textContent = "请求进行中 0.0s"
  refs.resultStorage.textContent = ""
  setDownloadDisabled()
  state.resultCandidates = []
  state.selectedCandidateIndex = 0
  renderResultCandidates()
}

function candidateImageSource(candidate) {
  return candidate?.saved_image_url || candidate?.image_data_url || candidate?.image_url || ""
}

function candidateAsset(candidate, payload, index) {
  const imageSource = candidateImageSource(candidate)
  if (!imageSource) {
    return null
  }
  const metadata = candidate.metadata && typeof candidate.metadata === "object" ? candidate.metadata : {}
  const originalSavedUrl = candidate.original_saved_image_url || candidate.source_saved_image_url || metadata.source_saved_image_url || ""
  const originalSavedPath = candidate.original_saved_image_path || candidate.source_saved_image_path || metadata.source_saved_image_path || metadata.source_image_path || ""
  return {
    name: candidate.saved_image_name || `picgen-${payload.mode}-${index + 1}-${Date.now()}.png`,
    type: candidate.saved_image_mime || (candidate.image_data_url ? inferMimeFromDataUrl(candidate.image_data_url) : ""),
    dataUrl: candidate.image_data_url || "",
    savedUrl: candidate.saved_image_url || "",
    savedPath: candidate.saved_image_path || "",
    generatedImageId: candidate.generated_image_id || null,
    sourceGeneratedImageId: candidate.source_generated_image_id || null,
    metadataPath: candidate.saved_metadata_path || "",
    fileUrl: candidate.saved_image_url || candidate.image_url || "",
    originalDataUrl: "",
    originalSavedUrl,
    originalFileUrl: originalSavedUrl,
    originalSavedPath,
    origin: "result",
    description: `候选 ${index + 1} · ${payload.model || ""}`,
    src: imageSource,
    logoOverlayApplied: Boolean(candidate.logo_overlay_applied),
  }
}

function selectedResultCandidate() {
  return state.resultCandidates[state.selectedCandidateIndex] || state.resultCandidates[0] || null
}

function originalCandidateDownloadSource(candidate = selectedResultCandidate()) {
  const asset = candidate?.asset || {}
  return {
    href: asset.originalSavedUrl || asset.originalFileUrl || asset.originalDataUrl || candidate?.saved_image_url || candidateImageSource(candidate),
    filename: imageDataUrlName(asset.name || candidate?.saved_image_name || "picgen-original.png", "original"),
  }
}

function updateOriginalDownloadButton(candidate = selectedResultCandidate()) {
  if (!refs.downloadOriginalButton) {
    return
  }
  const source = originalCandidateDownloadSource(candidate)
  refs.downloadOriginalButton.disabled = !source.href
  refs.downloadOriginalButton.dataset.href = source.href || ""
  refs.downloadOriginalButton.dataset.filename = source.filename || "picgen-original.png"
}

function setDownloadAvailable(href, filename, options = {}) {
  if (!refs.downloadButton) {
    return
  }
  refs.downloadButton.href = href
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.classList.toggle("download-ready-logo", Boolean(options.logoReady))
  refs.downloadButton.textContent = options.logoReady
    ? "下载带 6 人游 LOGO 成品"
    : "下载图像"
  refs.downloadButton.download = filename
  updateOriginalDownloadButton(options.candidate)
}

function setDownloadDisabled(label = "下载图像") {
  if (!refs.downloadButton) {
    return
  }
  refs.downloadButton.classList.add("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "true")
  refs.downloadButton.removeAttribute("href")
  refs.downloadButton.removeAttribute("download")
  refs.downloadButton.classList.remove("download-ready-logo")
  refs.downloadButton.textContent = label
}

function setDownloadPendingLogo() {
  setDownloadDisabled("LOGO 成品保存中")
}

function updateSelectedCandidateStorageText(selectedCandidate = selectedResultCandidate()) {
  if (!selectedCandidate) {
    refs.resultStorage.textContent = ""
    return
  }
  const actualSize = formatActualSize({
    saved_image_width: selectedCandidate.saved_image_width || selectedCandidate.width || selectedCandidate.actual_width,
    saved_image_height: selectedCandidate.saved_image_height || selectedCandidate.height || selectedCandidate.actual_height,
  })
  if (selectedCandidate.logo_overlay_applied) {
    refs.resultStorage.textContent = selectedCandidate.saved_image_path
      ? `LOGO 成品已落盘到 ${selectedCandidate.saved_image_path}${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
      : `LOGO 已在浏览器本地贴入，分享前需要重新保存${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
    return
  }
  refs.resultStorage.textContent = selectedCandidate.saved_image_path
    ? `已落盘到 ${selectedCandidate.saved_image_path}${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
    : actualSize
      ? `实际尺寸 ${actualSize}`
      : ""
}

function updateResultActionSurface() {
  const hasResult = Boolean(state.resultPreview?.src)
  const hasImage = Boolean(state.lastResultImage)
  refs.continueEditButton.disabled = !hasImage
  refs.startVariantButton.disabled = !hasImage
  refs.hoverContinueEditButton && (refs.hoverContinueEditButton.disabled = !hasImage)
  refs.hoverVariantButton && (refs.hoverVariantButton.disabled = !hasImage)
  refs.inspectLongImageButton && (refs.inspectLongImageButton.disabled = !hasResult)
  refs.hoverShareButton && (refs.hoverShareButton.disabled = !selectedGeneratedImageId())
  refs.showVersionsButton && (refs.showVersionsButton.disabled = !selectedGeneratedImageId())
  if (!hasResult) {
    refs.versionHistoryPanel?.classList.add("hidden")
  }
  updateOriginalDownloadButton()
}

function selectResultCandidate(index, { persist = true } = {}) {
  const candidate = state.resultCandidates[index]
  const imageSource = candidateImageSource(candidate)
  if (!candidate || !imageSource) {
    return
  }

  state.selectedCandidateIndex = index
  refs.resultImage.src = imageSource
  refs.resultImage.classList.add("visible")
  refs.resultPreviewEmpty.classList.add("hidden")
  state.resultPreview = {
    src: imageSource,
    mode: state.lastResultMode,
  }
  state.lastResultImage = cloneImageAsset(candidate.asset)
  setDownloadAvailable(
    candidate.saved_image_url || imageSource,
    candidate.saved_image_name || `picgen-${state.lastResultMode || "result"}-${index + 1}.png`,
    {
      candidate,
      logoReady: Boolean(candidate.logo_overlay_applied || candidate.logo_final_persisted),
    },
  )
  refs.feedbackReasonPanel?.classList.add("hidden")
  if (refs.feedbackReasonInput) {
    refs.feedbackReasonInput.value = ""
  }
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  setGalleryEditorMeta(candidate)
  updateSelectedCandidateStorageText(candidate)
  renderResultCandidates()
  updateFeedbackPanelVisibility()
  updatePreviewAvailability()
  updateResultActionSurface()
  if (persist) {
    scheduleWorkspacePersist()
  }
}

function renderResultCandidates() {
  if (!refs.resultCandidateStrip) {
    return
  }
  refs.resultCandidateStrip.replaceChildren()
  refs.resultCandidateStrip.classList.toggle("hidden", state.resultCandidates.length <= 1)

  state.resultCandidates.forEach((candidate, index) => {
    const imageSource = candidateImageSource(candidate)
    if (!imageSource) {
      return
    }
    const button = document.createElement("button")
    button.type = "button"
    button.className = "candidate-button"
    button.classList.toggle("active", index === state.selectedCandidateIndex)
    const img = document.createElement("img")
    img.src = imageSource
    img.alt = `候选 ${index + 1}`
    const label = document.createElement("span")
    label.textContent = `候选 ${index + 1}`
    button.append(img, label)
    button.addEventListener("click", () => selectResultCandidate(index))
    refs.resultCandidateStrip.appendChild(button)
  })
}

function applyPrimaryResultCandidate(firstCandidate, payload, imageSource, durationMs) {
  const actualSize = formatActualSize(payload)
  refs.resultImage.src = imageSource
  refs.resultImage.classList.add("visible")
  refs.resultPreviewEmpty.classList.add("hidden")
  refs.resultPreviewEmpty.textContent = "生成或编辑成功后，这里会显示输出结果。"
  state.resultPreview = {
    src: imageSource,
    mode: payload.mode || null,
  }
  state.lastResultImage = cloneImageAsset(firstCandidate.asset)
  refs.resultTiming.textContent = `请求耗时 ${durationMs.toFixed(1)} ms`
  if (firstCandidate.logo_overlay_applied) {
    refs.resultStorage.textContent = firstCandidate.saved_image_path
      ? `LOGO 成品已落盘到 ${firstCandidate.saved_image_path}${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
      : `LOGO 已在浏览器本地贴入，分享前需要重新保存${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
  } else {
    refs.resultStorage.textContent = firstCandidate.saved_image_path
      ? `已落盘到 ${firstCandidate.saved_image_path}${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
      : actualSize
        ? `实际尺寸 ${actualSize}`
        : ""
  }
  setDownloadAvailable(
    firstCandidate.saved_image_url || imageSource,
    firstCandidate.saved_image_name || `picgen-${payload.mode}-${Date.now()}.png`,
    {
      candidate: firstCandidate,
      logoReady: Boolean(firstCandidate.logo_overlay_applied || firstCandidate.logo_final_persisted),
    },
  )
}

async function composeLogoOverlayAfterDisplay(payload, durationMs, resultGenerationSeq) {
  try {
    const composedCandidates = await composeLogoOverlayForCandidates(state.resultCandidates, true)
    if (!composedCandidates.length || state.activeRequestController || resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    state.resultCandidates = composedCandidates
    const selectedIndex = Math.min(state.selectedCandidateIndex, composedCandidates.length - 1)
    const selectedCandidate = composedCandidates[selectedIndex] || composedCandidates[0]
    const imageSource = candidateImageSource(selectedCandidate)
    if (!imageSource) {
      return
    }
    applyPrimaryResultCandidate(selectedCandidate, payload, imageSource, durationMs)
    renderResultCandidates()
    updatePreviewAvailability()
    updateResultActionSurface()
    refs.logoComposeStatus.textContent = selectedCandidate.logo_final_persisted ? "成品已保存" : "本地已贴图"
    scheduleWorkspacePersist()
  } catch (error) {
    if (resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    appendDebugLine("本地 LOGO 合成失败", { error: error.message })
    refs.logoComposeStatus.textContent = "贴图失败，可先下载原图"
    const fallbackCandidate = state.resultCandidates[state.selectedCandidateIndex] || state.resultCandidates[0]
    const fallbackSource = candidateImageSource(fallbackCandidate)
    if (fallbackCandidate && fallbackSource) {
      setDownloadAvailable(
        fallbackCandidate.saved_image_url || fallbackSource,
        fallbackCandidate.saved_image_name || `picgen-${payload.mode || "result"}-${Date.now()}.png`,
      )
    }
  }
}

async function setResult(payload, durationMs, requestSource = null) {
  state.pendingResultSnapshot = null
  const candidates = Array.isArray(payload.images) && payload.images.length
    ? payload.images
    : [payload]
  const enrichedCandidates = candidates
    .map((candidate, index) => ({
      ...candidate,
      asset: candidateAsset(candidate, payload, index),
    }))
    .filter((candidate) => candidateImageSource(candidate))
  const firstCandidate = enrichedCandidates[0] || {}
  const imageSource = candidateImageSource(firstCandidate)
  if (!imageSource) {
    throw new Error("上游接口没有返回可展示的图片。")
  }

  const resultGenerationSeq = state.resultGenerationSeq + 1
  state.resultGenerationSeq = resultGenerationSeq
  state.resultCandidates = enrichedCandidates
  state.selectedCandidateIndex = 0
  const isTransformMode = ["edit", "variant", "reference"].includes(payload.mode)
  refs.resultPreviewLabel.textContent = payload.mode === "variant"
    ? "延展后"
    : payload.mode === "edit"
      ? "编辑后"
      : payload.mode === "reference"
        ? "参考生成"
        : payload.mode === "itinerary"
          ? "行程路线"
          : "输出"
  const displayedPrompt = payload.prompt || "结果已生成"
  state.lastResultPrompt = displayedPrompt
  refs.resultPrompt.textContent = displayedPrompt
  state.lastResultModel = payload.model || ""
  state.lastResultMode = payload.mode || null
  applyPrimaryResultCandidate(firstCandidate, payload, imageSource, durationMs)

  if (isTransformMode && getAssetDisplaySrc(requestSource)) {
    state.currentComparisonSource = cloneImageAsset(requestSource)
    applySourcePreview(requestSource, payload.mode === "variant" ? "延展前" : "编辑前")

    if (state.lastResultImage) {
      const followupSource = modelInputAssetForLogoWorkflow(state.lastResultImage)
      state.editImage = cloneImageAsset(followupSource, {
        origin: "result",
        generatedImageId: state.lastResultImage.generatedImageId,
        sourceGeneratedImageId: state.lastResultImage.sourceGeneratedImageId || null,
        description: `下一次编辑将默认使用最新输出 · ${state.lastResultImage.name}`,
      })
    }
  } else {
    state.currentComparisonSource = null
    if (state.activeMode !== "edit") {
      clearSourcePreview("原图")
    }

    if (payload.mode === "generate" && state.lastResultImage) {
      const followupSource = modelInputAssetForLogoWorkflow(state.lastResultImage)
      state.editImage = cloneImageAsset(followupSource, {
        origin: "result",
        generatedImageId: state.lastResultImage.generatedImageId,
        sourceGeneratedImageId: state.lastResultImage.sourceGeneratedImageId || null,
        description: `自动使用最新结果 · ${state.lastResultImage.name}`,
      })
    }
  }

  const metaLabel = payload.mode === "variant"
    ? "延展"
    : payload.mode === "edit"
      ? "编辑"
      : payload.mode === "reference"
        ? "参考生成"
        : payload.mode === "itinerary"
          ? "行程路线"
          : "生成"
  const metaParts = [metaLabel, payload.model]
  if (payload.transport === "responses-image") {
    metaParts.push("Responses")
  } else if (payload.transport === "images-edit") {
    metaParts.push("Images Edit")
  } else if (payload.transport === "images-generate") {
    metaParts.push("Images Gen")
  }
  if (payload.logo_requested) {
    metaParts.push("6 人游 LOGO")
  }
  if (payload.size && payload.size !== "auto") {
    metaParts.push(payload.size)
  }
  if (payload.quality && payload.quality !== "auto") {
    metaParts.push(`质量 ${payload.quality}`)
  }
  if (payload.output_format) {
    metaParts.push(payload.output_format.toUpperCase())
  }
  if (payload.background && payload.background !== "auto") {
    metaParts.push(`背景 ${payload.background}`)
  }
  const actualSize = formatActualSize(payload)
  if (actualSize) {
    metaParts.push(`实际 ${actualSize}`)
  }
  refs.resultMeta.textContent = metaParts.filter(Boolean).join(" · ")
  const compositionMessage = payload.composition?.message || ""
  if (payload.mode === "itinerary" && compositionMessage) {
    setStatusMessage(compositionMessage)
  }
  if (payload.size && payload.size !== "auto" && actualSize && !isSameSize(payload.size, actualSize)) {
    setError(`上游返回尺寸为 ${actualSize}，与请求尺寸 ${payload.size} 不一致。图片已按上游原始返回保存，本地没有缩放。`)
  } else {
    setError("")
  }
  state.rawResponsePreview = sanitizeRawResponse(payload.raw_response || {})
  renderRawResponsePreview()

  refs.feedbackReasonPanel?.classList.add("hidden")
  if (refs.feedbackReasonInput) {
    refs.feedbackReasonInput.value = ""
  }
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  renderResultCandidates()
  updateFeedbackPanelVisibility()
  refs.logoComposeStatus.textContent = payload.logo_requested ? "原图已显示，正在贴 LOGO" : "未启用"
  if (payload.logo_requested) {
    setDownloadPendingLogo()
    void composeLogoOverlayAfterDisplay(payload, durationMs, resultGenerationSeq)
  }
  const checks = [
    checkCopyrightRisk(payload),
    checkTextFidelity({ ...payload, text_contract: payload.text_contract || payload.textContract || {} }),
  ]
  void Promise.allSettled(checks)
  void refreshUsageSummary()
  void refreshImageStats()
  void refreshGallery()
  void refreshGenerationJobs()

  updateEditSourceUI()
  updateGenerateIntentUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function historySummary(item) {
  const parts = [item.model]
  if (item.transport === "responses-image") {
    parts.push("Responses")
  }
  if (item.logoRequested) {
    parts.push("6 人游 LOGO")
  }
  if (item.size && item.size !== "auto") {
    parts.push(item.size)
  }
  if (item.quality && item.quality !== "auto") {
    parts.push(item.quality)
  }
  if (item.output_format) {
    parts.push(item.output_format.toUpperCase())
  }
  if (item.mode === "generate" || item.mode === "variant" || item.mode === "reference") {
    return parts.filter(Boolean).join(" · ")
  }
  return parts.filter(Boolean).join(" · ")
}

function renderHistory() {
  refs.historyList.replaceChildren()
  refs.historyEmpty.classList.toggle("hidden", state.history.length > 0)

  state.history.forEach((item) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "history-item"

    const top = document.createElement("span")
    top.className = "history-item-top"

    const mode = document.createElement("strong")
    mode.textContent = item.mode === "variant"
      ? "延展"
      : item.mode === "edit"
        ? "编辑"
        : item.mode === "reference"
          ? "参考生成"
          : item.mode === "itinerary"
            ? "行程路线"
            : "生成"

    const time = document.createElement("time")
    time.textContent = formatTimestamp(item.createdAt)

    const prompt = document.createElement("span")
    prompt.className = "history-item-prompt"
    prompt.textContent = item.prompt

    const meta = document.createElement("span")
    meta.className = "history-item-meta"
    meta.textContent = historySummary(item)

    top.append(mode, time)
    button.append(top, prompt, meta)
    button.addEventListener("click", () => {
      if (item.mode === "itinerary") {
        setMode("itinerary")
        refs.itineraryTitleInput.value = item.itineraryTitle || item.prompt || refs.itineraryTitleInput.value
        refs.itinerarySubtitleInput.value = item.itinerarySubtitle || refs.itinerarySubtitleInput.value
        refs.itinerarySizeSelect.value = item.size || refs.itinerarySizeSelect.value
        refs.itineraryThemeSelect.value = item.itineraryTheme || refs.itineraryThemeSelect.value
        refs.itineraryDescriptionInput.value = item.itineraryDescription || item.prompt
        refs.itineraryLogoEnabled.checked = item.logoRequested !== false
        refs.generateModelInput.value = item.model || refs.generateModelInput.value
        refs.itineraryDescriptionInput.focus()
      } else if (item.mode === "generate" || item.mode === "variant" || item.mode === "reference") {
        setMode("generate")
        setGenerateIntent(item.mode === "variant" ? "variant" : "fresh")
        refs.generatePromptInput.value = item.prompt
        if (item.transport === "responses-image") {
          refs.responsesModelInput.value = item.model
        } else {
          refs.generateModelInput.value = item.model
        }
        setGenerateSize(item.size || state.serverConfig.default_size || "1024x1024")
        updatePromptCounters()
        refs.generatePromptInput.focus()
      } else {
        setMode("edit")
        refs.editPromptInput.value = item.prompt
        if (item.transport === "responses-image") {
          refs.responsesModelInput.value = item.model
        } else {
          refs.editModelInput.value = item.model
        }
        updatePromptCounters()
        refs.editPromptInput.focus()
      }
    })
    refs.historyList.appendChild(button)
  })
}

function pushHistory(item) {
  state.history = [item, ...state.history].slice(0, MAX_HISTORY_ITEMS)
  saveJSON(historyStorageKey(), state.history)
  renderHistory()
}

async function postJSON(url, payload, options = {}) {
  const requestId = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`
  const startedAt = performance.now()
  const timeoutMs = options.timeoutMs || REQUEST_TIMEOUT_MS
  appendDebugLine("准备发送本地代理请求", {
    requestId,
    url,
    mode: options.mode,
    ...summarizePayloadForDebug(payload),
  })
  setProgressPhase("uploading", options.progressLabel || "正在提交请求")

  const controller = new AbortController()
  state.activeRequestController = controller
  state.activeRequestCancelled = false
  const timeoutId = window.setTimeout(() => {
    appendDebugLine("请求超过等待时间，主动中断", { requestId, timeoutMs })
    controller.abort()
  }, timeoutMs)

  const waitingNoticeId = window.setTimeout(() => {
    appendDebugLine("请求仍在等待响应", {
      requestId,
      elapsedMs: Math.round(performance.now() - startedAt),
    })
  }, 5000)

  // 把中断控制权保持到响应体读完为止：以前一收到响应头就清掉
  // activeRequestController，之后如果代理在传输大体积 Base64 响应途中
  // 卡死，超时不再生效、"中断生成"也点不动，页面会永远停在忙碌状态。
  const translateAbort = (error) => {
    if (error.name !== "AbortError") {
      return error
    }
    const requestError = new Error(state.activeRequestCancelled
      ? "用户已中断当前生成。"
      : "请求等待超时。请查看本地服务终端日志，确认后端是否卡在上游接口。")
    requestError.cancelled = state.activeRequestCancelled
    return requestError
  }
  const markFailureUnlessCancelled = (error) => {
    // 用户主动取消走快照恢复；超时/网络失败必须把"等待上游返回"的
    // 占位面板标记为失败，否则面板会永远显示进行中。
    if (!error.cancelled) {
      setPendingResultFailure(error.message, error.details || "")
    }
    return error
  }

  let response
  let data
  try {
    try {
      appendDebugLine("fetch 已发出，等待本地服务响应", { requestId })
      setProgressPhase("waiting", options.waitingLabel || "等待上游生成")
      response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...proxyTokenHeaders(),
        },
        body: JSON.stringify(payload),
        signal: options.signal || controller.signal,
      })
    } catch (error) {
      appendDebugLine("fetch 失败", {
        requestId,
        elapsedMs: Math.round(performance.now() - startedAt),
        error: error.name === "AbortError"
          ? state.activeRequestCancelled ? "用户已中断当前生成" : "请求超时或被中断"
          : error.message,
      })
      throw markFailureUnlessCancelled(translateAbort(error))
    }

    appendDebugLine("本地服务已返回响应头", {
      requestId,
      status: response.status,
      ok: response.ok,
      elapsedMs: Math.round(performance.now() - startedAt),
    })
    setProgressPhase("receiving", "处理上游响应")

    try {
      data = await response.json()
    } catch (error) {
      if (error.name === "AbortError") {
        throw markFailureUnlessCancelled(translateAbort(error))
      }
      appendDebugLine("响应体不是有效 JSON", { requestId })
      throw markFailureUnlessCancelled(new Error("本地服务返回了无法解析的响应。"))
    }
  } finally {
    window.clearTimeout(timeoutId)
    window.clearTimeout(waitingNoticeId)
    if (state.activeRequestController === controller) {
      state.activeRequestController = null
    }
  }

  appendDebugLine("响应 JSON 解析完成", {
    requestId,
    keys: Object.keys(data || {}).join(","),
    elapsedMs: Math.round(performance.now() - startedAt),
  })
  setProgressPhase("receiving", response.ok ? "保存和展示结果" : "整理错误信息")

  if (!response.ok) {
    appendDebugLine("本地代理返回错误", {
      requestId,
      error: data.error || "请求失败",
      details: data.details || "",
    })
    if (isLocalAuthUnauthorized(response, data)) {
      enterAuthGate("login", "登录已过期，请重新登录。")
    }
    const requestError = new Error(data.error || "请求失败")
    requestError.code = data.code || ""
    requestError.details = errorDetailsWithRequestId(data)
    setPendingResultFailure(requestError.message, requestError.details)
    throw requestError
  }

  appendDebugLine("请求完成", {
    requestId,
    elapsedMs: Math.round(performance.now() - startedAt),
  })

  return data
}

async function postJSONSilent(url, payload, timeoutMs = 3 * 60 * 1000) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...proxyTokenHeaders(),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    // 代理/重启期间可能返回 HTML 错误页；裸 response.json() 会把
    // SyntaxError 原文透传到面板上，也会绕过 401 的会话过期处理。
    let data = {}
    try {
      data = await response.json()
    } catch {
      data = {}
    }
    if (!response.ok) {
      if (isLocalAuthUnauthorized(response, data)) {
        enterAuthGate("login", "登录已过期，请重新登录。")
      }
      const requestError = new Error(data.error || "请求失败")
      requestError.details = errorDetailsWithRequestId(data)
      throw requestError
    }
    return data
  } finally {
    window.clearTimeout(timeoutId)
  }
}

async function checkCopyrightRisk(payload) {
  const riskRequestSeq = state.copyrightRiskRequestSeq += 1
  const resultGenerationSeq = state.resultGenerationSeq
  const settings = getSettings()
  if (!settings.apiKey && !state.serverConfig?.has_default_api_key) {
    setRiskPanel("未检查", "未填写 API Key，无法调用 gpt-5.5 做版权风险提醒。")
    return
  }

  const selectedCandidate = state.resultCandidates[state.selectedCandidateIndex] || state.resultCandidates[0]
  const selectedAsset = selectedCandidate?.asset || candidateAsset(selectedCandidate || {}, payload, state.selectedCandidateIndex || 0)
  let sourceDataUrl = selectedAsset?.dataUrl || selectedCandidate?.image_data_url || ""
  // Results are now served from the saved file URL instead of an inline data
  // URL, so fetch the pixels on demand when we only have a URL.
  if (!sourceDataUrl && selectedAsset) {
    try {
      sourceDataUrl = await ensureAssetDataUrl(selectedAsset)
      if (riskRequestSeq !== state.copyrightRiskRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
        return
      }
    } catch (error) {
      appendDebugLine("版权检查取图失败", { error: error.message })
    }
  }
  let reviewDataUrl = ""
  try {
    reviewDataUrl = await downscaleDataUrlForRisk(sourceDataUrl)
  } catch (error) {
    // 图片解码失败时必须复位面板：否则上一张图的“已检查”结论会一直
    // 挂在新图上，看起来像新图已通过检查。
    appendDebugLine("版权检查图片预处理失败", { error: error.message })
    setRiskPanel("未检查", "当前图片无法解码用于版权检查。")
    return
  }
  if (riskRequestSeq !== state.copyrightRiskRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
    return
  }
  const images = reviewDataUrl
    ? [{
        name: selectedAsset?.name || "selected-result.jpg",
        type: inferMimeFromDataUrl(reviewDataUrl),
        data_url: reviewDataUrl,
      }]
    : []

  if (!images.length) {
    setRiskPanel("未检查", "当前结果没有可直接发送给 gpt-5.5 的图片数据。")
    return
  }

  setRiskPanel("检查中", "正在调用 gpt-5.5 查看当前选中结果里的商标、活动标识、Logo、IP 和版权元素风险。")
  try {
    const result = await postJSONSilent("api/copyright-risk", {
      api_key: settings.apiKey,
      endpoint_url: settings.responsesUrl,
      model: settings.responsesModel || state.serverConfig?.default_responses_model || "gpt-5.5",
      prompt: payload.prompt || state.lastResultPrompt || "",
      context: [
        `模式：${payload.mode || ""}`,
        `模型：${payload.model || ""}`,
        `尺寸：${payload.size || ""}`,
        `素材来源：用户上传/用户授权`,
      ].filter(Boolean).join("\n"),
      images,
    })
    if (riskRequestSeq !== state.copyrightRiskRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    setRiskPanel("已检查", result.risk_text || "未见明显风险，但商用前仍建议确认素材授权链。")
  } catch (error) {
    if (riskRequestSeq !== state.copyrightRiskRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    appendDebugLine("版权风险检查失败", { error: error.message })
    setRiskPanel("检查失败", error.message || "版权风险检查失败，不影响图片生成结果。")
  }
}

async function checkTextFidelity(payload) {
  const contract = payload.text_contract || payload.textContract || {}
  const required = Array.isArray(contract.required) ? contract.required.filter(Boolean) : []
  const forbidden = Array.isArray(contract.forbidden) ? contract.forbidden.filter(Boolean) : []
  // 编辑模式即使没有契约也要检查：用"编辑前 vs 编辑后"对比防止正文被
  // 偷偷换字。其它模式在契约为空时退回"以完整提示词为文字来源"（后端
  // 支持），只有连提示词都没有时才跳过——以前契约抽取不到标签（表格、
  // 自由排版提示词很常见）就直接放行，生产上的错字正是这样漏掉的。
  const editCompare = payload.mode === "edit" && Boolean(state.currentComparisonSource)
  const fidelityPrompt = payload.prompt || state.lastResultPrompt || ""
  if (!required.length && !forbidden.length && !editCompare && !fidelityPrompt.trim()) {
    setTextFidelityPanel("未检查", "当前提示词没有可核对的上屏文案。", { hidden: true })
    return
  }

  const fidelityRequestSeq = state.textFidelityRequestSeq += 1
  const resultGenerationSeq = state.resultGenerationSeq
  const settings = getSettings()
  if (!settings.apiKey && !state.serverConfig?.has_default_api_key) {
    setTextFidelityPanel("未检查", "未填写 API Key，无法调用 gpt-5.5 做文字一致性检查。")
    return
  }

  const selectedCandidate = state.resultCandidates[state.selectedCandidateIndex] || state.resultCandidates[0]
  const selectedAsset = selectedCandidate?.asset || candidateAsset(selectedCandidate || {}, payload, state.selectedCandidateIndex || 0)
  let sourceDataUrl = selectedAsset?.dataUrl || selectedCandidate?.image_data_url || ""
  if (!sourceDataUrl && selectedAsset) {
    try {
      sourceDataUrl = await ensureAssetDataUrl(selectedAsset)
      if (fidelityRequestSeq !== state.textFidelityRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
        return
      }
    } catch (error) {
      appendDebugLine("文字一致性检查取图失败", { error: error.message })
    }
  }
  // 前后对比模式要辨认单个汉字的差异，分辨率降得太低会把形近字抹平。
  const fidelityMaxEdge = editCompare ? 2048 : 1600
  let reviewDataUrl = ""
  try {
    reviewDataUrl = await downscaleDataUrlForRisk(sourceDataUrl, fidelityMaxEdge, 0.95)
  } catch (error) {
    appendDebugLine("文字一致性检查缩略图失败", { error: error.message })
    setTextFidelityPanel("检查失败", error.message || "文字一致性检查无法读取结果图。")
    return
  }
  if (fidelityRequestSeq !== state.textFidelityRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
    return
  }
  const images = reviewDataUrl
    ? [{
        name: selectedAsset?.name || "selected-result.jpg",
        type: inferMimeFromDataUrl(reviewDataUrl),
        data_url: reviewDataUrl,
      }]
    : []

  if (!images.length) {
    setTextFidelityPanel("未检查", "当前结果没有可直接发送给 gpt-5.5 的图片数据。")
    return
  }

  if (editCompare) {
    // 前后对比模式：第 1 张 = 编辑前，第 2 张 = 编辑后。后端会核对
    // 未被要求修改的文字是否逐字保留。
    try {
      const beforeRaw = await ensureAssetDataUrl(state.currentComparisonSource)
      const beforeReview = await downscaleDataUrlForRisk(beforeRaw, fidelityMaxEdge, 0.95)
      if (fidelityRequestSeq !== state.textFidelityRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
        return
      }
      if (beforeReview) {
        images.unshift({
          name: "edit-source.jpg",
          type: inferMimeFromDataUrl(beforeReview),
          data_url: beforeReview,
        })
      }
    } catch (error) {
      appendDebugLine("文字一致性检查读取编辑前图失败，退回单图检查", { error: error.message })
    }
  }

  setTextFidelityPanel("检查中", images.length >= 2
    ? "正在对比编辑前后的画面文字，未要求修改的部分必须逐字保留。"
    : "正在核对成图中文字是否逐字匹配用户输入。")
  try {
    const result = await postJSONSilent("api/text-fidelity", {
      api_key: settings.apiKey,
      endpoint_url: settings.responsesUrl,
      model: settings.responsesModel || state.serverConfig?.default_responses_model || "gpt-5.5",
      prompt: fidelityPrompt,
      context: [
        `模式：${payload.mode || ""}`,
        `模型：${payload.model || ""}`,
        `尺寸：${payload.size || ""}`,
      ].filter(Boolean).join("\n"),
      text_contract: { required, forbidden },
      images,
    })
    if (fidelityRequestSeq !== state.textFidelityRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    if (result.passed) {
      setTextFidelityPanel("文字通过", result.fidelity_text || "文字一致性检查通过。")
    } else {
      setTextFidelityPanel("文字需复核", result.fidelity_text || "文字一致性检查未通过。")
      setError("文字一致性检查未通过：请复核成图文字，必要时再次编辑或重生成。")
    }
  } catch (error) {
    if (fidelityRequestSeq !== state.textFidelityRequestSeq || resultGenerationSeq !== state.resultGenerationSeq) {
      return
    }
    appendDebugLine("文字一致性检查失败", { error: error.message })
    setTextFidelityPanel("检查失败", error.message || "文字一致性检查失败，不影响图片生成结果。")
  }
}

async function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error("读取图片失败。"))
    reader.readAsDataURL(file)
  })
}

async function blobToDataURL(blob) {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error("读取图片失败。"))
    reader.readAsDataURL(blob)
  })
}

async function loadImageElement(src, errorMessage = "无法读取图片。") {
  return await new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error(errorMessage))
    image.src = src
  })
}

function imageDataUrlName(baseName, suffix) {
  const safeBase = String(baseName || "picgen-result.png")
  const dotIndex = safeBase.lastIndexOf(".")
  if (dotIndex <= 0) {
    return `${safeBase}-${suffix}.png`
  }
  return `${safeBase.slice(0, dotIndex)}-${suffix}.png`
}

function findOpaqueContentBounds(imageData, alphaThreshold = 0) {
  const { data, width, height } = imageData
  let minX = width
  let minY = height
  let maxX = -1
  let maxY = -1

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = data[(y * width + x) * 4 + 3]
      if (alpha <= alphaThreshold) {
        continue
      }
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    }
  }

  if (maxX < minX || maxY < minY) {
    return { x: 0, y: 0, width, height }
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX + 1,
    height: maxY - minY + 1,
  }
}

function hasTransparentLogoBackground(imageData) {
  let hasVisiblePixel = false
  let hasFullyTransparentPixel = false
  for (let index = 3; index < imageData.data.length; index += 4) {
    const alpha = imageData.data[index]
    if (alpha === 0) {
      hasFullyTransparentPixel = true
    } else {
      hasVisiblePixel = true
    }
    if (hasVisiblePixel && hasFullyTransparentPixel) {
      return true
    }
  }
  return false
}

function createOfficialLogoCanvas(image) {
  const sourceCanvas = document.createElement("canvas")
  sourceCanvas.width = image.naturalWidth || image.width
  sourceCanvas.height = image.naturalHeight || image.height
  const sourceCtx = sourceCanvas.getContext("2d", { willReadFrequently: true })
  if (!sourceCtx) {
    throw new Error("当前浏览器无法处理 LOGO 图片。")
  }

  sourceCtx.drawImage(image, 0, 0)
  const imageData = sourceCtx.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height)
  if (!hasTransparentLogoBackground(imageData)) {
    throw new Error("官方 LOGO 缺少透明背景，请上传带透明通道的 6renyou.png。")
  }
  const bounds = findOpaqueContentBounds(imageData, 0)

  const logoCanvas = document.createElement("canvas")
  logoCanvas.width = bounds.width
  logoCanvas.height = bounds.height
  const logoCtx = logoCanvas.getContext("2d")
  if (!logoCtx) {
    throw new Error("当前浏览器无法处理 LOGO 图片。")
  }
  logoCtx.putImageData(imageData, -bounds.x, -bounds.y)
  return logoCanvas
}

function calculateRegionComplexity(ctx, region) {
  const x = Math.max(0, Math.floor(region.x))
  const y = Math.max(0, Math.floor(region.y))
  const width = Math.max(1, Math.min(ctx.canvas.width - x, Math.floor(region.width)))
  const height = Math.max(1, Math.min(ctx.canvas.height - y, Math.floor(region.height)))
  const sampleWidth = Math.max(1, Math.min(24, width))
  const sampleHeight = Math.max(1, Math.min(12, height))
  const imageData = ctx.getImageData(x, y, width, height)
  let total = 0
  let count = 0
  let previous = null
  for (let sy = 0; sy < sampleHeight; sy += 1) {
    const py = Math.min(height - 1, Math.floor((sy / sampleHeight) * height))
    for (let sx = 0; sx < sampleWidth; sx += 1) {
      const px = Math.min(width - 1, Math.floor((sx / sampleWidth) * width))
      const index = (py * width + px) * 4
      const luminance = 0.2126 * imageData.data[index]
        + 0.7152 * imageData.data[index + 1]
        + 0.0722 * imageData.data[index + 2]
      if (previous !== null) {
        total += Math.abs(luminance - previous)
        count += 1
      }
      previous = luminance
    }
  }
  return count ? total / count : 0
}

async function loadCompanyLogoCanvas() {
  if (state.companyLogoCanvas) {
    return state.companyLogoCanvas
  }
  const logoImage = await loadImageElement(COMPANY_LOGO_URL, "无法读取 6 人游 LOGO 图片。")
  state.companyLogoCanvas = createOfficialLogoCanvas(logoImage)
  return state.companyLogoCanvas
}

function calculateLogoPlacement(canvas, logoCanvas) {
  const targetWidth = Math.round(
    Math.min(
      COMPANY_LOGO_MAX_WIDTH,
      Math.max(COMPANY_LOGO_MIN_WIDTH, canvas.width * COMPANY_LOGO_WIDTH_RATIO),
    ),
  )
  const targetHeight = Math.max(1, Math.round(targetWidth * (logoCanvas.height / logoCanvas.width)))
  const margin = Math.round(
    Math.min(
      COMPANY_LOGO_MAX_MARGIN,
      Math.max(COMPANY_LOGO_MIN_MARGIN, Math.min(canvas.width, canvas.height) * COMPANY_LOGO_MARGIN_RATIO),
    ),
  )
  const candidates = [
    { x: margin, y: margin, width: targetWidth, height: targetHeight },
    { x: margin, y: Math.min(canvas.height - targetHeight - margin, margin + Math.round(targetHeight * 0.72)), width: targetWidth, height: targetHeight },
    { x: Math.min(canvas.width - targetWidth - margin, margin + Math.round(targetWidth * 0.42)), y: margin, width: targetWidth, height: targetHeight },
  ].filter((placement) => placement.x >= 0 && placement.y >= 0)

  const ctx = canvas.getContext("2d")
  if (!ctx) {
    return candidates[0]
  }
  return candidates
    .map((placement) => ({
      placement,
      complexity: calculateRegionComplexity(ctx, {
        x: placement.x,
        y: placement.y,
        width: placement.width,
        height: placement.height,
      }),
    }))
    .sort((left, right) => left.complexity - right.complexity)[0]?.placement || candidates[0]
}

function drawCanvasWithHighQuality(ctx, canvas, width, height) {
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = "high"
  ctx.drawImage(canvas, 0, 0, width, height)
}

function resizeCanvasHighQuality(sourceCanvas, targetWidth, targetHeight) {
  const finalWidth = Math.max(1, Math.round(targetWidth))
  const finalHeight = Math.max(1, Math.round(targetHeight))
  let currentCanvas = sourceCanvas

  while (currentCanvas.width > finalWidth * 2 && currentCanvas.height > finalHeight * 2) {
    const nextCanvas = document.createElement("canvas")
    nextCanvas.width = Math.max(finalWidth, Math.round(currentCanvas.width / 2))
    nextCanvas.height = Math.max(finalHeight, Math.round(currentCanvas.height / 2))
    const nextCtx = nextCanvas.getContext("2d")
    if (!nextCtx) {
      throw new Error("当前浏览器无法缩放 LOGO。")
    }
    drawCanvasWithHighQuality(nextCtx, currentCanvas, nextCanvas.width, nextCanvas.height)
    currentCanvas = nextCanvas
  }

  if (currentCanvas.width === finalWidth && currentCanvas.height === finalHeight) {
    return currentCanvas
  }

  const finalCanvas = document.createElement("canvas")
  finalCanvas.width = finalWidth
  finalCanvas.height = finalHeight
  const finalCtx = finalCanvas.getContext("2d")
  if (!finalCtx) {
    throw new Error("当前浏览器无法缩放 LOGO。")
  }
  drawCanvasWithHighQuality(finalCtx, currentCanvas, finalWidth, finalHeight)
  return finalCanvas
}

async function applyLogoOverlayToDataUrl(dataUrl) {
  if (!dataUrl) {
    return null
  }

  const [baseImage, logoCanvas] = await Promise.all([
    loadImageElement(dataUrl, "无法读取上游返回图片。"),
    loadCompanyLogoCanvas(),
  ])
  const width = baseImage.naturalWidth || baseImage.width
  const height = baseImage.naturalHeight || baseImage.height
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) {
    throw new Error("当前浏览器无法合成 LOGO。")
  }

  ctx.drawImage(baseImage, 0, 0, width, height)
  const placement = calculateLogoPlacement(canvas, logoCanvas)
  const scaledLogoCanvas = resizeCanvasHighQuality(logoCanvas, placement.width, placement.height)
  ctx.drawImage(scaledLogoCanvas, placement.x, placement.y)
  return {
    dataUrl: canvas.toDataURL(COMPANY_LOGO_MIME),
    width,
    height,
    placement: {
      ...placement,
      textColor: "original",
    },
  }
}

async function persistFinalLogoImage(candidate, asset, composed, composedName) {
  const generatedImageId = candidate.generated_image_id || asset.generatedImageId || null
  if (!generatedImageId || !composed?.dataUrl) {
    return null
  }
  const response = await postJSONSilent("api/final-images", {
    generated_image_id: generatedImageId,
    source_saved_image_path: candidate.saved_image_path || asset.savedPath || asset.originalSavedPath || "",
    source_saved_image_url: candidate.saved_image_url || asset.savedUrl || asset.originalSavedUrl || "",
    logo_overlay_applied: true,
    logo_overlay_source: COMPANY_LOGO_NAME,
    logo_text_color: composed.placement?.textColor || "original",
    image: {
      name: composedName,
      type: COMPANY_LOGO_MIME,
      data_url: composed.dataUrl,
    },
  }, REQUEST_TIMEOUT_MS)
  return response.image || null
}

async function composeLogoOverlayForCandidates(candidates, logoRequested) {
  if (!logoRequested) {
    refs.logoComposeStatus.textContent = "未启用"
    return candidates
  }

  refs.logoComposeStatus.textContent = "本地合成中"
  setProgressPhase("receiving", "本地合成 LOGO")
  appendDebugLine("本地贴入 6 人游 LOGO", {
    source: COMPANY_LOGO_NAME,
    placement: "top-left",
    alphaMode: "official-transparent-png",
  })

  const composedCandidates = []
  for (const candidate of candidates) {
    const asset = candidate.asset
    if (!asset) {
      composedCandidates.push(candidate)
      continue
    }
    const sourceDataUrl = asset.dataUrl || await ensureAssetDataUrl(asset)
    const composed = await applyLogoOverlayToDataUrl(sourceDataUrl)
    if (!composed) {
      composedCandidates.push(candidate)
      continue
    }
    const composedName = imageDataUrlName(asset.name || candidate.saved_image_name, "6renyou-logo")
    let persisted = null
    try {
      persisted = await persistFinalLogoImage(candidate, asset, composed, composedName)
    } catch (error) {
      appendDebugLine("LOGO 成品回传落盘失败", { error: error.message })
    }
    const serverUrl = persisted?.saved_image_url || ""
    const displaySrc = serverUrl || composed.dataUrl
    const composedAsset = {
      ...asset,
      name: persisted?.saved_image_name || composedName,
      type: COMPANY_LOGO_MIME,
      dataUrl: serverUrl ? "" : composed.dataUrl,
      savedUrl: serverUrl,
      fileUrl: serverUrl,
      src: displaySrc,
      originalDataUrl: sourceDataUrl,
      originalSavedUrl: asset.savedUrl,
      originalFileUrl: asset.fileUrl,
      originalSavedPath: asset.savedPath,
      savedPath: persisted?.saved_image_path || "",
      metadataPath: persisted?.saved_metadata_path || "",
      generatedImageId: persisted?.generated_image_id || candidate.generated_image_id || asset.generatedImageId || null,
      logoOverlayApplied: true,
      logoPlacement: composed.placement,
      description: serverUrl
        ? `${asset.description || asset.name || "结果图"} · 已保存 6 人游 LOGO 成品`
        : `${asset.description || asset.name || "结果图"} · 已本地贴入 6 人游 LOGO`,
    }
    composedCandidates.push({
      ...candidate,
      image_data_url: serverUrl ? null : composed.dataUrl,
      saved_image_url: serverUrl,
      saved_image_path: persisted?.saved_image_path || "",
      saved_metadata_path: persisted?.saved_metadata_path || "",
      saved_metadata_url: persisted?.saved_metadata_url || "",
      saved_image_name: persisted?.saved_image_name || composedName,
      saved_image_mime: COMPANY_LOGO_MIME,
      saved_image_width: persisted?.saved_image_width || composed.width,
      saved_image_height: persisted?.saved_image_height || composed.height,
      saved_image_bytes: persisted?.saved_image_bytes || candidate.saved_image_bytes || 0,
      generated_image_id: persisted?.generated_image_id || candidate.generated_image_id || null,
      logo_overlay_applied: true,
      logo_overlay_source: COMPANY_LOGO_NAME,
      logo_text_color: composed.placement.textColor || "original",
      logo_final_persisted: Boolean(serverUrl),
      asset: composedAsset,
    })
  }
  refs.logoComposeStatus.textContent = composedCandidates.some((candidate) => candidate.logo_final_persisted)
    ? "成品已保存"
    : "本地已贴图"
  return composedCandidates
}

async function downscaleDataUrlForRisk(dataUrl, maxSide = 768, quality = 0.82) {
  if (!dataUrl) {
    return ""
  }
  const image = await loadImageElement(dataUrl, "无法读取版权风险检查图片。")
  const naturalWidth = image.naturalWidth || image.width
  const naturalHeight = image.naturalHeight || image.height
  const scale = Math.min(1, maxSide / Math.max(naturalWidth, naturalHeight))
  const width = Math.max(1, Math.round(naturalWidth * scale))
  const height = Math.max(1, Math.round(naturalHeight * scale))
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) {
    return dataUrl
  }
  ctx.drawImage(image, 0, 0, width, height)
  return canvas.toDataURL("image/jpeg", quality)
}

async function ensureAssetDataUrl(asset) {
  if (asset?.dataUrl) {
    return asset.dataUrl
  }

  const assetSource = getAssetDisplaySrc(asset)
  if (!assetSource) {
    throw new Error("当前没有可编辑图片。先生成一张图，或手动上传一张图片。")
  }

  const response = await fetch(assetSource)
  if (!response.ok) {
    throw new Error("无法读取已保存的图片文件。")
  }

  const blob = await response.blob()
  const dataUrl = await blobToDataURL(blob)
  asset.dataUrl = dataUrl
  asset.type = asset.type || blob.type || inferMimeFromDataUrl(dataUrl)
  return dataUrl
}

function validateClientImageFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }
  if (file.size > CLIENT_IMAGE_UPLOAD_MAX_BYTES) {
    throw new Error(`图片文件过大，请选择 ${formatFileSize(CLIENT_IMAGE_UPLOAD_MAX_BYTES)} 以内的图片。`)
  }
}

async function useImageFile(file) {
  validateClientImageFile(file)

  const dataUrl = await fileToDataURL(file)
  setEditImage(
    {
      name: file.name,
      type: file.type,
      dataUrl,
      origin: "upload",
      description: `${file.name} · ${formatFileSize(file.size)}`,
    },
    { showPreview: true, previewLabel: "输入图" },
  )
}

async function useMaskFile(file) {
  validateClientImageFile(file)

  const dataUrl = await fileToDataURL(file)
  setEditMaskImage({
    name: file.name,
    type: file.type,
    dataUrl,
    origin: "mask",
    description: `${file.name} · ${formatFileSize(file.size)}`,
  })
}

async function useGenerateReferenceFile(file) {
  validateClientImageFile(file)

  const dataUrl = await fileToDataURL(file)
  setGenerateReferenceImage(
    {
      name: file.name,
      type: file.type,
      dataUrl,
      origin: "reference",
      description: `${file.name} · ${formatFileSize(file.size)}`,
    },
    { showPreview: true },
  )
}

async function useStyleReferenceFile(file) {
  validateClientImageFile(file)

  const dataUrl = await fileToDataURL(file)
  setStyleReferenceImage(
    {
      name: file.name,
      type: file.type,
      dataUrl,
      origin: "style_template",
      role: "style_template",
      description: `${file.name} · ${formatFileSize(file.size)}`,
    },
    { showPreview: true },
  )
}

async function useMaterialReferenceFile(file) {
  validateClientImageFile(file)

  const dataUrl = await fileToDataURL(file)
  setMaterialReferenceImage(
    {
      name: file.name,
      type: file.type,
      dataUrl,
      origin: "material",
      role: "material",
      description: `${file.name} · ${formatFileSize(file.size)}`,
    },
    { showPreview: true },
  )
}

async function submitVariantGenerate({ resetLog = true } = {}) {
  if (resetLog) {
    resetDebugLog("点击生成按钮：基于当前结果延展")
  }
  const promptPlan = buildEffectiveGeneratePrompt()
  let prompt = promptPlan.originalPrompt
  let effectivePrompt = promptPlan.effectivePrompt
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2"
  const logoRequested = shouldUseCompanyLogo()
  const itineraryId = getExplicitItineraryId()
  let confirmedPrompt = ""
  let imageOptions
  let size
  let forceResponsesForSize = false
  let model = imageModel
  let transport = "images-edit"

  if (!state.lastResultImage) {
    appendDebugLine("参数校验失败：没有可延展的结果图")
    setError("还没有可延展的结果图。先生成第一张图，再基于它换风格或换方向。")
    return
  }

  if (!prompt.trim()) {
    appendDebugLine("参数校验失败：延展提示词为空")
    setError("延展提示词不能为空。")
    refs.generatePromptInput.focus()
    return
  }

  try {
    imageOptions = getOpenAIImageOptions()
    size = getGenerateSize()
    forceResponsesForSize = shouldUseResponsesForSelectedSize(size)
    model = useResponses || forceResponsesForSize ? settings.responsesModel : imageModel
    transport = useResponses || forceResponsesForSize ? "responses-image" : "images-edit"
  } catch (error) {
    appendDebugLine("参数校验失败：OpenAI 图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

  if (useResponses || forceResponsesForSize) {
    if (!requireResponsesSettings(settings, forceResponsesForSize ? "基于当前结果延展的精确海报尺寸" : "基于当前结果延展")) {
      return
    }
  } else if (!requireEditSettings(settings, "基于当前结果延展")) {
    return
  }

  const confirmedText = await confirmPromptBeforeRun("generate", effectivePrompt)
  if (confirmedText === null) {
    appendDebugLine("用户取消延展提示词确认")
    return
  }
  prompt = confirmedText
  effectivePrompt = confirmedText
  if (promptPlan.promptMode === "free") {
    refs.generatePromptInput.value = confirmedText
    updatePromptCounters()
    updateEffectivePromptPreview()
  }
  const textContract = buildVisibleTextContract(effectivePrompt)
  confirmedPrompt = withLogoLayoutPrompt(effectivePrompt, logoRequested)

  const requestSnapshot = currentFormSnapshot()
  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "延展中", { progressLabel: "准备延展图像" })

  const requestSource = cloneImageAsset(modelInputAssetForLogoWorkflow(state.lastResultImage))
  previewPendingResult({
    mode: "variant",
    prompt,
    model,
    size,
    sourceName: requestSource.name || "最新结果",
  })
  const startedAt = performance.now()

  try {
    appendDebugLine("读取延展输入图片")
    setProgressPhase("preparing", "读取参考图")
    const requestSourceDataUrl = await ensureAssetDataUrl(requestSource)
    ensureRequestNotCancelled()
    const sourceGeneratedImageId = requestSource.generatedImageId || state.lastResultImage?.generatedImageId || null
    const imagePart = {
      name: requestSource.name,
      type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
      data_url: requestSourceDataUrl,
      role: "source_image",
    }
    let result
    if (useResponses || forceResponsesForSize) {
      if (forceResponsesForSize && !useResponses) {
        appendDebugLine("非标准海报尺寸改走 Responses 图像工具，避免 Images API 静默降级尺寸", { size })
      }
      result = await postJSON("api/responses-image", {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: confirmedPrompt,
        model,
        mode: "variant",
        transport: "responses-image",
        allow_inline_fallback: true,
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        source_generated_image_id: sourceGeneratedImageId,
        text_contract: textContract,
        ...sourceImageIdentityFields(requestSource),
        size,
        ...imageOptions,
        image: imagePart,
        images: [imagePart],
      }, {
        mode: "variant",
        progressLabel: "提交延展请求",
        waitingLabel: "等待上游延展",
      })
    } else {
      result = await postJSON("api/edit", {
        api_key: settings.apiKey,
        endpoint_url: settings.editUrl,
        prompt: confirmedPrompt,
        model,
        mode: "variant",
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        source_generated_image_id: sourceGeneratedImageId,
        text_contract: textContract,
        ...sourceImageIdentityFields(requestSource),
        size,
        ...imageOptions,
        image: imagePart,
        images: [imagePart],
      }, {
        mode: "variant",
        progressLabel: "提交延展请求",
        waitingLabel: "等待上游延展",
      })
    }
    await setResult({ ...result, mode: "variant", prompt, transport, logo_requested: logoRequested, text_contract: textContract }, performance.now() - startedAt, requestSource)
    rememberRegenerationRequest("generate", requestSnapshot)
    pushHistory({
      mode: "variant",
      prompt,
      model,
      transport,
      logoRequested,
      itineraryId,
      textContract,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("延展请求失败", { error: error.message })
    if (error.cancelled && restorePendingResultAfterCancellation()) {
      setStatusMessage("已中断生成，上一张结果已保留。")
    } else {
      setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
    }
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

async function submitGenerate() {
  if (state.isBusy) {
    return
  }
  if (state.generateIntent === "variant") {
    resetDebugLog("点击生成按钮：基于当前结果延展")
    appendDebugLine("当前生成方式为延展，转入编辑接口")
    await submitVariantGenerate({ resetLog: false })
    return
  }

  resetDebugLog("点击生成按钮：生成图片")

  const promptPlan = buildEffectiveGeneratePrompt()
  let prompt = promptPlan.originalPrompt
  let effectivePrompt = promptPlan.effectivePrompt
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2"
  const referenceImages = generateReferenceImages()
  const dualReference = hasStyleTransferReferences()
  const logoRequested = shouldUseCompanyLogo()
  const itineraryId = getExplicitItineraryId()
  let baseRequestPrompt = dualReference ? styleTransferPrompt(effectivePrompt) : effectivePrompt
  let confirmedPrompt = ""
  const requiresReferenceTransport = referenceImages.length > 0
  let forceResponsesForSize = false
  let referenceViaResponses = useResponses
  let textGenerateViaResponses = useResponses
  let model = imageModel

  if (!prompt.trim()) {
    appendDebugLine("参数校验失败：生成提示词为空")
    setError("生成提示词不能为空。")
    refs.generatePromptInput.focus()
    return
  }
  if (refs.itineraryIdEnabled?.checked && !itineraryId) {
    appendDebugLine("参数校验失败：行程 ID 为空")
    setError("已勾选行程 ID，请填写 ID，或取消勾选。")
    refs.itineraryIdInput?.focus()
    return
  }
  if (rejectLegacyProgramLayoutBackgroundPrompt(prompt) || rejectLegacyProgramLayoutBackgroundPrompt(effectivePrompt)) {
    return
  }

  let size
  let imageOptions
  let sampleCount
  try {
    size = getGenerateSize()
    imageOptions = getOpenAIImageOptions()
    sampleCount = referenceImages.length ? 1 : getGenerateSampleCount()
    forceResponsesForSize = shouldUseResponsesForSelectedSize(size)
    referenceViaResponses = useResponses || forceResponsesForSize
    textGenerateViaResponses = useResponses || forceResponsesForSize
    model = referenceImages.length && referenceViaResponses ? settings.responsesModel : imageModel
  } catch (error) {
    appendDebugLine("参数校验失败：OpenAI 图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

  if (requiresReferenceTransport) {
    if (referenceViaResponses) {
      if (!requireResponsesSettings(settings, "带参考图生成")) {
        return
      }
    } else if (!requireEditSettings(settings, "带参考图生成")) {
      return
    }
  } else if (textGenerateViaResponses) {
    if (!requireResponsesSettings(settings, "精确海报尺寸生成")) {
      return
    }
  } else if (!settings.generateUrl) {
    appendDebugLine("参数校验失败：生成接口 URL 为空")
    setError("请先填写生成接口 URL。")
    refs.generateUrlInput.focus()
    return
  }

  const confirmedText = await confirmPromptBeforeRun("generate", effectivePrompt)
  if (confirmedText === null) {
    appendDebugLine("用户取消生成提示词确认")
    return
  }
  prompt = confirmedText
  effectivePrompt = confirmedText
  if (promptPlan.promptMode === "free") {
    refs.generatePromptInput.value = confirmedText
    updatePromptCounters()
    updateEffectivePromptPreview()
  }
  baseRequestPrompt = dualReference ? styleTransferPrompt(effectivePrompt) : effectivePrompt
  const textContract = buildVisibleTextContract(baseRequestPrompt)
  confirmedPrompt = withLogoLayoutPrompt(baseRequestPrompt, logoRequested)

  const requestSnapshot = currentFormSnapshot()
  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "生成中", {
    progressLabel: "准备生成图像",
    expectedCount: dualReference ? STYLE_TRANSFER_SAMPLE_COUNT : sampleCount,
    estimatedSecondsPerImage: 210,
  })
  previewPendingResult({
    mode: requiresReferenceTransport ? "reference" : "generate",
    prompt,
    model,
    size,
    sourceName: dualReference ? "风格模板 + 素材图" : referenceImages[0]?.name || "",
  })

  const startedAt = performance.now()

  try {
    if (requiresReferenceTransport) {
      appendDebugLine("读取生成参考图")
      setProgressPhase("preparing", "读取参考图")
      const requestSources = referenceImages.map((asset) => cloneImageAsset(asset))
      const referenceParts = []
      for (const referenceSource of requestSources) {
        const referenceDataUrl = await ensureAssetDataUrl(referenceSource)
        ensureRequestNotCancelled()
        referenceParts.push({
          name: referenceSource.name,
          type: referenceSource.type || inferMimeFromDataUrl(referenceDataUrl),
          data_url: referenceDataUrl,
          role: referenceSource.role || referenceSource.origin || "reference",
        })
      }
      const requestParts = referenceParts
      const referencePart = requestParts.at(-1)
      const referenceLineageSource = requestSources.at(-1)
      const sourceGeneratedImageId = referenceLineageSource?.generatedImageId || null
      const transport = referenceViaResponses ? "responses-image" : "images-edit"
      const referenceSampleCount = dualReference ? STYLE_TRANSFER_SAMPLE_COUNT : sampleCount
      let result
      if (referenceViaResponses) {
        if (forceResponsesForSize && !useResponses) {
          appendDebugLine("非标准海报尺寸改走 Responses 图像工具，避免 Images API 静默降级尺寸", { size })
        }
        result = await postJSON("api/responses-image", {
          api_key: settings.apiKey,
          endpoint_url: settings.responsesUrl,
          prompt: confirmedPrompt,
          original_prompt: prompt,
          prompt_mode: promptPlan.promptMode,
          recipe_id: promptPlan.recipe?.id || "",
          recipe_version: promptPlan.recipe?.version || "",
          model: settings.responsesModel,
          mode: "reference",
          transport: "responses-image",
          allow_inline_fallback: true,
          logo_requested: logoRequested,
          itinerary_id: itineraryId,
          source_generated_image_id: sourceGeneratedImageId,
          text_contract: textContract,
          ...sourceImageIdentityFields(referenceLineageSource),
          sample_count: referenceSampleCount,
          size,
          ...imageOptions,
          image: referencePart,
          images: requestParts,
        }, {
          mode: "reference",
          progressLabel: "提交参考图生成",
          waitingLabel: "等待上游参考生成",
        })
      } else {
        result = await postJSON("api/edit", {
          api_key: settings.apiKey,
          endpoint_url: settings.editUrl,
          prompt: confirmedPrompt,
          original_prompt: prompt,
          prompt_mode: promptPlan.promptMode,
          recipe_id: promptPlan.recipe?.id || "",
          recipe_version: promptPlan.recipe?.version || "",
          model: imageModel,
          mode: "reference",
          logo_requested: logoRequested,
          itinerary_id: itineraryId,
          source_generated_image_id: sourceGeneratedImageId,
          text_contract: textContract,
          ...sourceImageIdentityFields(referenceLineageSource),
          sample_count: referenceSampleCount,
          size,
          ...imageOptions,
          image: referencePart,
          images: requestParts,
        }, {
          mode: "reference",
          progressLabel: "提交参考图生成",
          waitingLabel: "等待上游参考生成",
        })
      }
      await setResult({ ...result, mode: "reference", prompt, size, transport, logo_requested: logoRequested, text_contract: textContract }, performance.now() - startedAt, requestSources.at(-1))
      rememberRegenerationRequest("generate", requestSnapshot)
      pushHistory({
        mode: "reference",
        prompt,
        model: referenceViaResponses ? settings.responsesModel : imageModel,
        transport,
        logoRequested,
        itineraryId,
        sourceGeneratedImageId,
        textContract,
        size,
        sampleCount: referenceSampleCount,
        ...imageOptions,
        createdAt: new Date().toISOString(),
      })
      return
    }

    let result
    let transport = "images-generate"
    if (textGenerateViaResponses) {
      if (forceResponsesForSize && !useResponses) {
        appendDebugLine("非标准海报尺寸改走 Responses 图像工具，避免 Images API 静默降级尺寸", { size })
      }
      transport = "responses-image"
      result = await postJSON("api/responses-image", {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: confirmedPrompt,
        original_prompt: prompt,
        prompt_mode: promptPlan.promptMode,
        recipe_id: promptPlan.recipe?.id || "",
        recipe_version: promptPlan.recipe?.version || "",
        model: settings.responsesModel,
        mode: "generate",
        transport: "responses-image",
        allow_inline_fallback: true,
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        text_contract: textContract,
        sample_count: sampleCount,
        size,
        ...imageOptions,
      }, {
        mode: "generate",
        progressLabel: "提交 Responses 生成请求",
        waitingLabel: "等待 Responses 图像流",
      })
    } else {
      result = await postJSON("api/generate", {
        api_key: settings.apiKey,
        endpoint_url: settings.generateUrl,
        prompt: confirmedPrompt,
        original_prompt: prompt,
        prompt_mode: promptPlan.promptMode,
        recipe_id: promptPlan.recipe?.id || "",
        recipe_version: promptPlan.recipe?.version || "",
        model,
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        text_contract: textContract,
        sample_count: sampleCount,
        size,
        ...imageOptions,
      }, {
        mode: "generate",
        progressLabel: "提交生成请求",
        waitingLabel: "等待上游生成",
      })
    }
    await setResult({ ...result, logo_requested: logoRequested, text_contract: textContract }, performance.now() - startedAt)
    rememberRegenerationRequest("generate", requestSnapshot)
    pushHistory({
      mode: "generate",
      prompt,
      model: textGenerateViaResponses ? settings.responsesModel : model,
      transport,
      logoRequested,
      itineraryId,
      textContract,
      sampleCount,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("生成请求失败", { error: error.message })
    if (error.cancelled && restorePendingResultAfterCancellation()) {
      setStatusMessage("已中断生成，上一张结果已保留。")
    } else {
      setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
    }
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

async function submitEdit() {
  if (state.isBusy) {
    return
  }
  resetDebugLog("点击编辑按钮：编辑图片")
  let prompt = refs.editPromptInput.value
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = (refs.editModelInput.value.trim() || refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2")
  const logoRequested = shouldUseCompanyLogo()
  const itineraryId = getExplicitItineraryId()
  let confirmedPrompt = ""
  let size
  let imageOptions
  let forceResponsesForSize = false
  let model = imageModel
  let transport = "images-edit"

  if (!state.editImage) {
    appendDebugLine("参数校验失败：没有可编辑图片")
    setError("当前没有可编辑图片。先生成一张图，或手动上传一张图片。")
    return
  }

  if (!prompt.trim()) {
    appendDebugLine("参数校验失败：编辑指令为空")
    setError("编辑指令不能为空。")
    refs.editPromptInput.focus()
    return
  }

  try {
    size = getGenerateSize()
    imageOptions = getOpenAIImageOptions()
    forceResponsesForSize = shouldUseResponsesForSelectedSize(size)
    model = useResponses || forceResponsesForSize ? settings.responsesModel : imageModel
    transport = useResponses || forceResponsesForSize ? "responses-image" : "images-edit"
  } catch (error) {
    appendDebugLine("参数校验失败：编辑图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

  if (useResponses || forceResponsesForSize) {
    if (!requireResponsesSettings(settings, forceResponsesForSize ? "精确海报尺寸编辑" : "编辑图像")) {
      return
    }
  } else if (!requireEditSettings(settings, "编辑图像")) {
    return
  }

  const confirmedText = await confirmPromptBeforeRun("edit", prompt)
  if (confirmedText === null) {
    appendDebugLine("用户取消编辑提示词确认")
    return
  }
  prompt = confirmedText
  refs.editPromptInput.value = confirmedText
  updatePromptCounters()
  const textContract = buildVisibleTextContract(prompt)
  confirmedPrompt = withEditPreservePrompt(prompt, logoRequested)

  const requestSnapshot = currentFormSnapshot()
  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "编辑中", { progressLabel: "准备编辑图像" })

  const requestSource = cloneImageAsset(modelInputAssetForLogoWorkflow(state.editImage))
  previewPendingResult({
    mode: "edit",
    prompt,
    model,
    size,
    sourceName: requestSource.name || "输入图",
  })
  const startedAt = performance.now()

  try {
    appendDebugLine("读取编辑输入图片")
    setProgressPhase("preparing", "读取输入图")
    const requestSourceDataUrl = await ensureAssetDataUrl(requestSource)
    ensureRequestNotCancelled()
    const sourceGeneratedImageId = requestSource.generatedImageId || state.editImage?.generatedImageId || null
    const imagePart = {
      name: requestSource.name,
      type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
      data_url: requestSourceDataUrl,
      role: "source_image",
    }

    let maskPart = null
    if (state.editMaskImage) {
      appendDebugLine("读取编辑 mask")
      const maskDataUrl = await ensureAssetDataUrl(state.editMaskImage)
      ensureRequestNotCancelled()
      maskPart = {
        name: state.editMaskImage.name,
        type: state.editMaskImage.type || inferMimeFromDataUrl(maskDataUrl),
        data_url: maskDataUrl,
      }
    }

    let result
    if (useResponses || forceResponsesForSize) {
      if (forceResponsesForSize && !useResponses) {
        appendDebugLine("非标准海报尺寸编辑改走 Responses 图像工具，避免 Images API 静默降级尺寸", { size })
      }
      const requestPayload = {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: confirmedPrompt,
        model,
        mode: "edit",
        transport: "responses-image",
        allow_inline_fallback: true,
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        source_generated_image_id: sourceGeneratedImageId,
        text_contract: textContract,
        size,
        ...imageOptions,
        ...sourceImageIdentityFields(requestSource),
        image: imagePart,
        images: [imagePart],
      }
      if (maskPart) {
        requestPayload.mask = maskPart
      }
      result = await postJSON("api/responses-image", requestPayload, {
        mode: "edit",
        progressLabel: "提交 Responses 编辑请求",
        waitingLabel: "等待 Responses 图像流",
      })
    } else {
      const requestPayload = {
        api_key: settings.apiKey,
        endpoint_url: settings.editUrl,
        prompt: confirmedPrompt,
        model: imageModel,
        mode: "edit",
        logo_requested: logoRequested,
        itinerary_id: itineraryId,
        source_generated_image_id: sourceGeneratedImageId,
        text_contract: textContract,
        size,
        ...imageOptions,
        ...sourceImageIdentityFields(requestSource),
        image: imagePart,
        images: [imagePart],
      }
      if (maskPart) {
        requestPayload.mask = maskPart
      }
      result = await postJSON("api/edit", requestPayload, {
        mode: "edit",
        progressLabel: "提交编辑请求",
        waitingLabel: "等待上游编辑",
      })
    }
    await setResult({ ...result, mode: "edit", prompt, transport, logo_requested: logoRequested, size, text_contract: textContract }, performance.now() - startedAt, requestSource)
    rememberRegenerationRequest("edit", requestSnapshot)
    pushHistory({
      mode: "edit",
      prompt,
      model,
      transport,
      logoRequested,
      itineraryId,
      textContract,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("编辑请求失败", { error: error.message })
    if (error.cancelled && restorePendingResultAfterCancellation()) {
      setStatusMessage("已中断生成，上一张结果已保留。")
    } else {
      setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
    }
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

function clearGenerateForm() {
  refs.generatePromptInput.value = ""
  refs.generateModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  restoreCreativeBrief({})
  clearGenerateReferenceImage()
  setGenerateSize(state.serverConfig.default_size || "auto")
  refs.qualitySelect.value = "high"
  refs.backgroundSelect.value = "auto"
  refs.outputFormatSelect.value = "png"
  refs.outputCompressionInput.value = "100"
  refs.moderationSelect.value = "auto"
  refs.generateSampleCountInput.value = ""
  refs.logoOverlayEnabled.checked = true
  if (refs.itineraryIdEnabled) {
    refs.itineraryIdEnabled.checked = false
  }
  if (refs.itineraryIdInput) {
    refs.itineraryIdInput.value = ""
  }
  if (!state.lastResultImage) {
    state.generateIntent = "fresh"
  }
  updateLogoControlUI()
  updateItineraryIdControlUI()
  updateOpenAIOptionUI()
  updatePromptCounters()
  updateGenerateIntentUI()
  scheduleWorkspacePersist()
}

function clearEditForm() {
  refs.editPromptInput.value = ""
  refs.editModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  refs.editImageInput.value = ""
  clearEditMaskImage()
  updatePromptCounters()

  if (!useLastResultAsEditSource({ showPreview: true })) {
    state.editImage = null
    updateEditSourceUI()
    clearSourcePreview("输入图")
    scheduleWorkspacePersist()
  }
}

function continueEditingFromResult() {
  if (!state.lastResultImage) {
    setError("当前结果不能直接续改。请先完成一次返回 base64 图片结果的生成或编辑。")
    return
  }

  setMode("edit")
  useLastResultAsEditSource({ showPreview: true, focus: true })
}

function startVariantFromResult() {
  if (!state.lastResultImage) {
    setError("当前没有可延展的结果图。先生成第一张图，再基于它换风格。")
    return
  }

  setMode("generate")
  setGenerateIntent("variant")
  refs.generatePromptInput.focus()
  setError("")
}

async function handleClipboardPaste(event) {
  if (state.activeMode !== "edit") {
    return
  }

  const items = Array.from(event.clipboardData?.items || [])
  const imageItem = items.find((item) => item.type.startsWith("image/"))
  if (!imageItem) {
    return
  }

  const file = imageItem.getAsFile()
  if (!file) {
    return
  }

  event.preventDefault()
  try {
    await useImageFile(file)
    setError("")
  } catch (error) {
    setError(error.message, error.details)
  }
}

function bindPreviewTrigger(element, target) {
  element.addEventListener("click", () => openPreview(target, "single"))
  element.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      openPreview(target, "single")
    }
  })
}

function bindReferenceDropzone(dropzone, input, handler) {
  dropzone.addEventListener("click", () => input.click())
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      input.click()
    }
  })
  input.addEventListener("change", async (event) => {
    const file = event.target.files?.[0]
    // 清空 value：不清的话通过“继续编辑”或拖拽换图后，再点选同一个文件
    // 不会触发 change 事件，看起来像选择没生效。
    event.target.value = ""
    if (!file) {
      return
    }
    try {
      await handler(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })

  ;["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      dropzone.classList.add("dragging")
    })
  })

  ;["dragleave", "dragend", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      if (eventName !== "drop") {
        dropzone.classList.remove("dragging")
      }
    })
  })

  dropzone.addEventListener("drop", async (event) => {
    dropzone.classList.remove("dragging")
    const file = event.dataTransfer?.files?.[0]
    if (!file) {
      return
    }
    try {
      await handler(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })
}

function bindEvents() {
  refs.authForm?.addEventListener("submit", submitAuthForm)
  refs.loginAuthButton?.addEventListener("click", validateAuthFormInputs)
  refs.registerAuthButton?.addEventListener("click", () => {
    enterAuthGate(state.authMode === "register" ? "login" : "register")
  })
  refs.authCompanyInput?.addEventListener("change", () => {
    renderDepartmentSelect(refs.authDepartmentInput, state.orgUnits, refs.authCompanyInput?.value || "6renyou")
  })
  refs.forgotPasswordButton?.addEventListener("click", enterPasswordResetRequest)
  refs.passwordResetRequestForm?.addEventListener("submit", submitPasswordResetRequest)
  refs.cancelPasswordResetRequestButton?.addEventListener("click", leavePasswordResetRequest)
  refs.passwordResetConfirmForm?.addEventListener("submit", submitPasswordResetConfirm)
  refs.cancelPasswordResetConfirmButton?.addEventListener("click", () => enterAuthGate("login"))
  refs.logoutButton?.addEventListener("click", logout)
  refs.adminCreateUserForm?.addEventListener("submit", submitAdminCreateUser)
  refs.refreshAdminUsersButton?.addEventListener("click", refreshAdminUsers)
  refs.adminOrgCreateForm?.addEventListener("submit", submitAdminOrgUnit)
  refs.adminUserOrgForm?.addEventListener("submit", submitAdminUserOrg)
  refs.adminGroupAnnouncementForm?.addEventListener("submit", submitAdminGroupAnnouncement)
  refs.refreshAdminOrgButton?.addEventListener("click", refreshAdminOrgContext)
  refs.refreshFeedbackSummaryButton?.addEventListener("click", refreshFeedbackSummary)
  refs.refreshPasswordResetRequestsButton?.addEventListener("click", refreshPasswordResetRequests)
  refs.adminUsersList?.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null
    const button = target?.closest(".admin-delete-user-button")
    if (!button) {
      return
    }
    void deleteAdminUser(button.dataset.userId)
  })
  refs.passwordResetRequestsList?.addEventListener("submit", (event) => {
    event.preventDefault()
    const form = event.target instanceof HTMLFormElement ? event.target : null
    if (!form?.classList.contains("password-reset-admin-form")) {
      return
    }
    void submitPasswordResetAdminForm(form)
  })

  refs.newTaskButton.addEventListener("click", () => {
    clearResult()
    clearGenerateForm()
    clearEditForm()
    resetItineraryMapExample()
    setMode("generate", { autoLoadLatest: false })
    refs.generatePromptInput.focus()
    setError("")
  })
  refs.saveSettingsButton.addEventListener("click", saveSettings)
  refs.imageTransportInputs.forEach((input) => {
    input.addEventListener("change", () => {
      updateImageTransportUI()
      scheduleWorkspacePersist()
    })
  })
  refs.clearHistoryButton.addEventListener("click", () => {
    state.history = []
    saveJSON(historyStorageKey(), state.history)
    renderHistory()
  })

  refs.generateTab.addEventListener("click", () => setMode("generate"))
  refs.editTab.addEventListener("click", () => setMode("edit"))
  refs.itineraryTab?.addEventListener("click", () => setMode("itinerary"))
  refs.navModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setMode(button.dataset.mode || "generate")
      if (button.dataset.mode === "edit") {
        refs.editPromptInput.focus()
      } else if (button.dataset.mode === "itinerary") {
        refs.itineraryDescriptionInput?.focus()
      } else {
        refs.generatePromptInput.focus()
      }
    })
  })
  refs.freshGenerateMode.addEventListener("click", () => setGenerateIntent("fresh"))
  refs.variantGenerateMode.addEventListener("click", () => {
    if (!state.lastResultImage) {
      return
    }
    setGenerateIntent("variant")
  })
  refs.generateButton.addEventListener("click", submitGenerate)
  refs.editButton.addEventListener("click", submitEdit)
  refs.cancelRequestButton?.addEventListener("click", cancelActiveRequest)
  refs.clearGenerateButton.addEventListener("click", clearGenerateForm)
  refs.clearEditButton.addEventListener("click", clearEditForm)
  refs.continueEditButton.addEventListener("click", continueEditingFromResult)
  refs.startVariantButton.addEventListener("click", startVariantFromResult)
  refs.previewCompareButton.addEventListener("click", () => openPreview("result", "compare"))
  refs.showVersionsButton?.addEventListener("click", showImageVersions)
  refs.saveGroupAssetButton?.addEventListener("click", saveCurrentResultToGroupAssets)
  refs.hoverContinueEditButton?.addEventListener("click", continueEditingFromResult)
  refs.hoverVariantButton?.addEventListener("click", startVariantFromResult)
  refs.inspectLongImageButton?.addEventListener("click", () => openPreview("result", "cinema"))
  refs.hoverShareButton?.addEventListener("click", () => {
    if (selectedGeneratedImageId()) {
      showSharePanel()
      refs.shareRecipientSearchInput?.focus()
    }
  })
  refs.downloadOriginalButton?.addEventListener("click", () => {
    const href = refs.downloadOriginalButton.dataset.href || ""
    if (!href) {
      setStatusMessage("当前没有可下载的原始底图。")
      return
    }
    const link = document.createElement("a")
    link.href = href
    link.download = refs.downloadOriginalButton.dataset.filename || "picgen-original.png"
    document.body.append(link)
    link.click()
    link.remove()
  })
  refs.teamInspirationFeedButton?.addEventListener("click", openTeamInspirationFeed)
  refs.railToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      toggleRailSection(button.dataset.railToggle || "")
    })
  })
  refs.feedbackRatingButtons.forEach((button) => {
    button.addEventListener("click", () => {
      void submitResultFeedback(button.dataset.rating)
    })
  })
  refs.submitBadFeedbackButton?.addEventListener("click", submitBadFeedbackReason)
  refs.regenerateFromBadFeedbackButton?.addEventListener("click", regenerateFromBadFeedback)
  refs.submitShareResultButton?.addEventListener("click", submitShareResult)
  refs.shareRecipientSearchInput?.addEventListener("input", renderShareRecipientOptions)
  refs.refreshSharedResultsButton?.addEventListener("click", refreshSharedResults)
  refs.sharedResultsList?.addEventListener("click", (event) => {
    const button = event.target.closest(".shared-result-item")
    if (!button) {
      return
    }
    openSharedResult(button.dataset.shareId)
  })
  refs.refreshGalleryButton?.addEventListener("click", refreshGallery)
  refs.refreshJobsButton?.addEventListener("click", refreshGenerationJobs)
  refs.gallerySearchInput?.addEventListener("input", () => {
    window.clearTimeout(state.gallerySearchTimer)
    state.gallerySearchTimer = window.setTimeout(refreshGallery, 250)
  })
  refs.galleryFavoriteOnlyInput?.addEventListener("change", refreshGallery)
  refs.clearGalleryFiltersButton?.addEventListener("click", () => {
    if (refs.gallerySearchInput) {
      refs.gallerySearchInput.value = ""
    }
    if (refs.galleryFavoriteOnlyInput) {
      refs.galleryFavoriteOnlyInput.checked = false
    }
    state.gallerySearch = ""
    state.galleryFavoriteOnly = false
    void refreshGallery()
  })
  refs.saveGalleryMetaButton?.addEventListener("click", saveGalleryMeta)
  refs.changePasswordButton?.addEventListener("click", openChangePasswordModal)
  refs.closeChangePasswordButton?.addEventListener("click", closeChangePasswordModal)
  refs.changePasswordBackdrop?.addEventListener("click", closeChangePasswordModal)
  refs.changePasswordForm?.addEventListener("submit", submitChangePassword)
  refs.openProfileButton?.addEventListener("click", openProfileModal)
  refs.closeProfileButton?.addEventListener("click", closeProfileModal)
  refs.profileBackdrop?.addEventListener("click", closeProfileModal)
  refs.profileForm?.addEventListener("submit", submitProfile)
  refs.profileUsernameInput?.addEventListener("input", updateProfileUsernamePasswordHint)
  refs.profileCompanyInput?.addEventListener("change", () => {
    renderDepartmentSelect(refs.profileDepartmentInput, state.orgUnits, refs.profileCompanyInput?.value || "6renyou")
  })
  refs.profileAvatarInput?.addEventListener("change", uploadProfileAvatar)
  refs.teamChatButton?.addEventListener("click", openTeamChatModal)
  refs.closeTeamChatButton?.addEventListener("click", closeTeamChatModal)
  refs.teamChatBackdrop?.addEventListener("click", closeTeamChatModal)
  refs.teamChatTeamRoomButton?.addEventListener("click", () => {
    void switchTeamChatRoom({
      type: "team",
      recipientUserId: null,
      title: teamChatGroupDisplayTitle(),
      meta: teamChatGroupDisplayMeta(),
    })
  })
  refs.refreshTeamChatButton?.addEventListener("click", () => {
    void refreshTeamChatGroupContext()
    void refreshTeamChatMessages()
  })
  refs.teamChatGroupContextToggle?.addEventListener("click", () => {
    state.teamChatGroupContextExpanded = !state.teamChatGroupContextExpanded
    renderTeamChatGroupContextDisclosure()
  })
  refs.teamChatForm?.addEventListener("submit", submitTeamChatMessage)
  refs.clearTeamChatQuoteButton?.addEventListener("click", clearTeamChatQuote)
  refs.teamChatMessageInput?.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      refs.teamChatForm?.requestSubmit()
    }
  })
  refs.teamChatMessages?.addEventListener("click", (event) => {
    if (!event.target.closest(".team-chat-message-actions")) {
      closeTeamChatMessageMenu()
    }
  })
  refs.bugReportButton?.addEventListener("click", openBugReportModal)
  refs.closeBugReportButton?.addEventListener("click", closeBugReportModal)
  refs.bugReportBackdrop?.addEventListener("click", closeBugReportModal)
  refs.bugReportForm?.addEventListener("submit", submitBugReport)
  refs.refreshBugReportsButton?.addEventListener("click", refreshBugReports)
  refs.promptConfirmTextInput?.addEventListener("input", updatePromptConfirmButtonState)
  refs.promptConfirmCheckbox?.addEventListener("change", updatePromptConfirmButtonState)

  refs.copyPromptButton.addEventListener("click", async () => {
    if (!state.lastResultPrompt) {
      setError("当前没有可复制的提示词。")
      return
    }
    try {
      await navigator.clipboard.writeText(state.lastResultPrompt)
      setStatusMessage("已复制本次提示词。")
    } catch {
      setError("浏览器不允许复制到剪贴板。")
    }
  })

  refs.generateSizePreset.addEventListener("change", () => {
    if (refs.generateSizePreset.value !== "custom") {
      setGenerateSize(refs.generateSizePreset.value)
    } else {
      updateVisualSizePicker("custom")
    }
    scheduleWorkspacePersist()
  })

  refs.visualSizeInputs.forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.checked) {
        return
      }
      if (input.value === "custom") {
        refs.generateSizePreset.value = "custom"
        updateVisualSizePicker("custom")
      } else {
        setGenerateSize(input.value)
      }
      scheduleWorkspacePersist()
    })
  })

  ;[refs.generateWidthInput, refs.generateHeightInput].forEach((input) => {
    input.addEventListener("input", () => {
      syncSizePresetFromInputs()
      scheduleWorkspacePersist()
    })
  })

  ;[
    refs.generatePromptInput,
    refs.generateModelInput,
    refs.editPromptInput,
    refs.editModelInput,
    refs.responsesModelInput,
  ].forEach((input) => {
    input.addEventListener("input", () => {
      updatePromptCounters()
      updateEffectivePromptPreview()
      updateWorkflowStatus()
      updateGenerateIntentUI()
      updateOpenAIOptionUI()
      scheduleWorkspacePersist()
    })
  })

  ;[
    refs.qualitySelect,
    refs.backgroundSelect,
    refs.outputFormatSelect,
    refs.outputCompressionInput,
    refs.moderationSelect,
    refs.generateSampleCountInput,
  ].forEach((input) => {
    input.addEventListener("input", () => {
      updateOpenAIOptionUI()
      scheduleWorkspacePersist()
    })
    input.addEventListener("change", () => {
      updateOpenAIOptionUI()
      scheduleWorkspacePersist()
    })
  })

  ;[refs.generateUrlInput, refs.editUrlInput, refs.responsesUrlInput, refs.responsesModelInput, refs.apiKeyInput].forEach((input) => {
    input.addEventListener("input", updateWorkflowStatus)
  })

  ;[refs.logoOverlayEnabled].forEach((input) => {
    input.addEventListener("input", () => {
      updateLogoControlUI()
      scheduleWorkspacePersist()
    })
    input.addEventListener("change", () => {
      updateLogoControlUI()
      scheduleWorkspacePersist()
    })
  })

  ;[refs.itineraryIdEnabled, refs.itineraryIdInput].filter(Boolean).forEach((input) => {
    input.addEventListener("input", () => {
      updateItineraryIdControlUI()
      scheduleWorkspacePersist()
    })
    input.addEventListener("change", () => {
      updateItineraryIdControlUI()
      scheduleWorkspacePersist()
    })
  })

  refs.promptChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      appendPromptSnippet(chip.dataset.target || state.activeMode, chip.dataset.snippet || "")
    })
  })

  refs.applyCreativeBriefButton?.addEventListener("click", applyCreativeBriefToPrompt)
  refs.askBotCreativeBriefButton?.addEventListener("click", () => {
    void askBotWithCreativeBrief()
  })
  refs.promptModeInputs.forEach((input) => {
    input.addEventListener("change", () => {
      updatePromptModeUI()
      scheduleWorkspacePersist()
    })
  })
  refs.promptRecipeSelect?.addEventListener("change", () => {
    selectPromptRecipe(refs.promptRecipeSelect.value)
  })
  refs.applyPromptRecipeButton?.addEventListener("click", applyPromptRecipeToPrompt)
  creativeBriefFields().forEach(([, input]) => {
    input?.addEventListener("input", () => {
      updateEffectivePromptPreview()
      scheduleWorkspacePersist()
    })
  })
  ;[
    refs.itineraryTitleInput,
    refs.itinerarySubtitleInput,
    refs.itinerarySizeSelect,
    refs.itineraryThemeSelect,
    refs.itineraryDescriptionInput,
    refs.itineraryLogoEnabled,
  ].forEach((input) => {
    input?.addEventListener("input", scheduleWorkspacePersist)
    input?.addEventListener("change", scheduleWorkspacePersist)
  })
  refs.renderItineraryMapButton?.addEventListener("click", () => {
    void submitAIItineraryMap()
  })
  refs.clearItineraryMapButton?.addEventListener("click", resetItineraryMapExample)
  refs.copyItineraryTemplateButton?.addEventListener("click", () => {
    void copyDetailedItineraryTemplate()
  })
  refs.applyItineraryTemplateButton?.addEventListener("click", applyDetailedItineraryTemplate)

  refs.generatePromptInput.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      submitGenerate()
    }
  })

  bindReferenceDropzone(refs.styleReferenceDropzone, refs.styleReferenceInput, useStyleReferenceFile)
  bindReferenceDropzone(refs.materialReferenceDropzone, refs.materialReferenceInput, useMaterialReferenceFile)
  refs.clearGenerateReferenceButton.addEventListener("click", (event) => {
    event.stopPropagation()
    clearGenerateReferenceImage()
    setError("")
  })

  refs.editPromptInput.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      submitEdit()
    }
  })

  refs.imageDropzone.addEventListener("click", () => refs.editImageInput.click())
  refs.imageDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      refs.editImageInput.click()
    }
  })
  refs.editImageInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file) {
      return
    }
    try {
      await useImageFile(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })

  refs.maskDropzone.addEventListener("click", (event) => {
    if (event.target === refs.clearEditMaskButton) {
      return
    }
    refs.editMaskInput.click()
  })
  refs.maskDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      refs.editMaskInput.click()
    }
  })
  refs.editMaskInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file) {
      return
    }
    try {
      await useMaskFile(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })
  refs.clearEditMaskButton.addEventListener("click", (event) => {
    event.stopPropagation()
    clearEditMaskImage()
    setError("")
  })

  ;["dragenter", "dragover"].forEach((eventName) => {
    refs.maskDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      refs.maskDropzone.classList.add("dragging")
    })
  })

  ;["dragleave", "dragend", "drop"].forEach((eventName) => {
    refs.maskDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      if (eventName !== "drop") {
        refs.maskDropzone.classList.remove("dragging")
      }
    })
  })

  refs.maskDropzone.addEventListener("drop", async (event) => {
    refs.maskDropzone.classList.remove("dragging")
    const file = event.dataTransfer?.files?.[0]
    if (!file) {
      return
    }
    try {
      await useMaskFile(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })

  ;["dragenter", "dragover"].forEach((eventName) => {
    refs.imageDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      refs.imageDropzone.classList.add("dragging")
    })
  })

  ;["dragleave", "dragend", "drop"].forEach((eventName) => {
    refs.imageDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      if (eventName !== "drop") {
        refs.imageDropzone.classList.remove("dragging")
      }
    })
  })

  refs.imageDropzone.addEventListener("drop", async (event) => {
    refs.imageDropzone.classList.remove("dragging")
    const file = event.dataTransfer?.files?.[0]
    if (!file) {
      return
    }
    try {
      await useImageFile(file)
      setError("")
    } catch (error) {
      setError(error.message, error.details)
    }
  })

  bindPreviewTrigger(refs.sourcePreviewTrigger, "source")
  bindPreviewTrigger(refs.resultPreviewTrigger, "result")

  refs.previewSingleModeButton.addEventListener("click", () => {
    state.preview.mode = "single"
    renderPreviewModal()
  })
  refs.previewCompareModeButton.addEventListener("click", () => {
    if (!canComparePreviews()) {
      return
    }
    state.preview.mode = "compare"
    resetPreviewZoom()
    renderPreviewModal()
  })
  refs.previewZoomInButton?.addEventListener("click", () => changePreviewZoom(0.25))
  refs.previewZoomOutButton?.addEventListener("click", () => changePreviewZoom(-0.25))
  refs.previewZoomResetButton?.addEventListener("click", resetPreviewZoom)
  refs.previewSinglePane?.addEventListener("wheel", handlePreviewWheel, { passive: false })
  refs.previewSinglePane?.addEventListener("pointerdown", (event) => {
    startPreviewDrag(event)
    if (state.previewZoom.dragging) {
      refs.previewSinglePane.setPointerCapture(event.pointerId)
    }
  })
  refs.previewSinglePane?.addEventListener("pointermove", movePreviewDrag)
  refs.previewSinglePane?.addEventListener("pointerup", stopPreviewDrag)
  refs.previewSinglePane?.addEventListener("pointercancel", stopPreviewDrag)
  refs.previewSingleImage?.addEventListener("dragstart", (event) => event.preventDefault())
  refs.closePreviewButton.addEventListener("click", closePreview)
  refs.previewModalBackdrop.addEventListener("click", closePreview)
  refs.previewModal.addEventListener("click", (event) => {
    if (event.target === refs.previewModal) {
      closePreview()
    }
  })

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && refs.profileModal && !refs.profileModal.classList.contains("hidden")) {
      closeProfileModal()
      return
    }

    if (event.key === "Escape" && refs.teamChatModal && !refs.teamChatModal.classList.contains("hidden")) {
      if (state.teamChatOpenMenuId) {
        closeTeamChatMessageMenu()
        return
      }
      closeTeamChatModal()
      return
    }

    if (event.key === "Escape" && refs.changePasswordModal && !refs.changePasswordModal.classList.contains("hidden")) {
      closeChangePasswordModal()
      return
    }

    if (event.key === "Escape" && refs.bugReportModal && !refs.bugReportModal.classList.contains("hidden")) {
      closeBugReportModal()
      return
    }
    if (event.key === "Escape" && refs.promptConfirmModal && !refs.promptConfirmModal.classList.contains("hidden")) {
      refs.cancelPromptConfirmButton?.click()
      return
    }

    if (event.key === "Escape" && !refs.previewModal.classList.contains("hidden")) {
      closePreview()
      return
    }

    if (event.altKey && event.key === "1") {
      event.preventDefault()
      setMode("generate")
      refs.generatePromptInput.focus()
      return
    }

    if (event.altKey && event.key === "2") {
      event.preventDefault()
      setMode("edit")
      refs.editPromptInput.focus()
      return
    }

    if (event.altKey && event.key === "3") {
      event.preventDefault()
      setMode("itinerary")
      refs.itineraryDescriptionInput?.focus()
      return
    }

    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault()
      refs.newTaskButton.click()
      return
    }

    if (isTypingElement(document.activeElement)) {
      return
    }

    if (event.key === "/") {
      event.preventDefault()
      focusActivePrompt()
    }
  })

  window.addEventListener("paste", handleClipboardPaste)
  window.addEventListener("pagehide", () => {
    if (!state.persistenceReady) {
      return
    }
    saveWorkspaceSnapshot(createWorkspaceSnapshot()).catch((error) => {
      console.error("Persist workspace failed", error)
    })
  })
}

async function init() {
  clearResult()
  clearSourcePreview("原图")

  try {
    const response = await fetch("api/config", { cache: "no-store", headers: proxyTokenHeaders() })
    state.serverConfig = await response.json()
  } catch {
    refs.settingsHint.textContent = "无法读取服务端默认配置，但你仍然可以手动填写全部参数。"
    state.serverConfig = {
      default_model: "gpt-image-2",
      default_responses_model: "gpt-5.5",
      default_size: "1088x2240",
      generate_url: "",
      edit_url: "",
      responses_url: "",
      has_default_api_key: false,
    }
  }

  bindEvents()
  initializeRailDisclosure()
  await refreshOrgUnits()
  const resetToken = getPasswordResetTokenFromUrl()
  if (resetToken) {
    enterPasswordResetConfirm(resetToken)
    return
  }
  const authenticated = await checkAuthSession()
  if (!authenticated) {
    return
  }

  await startAuthenticatedApp()
}

async function startAuthenticatedApp() {
  // Fast path only when the SAME user is still active. A 401 sends the user to the
  // auth gate without resetting appReady, so without the id check a different user
  // logging in on a shared browser would inherit the previous user's API key,
  // history and workspace (the per-user loaders below would be skipped).
  if (state.appReady && state.lastReadyUserId === (state.currentUser?.id ?? null)) {
    await refreshUsageSummary()
    await refreshImageStats()
    await refreshGenerationJobs()
    startTeamChatPolling()
    await refreshTeamChatUnread()
    return
  }

  state.history = loadJSON(historyStorageKey(), [])
  loadTeamChatRecentDms()
  renderHistory()
  await loadUserPreferences()
  loadSettings()
  await loadPromptRecipes()
  updateLogoControlUI()
  updatePromptCounters()
  updatePromptModeUI()
  updateGenerateIntentUI()
  const restored = await restoreWorkspaceState()

  if (!restored) {
    updateEditSourceUI()
    updateEditMaskUI()
    updateGenerateIntentUI()
    updateOpenAIOptionUI()
    updatePreviewAvailability()
    setMode("generate", { autoLoadLatest: false })
  }

  state.persistenceReady = true
  state.appReady = true
  state.lastReadyUserId = state.currentUser?.id ?? null
  updateWorkflowStatus()
  startTeamChatPolling()
  await refreshTeamChatUnread()
  await refreshUsageSummary()
  await refreshImageStats()
  await refreshGenerationJobs()
  scheduleWorkspacePersist()
}

init()
