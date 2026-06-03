const STORAGE_KEY = "picgen-console-settings-v2"
const LEGACY_STORAGE_KEY = "picgen-console-settings-v1"
const HISTORY_KEY = "picgen-console-history-v1"
const COMPANY_LOGO_B64_URL = "6renyou.png.b64"
const COMPANY_LOGO_NAME = "6renyou.png"
const COMPANY_LOGO_MIME = "image/png"
const COMPANY_LOGO_GUIDANCE = [
  "",
  "6 人游 LOGO 合成要求：",
  "请把参考图中的 6 人游 LOGO 作为公司官方标识整合进最终画面，默认放在左上角的合理位置，整体 LOGO 面积要小一些，做成克制的品牌角标而不是主视觉元素。",
  "LOGO 由左侧图标和右侧两行文字组成：第一行文字必须精确保留为“6 人游定制旅行”，第二行文字必须精确保留为“Friends & Family”。",
  "必须保持 LOGO 的图标样式、文字内容、文字顺序、两行布局、比例、笔画结构和透明区域不变；不能删减、改写、翻译、替换大小写或改变这些文字内容。",
  "左侧图标原本的几种绿色必须保持不变，不能改成白色、黑色、单色或其他品牌色，也不能重新绘制图标。",
  "为了画面可读性，只能调整右侧两行文字的颜色；文字颜色应与背景和整体设计协调，避免突兀，可使用白色、浅色、深色或轻微描边/阴影来保证清晰。",
  "请让 LOGO 与最终设计的构图、光影、材质和留白协调，避免像后期随意贴上去的水印；尺寸控制在不抢主视觉的较小比例。",
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
  continueEditButton: document.querySelector("#continueEditButton"),
  startVariantButton: document.querySelector("#startVariantButton"),
  previewCompareButton: document.querySelector("#previewCompareButton"),
  copyPromptButton: document.querySelector("#copyPromptButton"),
  errorMessage: document.querySelector("#errorMessage"),
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

function setFlowState(element, stateName) {
  if (!element) {
    return
  }

  element.dataset.state = stateName
  element.classList.toggle("is-active", stateName === "active")
  element.classList.toggle("is-complete", stateName === "complete")
}

function updateWorkflowStatus() {
  const savedApiKey = state.savedApiKey || ""
  const hasConnection = Boolean(
    refs.generateUrlInput.value.trim()
      || refs.editUrlInput.value.trim()
      || refs.responsesUrlInput.value.trim()
      || refs.apiKeyInput.value.trim()
      || savedApiKey
      || state.serverConfig?.has_default_api_key,
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
  const local = loadJSON(STORAGE_KEY, {})
  const legacy = loadJSON(LEGACY_STORAGE_KEY, {})
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
  saveJSON(STORAGE_KEY, payload)
  refs.apiKeyInput.value = ""
  flashHint(newApiKey ? "新 API Key 已保存在当前浏览器本地；输入框已清空，不会回显 key。" : "设置已保存；API Key 未变更。")
  updateWorkflowStatus()
}

function loadSettings() {
  const local = loadJSON(STORAGE_KEY, {})
  const legacy = loadJSON(LEGACY_STORAGE_KEY, {})
  const localResponsesUrl = local.responsesUrl || ""
  const responsesUrl = DEPRECATED_RESPONSES_URLS.has(localResponsesUrl) && state.serverConfig.responses_url
    ? state.serverConfig.responses_url
    : localResponsesUrl || state.serverConfig.responses_url || ""
  state.savedApiKey = local.apiKey || legacy.apiKey || ""
  refs.apiKeyInput.value = ""
  refs.generateUrlInput.value = local.generateUrl || legacy.generateUrl || state.serverConfig.generate_url || ""
  refs.editUrlInput.value = local.editUrl || legacy.editUrl || state.serverConfig.edit_url || ""
  refs.responsesUrlInput.value = responsesUrl
  refs.responsesModelInput.value = normalizeResponsesModel(local.responsesModel || state.serverConfig.default_responses_model)

  refs.generateModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  refs.editModelInput.value = state.serverConfig.default_model || "gpt-image-2"
  setGenerateSize(state.serverConfig.default_size || "auto")
  setImageTransport(local.imageTransport === "responses" ? "responses" : "images")

  if (state.savedApiKey) {
    refs.settingsHint.textContent = "浏览器本地已保存 API Key。输入框只用于填入新 key，不会回显现有 key。"
  } else if (state.serverConfig.has_default_api_key) {
    refs.settingsHint.textContent = "服务端已预设默认 API Key。你可以在这里填入新 key 覆盖。"
  }

  updateWorkflowStatus()
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
  refs.logoComposeStatus.textContent = refs.logoOverlayEnabled.checked ? "AI 合成" : "未启用"
  updateGenerateSampleCountUI()
}

function shouldUseCompanyLogo() {
  return Boolean(refs.logoOverlayEnabled?.checked)
}

function updateGenerateSampleCountUI() {
  const hasReference = Boolean(generateReferenceImages().length)
  const isVariant = state.generateIntent === "variant"
  const logoRequested = shouldUseCompanyLogo()
  const disabled = logoRequested || hasReference || isVariant
  refs.generateSampleCountInput.disabled = disabled
  refs.generateSampleCountInput.closest("label")?.classList.toggle("is-disabled", disabled)

  if (isVariant) {
    refs.generateSampleCountHint.textContent = "基于当前结果延展固定 1 张。"
  } else if (hasReference) {
    refs.generateSampleCountHint.textContent = hasStyleTransferReferences()
      ? "模板 + 素材图仍按现有逻辑默认 3 张。"
      : "带参考图生成固定 1 张。"
  } else if (logoRequested) {
    refs.generateSampleCountHint.textContent = "带 LOGO 会走 AI 参考图合成，固定 1 张。"
  } else {
    refs.generateSampleCountHint.textContent = "纯文字生图可填 1-3；留空默认 1。"
  }
}

function withCompanyLogoPrompt(prompt, logoRequested = shouldUseCompanyLogo()) {
  return logoRequested ? `${prompt.trim()}\n${COMPANY_LOGO_GUIDANCE}` : prompt
}

function logoContextPrompt(prompt, contextLabel, logoRequested = shouldUseCompanyLogo()) {
  if (!logoRequested) {
    return prompt
  }
  return withCompanyLogoPrompt(
    `${prompt.trim()}\n本次任务需要基于${contextLabel}进行整体设计，不是简单覆盖贴图。`,
    logoRequested,
  )
}

async function buildCompanyLogoReferencePart() {
  const response = await fetch(COMPANY_LOGO_B64_URL)
  if (!response.ok) {
    throw new Error("无法读取 6 人游 LOGO 图片。")
  }
  const logoBase64 = (await response.text()).replace(/\s+/g, "")
  if (!logoBase64) {
    throw new Error("6 人游 LOGO 图片内容为空。")
  }
  return {
    name: COMPANY_LOGO_NAME,
    type: COMPANY_LOGO_MIME,
    data_url: `data:${COMPANY_LOGO_MIME};base64,${logoBase64}`,
    role: "brand_logo",
  }
}

async function appendCompanyLogoReference(parts, logoRequested = shouldUseCompanyLogo()) {
  if (!logoRequested) {
    refs.logoComposeStatus.textContent = "未启用"
    return parts
  }
  refs.logoComposeStatus.textContent = "随请求提交"
  appendDebugLine("将 6 人游 LOGO 作为 AI 参考图提交", {
    placement: "top-left",
    source: COMPANY_LOGO_NAME,
  })
  return [...parts, await buildCompanyLogoReferencePart()]
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

function stopProgress() {
  window.clearInterval(state.progressTimer)
  state.progressTimer = null
  state.progressStartedAt = 0
  state.progressPhase = "idle"
  state.progressExpectedCount = 1
  refs.requestProgressFill.style.width = "100%"
  refs.generationOrbit?.style.setProperty("--progress-degrees", "360deg")
  refs.generationOrbit?.setAttribute("data-progress", "100%")
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
  refs.generateButton.disabled = isBusy
  refs.editButton.disabled = isBusy
  refs.generateTab.disabled = isBusy
  refs.editTab.disabled = isBusy
  refs.requestStatus.textContent = label
  refs.requestBadge.textContent = label
  refs.requestBadge.className = `status-badge ${isBusy ? "working" : "idle"}`
  if (isBusy) {
    startProgress(options.progressLabel || label, options)
  } else {
    stopProgress()
  }
}

function setError(message = "", details = "") {
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

function setRiskPanel(status, text, { hidden = false } = {}) {
  refs.copyrightRiskPanel?.classList.toggle("hidden", hidden)
  if (refs.copyrightRiskStatus) {
    refs.copyrightRiskStatus.textContent = status
  }
  if (refs.copyrightRiskText) {
    refs.copyrightRiskText.textContent = text
  }
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
  refs.logoComposeStatus.textContent = refs.logoOverlayEnabled?.checked ? "AI 合成" : "未启用"
  refs.rawResponseOutput.textContent = "{}"
  refs.debugOutput.textContent = "等待操作。"
  setRiskPanel("等待检查", "生成完成后自动检查。", { hidden: true })
  refs.downloadButton.classList.add("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "true")
  refs.downloadButton.removeAttribute("href")

  state.lastResultPrompt = ""
  state.lastResultImage = null
  state.lastResultModel = ""
  state.lastResultMode = null
  state.currentComparisonSource = null
  state.resultPreview = null
  state.resultCandidates = []
  state.selectedCandidateIndex = 0
  state.rawResponsePreview = null
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
  renderResultCandidates()
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

function setResult(payload, durationMs, requestSource = null) {
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

  state.lastResultImage = cloneImageAsset(firstCandidate.asset)

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
  refs.resultTiming.textContent = `请求耗时 ${durationMs.toFixed(1)} ms`
  refs.resultStorage.textContent = firstCandidate.saved_image_path
    ? `已落盘到 ${firstCandidate.saved_image_path}${actualSize ? ` · 实际尺寸 ${actualSize}` : ""}`
    : actualSize
      ? `实际尺寸 ${actualSize}`
      : ""
  if (payload.size && actualSize && !isSameSize(payload.size, actualSize)) {
    setError(`上游返回尺寸为 ${actualSize}，与请求尺寸 ${payload.size} 不一致。图片已按上游原始返回保存，本地没有缩放。`)
  } else {
    setError("")
  }
  state.rawResponsePreview = sanitizeRawResponse(payload.raw_response || {})
  renderRawResponsePreview()

  refs.downloadButton.href = firstCandidate.saved_image_url || imageSource
  refs.downloadButton.classList.remove("disabled-link")
  refs.downloadButton.setAttribute("aria-disabled", "false")
  refs.downloadButton.download = firstCandidate.saved_image_name || `picgen-${payload.mode}-${Date.now()}.png`
  renderResultCandidates()
  refs.logoComposeStatus.textContent = payload.logo_requested ? "AI 已处理" : "未启用"
  void checkCopyrightRisk(payload)

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
  saveJSON(HISTORY_KEY, state.history)
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
      details: data.details || "",
    })
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    const data = await response.json()
    if (!response.ok) {
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

async function downscaleDataUrlForRisk(dataUrl, maxSide = 768, quality = 0.82) {
  if (!dataUrl) {
    return ""
  }
  const image = await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error("无法读取版权风险检查图片。"))
    img.src = dataUrl
  })
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
  const requestPrompt = logoContextPrompt(prompt, "当前结果图", logoRequested)
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

  saveSettings()
  setError("")
  closePreview()
  setBusy(true, "延展中", { progressLabel: "准备延展图像" })

  const requestSource = cloneImageAsset(state.lastResultImage)
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
    const imagePart = {
      name: requestSource.name,
      type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
      data_url: requestSourceDataUrl,
      role: "source_image",
    }
    const requestImages = await appendCompanyLogoReference([imagePart], logoRequested)
    let result
    if (useResponses) {
      result = await postJSON("api/responses-image", {
        api_key: settings.apiKey,
        endpoint_url: settings.responsesUrl,
        prompt: requestPrompt,
        model,
        mode: logoRequested ? "variant-with-logo" : "variant",
        transport: "responses-image",
        logo_requested: logoRequested,
        allow_inline_fallback: true,
        size,
        ...imageOptions,
        image: imagePart,
        images: requestImages,
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
        mode: logoRequested ? "variant-with-logo" : "variant",
        logo_requested: logoRequested,
        size,
        ...imageOptions,
        image: imagePart,
        images: requestImages,
      }, {
        mode: "variant",
        progressLabel: "提交延展请求",
        waitingLabel: "等待上游延展",
      })
    }
    setResult({ ...result, mode: "variant", prompt, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSource)
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
    setError(error.message, error.details)
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
  const settings = getSettings()
  const useResponses = settings.imageTransport === "responses"
  const imageModel = refs.generateModelInput.value.trim() || state.serverConfig?.default_model || "gpt-image-2"
  const referenceImages = generateReferenceImages()
  const dualReference = hasStyleTransferReferences()
  const logoRequested = shouldUseCompanyLogo()
  const model = (referenceImages.length || logoRequested) && useResponses ? settings.responsesModel : imageModel
  const requestPrompt = logoContextPrompt(
    dualReference ? styleTransferPrompt(prompt) : prompt,
    referenceImages.length ? "用户提供的参考图" : "6 人游 LOGO 参考图",
    logoRequested,
  )
  const requiresReferenceTransport = referenceImages.length || logoRequested

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
      if (!requireResponsesSettings(settings, logoRequested ? "带 LOGO 生成" : "带参考图生成")) {
        return
      }
    } else if (!requireEditSettings(settings, logoRequested ? "带 LOGO 生成" : "带参考图生成")) {
      return
    }
  }

  let size
  let imageOptions
  let sampleCount
  try {
    size = getGenerateSize()
    imageOptions = getOpenAIImageOptions()
    sampleCount = logoRequested || referenceImages.length ? 1 : getGenerateSampleCount()
  } catch (error) {
    appendDebugLine("参数校验失败：OpenAI 图片参数无效", { error: error.message })
    setError(error.message, error.details)
    return
  }

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
    sourceName: dualReference ? "风格模板 + 素材图" : referenceImages[0]?.name || (logoRequested ? COMPANY_LOGO_NAME : ""),
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
        referenceParts.push({
          name: referenceSource.name,
          type: referenceSource.type || inferMimeFromDataUrl(referenceDataUrl),
          data_url: referenceDataUrl,
          role: referenceSource.role || referenceSource.origin || "reference",
        })
      }
      const requestParts = await appendCompanyLogoReference(referenceParts, logoRequested)
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
          mode: logoRequested ? "reference-with-logo" : "reference",
          transport: "responses-image",
          logo_requested: logoRequested,
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
          mode: logoRequested ? "reference-with-logo" : "reference",
          logo_requested: logoRequested,
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
      setResult({ ...result, mode: "reference", prompt, size, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSources.at(-1))
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
      prompt,
      model,
      logo_requested: false,
      sample_count: sampleCount,
      size,
      ...imageOptions,
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
      logoRequested: false,
      sampleCount,
      size,
      ...imageOptions,
      createdAt: new Date().toISOString(),
    })
  } catch (error) {
    appendDebugLine("生成请求失败", { error: error.message })
    setError(error.message, error.details)
  } finally {
    setBusy(false, "空闲")
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
  const requestPrompt = logoContextPrompt(prompt, "输入图", logoRequested)

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
    const imagePart = {
      name: requestSource.name,
      type: requestSource.type || inferMimeFromDataUrl(requestSourceDataUrl),
      data_url: requestSourceDataUrl,
      role: "source_image",
    }
    const requestImages = await appendCompanyLogoReference([imagePart], logoRequested)

    let maskPart = null
    if (state.editMaskImage) {
      appendDebugLine("读取编辑 mask")
      const maskDataUrl = await ensureAssetDataUrl(state.editMaskImage)
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
        mode: logoRequested ? "edit-with-logo" : "edit",
        transport: "responses-image",
        logo_requested: logoRequested,
        allow_inline_fallback: true,
        image: imagePart,
        images: requestImages,
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
        mode: logoRequested ? "edit-with-logo" : "edit",
        logo_requested: logoRequested,
        image: imagePart,
        images: requestImages,
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
    setResult({ ...result, mode: "edit", prompt, transport, logo_requested: logoRequested }, performance.now() - startedAt, requestSource)
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
    setError(error.message, error.details)
  } finally {
    setBusy(false, "空闲")
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
    saveJSON(HISTORY_KEY, state.history)
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
  state.history = loadJSON(HISTORY_KEY, [])
  renderHistory()

  try {
    const response = await fetch("api/config", { cache: "no-store" })
    state.serverConfig = await response.json()
  } catch {
    refs.settingsHint.textContent = "无法读取服务端默认配置，但你仍然可以手动填写全部参数。"
    state.serverConfig = {
      default_model: "gpt-image-2",
      default_responses_model: "gpt-5.5",
      default_size: "1024x1024",
      generate_url: "",
      edit_url: "",
      responses_url: "",
      has_default_api_key: false,
    }
  }

  loadSettings()
  bindEvents()
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
  updateWorkflowStatus()
  scheduleWorkspacePersist()
}

init()
