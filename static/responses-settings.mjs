export const DEFAULT_RESPONSES_MODEL = "gpt-5.6-sol"
const LEGACY_DEFAULT_RESPONSES_MODEL = "gpt-5.5"
export const RESPONSES_MODEL_STORAGE_VERSION = 4

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
