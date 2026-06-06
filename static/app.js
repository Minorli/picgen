const STORAGE_KEY = "picgen-console-settings-v2"
const LEGACY_STORAGE_KEY = "picgen-console-settings-v1"
const HISTORY_KEY = "picgen-console-history-v1"
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
  "LOGO 布局要求：请在画面左上角为 6 人游 LOGO 预留干净留白，避免人物、文字、建筑边缘、产品主体或高对比元素与 LOGO 位置发生重合。",
  "最终 LOGO 将使用官方透明 PNG 原样贴入，图标、字体、颜色和比例均不得改动。",
  "LOGO 位置附近保留干净留白，背景尽量简单，避免图片元素和 LOGO 少量重合。",
].join("\n")
const MAX_HISTORY_ITEMS = 12
const WORKSPACE_DB_NAME = "picgen-console-workspace"
const WORKSPACE_STORE_NAME = "snapshots"
const WORKSPACE_KEY = "current-workspace"
const WORKSPACE_VERSION = 1
const REQUEST_TIMEOUT_MS = 20 * 60 * 1000 + 30 * 1000
const DEPRECATED_RESPONSES_MODELS = new Set(["gpt-5.4"])
const DEPRECATED_RESPONSES_URLS = new Set(["https://api.openai.com/v1/responses"])
const STYLE_TRANSFER_SAMPLE_COUNT = 3

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
  appReady: false,
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
  userPreferences: null,
}

const refs = {
  authOverlay: document.querySelector("#authOverlay"),
  authForm: document.querySelector("#authForm"),
  authTitle: document.querySelector("#authTitle"),
  authSubtitle: document.querySelector("#authSubtitle"),
  authUsernameInput: document.querySelector("#authUsernameInput"),
  authPasswordInput: document.querySelector("#authPasswordInput"),
  authError: document.querySelector("#authError"),
  loginAuthButton: document.querySelector("#loginAuthButton"),
  registerAuthButton: document.querySelector("#registerAuthButton"),
  forgotPasswordButton: document.querySelector("#forgotPasswordButton"),
  passwordResetRequestForm: document.querySelector("#passwordResetRequestForm"),
  passwordResetUsernameInput: document.querySelector("#passwordResetUsernameInput"),
  passwordResetRequestStatus: document.querySelector("#passwordResetRequestStatus"),
  submitPasswordResetRequestButton: document.querySelector("#submitPasswordResetRequestButton"),
  cancelPasswordResetRequestButton: document.querySelector("#cancelPasswordResetRequestButton"),
  bugReportButton: document.querySelector("#bugReportButton"),
  logoutButton: document.querySelector("#logoutButton"),
  currentUsername: document.querySelector("#currentUsername"),
  userAvatar: document.querySelector("#userAvatar"),
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
  requestStatus: document.querySelector("#requestStatus"),
  requestBadge: document.querySelector("#requestBadge"),
  generateTab: document.querySelector("#generateTab"),
  editTab: document.querySelector("#editTab"),
  generatePanel: document.querySelector("#generatePanel"),
  editPanel: document.querySelector("#editPanel"),
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
  resultActions: document.querySelector("#resultActions"),
  resultCandidateStrip: document.querySelector("#resultCandidateStrip"),
  generationOverlay: document.querySelector("#generationOverlay"),
  generationOrbit: document.querySelector(".generation-orbit"),
  generationOverlayTitle: document.querySelector("#generationOverlayTitle"),
  generationOverlaySubtitle: document.querySelector("#generationOverlaySubtitle"),
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
  logoOverlayEnabled: document.querySelector("#logoOverlayEnabled"),
  logoComposeStatus: document.querySelector("#logoComposeStatus"),
  generateSampleCountHint: document.querySelector("#generateSampleCountHint"),
  downloadButton: document.querySelector("#downloadButton"),
  openResultPreviewButton: document.querySelector("#openResultPreviewButton"),
  continueEditButton: document.querySelector("#continueEditButton"),
  startVariantButton: document.querySelector("#startVariantButton"),
  previewCompareButton: document.querySelector("#previewCompareButton"),
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
  bugReportModal: document.querySelector("#bugReportModal"),
  bugReportBackdrop: document.querySelector("#bugReportBackdrop"),
  bugReportForm: document.querySelector("#bugReportForm"),
  bugReportTitleInput: document.querySelector("#bugReportTitleInput"),
  bugReportDescriptionInput: document.querySelector("#bugReportDescriptionInput"),
  bugReportContactInput: document.querySelector("#bugReportContactInput"),
  bugReportStatus: document.querySelector("#bugReportStatus"),
  submitBugReportButton: document.querySelector("#submitBugReportButton"),
  closeBugReportButton: document.querySelector("#closeBugReportButton"),
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

function workspaceStorageKey() {
  return scopedStorageKey(WORKSPACE_KEY)
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  })
  let data = {}
  try {
    data = await response.json()
  } catch {
    data = {}
  }
  return { response, data }
}

function enterAuthGate(mode = state.authMode || "login", message = "") {
  state.authMode = mode === "register" ? "register" : "login"
  document.body.classList.add("auth-gate")
  document.body.classList.remove("app-shell")
  refs.authOverlay?.setAttribute("aria-hidden", "false")
  refs.authForm?.classList.remove("hidden")
  refs.passwordResetRequestForm?.classList.add("hidden")
  if (refs.authTitle) {
    refs.authTitle.textContent = state.authMode === "register" ? "注册 PicGen" : "登录 PicGen"
  }
  if (refs.authSubtitle) {
    refs.authSubtitle.textContent = state.authMode === "register"
      ? "填写用户名和密码即可创建账号。之后用同一账号登录。"
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
  if (refs.authError) {
    refs.authError.textContent = message
  }
  if (refs.passwordResetRequestStatus) {
    refs.passwordResetRequestStatus.textContent = ""
    refs.passwordResetRequestStatus.classList.remove("is-error")
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
  refs.authForm?.classList.add("hidden")
  refs.passwordResetRequestForm?.classList.remove("hidden")
  if (refs.authTitle) {
    refs.authTitle.textContent = "找回密码"
  }
  if (refs.authSubtitle) {
    refs.authSubtitle.textContent = "提交申请后，请联系管理员为你重置密码。"
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

function setCurrentUser(user) {
  state.currentUser = user || null
  const username = state.currentUser?.username || "未登录"
  const roleLabel = state.currentUser?.is_admin || state.currentUser?.role === "admin" ? "管理员" : "用户"
  if (refs.currentUsername) {
    refs.currentUsername.textContent = state.currentUser ? `${username} · ${roleLabel}` : username
  }
  if (refs.userAvatar) {
    refs.userAvatar.textContent = state.currentUser?.username?.slice(0, 1).toUpperCase() || "?"
  }
  updateAdminPanelVisibility()
}

async function checkAuthSession({ showLogin = true } = {}) {
  if (state.serverConfig?.auth_enabled === false) {
    setCurrentUser(null)
    enterAppShell()
    return true
  }
  const { response, data } = await fetchJSON("/api/me", { cache: "no-store" })
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
  await refreshFeedbackSummary()
  await refreshBugReports()
  await refreshPasswordResetRequests()
  await refreshSharedResults()
  await refreshShareRecipients()
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
          <span>${roleLabel} · ${activeLabel}</span>
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
  meta.textContent = item.matched_user
    ? `待管理员重置${timeText}`
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

function serverShareableImageUrl(candidate = {}) {
  const candidates = [
    candidate.saved_image_url,
    state.lastResultImage?.savedUrl,
    state.lastResultImage?.fileUrl,
    state.resultPreview?.src,
  ]
  return candidates.find((value) => value && !String(value).startsWith("data:")) || ""
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
  refs.downloadButton.href = state.resultPreview.src
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.download = asset.name
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  refs.shareResultPanel?.classList.add("hidden")
  renderResultCandidates()
  updatePreviewAvailability()
  scheduleWorkspacePersist()
  document.querySelector("#resultPanel")?.scrollIntoView({ behavior: "smooth", block: "start" })
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

async function submitAuthForm(event) {
  event.preventDefault()
  const username = refs.authUsernameInput.value.trim()
  const password = refs.authPasswordInput.value
  const endpoint = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login"
  refs.authError.textContent = ""
  refs.loginAuthButton.disabled = true
  if (refs.registerAuthButton) {
    refs.registerAuthButton.disabled = true
  }
  try {
    const { response, data } = await fetchJSON(endpoint, {
      method: "POST",
      body: JSON.stringify({ username, password }),
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
      refs.passwordResetRequestStatus.textContent = data.message || "申请已提交，请联系管理员。"
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

async function logout() {
  try {
    await fetchJSON("/api/auth/logout", { method: "POST" })
  } finally {
    state.persistenceReady = false
    state.appReady = false
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
      editPrompt: refs.editPromptInput.value,
      editModel: refs.editModelInput.value,
      responsesModel: refs.responsesModelInput.value,
      imageTransport: getImageTransport(),
      logoOverlayEnabled: refs.logoOverlayEnabled.checked,
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
  state.generateIntent = snapshot.generateIntent === "variant" ? "variant" : "fresh"
  refs.generatePromptInput.value = forms.generatePrompt || ""
  refs.generateModelInput.value = forms.generateModel || state.serverConfig.default_model || "gpt-image-2"
  refs.generateWidthInput.value = forms.generateWidth || ""
  refs.generateHeightInput.value = forms.generateHeight || ""
  refs.generateSizePreset.value = forms.generateSizePreset || "custom"
  refs.qualitySelect.value = forms.quality || "auto"
  refs.backgroundSelect.value = forms.background || "auto"
  refs.outputFormatSelect.value = forms.outputFormat || "png"
  refs.outputCompressionInput.value = forms.outputCompression || "100"
  refs.moderationSelect.value = forms.moderation || "auto"
  refs.generateSampleCountInput.value = forms.generateSampleCount || ""
  syncSizePresetFromInputs()

  if (!refs.generateWidthInput.value || !refs.generateHeightInput.value) {
    setGenerateSize(state.serverConfig.default_size || "auto")
  }

  refs.editPromptInput.value = forms.editPrompt || ""
  refs.editModelInput.value = forms.editModel || state.serverConfig.default_model || "gpt-image-2"
  refs.responsesModelInput.value = normalizeResponsesModel(forms.responsesModel || refs.responsesModelInput.value)
  refs.logoOverlayEnabled.checked = forms.logoOverlayEnabled !== false
  updateLogoControlUI()
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

  if (state.resultPreview?.src) {
    refs.resultPreviewLabel.textContent = result.labelText || "输出"
    refs.resultImage.src = state.resultPreview.src
    refs.resultImage.classList.add("visible")
    refs.resultPreviewEmpty.classList.add("hidden")
    refs.resultPrompt.textContent = result.promptText || "结果已恢复"
    refs.resultMeta.textContent = result.metaText || ""
    refs.resultTiming.textContent = result.timingText || ""
    refs.resultStorage.textContent = result.storageText || ""
    refs.downloadButton.href = state.resultPreview.src
    refs.downloadButton.classList.remove("disabled-link")
    refs.downloadButton.setAttribute("aria-disabled", "false")
    refs.downloadButton.download = state.lastResultImage?.name || `picgen-${state.lastResultMode || "result"}-restored.png`
    renderResultCandidates()
    restoreCopyrightRiskPanel()
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

function cloneImageAsset(asset, overrides = {}) {
  if (!asset) {
    return null
  }
  return { ...asset, ...overrides }
}

function modelInputAssetForLogoWorkflow(asset, logoRequested) {
  if (!logoRequested || !asset?.logoOverlayApplied) {
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
    logoOverlayApplied: false,
    description: `未贴 LOGO 的生成主体图 · ${asset.name || "最新结果"}`,
  }
  return getAssetDisplaySrc(source) ? source : asset
}

function getAssetDisplaySrc(asset) {
  return asset?.savedUrl || asset?.dataUrl || asset?.fileUrl || asset?.src || ""
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
      : "开始生成"
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
  refs.comparisonGrid?.classList.toggle("single-result", !hasSource)
  refs.sourcePreviewCard?.classList.toggle("hidden", !hasSource)
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
      : "编辑、参考图、延展默认走 OpenAI Images API + gpt-image-2，更稳定也更便宜。"
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

function withLogoLayoutPrompt(prompt, logoRequested = shouldUseCompanyLogo()) {
  const basePrompt = String(prompt || "").trim()
  return logoRequested ? `${basePrompt}\n\n${COMPANY_LOGO_LAYOUT_PROMPT}` : basePrompt
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

function updateVisualSizePicker(value) {
  refs.visualSizeInputs.forEach((input) => {
    const selected = input.value === value
    input.checked = selected
    input.closest("label")?.classList.toggle("selected", selected)
  })
}

function getOpenAIImageOptions() {
  const outputFormat = refs.outputFormatSelect.value || "png"
  const outputCompression = Number.parseInt(refs.outputCompressionInput.value, 10)

  if (!Number.isInteger(outputCompression) || outputCompression < 0 || outputCompression > 100) {
    throw new Error("输出压缩质量必须在 0 到 100 之间。")
  }

  const options = {
    quality: refs.qualitySelect.value || "auto",
    background: refs.backgroundSelect.value || "auto",
    output_format: outputFormat,
    moderation: refs.moderationSelect.value || "auto",
  }

  if (["jpeg", "webp"].includes(outputFormat)) {
    options.output_compression = outputCompression
  }

  return options
}

function currentFormSnapshot() {
  return {
    activeMode: state.activeMode,
    generateIntent: state.generateIntent,
    imageTransport: getImageTransport(),
    generatePrompt: refs.generatePromptInput.value,
    generateModel: refs.generateModelInput.value,
    generateSize: getSizeSnapshotValue(),
    quality: refs.qualitySelect.value,
    background: refs.backgroundSelect.value,
    outputFormat: refs.outputFormatSelect.value,
    outputCompression: refs.outputCompressionInput.value,
    moderation: refs.moderationSelect.value,
    generateSampleCount: refs.generateSampleCountInput.value,
    logoOverlayEnabled: refs.logoOverlayEnabled.checked,
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
  refs.generatePromptInput.value = snapshot.generatePrompt || ""
  refs.generateModelInput.value = snapshot.generateModel || state.serverConfig?.default_model || "gpt-image-2"
  setGenerateSize(snapshot.generateSize || "auto")
  refs.qualitySelect.value = snapshot.quality || "auto"
  refs.backgroundSelect.value = snapshot.background || "auto"
  refs.outputFormatSelect.value = snapshot.outputFormat || "png"
  refs.outputCompressionInput.value = snapshot.outputCompression || "100"
  refs.moderationSelect.value = snapshot.moderation || "auto"
  refs.generateSampleCountInput.value = snapshot.generateSampleCount || ""
  refs.logoOverlayEnabled.checked = snapshot.logoOverlayEnabled !== false
  refs.editPromptInput.value = snapshot.editPrompt || ""
  refs.editModelInput.value = snapshot.editModel || state.serverConfig?.default_model || "gpt-image-2"
  setGenerateIntent(snapshot.generateIntent || "fresh")
  setMode(snapshot.activeMode || "generate", { autoLoadLatest: false })
  updateLogoControlUI()
  updatePromptCounters()
}

function rememberRegenerationRequest(kind, snapshot) {
  state.lastRegenerationRequest = {
    kind,
    snapshot: { ...snapshot },
  }
}

async function rerunLastGeneration() {
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
    return "上游正在生成图像，较大尺寸通常需要更久。"
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
  refs.generationOverlayTitle.textContent = state.progressLabel || "处理中"
  refs.generationOverlaySubtitle.textContent = hint
  refs.generationOrbit?.style.setProperty("--progress-degrees", `${(progress * 3.6).toFixed(1)}deg`)
  refs.generationOrbit?.setAttribute("data-progress", `${Math.round(progress)}%`)
}

function setProgressPhase(phase, label) {
  if (!state.isBusy) {
    return
  }
  state.progressPhase = phase
  state.progressLabel = label
  refs.generationOverlayTitle.textContent = label
  refs.generationOverlaySubtitle.textContent = progressHintForPhase(phase, label)
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
  refs.generationOverlayTitle.textContent = label
  refs.generationOverlaySubtitle.textContent = progressHintForPhase("preparing", label)
  state.progressTimer = window.setInterval(renderProgress, 100)
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

function restoreCopyrightRiskPanel() {
  const risk = state.copyrightRisk || {}
  setRiskPanel(
    risk.status || "等待检查",
    risk.text || "生成完成后自动检查。",
    { hidden: risk.hidden !== false },
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

  const usesBaseImage = shouldUseCompanyLogo() && Boolean(state.lastResultImage.logoOverlayApplied)
  const inputAsset = modelInputAssetForLogoWorkflow(state.lastResultImage, usesBaseImage)
  const asset = cloneImageAsset(inputAsset, {
    origin: "result",
    description: usesBaseImage
      ? `自动使用未贴 LOGO 的主体图 · ${inputAsset.name}`
      : `自动使用最新结果 · ${inputAsset.name}`,
  })
  setEditImage(asset, { showPreview, previewLabel: "输入图" })

  if (!refs.editModelInput.value.trim() && state.lastResultModel) {
    refs.editModelInput.value = state.lastResultModel
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
  refs.navModeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode)
  })
  refs.generatePanel.classList.toggle("hidden", mode !== "generate")
  refs.editPanel.classList.toggle("hidden", mode !== "edit")
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
  refs.openResultPreviewButton.disabled = !hasResult
  refs.continueEditButton.disabled = !state.lastResultImage
  refs.startVariantButton.disabled = !state.lastResultImage
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
    refs.previewModalTitle.textContent = `${singleItem.label}预览`
    refs.previewModalMeta.textContent = singleItem.meta
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
  renderPreviewModal()
  refs.previewModal.classList.remove("hidden")
  refs.previewModal.setAttribute("aria-hidden", "false")
  document.body.classList.add("modal-open")
}

function clearResult() {
  refs.resultPreviewLabel.textContent = "输出"
  refs.resultImage.removeAttribute("src")
  refs.resultImage.classList.remove("visible")
  refs.resultPreviewEmpty.classList.remove("hidden")
  refs.resultPreviewEmpty.textContent = "生成或编辑成功后，这里会显示输出结果。"
  refs.resultPrompt.textContent = "还没有结果。"
  refs.resultMeta.textContent = ""
  refs.resultTiming.textContent = ""
  refs.resultStorage.textContent = ""
  refs.logoComposeStatus.textContent = refs.logoOverlayEnabled?.checked ? "本地贴图" : "未启用"
  refs.rawResponseOutput.textContent = "{}"
  refs.debugOutput.textContent = "等待操作。"
  setRiskPanel("等待检查", "生成完成后自动检查。", { hidden: true })
  refs.downloadButton.classList.add("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "true")
  refs.downloadButton.removeAttribute("href")
  refs.openResultPreviewButton.disabled = true
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
  state.resultCandidates = []
  state.selectedCandidateIndex = 0
  state.rawResponsePreview = null
  state.lastFeedbackPayload = null
  state.lastFeedbackRating = null
  state.debugLines = []
  state.generateIntent = "fresh"

  closePreview()
  renderRawResponsePreview()
  renderResultCandidates()
  updateGenerateIntentUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function previewPendingResult({ mode, prompt, model, size, sourceName = "" }) {
  const label = mode === "variant"
    ? "延展中"
    : mode === "edit"
      ? "编辑中"
      : mode === "reference"
        ? "参考生成中"
        : "生成中"
  const metaLabel = mode === "variant" ? "延展" : mode === "edit" ? "编辑" : mode === "reference" ? "参考生成" : "生成"
  const metaParts = [metaLabel, model]

  if (size) {
    metaParts.push(size)
  }
  if (sourceName) {
    metaParts.push(`参考图 ${sourceName}`)
  }

  refs.resultPreviewLabel.textContent = label
  refs.resultImage.removeAttribute("src")
  refs.resultImage.classList.remove("visible")
  refs.resultPreviewEmpty.classList.remove("hidden")
  refs.resultPreviewEmpty.textContent = "请求已提交，正在等待上游返回新图。"
  refs.resultPrompt.textContent = prompt || "本次请求已提交。"
  refs.resultMeta.textContent = metaParts.filter(Boolean).join(" · ")
  refs.resultTiming.textContent = "请求进行中 0.0s"
  refs.resultStorage.textContent = ""
  refs.downloadButton.classList.add("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "true")
  refs.downloadButton.removeAttribute("href")
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
  return {
    name: candidate.saved_image_name || `picgen-${payload.mode}-${index + 1}-${Date.now()}.png`,
    type: candidate.saved_image_mime || (candidate.image_data_url ? inferMimeFromDataUrl(candidate.image_data_url) : ""),
    dataUrl: candidate.image_data_url || "",
    savedUrl: candidate.saved_image_url || "",
    savedPath: candidate.saved_image_path || "",
    generatedImageId: candidate.generated_image_id || null,
    metadataPath: candidate.saved_metadata_path || "",
    fileUrl: candidate.saved_image_url || candidate.image_url || "",
    origin: "result",
    description: `候选 ${index + 1} · ${payload.model || ""}`,
    src: imageSource,
  }
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
  refs.downloadButton.href = candidate.saved_image_url || imageSource
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.download = candidate.saved_image_name || `picgen-${state.lastResultMode || "result"}-${index + 1}.png`
  refs.feedbackReasonPanel?.classList.add("hidden")
  if (refs.feedbackReasonInput) {
    refs.feedbackReasonInput.value = ""
  }
  updateFeedbackSelection(null)
  setFeedbackStatus("等待评价")
  renderResultCandidates()
  updateFeedbackPanelVisibility()
  updatePreviewAvailability()
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
  refs.downloadButton.href = firstCandidate.saved_image_url || imageSource
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.download = firstCandidate.saved_image_name || `picgen-${payload.mode}-${Date.now()}.png`
}

async function composeLogoOverlayAfterDisplay(payload, durationMs) {
  try {
    const composedCandidates = await composeLogoOverlayForCandidates(state.resultCandidates, true)
    if (!composedCandidates.length || state.activeRequestController) {
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
    refs.logoComposeStatus.textContent = selectedCandidate.logo_final_persisted ? "成品已保存" : "本地已贴图"
    scheduleWorkspacePersist()
  } catch (error) {
    appendDebugLine("本地 LOGO 合成失败", { error: error.message })
    refs.logoComposeStatus.textContent = "贴图失败，可先下载原图"
  }
}

async function setResult(payload, durationMs, requestSource = null) {
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

  state.resultCandidates = enrichedCandidates
  state.selectedCandidateIndex = 0
  const isTransformMode = ["edit", "variant", "reference"].includes(payload.mode)
  refs.resultPreviewLabel.textContent = payload.mode === "variant"
    ? "延展后"
    : payload.mode === "edit"
      ? "编辑后"
      : payload.mode === "reference"
        ? "参考生成"
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
      state.editImage = cloneImageAsset(state.lastResultImage, {
        origin: "result",
        description: `下一次编辑将默认使用最新输出 · ${state.lastResultImage.name}`,
      })
    }
  } else {
    state.currentComparisonSource = null
    if (state.activeMode !== "edit") {
      clearSourcePreview("原图")
    }

    if (payload.mode === "generate" && state.lastResultImage) {
      state.editImage = cloneImageAsset(state.lastResultImage, {
        origin: "result",
        description: `自动使用最新结果 · ${state.lastResultImage.name}`,
      })
    }
  }

  const metaLabel = payload.mode === "variant" ? "延展" : payload.mode === "edit" ? "编辑" : payload.mode === "reference" ? "参考生成" : "生成"
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
  if (payload.size && actualSize && !isSameSize(payload.size, actualSize)) {
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
    void composeLogoOverlayAfterDisplay(payload, durationMs)
  }
  void checkCopyrightRisk(payload)
  void refreshUsageSummary()

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
    mode.textContent = item.mode === "variant" ? "延展" : item.mode === "edit" ? "编辑" : item.mode === "reference" ? "参考生成" : "生成"

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
      if (item.mode === "generate" || item.mode === "variant" || item.mode === "reference") {
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

  let response
  try {
    appendDebugLine("fetch 已发出，等待本地服务响应", { requestId })
    setProgressPhase("waiting", options.waitingLabel || "等待上游生成")
    response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
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
    if (error.name === "AbortError") {
      const requestError = new Error(state.activeRequestCancelled
        ? "用户已中断当前生成。"
        : "请求等待超时。请查看本地服务终端日志，确认后端是否卡在上游接口。")
      requestError.cancelled = state.activeRequestCancelled
      throw requestError
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
    window.clearTimeout(waitingNoticeId)
    if (state.activeRequestController === controller) {
      state.activeRequestController = null
    }
  }

  appendDebugLine("本地服务已返回响应头", {
    requestId,
    status: response.status,
    ok: response.ok,
    elapsedMs: Math.round(performance.now() - startedAt),
  })
  setProgressPhase("receiving", "处理上游响应")

  let data
  try {
    data = await response.json()
  } catch {
    appendDebugLine("响应体不是有效 JSON", { requestId })
    throw new Error("本地服务返回了无法解析的响应。")
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
    if (response.status === 401) {
      enterAuthGate("login", "登录已过期，请重新登录。")
    }
    const requestError = new Error(data.error || "请求失败")
    requestError.details = data.details || ""
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
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    const data = await response.json()
    if (!response.ok) {
      if (response.status === 401) {
        enterAuthGate("login", "登录已过期，请重新登录。")
      }
      const requestError = new Error(data.error || "请求失败")
      requestError.details = data.details || ""
      throw requestError
    }
    return data
  } finally {
    window.clearTimeout(timeoutId)
  }
}

async function checkCopyrightRisk(payload) {
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
    } catch (error) {
      appendDebugLine("版权检查取图失败", { error: error.message })
    }
  }
  const reviewDataUrl = await downscaleDataUrlForRisk(sourceDataUrl)
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
    setRiskPanel("已检查", result.risk_text || "未见明显风险，但商用前仍建议确认素材授权链。")
  } catch (error) {
    appendDebugLine("版权风险检查失败", { error: error.message })
    setRiskPanel("检查失败", error.message || "版权风险检查失败，不影响图片生成结果。")
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

async function useImageFile(file) {
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }

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
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }

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
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }

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
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }

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
  if (!file || !file.type.startsWith("image/")) {
    throw new Error("请选择图片文件。")
  }

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
  const prompt = refs.generatePromptInput.value
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2"
  const model = useResponses ? settings.responsesModel : imageModel
  const transport = useResponses ? "responses-image" : "images-edit"
  const logoRequested = shouldUseCompanyLogo()
  const requestPrompt = withLogoLayoutPrompt(prompt, logoRequested)
  let imageOptions
  let size

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

  if (useResponses) {
    if (!requireResponsesSettings(settings, "基于当前结果延展")) {
      return
    }
  } else if (!requireEditSettings(settings, "基于当前结果延展")) {
    return
  }

  try {
    imageOptions = getOpenAIImageOptions()
    size = getGenerateSize()
  } catch (error) {
    appendDebugLine("参数校验失败：OpenAI 图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

  const requestSnapshot = currentFormSnapshot()
  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "延展中", { progressLabel: "准备延展图像" })

  const requestSource = cloneImageAsset(modelInputAssetForLogoWorkflow(state.lastResultImage, logoRequested))
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
    const imagePart = {
      name: requestSource.name,
      type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
      data_url: requestSourceDataUrl,
      role: "source_image",
    }
    let result
    if (useResponses) {
      result = await postJSON("api/responses-image", {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: requestPrompt,
        model,
        mode: "variant",
        transport: "responses-image",
        allow_inline_fallback: true,
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
        prompt: requestPrompt,
        model,
        mode: "variant",
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
    await setResult({ ...result, mode: "variant", prompt, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSource)
    rememberRegenerationRequest("generate", requestSnapshot)
    pushHistory({
      mode: "variant",
      prompt,
      model,
      transport,
      logoRequested,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("延展请求失败", { error: error.message })
    setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

async function submitGenerate() {
  if (state.generateIntent === "variant") {
    resetDebugLog("点击生成按钮：基于当前结果延展")
    appendDebugLine("当前生成方式为延展，转入编辑接口")
    await submitVariantGenerate({ resetLog: false })
    return
  }

  resetDebugLog("点击生成按钮：生成图片")

  const prompt = refs.generatePromptInput.value
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2"
  const referenceImages = generateReferenceImages()
  const dualReference = hasStyleTransferReferences()
  const logoRequested = shouldUseCompanyLogo()
  const model = referenceImages.length && useResponses ? settings.responsesModel : imageModel
  const baseRequestPrompt = dualReference ? styleTransferPrompt(prompt) : prompt
  const requestPrompt = withLogoLayoutPrompt(baseRequestPrompt, logoRequested)
  const requiresReferenceTransport = referenceImages.length > 0

  if (!prompt.trim()) {
    appendDebugLine("参数校验失败：生成提示词为空")
    setError("生成提示词不能为空。")
    refs.generatePromptInput.focus()
    return
  }

  if (!requiresReferenceTransport && !settings.generateUrl) {
    appendDebugLine("参数校验失败：生成接口 URL 为空")
    setError("请先填写生成接口 URL。")
    refs.generateUrlInput.focus()
    return
  }

  if (requiresReferenceTransport) {
    if (useResponses) {
      if (!requireResponsesSettings(settings, "带参考图生成")) {
        return
      }
    } else if (!requireEditSettings(settings, "带参考图生成")) {
      return
    }
  }

  let size
  let imageOptions
  let sampleCount
  try {
    size = getGenerateSize()
    imageOptions = getOpenAIImageOptions()
    sampleCount = referenceImages.length ? 1 : getGenerateSampleCount()
  } catch (error) {
    appendDebugLine("参数校验失败：OpenAI 图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

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
      const transport = useResponses ? "responses-image" : "images-edit"
      const referenceSampleCount = dualReference ? STYLE_TRANSFER_SAMPLE_COUNT : sampleCount
      let result
      if (useResponses) {
        result = await postJSON("api/responses-image", {
          api_key: settings.apiKey,
          endpoint_url: settings.responsesUrl,
          prompt: requestPrompt,
          model: settings.responsesModel,
          mode: "reference",
          transport: "responses-image",
          allow_inline_fallback: true,
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
          prompt: requestPrompt,
          model: imageModel,
          mode: "reference",
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
      await setResult({ ...result, mode: "reference", prompt, size, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSources.at(-1))
      rememberRegenerationRequest("generate", requestSnapshot)
      pushHistory({
        mode: "reference",
        prompt,
        model: useResponses ? settings.responsesModel : imageModel,
        transport,
        logoRequested,
        size,
        sampleCount: referenceSampleCount,
        ...imageOptions,
        createdAt: new Date().toISOString(),
      })
      return
    }

    const result = await postJSON("api/generate", {
      api_key: settings.apiKey,
      endpoint_url: settings.generateUrl,
      prompt: requestPrompt,
      model,
      sample_count: sampleCount,
      size,
      ...imageOptions,
    }, {
      mode: "generate",
      progressLabel: "提交生成请求",
      waitingLabel: "等待上游生成",
    })
    await setResult({ ...result, logo_requested: logoRequested }, performance.now() - startedAt)
    rememberRegenerationRequest("generate", requestSnapshot)
    pushHistory({
      mode: "generate",
      prompt,
      model,
      logoRequested,
      sampleCount,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("生成请求失败", { error: error.message })
    setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

async function submitEdit() {
  resetDebugLog("点击编辑按钮：编辑图片")
  const prompt = refs.editPromptInput.value
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = (refs.editModelInput.value.trim() || refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2")
  const model = useResponses ? settings.responsesModel : imageModel
  const transport = useResponses ? "responses-image" : "images-edit"
  const logoRequested = shouldUseCompanyLogo()
  const requestPrompt = withLogoLayoutPrompt(prompt, logoRequested)

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

  if (useResponses) {
    if (!requireResponsesSettings(settings, "编辑图像")) {
      return
    }
  } else if (!requireEditSettings(settings, "编辑图像")) {
    return
  }

  const requestSnapshot = currentFormSnapshot()
  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "编辑中", { progressLabel: "准备编辑图像" })

  const requestSource = cloneImageAsset(modelInputAssetForLogoWorkflow(state.editImage, logoRequested))
  previewPendingResult({
    mode: "edit",
    prompt,
    model,
    sourceName: requestSource.name || "输入图",
  })
  const startedAt = performance.now()

  try {
    appendDebugLine("读取编辑输入图片")
    setProgressPhase("preparing", "读取输入图")
    const requestSourceDataUrl = await ensureAssetDataUrl(requestSource)
    ensureRequestNotCancelled()
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
    if (useResponses) {
      const requestPayload = {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: requestPrompt,
        model,
        mode: "edit",
        transport: "responses-image",
        allow_inline_fallback: true,
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
        prompt: requestPrompt,
        model: imageModel,
        mode: "edit",
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
    await setResult({ ...result, mode: "edit", prompt, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSource)
    rememberRegenerationRequest("edit", requestSnapshot)
    pushHistory({
      mode: "edit",
      prompt,
      model,
      transport,
      logoRequested,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("编辑请求失败", { error: error.message })
    setError(error.cancelled ? "已中断生成，可以修改提示词后重新提交。" : error.message, error.details)
  } finally {
    setBusy(false, "空闲", { cancelled: state.activeRequestCancelled })
    state.activeRequestCancelled = false
  }
}

function clearGenerateForm() {
  refs.generatePromptInput.value = ""
  refs.generateModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  clearGenerateReferenceImage()
  setGenerateSize(state.serverConfig.default_size || "auto")
  refs.qualitySelect.value = "auto"
  refs.backgroundSelect.value = "auto"
  refs.outputFormatSelect.value = "png"
  refs.outputCompressionInput.value = "100"
  refs.moderationSelect.value = "auto"
  refs.generateSampleCountInput.value = ""
  refs.logoOverlayEnabled.checked = true
  if (!state.lastResultImage) {
    state.generateIntent = "fresh"
  }
  updateLogoControlUI()
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
  refs.registerAuthButton?.addEventListener("click", () => {
    enterAuthGate(state.authMode === "register" ? "login" : "register")
  })
  refs.forgotPasswordButton?.addEventListener("click", enterPasswordResetRequest)
  refs.passwordResetRequestForm?.addEventListener("submit", submitPasswordResetRequest)
  refs.cancelPasswordResetRequestButton?.addEventListener("click", leavePasswordResetRequest)
  refs.logoutButton?.addEventListener("click", logout)
  refs.adminCreateUserForm?.addEventListener("submit", submitAdminCreateUser)
  refs.refreshAdminUsersButton?.addEventListener("click", refreshAdminUsers)
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
  refs.navModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setMode(button.dataset.mode || "generate")
      if (button.dataset.mode === "edit") {
        refs.editPromptInput.focus()
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
  refs.openResultPreviewButton.addEventListener("click", () => openPreview("result", "single"))
  refs.previewCompareButton.addEventListener("click", () => openPreview("result", "compare"))
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
  refs.bugReportButton?.addEventListener("click", openBugReportModal)
  refs.closeBugReportButton?.addEventListener("click", closeBugReportModal)
  refs.bugReportBackdrop?.addEventListener("click", closeBugReportModal)
  refs.bugReportForm?.addEventListener("submit", submitBugReport)
  refs.refreshBugReportsButton?.addEventListener("click", refreshBugReports)

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

  refs.promptChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      appendPromptSnippet(chip.dataset.target || state.activeMode, chip.dataset.snippet || "")
    })
  })

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
    if (event.key === "Escape" && refs.bugReportModal && !refs.bugReportModal.classList.contains("hidden")) {
      closeBugReportModal()
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
    const response = await fetch("api/config", { cache: "no-store" })
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
  const authenticated = await checkAuthSession()
  if (!authenticated) {
    return
  }

  await startAuthenticatedApp()
}

async function startAuthenticatedApp() {
  if (state.appReady) {
    await refreshUsageSummary()
    return
  }

  state.history = loadJSON(historyStorageKey(), [])
  renderHistory()
  await loadUserPreferences()
  loadSettings()
  updateLogoControlUI()
  updatePromptCounters()
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
  updateWorkflowStatus()
  await refreshUsageSummary()
  scheduleWorkspacePersist()
}

init()
