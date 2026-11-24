export function filterAdminUsers(users, query = "") {
  const list = Array.isArray(users) ? users : []
  const normalized = String(query || "").trim().toLowerCase()
  if (!normalized) {
    return list
  }
  const numericQuery = normalized.startsWith("#") ? normalized.slice(1) : normalized
  return list.filter((user) => {
    const idText = String(user?.id ?? "")
    const username = String(user?.username || "").toLowerCase()
    const displayName = String(user?.display_name || "").toLowerCase()
    const company = String(user?.company || "").toLowerCase()
    const department = String(user?.department || "").toLowerCase()
    const role = user?.role === "admin" ? "admin 管理员" : "user 普通用户"
    return (
      idText === numericQuery
      || username.includes(normalized)
      || displayName.includes(normalized)
      || company.includes(normalized)
      || department.includes(normalized)
      || role.includes(normalized)
    )
  })
}

export function formatAdminUserOptionLabel(user) {
  if (!user || !user.id) {
    return ""
  }
  const username = String(user.username || `user-${user.id}`)
  const displayName = String(user.display_name || "").trim()
  const namePart = displayName && displayName !== username ? `${displayName} (@${username})` : username
  const orgPart = `${user.company || "未分配"} / ${user.department || "未分配"}`
  return `${namePart} · ${orgPart} (ID #${user.id})`
}

export function countPendingPasswordResets(requests) {
  if (!Array.isArray(requests)) {
    return 0
  }
  return requests.length
}
