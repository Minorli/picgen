import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "static" / "styles.css"
START_MARKER = "/* C6 simple shell: start */"
END_MARKER = "/* C6 simple shell: end */"


def _shell_styles() -> str:
    css = STYLES.read_text(encoding="utf-8")
    assert START_MARKER in css
    assert END_MARKER in css
    return css.split(START_MARKER, 1)[1].split(END_MARKER, 1)[0]


def _declarations(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}", css)
    assert match is not None, f"missing selector: {selector}"
    return match.group("body")


def test_c6_shell_styles_are_scoped_to_simple_mode_and_use_ux_tokens() -> None:
    css = _shell_styles()

    selectors = re.findall(r"(?:^|\})\s*([^{}]+)\{", css)
    assert selectors
    for selector_group in selectors:
        selectors_in_group = [selector.strip() for selector in selector_group.split(",")]
        assert all(selector.startswith("body.ui-simple-mode ") for selector in selectors_in_group)

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|\b\d+(?:\.\d+)?px\b", css)
    assert not re.search(r"var\(--(?:line|green|muted|panel|radius|shadow|text)\b", css)


def test_c6_shell_covers_topbar_status_preview_and_footer() -> None:
    css = _shell_styles()

    topbar = _declarations(css, "body.ui-simple-mode .app-topbar")
    assert "border-color: var(--ux-border-2);" in topbar
    assert "background: var(--ux-bg-2);" in topbar

    controls = _declarations(
        css,
        "body.ui-simple-mode .topbar-tools > .ghost-button,\nbody.ui-simple-mode .topbar-tools > .system-pill",
    )
    assert "min-height: var(--ux-control-height);" in controls
    assert "border-radius: var(--ux-radius-control);" in controls
    assert "font-weight: var(--ux-font-weight-medium);" in controls

    status = _declarations(css, "body.ui-simple-mode .status-badge")
    assert "background: var(--ux-success-light);" in status
    assert "color: var(--ux-success-text);" in status

    result_panel = _declarations(css, "body.ui-simple-mode #resultPanel")
    assert "border-color: var(--ux-color-transparent);" in result_panel
    assert "box-shadow: var(--ux-shadow-none);" in result_panel

    preview_card = _declarations(css, "body.ui-simple-mode .preview-card")
    assert "border-color: var(--ux-border-2);" in preview_card
    assert "box-shadow: var(--ux-shadow-card-rest);" in preview_card

    footer = _declarations(css, "body.ui-simple-mode .system-footer")
    assert "border-color: var(--ux-border-2);" in footer
    assert "color: var(--ux-text-3);" in footer
