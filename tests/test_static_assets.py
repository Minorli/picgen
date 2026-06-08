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
    assert "credentials: \"same-origin\"" in app_js
    assert "scopedStorageKey" in app_js
    assert "settingsStorageKey()" in app_js
    assert "historyStorageKey()" in app_js
    assert "workspaceStorageKey()" in app_js
    assert "enterAuthGate(" in app_js
    assert "enterAppShell()" in app_js
    assert "localStorage.setItem('token'" not in app_js
    assert "localStorage.setItem(\"token\"" not in app_js
    assert "submitChangePassword" in app_js
    assert ".change-password-dialog" in styles_css


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
    assert "refs.resultPreviewLabel.textContent = \"生成失败\"" in app_js
    assert ".preview-empty.failure" in styles_css


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
    assert "setDownloadPendingLogo" in app_js
    assert "成品保存中" in app_js
    assert "submitShareResult" in app_js
    assert "openSharedResult" in app_js
    assert ".share-result-panel" in styles_css
    assert ".share-recipient-search" in styles_css
    assert ".shared-result-item" in styles_css


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
    assert "AI 路线图" in index_html
    assert "AI 生成行程路线" in index_html
    assert 'id="copyItineraryTemplateButton"' in index_html
    assert 'id="applyItineraryTemplateButton"' in index_html
    assert "复制精细模板" in index_html
    assert "套用精细模板" in index_html
    assert "官方 LOGO 安全区" in index_html
    assert 'value="定制旅行路线图"' in index_html
    assert 'id="itinerarySubtitleInput" type="text" maxlength="160" placeholder="例如：5/12 - 5/24"' in index_html
    assert 'id="itineraryTitleInput" type="text" maxlength="120" value="新疆深度定制旅行"' not in index_html
    assert 'value="comic"' in index_html
    assert "漫画路线图" in index_html
    assert "默认按漫画风格路线图生成" in index_html
    assert index_html.index('<option value="1792x1792">方图 1792 x 1792</option>') < index_html.index(
        '<option value="1088x2240">6 人游竖版 1088 x 2240</option>'
    )
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

    assert "itineraryPanel: document.querySelector(\"#itineraryPanel\")" in app_js
    assert "itineraryDescriptionInput: document.querySelector(\"#itineraryDescriptionInput\")" in app_js
    assert "buildAIItineraryMapPrompt" in app_js
    assert "isCompleteItineraryPrompt" in app_js
    assert "完整行程地图 prompt" in app_js
    assert "return normalizedDescription" in app_js
    assert "stripCodeFence" in app_js
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
    assert "地点与地理校验" in app_js
    assert "copyDetailedItineraryTemplate" in app_js
    assert "applyDetailedItineraryTemplate" in app_js
    assert "shouldUseXinjiangRouteGuard" not in app_js
    assert "xinjiangRouteGuardPrompt" not in app_js
    assert "api/generate" in app_js
    assert "drawItineraryLogoSafeArea" in app_js
    assert "withLogoLayoutPrompt(aiPrompt, logoRequested)" in app_js
    assert "地理正确性硬性要求" in app_js
    assert "不能为了画面好看而调整地点相对位置" in app_js
    assert "库尔德宁" not in app_js
    assert "喀拉峻" not in app_js
    assert "伊宁" not in app_js
    assert "琼库什台" not in app_js
    assert "赛里木湖" not in app_js
    assert "喀什" not in app_js
    assert "日期必须逐日出现" in app_js
    assert "5/18" in app_js
    assert "每两个连续地点之间必须有路线连接" in app_js
    assert "必须标注大致距离或飞行/转场说明" in app_js
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
    assert 'transport: "images-generate"' in app_js
    itinerary_submit_block = app_js[
        app_js.index("async function submitAIItineraryMap()") : app_js.index('rememberRegenerationRequest("itinerary"')
    ]
    assert 'const result = await postJSON("api/generate"' in itinerary_submit_block
    assert 'mode: "itinerary"' in itinerary_submit_block
    assert "logo_requested: logoRequested" in itinerary_submit_block
    assert "行程描述不能为空" in app_js
    assert "不要让 AI 绘制或改造 6 人游 LOGO" in app_js
    assert "左上角预留干净白底 LOGO 安全区" in app_js
    assert "mode: \"itinerary\"" in app_js
    assert "COMPANY_LOGO_URL" in app_js
    assert "ensureCompanyLogoCanvas" not in app_js
    assert "parseItineraryStops" not in app_js
    assert "projectItineraryPoint" not in app_js
    assert "ITINERARY_MAP_FEATURES" not in app_js
    assert "setMode(\"itinerary\"" in app_js

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


def test_layout_review_fixes_keep_generation_path_quiet() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    assert "海报生成" in index_html
    assert "开始海报生成" in index_html
    assert "\"开始海报生成\"" in app_js
    assert "\"开始生成\"" not in app_js
    assert "--font: \"SF Pro Text\"" in styles_css
    assert "Inter" not in styles_css
    assert 'class="advanced-params"' in index_html
    assert '<summary>高级参数</summary>' in index_html
    assert 'id="generateSizePreset" hidden' in index_html
    assert 'id="logoOverlayEnabled"' in index_html
    assert 'href="#resultPanel"' not in index_html
    assert 'id="resultActions" class="result-actions hidden"' in index_html
    assert 'id="sourcePreviewCard" class="preview-card source-card hidden"' in index_html
    assert "setStatusMessage(\"已复制本次提示词。\")" in app_js
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
    assert "refs.teamChatMessageInput.value = \"\"" in app_js
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
    assert 'button.dataset.action = action' in app_js
    assert '"copy", "复制"' in app_js
    assert '"quote", "引用"' in app_js
    assert '"recall", "撤回"' in app_js
    assert "actions.push([\"recall\"" in app_js
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
    assert "!static/*.png" in dockerignore
    assert "env_file:" not in compose
    assert f"image: minorli/picgen:{version}" in compose
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
