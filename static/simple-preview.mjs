const NON_VISIBLE_FIELD_NAMES = new Set([
  "atmosphere",
  "style",
  "quick_actions",
  "reference_image",
  "image",
  "size",
])

export function resolveSimpleScenarioBadge(recipe) {
  const scene = recipe?.scene_card
  if (!scene) {
    return ""
  }
  const submitKind = scene.submit?.kind || ""
  if (submitKind === "edit") {
    return "保持原图比例"
  }
  if (submitKind === "itinerary") {
    return "智能画幅 · 真实路线"
  }
  if (recipe.id === "travel-poster-premium") {
    return "9:19 手机海报"
  }
  if (recipe.id === "list-ranking") {
    return "9:19 信息长图"
  }
  const hasSizePicker = (scene.fields || []).some((field) => field.kind === "size")
  if (hasSizePicker) {
    return "多画幅可选"
  }
  if (scene.default_size === "1088x2240") {
    return "9:19 竖版"
  }
  if (scene.default_size === "auto") {
    return "智能画幅"
  }
  return String(scene.default_size || "")
}

function summarizeVisibleText(raw) {
  const cleaned = String(raw || "").replace(/\s+/g, " ").trim()
  if (!cleaned) {
    return ""
  }
  return cleaned.length > 56 ? `${cleaned.slice(0, 56)}…` : cleaned
}

export function extractSimpleVisibleTextItems(recipe, values = {}, maxItems = 8) {
  const fields = Array.isArray(recipe?.scene_card?.fields) ? recipe.scene_card.fields : []
  if (!fields.length) {
    return []
  }
  const items = []
  for (const field of fields) {
    if (!field?.name || NON_VISIBLE_FIELD_NAMES.has(field.name)) {
      continue
    }
    if (field.kind === "image" || field.kind === "size" || field.kind === "chips") {
      continue
    }
    const rawValue = values?.[field.name]
    if (field.kind === "list") {
      const listEntries = (Array.isArray(rawValue) ? rawValue : [])
        .map((entry) => summarizeVisibleText(entry))
        .filter(Boolean)
      listEntries.forEach((entry, index) => {
        items.push({
          label: listEntries.length > 1 ? `${field.label} ${index + 1}` : field.label,
          text: entry,
        })
      })
      continue
    }
    if (field.kind === "textarea") {
      const lines = String(rawValue || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
      if (!lines.length) {
        continue
      }
      if (field.name === "itinerary") {
        lines.slice(0, 4).forEach((line, index) => {
          items.push({
            label: `行程 ${index + 1}`,
            text: summarizeVisibleText(line),
          })
        })
        if (lines.length > 4) {
          items.push({
            label: "行程共",
            text: `${lines.length} 行记录`,
          })
        }
      } else {
        items.push({
          label: field.label,
          text: summarizeVisibleText(lines.join(" · ")),
        })
      }
      continue
    }
    const single = summarizeVisibleText(rawValue)
    if (single) {
      items.push({
        label: field.label,
        text: single,
      })
    }
  }
  if (items.length <= maxItems) {
    return items
  }
  const extraCount = items.length - maxItems
  return [
    ...items.slice(0, maxItems),
    { label: "其余文案", text: `共 +${extraCount} 项` },
  ]
}
