export const DEFAULT_RESPONSES_MODEL = "gpt-5.6-sol"
const LEGACY_DEFAULT_RESPONSES_MODEL = "gpt-5.5"
export const RESPONSES_MODEL_STORAGE_VERSION = 4
export const RESPONSES_REASONING_STORAGE_VERSION = 1
const LEGACY_DEFAULT_RESPONSES_REASONING_EFFORT = "max"
const RESPONSES_REASONING_EFFORTS = new Set(["low", "medium", "high", "xhigh", "max", "ultra"])

export function migrateStoredResponsesSettings(settings = {}, defaultModel = DEFAULT_RESPONSES_MODEL) {
  const version = Number(settings.responsesModelStorageVersion || 0)
  const storedModel = String(settings.responsesModel || "").trim()
  if (version >= RESPONSES_MODEL_STORAGE_VERSION && storedModel !== LEGACY_DEFAULT_RESPONSES_MODEL) {
    return settings
  }

  const configuredDefault = String(defaultModel || "").trim()
  const normalizedDefault = !configuredDefault || configuredDefault === LEGACY_DEFAULT_RESPONSES_MODEL
    ? DEFAULT_RESPONSES_MODEL
    : configuredDefault
  return {
    ...settings,
    responsesModel: storedModel === LEGACY_DEFAULT_RESPONSES_MODEL
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
