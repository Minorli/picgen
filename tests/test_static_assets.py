from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_legacy_responses_model_storage_is_migrated_once() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    settings_js = (ROOT_DIR / "static" / "responses-settings.mjs").read_text(encoding="utf-8")

    assert 'const DEPRECATED_RESPONSES_MODELS = new Set(["gpt-5.4"])' in app_js
    assert 'from "./responses-settings.mjs?v=0.1.67"' in app_js
    assert 'const LEGACY_DEFAULT_RESPONSES_MODEL = "gpt-5.5"' in settings_js
    assert "const RESPONSES_MODEL_STORAGE_VERSION = 4" in settings_js
    assert "function migrateStoredResponsesSettings" in settings_js
    assert "const RESPONSES_REASONING_STORAGE_VERSION = 1" in settings_js
    assert "function migrateStoredResponsesReasoningSettings" in settings_js
    assert app_js.count("responsesModelStorageVersion: RESPONSES_MODEL_STORAGE_VERSION") >= 2
    assert app_js.count("migrateStoredResponsesSettings(") >= 2
    assert app_js.count("responsesReasoningStorageVersion: RESPONSES_REASONING_STORAGE_VERSION") >= 2
    assert app_js.count("migrateStoredResponsesReasoningSettings(") >= 2
    assert "const currentResponsesModel = normalizeResponsesModel(refs.responsesModelInput.value)" in app_js
    assert "responses_model_storage_version: RESPONSES_MODEL_STORAGE_VERSION" in app_js


def test_logo_overlay_uses_uploaded_asset_without_ai_guidance() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    placement_js = (ROOT_DIR / "static" / "logo-placement.mjs").read_text(encoding="utf-8")
    logo_png = ROOT_DIR / "static" / "6renyou.png"
    logo_bytes = logo_png.read_bytes()
    assert logo_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert logo_bytes[12:16] == b"IHDR"
    assert logo_bytes[25] == 6
    assert 'const COMPANY_LOGO_URL = "6renyou.png"' in app_js
    assert "composeLogoOverlayForCandidates" in app_js
    assert "createOfficialLogoCanvas" in app_js
    assert 'from "./logo-placement.mjs?v=0.1.67"' in app_js
    assert "chooseLogoPlacement" in app_js
    assert "calculateLogoPlacementScore" in app_js
    assert "calculateOfficialLogoPixelMatch" in app_js
    assert "scaleLogoDetectionPlacements" in app_js
    assert "createLogoPreservationDiagnostic" in app_js
    assert "findExistingOfficialLogo" in app_js
    assert "composed.preserved" in app_js
    assert "已有官方 LOGO，保留原位置且不重复贴入" in app_js
    assert "logo_preservation" in app_js
    assert "match_rate" in app_js
    assert 'basis: "official_logo_pixel_match"' in (ROOT_DIR / "static" / "logo-placement.mjs").read_text(
        encoding="utf-8"
    )
    compose = app_js[
        app_js.index("async function composeLogoOverlayForCandidates") :
        app_js.index("async function downscaleDataUrlForRisk")
    ]
    preserved_branch = compose.index("if (composed.preserved)")
    persist_call = compose.index("persistFinalLogoImage")
    assert preserved_branch < persist_call
    assert "continue" in compose[preserved_branch:persist_call]
    assert "logo_preserved: true" in compose[preserved_branch:persist_call]
    storage_copy = app_js[
        app_js.index("function updateSelectedCandidateStorageText") :
        app_js.index("function updateResultActionSurface")
    ]
    assert "selectedCandidate.logo_preserved" in storage_copy
    assert "expandLogoSafetyRegion" in placement_js
    assert "calculateRegionTextEdgePenalty" in placement_js
    assert "hasTransparentLogoBackground" in app_js
    assert "resizeCanvasHighQuality" in app_js
    assert "applyLogoOverlayToDataUrl" in app_js
    assert "withLogoLayoutPrompt" in app_js
    assert "官方透明 PNG 原样贴入" in app_js
    assert "图标、字体、颜色和比例均不得改动" in app_js
    assert "LOGO 位置附近保留自然干净背景" in app_js
    assert "不要绘制 LOGO 占位框" in app_js
    assert "白色底板" in app_js
    assert "logo_text_color" in app_js
    assert 'textColor: "original"' in app_js
    assert "drawLogoContrastMatte" not in app_js
    assert "soft-warm-matte" not in app_js
    assert "rgba(255, 244, 218" not in app_js
    assert "contrastMatte" not in app_js
    assert "ctx.drawImage(scaledLogoCanvas, placement.x, placement.y)" in app_js
    assert "官方 LOGO 缺少透明背景" in app_js
    assert 'imageSmoothingQuality = "high"' in app_js
    assert "chooseLogoTextColorForPlacement" not in app_js
    assert "recolorLogoTextPixels" not in app_js
    assert "removeWhiteMatteFromLogoPixels" not in app_js
    assert "COMPANY_LOGO_WHITE_CUTOFF" not in app_js
    assert "COMPANY_LOGO_TEXT_RECOLOR" not in app_js
    assert "主图偏深时，LOGO 字体只能使用白色" not in app_js
    assert "主图偏浅时，LOGO 字体只能使用黑色" not in app_js
    assert "logoRequested ? 1 : getGenerateSampleCount()" not in app_js
    assert "6renyou.png.b64" not in app_js
    assert "AI 合成要求" not in app_js
    assert "作为 AI 参考图提交" not in app_js
    assert "buildCompanyLogoReferencePart" not in app_js
    assert "appendCompanyLogoReference" not in app_js


def test_generate_sample_count_ui_is_not_disabled_by_logo_overlay() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="generateSampleCountInput"' in index_html
    assert 'max="3"' in index_html
    assert "getGenerateSampleCount" in app_js
    assert "生成数量必须在 1 到 3 之间" in app_js
    assert "referenceImages.length ? 1 : getGenerateSampleCount()" in app_js
    assert "logoRequested || hasReference || isVariant" not in app_js
    assert "sample_count: sampleCount" in app_js


def test_model_controls_are_admin_only_and_generation_uses_unified_endpoint() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    generate_controls = index_html.split('<section class="studio-block model-block">', 1)[1].split(
        "</section>", 1
    )[0]
    edit_controls = index_html.split('<section id="editPanel"', 1)[1].split(
        '<section id="itineraryPanel"', 1
    )[0]
    connection_settings = index_html.split('<section id="connectionSettings"', 1)[1].split(
        '<div class="feedback-strip">', 1
    )[0]

    assert 'id="generateModelInput"' not in generate_controls
    assert 'id="editModelInput"' not in edit_controls
    assert 'class="studio-card settings-drawer hidden"' in index_html
    assert 'id="connectionSettingsLink"' in index_html
    assert 'id="generateModelInput"' in connection_settings
    assert 'id="editModelInput"' in connection_settings
    assert 'id="responsesModelInput"' in connection_settings
    assert 'id="responsesReasoningEffortSelect"' in connection_settings
    assert '<option value="" selected>服务端默认</option>' in connection_settings
    assert '<option value="xhigh">xhigh</option>' in connection_settings

    assert 'postJSON("api/generate"' not in app_js
    assert 'postJSON("api/edit"' not in app_js
    assert 'postJSON("api/responses-image"' not in app_js
    assert app_js.count('postJSON("api/image-jobs"') >= 3
    assert "imageJobAdvancedOptions" in app_js
    assert 'refs.connectionSettings?.classList.toggle("hidden", !canManageExecution)' in app_js
    assert 'refs.connectionSettingsLink?.classList.toggle("hidden", !canManageExecution)' in app_js
    assert 'state.serverConfig?.allow_anonymous_execution_overrides === true' in app_js
    assert "state.serverConfig?.default_responses_reasoning_effort" in app_js
    assert "reasoning_effort: settings.responsesReasoningEffort || undefined" in app_js
    assert 'refs.debugOutput?.closest("details")?.classList.toggle("hidden", !canManageExecution)' in app_js
    assert 'refs.rawResponseOutput?.closest("details")?.classList.toggle("hidden", !canManageExecution)' in app_js
    assert "job.transport" in app_js
    assert "job.model" in app_js
    assert "job.reasoning_effort" in app_js


def test_mobile_user_identity_stays_on_one_line() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".topbar-tools {\n    width: 100%;" in styles_css
    assert ".user-pill {\n    flex: 0 1 180px;\n    min-width: 150px;" in styles_css
    assert ".user-pill strong {\n    white-space: nowrap;" in styles_css


def test_auth_overlay_supports_open_registration_and_cookie_sessions() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert '<body class="auth-gate">' in index_html
    assert 'id="authOverlay"' in index_html
    assert 'class="auth-page"' in index_html
    assert 'id="loginAuthButton"' in index_html
    assert 'id="registerAuthButton"' in index_html
    assert 'id="authCompanyInput"' in index_html
    assert 'id="authDepartmentInput"' in index_html
    assert '<option value="6renyou">6renyou</option>' in index_html
    assert '<option value="PD &amp; OPS">PD &amp; OPS</option>' in index_html
    assert "注册" in index_html
    assert 'id="logoutButton"' in index_html
    assert 'id="changePasswordButton"' in index_html
    assert 'id="changePasswordModal"' in index_html
    assert 'id="changePasswordForm"' in index_html
    assert 'id="userUsageSummary"' in index_html
    assert 'id="userImageStats"' in index_html
    assert 'id="adminPanel"' in index_html
    assert 'id="adminCreateUserForm"' in index_html
    assert 'id="adminUsersList"' in index_html
    assert "body.auth-gate .desktop-shell" in styles_css
    assert ".admin-panel" in styles_css
    assert "/api/auth/login" in app_js
    assert "/api/auth/register" in app_js
    assert "/api/auth/logout" in app_js
    assert "authCompanyInput" in app_js
    assert "authDepartmentInput" in app_js
    assert "/api/me/password" in app_js
    assert "/api/admin/users" in app_js
    assert "/api/me" in app_js
    assert "/api/usage" in app_js
    assert "/api/image-stats" in app_js
    assert "originalSavedUrl" in app_js
    assert "sourceImageIdentityFields" in app_js
    assert 'credentials: "same-origin"' in app_js
    assert "scopedStorageKey" in app_js
    assert "settingsStorageKey()" in app_js
    assert "historyStorageKey()" in app_js
    assert "workspaceStorageKey()" in app_js
    assert "enterAuthGate(" in app_js
    assert "enterAppShell()" in app_js
    assert "localStorage.setItem('token'" not in app_js
    assert 'localStorage.setItem("token"' not in app_js
    assert "submitChangePassword" in app_js
    assert ".change-password-dialog" in styles_css


def test_auth_login_button_shows_validation_feedback_before_native_submit_block() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert '<form id="authForm" class="auth-form" novalidate>' in index_html
    assert "function validateAuthFormInputs()" in app_js
    assert "用户名至少需要 2 个字符。" in app_js
    assert "密码至少需要 8 位。" in app_js
    assert 'refs.loginAuthButton?.addEventListener("click", validateAuthFormInputs)' in app_js
    assert "if (!validateAuthFormInputs()) {" in app_js


def test_image_quality_defaults_to_high_without_unsupported_xhigh() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert '<option value="high" selected>High</option>' in index_html
    assert 'refs.qualitySelect.value = forms.quality || "high"' in app_js
    assert 'quality: refs.qualitySelect.value || "high"' in app_js
    assert 'refs.qualitySelect.value = snapshot.quality || "high"' in app_js
    quality_select = index_html.split('<select id="qualitySelect">', 1)[1].split("</select>", 1)[0]
    assert 'value="xhigh"' not in quality_select
    assert 'refs.qualitySelect.value = forms.quality || "xhigh"' not in app_js
    assert 'quality: refs.qualitySelect.value || "xhigh"' not in app_js


def test_result_preview_zoom_and_feedback_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="previewZoomInButton"' in index_html
    assert 'id="previewZoomOutButton"' in index_html
    assert 'id="previewZoomResetButton"' in index_html
    assert 'id="openResultPreviewButton"' not in index_html
    assert "openResultPreviewButton" not in app_js
    assert "applyPreviewZoom" in app_js
    assert "previewZoom" in app_js
    assert 'draggable="false"' in index_html
    assert "event.preventDefault()" in app_js
    assert "setPointerCapture(event.pointerId)" in app_js
    assert "preview-modal-single-wrap" in styles_css
    assert "cursor: grab" in styles_css

    assert 'id="resultFeedbackPanel"' in index_html
    assert 'data-rating="good"' in index_html
    assert 'data-rating="ok"' in index_html
    assert 'data-rating="bad"' in index_html
    assert 'id="feedbackReasonPanel"' in index_html
    assert "/api/feedback" in app_js
    assert "/api/feedback/summary" in app_js
    assert "submitResultFeedback" in app_js
    assert "refreshFeedbackSummary" in app_js


def test_generation_progress_explains_retry_attempts_inside_preview() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert "UPSTREAM_ATTEMPT_PLAN" not in app_js
    assert "progressAttemptInfo" not in app_js
    assert "第 1 次尝试" not in app_js
    assert "第 2 次尝试" not in app_js
    assert "第 3 次尝试" not in app_js
    assert "等待上游响应中" in app_js
    assert "后台如遇临时 502/503/504 会自动重试" in app_js
    assert "第几次重试以最终错误详情或服务端日志为准" in app_js
    assert "已多次尝试仍未成功" in app_js
    assert "setPendingResultFailure" in app_js
    assert "refs.resultPreviewEmpty.textContent = safeMessage" in app_js
    assert 'refs.resultPreviewLabel.textContent = "生成失败"' in app_js
    # 结果占位元素的类是 empty-placeholder；旧选择器 .preview-empty.failure
    # 匹配不到任何节点，失败态从未变红过。
    assert ".empty-placeholder.failure" in styles_css


def test_copyright_risk_state_survives_workspace_restore() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "copyrightRisk: state.copyrightRisk" in app_js
    assert 'normalizeRestoredReviewState(result.copyrightRisk, "copyright")' in app_js
    assert "restoreCopyrightRiskPanel" in app_js
    assert "scheduleWorkspacePersist()" in app_js


def test_bug_reports_and_result_sharing_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="bugReportButton"' in index_html
    assert 'id="bugReportModal"' in index_html
    assert 'id="bugReportForm"' in index_html
    assert "/api/bug-reports" in app_js
    assert "submitBugReport" in app_js
    assert "refreshBugReports" in app_js
    assert ".bug-report-dialog" in styles_css

    assert 'id="shareResultPanel"' in index_html
    assert 'id="shareRecipientSearchInput"' in index_html
    assert 'id="shareRecipientsList"' in index_html
    assert 'id="sharedResultsList"' in index_html
    assert "/api/users" in app_js
    assert "/api/shares" in app_js
    assert "/api/shares/inbox" in app_js
    assert "api/final-images" in app_js
    assert "persistFinalLogoImage" in app_js
    assert "setDownloadPendingLogo" in app_js
    assert "成品保存中" in app_js
    assert "submitShareResult" in app_js
    assert "openSharedResult" in app_js
    assert ".share-result-panel" in styles_css
    assert ".share-recipient-search" in styles_css
    assert ".shared-result-item" in styles_css


def test_share_success_status_survives_recipient_list_reset() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    submit_share = app_js[
        app_js.index("async function submitShareResult") : app_js.index("function renderSharedResults")
    ]

    reset_index = submit_share.index("renderShareRecipientOptions()")
    success_index = submit_share.index("setShareStatus(`已分享给 ${count} 人`)")
    assert reset_index < success_index


def test_simple_mode_exposes_shared_results_inbox() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="simpleSharedResultsSection"' in index_html
    assert 'id="simpleSharedResultsList"' in index_html
    assert 'id="simpleSharedResultsEmpty"' in index_html
    assert 'id="simpleRefreshSharedResultsButton"' in index_html
    assert index_html.index('id="simpleSharedResultsSection"') < index_html.index('id="simpleGallerySection"')
    simple_shared_html = index_html[
        index_html.index('id="simpleSharedResultsSection"') : index_html.index('id="simpleGallerySection"')
    ]
    assert 'aria-live=' not in simple_shared_html

    refs = app_js[app_js.index("const refs = {") : app_js.index("function loadJSON")]
    assert 'simpleSharedResultsList: document.querySelector("#simpleSharedResultsList")' in refs
    assert 'simpleSharedResultsEmpty: document.querySelector("#simpleSharedResultsEmpty")' in refs
    assert 'simpleRefreshSharedResultsButton: document.querySelector("#simpleRefreshSharedResultsButton")' in refs
    assert 'simpleSharedResultsSection: document.querySelector("#simpleSharedResultsSection")' in refs

    renderer = app_js[
        app_js.index("function renderSharedResults") : app_js.index("async function refreshSharedResults")
    ]
    assert "refs.simpleSharedResultsList" in renderer
    assert "refs.simpleSharedResultsEmpty" in renderer

    bindings = app_js[app_js.index("function bindEvents()") : app_js.index("async function init()")]
    assert "refs.simpleRefreshSharedResultsButton?.addEventListener(\"click\", refreshSharedResults)" in bindings
    assert "bindSharedResultsList(refs.simpleSharedResultsList)" in bindings

    assert ".simple-shared-results-list" in styles_css
    assert ".simple-shared-result-item" in styles_css
    shared_list_css = styles_css[
        styles_css.index(".simple-shared-results-list {") : styles_css.index(".simple-shared-result-item {")
    ]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in shared_list_css
    assert ".simple-shared-results-list > .empty-history" in styles_css
    assert "grid-column: 1 / -1;" in styles_css[
        styles_css.index(".simple-shared-results-list > .empty-history") :
        styles_css.index(".simple-shared-result-item {")
    ]
    mobile_css = styles_css[styles_css.index("@media (max-width: 820px)") :]
    assert ".simple-shared-results-list {\n    grid-template-columns: minmax(0, 1fr);" in mobile_css


def test_received_share_actions_cannot_rerun_or_complete_onboarding() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    feedback_visibility = app_js[
        app_js.index("function updateFeedbackPanelVisibility") :
        app_js.index("function buildFeedbackPayload")
    ]
    assert "currentResultIsShared()" in feedback_visibility

    bad_feedback = app_js[
        app_js.index("async function submitBadFeedbackReason") :
        app_js.index("async function regenerateFromBadFeedback")
    ]
    assert "!currentResultIsShared()" in bad_feedback

    open_share = app_js[
        app_js.index("function openSharedResult") : app_js.index("function bindSharedResultsList")
    ]
    assert "state.isBusy" in open_share
    assert "updateFeedbackPanelVisibility()" in open_share
    assert "updateResultActionSurface()" in open_share
    assert "shared_generated_image_id" in open_share
    assert "\n    generated_image_id: share.generated_image_id" not in open_share

    bindings = app_js[app_js.index("function bindEvents()") : app_js.index("async function init()")]
    download_binding = bindings[
        bindings.index('refs.downloadButton?.addEventListener("click"') :
        bindings.index('document.addEventListener("click"')
    ]
    assert "!currentResultIsShared()" in download_binding

    simple_result_surface = app_js[
        app_js.index("function updateSimpleResultSurface") : app_js.index("function setResultSizeWarning")
    ]
    assert "currentResultIsShared()" in simple_result_surface

    anonymous = app_js[
        app_js.index("function applyAnonymousShellChrome") : app_js.index("function renderAvatarElement")
    ]
    assert 'refs.simpleSharedResultsSection?.classList.add("hidden")' in anonymous


def test_result_displays_and_restores_size_mismatch_warning() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="resultSizeWarning"' in index_html
    assert 'id="resultSizeWarningText"' in index_html
    assert ".result-size-warning:not(.hidden)" in styles_css
    assert "function setResultSizeWarning" in app_js
    assert "setResultSizeWarning(sizeMismatchMessage)" in app_js
    assert "sizeWarningText: refs.resultSizeWarningText" in app_js
    assert 'setResultSizeWarning(result.sizeWarningText || "")' in app_js
    assert "setError(sizeMismatchMessage)" not in app_js


def test_result_previews_show_the_complete_image_without_grid_clipping() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    preview_css = styles_css[
        styles_css.index(".preview-frame img {") : styles_css.index(".preview-frame img.visible")
    ]
    assert "min-width: 0;" in preview_css
    assert "min-height: 0;" in preview_css
    assert "object-fit: contain;" in preview_css

    candidate_css = styles_css[
        styles_css.index(".candidate-button img {") : styles_css.index(".candidate-button span {")
    ]
    assert "object-fit: contain;" in candidate_css
    assert "object-fit: cover;" not in candidate_css


def test_gallery_favorite_checkbox_keeps_label_close() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    toggle_css = styles_css[
        styles_css.index(".gallery-favorite-toggle input {") :
        styles_css.index(".gallery-tags-field {")
    ]
    assert "width: 16px;" in toggle_css
    assert "height: 16px;" in toggle_css
    assert "min-height: 0;" in toggle_css
    assert "flex: 0 0 auto;" in toggle_css


def test_size_mismatch_warning_prefers_server_summary_for_mixed_candidates() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function parseSizeValue") : app_js.index("function setGenerateSize")
    ]
    expression = """
const serverSummary = "上游返回尺寸为 1024x1536，与请求尺寸 1024x1024 不一致。图片已按上游原始返回保存，本地没有缩放。";
console.log(JSON.stringify({
  exact: resolveSizeMismatchWarning(
    { size: "1024x1024", size_mismatch: false },
    "1024x1024",
  ),
  observed: resolveSizeMismatchWarning(
    { size: "1024x1024", size_mismatch: false },
    "1024x1536",
  ),
  mixed: resolveSizeMismatchWarning(
    { size: "1024x1024", size_mismatch: true, size_mismatch_message: serverSummary },
    "1024x1024",
  ),
  mixedWithoutMessage: resolveSizeMismatchWarning(
    { size: "1024x1024", size_mismatch: true },
    "1024x1024",
  ),
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", f"{function_source}\n{expression}"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["exact"] == ""
    assert "1024x1536" in result["observed"]
    assert result["mixed"] == (
        "上游返回尺寸为 1024x1536，与请求尺寸 1024x1024 不一致。"
        "图片已按上游原始返回保存，本地没有缩放。"
    )
    assert "部分候选图" in result["mixedWithoutMessage"]
    assert "1024x1024" in result["mixedWithoutMessage"]
    assert "没有缩放" in result["mixedWithoutMessage"]


def test_gallery_library_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="galleryList"' in index_html
    assert 'id="gallerySearchInput"' in index_html
    assert 'id="galleryFavoriteOnlyInput"' in index_html
    assert 'id="galleryEditorPanel"' in index_html
    assert 'id="galleryFavoriteInput"' in index_html
    assert 'id="galleryTagsInput"' in index_html
    assert 'id="saveGalleryMetaButton"' in index_html
    assert "/api/gallery" in app_js
    assert "/api/gallery/${generatedImageId}" in app_js
    assert "refreshGallery" in app_js
    assert "renderGalleryItems" in app_js
    assert "openGalleryItem" in app_js
    assert "saveGalleryMeta" in app_js
    assert "setGalleryEditorMeta" in app_js
    assert "galleryItemToAsset" in app_js
    assert ".gallery-item" in styles_css
    assert ".gallery-editor-panel" in styles_css


def test_generation_task_center_and_lineage_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="refreshJobsButton"' in index_html
    assert 'id="jobCenterList"' in index_html
    assert 'id="jobCenterEmpty"' in index_html
    assert "/api/jobs?limit=20" in app_js
    assert "/api/generated-images/${encodeURIComponent(generatedImageId)}" in app_js
    assert "renderGenerationJobs" in app_js
    assert "openGeneratedImageDetail" in app_js
    assert "openGalleryLikeImage" in app_js
    assert "void refreshGenerationJobs()" in app_js
    assert ".job-center-item" in styles_css
    assert ".job-center-thumb" in styles_css


def test_image_version_history_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="showVersionsButton"' in index_html
    assert 'id="versionHistoryPanel"' in index_html
    assert 'id="versionHistoryList"' in index_html
    assert "/api/generated-images/${encodeURIComponent(generatedImageId)}/versions" in app_js
    assert "showImageVersions" in app_js
    assert "renderImageVersions" in app_js
    assert "source_generated_image_id" in app_js
    assert ".version-history-panel" in styles_css
    assert ".version-history-item" in styles_css


def test_logo_final_images_use_original_asset_for_followup_model_input() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function modelInputAssetForLogoWorkflow(asset)" in app_js
    helper_start = app_js.index("function modelInputAssetForLogoWorkflow(asset)")
    helper_end = app_js.index("function getAssetDisplaySrc", helper_start)
    helper = app_js[helper_start:helper_end]
    assert "!asset?.logoOverlayApplied" in helper
    assert "asset.originalSavedUrl" in helper
    assert "asset.originalSavedPath || asset.savedPath || \"\"" in helper
    assert "return getAssetDisplaySrc(source) ? source : asset" in helper

    assert "modelInputAssetForLogoWorkflow(state.lastResultImage)" in app_js
    assert "modelInputAssetForLogoWorkflow(state.editImage)" in app_js
    assert "modelInputAssetForLogoWorkflow(state.lastResultImage, logoRequested)" not in app_js
    assert "modelInputAssetForLogoWorkflow(state.editImage, logoRequested)" not in app_js


def test_continue_edit_source_keeps_generation_lineage_and_uses_defined_base_asset_flag() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    use_start = app_js.index("function useLastResultAsEditSource")
    use_end = app_js.index("function setMode", use_start)
    use_block = app_js[use_start:use_end]
    assert "const usesBaseImage = inputAsset !== state.lastResultImage" in use_block
    assert "generatedImageId: state.lastResultImage.generatedImageId" in use_block
    assert "sourceGeneratedImageId: state.lastResultImage.sourceGeneratedImageId || null" in use_block

    result_start = app_js.index("async function setResult")
    result_end = app_js.index("const metaLabel =", result_start)
    result_block = app_js[result_start:result_end]
    assert "const followupSource = modelInputAssetForLogoWorkflow(state.lastResultImage)" in result_block
    assert "generatedImageId: state.lastResultImage.generatedImageId" in result_block
    assert "state.editImage = cloneImageAsset(followupSource" in result_block
    assert "sourceGeneratedImageId: state.lastResultImage.sourceGeneratedImageId || null" in result_block


def test_edit_requests_send_selected_size_and_quality_for_strict_poster_edits() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    submit_start = app_js.index("async function submitEdit")
    submit_end = app_js.index("function clearGenerateForm", submit_start)
    submit_block = app_js[submit_start:submit_end]
    assert "size = getGenerateSize()" in submit_block
    assert "imageOptions = getOpenAIImageOptions()" in submit_block
    assert 'postJSON("api/image-jobs", requestPayload' in submit_block
    assert "shouldUseResponsesForSelectedSize" not in submit_block
    assert 'postJSON("api/responses-image"' not in submit_block
    assert 'postJSON("api/edit"' not in submit_block
    assert "size," in submit_block
    assert "...imageOptions" in submit_block
    assert "mode: \"edit\"" in submit_block


def test_reference_generation_keeps_source_lineage_when_reference_is_generated_asset() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    submit_start = app_js.index("async function submitGenerate")
    reference_start = app_js.index("const requestParts = referenceParts", submit_start)
    reference_end = app_js.index("      await setResult({", reference_start)
    reference_block = app_js[reference_start:reference_end]
    assert "const referenceLineageSource = requestSources.at(-1)" in reference_block
    assert "const sourceGeneratedImageId = referenceLineageSource?.generatedImageId || null" in reference_block
    assert "source_generated_image_id: sourceGeneratedImageId" in reference_block
    assert "...sourceImageIdentityFields(referenceLineageSource)" in reference_block


def test_image_centric_workspace_actions_and_brand_download_gateway_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="resultHoverActions" class="result-hover-actions hidden"' in index_html
    assert 'id="inspectLongImageButton"' in index_html
    assert 'id="downloadOriginalButton"' in index_html
    assert "下载带 6 人游 LOGO 成品" in index_html
    assert "原始底图" in index_html
    assert 'openPreview("result", "cinema")' in app_js
    assert "setDownloadPendingLogo" in app_js
    assert "downloadOriginalButton" in app_js
    assert "updateResultActionSurface" in app_js
    assert "download-ready-logo" in styles_css
    assert ".result-hover-actions" in styles_css
    assert ".result-frame:hover .result-hover-actions" in styles_css


def test_progress_overlay_and_my_favorites_are_visible_workflows() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="generationOverlaySteps"' in index_html
    assert "准备请求" in index_html
    assert "等待上游" in index_html
    assert "保存成品" in index_html
    assert "renderGenerationOverlaySteps" in app_js
    assert "updateGenerationOverlay" in app_js
    assert "后台如遇临时错误会自动重试" in app_js
    assert 'id="teamInspirationFeedButton"' in index_html
    assert "我的收藏" in index_html
    assert "团队灵感流" not in index_html
    assert "openTeamInspirationFeed" in app_js
    assert ".generation-overlay-steps" in styles_css
    assert ".team-feed-entry" in styles_css


def test_my_favorites_summary_tracks_the_favorite_only_filter() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function syncMyFavoritesSummary") : app_js.index("function openTeamInspirationFeed")
    ]
    script = f"""
let hidden = null;
const refs = {{
  galleryFavoriteOnlyInput: {{ checked: true }},
  teamInspirationFeed: {{ classList: {{ toggle: (name, value) => {{ hidden = value; }} }} }},
}};
{function_source}
syncMyFavoritesSummary();
const favoriteOnlyHidden = hidden;
refs.galleryFavoriteOnlyInput.checked = false;
syncMyFavoritesSummary();
console.log(JSON.stringify({{ favoriteOnlyHidden, allWorksHidden: hidden }}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "favoriteOnlyHidden": False,
        "allWorksHidden": True,
    }
    assert "syncMyFavoritesSummary()\n    void refreshGallery()" in app_js


def test_mobile_rail_sections_are_collapsible() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'data-rail-toggle="history"' in index_html
    assert 'data-rail-toggle="shared"' in index_html
    assert 'data-rail-toggle="gallery"' in index_html
    assert "toggleRailSection" in app_js
    assert "rail-section.collapsed" in styles_css
    assert "@media (max-width: 820px)" in styles_css


def test_itinerary_map_mode_renders_real_route_map_with_logo_safe_area() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    detailed_template = app_js.split("const DETAILED_ITINERARY_TEMPLATE = [", 1)[1].split(
        '].join("\\n")',
        1,
    )[0]

    assert (
        index_html.index('data-mode="generate">海报生成')
        < index_html.index('data-mode="itinerary">行程路线')
        < index_html.index('data-mode="edit">编辑')
    )
    assert 'data-mode="itinerary"' in index_html
    assert 'id="itineraryTab"' in index_html
    assert 'id="itineraryPanel"' in index_html
    assert 'id="itineraryDescriptionInput"' in index_html
    assert 'id="renderItineraryMapButton"' in index_html
    assert "行程路线" in index_html
    assert "粘贴客户行程" in index_html
    assert "准确路线图" in index_html
    assert "生成准确路线图" in index_html
    assert "AI 路线图" not in index_html
    assert "AI 生成行程路线" not in index_html
    assert 'id="copyItineraryTemplateButton"' in index_html
    assert 'id="applyItineraryTemplateButton"' in index_html
    assert "复制精细模板" in index_html
    assert "套用精细模板" in index_html
    assert "系统会自动定位地点" in index_html
    assert "地点不明确时会提示补充更完整名称" in index_html
    assert "请补充 @坐标 行" not in index_html
    assert "未补充坐标时不会生成伪精确地图" not in index_html
    assert "不要求用户提供经纬度" not in index_html
    assert "官方 LOGO 安全区" in index_html
    assert 'value="定制旅行路线图"' in index_html
    assert (
        'id="itinerarySubtitleInput" type="text" maxlength="160" placeholder="例如：5/12 - 5/24" required' in index_html
    )
    assert 'id="itineraryTitleInput" type="text" maxlength="120" value="新疆深度定制旅行"' not in index_html
    assert 'value="comic"' in index_html
    assert "漫画路线图" in index_html
    assert "程序覆盖路线、日期、文字和官方 LOGO" in index_html
    assert '<option value="auto" selected>自动比例（按真实路线选择）</option>' in index_html
    assert 'class="itinerary-size-hint"' in index_html
    assert ".itinerary-size-hint" in styles_css
    assert index_html.index('<option value="auto" selected>自动比例（按真实路线选择）</option>') < index_html.index(
        '<option value="1792x1792">方图 1792 x 1792</option>'
    )
    assert index_html.index('<option value="1792x1792">方图 1792 x 1792</option>') < index_html.index(
        '<option value="1088x2240">6 人游竖版 1088 x 2240</option>'
    )
    assert "系统会按真实坐标自动选择竖版、横版或方图" in index_html
    assert 'value="1088x2240"' in index_html
    assert 'value="1792x1792"' in index_html
    assert 'value="1920x1088"' in index_html
    assert "抵达乌鲁木齐" not in index_html
    assert "赛里木湖" not in index_html
    assert "喀拉峻" not in index_html
    assert "库尔德宁" not in index_html
    assert "Super8" not in index_html
    assert "喀什古城万斐国际酒店" not in index_html
    assert "1800x1800" not in index_html
    assert "1920x1080" not in index_html

    assert 'itineraryPanel: document.querySelector("#itineraryPanel")' in app_js
    assert 'itineraryDescriptionInput: document.querySelector("#itineraryDescriptionInput")' in app_js
    assert "buildAIItineraryMapPrompt" not in app_js
    assert "parseItineraryCoordinateStops" in app_js
    assert "parseItineraryTextStops" in app_js
    assert "isItineraryInstructionSection" in app_js
    assert "isItineraryInstructionRow" in app_js
    assert "cleanItineraryStopName" in app_js
    assert 'postJSON("api/itinerary-map/render"' in app_js
    assert "itinerary_coordinates_required" in app_js
    assert "isCompleteItineraryPrompt" not in app_js
    assert "normalizeCompleteItineraryPrompt" not in app_js
    assert "ITINERARY_GEOGRAPHY_GUARD" not in app_js
    assert "stripCodeFence" not in app_js
    assert "submitAIItineraryMap" in app_js
    assert "AI_ITINERARY_EXAMPLE" in app_js
    assert "DETAILED_ITINERARY_TEMPLATE" in app_js
    assert "DEFAULT_ITINERARY_TITLE" in app_js
    assert "SANITIZED_ITINERARY_EXAMPLE_TITLE" in app_js
    assert "XINJIANG_ITINERARY_EXAMPLE_TITLE" not in app_js
    assert "目的地/主题：请替换为本次路线目的地" in detailed_template
    assert "出行日期：请替换为本次真实日期范围" in detailed_template
    assert "地图标题建议：请替换为客户可见标题" in detailed_template
    assert "地点与地理校验（请按本次目的地改写）" in detailed_template
    assert "不要保留示例地名" in detailed_template
    assert '"- 目的地/主题：新疆深度定制旅行"' not in detailed_template
    assert '"- 地图标题建议：新疆游"' not in detailed_template
    assert "赛里木湖 AC 万豪" not in detailed_template
    assert "喀什古城万斐国际酒店" not in detailed_template
    assert "真实客户姓名" not in app_js
    assert "真实订单" not in app_js
    assert "真实酒店" not in app_js
    assert "行程基础信息" in app_js
    assert "逐日行程" in app_js
    assert "程序坐标（用于准确落点，至少填写两个）" in app_js
    assert "@坐标: D1,城市/地点 A,纬度,经度,交通方式" in app_js
    assert "地点与地理校验" in app_js
    assert "copyDetailedItineraryTemplate" in app_js
    assert "applyDetailedItineraryTemplate" in app_js
    assert "shouldUseXinjiangRouteGuard" not in app_js
    assert "xinjiangRouteGuardPrompt" not in app_js
    assert "drawItineraryLogoSafeArea" not in app_js
    assert "withLogoLayoutPrompt(aiPrompt, logoRequested)" not in app_js
    assert "库尔德宁" not in app_js
    assert "喀拉峻" not in app_js
    assert "伊宁" not in app_js
    assert "琼库什台" not in app_js
    assert "赛里木湖" not in app_js
    assert "喀什" not in app_js
    assert "日期必须逐日出现" in app_js
    assert "交通工具图标" in app_js
    assert "水彩漫画路线图" in app_js
    assert "红色粗路线" in app_js
    assert "圆点站位" in app_js
    assert "地标小插画" in app_js
    assert "漫画风格不能牺牲地理真实性" in app_js
    assert "日期、距离、交通方式、酒店和核心景区不能省略" in app_js
    assert "template-route.jpg" not in app_js
    assert "已验证满意样张的稳定风格" not in app_js
    assert "22cee0390f9c" not in app_js
    assert "新疆游" not in app_js
    assert 'mode: "itinerary"' in app_js
    assert '"responses-itinerary-artwork"' in app_js
    itinerary_submit_block = app_js[
        app_js.index("async function submitAIItineraryMap()") : app_js.index('rememberRegenerationRequest("itinerary"')
    ]
    assert 'const result = await postJSON("api/itinerary-map/render"' in itinerary_submit_block
    assert '"responses-itinerary-artwork"' in itinerary_submit_block
    assert 'mode: "itinerary"' in itinerary_submit_block
    assert 'if (selectedSize === "auto")' in app_js
    assert "composition?.message" in app_js
    assert "api_key: canOverrideExecution ? settings.apiKey || undefined : undefined" in itinerary_submit_block
    assert "endpoint_url: settings.responsesUrl" not in itinerary_submit_block
    assert "model: canOverrideExecution ? itineraryModel : undefined" in itinerary_submit_block
    assert "generate_background: true" in itinerary_submit_block
    assert "logo_requested: logoRequested" in itinerary_submit_block
    assert "logo_requested: true" not in itinerary_submit_block
    assert "if (!routeStops.length)" in itinerary_submit_block
    assert "请填写副标题日期" in itinerary_submit_block
    assert "行程描述不能为空" in app_js
    assert "不要画 LOGO 占位框" in app_js
    assert "不要画边框" in app_js
    assert "不要画白底底板" in app_js
    assert "左上角预留干净白底 LOGO 安全区" not in app_js
    assert 'mode: "itinerary"' in app_js
    assert "COMPANY_LOGO_URL" in app_js
    assert "ensureCompanyLogoCanvas" not in app_js
    assert "parseItineraryStops" not in app_js
    assert "projectItineraryPoint" not in app_js
    assert "ITINERARY_MAP_FEATURES" not in app_js
    assert 'setMode("itinerary"' in app_js

    assert "#itineraryPanel" in styles_css
    assert ".itinerary-ai-options" in styles_css
    assert ".itinerary-stop-grid" in styles_css
    assert ".itinerary-help-panel" in styles_css
    assert "约 350km" not in index_html
    assert "约 350km" not in app_js


def test_edit_prompt_preserves_user_assets_dates_routes_and_logo() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert "EDIT_PRESERVE_PROMPT" in app_js
    assert "withEditPreservePrompt" in app_js
    assert "只修改用户明确要求修改的部分" in app_js
    assert "用户没有明确要求删除或替换的元素必须保留" in app_js
    assert "路线、地点、日期标签、距离标注、交通工具图标" in app_js
    assert "不能重绘、改造、遮挡或删除 LOGO" in app_js
    assert "withEditPreservePrompt(prompt, logoRequested)" in app_js
    assert "保留现有构图、路线、日期、文字、人物/景物、6 人游 LOGO 和品牌元素" in index_html


def test_image_prompts_require_exact_user_text_rendering() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert "TEXT_RENDERING_FIDELITY_PROMPT" in app_js
    assert "文字渲染分层要求" in app_js
    assert "必须逐字使用用户提供的文字" in app_js
    assert "不得改写、翻译、替换、增删或自行纠错" in app_js
    assert "主标题/核心标题" in app_js
    assert "高识别度商业美术字" in app_js
    assert "手写标题" in app_js
    assert "立体描边" in app_js
    assert "金属或笔刷字效" in app_js
    assert "不能被压成普通正文印刷字" in app_js
    assert "正文/地名/日期/序号/说明/贴士" in app_js
    assert "继续严格清晰逐字" in app_js
    assert "如果用户文字很多，优先保持文字准确和清晰可读，再考虑装饰" not in app_js
    assert "VISIBLE_TEXT_CONTRACT_HEADING" in app_js
    assert "buildVisibleTextContract" in app_js
    assert "extractTextReplacementPairs" in app_js
    assert "必须出现以下文字，逐字一致" in app_js
    assert "旧文字不得继续出现" in app_js
    assert "TEXT_REPLACEMENT_RE" in app_js
    assert "改成|替换成|换成|改为|变成" in app_js
    assert "formatVisibleTextContractPrompt(textContract)" in app_js
    assert "text_contract: textContract" in app_js
    assert "withTextRenderingFidelityPrompt" in app_js
    assert "withTextRenderingFidelityPrompt(prompt)" in app_js
    assert "withTextRenderingFidelityPrompt(requestText)" in app_js
    assert "confirmedPrompt = withLogoLayoutPrompt(effectivePrompt, logoRequested)" in app_js
    assert "confirmedPrompt = withLogoLayoutPrompt(baseRequestPrompt, logoRequested)" in app_js
    assert "confirmedPrompt = withEditPreservePrompt(prompt, logoRequested)" in app_js
    assert "prompt: confirmedPrompt" in app_js
    assert "prompt: requestPrompt" not in app_js
    assert 'id="textFidelityPanel"' in index_html
    assert 'id="textFidelityStatus"' in index_html
    assert 'id="textFidelityText"' in index_html


def test_generated_images_run_text_fidelity_check_against_required_phrases() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "function setTextFidelityPanel" in app_js
    assert "function restoreTextFidelityPanel" in app_js
    assert "async function checkTextFidelity" in app_js
    assert "api/text-fidelity" in app_js
    assert "text_contract: payload.text_contract || payload.textContract || {}" in app_js
    assert "文字一致性检查缩略图失败" in app_js
    assert (
        "checkTextFidelity({ ...payload, text_contract: payload.text_contract || payload.textContract || {} })"
        in app_js
    )
    assert "void Promise.allSettled(checks)" in app_js


def test_prompt_confirmation_modal_blocks_generation_until_checked() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="promptConfirmModal"' in index_html
    assert 'id="promptConfirmTextInput"' in index_html
    assert 'id="promptConfirmCheckbox"' in index_html
    assert 'id="submitPromptConfirmButton"' in index_html
    assert "openPromptConfirmModal" in app_js
    assert "confirmPromptBeforeRun" in app_js
    assert "refs.promptConfirmCheckbox.checked" in app_js
    assert "submitPromptConfirmButton.disabled" in app_js
    assert "await confirmPromptBeforeRun" in app_js
    assert "生成海报前确认提示词" in app_js
    assert "生成路线图前确认提示词" in app_js
    assert "请核对标题、日期和每天的地点顺序。" in app_js
    assert "请逐字检查行程日期、地点、酒店、交通和每日说明。" not in app_js
    assert "开始编辑前确认提示词" in app_js
    assert ".prompt-confirm-modal" in styles_css
    assert ".prompt-confirm-dialog" in styles_css
    assert ".prompt-confirm-textarea" in styles_css


def test_generation_post_helpers_only_send_local_auth_401_to_login_gate() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    post_json_block = app_js[app_js.index("async function postJSON(") : app_js.index("async function postJSONSilent(")]
    post_json_silent_block = app_js[
        app_js.index("async function postJSONSilent(") : app_js.index("async function checkCopyrightRisk(")
    ]
    fetch_json_block = app_js[app_js.index("async function fetchJSON(") : app_js.index("function enterAuthGate(")]

    assert 'enterAuthGate("login", "登录已过期，请重新登录。")' in fetch_json_block
    assert 'isLocalAuthUnauthorized(response, data)' in post_json_block
    assert 'isLocalAuthUnauthorized(response, data)' in post_json_silent_block
    # Local session expiry is code "unauthorized"; upstream 401s are classified
    # as "upstream_error" by classify_upstream_error, so the code equality
    # check alone keeps upstream auth failures out of the login gate.
    assert 'response.status === 401 && data?.code === "unauthorized"' in app_js


def test_poster_size_routing_is_owned_by_the_unified_backend_endpoint() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    submit_generate_block = app_js[
        app_js.index("async function submitGenerate()") : app_js.index("async function submitEdit()")
    ]

    assert "IMAGES_API_EXACT_SIZES" not in app_js
    assert "shouldUseResponsesForSelectedSize" not in app_js
    assert 'postJSON("api/image-jobs"' in submit_generate_block
    assert 'postJSON("api/responses-image"' not in submit_generate_block
    assert 'postJSON("api/generate"' not in submit_generate_block
    assert 'mode: "generate"' in submit_generate_block
    assert "size," in submit_generate_block


def test_layout_review_fixes_keep_generation_path_quiet() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert "海报生成" in index_html
    assert "开始海报生成" in index_html
    assert '"开始海报生成"' in app_js
    assert '"开始生成"' not in app_js
    assert '--font: "SF Pro Text"' in styles_css
    assert "Inter" not in styles_css
    assert 'class="advanced-params"' in index_html
    assert "<summary>高级参数</summary>" in index_html
    assert 'id="generateSizePreset" hidden' in index_html
    assert 'id="logoOverlayEnabled"' in index_html
    assert 'href="#resultPanel"' not in index_html
    assert 'id="resultActions" class="result-actions hidden"' in index_html
    assert 'id="sourcePreviewCard" class="preview-card source-card hidden"' in index_html
    assert 'setStatusMessage("已复制本次提示词。")' in app_js
    assert "errorDetailsWithRequestId" in app_js
    assert "request_id:" in app_js
    assert "flowConnect" not in app_js
    assert "setFlowState" not in app_js
    assert 'id="toastMessage"' in index_html
    assert ".toast-message" in styles_css
    assert 'class="comparison-grid single-result"' in index_html
    assert "集成 6 人游 LOGO" in index_html
    assert ".comparison-grid.single-result" in styles_css


def test_password_reset_ui_supports_email_self_service_and_admin_fallback() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="forgotPasswordButton"' in index_html
    assert 'id="passwordResetRequestForm"' in index_html
    assert 'id="passwordResetConfirmForm"' in index_html
    assert 'id="passwordResetNewPasswordInput"' in index_html
    assert "/api/password-reset/confirm" in app_js
    assert "reset_token" in app_js
    assert 'id="adminPasswordResetPanel"' in index_html
    assert 'id="passwordResetRequestsList"' in index_html
    assert "/api/password-reset-requests" in app_js
    assert "/api/admin/password-reset-requests" in app_js
    assert "submitPasswordResetAdminForm" in app_js
    assert ".password-reset-admin-form" in styles_css
    assert "如果账号存在且已填写邮箱，会收到重置邮件" in app_js


def test_fetch_json_handles_expired_session_like_post_json() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    fetch_json_block = app_js[app_js.index("async function fetchJSON") : app_js.index("function enterAuthGate")]

    assert "response.status === 401" in fetch_json_block
    assert 'enterAuthGate("login", "登录已过期，请重新登录。")' in fetch_json_block
    assert "state.appReady = false" in fetch_json_block


def test_frontend_guards_async_logo_and_team_chat_room_races() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    logo_block = app_js[
        app_js.index("async function composeLogoOverlayAfterDisplay") : app_js.index("async function setResult")
    ]
    chat_block = app_js[
        app_js.index("async function refreshTeamChatMessages") : app_js.index("async function markCurrentTeamChatRead")
    ]
    logout_block = app_js[app_js.index("async function logout") : app_js.index("async function loadWorkspaceSnapshot")]
    reset_chat_block = app_js[
        app_js.index("function resetTeamChatState") : app_js.index("function renderTeamChatMemberAvatar")
    ]

    assert "resultGenerationSeq !== state.resultGenerationSeq" in logo_block
    assert "const resultGenerationSeq = state.resultGenerationSeq + 1" in app_js
    assert "const requestedRoomKey = currentTeamChatRoomKey()" in chat_block
    assert "requestedRoomKey === currentTeamChatRoomKey()" in chat_block
    assert "requestSeq === state.teamChatMessageRequestSeq" in chat_block
    assert "message.room_key === requestedRoomKey" in chat_block
    assert "window.clearTimeout(state.persistTimer)" in logout_block
    assert "state.persistTimer = null" in logout_block
    assert "renderTeamChatMessages()" in reset_chat_block


def test_responses_shortfall_notice_reports_requested_and_returned_counts() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function resolveResultCountNotice") : app_js.index("function setResultCountNotice")
    ]
    expression = """
console.log(JSON.stringify({
  short: resolveResultCountNotice({ transport: "responses-image", requested_sample_count: 3 }, 1),
  complete: resolveResultCountNotice({ transport: "responses-image", requested_sample_count: 3 }, 3),
  imagesApi: resolveResultCountNotice({ transport: "images-generate", requested_sample_count: 3 }, 1),
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", f"{function_source}\n{expression}"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "short": "本次请求 3 张，上游返回 1 张",
        "complete": "",
        "imagesApi": "",
    }
    assert 'id="resultCountNotice"' in index_html
    assert 'id="resultCountNoticeText"' in index_html
    assert "setResultCountNotice(resolveResultCountNotice(payload, enrichedCandidates.length))" in app_js


def test_team_chat_poll_renders_only_when_messages_change() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    room_params_source = app_js[
        app_js.index("function teamChatRoomParams") : app_js.index("function teamChatReadPayload")
    ]
    merge_source = app_js[
        app_js.index("function updateTeamChatLastMessageId") : app_js.index("function isOwnTeamChatMessage")
    ]
    room_key_source = app_js[
        app_js.index("function currentTeamChatRoomKey") : app_js.index("function scheduleTeamChatFastPolling")
    ]
    refresh_source = app_js[
        app_js.index("async function refreshTeamChatMessages") : app_js.index("async function markCurrentTeamChatRead")
    ]
    script = f"""
const firstMessage = {{ id: 1, room_key: "team:ops", content: "hello", created_at: "2026-07-12T00:00:00Z" }};
const secondMessage = {{ id: 2, room_key: "team:ops", content: "new", created_at: "2026-07-12T00:00:01Z" }};
const state = {{
  currentUser: {{ id: 7 }},
  teamChatRoom: {{ type: "team", recipientUserId: null }},
  teamChatGroup: {{ roomKey: "team:ops" }},
  teamChatMessages: [firstMessage],
  teamChatLastMessageId: 1,
}};
const refs = {{
  teamChatMessages: {{}},
  teamChatModal: {{ classList: {{ contains: () => true }} }},
}};
let renderCalls = 0;
let responseIndex = 0;
const responses = [[], [secondMessage]];
async function fetchJSON() {{
  return {{ response: {{ ok: true }}, data: {{ messages: responses[responseIndex++] }} }};
}}
function renderTeamChatMessages() {{ renderCalls += 1; }}
function setTeamChatStatus() {{}}
async function markCurrentTeamChatRead() {{}}
{room_params_source}
{merge_source}
{room_key_source}
{refresh_source}
const originalMessages = state.teamChatMessages;
const firstSuccess = await refreshTeamChatMessages({{ append: true }});
const firstRenderCalls = renderCalls;
const preservedReference = state.teamChatMessages === originalMessages;
const secondSuccess = await refreshTeamChatMessages({{ append: true }});
console.log(JSON.stringify({{
  firstSuccess,
  secondSuccess,
  firstRenderCalls,
  totalRenderCalls: renderCalls,
  preservedReference,
  lastMessageId: state.teamChatLastMessageId,
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "firstSuccess": True,
        "secondSuccess": True,
        "firstRenderCalls": 0,
        "totalRenderCalls": 1,
        "preservedReference": True,
        "lastMessageId": 2,
    }


def test_team_chat_ignores_an_older_full_refresh_after_a_newer_incremental_response() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    room_params_source = app_js[
        app_js.index("function teamChatRoomParams") : app_js.index("function teamChatReadPayload")
    ]
    merge_source = app_js[
        app_js.index("function updateTeamChatLastMessageId") : app_js.index("function isOwnTeamChatMessage")
    ]
    room_key_source = app_js[
        app_js.index("function currentTeamChatRoomKey") : app_js.index("function scheduleTeamChatFastPolling")
    ]
    refresh_source = app_js[
        app_js.index("async function refreshTeamChatMessages") : app_js.index("async function markCurrentTeamChatRead")
    ]
    script = f"""
const first = {{ id: 1, room_key: "team:ops", content: "first", created_at: "2026-07-12T00:00:00Z" }};
const second = {{ id: 2, room_key: "team:ops", content: "second", created_at: "2026-07-12T00:00:01Z" }};
const state = {{
  currentUser: {{ id: 7 }},
  teamChatRoom: {{ type: "team", recipientUserId: null }},
  teamChatGroup: {{ roomKey: "team:ops" }},
  teamChatMessages: [first],
  teamChatLastMessageId: 1,
  teamChatMessageRequestSeq: 0,
}};
const refs = {{
  teamChatMessages: {{}},
  teamChatModal: {{ classList: {{ contains: () => true }} }},
}};
let resolveFull;
let resolveAppend;
let renderCalls = 0;
async function fetchJSON(url) {{
  return await new Promise((resolve) => {{
    if (url.includes("after_id=")) resolveAppend = resolve;
    else resolveFull = resolve;
  }});
}}
function renderTeamChatMessages() {{ renderCalls += 1; }}
function setTeamChatStatus() {{}}
async function markCurrentTeamChatRead() {{}}
{room_params_source}
{merge_source}
{room_key_source}
{refresh_source}
const olderFull = refreshTeamChatMessages();
const newerAppend = refreshTeamChatMessages({{ append: true }});
resolveAppend({{ response: {{ ok: true }}, data: {{ messages: [second] }} }});
const appendResult = await newerAppend;
resolveFull({{ response: {{ ok: true }}, data: {{ messages: [first] }} }});
const fullResult = await olderFull;
console.log(JSON.stringify({{
  appendResult,
  fullResult,
  ids: state.teamChatMessages.map((message) => message.id),
  renderCalls,
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "appendResult": True,
        "fullResult": False,
        "ids": [1, 2],
        "renderCalls": 1,
    }


def test_team_chat_old_read_completion_cannot_clear_a_newer_request_error() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    refresh_source = app_js[
        app_js.index("async function refreshTeamChatMessages") : app_js.index("async function markCurrentTeamChatRead")
    ]
    script = f"""
const state = {{
  currentUser: {{ id: 7 }},
  teamChatMessageRequestSeq: 0,
  teamChatLastMessageId: 1,
}};
const refs = {{
  teamChatMessages: {{}},
  teamChatModal: {{ classList: {{ contains: () => false }} }},
}};
let requestCount = 0;
let releaseRead;
let notifyReadStarted;
const readStarted = new Promise((resolve) => {{ notifyReadStarted = resolve; }});
const readGate = new Promise((resolve) => {{ releaseRead = resolve; }});
let status = "";
function currentTeamChatRoomKey() {{ return "team:ops"; }}
function teamChatRoomParams() {{ return new URLSearchParams(); }}
function mergeTeamChatMessages() {{ return false; }}
function renderTeamChatMessages() {{}}
function setTeamChatStatus(message) {{ status = message; }}
async function fetchJSON() {{
  requestCount += 1;
  if (requestCount === 1) return {{ response: {{ ok: true }}, data: {{ messages: [] }} }};
  return {{ response: {{ ok: false }}, data: {{ error: "new request failed" }} }};
}}
async function markCurrentTeamChatRead() {{
  notifyReadStarted();
  await readGate;
}}
{refresh_source}
const older = refreshTeamChatMessages().then((success) => {{
  if (success) setTeamChatStatus("");
  return success;
}});
await readStarted;
const newerResult = await refreshTeamChatMessages();
releaseRead();
const olderResult = await older;
console.log(JSON.stringify({{ olderResult, newerResult, status }}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "olderResult": False,
        "newerResult": False,
        "status": "new request failed",
    }


def test_asset_data_url_hydrates_missing_dimensions_for_logo_detection() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    dimension_source = app_js[
        app_js.index("async function ensureAssetDimensions") : app_js.index("function validateClientImageFile")
    ]
    script = f"""
async function loadImageElement() {{ return {{ naturalWidth: 1536, naturalHeight: 2048 }}; }}
function imageAssetDimensions() {{ return null; }}
{dimension_source}
const asset = {{ dataUrl: "data:image/png;base64,AAAA" }};
await ensureAssetDataUrl(asset);
console.log(JSON.stringify(asset));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "dataUrl": "data:image/png;base64,AAAA",
        "width": 1536,
        "height": 2048,
    }


def test_team_chat_send_completion_is_bound_to_the_send_time_room() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    send_payload_source = app_js[
        app_js.index("function teamChatSendPayload") : app_js.index("function teamChatDisplayName")
    ]
    submit_source = app_js[
        app_js.index("async function submitTeamChatMessage") : app_js.index("async function submitChangePassword")
    ]
    script = f"""
const state = {{
  currentUser: {{ id: 7, username: "alice" }},
  teamChatGroup: {{ roomKey: "team:ops" }},
  teamChatRoom: {{ type: "team", recipientUserId: null }},
  teamChatMessages: [],
  teamChatSending: false,
  teamChatQuotedMessage: null,
}};
const refs = {{
  teamChatMessageInput: {{ value: "hello", focus: () => {{}} }},
  sendTeamChatButton: {{ disabled: false, textContent: "发送" }},
}};
let resolveFetch;
let notifyFetchStarted;
const fetchStarted = new Promise((resolve) => {{ notifyFetchStarted = resolve; }});
let sentPayload = null;
let replaceCalls = 0;
let renderCalls = 0;
let markReadCalls = 0;
async function fetchJSON(_url, options) {{
  sentPayload = JSON.parse(options.body);
  notifyFetchStarted();
  return await new Promise((resolve) => {{ resolveFetch = resolve; }});
}}
function currentTeamChatRoomKey() {{
  if (state.teamChatRoom.type === "team") return state.teamChatGroup.roomKey;
  return `dm:7:${{state.teamChatRoom.recipientUserId}}`;
}}
function formatTeamChatOutgoingContent(content) {{ return content; }}
function clearTeamChatQuote() {{ state.teamChatQuotedMessage = null; }}
function createOptimisticTeamChatMessage(content) {{
  return {{ id: -1, client_id: "local-1", room_key: currentTeamChatRoomKey(), content, pending: true }};
}}
function mergeTeamChatMessages(messages) {{ state.teamChatMessages = [...state.teamChatMessages, ...messages]; }}
function renderTeamChatMessages() {{ renderCalls += 1; }}
function setTeamChatSending(value) {{ state.teamChatSending = Boolean(value); }}
function setTeamChatStatus() {{}}
function restoreTeamChatDraft() {{}}
function replaceOptimisticTeamChatMessage(_clientId, messages) {{
  replaceCalls += 1;
  state.teamChatMessages = messages;
}}
async function markCurrentTeamChatRead() {{ markReadCalls += 1; }}
function scheduleTeamChatFastPolling() {{}}
async function refreshTeamChatMessages() {{}}
{send_payload_source}
{submit_source}
const pending = submitTeamChatMessage({{ preventDefault: () => {{}} }});
await fetchStarted;
state.teamChatRoom = {{ type: "dm", recipientUserId: 9 }};
state.teamChatMessages = [];
resolveFetch({{
  response: {{ ok: true }},
  data: {{
    messages: [{{ id: 11, room_key: "team:ops", content: "hello" }}],
    bot_reply_pending: false,
  }},
}});
await pending;
console.log(JSON.stringify({{
  sentPayload,
  replaceCalls,
  renderCalls,
  markReadCalls,
  currentMessages: state.teamChatMessages,
  sending: state.teamChatSending,
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["sentPayload"] == {
        "room_type": "team",
        "recipient_user_id": None,
        "content": "hello",
    }
    assert result["replaceCalls"] == 0
    assert result["renderCalls"] == 1
    assert result["markReadCalls"] == 0
    assert result["currentMessages"] == []
    assert result["sending"] is False


def test_user_profile_ui_supports_avatar_and_editable_login_username() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="openProfileButton"' in index_html
    assert 'id="profileModal"' in index_html
    assert 'id="profileAvatarInput"' in index_html
    assert 'accept="image/png,image/jpeg,image/webp"' in index_html
    assert 'id="profileUsernameInput"' in index_html
    assert "用于登录。修改后，下次登录请使用新用户名。" in index_html
    assert 'id="profileDisplayNameInput"' in index_html
    assert "仅用于页面显示，不改变登录用户名。" in index_html
    assert 'id="profilePhoneCountryCodeInput"' in index_html
    assert '<option value="+86">+86 中国</option>' in index_html
    assert 'id="profileCompanyInput"' in index_html
    assert 'id="profileDepartmentInput"' in index_html
    assert 'id="profileJobTitleInput"' in index_html
    assert "真实姓名" not in index_html
    assert "/api/me/profile" in app_js
    assert "/api/me/avatar" in app_js
    assert "profileCompanyInput" in app_js
    assert "profileDepartmentInput" in app_js
    assert "修改登录用户名需要填写当前密码" in app_js
    assert "updateProfileUsernamePasswordHint" in app_js
    assert ".profile-dialog" in styles_css
    assert ".profile-avatar-preview" in styles_css
    assert ".phone-input-row" in styles_css


def test_team_chat_ui_is_available_without_openai_api_badge() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="teamChatButton"' in index_html
    assert "Team Chat" in index_html
    assert 'id="teamChatModal"' in index_html
    assert 'id="teamChatMembers"' in index_html
    assert 'id="teamChatGroupMembers"' in index_html
    assert 'id="teamChatMessageInput"' in index_html
    assert "输入群消息，可以 @GPT-BOT" in index_html
    assert 'id="teamChatQuotePreview"' in index_html
    assert 'id="clearTeamChatQuoteButton"' in index_html
    assert 'id="teamChatTeamRoomName"' in index_html
    assert 'id="teamChatTeamRoomMeta"' in index_html
    assert 'id="teamChatMain"' in index_html
    assert 'id="teamChatGroupContextToggle"' in index_html
    assert 'id="teamChatGroupContextBody"' in index_html
    assert 'id="teamChatAnnouncement"' in index_html
    assert 'id="teamChatGroupMemberPanel"' in index_html
    assert 'id="teamChatGroupAssets"' in index_html
    assert 'id="teamChatGroupStats"' in index_html
    assert 'id="teamChatGroupSummary"' in index_html
    assert 'id="saveGroupAssetButton"' in index_html
    assert "部门群" in index_html
    assert "AI 助手" in index_html
    assert "最近私聊" in app_js
    assert "OpenAI Images API" not in index_html
    assert "/api/team-chat/members" in app_js
    assert "/api/team-chat/messages" in app_js
    assert "/api/team-chat/unread" in app_js
    assert "/api/org-units" in app_js
    assert "/api/team-chat/group-announcement" in app_js
    assert "/api/team-chat/group-assets" in app_js
    assert "/api/team-chat/group-stats" in app_js
    assert "/api/team-chat/group-summary" in app_js
    assert "openTeamChatModal" in app_js
    assert "GPT-BOT" in app_js
    assert "normalizeTeamChatGroup" in app_js
    assert "teamChatHumanMembers" in app_js
    assert "teamChatRecentDms" in app_js
    assert "TEAM_CHAT_MAX_RECENT_DMS" in app_js
    assert "loadTeamChatRecentDms" in app_js
    assert "rememberTeamChatRecentDm" in app_js
    assert "saveTeamChatRecentDms" in app_js
    assert "teamChatInputPlaceholder" in app_js
    assert "向 GPT-BOT 提问" in app_js
    assert "发给 ${state.teamChatRoom.title" in app_js
    assert "renderTeamChatGroupMembers" in app_js
    assert "human_members" in app_js
    assert "teamChatGroupDisplayTitle" in app_js
    assert "switchTeamChatDirectMember" in app_js
    assert "without-member-panel" in app_js
    assert "renderTeamChatGroupContextDisclosure" in app_js
    assert "teamChatGroupContextExpanded" in app_js
    assert "state.teamChatGroup" in app_js
    assert "teamChatSending: false" in app_js
    assert "setTeamChatSending" in app_js
    assert "mergeTeamChatMessages" in app_js
    assert "updateTeamChatLastMessageId" in app_js
    assert 'refs.teamChatMessageInput.value = ""' in app_js
    assert "refs.sendTeamChatButton.disabled = isSending" in app_js
    assert "restoreTeamChatDraft" in app_js
    assert "createOptimisticTeamChatMessage" in app_js
    assert "replaceOptimisticTeamChatMessage" in app_js
    assert "bot_reply_pending" in app_js
    assert "TEAM_CHAT_FAST_POLL_LIMIT" in app_js
    assert "saveCurrentResultToGroupAssets" in app_js
    assert "openTeamChatMessageMenu" in app_js
    assert "copyTeamChatMessage" in app_js
    assert "quoteTeamChatMessage" in app_js
    assert "parseTeamChatQuotedContent" in app_js
    assert "renderTeamChatBubbleContent" in app_js
    assert "isOwnTeamChatMessage" in app_js
    assert "button.dataset.action = action" in app_js
    assert '"copy", "复制"' in app_js
    assert '"quote", "引用"' in app_js
    assert '"recall", "撤回"' in app_js
    assert 'actions.push(["recall"' in app_js
    assert "已引用这条消息。" in app_js
    assert 'setTeamChatStatus("逗你的，撤回不了。")' in app_js
    assert ".team-chat-dialog" in styles_css
    assert ".team-chat-button.has-unread" in styles_css
    assert "grid-template-rows: auto minmax(0, 1fr)" in styles_css
    assert ".team-chat-members" in styles_css
    assert ".team-chat-conversation-label" in styles_css
    assert ".team-chat-room-pane" in styles_css
    assert ".team-chat-main.without-member-panel" in styles_css
    assert ".team-chat-group-context-toggle" in styles_css
    assert ".team-chat-group-context-body" in styles_css
    assert ".team-chat-group-members" in styles_css
    assert ".team-chat-current-dm" in styles_css
    assert "min-height: 46px" in styles_css
    assert "max-height: 96px" in styles_css
    assert "overscroll-behavior: contain" in styles_css
    assert "grid-template-columns: minmax(0, 1fr) 26px" in styles_css
    assert ".team-chat-message-bubble" in styles_css
    assert ".team-chat-message-quote" in styles_css
    assert ".team-chat-message.mine .team-chat-message-actions" not in styles_css
    assert ".team-chat-message-menu" in styles_css
    assert ".team-chat-message.pending" in styles_css
    assert ".team-chat-quote-preview" in styles_css
    assert ".team-chat-group-context" in styles_css
    assert ".team-chat-asset-card" in styles_css
    assert "body.chat-open .desktop-shell" in styles_css


def test_admin_org_management_ui_is_available() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="adminOrgPanel"' in index_html
    assert 'id="adminOrgCreateForm"' in index_html
    assert 'id="adminUserOrgForm"' in index_html
    assert 'id="adminGroupAnnouncementForm"' in index_html
    assert 'id="adminAnnouncementOrgSelect"' in index_html
    assert 'id="adminOrgUnitSelect"' in index_html
    assert 'id="adminOrgStatsList"' in index_html
    assert "renderOrgUnitControls" in app_js
    assert "submitAdminGroupAnnouncement" in app_js
    assert "renderAdminOrgStats" in app_js
    assert "/api/admin/org-units" in app_js
    assert "/api/admin/org-audit" in app_js
    assert "/api/admin/org-stats" in app_js
    assert "/api/admin/users/${userId}/org" in app_js
    assert "refreshAdminOrgContext" in app_js


def test_generation_can_be_interrupted_from_ui() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="cancelRequestButton"' in index_html
    assert "中断生成" in index_html
    assert "cancelActiveRequest" in app_js
    assert "ensureRequestNotCancelled" in app_js
    assert "state.activeRequestController" in app_js
    assert "options.signal || controller.signal" in app_js
    assert "用户已中断当前生成" in app_js
    assert ".cancel-request-button" in styles_css


def test_generate_prompt_chips_match_travel_brand_keywords() -> None:
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert 'data-snippet="高级旅行海报质感，商业摄影风格">高级旅行</button>' in index_html
    assert 'data-snippet="精致商业海报，构图稳定，主体突出">精致海报</button>' in index_html
    assert 'data-snippet="精品酒店场景，真实材质，精致光影">酒店质感</button>' in index_html
    assert 'data-snippet="山野度假氛围，户外自然，生活方式摄影">山野度假</button>' in index_html
    assert 'data-snippet="电影感构图，光影克制，氛围高级">电影光影</button>' in index_html
    assert 'data-snippet="色彩克制，统一色调，画面高级">色彩克制</button>' in index_html
    assert ">山间湖泊</button>" not in index_html
    assert ">木屋</button>" not in index_html


def test_optional_creative_brief_keeps_free_prompt_as_primary_path() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="creativeBriefPanel"' in index_html
    assert "<summary>创意辅助（可选）</summary>" in index_html
    assert "自由提示词仍是主路径" in index_html
    assert 'id="creativeBriefDestinationInput"' in index_html
    assert 'id="creativeBriefAudienceInput"' in index_html
    assert 'id="creativeBriefChannelInput"' in index_html
    assert 'id="creativeBriefMoodInput"' in index_html
    assert 'id="creativeBriefMustHaveInput"' in index_html
    assert 'id="creativeBriefAvoidInput"' in index_html
    assert 'id="applyCreativeBriefButton"' in index_html
    assert 'id="askBotCreativeBriefButton"' in index_html
    assert "buildCreativeBriefSnippet" in app_js
    assert "applyCreativeBriefToPrompt" in app_js
    assert "askBotWithCreativeBrief" in app_js
    assert "不会替你重写整段提示词" in index_html
    assert "只把可选 brief 作为补充上下文" in app_js
    assert ".creative-brief-panel" in styles_css


def test_prompt_recipe_mode_keeps_precise_prompt_as_default_and_records_lineage() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'name="promptMode" value="free" checked' in index_html
    assert "精确提示词" in index_html
    assert "默认原样发送" in index_html
    assert "配方辅助" in index_html
    assert 'id="promptRecipeSelect"' in index_html
    assert 'id="promptRecipeCards"' in index_html
    assert 'id="applyPromptRecipeButton"' in index_html
    assert 'id="effectivePromptPreview"' in index_html
    assert "buildEffectiveGeneratePrompt" in app_js
    assert "loadPromptRecipes" in app_js
    assert "renderPromptRecipeCards" in app_js
    assert "selectPromptRecipe(" in app_js
    assert 'fetchJSON("api/recipes"' in app_js
    assert "original_prompt: prompt" in app_js
    assert "prompt_mode: promptPlan.promptMode" in app_js
    assert "recipe_id: promptPlan.recipe?.id" in app_js
    assert "confirmedPrompt = withLogoLayoutPrompt(effectivePrompt, logoRequested)" in app_js
    assert "confirmedPrompt = withLogoLayoutPrompt(baseRequestPrompt, logoRequested)" in app_js
    assert 'id="itineraryIdEnabled"' in index_html
    assert 'id="itineraryIdInput"' in index_html
    assert "itinerary_id: itineraryId" in app_js
    assert "getExplicitItineraryId" in app_js
    assert ".itinerary-id-toggle" in styles_css
    assert "只追加质量要求，不覆盖原提示词" in app_js
    assert ".prompt-mode-panel" in styles_css
    assert ".recipe-assist-panel" in styles_css
    assert ".prompt-recipe-cards" in styles_css
    assert ".prompt-recipe-card" in styles_css
    assert ".effective-prompt-panel" in styles_css


def test_prompt_flow_only_keeps_exact_and_recipe_assist_controls() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert "精确提示词" in index_html
    assert "配方辅助" in index_html
    assert 'id="promptRecipeSelect"' in index_html
    assert 'id="applyPromptRecipeButton"' in index_html
    assert 'id="effectivePromptPreview"' in index_html
    assert "只追加质量要求，不覆盖原提示词" in app_js
    assert ".prompt-mode-panel" in styles_css
    assert ".recipe-assist-panel" in styles_css

    removed_tokens = [
        'id="optimizePromptButton"',
        'id="promptOptimizationReview"',
        'id="repeatWarningPanel"',
        'id="posterLayoutPanel"',
        'id="renderPosterLayoutButton"',
        'id="successTemplateList"',
        'fetchJSON("/api/prompt/optimize"',
        'fetchJSON("/api/prompt/repetition-check"',
        'fetchJSON("/api/poster-layout/render"',
        'fetchJSON("/api/success-templates"',
        "maybeOptimizeTextHeavyPromptBeforeImage",
        "looksLikePosterLayoutPrompt",
        "submitPosterLayoutRender",
        "showRepeatWarning",
        "useSuccessTemplate",
        ".prompt-optimization-review",
        ".repeat-warning-panel",
        ".poster-layout-panel",
        ".success-template-list",
    ]
    combined_assets = "\n".join([index_html, app_js, styles_css])
    for token in removed_tokens:
        assert token not in combined_assets


def test_legacy_program_layout_background_prompt_is_blocked_before_generation() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "isLegacyProgramLayoutBackgroundPrompt" in app_js
    assert "legacy_layout_background_prompt" in app_js
    assert "旧程序排版背景底图提示词" in app_js
    assert "sanitizeLegacyWorkspacePrompt" in app_js
    assert "已清空旧程序排版背景底图提示词" in app_js


def test_aesthetic_memory_is_optional_and_never_forced_into_prompts() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "优秀资产" in app_js
    assert "满意作品会自动沉淀到这里" in app_js
    assert "renderTeamChatGroupAssets" in app_js
    assert "useGroupAssetAsReference" in app_js
    assert "仅作可选参考" in app_js
    assert "强制套用历史风格" not in app_js
    assert "autoApplyAestheticMemory" not in app_js


def test_docker_packaging_excludes_local_env_and_persists_container_data() -> None:
    dockerignore = (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    build_script = (ROOT_DIR / "scripts" / "docker-build-push.sh").read_text(encoding="utf-8")
    pyproject = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    version_line = next(line for line in pyproject.splitlines() if line.startswith("version = "))
    version = version_line.split('"', 2)[1]

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "data/" in dockerignore
    assert "/*.png" in dockerignore
    assert "/*.jpg" in dockerignore
    assert "/*.jpeg" in dockerignore
    assert "/*.webp" in dockerignore
    assert "!static/*.png" in dockerignore
    assert "uv.lock" not in dockerignore.splitlines()
    assert "env_file:" not in compose
    assert f"image: minorli/picgen:{version}" in compose
    assert "picgen-data:/app/data" in compose
    assert 'VOLUME ["/app/data"]' in dockerfile
    assert "PICGEN_STATIC_DIR=/app/static" in dockerfile
    assert "PICGEN_ROOT_DIR=/app" in dockerfile
    assert "PICGEN_ENV_FILE=/app/data/.env" in dockerfile
    assert "PICGEN_AUTH_DB_PATH" not in dockerfile
    assert "apt-get" not in dockerfile
    assert "curl" not in dockerfile
    assert "urllib.request.urlopen" in dockerfile
    assert "/api/ready" in dockerfile
    assert "/api/ready" in compose
    assert "urlopen('http://127.0.0.1:%s/api/health'" not in dockerfile
    assert "urlopen('http://127.0.0.1:%s/api/health'" not in compose
    assert "uv sync --frozen --no-dev" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert '"--workers", "2"' not in dockerfile
    assert "https://sub.tidba.com/v1/images/generations" in dockerfile
    assert "https://sub.tidba.com/v1/images/edits" in dockerfile
    assert "https://sub.tidba.com/v1/responses" in dockerfile
    assert 'IMAGE="${IMAGE:-minorli/picgen}"' in build_script
    assert f'VERSION="${{VERSION:-{version}}}"' in build_script
    assert "--push" in build_script


def test_static_footer_version_matches_release() -> None:
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    pyproject = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    version_line = next(line for line in pyproject.splitlines() if line.startswith("version = "))
    version = version_line.split('"', 2)[1]

    assert f"PicGen Console　v{version}" in index_html
    assert f'href="styles.css?v={version}"' in index_html
    assert f'src="app.js?v={version}"' in index_html
    assert "PicGen Console　v0.1.2</span>" not in index_html


def test_frontend_generation_result_state_race_guards_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "snapshotCurrentResultState" in app_js
    assert "restoreResultStateSnapshot" in app_js
    assert "state.pendingResultSnapshot" in app_js
    assert "restorePendingResultAfterCancellation" in app_js
    assert "selectedCandidate.saved_image_path" in app_js
    assert "LOGO 成品已落盘到 ${selectedCandidate.saved_image_path}" in app_js
    assert "state.copyrightRiskRequestSeq += 1" in app_js
    assert "riskRequestSeq !== state.copyrightRiskRequestSeq" in app_js


def test_frontend_rejects_oversized_image_uploads_before_reading_files() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "CLIENT_IMAGE_UPLOAD_MAX_BYTES" in app_js
    assert "validateClientImageFile" in app_js
    assert "图片文件过大" in app_js
    assert "validateClientImageFile(file)" in app_js


def test_frontend_concurrency_and_persistence_guards_cover_new_edge_cases() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "rerunInProgress: false" in app_js
    assert "userContextEpoch: 0" in app_js
    assert "preferenceSyncTail: Promise.resolve()" in app_js

    auth_gate = app_js[app_js.index("function enterAuthGate") : app_js.index("function enterAppShell")]
    assert "cancelPendingPromptConfirmation()" in auth_gate

    user_switch = app_js[
        app_js.index("function invalidateUserContext") : app_js.index("function applyAnonymousShellChrome")
    ]
    assert "state.userContextEpoch += 1" in user_switch
    assert "state.activeRequestController?.abort()" in user_switch
    session_expiry = app_js[
        app_js.index("function handleSessionExpired") : app_js.index("function enterAuthGate")
    ]
    assert "setCurrentUser(null)" in session_expiry
    fetch_json = app_js[app_js.index("async function fetchJSON") : app_js.index("function handleSessionExpired")]
    assert fetch_json.index("ensureUserContextCurrent(requestUserContextEpoch)") < fetch_json.index(
        "if (response.status === 401)"
    )

    user_scope_reset = app_js[
        app_js.index("function resetWorkspaceForUserScope") : app_js.index("function openWorkspaceDb")
    ]
    assert "state.persistenceReady = false" in user_scope_reset
    assert "clearResult()" in user_scope_reset
    assert "clearGenerateForm()" in user_scope_reset
    assert "clearEditForm()" in user_scope_reset
    assert "resetItineraryMapExample()" in user_scope_reset
    bootstrap_start = app_js.index("async function startAuthenticatedApp")
    authenticated_bootstrap = app_js[bootstrap_start : app_js.index("\n\ninit()", bootstrap_start)]
    assert authenticated_bootstrap.index("resetWorkspaceForUserScope()") < authenticated_bootstrap.index(
        "state.history = loadJSON(historyStorageKey(), [])"
    )

    load_workspace = app_js[
        app_js.index("async function loadWorkspaceSnapshot") : app_js.index("async function saveWorkspaceSnapshot")
    ]
    assert load_workspace.index("const storageKey = workspaceStorageKey()") < load_workspace.index(
        "await openWorkspaceDb()"
    )
    save_workspace = app_js[
        app_js.index("async function saveWorkspaceSnapshot") : app_js.index("function sanitizeRawResponse")
    ]
    assert "storageKey = workspaceStorageKey()" in save_workspace
    assert "store.put(snapshot, storageKey)" in save_workspace
    workspace_snapshot = app_js[
        app_js.index("function createWorkspaceSnapshot") : app_js.index("function scheduleWorkspacePersist")
    ]
    assert "ownerUserId: state.currentUser?.id ?? null" in workspace_snapshot

    preferences_sync = app_js[
        app_js.index("async function syncUserPreferences") : app_js.index("function getImageTransport")
    ]
    assert "state.preferenceSyncTail" in preferences_sync
    assert "userContextIsCurrent" in preferences_sync
    assert "user_context_epoch" not in preferences_sync

    post_json = app_js[app_js.index("async function postJSON") : app_js.index("async function postJSONSilent")]
    assert "options.userContextEpoch" in post_json
    for function_name, next_function in (
        ("submitAIItineraryMap", "resetItineraryMapExample"),
        ("submitVariantGenerate", "submitGenerate"),
        ("submitGenerate", "submitEdit"),
        ("submitEdit", "workspaceHasDraftContent"),
    ):
        block = app_js[
            app_js.index(f"async function {function_name}") : app_js.index(f"function {next_function}")
        ]
        assert "userContextEpoch" in block
        assert "userContextIsCurrent" in block

    candidate_switch = app_js[
        app_js.index("function selectResultCandidate") : app_js.index("function renderResultCandidates")
    ]
    assert "state.copyrightRiskRequestSeq += 1" in candidate_switch
    assert "state.textFidelityRequestSeq += 1" in candidate_switch

    workspace_snapshot = app_js[
        app_js.index("function createWorkspaceSnapshot") : app_js.index("function scheduleWorkspacePersist")
    ]
    assert "checkedCandidateIndex: state.checkedCandidateIndex" in workspace_snapshot
    workspace_restore = app_js[
        app_js.index("async function restoreWorkspaceState") : app_js.index("function currentFormSnapshot")
    ]
    assert "legacyMultiCandidateCheck" in workspace_restore
    assert "旧工作区没有记录检查对应的候选" in workspace_restore
    persist = app_js[
        app_js.index("function scheduleWorkspacePersist") : app_js.index("async function restoreWorkspaceState")
    ]
    assert "state.suppressSettingsPersist" in persist
    pagehide = app_js[app_js.index('window.addEventListener("pagehide"') : app_js.index("async function init")]
    assert "state.suppressSettingsPersist" in pagehide

    save_json = app_js[app_js.index("function saveJSON") : app_js.index("function escapeHTML")]
    assert "return true" in save_json
    assert "return false" in save_json
    save_settings = app_js[app_js.index("function saveSettings") : app_js.index("function loadSettings")]
    assert "if (!saveJSON" in save_settings

    coordinate_merge = app_js[
        app_js.index("function mergeItineraryCoordinateStops") : app_js.index("function itineraryCoordinateHelpText")
    ]
    assert "exactNameMatches" in coordinate_merge
    assert "name.includes(coordName)" not in coordinate_merge
    assert "!coordName" in coordinate_merge

    external_result_reset = app_js[
        app_js.index("function resetReviewStateForExternalResult") : app_js.index("function openSharedResult")
    ]
    assert "state.resultGenerationSeq += 1" in external_result_reset
    assert "state.copyrightRiskRequestSeq += 1" in external_result_reset
    assert "state.textFidelityRequestSeq += 1" in external_result_reset
    assert "state.generatedImageDetailRequestSeq += 1" in external_result_reset
    assert "state.checkedCandidateIndex = null" in external_result_reset
    assert 'setError("")' in external_result_reset
    assert "resetReviewStateForExternalResult()" in app_js[
        app_js.index("function openSharedResult") : app_js.index("function galleryItemToAsset")
    ]
    assert "resetReviewStateForExternalResult()" in app_js[
        app_js.index("function openGalleryLikeImage") : app_js.index("function openGalleryItem")
    ]

    candidate_switch = app_js[
        app_js.index("function selectResultCandidate") : app_js.index("function renderResultCandidates")
    ]
    assert "state.candidateReviewStates" in candidate_switch
    assert "reviewPayloadForCandidate" in candidate_switch
    assert "reviewStatusNeedsRetry" in candidate_switch

    set_result = app_js[app_js.index("async function setResult") : app_js.index("function historySummary")]
    assert 'setRiskPanel("等待检查"' in set_result
    assert 'setTextFidelityPanel("等待检查"' in set_result
    assert 'refs.shareResultPanel?.classList.add("hidden")' in set_result

    pending_result = app_js[
        app_js.index("function previewPendingResult") : app_js.index("function candidateImageSource")
    ]
    assert "normalizePendingReviewSnapshot" in pending_result
    assert "state.resultGenerationSeq += 1" in pending_result
    assert "state.copyrightRiskRequestSeq += 1" in pending_result
    assert "state.textFidelityRequestSeq += 1" in pending_result
    assert 'refs.shareResultPanel?.classList.add("hidden")' in pending_result

    risk_check = app_js[
        app_js.index("async function checkCopyrightRisk") : app_js.index("async function checkTextFidelity")
    ]
    assert risk_check.count("riskRequestSeq !== state.copyrightRiskRequestSeq") >= 6
    fidelity_check = app_js[
        app_js.index("async function checkTextFidelity") : app_js.index("async function fileToDataURL")
    ]
    assert fidelity_check.count("fidelityRequestSeq !== state.textFidelityRequestSeq") >= 8

    rerun = app_js[
        app_js.index("async function regenerateFromBadFeedback") : app_js.index("function validateAuthFormInputs")
    ]
    assert "state.rerunInProgress" in rerun
    assert "if (!submitted)" in rerun
    rerun_last = app_js[
        app_js.index("async function rerunLastGeneration") : app_js.index("function getGenerateSampleCount")
    ]
    assert "state.rerunInProgress = true" in rerun_last
    assert "state.rerunInProgress = false" in rerun_last
    assert "mergeRerunDraftSnapshots" in rerun_last

    form_snapshot = app_js[app_js.index("function currentFormSnapshot") : app_js.index("function getSizeSnapshotValue")]
    assert "generateWidth" in form_snapshot
    assert "generateHeight" in form_snapshot
    apply_snapshot = app_js[
        app_js.index("function applyFormSnapshot") : app_js.index("function rememberRegenerationRequest")
    ]
    assert "snapshot.generateWidth" in apply_snapshot
    assert "snapshot.generateHeight" in apply_snapshot

    feedback = app_js[
        app_js.index("async function submitResultFeedback") : app_js.index("async function submitBadFeedbackReason")
    ]
    assert feedback.index("state.feedbackSubmitting") < feedback.index("updateFeedbackSelection")
    assert "feedbackResultGenerationSeq" in feedback
    assert "feedbackCandidateIndex" in feedback
    assert feedback.count("feedbackTargetIsCurrent()") >= 3

    workspace_restore = app_js[
        app_js.index("async function restoreWorkspaceState") : app_js.index("function currentFormSnapshot")
    ]
    assert "normalizeRestoredReviewState" in workspace_restore

    push_history = app_js[app_js.index("function pushHistory") : app_js.index("async function postJSON")]
    assert "const nextHistory" in push_history
    assert "if (!saveJSON" in push_history

    draft_check = app_js[app_js.index("function workspaceHasDraftContent") : app_js.index("function clearGenerateForm")]
    assert "state.lastResultImage" in draft_check
    assert "state.editImage" in draft_check
    assert "state.editMaskImage" in draft_check
    assert "creativeBriefSnapshot" in draft_check
    assert "DEFAULT_ITINERARY_TITLE" in draft_check

    clear_history = app_js[
        app_js.index('refs.clearHistoryButton.addEventListener("click"') : app_js.index(
            'refs.generateTab.addEventListener("click"'
        )
    ]
    assert "if (!saveJSON" in clear_history

    new_task = app_js[
        app_js.index('refs.newTaskButton.addEventListener("click"') : app_js.index(
            'refs.saveSettingsButton.addEventListener("click"'
        )
    ]
    assert "cancelPendingPromptConfirmation()" in new_task

    new_task_shortcut = app_js[
        app_js.rindex("if (", 0, app_js.index('event.key.toLowerCase() === "k"')) : app_js.index(
            'if (isTypingElement(document.activeElement))'
        )
    ]
    assert "isTypingElement(document.activeElement)" in new_task_shortcut
    assert "promptConfirmModal" in new_task_shortcut

    generated_detail = app_js[
        app_js.index("async function openGeneratedImageDetail") : app_js.index("function openGalleryLikeImage")
    ]
    assert "generatedImageDetailRequestSeq" in generated_detail
    assert "requestSeq !== state.generatedImageDetailRequestSeq" in generated_detail

    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="retryResultReviewButton"' in index_html
    assert "retrySelectedCandidateReview" in app_js

    shortcuts = app_js[app_js.index("// macOS 上 Option+数字") : app_js.index('if (event.key === "/")')]
    assert shortcuts.count("!isTypingElement(document.activeElement)") >= 3


def test_itinerary_coordinate_merge_prefers_exact_name_and_date() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function mergeItineraryCoordinateStops") : app_js.index("function itineraryCoordinateHelpText")
    ]
    expression = """
const textStops = [
  { date: "D1", name: "巴黎北站", transport: "" },
  { date: "D2", name: "巴黎", transport: "" },
  { date: "D3", name: "巴黎南站", transport: "" },
];
const coordinates = [
  { date: "D2", name: "巴黎", lat: 48.8566, lng: 2.3522, transport: "火车" },
];
const ambiguous = [
  { date: "", name: "巴黎", lat: 1, lng: 2, transport: "" },
];
console.log(JSON.stringify({
  exact: mergeItineraryCoordinateStops(textStops, coordinates),
  ambiguous: mergeItineraryCoordinateStops(
    [textStops[0], textStops[2]],
    ambiguous,
  ),
  conflictingDateAndName: mergeItineraryCoordinateStops(
    [
      { date: "D1", name: "巴黎", transport: "" },
      { date: "D2", name: "里昂", transport: "" },
    ],
    [{ date: "D2", name: "巴黎", lat: 9, lng: 10, transport: "火车" }],
  ),
  substringCollision: mergeItineraryCoordinateStops(
    [{ date: "D1", name: "东京都", transport: "" }],
    [{ date: "D1", name: "京都", lat: 35.0116, lng: 135.7681, transport: "火车" }],
  ),
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", f"{function_source}\n{expression}"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert "lat" not in result["exact"][0]
    assert result["exact"][1]["lat"] == 48.8566
    assert result["exact"][1]["transport"] == "火车"
    assert all("lat" not in stop for stop in result["ambiguous"])
    assert all("lat" not in stop for stop in result["conflictingDateAndName"])
    assert all("lat" not in stop for stop in result["substringCollision"])


def test_rerun_snapshot_merge_preserves_edits_made_while_request_is_running() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function isPlainSnapshotObject") : app_js.index("async function rerunLastGeneration")
    ]
    expression = """
const original = {
  generatePrompt: "draft prompt",
  quality: "high",
  generateSize: "1088x2240",
  generateSizePreset: "1088x2240",
  generateWidth: "1088",
  generateHeight: "2240",
  creativeBrief: { destination: "draft destination", mood: "draft mood" },
};
const baseline = {
  generatePrompt: "rerun prompt",
  quality: "low",
  generateSize: "1024x1024",
  generateSizePreset: "1024x1024",
  generateWidth: "1024",
  generateHeight: "1024",
  creativeBrief: { destination: "rerun destination", mood: "rerun mood" },
};
const latest = {
  generatePrompt: "new prompt typed while waiting",
  quality: "low",
  generateSize: "custom",
  generateSizePreset: "custom",
  generateWidth: "1536",
  generateHeight: "",
  creativeBrief: { destination: "rerun destination", mood: "new mood while waiting" },
};
console.log(JSON.stringify(mergeRerunDraftSnapshots(original, baseline, latest)));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", f"{function_source}\n{expression}"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "generatePrompt": "new prompt typed while waiting",
        "quality": "high",
        "generateSize": "custom",
        "generateSizePreset": "custom",
        "generateWidth": "1536",
        "generateHeight": "",
        "creativeBrief": {
            "destination": "draft destination",
            "mood": "new mood while waiting",
        },
    }


def test_hidden_size_radios_and_desktop_result_actions_cannot_expand_the_page() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    size_radio = styles_css[styles_css.index(".size-picker input {") : styles_css.index(".size-picker span {")]

    assert "width: 1px" in size_radio
    assert "height: 1px" in size_radio
    assert "min-height: 0" in size_radio
    assert "clip-path: inset(50%)" in size_radio
    assert "@media (min-width: 821px) and (max-width: 1600px)" in styles_css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in styles_css


def test_simple_itinerary_template_headers_are_not_parsed_as_route_stops() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    function_source = app_js[
        app_js.index("function isItineraryInstructionSection") : app_js.index(
            "function mergeItineraryCoordinateStops"
        )
    ]
    expression = """
const prompt = [
  "标题：北疆秋日之旅",
  "副标题/日期：9/5 - 9/12",
  "逐日行程：",
  "D1 乌鲁木齐 → 布尔津",
  "D2 布尔津 → 喀纳斯",
].join("\\n");
console.log(JSON.stringify(parseItineraryTextStops(prompt)));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", f"{function_source}\n{expression}"],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    stops = json.loads(completed.stdout)

    assert [stop["name"] for stop in stops] == ["乌鲁木齐", "布尔津", "喀纳斯"]
    assert all(stop["name"] != "9/12" for stop in stops)


def test_ui_mode_toggle_uses_the_primary_accent_palette() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    def declarations(selector: str) -> str:
        start = styles_css.index(f"{selector} {{")
        return styles_css[start : styles_css.index("\n}", start)]

    base = declarations(".ui-mode-toggle")
    assert "border-color: var(--ux-primary-8);" in base
    assert "background: var(--ux-primary-8);" in base
    assert "color: var(--ux-color-white);" in base
    assert "font-weight: var(--ux-font-weight-semibold);" in base

    hover = declarations(
        '.ux-button-secondary.ui-mode-toggle:hover:not(:disabled):not([aria-disabled="true"])'
        ':not([aria-busy="true"]):not(.is-loading)'
    )
    assert "background: var(--ux-primary-7);" in hover
    assert "color: var(--ux-color-white);" in hover

    active = declarations(
        '.ux-button-secondary.ui-mode-toggle:active:not(:disabled):not([aria-disabled="true"])'
        ':not([aria-busy="true"]):not(.is-loading)'
    )
    assert "background: var(--ux-primary-9);" in active
    assert "color: var(--ux-color-white);" in active

    focus = declarations(".ux-button-secondary.ui-mode-toggle:focus-visible")
    assert "box-shadow: var(--ux-focus-ring-primary);" in focus


def test_simple_mode_dom_and_existing_submit_path_contract() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    for element_id in (
        "uiModeToggleButton",
        "simpleModePanel",
        "simpleScenarioPicker",
        "simpleScenarioGrid",
        "simpleScenarioForm",
        "simpleScenarioFields",
        "simpleGenerateButton",
        "simpleFirstRunChecklist",
        "simpleResultSkeleton",
        "simpleResultEmpty",
        "simpleShareResultButton",
        "simpleMoreActionsButton",
        "simpleMoreActionsMenu",
        "resultPanelTitle",
        "resultPanelSubtitle",
    ):
        assert f'id="{element_id}"' in index_html

    assert "function applyUiMode(" in app_js
    assert "function renderSimpleScenarioCards(" in app_js
    assert "function renderSimpleScenarioForm(" in app_js
    assert "function assembleSimpleScenarioPrompt(" in app_js
    assert "async function submitSimpleScenario(" in app_js
    assert "await submitGenerate()" in app_js
    assert "await submitEdit()" in app_js
    assert "await submitAIItineraryMap()" in app_js
    assert "ui_mode: state.uiMode" in app_js
    assert "simpleDraft: simpleDraftSnapshot()" in app_js
    assert 'refs.resultPanelTitle.textContent = simple ? "成品预览" : "结果对比"' in app_js
    assert (
        'refs.resultPanelSubtitle.textContent = simple ? "生成完成后可放大查看" : "并排查看源图与结果图"'
        in app_js
    )
    assert '.replace(/([：:])(?=- )/g, "$1\\n")' in app_js
    assert "function currentSimpleListValues()" in app_js
    assert "const currentSelected = new Set(" in app_js
    assert 'view: "picker"' in app_js
    assert "function simpleScenarioAcceptsReferenceImage(" in app_js
    assert "preserveSceneRecipe" in app_js
    assert "function uiModePreferencesPayload()" in app_js
    initialize_mode = app_js[
        app_js.index("function initializeUiMode") : app_js.index("function renderPromptRecipeCards")
    ]
    assert "sync: false" in initialize_mode
    assemble_block = app_js[
        app_js.index("function assembleSimpleScenarioPrompt") : app_js.index("function simpleRequiredFieldMissing")
    ]
    assert ".filter((line, index)" not in assemble_block
    assert "templateLines" in assemble_block
    continue_edit = app_js[
        app_js.index("function continueEditingFromResult") : app_js.index("function startVariantFromResult")
    ]
    assert 'state.uiMode === "simple"' in continue_edit
    start_variant = app_js[
        app_js.index("function startVariantFromResult") : app_js.index("async function handleClipboardPaste")
    ]
    assert "void rerunLastGeneration()" in start_variant
    assert "right: calc(100% + var(--ux-space-2));" in styles_css
    assert "order: 99;" in styles_css
    assert "body.ui-simple-mode #resultPanel > .debug-panel" in styles_css
    assert "max-height: var(--ux-result-preview-max-height);" in styles_css


def test_simple_mode_scene_covers_and_official_icon_sprite_are_real_assets() -> None:
    icons_svg = (ROOT_DIR / "static" / "icons.svg").read_text(encoding="utf-8")

    assert icons_svg.count("<symbol ") == 30
    assert "Copyright (c) 2021 Bytedance" in icons_svg
    assert 'viewBox="0 0 48 48"' in icons_svg
    assert 'stroke="currentColor"' in icons_svg
    assert 'stroke-width="4"' in icons_svg

    for filename in (
        "scene-poster.jpg",
        "scene-itinerary.jpg",
        "scene-ranking.jpg",
        "scene-edit.jpg",
        "scene-free.jpg",
    ):
        payload = (ROOT_DIR / "static" / filename).read_bytes()
        assert payload.startswith(b"\xff\xd8\xff")
        assert len(payload) > 10_000


def test_simple_mode_css_uses_the_phase_zero_token_layer() -> None:
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert styles_css.count("--ux-primary-") >= 10
    simple_css = styles_css.split("/* Simple mode: start */", 1)[1].split("/* Simple mode: end */", 1)[0]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", simple_css)
    assert all(
        value.strip().startswith("var(")
        for value in re.findall(r"box-shadow:\s*([^;]+)", simple_css)
    )
    assert not re.search(r"(?:transition|animation)(?:-duration)?:\s*[^;]*(?:\d+ms|\d*\.\d+s)", simple_css)
    assert "var(--ux-" in simple_css
    assert ".simple-input:focus:not(:disabled)" in simple_css
    assert ".simple-textarea:focus:not(:disabled)" in simple_css
    assert ".simple-dynamic-input:focus:not(:disabled)" in simple_css
    checklist_css = simple_css[
        simple_css.index(".simple-first-run-checklist {") :
        simple_css.index(".simple-first-run-checklist header {")
    ]
    assert "width: 100%;" in checklist_css
    assert "position: fixed;" not in checklist_css
    assert "icons.svg#icon-" in (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")


def test_release_blocker_frontend_guards_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    auth_gate = app_js[app_js.index("function enterAuthGate") : app_js.index("function enterAppShell")]
    assert "self_registration_enabled" in auth_gate
    assert "registrationEnabled" in auth_gate
    auth_submit = app_js[
        app_js.index("async function submitAuthForm") : app_js.index("async function submitPasswordResetRequest")
    ]
    assert "authPayload.company" not in auth_submit
    assert auth_submit.index("await startAuthenticatedApp()") < auth_submit.index("enterAppShell()")

    invalidation = app_js[
        app_js.index("function invalidateUserContext") : app_js.index("function userContextIsCurrent")
    ]
    assert "state.preferenceSyncController?.abort()" in invalidation
    assert "state.preferenceSyncTail = Promise.resolve()" in invalidation
    assert "state.simpleChecklistCompletionTimer" in invalidation

    reset = app_js[app_js.index("function resetWorkspaceForUserScope") : app_js.index("function openWorkspaceDb")]
    assert "renderGalleryItems([])" in reset
    assert "renderSharedResults([])" in reset

    rerun = app_js[app_js.index("async function rerunLastGeneration") : app_js.index("function getGenerateSampleCount")]
    assert "const userContextEpoch = state.userContextEpoch" in rerun
    assert rerun.index("if (!userContextIsCurrent(userContextEpoch))") < rerun.index("const latestSnapshot")

    preference_sync = app_js[
        app_js.index("async function syncUserPreferences") : app_js.index("function getImageTransport")
    ]
    assert "signal: controller.signal" in preference_sync
    assert 'endpoint = "/api/preferences"' in preference_sync
    assert 'method = "PUT"' in preference_sync
    assert 'endpoint: "/api/preferences/ui-mode"' in app_js
    assert 'endpoint: "/api/preferences/simple-checklist"' in app_js

    checklist = app_js[app_js.index("function loadSimpleChecklistState") : app_js.index("function median")]
    assert "simple_checklist_completed" in checklist
    assert "const completionUserContextEpoch" in checklist
    assert "completionStorageKey" in checklist

    paste = app_js[app_js.index("async function handleClipboardPaste") : app_js.index("function bindPreviewTrigger")]
    assert "useSimpleImageFieldFile(recipe, imageField, file)" in paste

    simple_sync = app_js[
        app_js.index("function syncSimpleScenarioToProfessional") : app_js.index("async function submitSimpleScenario")
    ]
    assert "simpleEditSourceSize" in simple_sync
    upload = app_js[app_js.index("async function useImageFile") : app_js.index("async function useMaskFile")]
    assert "width:" in upload
    assert "height:" in upload
    assert 'createSpriteIcon("loading", "ux-icon simple-upload-loading")' in app_js

    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    assert ".simple-upload-zone:hover:not(:disabled):not([aria-busy=\"true\"])" in styles_css
    assert ".simple-upload-zone:active:not(:disabled):not([aria-busy=\"true\"])" in styles_css
    assert ".simple-upload-zone:disabled" in styles_css
    assert ".simple-upload-zone[aria-busy=\"true\"]" in styles_css


def test_file_reads_use_channel_scoped_latest_request_and_busy_lifecycle() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    state_block = app_js[app_js.index("const state = {") : app_js.index("const refs = {")]
    assert "latestFileReadEpoch: 0" in state_block
    assert "latestFileReadSequences: {}" in state_block
    assert "latestFileReadBusyChannels: new Set()" in state_block

    for channel in (
        'editImage: "edit-image"',
        'editMask: "edit-mask"',
        'styleReference: "style-reference"',
        'materialReference: "material-reference"',
        'generateReference: "generate-reference"',
    ):
        assert channel in app_js

    invalidation = app_js[
        app_js.index("function invalidateUserContext") : app_js.index("function userContextIsCurrent")
    ]
    assert "invalidateLatestFileReads()" in invalidation

    lifecycle = app_js[
        app_js.index("function latestFileReadChannelIsBusy") : app_js.index("function simpleImageAsset")
    ]
    assert "state.latestFileReadSequences[request.channel] === request.sequence" in lifecycle
    assert "request.userContextEpoch === state.userContextEpoch" in lifecycle
    assert "request.latestFileReadEpoch === state.latestFileReadEpoch" in lifecycle
    assert "request.contextIsCurrent?.() !== false" in lifecycle
    assert "error.staleLatestFileRead = true" in lifecycle
    assert "finishLatestFileRead(request)" in lifecycle
    assert "if (!latestFileReadRequestOwnsBusyState(request))" in lifecycle

    upload = app_js[
        app_js.index("async function useSimpleImageFieldFile") : app_js.index("function renderSimpleImageField")
    ]
    assert "await runLatestFileRead(" in upload
    assert "contextIsCurrent:" in upload
    assert 'state.simpleDraft.view === "form"' in upload
    assert "onApplied:" in upload

    reader_boundaries = (
        ("async function useImageFile", "async function useMaskFile", "setEditImage("),
        ("async function useMaskFile", "async function useGenerateReferenceFile", "setEditMaskImage("),
        (
            "async function useGenerateReferenceFile",
            "async function useStyleReferenceFile",
            "setGenerateReferenceImage(",
        ),
        ("async function useStyleReferenceFile", "async function useMaterialReferenceFile", "setStyleReferenceImage("),
        (
            "async function useMaterialReferenceFile",
            "async function submitVariantGenerate",
            "setMaterialReferenceImage(",
        ),
    )
    for start, end, setter in reader_boundaries:
        reader = app_js[app_js.index(start) : app_js.index(end)]
        assert "commitGuard = null" in reader
        assert reader.index("commitGuard?.()") < reader.index(setter)

    rendered_upload = app_js[
        app_js.index("function renderSimpleImageField") : app_js.index("function renderSimpleScenarioForm")
    ]
    assert "latestFileReadChannelForSimpleRecipe(recipe)" in rendered_upload
    assert "bindLatestFileReadControls(dropzone, input, channel)" in rendered_upload

    professional_bindings = app_js[app_js.index("function bindReferenceDropzone") : app_js.index("function bindEvents")]
    assert "runLatestFileRead(channel, file, handler)" in professional_bindings
    bind_events = app_js[app_js.index("function bindEvents") : app_js.index("async function init")]
    assert "FILE_READ_CHANNELS.styleReference" in bind_events
    assert "FILE_READ_CHANNELS.materialReference" in bind_events
    assert "FILE_READ_CHANNELS.editImage" in bind_events
    assert "FILE_READ_CHANNELS.editMask" in bind_events


def test_file_read_invalidation_covers_clear_auto_source_and_mode_changes() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    clear_reference = app_js[
        app_js.index("function clearGenerateReferenceImage") : app_js.index("function clearSourcePreview")
    ]
    assert "invalidateLatestFileReadChannels(" in clear_reference
    assert "FILE_READ_CHANNELS.styleReference" in clear_reference
    assert "FILE_READ_CHANNELS.materialReference" in clear_reference
    assert "FILE_READ_CHANNELS.generateReference" in clear_reference

    clear_mask = app_js[
        app_js.index("function clearEditMaskImage") : app_js.index("function useLastResultAsEditSource")
    ]
    assert "invalidateLatestFileReadChannel(FILE_READ_CHANNELS.editMask)" in clear_mask

    auto_source = app_js[app_js.index("function useLastResultAsEditSource") : app_js.index("function setMode")]
    assert "invalidateLatestFileReadChannel(FILE_READ_CHANNELS.editImage)" in auto_source

    set_mode = app_js[app_js.index("function setMode") : app_js.index("function canComparePreviews")]
    assert "invalidateLatestFileReads()" in set_mode

    apply_ui_mode = app_js[app_js.index("function applyUiMode") : app_js.index("function initializeUiMode")]
    assert "invalidateLatestFileReads()" in apply_ui_mode


def test_simple_picker_edit_upload_uses_latest_read_busy_and_loading_states() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    cards = app_js[
        app_js.index("function renderSimpleScenarioCards") : app_js.index("function handleSimpleEditImageFile")
    ]
    assert "bindLatestFileReadControls(card, refs.simpleEditImageInput, FILE_READ_CHANNELS.editImage)" in cards
    assert 'createSpriteIcon("loading", "ux-icon simple-scenario-card-loading")' in cards

    picker_upload = app_js[
        app_js.index("async function handleSimpleEditImageFile") : app_js.index("function showSimpleScenarioPicker")
    ]
    assert "await runLatestFileRead(" in picker_upload
    assert "FILE_READ_CHANNELS.editImage" in picker_upload
    assert "contextIsCurrent:" in picker_upload
    assert 'state.uiMode === "simple"' in picker_upload
    assert 'state.simpleDraft.view === "picker"' in picker_upload
    assert "onApplied:" in picker_upload

    assert ".simple-scenario-card-loading" in styles_css
    assert '.simple-scenario-card[aria-busy="true"] .simple-scenario-card-loading' in styles_css


def test_user_scoped_refreshes_ignore_stale_request_errors() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    function_boundaries = (
        ("async function refreshUsageSummary", "async function refreshImageStats"),
        ("async function refreshImageStats", "function updateAdminPanelVisibility"),
        ("async function refreshShareRecipients", "function showSharePanel"),
        ("async function refreshSharedResults", "function resetReviewStateForExternalResult"),
        ("async function refreshGenerationJobs", "async function openGeneratedImageDetail"),
        ("async function loadUserPreferences", "async function syncUserPreferences"),
    )
    for start, end in function_boundaries:
        block = app_js[app_js.index(start) : app_js.index(end)]
        assert "catch (error)" in block
        assert "if (error?.staleUserContext)" in block
        stale_guard = block.index("if (error?.staleUserContext)")
        assert block.index("return", stale_guard) > stale_guard


def test_latest_file_read_programmatic_sources_and_busy_controls_are_coordinated() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    set_busy = app_js[app_js.index("function setBusy") : app_js.index("function cancelActiveRequest")]
    assert "syncLatestFileReadControls()" in set_busy

    setter_expectations = (
        ("function setGenerateReferenceImage", "function setStyleReferenceImage", "generateReference"),
        ("function setStyleReferenceImage", "function setMaterialReferenceImage", "styleReference"),
        ("function setMaterialReferenceImage", "function clearGenerateReferenceImage", "materialReference"),
        ("function setEditImage", "function setEditMaskImage", "editImage"),
        ("function setEditMaskImage", "function clearEditMaskImage", "editMask"),
    )
    for start, end, channel in setter_expectations:
        setter = app_js[app_js.index(start) : app_js.index(end)]
        assert "preserveLatestFileRead = false" in setter
        assert f"invalidateLatestFileReadChannel(FILE_READ_CHANNELS.{channel})" in setter

    readers = app_js[app_js.index("async function useImageFile") : app_js.index("async function submitVariantGenerate")]
    assert readers.count("preserveLatestFileRead: true") == 5

    group_asset = app_js[
        app_js.index("function useGroupAssetAsReference") : app_js.index("async function refreshTeamChatGroupContext")
    ]
    assert "invalidateLatestFileReadChannels(" in group_asset
    assert "FILE_READ_CHANNELS.styleReference" in group_asset
    assert "FILE_READ_CHANNELS.materialReference" in group_asset

    result_commit = app_js[app_js.index("async function setResult") : app_js.index("function historySummary")]
    assert "invalidateLatestFileReadChannel(FILE_READ_CHANNELS.editImage)" in result_commit

    professional_dropzone = app_js[
        app_js.index("function bindReferenceDropzone") : app_js.index("function bindEvents")
    ]
    assert professional_dropzone.count("latestFileReadInteractionBlocked(channel)") >= 3
    bind_events = app_js[app_js.index("function bindEvents") : app_js.index("async function init")]
    assert bind_events.count("latestFileReadInteractionBlocked(FILE_READ_CHANNELS.editImage)") >= 3
    assert bind_events.count("latestFileReadInteractionBlocked(FILE_READ_CHANNELS.editMask)") >= 3
