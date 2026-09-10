export const DEFAULT_RESPONSES_MODEL = "gpt-6-astra"
const LEGACY_RESPONSES_MODELS = new Set(["gpt-5.5", "gpt-5.6-sol"])
const LEGACY_DEFAULT_RESPONSES_MODEL = "gpt-5.5"
export const RESPONSES_MODEL_STORAGE_VERSION = 5
export const RESPONSES_REASONING_STORAGE_VERSION = 1
const LEGACY_DEFAULT_RESPONSES_REASONING_EFFORT = "max"
const RESPONSES_REASONING_EFFORTS = new Set(["low", "medium", "high", "xhigh", "max", "ultra"])

export function migrateStoredImageModel(model, defaultModel = "gpt-image-2.5-sunburst") {
  const value = String(model || "").trim()
  return !value || value === "gpt-image-2" ? defaultModel : value
}

export function migrateStoredResponsesSettings(settings = {}, defaultModel = DEFAULT_RESPONSES_MODEL) {
  const version = Number(settings.responsesModelStorageVersion || 0)
  const storedModel = String(settings.responsesModel || "").trim()
  if (version >= RESPONSES_MODEL_STORAGE_VERSION && !LEGACY_RESPONSES_MODELS.has(storedModel)) {
    return settings
  }

  const configuredDefault = String(defaultModel || "").trim()
  const normalizedDefault = !configuredDefault || configuredDefault === LEGACY_DEFAULT_RESPONSES_MODEL
    ? DEFAULT_RESPONSES_MODEL
    : configuredDefault
  return {
    ...settings,
    responsesModel: LEGACY_RESPONSES_MODELS.has(storedModel)
      ? normalizedDefault
      : storedModel,
    responsesModelStorageVersion: RESPONSES_MODEL_STORAGE_VERSION,
  }
}

export function migrateStoredResponsesReasoningSettings(settings = {}) {
  const version = Number(settings.responsesReasoningStorageVersion || 0)
  const rawEffort = String(settings.responsesReasoningEffort || "").trim()
  const normalizedEffort = rawEffort.toLowerCase()
  const storedEffort = RESPONSES_REASONING_EFFORTS.has(normalizedEffort)
    ? normalizedEffort
    : ""
  if (
    version >= RESPONSES_REASONING_STORAGE_VERSION
    && rawEffort === storedEffort
  ) {
    return settings
  }

  return {
    ...settings,
    responsesReasoningEffort: version < RESPONSES_REASONING_STORAGE_VERSION
      && storedEffort === LEGACY_DEFAULT_RESPONSES_REASONING_EFFORT
      ? ""
      : storedEffort,
    responsesReasoningStorageVersion: RESPONSES_REASONING_STORAGE_VERSION,
  }
}
