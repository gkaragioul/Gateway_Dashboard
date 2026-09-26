const state = {
  authenticated: false,
  configured: false,
  contextTarget: null,
  currentPath: null,
  currentChildren: [],
  locations: [],
  activePath: null,
  currentPreviewPath: null,
  uploadTargetPath: null,
  fileClipboard: null,
  uploadProgress: null,
  uploadProgressTimer: null,
};

const $ = (id) => document.getElementById(id);

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )pcdd_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = csrfToken();
  }
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {
      // Keep the HTTP status text.
    }
    throw new Error(message);
  }
  return response.json();
}

async function boot() {
  bindEvents();
  const auth = await api("/api/auth/state");
  state.authenticated = auth.authenticated;
  state.configured = auth.configured;
  state.setupRequiresCode = Boolean(auth.setup_requires_code);
  updateAuthView();
  if (state.authenticated) {
    await loadDashboard();
  }
}

function bindEvents() {
  $("authForm").addEventListener("submit", handleAuth);
  $("refreshButton").addEventListener("click", loadDashboard);
  $("logoutButton").addEventListener("click", logout);
  $("currentFolderActionsButton").addEventListener("click", showCurrentFolderActions);
  $("treeList").addEventListener("contextmenu", showCurrentFolderActions);
  $("backButton").addEventListener("click", loadParent);
  $("forwardButton").addEventListener("click", openActiveFolder);
  $("refreshLogsButton").addEventListener("click", loadLogs);
  $("previewCloseButton").addEventListener("click", closePreview);
  $("previewActionsButton").addEventListener("click", showPreviewActions);
  $("previewPreviousButton").addEventListener("click", () => previewAdjacent(-1));
  $("previewNextButton").addEventListener("click", () => previewAdjacent(1));
  $("uploadInput").addEventListener("change", handleUploadSelection);
  $("previewOverlay").addEventListener("click", (event) => {
    if (event.target === $("previewOverlay")) closePreview();
  });
  document.querySelectorAll("[data-context-action]").forEach((button) => {
    button.addEventListener("click", () => contextAction(button.dataset.contextAction));
  });
  document.addEventListener("click", (event) => {
    if (!$("contextMenu").contains(event.target)) hideContextMenu();
  });
  document.addEventListener("keydown", async (event) => {
    if (event.key === "Escape") {
      hideContextMenu();
      closePreview();
      return;
    }
    await handleKeyboardNavigation(event);
  });
  window.addEventListener("resize", hideContextMenu);
  window.addEventListener("scroll", hideContextMenu, true);
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
}

function updateAuthView() {
  const needsSetup = !state.configured;
  const needsSetupCode = needsSetup && state.setupRequiresCode;
  $("authTitle").textContent = needsSetup ? "Create dashboard password" : "Login";
  $("authCopy").textContent = needsSetupCode
    ? "Finish setup on the PC: enter the one-time setup code from setup-code.txt in the dashboard's config folder on the PC (also printed in the server log), or create the password in a browser on the PC itself."
    : needsSetup
      ? "Set the first dashboard password. Only a salted hash is written to the PC config."
      : "Enter the dashboard password for this browser session.";
  $("setupCodeField")?.classList.toggle("hidden", !needsSetupCode);
  if ($("setupCodeInput")) $("setupCodeInput").required = needsSetupCode;
  $("authView").classList.toggle("hidden", state.authenticated);
  document.querySelectorAll(".view").forEach((view) => {
    const name = view.id.replace(/View$/, "");
    const activeName = document.querySelector(".nav-button.active")?.dataset.view || "explorer";
    view.classList.toggle("hidden", !state.authenticated || name !== activeName);
  });
}

async function handleAuth(event) {
  event.preventDefault();
  $("authError").textContent = "";
  const password = $("passwordInput").value;
  const remember = $("rememberInput").checked;
  const path = state.configured ? "/api/auth/login" : "/api/auth/setup";
  const payload = {
    password,
    remember,
    device_name: navigator.userAgent.slice(0, 110) || "Browser",
  };
  if (!state.configured) payload.setup_code = $("setupCodeInput")?.value || "";
  try {
    await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.authenticated = true;
    state.configured = true;
    $("passwordInput").value = "";
    if ($("setupCodeInput")) $("setupCodeInput").value = "";
    updateAuthView();
    await loadDashboard();
  } catch (error) {
    $("authError").textContent = error.message;
  }
}

async function loadDashboard() {
  await Promise.all([loadDrives(), loadLocations()]);
  if (state.currentPath) {
    await loadPath(state.currentPath);
  }
}

async function loadDrives() {
  const data = await api("/api/drives");
  const grid = $("driveGrid");
  grid.innerHTML = "";
  data.drives.forEach((drive) => {
    const usedPercent = drive.total ? Math.round(((drive.total - drive.free) / drive.total) * 100) : 0;
    const button = document.createElement("button");
    button.className = `drive-card ${drive.available ? "" : "unavailable"}`;
    button.disabled = !drive.available;
    button.innerHTML = `
      <strong>${escapeHtml(drive.letter)}:</strong>
      <span>${escapeHtml(drive.label)}</span>
      <small>${escapeHtml(drive.role)}</small>
      <div class="meter"><div style="width:${usedPercent}%"></div></div>
      <small>${drive.available ? `${formatBytes(drive.free)} free` : escapeHtml(drive.warning || "Unavailable")}</small>
    `;
    button.addEventListener("click", () => loadPath(drive.path));
    button.addEventListener("contextmenu", (event) => showContextMenu(event, drive.path, "drive"));
    grid.appendChild(button);
  });
}

async function loadLocations() {
  const data = await api("/api/locations");
  state.locations = data.locations || [];
  renderQuickLocations();
}

function renderQuickLocations() {
  const container = $("quickLocations");
  container.innerHTML = "";
  container.classList.toggle("hidden", !state.locations.length);
  state.locations.forEach((location) => {
    const item = document.createElement("div");
    item.className = "quick-location";
    item.addEventListener("contextmenu", (event) => showContextMenu(event, location.path, location.kind || "folder"));

    const button = document.createElement("button");
    button.type = "button";
    button.className = "quick-location-button";
    button.textContent = location.name;
    button.title = location.path;
    button.addEventListener("click", () => loadPath(location.path));

    const action = document.createElement("button");
    action.type = "button";
    action.className = "quick-location-action";
    action.textContent = "...";
    action.title = `${location.name} actions`;
    action.setAttribute("aria-label", `${location.name} actions`);
    action.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = action.getBoundingClientRect();
      showContextMenu(event, location.path, location.kind || "folder", null, rect.left, rect.bottom + 6);
    });

    item.append(button, action);
    container.appendChild(item);
  });
}

async function loadPath(path) {
  $("treeList").innerHTML = `<div class="tree-row"><span class="row-kind">Load</span><span class="row-name">${escapeHtml(path)}</span></div>`;
  try {
    const data = await api(`/api/tree?path=${encodeURIComponent(path)}&page_size=300`);
    state.currentPath = data.path;
    state.currentChildren = data.children;
    state.activePath = data.children.some((child) => child.path === state.activePath) ? state.activePath : null;
    state.currentPreviewPath = data.children.some((child) => child.path === state.currentPreviewPath) ? state.currentPreviewPath : null;
    $("currentPath").textContent = data.path;
    updateExplorerNavButtons();
    renderTree(data.children, data.total);
    updateExplorerNavButtons();
    updatePreviewNavButtons();
    state.contextTarget = null;
    hideContextMenu();
  } catch (error) {
    $("treeList").innerHTML = `<div class="tree-row"><span class="row-kind">Error</span><span class="row-name">${escapeHtml(error.message)}</span></div>`;
  }
}

function renderTree(children, total) {
  const list = $("treeList");
  list.innerHTML = "";
  if (!children.length) {
    list.innerHTML = `<div class="tree-row"><span class="row-kind">Empty</span><span class="row-name">No children found</span></div>`;
    updateExplorerNavButtons();
    return;
  }
  children.forEach((child, index) => {
    const row = document.createElement("div");
    row.className = "tree-row";
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    row.dataset.path = child.path;
    row.dataset.kind = child.kind;
    row.dataset.index = String(index);
    if (child.path === state.activePath) row.classList.add("active");
    row.innerHTML = `
      <span class="row-icon ${child.kind}" aria-hidden="true"></span>
      <span class="row-name" title="${escapeHtml(child.path)}">${escapeHtml(child.name)}</span>
      <span class="row-meta">${child.modified ? new Date(child.modified * 1000).toLocaleString() : ""}</span>
      <span class="row-action" title="Actions" aria-label="Actions">...</span>
    `;
    row.addEventListener("click", async () => handleTreeRowClick(row, child));
    row.addEventListener("dblclick", async () => previewDashboardItem(child));
    row.addEventListener("contextmenu", (event) => showContextMenu(event, child.path, child.kind, row));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        previewDashboardItem(child);
        return;
      }
      if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
        event.preventDefault();
        const rect = row.getBoundingClientRect();
        showContextMenu(event, child.path, child.kind, row, rect.left + 28, rect.top + 28);
      }
    });
    row.querySelector(".row-action").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = event.currentTarget.getBoundingClientRect();
      showContextMenu(event, child.path, child.kind, row, rect.left, rect.bottom + 6);
    });
    list.appendChild(row);
  });
  if (children.length < total) {
    const more = document.createElement("div");
    more.className = "tree-row";
    more.innerHTML = `<span class="row-kind">More</span><span class="row-name">${children.length} of ${total} shown</span>`;
    list.appendChild(more);
  }
}

async function handleTreeRowClick(row, child) {
  if (child.kind === "folder" || child.kind === "drive") {
    await previewDashboardItem(child);
    return;
  }
  setActiveRow(row, child);
}

function setActiveRow(row) {
  document.querySelectorAll(".tree-row.active").forEach((item) => item.classList.remove("active"));
  if (row) {
    row.classList.add("active");
    state.activePath = row.dataset.path || null;
    row.scrollIntoView({ block: "nearest" });
  } else {
    state.activePath = null;
  }
  updateExplorerNavButtons();
}

async function setContextTarget(path, kind) {
  const variants = await api("/api/path/copy", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
  state.contextTarget = {
    path,
    kind,
    name: variants.name,
    variants,
  };
}

async function showContextMenu(event, path, kind, row = null, x = event.clientX, y = event.clientY) {
  event.preventDefault();
  event.stopPropagation();
  setActiveRow(row);
  try {
    await setContextTarget(path, kind);
    renderContextPreview(state.contextTarget);
    updateContextActions(state.contextTarget);
    positionContextMenu(x, y);
  } catch (error) {
    toast(error.message);
  }
}

async function showPreviewActions(event) {
  event.preventDefault();
  event.stopPropagation();
  const trigger = event.currentTarget;
  if (!trigger || !state.currentPreviewPath) return;
  const rect = trigger.getBoundingClientRect();

  try {
    await setContextTarget(state.currentPreviewPath, "file");
    renderContextPreview(state.contextTarget);
    updateContextActions(state.contextTarget);
    positionContextMenu(rect.left, rect.bottom + 6);
  } catch (error) {
    toast(error.message);
  }
}

async function showCurrentFolderActions(event) {
  event.preventDefault();
  event.stopPropagation();
  if (!state.currentPath) return;

  let x = event.clientX;
  let y = event.clientY;
  if (event.type === "click") {
    const rect = event.currentTarget.getBoundingClientRect();
    x = rect.left;
    y = rect.bottom + 6;
  }

  try {
    setActiveRow(null);
    const targetKind = isDriveRoot(state.currentPath) ? "drive" : "folder";
    await setContextTarget(state.currentPath, targetKind);
    renderContextPreview(state.contextTarget);
    updateContextActions(state.contextTarget);
    positionContextMenu(x, y);
  } catch (error) {
    toast(error.message);
  }
}

function positionContextMenu(x, y) {
  const menu = $("contextMenu");
  menu.classList.remove("hidden");
  menu.style.left = "0px";
  menu.style.top = "0px";
  const rect = menu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - rect.width - 8);
  const top = Math.min(y, window.innerHeight - rect.height - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
  const firstAction = menu.querySelector("button");
  if (firstAction) firstAction.focus({ preventScroll: true });
}

function hideContextMenu() {
  $("contextMenu").classList.add("hidden");
  clearContextPreview();
  updateContextActions(null);
}

function updateContextActions(target) {
  const canReceiveItems = target && (target.kind === "folder" || target.kind === "drive");
  const isDrive = target && target.kind === "drive";
  document.querySelectorAll("[data-folder-action='upload']").forEach((button) => {
    button.classList.toggle("hidden", !canReceiveItems);
  });
  document.querySelectorAll("[data-clipboard-action='paste']").forEach((button) => {
    button.classList.toggle("hidden", !canReceiveItems || !state.fileClipboard);
    if (state.fileClipboard && canReceiveItems) {
      button.textContent = `${state.fileClipboard.mode === "cut" ? "Move" : "Copy"} ${state.fileClipboard.name} here`;
    } else {
      button.textContent = "Paste here";
    }
  });
  document.querySelectorAll("[data-destructive-action='delete']").forEach((button) => {
    button.classList.toggle("hidden", !target || isDrive);
  });
  document.querySelectorAll("[data-context-action='copy-item'], [data-context-action='cut-item']").forEach((button) => {
    button.classList.toggle("hidden", !target || isDrive);
  });
}

function renderContextPreview(target) {
  const preview = $("contextPreview");
  clearContextPreview();
  if (!target || target.kind === "folder" || target.kind === "drive") return;

  const kind = previewKind(target.path);
  const name = target.name || fileNameFromPath(target.path);
  const url = `/api/file?path=${encodeURIComponent(target.path)}`;
  let media = null;

  if (kind === "image") {
    media = document.createElement("img");
    media.alt = name;
  } else if (kind === "video") {
    media = document.createElement("video");
    media.muted = true;
    media.preload = "metadata";
    media.playsInline = true;
  }

  if (media) {
    media.className = `context-preview-media ${kind}`;
    media.src = url;
    preview.appendChild(media);
  }

  const label = document.createElement("div");
  label.className = "context-preview-label";
  label.innerHTML = `
    <strong>${escapeHtml(name)}</strong>
    <span>${escapeHtml(contextPreviewLabel(kind))}</span>
  `;
  preview.appendChild(label);
  preview.classList.remove("hidden");
}

function clearContextPreview() {
  const preview = $("contextPreview");
  if (!preview) return;
  preview.innerHTML = "";
  preview.classList.add("hidden");
}

function contextPreviewLabel(kind) {
  if (kind === "image") return "Image preview";
  if (kind === "video") return "Video preview";
  if (kind === "audio") return "Audio file";
  if (kind === "pdf") return "PDF document";
  if (kind === "text") return "Text document";
  return "File";
}

async function loadParent() {
  if (!state.currentPath || isDriveRoot(state.currentPath)) return;
  const trimmed = state.currentPath.replace(/\\+$/, "");
  const parent = trimmed.slice(0, trimmed.lastIndexOf("\\") + 1);
  await loadPath(parent || `${state.currentPath[0]}:\\`);
}

function updateExplorerNavButtons() {
  $("currentFolderActionsButton").disabled = !state.currentPath;
  $("backButton").disabled = !state.currentPath || isDriveRoot(state.currentPath);
  $("forwardButton").disabled = !isBrowsableFolder(activeItem());
}

function activeIndex() {
  return state.currentChildren.findIndex((item) => item.path === state.activePath);
}

function activeItem() {
  const index = activeIndex();
  return index >= 0 ? state.currentChildren[index] : null;
}

function fileItems() {
  return state.currentChildren.filter((item) => item.kind === "file");
}

function selectAdjacentRow(delta) {
  if (!state.currentChildren.length) return;
  const currentIndex = activeIndex();
  const nextIndex = Math.min(
    Math.max((currentIndex >= 0 ? currentIndex : delta > 0 ? -1 : state.currentChildren.length) + delta, 0),
    state.currentChildren.length - 1
  );
  selectItemAtIndex(nextIndex);
}

function selectItemAtIndex(index) {
  const item = state.currentChildren[index];
  if (!item) return;
  const row = rowForPath(item.path);
  if (row) {
    setActiveRow(row);
    row.focus({ preventScroll: true });
  } else {
    state.activePath = item.path;
    updateExplorerNavButtons();
  }
}

function selectRowByPath(path) {
  const row = rowForPath(path);
  if (row) {
    setActiveRow(row);
    return;
  }
  if (state.currentChildren.some((item) => item.path === path)) {
    state.activePath = path;
    updateExplorerNavButtons();
  }
}

function rowForPath(path) {
  return Array.from(document.querySelectorAll(".tree-row")).find((row) => row.dataset.path === path) || null;
}

function previewAdjacent(delta) {
  const files = fileItems();
  if (!files.length) return;
  let index = files.findIndex((item) => item.path === state.currentPreviewPath);
  if (index < 0) index = files.findIndex((item) => item.path === state.activePath);
  const nextIndex = Math.min(Math.max((index >= 0 ? index : delta > 0 ? -1 : files.length) + delta, 0), files.length - 1);
  const next = files[nextIndex];
  if (!next || next.path === state.currentPreviewPath) return;
  selectRowByPath(next.path);
  previewFile(next.path, next.name);
}

function updatePreviewNavButtons() {
  const files = fileItems();
  const index = files.findIndex((item) => item.path === state.currentPreviewPath);
  $("previewPreviousButton").disabled = index <= 0;
  $("previewNextButton").disabled = !files.length || index >= files.length - 1;
}

async function handleKeyboardNavigation(event) {
  if (shouldIgnoreKeyboardNavigation(event) || $("contextMenu").classList.contains("hidden") === false) return;
  const previewOpen = !$("previewOverlay").classList.contains("hidden");

  if (previewOpen) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      previewAdjacent(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      previewAdjacent(1);
    }
    if (event.key === " " || event.code === "Space") {
      event.preventDefault();
      handlePreviewSpacebar();
    }
    return;
  }

  if ($("explorerView").classList.contains("hidden") || !state.authenticated) return;
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    await loadParent();
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    await openActiveFolder();
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    selectAdjacentRow(-1);
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    selectAdjacentRow(1);
  }
  if (event.key === "Enter") {
    const item = activeItem();
    if (!item) return;
    event.preventDefault();
    previewDashboardItem(item);
  }
}

function shouldIgnoreKeyboardNavigation(event) {
  const tagName = event.target?.tagName?.toLowerCase();
  return (
    ["button", "input", "textarea", "select"].includes(tagName) ||
    event.target?.closest?.(".preview-video-controls") ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey
  );
}

function isDriveRoot(path) {
  return /^[A-Z]:\\$/i.test(path);
}

async function contextAction(action) {
  const target = state.contextTarget;
  hideContextMenu();
  if (!target) return;
  if (action === "preview") {
    await previewDashboardItem(target);
    return;
  }
  if (action === "open") {
    await openPath(target.path);
    return;
  }
  if (action === "upload") {
    chooseUploadFiles(target);
    return;
  }
  if (action === "download") {
    downloadToMac(target);
    return;
  }
  if (action === "copy-item") {
    setFileClipboard(target, "copy");
    return;
  }
  if (action === "cut-item") {
    setFileClipboard(target, "cut");
    return;
  }
  if (action === "paste-item") {
    await pasteClipboardInto(target.path);
    return;
  }
  if (action === "delete-item") {
    await deleteRemoteItem(target);
    return;
  }
  const variantByAction = {
    "copy-windows": "windows",
    "copy-ssh": "ssh",
    "copy-posix": "posix",
    "copy-name": "name",
  };
  const variant = variantByAction[action];
  if (!variant) return;
  await copyToClipboard(target.variants[variant]);
  toast(`Copied ${variant} path`);
}

async function copyToClipboard(value) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (_) {
      // Fall back for browsers that expose the API but reject this origin.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard copy failed");
}

function chooseUploadFiles(target) {
  if (!target || (target.kind !== "folder" && target.kind !== "drive")) return;
  state.uploadTargetPath = target.path;
  const input = $("uploadInput");
  input.value = "";
  input.click();
}

async function handleUploadSelection(event) {
  const input = event.currentTarget;
  const targetPath = state.uploadTargetPath;
  const files = Array.from(input.files || []);
  state.uploadTargetPath = null;
  input.value = "";
  if (!targetPath || !files.length) return;

  let uploaded = 0;
  for (const file of files) {
    try {
      updateUploadProgress(file, 0, file.size, `Queued ${uploaded + 1}/${files.length}`);
      await uploadFileToPath(targetPath, file, (loaded, total) => {
        updateUploadProgress(file, loaded, total, `Uploading ${uploaded + 1}/${files.length}`);
      });
      uploaded += 1;
      updateUploadProgress(file, file.size, file.size, `Uploaded ${uploaded}/${files.length}`);
      toast(`Uploaded ${uploaded}/${files.length}: ${file.name}`);
    } catch (error) {
      updateUploadProgress(file, 0, file.size, `Failed: ${error.message}`);
      toast(`Upload failed: ${file.name}: ${error.message}`);
      break;
    }
  }

  if (uploaded) {
    await loadPath(targetPath);
    toast(`Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"} to ${targetPath}`);
    scheduleTransferPanelHide();
  }
}

function updateUploadProgress(file, loaded, total, status) {
  state.uploadProgress = {
    name: file.name || "Upload",
    loaded: loaded || 0,
    total: total || file.size || 0,
    status: status || "Uploading",
  };
  renderTransferPanel(state.uploadProgress);
}

function renderTransferPanel(progress = state.uploadProgress) {
  const panel = $("transferPanel");
  if (!panel) return;
  if (!progress) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const percent = progress.total ? Math.min(100, Math.round((progress.loaded / progress.total) * 100)) : 0;
  panel.innerHTML = `
    <div class="transfer-panel-title">${escapeHtml(progress.status)}</div>
    <div class="transfer-panel-name" title="${escapeHtml(progress.name)}">${escapeHtml(progress.name)}</div>
    <div class="transfer-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}">
      <div style="width:${percent}%"></div>
    </div>
    <div class="transfer-panel-meta">${percent}% · ${escapeHtml(formatBytes(progress.loaded))}${progress.total ? ` / ${escapeHtml(formatBytes(progress.total))}` : ""}</div>
  `;
  panel.classList.remove("hidden");
}

function scheduleTransferPanelHide() {
  window.clearTimeout(state.uploadProgressTimer);
  state.uploadProgressTimer = window.setTimeout(() => {
    state.uploadProgress = null;
    renderTransferPanel(null);
  }, 6500);
}

function downloadToMac(target) {
  if (!target || !target.path) return;
  const link = document.createElement("a");
  link.href = `/api/download?path=${encodeURIComponent(target.path)}`;
  link.download = target.kind === "folder" || target.kind === "drive" ? `${target.name || "download"}.zip` : target.name || "download";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  toast(`Download started: ${target.name || "item"}`);
}

function setFileClipboard(target, mode) {
  if (!target || !target.path || target.kind === "drive") return;
  state.fileClipboard = {
    path: target.path,
    name: target.name || fileNameFromPath(target.path),
    kind: target.kind,
    mode,
  };
  toast(`${mode === "cut" ? "Cut" : "Copied"}: ${state.fileClipboard.name}`);
}

async function pasteClipboardInto(destinationPath) {
  if (!state.fileClipboard || !destinationPath) return;
  const clipboard = state.fileClipboard;
  try {
    const result = await api("/api/paste", {
      method: "POST",
      body: JSON.stringify({
        source_path: clipboard.path,
        destination_path: destinationPath,
        operation: clipboard.mode,
      }),
    });
    if (clipboard.mode === "cut") state.fileClipboard = null;
    await loadPath(destinationPath);
    selectRowByPath(result.path);
    toast(`${clipboard.mode === "cut" ? "Moved" : "Copied"}: ${result.name}`);
  } catch (error) {
    toast(error.message);
  }
}

async function deleteRemoteItem(target) {
  if (!target || !target.path || target.kind === "drive") return;
  const name = target.name || fileNameFromPath(target.path);
  if (!window.confirm(`Delete ${name} from the PC? This cannot be undone from the dashboard.`)) return;
  try {
    await api("/api/delete", {
      method: "POST",
      body: JSON.stringify({ path: target.path }),
    });
    if (state.fileClipboard?.path === target.path) state.fileClipboard = null;
    if (state.currentPreviewPath === target.path) closePreview();
    if (state.currentPath) await loadPath(state.currentPath);
    toast(`Deleted: ${name}`);
  } catch (error) {
    toast(error.message);
  }
}

function uploadFileToPath(path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-CSRF-Token", csrfToken());
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText || "{}"));
        return;
      }
      let message = `${xhr.status} ${xhr.statusText}`;
      try {
        const body = JSON.parse(xhr.responseText || "{}");
        message = body.detail || message;
      } catch (_) {
        // Keep the HTTP status text.
      }
      reject(new Error(message));
    });
    xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
    xhr.addEventListener("abort", () => reject(new Error("Upload aborted")));

    const form = new FormData();
    form.append("path", path);
    form.append("file", file, file.name);
    xhr.send(form);
  });
}

async function previewDashboardItem(item) {
  if (item.kind === "folder" || item.kind === "drive") {
    await loadPath(item.path);
    return;
  }
  selectRowByPath(item.path);
  previewFile(item.path, item.name || fileNameFromPath(item.path));
}

function isBrowsableFolder(item) {
  return !!item && (item.kind === "folder" || item.kind === "drive");
}

async function openActiveFolder() {
  const item = activeItem();
  if (!isBrowsableFolder(item)) return;
  await loadPath(item.path);
}

function previewFile(path, name = fileNameFromPath(path)) {
  const kind = previewKind(path);
  state.currentPreviewPath = path;
  $("previewTitle").textContent = name;
  $("previewPath").textContent = path;
  const body = $("previewBody");
  body.innerHTML = "";

  const url = `/api/file?path=${encodeURIComponent(path)}`;
  let element = null;
  if (kind === "image") {
    element = document.createElement("img");
    element.alt = name;
  } else if (kind === "video") {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.playsInline = true;
    video.src = url;
    video.className = `preview-media ${kind}`;
    body.appendChild(createVideoPlayer(video));
  } else if (kind === "audio") {
    element = document.createElement("audio");
    element.controls = true;
  } else if (kind === "pdf" || kind === "text") {
    element = document.createElement("iframe");
    element.title = name;
  }

  if (element) {
    element.className = `preview-media ${kind}`;
    element.src = url;
    body.appendChild(element);
  } else {
    const message = document.createElement("div");
    message.className = "preview-message";
    message.innerHTML = `
      <strong>Preview unavailable</strong>
      <p>This file type cannot be rendered safely in the dashboard.</p>
    `;
    body.appendChild(message);
  }

  $("previewOverlay").classList.remove("hidden");
  updatePreviewNavButtons();
}

function createVideoPlayer(video) {
  const player = document.createElement("div");
  player.className = "preview-video-player";

  const controls = document.createElement("div");
  controls.className = "preview-video-controls";

  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "video-control-button";
  playButton.textContent = "Play";
  playButton.setAttribute("aria-label", "Play video");

  const seek = document.createElement("input");
  seek.type = "range";
  seek.className = "video-seek";
  seek.min = "0";
  seek.max = "0";
  seek.step = "0.1";
  seek.value = "0";
  seek.setAttribute("aria-label", "Video position");

  const time = document.createElement("span");
  time.className = "video-time";
  time.textContent = "0:00 / 0:00";

  const muteButton = document.createElement("button");
  muteButton.type = "button";
  muteButton.className = "video-control-button";
  muteButton.textContent = "Mute";
  muteButton.setAttribute("aria-label", "Mute video");

  const volume = document.createElement("input");
  volume.type = "range";
  volume.className = "video-volume";
  volume.min = "0";
  volume.max = "1";
  volume.step = "0.01";
  volume.value = String(video.volume || 1);
  volume.setAttribute("aria-label", "Volume");

  const duration = () => (Number.isFinite(video.duration) ? video.duration : 0);
  const syncTime = () => {
    const total = duration();
    seek.max = String(total);
    seek.value = String(Math.min(video.currentTime || 0, total || 0));
    time.textContent = `${formatMediaTime(video.currentTime)} / ${formatMediaTime(total)}`;
  };
  const syncPlayState = () => {
    playButton.textContent = video.paused ? "Play" : "Pause";
    playButton.setAttribute("aria-label", video.paused ? "Play video" : "Pause video");
  };
  const syncVolumeState = () => {
    volume.value = String(video.muted ? 0 : video.volume);
    muteButton.textContent = video.muted || video.volume === 0 ? "Unmute" : "Mute";
    muteButton.setAttribute("aria-label", video.muted || video.volume === 0 ? "Unmute video" : "Mute video");
  };

  playButton.addEventListener("click", () => togglePreviewVideo(video));
  video.addEventListener("click", () => togglePreviewVideo(video));
  seek.addEventListener("input", () => {
    if (!duration()) return;
    video.currentTime = Number(seek.value);
  });
  muteButton.addEventListener("click", () => {
    if (video.muted || video.volume === 0) {
      video.muted = false;
      if (video.volume === 0) video.volume = 0.7;
    } else {
      video.muted = true;
    }
    syncVolumeState();
  });
  volume.addEventListener("input", () => {
    video.volume = Number(volume.value);
    video.muted = video.volume === 0;
    syncVolumeState();
  });

  video.addEventListener("loadedmetadata", syncTime);
  video.addEventListener("durationchange", syncTime);
  video.addEventListener("timeupdate", syncTime);
  video.addEventListener("play", syncPlayState);
  video.addEventListener("pause", syncPlayState);
  video.addEventListener("volumechange", syncVolumeState);

  controls.append(playButton, seek, time, muteButton, volume);
  player.append(video, controls);
  syncPlayState();
  syncVolumeState();
  return player;
}

function handlePreviewSpacebar() {
  if (previewKind(state.currentPreviewPath) === "video") {
    const video = $("previewBody").querySelector("video");
    if (video) togglePreviewVideo(video);
    return;
  }
  if (previewKind(state.currentPreviewPath) === "image") {
    previewAdjacent(1);
  }
}

function togglePreviewVideo(video) {
  if (!video) return;
  if (video.paused) {
    video.play().catch((error) => toast(error.message || "Video playback failed"));
  } else {
    video.pause();
  }
}

function formatMediaTime(seconds) {
  const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainingSeconds = String(value % 60).padStart(2, "0");
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${remainingSeconds}`;
  return `${minutes}:${remainingSeconds}`;
}

function closePreview() {
  const overlay = $("previewOverlay");
  if (!overlay || overlay.classList.contains("hidden")) return;
  hideContextMenu();
  $("previewBody").innerHTML = "";
  state.currentPreviewPath = null;
  updatePreviewNavButtons();
  overlay.classList.add("hidden");
}

function previewKind(path) {
  const extension = fileExtension(path);
  if ([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico", ".avif", ".heic", ".heif", ".tif", ".tiff"].includes(extension)) return "image";
  if ([".mp4", ".m4v", ".mov", ".webm", ".mkv", ".wmv", ".avi"].includes(extension)) return "video";
  if ([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"].includes(extension)) return "audio";
  if (extension === ".pdf") return "pdf";
  if (
    [
      ".bat",
      ".c",
      ".cfg",
      ".cmd",
      ".cpp",
      ".cs",
      ".css",
      ".csv",
      ".env",
      ".go",
      ".h",
      ".hpp",
      ".htm",
      ".html",
      ".ini",
      ".java",
      ".js",
      ".json",
      ".jsx",
      ".log",
      ".md",
      ".ps1",
      ".py",
      ".rb",
      ".rs",
      ".sh",
      ".sql",
      ".swift",
      ".toml",
      ".ts",
      ".tsx",
      ".txt",
      ".xml",
      ".yaml",
      ".yml",
    ].includes(extension) ||
    [".gitignore", "makefile", "readme"].includes(fileNameFromPath(path).toLowerCase())
  ) {
    return "text";
  }
  return "unsupported";
}

function fileExtension(path) {
  const name = fileNameFromPath(path);
  const dotIndex = name.lastIndexOf(".");
  return dotIndex >= 0 ? name.slice(dotIndex).toLowerCase() : "";
}

function fileNameFromPath(path) {
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || path;
}

async function openPath(path) {
  try {
    await api("/api/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    toast("Open request sent to PC");
  } catch (error) {
    toast(error.message);
  }
}

async function loadLogs() {
  const data = await api("/api/jobs?limit=100");
  $("logList").innerHTML = data.events.length
    ? data.events
        .reverse()
        .map(
          (event) => `
          <article class="log-entry">
            <strong>${escapeHtml(event.event)} - ${escapeHtml(event.result)}</strong>
            <code>${escapeHtml(JSON.stringify(event))}</code>
          </article>
        `
        )
        .join("")
    : `<article class="log-entry">No log events yet.</article>`;
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } finally {
    state.authenticated = false;
    state.contextTarget = null;
    hideContextMenu();
    updateAuthView();
  }
}

async function switchView(view) {
  if (!["explorer", "logs"].includes(view)) return;
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  ["explorer", "logs"].forEach((name) => {
    $(`${name}View`).classList.toggle("hidden", name !== view || !state.authenticated);
  });
  if (view === "logs") await loadLogs();
}

function formatBytes(value) {
  if (value === null || value === undefined) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

let toastTimer = null;
function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.classList.remove("hidden");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => element.classList.add("hidden"), 3200);
}

boot().catch((error) => {
  $("authError").textContent = error.message;
  updateAuthView();
});
