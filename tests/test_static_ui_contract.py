from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "pc_drive_dashboard" / "static"


class StaticUiContractTests(unittest.TestCase):
    def test_app_branding_uses_gateway_dashboard_without_host_tag(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        app = (ROOT / "pc_drive_dashboard" / "app.py").read_text(encoding="utf-8")

        self.assertIn("<title>Gateway Dashboard</title>", html)
        self.assertIn("<h1>Gateway Dashboard</h1>", html)
        self.assertIn('rel="icon"', html)
        self.assertIn('rel="shortcut icon"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('/static/favicon-32.png', html)
        self.assertIn('/static/favicon-16.png', html)
        self.assertIn('/favicon.ico', html)
        self.assertIn('/static/app-icon.png', html)
        self.assertNotIn("PC Drive Dashboard", html)
        self.assertNotIn("Drive Dashboard</h1>", html)
        self.assertNotIn("LegacyHostName", html)
        self.assertNotIn('id="hostLabel"', html)
        self.assertNotIn("hostLabel", script)
        self.assertNotIn("LegacyHostName", script)
        self.assertIn('FastAPI(title="Gateway Dashboard"', app)

    def test_favicon_assets_are_real_logo_files(self):
        png_signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])

        self.assertTrue((STATIC / "app-icon.png").read_bytes().startswith(png_signature))
        self.assertTrue((STATIC / "favicon-16.png").read_bytes().startswith(png_signature))
        self.assertTrue((STATIC / "favicon-32.png").read_bytes().startswith(png_signature))
        self.assertEqual((STATIC / "favicon.ico").read_bytes()[:4], bytes([0, 0, 1, 0]))

    def test_explorer_uses_context_menu_instead_of_details_panel(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="contextMenu"', html)
        self.assertIn('class="context-menu hidden"', html)
        self.assertNotIn('class="panel details-panel"', html)
        self.assertNotIn('id="detailsList"', html)
        self.assertIn('addEventListener("contextmenu"', script)

    def test_visible_ui_has_no_placeholder_operations(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        app = (ROOT / "pc_drive_dashboard" / "app.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        combined = f"{html}\n{script}\n{app}\n{readme}"
        self.assertNotIn("intentionally disabled", combined)
        self.assertNotIn("placeholder", combined.lower())
        self.assertNotIn("/api/ops/preview", combined)
        self.assertNotIn("/api/ops/run", combined)

    def test_context_menu_actions_match_existing_working_apis(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        for action in ("preview", "open", "copy-windows", "copy-ssh", "copy-posix", "copy-name"):
            self.assertIn(f'data-context-action="{action}"', html)

        self.assertIn('action === "preview"', script)
        self.assertIn('"copy-posix": "posix"', script)
        self.assertIn('action === "open"', script)
        self.assertIn("copyToClipboard", script)
        self.assertIn('document.execCommand("copy")', script)
        self.assertIn('/api/file?path=', script)
        self.assertIn('/api/open', script)
        self.assertIn('/api/path/copy', script)

    def test_double_click_previews_files_without_opening_on_pc(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="previewOverlay"', html)
        self.assertIn('id="previewBody"', html)
        self.assertIn('id="previewCloseButton"', html)
        self.assertIn("previewDashboardItem", script)
        self.assertIn("previewFile", script)
        self.assertIn('row.addEventListener("dblclick", async () => previewDashboardItem(child));', script)
        self.assertNotIn('row.addEventListener("dblclick", async () => openPath(child.path));', script)
        self.assertIn('".heic"', script)
        self.assertIn('".avi"', script)
        self.assertIn("preview-overlay", styles)
        self.assertIn("preview-media", styles)
        self.assertIn("object-fit: contain", styles)
        self.assertIn("align-items: center", styles)
        self.assertIn("justify-content: center", styles)

    def test_single_click_opens_folders_only(self):
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        self.assertIn('row.addEventListener("click", async () => handleTreeRowClick(row, child));', script)
        self.assertIn("async function handleTreeRowClick(row, child)", script)
        self.assertIn('if (child.kind === "folder" || child.kind === "drive")', script)
        self.assertIn("await previewDashboardItem(child)", script)
        self.assertIn("setActiveRow(row, child)", script)
        self.assertNotIn('row.addEventListener("click", () => {\n      setActiveRow(row, child);\n    });', script)

    def test_context_menu_shows_media_preview_before_actions(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="contextPreview"', html)
        self.assertIn('class="context-preview hidden"', html)
        self.assertIn("renderContextPreview", script)
        self.assertIn("clearContextPreview", script)
        self.assertIn('className = `context-preview-media ${kind}`', script)
        self.assertIn("context-preview", styles)
        self.assertIn("context-preview-media", styles)
        self.assertIn("aspect-ratio: 16 / 10", styles)

    def test_preview_window_exposes_same_file_actions(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="previewActionsButton"', html)
        self.assertIn('aria-label="Preview actions"', html)
        self.assertIn('"previewActionsButton").addEventListener("click", showPreviewActions)', script)
        self.assertIn("async function showPreviewActions(event)", script)
        self.assertIn("state.currentPreviewPath", script)
        self.assertIn('await setContextTarget(state.currentPreviewPath, "file")', script)
        self.assertIn("renderContextPreview(state.contextTarget)", script)
        self.assertIn("positionContextMenu(rect.left, rect.bottom + 6)", script)
        self.assertIn("preview-actions-button", styles)
        self.assertIn("z-index: 30", styles)

    def test_preview_actions_capture_trigger_before_async_work(self):
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        function_start = script.index("async function showPreviewActions(event)")
        function_body = script[function_start : script.index("\nfunction positionContextMenu", function_start)]

        self.assertIn("const trigger = event.currentTarget;", function_body)
        self.assertIn("const rect = trigger.getBoundingClientRect();", function_body)

        rect_position = function_body.index("const rect = trigger.getBoundingClientRect();")
        async_position = function_body.index('await setContextTarget(state.currentPreviewPath, "file")')

        self.assertLess(rect_position, async_position)

    def test_preview_arrows_remain_inside_media_viewer_only(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="previewPreviousButton"', html)
        self.assertIn('id="previewNextButton"', html)
        self.assertNotIn('id="itemPreviousButton"', html)
        self.assertNotIn('id="itemNextButton"', html)

        self.assertIn("currentChildren", script)
        self.assertIn("currentPreviewPath", script)
        self.assertIn("previewAdjacent", script)
        self.assertNotIn("selectAdjacentItem", script)
        self.assertNotIn("itemPreviousButton", script)
        self.assertNotIn("itemNextButton", script)
        self.assertIn("activeItem", script)
        self.assertIn('event.key === "ArrowLeft"', script)
        self.assertIn('event.key === "ArrowRight"', script)
        self.assertIn('event.key === "ArrowUp"', script)
        self.assertIn('event.key === "ArrowDown"', script)
        self.assertIn('event.key === "Enter"', script)
        self.assertIn("preview-nav", styles)
        self.assertIn("preview-stage", styles)
        self.assertNotIn("item-nav-button", styles)

    def test_video_preview_has_visible_seek_volume_and_spacebar_controls(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertIn("video-controls-v1", html)
        self.assertIn("createVideoPlayer", script)
        self.assertIn("preview-video-controls", script)
        self.assertIn("video-seek", script)
        self.assertIn("video-volume", script)
        self.assertIn("handlePreviewSpacebar", script)
        self.assertIn('event.key === " " || event.code === "Space"', script)
        self.assertIn('previewKind(state.currentPreviewPath) === "video"', script)
        self.assertIn('previewKind(state.currentPreviewPath) === "image"', script)
        self.assertIn("togglePreviewVideo", script)
        self.assertIn("formatMediaTime", script)
        self.assertIn("preview-video-player", styles)
        self.assertIn("preview-video-controls", styles)
        self.assertIn("video-seek", styles)
        self.assertIn("video-volume", styles)

    def test_explorer_arrows_navigate_folder_levels_not_item_history(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="backButton"', html)
        self.assertIn('id="forwardButton"', html)
        self.assertIn('aria-label="Up one folder"', html)
        self.assertIn('aria-label="Open selected folder"', html)
        self.assertNotIn('id="parentButton"', html)
        self.assertIn('"backButton").addEventListener("click", loadParent)', script)
        self.assertIn('"forwardButton").addEventListener("click", openActiveFolder)', script)
        self.assertIn("function openActiveFolder()", script)
        self.assertIn("function isBrowsableFolder(item)", script)
        self.assertIn("selectAdjacentRow(-1)", script)
        self.assertIn("selectAdjacentRow(1)", script)
        self.assertIn("await loadParent()", script)
        self.assertIn("await openActiveFolder()", script)
        self.assertNotIn("loadBack", script)
        self.assertNotIn("loadForward", script)
        self.assertNotIn("pushHistory", script)
        self.assertNotIn("backStack", script)
        self.assertNotIn("forwardStack", script)

    def test_explorer_has_discoverable_navigation_and_actions(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="breadcrumb"', html)
        self.assertIn('id="backButton"', html)
        self.assertIn('id="forwardButton"', html)
        self.assertIn("loadParent", script)
        self.assertIn("openActiveFolder", script)
        self.assertNotIn("renderBreadcrumb", script)
        self.assertNotIn("${child.kind === \"folder\" ? \"Folder\" : \"File\"}", script)
        self.assertIn("row-icon", script)
        self.assertIn("row-action", script)
        self.assertIn("showContextMenu", script)
        self.assertIn('document.createElement("div")', script)
        self.assertNotIn('document.createElement("button");\n    row.className = "tree-row"', script)
        self.assertIn("min-height: 58px", styles)
        self.assertIn("grid-template-columns: 36px minmax(260px, 1fr) 180px 48px", styles)
        self.assertIn("width: 100%", styles)

    def test_shell_is_minimal_and_production_only(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        styles = (STATIC / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn('data-view="settings"', html)
        self.assertNotIn('id="settingsView"', html)
        self.assertNotIn('id="storageHealth"', html)
        self.assertNotIn('class="status-strip"', html)
        self.assertNotIn('id="authStatus"', html)
        self.assertNotIn('id="writeStatus"', html)
        self.assertNotIn("loadSettings", script)
        self.assertNotIn("loadStorageHealth", script)
        self.assertNotIn("loadSystem", script)
        self.assertNotIn("storageHealthTitle", script)
        self.assertNotIn("write_operations_enabled", script)
        self.assertIn('"refreshButton").addEventListener("click", loadDashboard)', script)
        self.assertIn('"/api/auth/logout"', script)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(132px, 1fr))", styles)
        self.assertIn("min-height: 108px", styles)


if __name__ == "__main__":
    unittest.main()
