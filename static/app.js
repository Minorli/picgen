const STORAGE_KEY = "picgen-console-settings-v1"
const HISTORY_KEY = "picgen-console-history-v1"
const MAX_HISTORY_ITEMS = 12
const WORKSPACE_DB_NAME = "picgen-console-workspace"
const WORKSPACE_STORE_NAME = "snapshots"
const WORKSPACE_KEY = "current-workspace"
const WORKSPACE_VERSION = 1

const SIZE_PRESETS = [
  "128x128",
  "256x256",
  "512x512",
  "768x768",
  "1024x1024",
  "1536x1024",
  "1024x1536",
  "2048x2048",
  "3840x2160",
  "2160x3840",
  "4096x4096",
]

const state = {
  activeMode: "generate",
  generateIntent: "fresh",
  serverConfig: null,
  editImage: null,
  generateReferenceImage: null,
  displayedSourceImage: null,
  history: [],
  lastResultPrompt: "",
  lastResultImage: null,
  lastResultModel: "",
  lastResultMode: null,
  currentComparisonSource: null,
  resultPreview: null,
  progressTimer: null,
  progressStartedAt: 0,
  progressPhase: "idle",
  progressLabel: "",
  preview: {
    mode: "single",
    target: "result",
  },
  rawResponsePreview: null,
  debugLines: [],
  persistTimer: null,
  persistenceReady: false,
  isBusy: false,
}

const refs = {
  apiKeyInput: document.querySelector("#apiKeyInput"),
  generateUrlInput: document.querySelector("#generateUrlInput"),
  editUrlInput: document.querySelector("#editUrlInput"),
  settingsHint: document.querySelector("#settingsHint"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  toggleKeyButton: document.querySelector("#toggleKeyButton"),
  clearHistoryButton: document.querySelector("#clearHistoryButton"),
  historyList: document.querySelector("#historyList"),
  historyEmpty: document.querySelector("#historyEmpty"),
  requestStatus: document.querySelector("#requestStatus"),
  requestBadge: document.querySelector("#requestBadge"),
  flowConnect: document.querySelector("#flowConnect"),
  flowGenerate: document.querySelector("#flowGenerate"),
  flowEdit: document.querySelector("#flowEdit"),
  flowCompare: document.querySelector("#flowCompare"),
  flowExport: document.querySelector("#flowExport"),
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
  generateReferenceDropzone: document.querySelector("#generateReferenceDropzone"),
  generateReferenceInput: document.querySelector("#generateReferenceInput"),
  generateReferenceTitle: document.querySelector("#generateReferenceTitle"),
  generateReferenceMeta: document.querySelector("#generateReferenceMeta"),
  clearGenerateReferenceButton: document.querySelector("#clearGenerateReferenceButton"),
  generatePromptInput: document.querySelector("#generatePromptInput"),
  generatePromptCount: document.querySelector("#generatePromptCount"),
  generateModelInput: document.querySelector("#generateModelInput"),
  generateSizePreset: document.querySelector("#generateSizePreset"),
  generateWidthInput: document.querySelector("#generateWidthInput"),
  generateHeightInput: document.querySelector("#generateHeightInput"),
  clearGenerateButton: document.querySelector("#clearGenerateButton"),
  generateButton: document.querySelector("#generateButton"),
  imageDropzone: document.querySelector("#imageDropzone"),
  imageDropzoneTitle: document.querySelector("#imageDropzoneTitle"),
  imageDropzoneSubtitle: document.querySelector("#imageDropzoneSubtitle"),
  editImageInput: document.querySelector("#editImageInput"),
  editImageMeta: document.querySelector("#editImageMeta"),
  editPromptInput: document.querySelector("#editPromptInput"),
  editPromptCount: document.querySelector("#editPromptCount"),
  editModelInput: document.querySelector("#editModelInput"),
  clearEditButton: document.querySelector("#clearEditButton"),
  editButton: document.querySelector("#editButton"),
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
  generationOverlay: document.querySelector("#generationOverlay"),
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
  downloadButton: document.querySelector("#downloadButton"),
  continueEditButton: document.querySelector("#continueEditButton"),
  startVariantButton: document.querySelector("#startVariantButton"),
  previewCompareButton: document.querySelector("#previewCompareButton"),
  copyPromptButton: document.querySelector("#copyPromptButton"),
  errorMessage: document.querySelector("#errorMessage"),
  debugOutput: document.querySelector("#debugOutput"),
  rawResponseOutput: document.querySelector("#rawResponseOutput"),
  previewModal: document.querySelector("#previewModal"),
  previewModalBackdrop: document.querySelector("#previewModalBackdrop"),
  previewModalTitle: document.querySelector("#previewModalTitle"),
  previewModalMeta: document.querySelector("#previewModalMeta"),
  previewSingleModeButton: document.querySelector("#previewSingleModeButton"),
  previewCompareModeButton: document.querySelector("#previewCompareModeButton"),
  closePreviewButton: document.querySelector("#closePreviewButton"),
  previewSinglePane: document.querySelector("#previewSinglePane"),
  previewComparePane: document.querySelector("#previewComparePane"),
  previewSingleImage: document.querySelector("#previewSingleImage"),
  previewCompareSourceImage: document.querySelector("#previewCompareSourceImage"),
  previewCompareResultImage: document.querySelector("#previewCompareResultImage"),
  promptChips: Array.from(document.querySelectorAll(".prompt-chip")),
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
    const request = store.get(WORKSPACE_KEY)

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
    store.put(snapshot, WORKSPACE_KEY)

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
    size: payload.size,
    promptChars: String(payload.prompt || "").length,
    hasApiKey: Boolean(payload.api_key),
    imageName: payload.image?.name,
    imageType: payload.image?.type,
    imageBytesApprox: payload.image?.data_url ? Math.round((payload.image.data_url.length * 3) / 4) : undefined,
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
      editPrompt: refs.editPromptInput.value,
      editModel: refs.editModelInput.value,
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
    },
    source: {
      labelText: refs.sourcePreviewLabel.textContent,
      displayedSourceImage: state.displayedSourceImage,
      editImage: state.editImage,
      generateReferenceImage: state.generateReferenceImage,
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
  syncSizePresetFromInputs()

  if (!refs.generateWidthInput.value || !refs.generateHeightInput.value) {
    setGenerateSize(state.serverConfig.default_size || "1024x1024")
  }

  refs.editPromptInput.value = forms.editPrompt || ""
  refs.editModelInput.value = forms.editModel || state.serverConfig.default_model || "gpt-image-2"
  updatePromptCounters()

  const result = snapshot.result || {}
  state.lastResultPrompt = result.lastResultPrompt || ""
  state.lastResultModel = result.lastResultModel || ""
  state.lastResultMode = result.lastResultMode || null
  state.lastResultImage = cloneImageAsset(result.lastResultImage)
  state.currentComparisonSource = cloneImageAsset(result.currentComparisonSource)
  state.resultPreview = result.imageSrc
    ? {
        src: result.imageSrc,
        mode: result.lastResultMode || null,
      }
    : null
  state.rawResponsePreview = result.rawResponsePreview || null

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
  }

  const source = snapshot.source || {}
  state.editImage = cloneImageAsset(source.editImage)
  state.generateReferenceImage = cloneImageAsset(source.generateReferenceImage)

  if (getAssetDisplaySrc(source.displayedSourceImage)) {
    applySourcePreview(source.displayedSourceImage, source.labelText || "输入图")
  } else {
    clearSourcePreview(source.labelText || "原图")
  }

  renderRawResponsePreview()
  setMode(snapshot.activeMode || "generate", { autoLoadLatest: false })
  updateGenerateIntentUI()
  updateGenerateReferenceUI()
  updateEditSourceUI()
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

function getAssetDisplaySrc(asset) {
  return asset?.savedUrl || asset?.dataUrl || asset?.fileUrl || asset?.src || ""
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
  const hasReference = Boolean(state.generateReferenceImage)

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
}

function setFlowState(element, stateName) {
  if (!element) {
    return
  }

  element.dataset.state = stateName
  element.classList.toggle("is-active", stateName === "active")
  element.classList.toggle("is-complete", stateName === "complete")
}

function updateWorkflowStatus() {
  const hasConnection = Boolean(
    refs.generateUrlInput.value.trim() || refs.editUrlInput.value.trim() || refs.apiKeyInput.value.trim() || state.serverConfig?.has_default_api_key,
  )
  const hasResult = Boolean(state.resultPreview?.src)
  const hasGenerated = Boolean(hasResult && ["generate", "variant"].includes(state.lastResultMode))
  const hasEdited = Boolean(hasResult && ["edit", "variant"].includes(state.lastResultMode))
  const hasCompare = canComparePreviews()
  const hasExport = Boolean(state.lastResultImage?.savedPath || refs.downloadButton.getAttribute("href"))

  setFlowState(refs.flowConnect, hasConnection ? "complete" : "active")
  setFlowState(refs.flowGenerate, hasGenerated ? "complete" : state.activeMode === "generate" ? "active" : "idle")
  setFlowState(refs.flowEdit, hasEdited ? "complete" : state.activeMode === "edit" ? "active" : "idle")
  setFlowState(refs.flowCompare, hasCompare ? "complete" : state.lastResultMode === "edit" ? "active" : "idle")
  setFlowState(refs.flowExport, hasExport ? "complete" : hasResult ? "active" : "idle")
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
  const payload = {
    apiKey: refs.apiKeyInput.value.trim(),
    generateUrl: refs.generateUrlInput.value.trim(),
    editUrl: refs.editUrlInput.value.trim(),
  }
  saveJSON(STORAGE_KEY, payload)
  flashHint("设置已保存到当前浏览器。")
  updateWorkflowStatus()
}

function loadSettings() {
  const local = loadJSON(STORAGE_KEY, {})
  refs.apiKeyInput.value = local.apiKey || ""
  refs.generateUrlInput.value = local.generateUrl || state.serverConfig.generate_url || ""
  refs.editUrlInput.value = local.editUrl || state.serverConfig.edit_url || ""

  refs.generateModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  refs.editModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  setGenerateSize(state.serverConfig.default_size || "1024x1024")

  if (state.serverConfig.has_default_api_key && !local.apiKey) {
    refs.settingsHint.textContent = "服务端已预设默认 API Key。你也可以在这里覆盖它。"
  }

  updateWorkflowStatus()
}

function flashHint(text) {
  refs.settingsHint.textContent = text
  window.clearTimeout(flashHint.timeoutId)
  flashHint.timeoutId = window.setTimeout(() => {
    if (state.serverConfig?.has_default_api_key && !refs.apiKeyInput.value.trim()) {
      refs.settingsHint.textContent = "服务端已预设默认 API Key。你也可以在这里覆盖它。"
      return
    }
    refs.settingsHint.textContent = "设置会保存在当前浏览器。服务端如果已预设默认 key，这里可以留空。"
  }, 2200)
}

function getSettings() {
  return {
    apiKey: refs.apiKeyInput.value.trim(),
    generateUrl: refs.generateUrlInput.value.trim(),
    editUrl: refs.editUrlInput.value.trim(),
  }
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

function setGenerateSize(size) {
  const parsed = parseSizeValue(size) || { width: 1024, height: 1024 }
  refs.generateWidthInput.value = String(parsed.width)
  refs.generateHeightInput.value = String(parsed.height)
  refs.generateSizePreset.value = SIZE_PRESETS.includes(formatSizeValue(parsed.width, parsed.height))
    ? formatSizeValue(parsed.width, parsed.height)
    : "custom"
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
}

function getGenerateSize() {
  const width = Number.parseInt(refs.generateWidthInput.value, 10)
  const height = Number.parseInt(refs.generateHeightInput.value, 10)

  if (!Number.isInteger(width) || !Number.isInteger(height)) {
    throw new Error("请填写有效的宽高尺寸。")
  }

  if (width < 64 || height < 64) {
    throw new Error("宽高都不能小于 64。")
  }

  if (width > 4096 || height > 4096) {
    throw new Error("宽高都不能超过 4096。")
  }

  return formatSizeValue(width, height)
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

function renderProgress() {
  if (!state.progressStartedAt) {
    return
  }

  const elapsedMs = performance.now() - state.progressStartedAt
  const progress = estimateProgress(elapsedMs, state.progressPhase)
  refs.requestProgressFill.style.width = `${progress.toFixed(1)}%`
  refs.progressElapsed.textContent = `${(elapsedMs / 1000).toFixed(1)}s`
  refs.resultTiming.textContent = `请求进行中 ${(elapsedMs / 1000).toFixed(1)}s`
  refs.progressStageLabel.textContent = state.progressLabel || "处理中"
  refs.progressHint.textContent = progressHintForPhase(state.progressPhase, state.progressLabel)
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

function startProgress(label) {
  window.clearInterval(state.progressTimer)
  state.progressStartedAt = performance.now()
  state.progressPhase = "preparing"
  state.progressLabel = label
  refs.progressInspectorItem.classList.remove("hidden")
  refs.generationOverlay.classList.remove("hidden")
  refs.resultPreviewTrigger.classList.add("preview-frame-busy")
  refs.requestProgressFill.style.width = "6%"
  refs.progressElapsed.textContent = "0.0s"
  refs.progressStageLabel.textContent = label
  refs.progressHint.textContent = progressHintForPhase("preparing", label)
  refs.generationOverlayTitle.textContent = label
  refs.generationOverlaySubtitle.textContent = progressHintForPhase("preparing", label)
  state.progressTimer = window.setInterval(renderProgress, 100)
}

function stopProgress() {
  window.clearInterval(state.progressTimer)
  state.progressTimer = null
  state.progressStartedAt = 0
  state.progressPhase = "idle"
  refs.requestProgressFill.style.width = "100%"
  window.setTimeout(() => {
    if (state.isBusy) {
      return
    }
    refs.progressInspectorItem.classList.add("hidden")
    refs.generationOverlay.classList.add("hidden")
    refs.resultPreviewTrigger.classList.remove("preview-frame-busy")
    refs.requestProgressFill.style.width = "0%"
  }, 420)
}

function setBusy(isBusy, label, options = {}) {
  state.isBusy = isBusy
  refs.generateButton.disabled = isBusy
  refs.editButton.disabled = isBusy
  refs.generateTab.disabled = isBusy
  refs.editTab.disabled = isBusy
  refs.requestStatus.textContent = label
  refs.requestBadge.textContent = label
  refs.requestBadge.className = `status-badge ${isBusy ? "working" : "idle"}`
  if (isBusy) {
    startProgress(options.progressLabel || label)
  } else {
    stopProgress()
  }
}

function setError(message = "", details = "") {
  refs.errorMessage.textContent = details ? `${message} ${details}` : message
}

function updateGenerateReferenceUI() {
  const hasReference = Boolean(state.generateReferenceImage)
  refs.generateReferenceDropzone.classList.toggle("ready", hasReference)
  refs.clearGenerateReferenceButton.classList.toggle("hidden", !hasReference)

  if (hasReference) {
    refs.generateReferenceTitle.textContent = "已加载参考图"
    refs.generateReferenceMeta.textContent = state.generateReferenceImage.description || state.generateReferenceImage.name
  } else {
    refs.generateReferenceTitle.textContent = "可选：添加参考图"
    refs.generateReferenceMeta.textContent = "全新开题也可以带一张参考图；有参考图时会使用编辑接口发送。"
  }

  updateGenerateIntentUI()
}

function setGenerateReferenceImage(asset, { showPreview = state.activeMode === "generate" } = {}) {
  state.generateReferenceImage = cloneImageAsset(asset)
  updateGenerateReferenceUI()
  if (showPreview && getAssetDisplaySrc(state.generateReferenceImage)) {
    applySourcePreview(state.generateReferenceImage, "参考图")
  }
  scheduleWorkspacePersist()
}

function clearGenerateReferenceImage({ clearInput = true } = {}) {
  state.generateReferenceImage = null
  if (clearInput) {
    refs.generateReferenceInput.value = ""
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

function setEditImage(asset, { showPreview = state.activeMode === "edit", previewLabel = "输入图" } = {}) {
  state.editImage = cloneImageAsset(asset)
  updateEditSourceUI()

  if (showPreview) {
    applySourcePreview(state.editImage, previewLabel)
  }

  scheduleWorkspacePersist()
}

function useLastResultAsEditSource({ showPreview = true, focus = false } = {}) {
  if (!state.lastResultImage) {
    return false
  }

  const asset = cloneImageAsset(state.lastResultImage, {
    origin: "result",
    description: `自动使用最新结果 · ${state.lastResultImage.name}`,
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
  refs.generatePanel.classList.toggle("hidden", mode !== "generate")
  refs.editPanel.classList.toggle("hidden", mode !== "edit")
  refs.sourcePreviewCard.classList.toggle("subtle", mode !== "edit")

  if (mode === "edit" && previousMode !== "edit" && options.autoLoadLatest !== false && state.lastResultImage) {
    useLastResultAsEditSource({ showPreview: true })
  } else if (mode === "generate" && getAssetDisplaySrc(state.generateReferenceImage)) {
    applySourcePreview(state.generateReferenceImage, "参考图")
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
  updateWorkflowStatus()
}

function closePreview() {
  refs.previewModal.classList.add("hidden")
  refs.previewModal.setAttribute("aria-hidden", "true")
  document.body.classList.remove("modal-open")
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
  refs.rawResponseOutput.textContent = "{}"
  refs.debugOutput.textContent = "等待操作。"
  refs.downloadButton.classList.add("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "true")
  refs.downloadButton.removeAttribute("href")

  state.lastResultPrompt = ""
  state.lastResultImage = null
  state.lastResultModel = ""
  state.lastResultMode = null
  state.currentComparisonSource = null
  state.resultPreview = null
  state.rawResponsePreview = null
  state.debugLines = []
  state.generateIntent = "fresh"

  closePreview()
  renderRawResponsePreview()
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
}

function setResult(payload, durationMs, requestSource = null) {
  const imageSource = payload.saved_image_url || payload.image_data_url || payload.image_url
  if (!imageSource) {
    throw new Error("上游接口没有返回可展示的图片。")
  }

  const isTransformMode = ["edit", "variant", "reference"].includes(payload.mode)
  refs.resultPreviewLabel.textContent = payload.mode === "variant"
    ? "延展后"
    : payload.mode === "edit"
      ? "编辑后"
      : payload.mode === "reference"
        ? "参考生成"
        : "输出"
  refs.resultImage.src = imageSource
  refs.resultImage.classList.add("visible")
  refs.resultPreviewEmpty.classList.add("hidden")
  refs.resultPreviewEmpty.textContent = "生成或编辑成功后，这里会显示输出结果。"

  const displayedPrompt = payload.prompt || "结果已生成"
  state.lastResultPrompt = displayedPrompt
  refs.resultPrompt.textContent = displayedPrompt
  state.lastResultModel = payload.model || ""
  state.lastResultMode = payload.mode || null
  state.resultPreview = {
    src: imageSource,
    mode: payload.mode || null,
  }

  if (payload.image_data_url || payload.saved_image_url || payload.image_url) {
    state.lastResultImage = {
      name: payload.saved_image_name || `picgen-${payload.mode}-${Date.now()}.png`,
      type: payload.saved_image_mime || (payload.image_data_url ? inferMimeFromDataUrl(payload.image_data_url) : ""),
      dataUrl: payload.image_data_url || "",
      savedUrl: payload.saved_image_url || "",
      savedPath: payload.saved_image_path || "",
      metadataPath: payload.saved_metadata_path || "",
      fileUrl: payload.saved_image_url || payload.image_url || "",
      origin: "result",
      description: `最新输出 · ${payload.model || ""}`,
      src: imageSource,
    }
  } else {
    state.lastResultImage = null
  }

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
  if (payload.size) {
    metaParts.push(payload.size)
  }
  refs.resultMeta.textContent = metaParts.filter(Boolean).join(" · ")
  refs.resultTiming.textContent = `请求耗时 ${durationMs.toFixed(1)} ms`
  refs.resultStorage.textContent = payload.saved_image_path ? `已落盘到 ${payload.saved_image_path}` : ""
  state.rawResponsePreview = sanitizeRawResponse(payload.raw_response || {})
  renderRawResponsePreview()

  refs.downloadButton.href = payload.saved_image_url || imageSource
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.download = payload.saved_image_name || `picgen-${payload.mode}-${Date.now()}.png`

  updateEditSourceUI()
  updateGenerateIntentUI()
  updatePreviewAvailability()
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

function historySummary(item) {
  if (item.mode === "generate" || item.mode === "variant" || item.mode === "reference") {
    return item.size ? `${item.model} · ${item.size}` : item.model
  }
  return item.model
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
        refs.generateModelInput.value = item.model
        setGenerateSize(item.size || state.serverConfig.default_size || "1024x1024")
        updatePromptCounters()
        refs.generatePromptInput.focus()
      } else {
        setMode("edit")
        refs.editPromptInput.value = item.prompt
        refs.editModelInput.value = item.model
        updatePromptCounters()
        refs.editPromptInput.focus()
      }
    })
    refs.historyList.appendChild(button)
  })
}

function pushHistory(item) {
  state.history = [item, ...state.history].slice(0, MAX_HISTORY_ITEMS)
  saveJSON(HISTORY_KEY, state.history)
  renderHistory()
}

async function postJSON(url, payload, options = {}) {
  const requestId = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`
  const startedAt = performance.now()
  const timeoutMs = options.timeoutMs || 190000
  appendDebugLine("准备发送本地代理请求", {
    requestId,
    url,
    mode: options.mode,
    ...summarizePayloadForDebug(payload),
  })
  setProgressPhase("uploading", options.progressLabel || "正在提交请求")

  const controller = new AbortController()
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (error) {
    appendDebugLine("fetch 失败", {
      requestId,
      elapsedMs: Math.round(performance.now() - startedAt),
      error: error.name === "AbortError" ? "请求超时或被中断" : error.message,
    })
    throw error.name === "AbortError"
      ? new Error("请求等待超时。请查看本地服务终端日志，确认后端是否卡在上游接口。")
      : error
  } finally {
    window.clearTimeout(timeoutId)
    window.clearTimeout(waitingNoticeId)
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
    })
    throw new Error(data.details ? `${data.error}\n${data.details}` : data.error || "请求失败")
  }

  appendDebugLine("请求完成", {
    requestId,
    elapsedMs: Math.round(performance.now() - startedAt),
  })

  return data
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

async function submitVariantGenerate({ resetLog = true } = {}) {
  if (resetLog) {
    resetDebugLog("点击生成按钮：基于当前结果延展")
  }
  const prompt = refs.generatePromptInput.value
  const model = refs.generateModelInput.value.trim()
  const settings = getSettings()

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

  if (!settings.editUrl) {
    appendDebugLine("参数校验失败：编辑接口 URL 为空")
    setError("基于当前结果延展需要编辑接口 URL。")
    refs.editUrlInput.focus()
    return
  }

  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "延展中", { progressLabel: "准备延展图像" })

  const requestSource = cloneImageAsset(state.lastResultImage)
  previewPendingResult({
    mode: "variant",
    prompt,
    model,
    sourceName: requestSource.name || "最新结果",
  })
  const startedAt = performance.now()

  try {
    appendDebugLine("读取延展输入图片")
    setProgressPhase("preparing", "读取参考图")
    const requestSourceDataUrl = await ensureAssetDataUrl(requestSource)
    const result = await postJSON("/api/edit", {
      api_key: settings.apiKey,
      endpoint_url: settings.editUrl,
      prompt,
      model,
      image: {
        name: requestSource.name,
        type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
        data_url: requestSourceDataUrl,
      },
    }, {
      mode: "variant",
      progressLabel: "提交延展请求",
      waitingLabel: "等待上游延展",
    })
    setResult({ ...result, mode: "variant" }, performance.now() - startedAt, requestSource)
    pushHistory({
      mode: "variant",
      prompt,
      model,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("延展请求失败", { error: error.message })
    setError(error.message)
  } finally {
    setBusy(false, "空闲")
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
  const model = refs.generateModelInput.value.trim()
  const settings = getSettings()

  if (!prompt.trim()) {
    appendDebugLine("参数校验失败：生成提示词为空")
    setError("生成提示词不能为空。")
    refs.generatePromptInput.focus()
    return
  }

  if (!state.generateReferenceImage && !settings.generateUrl) {
    appendDebugLine("参数校验失败：生成接口 URL 为空")
    setError("请先填写生成接口 URL。")
    refs.generateUrlInput.focus()
    return
  }

  if (state.generateReferenceImage && !settings.editUrl) {
    appendDebugLine("参数校验失败：参考图生成缺少编辑接口 URL")
    setError("带参考图生成需要填写编辑接口 URL，因为图片会通过 multipart 发送给上游。")
    refs.editUrlInput.focus()
    return
  }

  let size
  try {
    size = getGenerateSize()
  } catch (error) {
    appendDebugLine("参数校验失败：尺寸无效", { error: error.message })
    setError(error.message)
    return
  }

  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "生成中", { progressLabel: "准备生成图像" })
  previewPendingResult({
    mode: state.generateReferenceImage ? "reference" : "generate",
    prompt,
    model,
    size,
    sourceName: state.generateReferenceImage?.name || "",
  })

  const startedAt = performance.now()

  try {
    if (state.generateReferenceImage) {
      appendDebugLine("读取生成参考图")
      setProgressPhase("preparing", "读取参考图")
      const referenceSource = cloneImageAsset(state.generateReferenceImage)
      const referenceDataUrl = await ensureAssetDataUrl(referenceSource)
      const result = await postJSON("/api/edit", {
        api_key: settings.apiKey,
        endpoint_url: settings.editUrl,
        prompt,
        model,
        size,
        image: {
          name: referenceSource.name,
          type: referenceSource.type || inferMimeFromDataUrl(referenceDataUrl),
          data_url: referenceDataUrl,
        },
      }, {
        mode: "reference",
        progressLabel: "提交参考图生成",
        waitingLabel: "等待上游参考生成",
      })
      setResult({ ...result, mode: "reference", size }, performance.now() - startedAt, referenceSource)
      pushHistory({
        mode: "reference",
        prompt,
        model,
        size,
        createdAt: new Date().toISOString(),
      })
      return
    }

    const result = await postJSON("/api/generate", {
      api_key: settings.apiKey,
      endpoint_url: settings.generateUrl,
      prompt,
      model,
      size,
      n: 1,
    }, {
      mode: "generate",
      progressLabel: "提交生成请求",
      waitingLabel: "等待上游生成",
    })
    setResult(result, performance.now() - startedAt)
    pushHistory({
      mode: "generate",
      prompt,
      model,
      size,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("生成请求失败", { error: error.message })
    setError(error.message)
  } finally {
    setBusy(false, "空闲")
  }
}

async function submitEdit() {
  resetDebugLog("点击编辑按钮：编辑图片")
  const prompt = refs.editPromptInput.value
  const model = refs.editModelInput.value.trim()
  const settings = getSettings()

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

  if (!settings.editUrl) {
    appendDebugLine("参数校验失败：编辑接口 URL 为空")
    setError("请先填写编辑接口 URL。")
    refs.editUrlInput.focus()
    return
  }

  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "编辑中", { progressLabel: "准备编辑图像" })

  const requestSource = cloneImageAsset(state.editImage)
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
    const result = await postJSON("/api/edit", {
      api_key: settings.apiKey,
      endpoint_url: settings.editUrl,
      prompt,
      model,
      image: {
        name: requestSource.name,
        type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
        data_url: requestSourceDataUrl,
      },
    }, {
      mode: "edit",
      progressLabel: "提交编辑请求",
      waitingLabel: "等待上游编辑",
    })
    setResult(result, performance.now() - startedAt, requestSource)
    pushHistory({
      mode: "edit",
      prompt,
      model,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("编辑请求失败", { error: error.message })
    setError(error.message)
  } finally {
    setBusy(false, "空闲")
  }
}

function clearGenerateForm() {
  refs.generatePromptInput.value = ""
  refs.generateModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  clearGenerateReferenceImage()
  setGenerateSize(state.serverConfig.default_size || "1024x1024")
  if (!state.lastResultImage) {
    state.generateIntent = "fresh"
  }
  updatePromptCounters()
  updateGenerateIntentUI()
  scheduleWorkspacePersist()
}

function clearEditForm() {
  refs.editPromptInput.value = ""
  refs.editModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  refs.editImageInput.value = ""
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
    setError(error.message)
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

function bindEvents() {
  refs.saveSettingsButton.addEventListener("click", saveSettings)
  refs.toggleKeyButton.addEventListener("click", () => {
    const isHidden = refs.apiKeyInput.type === "password"
    refs.apiKeyInput.type = isHidden ? "text" : "password"
    refs.toggleKeyButton.textContent = isHidden ? "隐藏" : "显示"
  })
  refs.clearHistoryButton.addEventListener("click", () => {
    state.history = []
    saveJSON(HISTORY_KEY, state.history)
    renderHistory()
  })

  refs.generateTab.addEventListener("click", () => setMode("generate"))
  refs.editTab.addEventListener("click", () => setMode("edit"))
  refs.freshGenerateMode.addEventListener("click", () => setGenerateIntent("fresh"))
  refs.variantGenerateMode.addEventListener("click", () => {
    if (!state.lastResultImage) {
      return
    }
    setGenerateIntent("variant")
  })
  refs.generateButton.addEventListener("click", submitGenerate)
  refs.editButton.addEventListener("click", submitEdit)
  refs.clearGenerateButton.addEventListener("click", clearGenerateForm)
  refs.clearEditButton.addEventListener("click", clearEditForm)
  refs.continueEditButton.addEventListener("click", continueEditingFromResult)
  refs.startVariantButton.addEventListener("click", startVariantFromResult)
  refs.previewCompareButton.addEventListener("click", () => openPreview("result", "compare"))

  refs.copyPromptButton.addEventListener("click", async () => {
    if (!state.lastResultPrompt) {
      setError("当前没有可复制的提示词。")
      return
    }
    try {
      await navigator.clipboard.writeText(state.lastResultPrompt)
      setError("已复制本次提示词。")
    } catch {
      setError("浏览器不允许复制到剪贴板。")
    }
  })

  refs.generateSizePreset.addEventListener("change", () => {
    if (refs.generateSizePreset.value !== "custom") {
      setGenerateSize(refs.generateSizePreset.value)
    }
    scheduleWorkspacePersist()
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
  ].forEach((input) => {
    input.addEventListener("input", () => {
      updatePromptCounters()
      updateWorkflowStatus()
      updateGenerateIntentUI()
      scheduleWorkspacePersist()
    })
  })

  ;[refs.generateUrlInput, refs.editUrlInput, refs.apiKeyInput].forEach((input) => {
    input.addEventListener("input", updateWorkflowStatus)
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

  refs.generateReferenceDropzone.addEventListener("click", () => refs.generateReferenceInput.click())
  refs.generateReferenceDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      refs.generateReferenceInput.click()
    }
  })
  refs.generateReferenceInput.addEventListener("change", async (event) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    try {
      await useGenerateReferenceFile(file)
      setError("")
    } catch (error) {
      setError(error.message)
    }
  })
  refs.clearGenerateReferenceButton.addEventListener("click", (event) => {
    event.stopPropagation()
    clearGenerateReferenceImage()
    setError("")
  })

  ;["dragenter", "dragover"].forEach((eventName) => {
    refs.generateReferenceDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      refs.generateReferenceDropzone.classList.add("dragging")
    })
  })

  ;["dragleave", "dragend", "drop"].forEach((eventName) => {
    refs.generateReferenceDropzone.addEventListener(eventName, (event) => {
      event.preventDefault()
      if (eventName !== "drop") {
        refs.generateReferenceDropzone.classList.remove("dragging")
      }
    })
  })

  refs.generateReferenceDropzone.addEventListener("drop", async (event) => {
    refs.generateReferenceDropzone.classList.remove("dragging")
    const file = event.dataTransfer?.files?.[0]
    if (!file) {
      return
    }
    try {
      await useGenerateReferenceFile(file)
      setError("")
    } catch (error) {
      setError(error.message)
    }
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
      setError(error.message)
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
      setError(error.message)
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
    renderPreviewModal()
  })
  refs.closePreviewButton.addEventListener("click", closePreview)
  refs.previewModalBackdrop.addEventListener("click", closePreview)
  refs.previewModal.addEventListener("click", (event) => {
    if (event.target === refs.previewModal) {
      closePreview()
    }
  })

  window.addEventListener("keydown", (event) => {
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
  state.history = loadJSON(HISTORY_KEY, [])
  renderHistory()

  try {
    const response = await fetch("/api/config", { cache: "no-store" })
    state.serverConfig = await response.json()
  } catch {
    refs.settingsHint.textContent = "无法读取服务端默认配置，但你仍然可以手动填写全部参数。"
    state.serverConfig = {
      default_model: "gpt-image-2",
      default_size: "1024x1024",
      generate_url: "",
      edit_url: "",
      has_default_api_key: false,
    }
  }

  loadSettings()
  bindEvents()
  updatePromptCounters()
  updateGenerateIntentUI()
  const restored = await restoreWorkspaceState()

  if (!restored) {
    updateEditSourceUI()
    updateGenerateIntentUI()
    updatePreviewAvailability()
    setMode("generate", { autoLoadLatest: false })
  }

  state.persistenceReady = true
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

init()
