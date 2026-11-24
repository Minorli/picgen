export function sanitizeDownloadHref(
  rawHref,
  baseOrigin = (typeof window !== "undefined" && window.location?.origin) || "http://localhost",
) {
  const value = String(rawHref || "").trim()
  if (!value) {
    return ""
  }
  if (
    value.startsWith("/")
    || value.startsWith("files/")
    || value.startsWith("./")
    || value.startsWith("blob:")
  ) {
    if (value.startsWith("//")) {
      return ""
    }
    return value
  }
  if (/^data:image\/(?:png|jpeg|jpg|webp|gif|svg\+xml);base64,/i.test(value)) {
    return value
  }
  try {
    const parsed = new URL(value, baseOrigin)
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href
    }
  } catch {
    return ""
  }
  return ""
}

export function formatHumanDurationMs(durationMs) {
  const ms = Number(durationMs)
  if (!Number.isFinite(ms) || ms < 0) {
    return ""
  }
  const totalSeconds = ms / 1000
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(1)}s`
  }
  const minutes = Math.floor(totalSeconds / 60)
  const restSeconds = Math.round(totalSeconds % 60)
  return restSeconds > 0 ? `${minutes}分 ${restSeconds}秒` : `${minutes}分`
}

export function classifyReviewPanelTone(status, text) {
  const normalizedStatus = String(status || "").trim()
  if (!normalizedStatus || normalizedStatus === "等待检查" || normalizedStatus === "检查中") {
    return "pending"
  }
  if (/^(?:文字通过|已通过|通过|低风险|无需检查)$/.test(normalizedStatus)) {
    return "pass"
  }
  if (/^(?:文字需复核|需复核|高风险|中风险|检查失败|未检查|不通过)$/.test(normalizedStatus)) {
    return "warn"
  }
  const sanitizedText = String(text || "")
    .trim()
    .replace(/缺失或疑似错误[:：]\s*无/g, "")
    .replace(/残留旧文字[:：]\s*无/g, "")
    .replace(/未发现(?:错漏字|错字|漏字)/g, "正常")
  const combined = `${normalizedStatus} ${sanitizedText}`
  if (/高风险|中风险|不通过|不一致|缺失|疑似错误|错字|漏字|失败|未检查/.test(combined)) {
    return "warn"
  }
  if (/通过|正常|低风险|未发现|无需/.test(combined)) {
    return "pass"
  }
  return "pending"
}
