from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_logo_overlay_uses_uploaded_asset_without_ai_guidance() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    logo_png = ROOT_DIR / "static" / "6renyou.png"
    logo_bytes = logo_png.read_bytes()
    assert logo_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert logo_bytes[12:16] == b"IHDR"
    assert logo_bytes[25] == 6
    assert 'const COMPANY_LOGO_URL = "6renyou.png"' in app_js
    assert "composeLogoOverlayForCandidates" in app_js
    assert "createOfficialLogoCanvas" in app_js
    assert "hasTransparentLogoBackground" in app_js
    assert "resizeCanvasHighQuality" in app_js
    assert "applyLogoOverlayToDataUrl" in app_js
    assert "withLogoLayoutPrompt" in app_js
    assert "官方透明 PNG 原样贴入" in app_js
    assert "图标、字体、颜色和比例均不得改动" in app_js
    assert "LOGO 位置附近保留干净留白" in app_js
    assert "logo_text_color" in app_js
    assert 'textColor: "original"' in app_js
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


def test_auth_overlay_supports_open_registration_and_cookie_sessions() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert '<body class="auth-gate">' in index_html
    assert 'id="authOverlay"' in index_html
    assert 'class="auth-page"' in index_html
    assert 'id="loginAuthButton"' in index_html
    assert 'id="registerAuthButton"' in index_html
    assert "注册" in index_html
    assert 'id="logoutButton"' in index_html
    assert 'id="userUsageSummary"' in index_html
    assert 'id="adminPanel"' in index_html
    assert 'id="adminCreateUserForm"' in index_html
    assert 'id="adminUsersList"' in index_html
    assert "body.auth-gate .desktop-shell" in styles_css
    assert ".admin-panel" in styles_css
    assert "/api/auth/login" in app_js
    assert "/api/auth/register" in app_js
    assert "/api/auth/logout" in app_js
    assert "/api/admin/users" in app_js
    assert "/api/me" in app_js
    assert "/api/usage" in app_js
    assert "credentials: \"same-origin\"" in app_js
    assert "scopedStorageKey" in app_js
    assert "settingsStorageKey()" in app_js
    assert "historyStorageKey()" in app_js
    assert "workspaceStorageKey()" in app_js
    assert "enterAuthGate(" in app_js
    assert "enterAppShell()" in app_js
    assert "localStorage.setItem('token'" not in app_js
    assert "localStorage.setItem(\"token\"" not in app_js


def test_result_preview_zoom_and_feedback_controls_are_present() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="previewZoomInButton"' in index_html
    assert 'id="previewZoomOutButton"' in index_html
    assert 'id="previewZoomResetButton"' in index_html
    assert 'id="openResultPreviewButton"' in index_html
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


def test_copyright_risk_state_survives_workspace_restore() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    assert "copyrightRisk: state.copyrightRisk" in app_js
    assert "state.copyrightRisk = result.copyrightRisk" in app_js
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
    assert "submitShareResult" in app_js
    assert "openSharedResult" in app_js
    assert ".share-result-panel" in styles_css
    assert ".share-recipient-search" in styles_css
    assert ".shared-result-item" in styles_css


def test_layout_review_fixes_keep_generation_path_quiet() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert "--font: \"SF Pro Text\"" in styles_css
    assert "Inter" not in styles_css
    assert 'class="advanced-params"' in index_html
    assert '<summary>高级参数</summary>' in index_html
    assert 'id="generateSizePreset" hidden' in index_html
    assert 'id="logoOverlayEnabled"' in index_html
    assert 'id="resultActions" class="result-actions hidden"' in index_html
    assert 'id="sourcePreviewCard" class="preview-card source-card hidden"' in index_html
    assert "setStatusMessage(\"已复制本次提示词。\")" in app_js
    assert "flowConnect" not in app_js
    assert "setFlowState" not in app_js
    assert 'id="toastMessage"' in index_html
    assert ".toast-message" in styles_css
    assert 'class="comparison-grid single-result"' in index_html
    assert "集成 6 人游 LOGO" in index_html
    assert ".comparison-grid.single-result" in styles_css


def test_password_reset_ui_is_admin_assisted() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="forgotPasswordButton"' in index_html
    assert 'id="passwordResetRequestForm"' in index_html
    assert 'id="adminPasswordResetPanel"' in index_html
    assert 'id="passwordResetRequestsList"' in index_html
    assert "/api/password-reset-requests" in app_js
    assert "/api/admin/password-reset-requests" in app_js
    assert "submitPasswordResetAdminForm" in app_js
    assert ".password-reset-admin-form" in styles_css
    assert "申请已提交，请联系管理员" in app_js


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


def test_docker_packaging_excludes_local_env_and_persists_container_data() -> None:
    dockerignore = (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    build_script = (ROOT_DIR / "scripts" / "docker-build-push.sh").read_text(encoding="utf-8")

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "data/" in dockerignore
    assert "/*.png" in dockerignore
    assert "!static/*.png" in dockerignore
    assert "env_file:" not in compose
    assert "image: minorli/picgen:0.1.14" in compose
    assert "picgen-data:/app/data" in compose
    assert "VOLUME [\"/app/data\"]" in dockerfile
    assert "PICGEN_STATIC_DIR=/app/static" in dockerfile
    assert "PICGEN_ROOT_DIR=/app" in dockerfile
    assert "PICGEN_ENV_FILE=/app/data/.env" in dockerfile
    assert "PICGEN_AUTH_DB_PATH" not in dockerfile
    assert "apt-get" not in dockerfile
    assert "curl" not in dockerfile
    assert "urllib.request.urlopen" in dockerfile
    assert "https://sub.tidba.com/v1/images/generations" in dockerfile
    assert "https://sub.tidba.com/v1/images/edits" in dockerfile
    assert "https://sub.tidba.com/v1/responses" in dockerfile
    assert 'IMAGE="${IMAGE:-minorli/picgen}"' in build_script
    assert 'VERSION="${VERSION:-0.1.14}"' in build_script
    assert "--push" in build_script


def test_static_footer_version_matches_release() -> None:
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert "PicGen Console　v0.1.14" in index_html
    assert "PicGen Console　v0.1.2" not in index_html
