// StreamDesk Studio Pro — UI/UX Overhaul & 1-Click App Linking
let config = null;

// Size of the deck, from the profile (older profiles have no layout: 2 rows of 6).
// Each page has its own size (older profiles: the profile's). These read the page being edited.
function pageLayout(index = activePageIndex) { return config?.pages?.[index]?.layout || config?.layout; }
function gridCols() { return pageLayout()?.columns || 6; }
function gridRows() { return pageLayout()?.rows || 2; }
function gridTotal() { return pageLayout()?.total_slots || gridCols() * gridRows(); }
// A fader starts on the first row of its column and is `row_span` rows tall (2 unless set). True when this cell is part of one.
function faderSpan(slot) {
  const span = Number(slot?.row_span);
  return Math.max(1, Math.min(Number.isInteger(span) ? span : 2, gridRows()));
}
function inFaderColumn(slots, index) {
  const col = index % gridCols();
  const row = Math.floor(index / gridCols());
  return (slots[col]?.type === "slider" && row < faderSpan(slots[col])) || slots[index]?.type === "occupied_by_slider";
}
// Indices of the cells a fader covers (its own and the ones under it), or none when the column has no fader.
function faderCells(slots, col) {
  if (slots[col]?.type !== "slider") return [];
  return Array.from({ length: faderSpan(slots[col]) }, (_, k) => col + k * gridCols());
}

// What a new control looks like. A new key does nothing until the user chooses; a new fader controls the Windows volume.
const NEW_BUTTON = { label: "Botón", sublabel: "", icon: "", image: "/static/icons/plus.svg", color: "#555555", action_type: "none", target: "", extra: {} };
function newEmptyButton(index) {
  return { index, type: "button", id: `btn_${Date.now()}`, ...JSON.parse(JSON.stringify(NEW_BUTTON)) };
}
function newMasterFader(col, span = 2) {
  return {
    index: col, type: "slider", id: `slider_${Date.now()}`, label: "Master", sublabel: "PC", slider_type: "master", target_app: null,
    row_span: span, color: "#f8c700", icon: "/static/icons/volume_up.svg", image: "/static/icons/volume_up.svg",
  };
}
let activePageIndex = 0;
let selectedSlotIndex = null;
let audioSessions = [];
let detectedSystemApps = [];
let dragSourceType = null; // 'palette_btn' | 'palette_slider' | 'slot'
let draggedSlotIndex = null;
let activeInspectorTab = "action"; // what to open when a button is selected: action | apps | integrations | design

const phoneScreen = document.getElementById("phone-screen");
const inspectorTitle = document.getElementById("inspector-title");
const inspectorContent = document.getElementById("inspector-content");
const toast = document.getElementById("toast");
const updateCylinder = document.getElementById("update-cylinder");
const updateStatusText = document.getElementById("update-status-text");
const btnApplyUpdate = document.getElementById("btn-apply-update");
const pageTabs = document.getElementById("page-tabs");
const btnAddPage = document.getElementById("btn-add-page");
const phonePreviewPageName = document.getElementById("phone-preview-page-name");
const btnDeletePage = document.getElementById("btn-delete-page");
let copiedSlotConfig = null;
// What the PC is doing right now. Studio listens to the same live feed as the phone, so the
// faders in the preview and the audio list follow the real volumes instead of showing fixed values.
let liveAudio = { master: null };
let liveTelemetry = null;
let studioSocket = null;

// Button colours for instant styling, grouped by hue. All of them read well on the dark keycaps.
const COLOR_GROUPS = [
  ["Corporativos", ["#f8c700", "#ffd633", "#ffffff", "#c4c4c4", "#8c8c8c", "#555555"]],
  ["Rojos y rosas", ["#ef4444", "#dc2626", "#f43f5e", "#fb7185", "#ec4899", "#f472b6"]],
  ["Naranjas y amarillos", ["#f97316", "#fb923c", "#f59e0b", "#fbbf24", "#eab308", "#facc15"]],
  ["Verdes", ["#10b981", "#22c55e", "#4ade80", "#84cc16", "#14b8a6", "#1db954"]],
  ["Azules", ["#0ea5e9", "#38bdf8", "#06b6d4", "#3b82f6", "#6366f1", "#5865f2"]],
  ["Violetas", ["#a855f7", "#8b5cf6", "#a78bfa", "#d946ef", "#c084fc", "#7c3aed"]],
  ["Neutros fríos", ["#64748b", "#94a3b8", "#78716c", "#a8a29e", "#302e31", "#171a21"]],
];
const COLOR_SWATCHES = COLOR_GROUPS.flatMap(([, colours]) => colours);

// Clean Vector SVG Library (30 Available Icons)
const SVG_ICONS = [
  "power", "play_pause", "play", "pause", "next", "prev", "mute", "volume_up",
  "spotify", "discord", "obs", "steam", "chrome", "gamepad", "video", "broadcast",
  "cpu", "ram", "disk", "sliders", "notes", "calc", "gear", "folder",
  "link", "macro", "plus", "trash", "youtube", "fader", "soundboard"
];

// Multimedia Preset Actions
const MEDIA_PRESETS = [
  { id: "play_pause", name: "Play / Pausa", icon: "/static/icons/play_pause.svg", color: "#22c55e", sub: "Reproducir / Pausar", target: "play_pause" },
  { id: "next", name: "Siguiente Pista", icon: "/static/icons/next.svg", color: "#38bdf8", sub: "Canción siguiente", target: "next" },
  { id: "prev", name: "Anterior Pista", icon: "/static/icons/prev.svg", color: "#38bdf8", sub: "Canción anterior", target: "prev" },
  { id: "mute", name: "Mute Master", icon: "/static/icons/mute.svg", color: "#ef4444", sub: "Silenciar ordenador", target: "mute" },
  { id: "volume_up", name: "Subir volumen", icon: "/static/icons/volume_up.svg", color: "#0ea5e9", sub: "Volumen de Windows", target: "volume_up" },
  { id: "volume_down", name: "Bajar volumen", icon: "/static/icons/mute.svg", color: "#0ea5e9", sub: "Volumen de Windows", target: "volume_down" },
];

// System gauges offered in the action library. How each one reads is in monitors.js.
const TELEMETRY_PRESETS = [
  { id: "mon_cpu", name: "Monitor CPU", icon: "/static/icons/cpu.svg", color: "#f8c700", sub: "Uso del procesador", target: "cpu" },
  { id: "mon_ram", name: "Monitor RAM", icon: "/static/icons/ram.svg", color: "#f8c700", sub: "Memoria RAM", target: "ram" },
  { id: "mon_gpu", name: "Monitor GPU", icon: "/static/icons/gpu.svg", color: "#f8c700", sub: "Uso de la tarjeta gráfica", target: "gpu" },
  { id: "mon_vram", name: "Monitor VRAM", icon: "/static/icons/ram.svg", color: "#f8c700", sub: "Memoria de vídeo", target: "vram" },
  { id: "mon_net", name: "Monitor Red", icon: "/static/icons/network.svg", color: "#f8c700", sub: "Descarga y subida", target: "net" },
  { id: "mon_disk", name: "Monitor Disco", icon: "/static/icons/disk.svg", color: "#f8c700", sub: "Velocidad de lectura y escritura", target: "disk_speed" },
  { id: "taskmgr", name: "Adm. Tareas", icon: "/static/icons/sliders.svg", color: "#f8c700", sub: "Abrir TaskMgr", target: "taskmgr" }
];

// Load Pairing Info & QR
let pinExpiresAt = 0;

function showPairingInfo(data) {
  const pinEl = document.getElementById("pin-code");
  const qrEl = document.getElementById("qr-image");
  if (pinEl.textContent !== data.pin) pinEl.textContent = data.pin;
  // Re-assigning the same image makes the QR flicker, so only touch it when the PIN changed.
  if (qrEl.dataset.pin !== data.pin) {
    qrEl.src = data.qr_code;
    qrEl.dataset.pin = data.pin;
  }
  const proto = data.protocol || (location.protocol === "https:" ? "https" : "http");
  document.getElementById("server-url").textContent = `${proto}://${data.ip}:${data.port}`;
  pinExpiresAt = Date.now() + (data.expires_in || 0) * 1000;
  renderPinCountdown();
}

function renderPinCountdown() {
  const el = document.getElementById("pin-expiry");
  if (!el || !pinExpiresAt) return;
  const left = Math.max(0, Math.round((pinExpiresAt - Date.now()) / 1000));
  el.textContent = `Se renueva en ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
}

// The server rotates the PIN every few minutes and after each pairing: keep the screen in step with it.
async function loadAuthInfo() {
  try {
    const res = await fetch("/api/auth/pin");
    showPairingInfo(await res.json());
  } catch (e) {
    console.error("Error loading PIN", e);
  }
}
setInterval(loadAuthInfo, 10000);
setInterval(renderPinCountdown, 1000);

async function regenerateAuthPin() {
  try {
    const res = await fetch("/api/auth/regenerate-pin", { method: "POST" });
    showPairingInfo(await res.json());
    showToast("PIN y código QR nuevos");
  } catch (e) {
    console.error("Error regenerating PIN", e);
  }
}

document.getElementById("btn-refresh-pin")?.addEventListener("click", () => {
  regenerateAuthPin();
});

// Check GitHub Updates. The installed app looks at the project's releases ("release" mode); a source checkout
// looks at the latest commit. Both end in the same button.
let updateMode = "";
async function checkGitHubUpdates() {
  try {
    const res = await fetch("/api/system/check-update");
    const data = await res.json();
    updateMode = data.mode || "";
    if (data.update_available) {
      updateCylinder.className = "update-cylinder update-ready";
      const label = data.mode === "release" ? `v${data.latest_version}` : (data.commit_message || "nueva");
      updateStatusText.textContent = `Versión ${label} disponible`;
      updateStatusText.title = data.notes || "";
      updateCylinder.title = `Tienes la v${data.current_version}. Pulsa «Actualizar» para instalar la ${label}`;
      btnApplyUpdate.textContent = data.mode === "release" ? `Actualizar a v${data.latest_version}` : "Actualizar";
      btnApplyUpdate.style.display = "inline-block";
      announceUpdateOnce(label);
    } else {
      updateCylinder.className = "update-cylinder";
      const suffix = data.status === "offline" ? "sin conexión" : (data.can_update === false ? "" : "al día");
      updateStatusText.textContent = `v${data.current_version || ""}${suffix ? ` · ${suffix}` : ""}`;
      updateStatusText.title = "";
      updateCylinder.title = "Versión de StreamDesk. Pulsa para buscar actualizaciones";
      btnApplyUpdate.style.display = "none";
    }
  } catch (e) {
    console.log("Update check offline", e);
  }
}

// One notice per session: an update that shows up while Studio is open (or at startup) is announced once.
function announceUpdateOnce(label) {
  try {
    if (sessionStorage.getItem("streamdesk_update_announced") === label) return;
    sessionStorage.setItem("streamdesk_update_announced", label);
  } catch (e) { /* storage blocked: announce every time */ }
  showToast(`Hay una versión nueva (${label}). Pulsa «Actualizar» arriba a la derecha.`);
}

// The chip is also a button: a click looks for updates now.
updateCylinder?.addEventListener("click", async (event) => {
  if (event.target.closest("#btn-apply-update") || updateCylinder.classList.contains("update-busy")) return;
  updateStatusText.textContent = "Buscando...";
  await checkGitHubUpdates();
  if (!updateCylinder.classList.contains("update-ready")) showToast(`${updateStatusText.textContent}`);
});
updateCylinder?.addEventListener("keydown", (event) => {
  if ((event.key === "Enter" || event.key === " ") && event.target === updateCylinder) { event.preventDefault(); updateCylinder.click(); }
});

// Follows the download and the installation of a new version until the app closes itself or it fails.
async function followReleaseUpdate() {
  updateCylinder.classList.add("update-busy");
  btnApplyUpdate.style.display = "none";
  try {
    await followReleaseUpdateSteps();
  } finally {
    updateCylinder.classList.remove("update-busy");
  }
}

async function followReleaseUpdateSteps() {
  for (;;) {
    await new Promise(resolve => setTimeout(resolve, 700));
    let status;
    try {
      status = await (await fetch("/api/system/update-status")).json();
    } catch (err) {
      updateStatusText.textContent = "Instalando: StreamDesk se está reiniciando...";
      return; // the server went away because the installer closed the app
    }
    if (status.state === "downloading") {
      updateStatusText.textContent = `Descargando la nueva versión ${Math.round((status.progress || 0) * 100)} %`;
    } else if (status.state === "verifying" || status.state === "installing") {
      updateStatusText.textContent = status.message;
    } else if (status.state === "error") {
      updateStatusText.textContent = "No se pudo actualizar";
      btnApplyUpdate.disabled = false;
      btnApplyUpdate.style.display = "inline-block";
      showToast(status.message || "No se pudo actualizar");
      return;
    } else {
      return;
    }
  }
}

btnApplyUpdate?.addEventListener("click", async () => {
  btnApplyUpdate.disabled = true;
  updateStatusText.textContent = updateMode === "release" ? "Preparando la actualización..." : "Actualizando desde GitHub...";
  try {
    const res = await fetch("/api/system/apply-update", { method: "POST" });
    const data = await res.json();
    if (data.mode === "release") {
      if (data.started === false) showToast("Ya se está actualizando");
      await followReleaseUpdate();
      return;
    }
    btnApplyUpdate.disabled = false;
    if (data.success) {
      showToast("¡Actualizado con éxito desde GitHub! Reiniciando...");
      setTimeout(() => window.location.reload(), 1500);
    } else {
      showToast("Aviso: " + (data.output || "Error al actualizar"));
    }
  } catch (err) {
    btnApplyUpdate.disabled = false;
    showToast("Error de conexión al actualizar");
  }
});

// Look again every few hours while Studio stays open, so a release published later still shows up.
setInterval(checkGitHubUpdates, 6 * 60 * 60 * 1000);

// Load System Apps
async function loadSystemApps() {
  try {
    const res = await fetch("/api/system/apps");
    const data = await res.json();
    detectedSystemApps = data.apps || [];
  } catch (e) {
    console.error("Error loading system apps", e);
  }
}

// Load Audio Sessions
async function loadAudioSessions() {
  try {
    const res = await fetch("/api/audio/sessions");
    const data = await res.json();
    audioSessions = data.sessions || [];
    liveAudio.master = data.master || liveAudio.master;
    renderAudioSessionsSidebar();
    paintStudioFaders();
  } catch (e) {
    console.error("Error loading audio sessions", e);
  }
}

function renderAudioSessionsSidebar() {
  const container = document.getElementById("audio-sessions-list");
  if (!container) return;
  container.innerHTML = "";

  if (audioSessions.length === 0) {
    container.innerHTML = `<div class="audio-sessions-empty">Ninguna app está sonando</div>`;
    return;
  }

  audioSessions.forEach(s => {
    const item = document.createElement("div");
    item.className = "audio-session-item";
    item.innerHTML = `
      <div class="audio-session-info">
        <span class="badge-live-dot"></span>
        <span class="audio-session-name" title="${escapeHtml(s.display_name)}">${escapeHtml(s.display_name)}</span>
      </div>
      <span class="audio-session-vol">${s.volume}%</span>
    `;
    container.appendChild(item);
  });
}

// Load Deck Configuration
async function loadConfig() {
  try {
    const res = await fetch("/api/deck/config");
    config = await res.json();
    activePageIndex = config.current_page || 0;
    renderPageTabs();
    renderPhoneScreen();
    if (selectedSlotIndex !== null) {
      selectSlot(selectedSlotIndex);
    }
  } catch (e) {
    console.error("Error loading config", e);
  }
}

// Render Page Tabs
function renderPageTabs() {
  if (!config) return;
  if (typeof updateGridChip === "function") updateGridChip();
  pageTabs.innerHTML = "";

  const pages = config.pages || [];
  pages.forEach((p, idx) => {
    const btn = document.createElement("button");
    btn.className = `page-tab-btn ${idx === activePageIndex ? 'active' : ''}`;
    btn.textContent = p.name || `Pág ${idx + 1}`;
    btn.addEventListener("click", () => switchPage(idx));
    pageTabs.appendChild(btn);
  });

  // With many pages the strip scrolls: bring the active tab into view.
  pageTabs.querySelector(".page-tab-btn.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });

  if (phonePreviewPageName && pages[activePageIndex]) {
    phonePreviewPageName.textContent = pages[activePageIndex].name || `Página ${activePageIndex + 1}`;
  }

  if (btnDeletePage) {
    btnDeletePage.style.display = pages.length > 1 ? "inline-flex" : "none";
  }
}

async function switchPage(pageIndex) {
  activePageIndex = pageIndex;
  selectedSlotIndex = null;
  renderPageTabs();
  renderPhoneScreen();
  resetInspectorDrawer();

  try {
    await fetch("/api/deck/page/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_index: pageIndex })
    });
  } catch (e) {}
}

btnAddPage?.addEventListener("click", async () => {
  openNewPageDialog();
});

btnDeletePage?.addEventListener("click", async () => {
  const pages = config.pages || [];
  if (pages.length <= 1) {
    showToast("No se puede eliminar la única página");
    return;
  }
  const curName = pages[activePageIndex]?.name || `Página ${activePageIndex + 1}`;
  const confirmed = await askConfirm({
    title: "Eliminar página",
    message: `Se borrará la página "${curName}" con todos sus botones. No se puede deshacer.`,
    confirmLabel: "Eliminar",
    danger: true,
  });
  if (!confirmed) return;
  try {
    const deletedIndex = activePageIndex;
    const res = await fetch("/api/deck/page/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_index: deletedIndex })
    });
    const data = await res.json();
    if (data.success) {
      await loadConfig(); // this may already have moved activePageIndex, so use the index we deleted
      switchPage(Math.max(0, deletedIndex - 1));
      showToast(`Página "${curName}" eliminada`);
    } else {
      showToast(data.error || "Error al eliminar página");
    }
  } catch (e) {
    showToast("Error de conexión al eliminar página");
  }
});

function resetInspectorDrawer() {
  inspectorTitle.textContent = "Configura una casilla";
  inspectorContent.innerHTML = `
    <div class="empty-inspector-tip">
      <img src="/static/icons/sliders.svg" alt="">
      <ol class="empty-steps">
        <li><strong>Elige una casilla</strong> de la pantalla del centro.</li>
        <li><strong>Pulsa «Elegir acción»</strong> para decidir qué hace. Un botón nuevo nace vacío.</li>
        <li><strong>Ajusta el aspecto</strong>: título, color e icono.</li>
      </ol>
      <p class="empty-arrow">← Arrastra un botón o un fader desde «Añadir»</p>
    </div>
  `;
}

// Render the phone screen simulator (the deck, in the size the profile has)
function renderPhoneScreen() {
  if (!config) return;
  phoneScreen.innerHTML = "";

  const pages = config.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config.slots) || [];

  phoneScreen.style.setProperty("--cols", gridCols());
  phoneScreen.style.setProperty("--rows", gridRows());
  // Many columns or rows: smaller cells, and a wider preview so the buttons stay readable.
  phoneScreen.classList.toggle("is-dense", gridCols() > 6 || gridRows() > 3);
  phoneScreen.closest(".phone-mockup")?.classList.toggle("is-wide", gridCols() > 6);
  for (let i = 0; i < gridTotal(); i++) {
    const slot = currentSlots[i] || { index: i, type: "empty" };
    const col = (i % gridCols()) + 1;
    const row = Math.floor(i / gridCols()) + 1;

    // If occupied by a 2-height vertical slider, it is merged with the slot above
    if (slot.type === "occupied_by_slider") {
      continue;
    }

    const cell = document.createElement("div");
    cell.className = `slot-cell ${selectedSlotIndex === i ? 'selected' : ''}`;
    cell.id = `cell_slot_${i}`;
    cell.dataset.index = i;
    cell.style.gridColumn = `${col}`;

    if (slot.type === "slider") {
      cell.style.gridRow = `1 / span ${faderSpan(slot)}`;
      cell.classList.add("cell-slider-spanning");
    } else {
      cell.style.gridRow = `${row}`;
    }

    // Attach Drop Target Events
    cell.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (isDraggingFader()) {
        highlightCoordinatedFaderColumn(col - 1);
      } else {
        cell.classList.add("drag-over");
      }
    });

    cell.addEventListener("dragleave", (e) => {
      if (isDraggingFader()) {
        // clear highlights only if left the phone screen or target
        const related = e.relatedTarget;
        if (!related || !phoneScreen.contains(related)) {
          clearAllDragHighlights();
        }
      } else {
        cell.classList.remove("drag-over");
      }
    });

    cell.addEventListener("drop", (e) => {
      e.preventDefault(); // also for a file or text from elsewhere, so the browser does not open it
      clearAllDragHighlights();
      if (!dragSourceType) return; // not one of our own drags
      handleDropOnSlot(i);
    });

    // Direct Click to Select
    cell.addEventListener("click", () => {
      selectSlot(i);
    });

    if (slot.type === "button") {
      cell.appendChild(createStudioButtonKeycap(slot, i));
    } else if (slot.type === "slider") {
      cell.appendChild(createStudioFaderCard(slot, i));
    } else {
      // Empty slot placeholder
      cell.classList.add("slot-empty-add");
      cell.innerHTML = `<span>+</span>`;
    }

    phoneScreen.appendChild(cell);
  }
  paintStudioFaders();
  paintStudioMonitors();
}

// Fader previews show the real volume of what they control (or "no sound" when the app is silent).
function paintStudioFaders() {
  document.querySelectorAll("#phone-screen .slot-fader").forEach((card) => {
    let volume = null;
    let muted = false;
    if (card.dataset.sliderType === "master") {
      if (liveAudio.master) ({ volume, muted } = liveAudio.master);
    } else {
      const wanted = (card.dataset.targetApp || "").toLowerCase();
      const session = audioSessions.find(s => (s.process_name || "").toLowerCase() === wanted);
      if (session) ({ volume, muted } = session);
    }
    card.classList.toggle("is-idle", volume === null);
    card.classList.toggle("is-muted", Boolean(muted));
    const val = card.querySelector(".slot-fader-val");
    if (volume === null) {
      val.textContent = "—";
      return;
    }
    card.querySelector(".slot-fader-fill").style.height = `${volume}%`;
    val.textContent = muted ? "Mute" : `${volume}%`;
  });
}

function paintStudioMonitors() {
  if (!liveTelemetry) return;
  document.querySelectorAll("#phone-screen .slot-monitor").forEach((el) => {
    paintMonitor(el, "slot-monitor", el.dataset.monitor, liveTelemetry);
  });
}

function handleStudioMessage(message) {
  switch (message.type) {
    case "init_state":
    case "audio_state":
      audioSessions = message.sessions || [];
      liveAudio.master = message.master || liveAudio.master;
      break;
    case "master_volume_updated":
      liveAudio.master = { volume: message.volume, muted: message.muted };
      break;
    case "master_mute_updated":
      if (liveAudio.master) liveAudio.master.muted = message.muted;
      break;
    case "app_volume_updated":
      audioSessions.forEach(s => { if (s.process_name?.toLowerCase() === message.process?.toLowerCase()) s.volume = message.volume; });
      break;
    case "app_mute_updated":
      audioSessions.forEach(s => { if (s.process_name?.toLowerCase() === message.process?.toLowerCase()) s.muted = message.muted; });
      break;
    case "telemetry_update":
      liveTelemetry = message;
      paintStudioMonitors();
      return;
    default:
      return;
  }
  renderAudioSessionsSidebar();
  paintStudioFaders();
}

function connectStudioSocket() {
  // Studio runs on this PC, so the server accepts it without a pairing token.
  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${wsProto}//${location.host}/ws`);
  studioSocket = socket;
  socket.onmessage = (event) => {
    try { handleStudioMessage(JSON.parse(event.data)); } catch (e) { console.error("Studio feed", e); }
  };
  socket.onclose = () => {
    if (socket === studioSocket) setTimeout(connectStudioSocket, 2000);
  };
}

function isDraggingFader() {
  if (dragSourceType === "palette_slider") return true;
  if (dragSourceType === "slot" && draggedSlotIndex !== null) {
    const pages = config?.pages || [];
    const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
    return currentSlots[draggedSlotIndex]?.type === "slider";
  }
  return false;
}

// ---- Dragging: what the drag looks like, and dropping a slot outside the grid to delete it ----

let slotDragHandled = false;   // a drop on a cell or the trash already dealt with this drag
let slotDragCancelled = false; // Escape was pressed during the drag
window.addEventListener("keydown", (e) => { if (e.key === "Escape" && dragSourceType) slotDragCancelled = true; }, true);

// The same markup the deck uses for a key and for a fader: the drag image and the tiles of the sidebar are built from it,
// so what you pick up looks like what you will get.
function keycapHtml(data) {
  const colour = escapeHtml(data.color || "#f8c700");
  const icon = escapeHtml(data.image || data.icon || "/static/icons/power.svg");
  return `<div class="slot-keycap">
      <div class="slot-keycap-inner">
        <div class="slot-accent" style="background: ${colour};"></div>
        <img src="${icon}" class="slot-keycap-img" alt="">
        <div class="slot-keycap-title">${escapeHtml(data.label || "Botón")}</div>
        <div class="slot-keycap-sub">${escapeHtml(data.sublabel || data.sub || "")}</div>
      </div>
    </div>`;
}

function faderHtml(data, percent = 60) {
  const colour = escapeHtml(data.color || "#f8c700");
  const icon = escapeHtml(data.image || data.icon || "/static/icons/volume_up.svg");
  return `<div class="slot-fader">
      <div class="slot-fader-head"><img src="${icon}" alt=""><span>${escapeHtml(data.label || "Volumen")}</span></div>
      <div class="slot-fader-track"><div class="slot-fader-fill" style="height: ${percent}%; background: ${colour};"></div></div>
      <div class="slot-fader-val">${percent}%</div>
    </div>`;
}

// Size of a cell of the deck as it is on screen now, so the drag image is as big as the real thing.
function deckCellSize(kind, span = 2) {
  const cell = phoneScreen?.querySelector(".slot-cell:not(.cell-slider-spanning)");
  if (!cell) return null;
  const box = cell.getBoundingClientRect();
  if (!box.width || !box.height) return null;
  const gap = parseFloat(getComputedStyle(phoneScreen).rowGap) || 0;
  return kind === "fader" ? { width: box.width, height: box.height * span + gap * (span - 1) } : { width: box.width, height: box.height };
}

// The drag image is a copy of the real control: a keycap or a tall fader, with its icon, name and colour.
function setDragGhost(event, kind, data, size) {
  if (!event.dataTransfer?.setDragImage) return;
  const measured = size || deckCellSize(kind, faderSpan(data));
  const width = measured?.width || (kind === "fader" ? 92 : 116);
  const height = measured?.height || (kind === "fader" ? 232 : 116);
  const ghost = document.createElement("div");
  ghost.className = "drag-ghost";
  ghost.style.width = `${width}px`;
  ghost.style.height = `${height}px`;
  ghost.innerHTML = kind === "fader" ? faderHtml(data) : keycapHtml(data);
  document.body.appendChild(ghost);
  event.dataTransfer.setDragImage(ghost, width / 2, height / 2);
  setTimeout(() => ghost.remove(), 0); // the browser has taken its snapshot by then
}

// The tiles of "Añadir" show a key and a fader exactly as they will look once dropped.
function renderPalettePreviews() {
  // Each control inside the same stage, at its own proportions: both tiles end up the same size.
  const key = document.querySelector(".palette-preview-key");
  if (key) key.innerHTML = `<span class="palette-box palette-box-key">${keycapHtml(NEW_BUTTON)}</span>`;
  const fader = document.querySelector(".palette-preview-fader");
  if (fader) fader.innerHTML = `<span class="palette-box palette-box-fader">${faderHtml(newMasterFader(0), 60)}</span>`;
}
renderPalettePreviews();

function startSlotDrag(event, index, wrap, kind, data) {
  dragSourceType = "slot";
  draggedSlotIndex = index;
  slotDragHandled = false;
  slotDragCancelled = false;
  event.dataTransfer.effectAllowed = "move";
  const box = wrap.getBoundingClientRect();
  setDragGhost(event, kind, data, { width: box.width, height: box.height });
  wrap.classList.add("dragging");
  document.getElementById(`cell_slot_${index}`)?.classList.add("is-source-dragging");
  document.body.classList.add("is-dragging-slot"); // shows the "drop outside to delete" hint
}

function finishSlotDrag(event, index, wrap) {
  wrap.classList.remove("dragging");
  document.getElementById(`cell_slot_${index}`)?.classList.remove("is-source-dragging");
  document.body.classList.remove("is-dragging-slot");
  const handled = slotDragHandled, cancelled = slotDragCancelled;
  slotDragHandled = false;
  slotDragCancelled = false;
  // Nothing of this drag may outlive it: a later drop of text or a file must not find a stale slot to move.
  dragSourceType = null;
  draggedSlotIndex = null;
  clearAllDragHighlights();
  // A drop on a cell or on the trash already ran. Anywhere else the browser reports dropEffect "none":
  // that deletes the slot, unless Escape cancelled the drag or it was released outside the window.
  if (handled || cancelled || event.dataTransfer?.dropEffect !== "none") return;
  const { clientX: x, clientY: y } = event;
  if ((x === 0 && y === 0) || x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) return;
  // The gaps between cells and the frame's padding are not "outside": there it is just a drop that missed.
  const frame = document.querySelector(".phone-screen-wrapper")?.getBoundingClientRect();
  const margin = 16;
  if (frame && x >= frame.left - margin && x <= frame.right + margin && y >= frame.top - margin && y <= frame.bottom + margin) return;
  deleteSlotByDrag(index);
}

// What was removed last (a button, or a fader with the cell under it), so Ctrl+Z can bring it back.
let lastDeleted = null;

function rememberDeleted(pageIndex, slots, indices) {
  lastDeleted = { page: pageIndex, cells: indices.map(index => ({ index, slot: JSON.parse(JSON.stringify(slots[index])) })) };
}

function undoLastDelete() {
  if (!lastDeleted || !config?.pages?.[lastDeleted.page]) return false;
  const { page, cells } = lastDeleted;
  const slots = config.pages[page].slots;
  // Only into cells that are still empty: undoing must never overwrite what was put there since.
  if (cells.some(({ index }) => slots[index] && slots[index].type !== "empty")) {
    showToast("No se puede deshacer: esa casilla ya tiene otra cosa");
    lastDeleted = null;
    return true;
  }
  if (page !== activePageIndex) switchPage(page);
  cells.forEach(({ index, slot }) => { slots[index] = slot; });
  lastDeleted = null;
  renderPhoneScreen();
  selectSlot(cells[0].index);
  saveConfigToServer();
  showToast("Deshecho: casilla recuperada");
  return true;
}

// Ctrl+Z brings back the last deleted button or fader, except while typing in a field.
window.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.key.toLowerCase() !== "z") return;
  const el = document.activeElement;
  if (el && (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable)) return;
  if (lastDeleted) {
    e.preventDefault();
    undoLastDelete();
  }
});

function deleteSlotByDrag(index) {
  const slots = config?.pages?.[activePageIndex]?.slots;
  const slot = slots?.[index];
  if (!slot || slot.type === "empty" || slot.type === "occupied_by_slider") return;
  const name = slot.label || (slot.type === "slider" ? "Fader" : "Botón");
  if (slot.type === "slider") {
    removeFader(slots, index % gridCols());
  } else {
    rememberDeleted(activePageIndex, slots, [index]);
    slots[index] = { index, type: "empty" };
  }
  selectedSlotIndex = null;
  renderPhoneScreen();
  resetInspectorDrawer();
  saveConfigToServer();
  showUndoToast(`Eliminado: ${name}`);
}

function clearAllDragHighlights() {
  document.querySelectorAll(".slot-cell").forEach(cell => {
    cell.classList.remove("drag-over", "drag-over-fader-top", "drag-over-fader-bottom");
  });
  document.getElementById("trash-dropzone")?.classList.remove("trash-drag-over");
}

function highlightCoordinatedFaderColumn(col) {
  clearAllDragHighlights();
  const topCell = document.getElementById(`cell_slot_${col}`);
  const bottomCell = document.getElementById(`cell_slot_${col + gridCols()}`);
  if (topCell) {
    if (topCell.classList.contains("cell-slider-spanning")) {
      topCell.classList.add("drag-over-fader-top", "drag-over-fader-bottom");
    } else {
      topCell.classList.add("drag-over-fader-top");
      if (bottomCell) bottomCell.classList.add("drag-over-fader-bottom");
    }
  }
}

function triggerDropBounce(index) {
  setTimeout(() => {
    const cell = document.getElementById(`cell_slot_${index}`);
    if (cell) {
      cell.classList.remove("slot-drop-bounce");
      void cell.offsetWidth;
      cell.classList.add("slot-drop-bounce");
      setTimeout(() => cell.classList.remove("slot-drop-bounce"), 350);
    }
  }, 30);
}

function clearColumn(slots, col) {
  const cells = faderCells(slots, col);
  (cells.length ? cells : [col, col + gridCols()]).forEach(i => { slots[i] = { index: i, type: "empty" }; });
}

// Takes a fader out (all the cells it covers), keeping it for Ctrl+Z.
function removeFader(slots, col) {
  const cells = faderCells(slots, col);
  const targets = cells.length ? cells : [col, col + gridCols()];
  rememberDeleted(activePageIndex, slots, targets);
  clearColumn(slots, col);
}

// Puts a fader of `span` rows in a column. What was in those cells goes to Ctrl+Z, never silently lost.
function placeFader(slots, col, fader, span = 2) {
  span = Math.max(1, Math.min(span, gridRows()));
  const cols = gridCols();
  const affected = new Set([...faderCells(slots, col), ...Array.from({ length: span }, (_, k) => col + k * cols)]);
  if ([...affected].some(i => slots[i] && slots[i].type !== "empty")) rememberDeleted(activePageIndex, slots, [...affected].sort((a, b) => a - b));
  affected.forEach(i => { slots[i] = { index: i, type: "empty" }; });
  slots[col] = { ...fader, index: col, row_span: span };
  for (let k = 1; k < span; k++) {
    const index = col + k * cols;
    slots[index] = { index, type: "occupied_by_slider", id: `occ_${col}_${k}_${Date.now()}`, parent_slot: col };
  }
}

// Changes how many rows a fader covers. Growing needs the cells under it to be free: nothing is deleted to make room.
function resizeFader(col, wanted) {
  const slots = config.pages[activePageIndex].slots;
  const top = slots[col];
  if (top?.type !== "slider") return false;
  const cols = gridCols();
  const span = Math.max(1, Math.min(wanted, gridRows()));
  const old = faderSpan(top);
  if (span === old) return false;
  for (let k = old; k < span; k++) {
    const cell = slots[col + k * cols];
    if (cell && cell.type !== "empty") {
      showToast(`Para hacer el fader más alto, libera antes la casilla ${col + k * cols + 1}`);
      return false;
    }
  }
  for (let k = Math.min(old, span); k < Math.max(old, span); k++) {
    const index = col + k * cols;
    slots[index] = span > old
      ? { index, type: "occupied_by_slider", id: `occ_${col}_${k}_${Date.now()}`, parent_slot: col }
      : { index, type: "empty" };
  }
  top.row_span = span;
  renderPhoneScreen();
  saveConfigToServer();
  return true;
}

function emptySlotByIndex(idx) {
  const pages = config?.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
  const col = idx % gridCols();
  const slot = currentSlots[idx];
  if (!slot || slot.type === "empty") return;

  if (slot.type === "slider" || slot.type === "occupied_by_slider" || inFaderColumn(currentSlots, idx)) {
    removeFader(currentSlots, col);
    showUndoToast(`Columna ${col + 1} vaciada`);
  } else {
    rememberDeleted(activePageIndex, currentSlots, [idx]);
    currentSlots[idx] = { index: idx, type: "empty" };
    showUndoToast(`Casilla ${idx + 1} vaciada`);
  }
  renderPhoneScreen();
  selectSlot(idx);
  saveConfigToServer();
}

function pasteCopiedSlot(targetIdx) {
  if (!copiedSlotConfig) return;
  const pages = config?.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
  const tCol = targetIdx % gridCols();

  if (copiedSlotConfig.type === "slider") {
    const pastedSlider = JSON.parse(JSON.stringify(copiedSlotConfig));
    pastedSlider.id = `slider_${Date.now()}`;
    placeFader(currentSlots, tCol, pastedSlider, faderSpan(pastedSlider));
    renderPhoneScreen();
    selectSlot(tCol);
    triggerDropBounce(tCol);
    saveConfigToServer();
    showToast(`Fader pegado en Columna #${tCol + 1} (Ctrl+V)`);
  } else {
    if (inFaderColumn(currentSlots, targetIdx)) {
      removeFader(currentSlots, tCol);
    }
    const pastedBtn = JSON.parse(JSON.stringify(copiedSlotConfig));
    pastedBtn.index = targetIdx;
    pastedBtn.id = `btn_${Date.now()}`;
    currentSlots[targetIdx] = pastedBtn;
    renderPhoneScreen();
    selectSlot(targetIdx);
    triggerDropBounce(targetIdx);
    saveConfigToServer();
    showToast(`Botón pegado en Casilla #${targetIdx + 1} (Ctrl+V)`);
  }
}

function createStudioButtonKeycap(btn, index) {
  const wrap = document.createElement("div");
  wrap.className = "slot-keycap";
  wrap.draggable = true;

  wrap.addEventListener("dragstart", (e) => startSlotDrag(e, index, wrap, "button", btn));
  wrap.addEventListener("dragend", (e) => finishSlotDrag(e, index, wrap));

  if (btn.action_type === "hardware_monitor") {
    wrap.innerHTML = `
      <div class="slot-keycap-inner slot-monitor kind-${MONITORS[btn.target]?.kind || "percent"}" data-monitor="${escapeHtml(btn.target)}">
        <div class="slot-accent" style="background: ${escapeHtml(btn.color || 'var(--accent)')};"></div>
        ${monitorInnerHtml("slot-monitor", btn.target)}
      </div>`;
    wrap.querySelector(".slot-monitor-name").textContent = btn.label || MONITORS[btn.target]?.name || btn.target;
    if (liveTelemetry) paintMonitor(wrap.querySelector(".slot-monitor"), "slot-monitor", btn.target, liveTelemetry);
    return wrap;
  }

  let iconSrc = btn.image || btn.icon || "/static/icons/power.svg";

  wrap.classList.toggle("is-disabled", Boolean(btn.disabled));
  wrap.classList.toggle("is-unset", btn.action_type === "none");
  const badges = [btn.long_press ? "⏱" : "", btn.double_tap ? "×2" : "", btn.toggle ? "⇄" : "", btn.confirm ? "?" : ""].filter(Boolean).join(" ");
  wrap.title = btn.action_type === "none" ? "Sin acción todavía" : describeAction(btn);
  wrap.innerHTML = `
    ${badges ? `<span class="slot-badges" aria-hidden="true">${badges}</span>` : ""}
    <div class="slot-keycap-inner">
      <div class="slot-accent" style="background: ${btn.color || 'var(--accent)'};"></div>
      <img src="${escapeHtml(iconSrc)}" class="slot-keycap-img" alt="">
      <div class="slot-keycap-title">${escapeHtml(btn.label || 'Botón')}</div>
      <div class="slot-keycap-sub">${escapeHtml(btn.sublabel || '')}</div>
    </div>
  `;

  return wrap;
}

function createStudioFaderCard(slider, index) {
  const isMaster = slider.slider_type === "master" || slider.type === "master";
  const wrap = document.createElement("div");
  wrap.className = "slot-fader";
  wrap.draggable = true;

  wrap.addEventListener("dragstart", (e) => startSlotDrag(e, index, wrap, "fader", slider));
  wrap.addEventListener("dragend", (e) => finishSlotDrag(e, index, wrap));

  wrap.dataset.sliderType = isMaster ? "master" : "app";
  wrap.dataset.targetApp = slider.target_app || "";
  const headerIcon = slider.image || (isMaster ? '/static/icons/volume_up.svg' : '/static/icons/spotify.svg');
  const accentColor = slider.color || 'var(--accent)';

  wrap.innerHTML = `
    <div class="slot-fader-head">
      <img src="${escapeHtml(headerIcon)}" alt="">
      <span>${escapeHtml(slider.label || (isMaster ? 'Master' : 'App'))}</span>
    </div>
    <div class="slot-fader-track">
      <div class="slot-fader-fill" style="height: 60%; background: ${accentColor};"></div>
    </div>
    <div class="slot-fader-val">60%</div>
    <div class="fader-resize-handle" role="slider" tabindex="0" title="Arrastra para cambiar el alto del fader"
         aria-label="Alto del fader en filas" aria-valuemin="1" aria-valuemax="${gridRows()}" aria-valuenow="${faderSpan(slider)}"></div>
  `;
  wireFaderResize(wrap, slider, index);

  return wrap;
}

// Dragging the bottom edge of a fader changes its height row by row; the arrow keys do the same.
function wireFaderResize(wrap, slider, index) {
  const handle = wrap.querySelector(".fader-resize-handle");
  if (!handle) return;
  const col = index % gridCols();
  handle.addEventListener("keydown", (event) => {
    if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    if (resizeFader(col, faderSpan(slider) + (event.key === "ArrowDown" ? 1 : -1))) {
      selectSlot(col);
      document.querySelector(`#cell_slot_${col} .fader-resize-handle`)?.focus();
    }
  });
  handle.addEventListener("click", (event) => event.stopPropagation());
  handle.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const cell = wrap.closest(".slot-cell");
    const start = faderSpan(slider);
    const gap = parseFloat(getComputedStyle(phoneScreen).rowGap) || 0;
    const pitch = (cell.getBoundingClientRect().height + gap) / start; // one row, with its gap
    let target = start;
    wrap.draggable = false; // the fader itself must not start a drag of its own
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("is-active");
    const move = (e) => {
      target = Math.max(1, Math.min(gridRows(), start + Math.round((e.clientY - event.clientY) / pitch)));
      cell.style.gridRow = `1 / span ${target}`;
    };
    const finish = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", finish);
      handle.removeEventListener("pointercancel", finish);
      wrap.draggable = true;
      if (target === start || !resizeFader(col, target)) renderPhoneScreen(); // cancelled or blocked: back to how it was
      else selectSlot(col);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  });
}

// Drag & Drop Handling on Slots
function handleDropOnSlot(targetIndex) {
  slotDragHandled = true; // a drop on a cell is a move, never a delete
  clearAllDragHighlights();
  const col = targetIndex % gridCols();
  const topSlot = col;
  const bottomSlot = col + gridCols();
  const currentSlots = config.pages[activePageIndex].slots;

  if (dragSourceType === "palette_slider") {
    placeFader(currentSlots, col, newMasterFader(col), 2);
    renderPhoneScreen();
    selectSlot(topSlot);
    triggerDropBounce(topSlot);
    saveConfigToServer();
    showToast(`Fader del volumen de Windows colocado en la columna ${col + 1}`);

  } else if (dragSourceType === "palette_btn") {
    // A key dropped on a fader replaces it (Ctrl+Z brings it back).
    if (inFaderColumn(currentSlots, targetIndex)) removeFader(currentSlots, col);
    else if (currentSlots[targetIndex] && currentSlots[targetIndex].type !== "empty") rememberDeleted(activePageIndex, currentSlots, [targetIndex]);
    currentSlots[targetIndex] = newEmptyButton(targetIndex);

    renderPhoneScreen();
    selectSlot(targetIndex);
    triggerDropBounce(targetIndex);
    saveConfigToServer();
    showToast("Botón vacío colocado: elige a la derecha qué hace");

  } else if (dragSourceType === "slot" && draggedSlotIndex !== null) {
    if (draggedSlotIndex !== targetIndex) {
      const isSourceSlider = currentSlots[draggedSlotIndex]?.type === "slider";

      if (isSourceSlider) {
        const sCol = draggedSlotIndex % gridCols();
        const tCol = targetIndex % gridCols();
        if (sCol !== tCol) {
          const sourceSlider = JSON.parse(JSON.stringify(currentSlots[sCol]));
          clearColumn(currentSlots, sCol);
          placeFader(currentSlots, tCol, sourceSlider, faderSpan(sourceSlider));

          renderPhoneScreen();
          selectSlot(tCol);
          triggerDropBounce(tCol);
          saveConfigToServer();
          showToast(`Fader reubicado a Columna #${tCol + 1}`);
        }
      } else {
        const sIdx = draggedSlotIndex;
        const tIdx = targetIndex;
        const tCol = tIdx % gridCols();
        const sourceBtn = JSON.parse(JSON.stringify(currentSlots[sIdx]));

        // Check if target is part of a fader (the rows it covers in its column)
        if (inFaderColumn(currentSlots, tIdx)) {
          removeFader(currentSlots, tCol);
          currentSlots[sIdx] = { index: sIdx, type: "empty" };
          sourceBtn.index = tIdx;
          currentSlots[tIdx] = sourceBtn;
        } else {
          // Normal swap with target slot
          const targetItem = (currentSlots[tIdx] && currentSlots[tIdx].type !== "empty")
            ? JSON.parse(JSON.stringify(currentSlots[tIdx]))
            : { index: sIdx, type: "empty" };

          sourceBtn.index = tIdx;
          currentSlots[tIdx] = sourceBtn;
          targetItem.index = sIdx;
          currentSlots[sIdx] = targetItem;
        }

        renderPhoneScreen();
        selectSlot(tIdx);
        triggerDropBounce(tIdx);
        saveConfigToServer();
        showToast("Posición actualizada");
      }
    }
  }

  dragSourceType = null;
  draggedSlotIndex = null;
  clearAllDragHighlights();
}

// Setup Trash Dropzone
function setupTrashDropZone() {
  const trashZone = document.getElementById("trash-dropzone");
  if (!trashZone) return;

  trashZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    trashZone.classList.add("trash-drag-over");
  });

  trashZone.addEventListener("dragleave", () => {
    trashZone.classList.remove("trash-drag-over");
  });

  trashZone.addEventListener("drop", (e) => {
    e.preventDefault();
    trashZone.classList.remove("trash-drag-over");
    slotDragHandled = true;
    if (dragSourceType === "slot" && draggedSlotIndex !== null) {
      emptySlotByIndex(draggedSlotIndex);
      dragSourceType = null;
      draggedSlotIndex = null;
    }
  });

  trashZone.addEventListener("click", () => {
    if (selectedSlotIndex !== null) {
      emptySlotByIndex(selectedSlotIndex);
    } else {
      showToast("Selecciona una casilla para vaciarla");
    }
  });
}

// Palette Drag Events
const paletteNewBtn = document.getElementById("palette-new-btn");
if (paletteNewBtn) {
  paletteNewBtn.addEventListener("dragstart", (e) => {
    dragSourceType = "palette_btn";
    e.dataTransfer.effectAllowed = "copy";
    setDragGhost(e, "button", NEW_BUTTON);
    paletteNewBtn.classList.add("is-dragging");
  });
  paletteNewBtn.addEventListener("dragend", () => {
    paletteNewBtn.classList.remove("is-dragging");
    dragSourceType = null;
    clearAllDragHighlights();
  });
}

const paletteNewSlider = document.getElementById("palette-new-slider");
if (paletteNewSlider) {
  paletteNewSlider.addEventListener("dragstart", (e) => {
    dragSourceType = "palette_slider";
    e.dataTransfer.effectAllowed = "copy";
    setDragGhost(e, "fader", newMasterFader(0));
    paletteNewSlider.classList.add("is-dragging");
  });
  paletteNewSlider.addEventListener("dragend", () => {
    paletteNewSlider.classList.remove("is-dragging");
    dragSourceType = null;
    clearAllDragHighlights();
  });
}

// The next cell for an arrow key, wrapping around the grid and skipping the cell under a fader (it has no
// button of its own: selecting it would leave nothing highlighted and the editor showing the previous one).
function nextSelectableSlot(step) {
  const total = gridTotal();
  const slots = config?.pages?.[activePageIndex]?.slots || config?.slots || [];
  if (selectedSlotIndex === null) return 0;
  let index = selectedSlotIndex;
  for (let tries = 0; tries < total; tries++) {
    index = (index + step + total) % total;
    if (slots[index]?.type !== "occupied_by_slider") return index;
  }
  return selectedSlotIndex;
}

// Keyboard Shortcuts Controller
window.addEventListener("keydown", (e) => {
  const activeEl = document.activeElement;
  if (activeEl && (["INPUT", "TEXTAREA", "SELECT"].includes(activeEl.tagName) || activeEl.isContentEditable)) {
    return;
  }
  // A dialog is on top: the keys belong to it (Delete would empty the cell behind it, the arrows move a hidden selection).
  if (document.querySelector(".modal-overlay")) return;

  if (e.key === "Delete") {
    if (selectedSlotIndex !== null) {
      e.preventDefault();
      emptySlotByIndex(selectedSlotIndex);
    }
  } else if (e.key === "Escape") {
    if (selectedSlotIndex !== null) {
      e.preventDefault();
      selectedSlotIndex = null;
      renderPhoneScreen();
      resetInspectorDrawer();
    }
  } else if (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: gridCols(), ArrowUp: -gridCols() }[e.key];
    selectSlot(nextSelectableSlot(step));
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
    if (selectedSlotIndex !== null) {
      const pages = config?.pages || [];
      const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
      const slot = currentSlots[selectedSlotIndex];
      if (slot && slot.type !== "empty" && slot.type !== "occupied_by_slider") {
        copiedSlotConfig = JSON.parse(JSON.stringify(slot));
        showToast(`Casilla copiada (${slot.label || slot.type}) [Ctrl+C]`);
      }
    }
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "v") {
    if (copiedSlotConfig && selectedSlotIndex !== null) {
      pasteCopiedSlot(selectedSlotIndex);
    }
  }
});

// Select Slot and Open Inspector Drawer
function selectSlot(index) {
  selectedSlotIndex = index;
  renderPhoneScreen();

  const currentSlots = config.pages[activePageIndex].slots;
  const slot = currentSlots[index];

  if (!slot || slot.type === "empty") {
    inspectorTitle.textContent = `Casilla #${index + 1} (Vacía)`;
    renderEmptySlotInspector(index);
  } else if (slot.type === "button") {
    inspectorTitle.textContent = `Configurar Botón #${index + 1}`;
    renderButtonInspector(slot, index);
  } else if (slot.type === "slider") {
    inspectorTitle.textContent = `Configurar Fader (Col #${(index % gridCols()) + 1})`;
    renderSliderInspector(slot, index);
  }
}

// Empty Slot Inspector
function renderEmptySlotInspector(index) {
  const col = index % gridCols();
  const currentSlots = config.pages[activePageIndex].slots;

  inspectorContent.innerHTML = `
    <p class="integration-hint" style="margin-bottom: 14px;">Esta casilla está vacía. ¿Qué quieres poner aquí?</p>
    <div class="inspector-actions">
      <button class="btn-primary" id="btn-create-button-here">
        <img src="/static/icons/plus.svg" alt=""> Añadir un botón vacío
      </button>
      <button class="btn-secondary" id="btn-create-slider-here">
        <img src="/static/icons/fader.svg" alt=""> Añadir un fader del volumen de Windows (columna ${col + 1})
      </button>
    </div>
  `;

  document.getElementById("btn-create-button-here")?.addEventListener("click", () => {
    currentSlots[index] = newEmptyButton(index);
    activeInspectorTab = "action";
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
  });

  document.getElementById("btn-create-slider-here")?.addEventListener("click", () => {
    placeFader(currentSlots, col, newMasterFader(col), 2);
    renderPhoneScreen();
    selectSlot(col);
    saveConfigToServer();
    showToast("Fader del volumen de Windows colocado");
  });
}

// Button inspector: a summary of what the button does, then three folding sections:
// what it does, how it looks, and the extras (long press, double tap, confirmation, off).
// The actions are chosen in one dialog (see openActionPicker).
const INSPECTOR_TABS = [
  ["apps", "Apps"],
  ["integrations", "Conectores"],
  ["action", "Acción"],
  ["design", "Aspecto"],
];
let openSections = { what: true, look: false, more: false, states: false };

function renderButtonInspector(btn, index) {
  const currentSlots = config.pages[activePageIndex].slots;
  // A placer (new button, Spotify/Discord pickers) may ask for the action dialog on a given tab.
  const wantedPicker = activeInspectorTab === "apps" ? "apps" : (activeInspectorTab === "integrations" ? "programs" : "");
  if (activeInspectorTab === "design") openSections.look = true;
  if (activeInspectorTab !== "action") activeInspectorTab = "action";

  inspectorContent.innerHTML = `
    <div class="inspector-summary">
      <div class="inspector-preview-card">
        <div class="preview-btn-mock">
          <div class="slot-keycap-inner">
            <div class="slot-accent" style="background: ${escapeHtml(btn.color || '#f8c700')};"></div>
            <img src="${escapeHtml(btn.image || btn.icon || '/static/icons/power.svg')}" class="slot-keycap-img" id="inspector-preview-img" alt="">
            <div class="slot-keycap-title" id="inspector-preview-title">${escapeHtml(btn.label || 'Botón')}</div>
            <div class="slot-keycap-sub" id="inspector-preview-sub">${escapeHtml(btn.sublabel || '')}</div>
          </div>
        </div>
      </div>
      <div class="inspector-summary-text">
        <span class="inspector-summary-label">Este botón hace</span>
        <strong id="inspector-summary-action">${escapeHtml(describeAction(btn) || "Nada todavía")}</strong>
        <button class="btn-primary btn-choose-action" id="btn-choose-action" type="button">Elegir acción</button>
      </div>
    </div>

    <details class="inspector-section" id="section-what" ${openSections.what ? "open" : ""}>
      <summary>1. Qué hace</summary>
      <div class="inspector-section-body" id="inspector-tab-content"></div>
    </details>
    <details class="inspector-section" id="section-look" ${openSections.look ? "open" : ""}>
      <summary>2. Apariencia <small>título, color e icono</small></summary>
      <div class="inspector-section-body" id="inspector-look-content"></div>
    </details>
    <details class="inspector-section" id="section-more" ${openSections.more ? "open" : ""}>
      <summary>3. Más opciones <small>pulsación larga, doble toque, confirmar, desactivar</small></summary>
      <div class="inspector-section-body" id="inspector-more-content"></div>
    </details>
    ${btn.action_type === "hardware_monitor" || btn.action_type === "none" ? "" : `<details class="inspector-section" id="section-states" ${openSections.states || btn.toggle ? "open" : ""}>
      <summary>4. Dos estados <small>${btn.toggle ? "activado" : "encendido y apagado"}</small></summary>
      <div class="inspector-section-body" id="inspector-states-content"></div>
    </details>`}

    <button class="btn-danger" id="btn-delete-slot">
      <img src="/static/icons/trash.svg" alt=""> Vaciar esta casilla
    </button>
  `;

  [["what", "section-what"], ["look", "section-look"], ["more", "section-more"], ["states", "section-states"]].forEach(([key, id]) => {
    document.getElementById(id)?.addEventListener("toggle", (event) => { openSections[key] = event.target.open; });
  });

  const whatBox = document.getElementById("inspector-tab-content");
  renderTabAction(whatBox, btn, index);
  // The extras (gestures, confirm, disabled) get their own section: move them out of the action editor.
  const extras = whatBox.querySelector("#gesture-section");
  const moreBox = document.getElementById("inspector-more-content");
  if (extras) moreBox.appendChild(extras);
  else moreBox.innerHTML = `<p class="integration-hint">${btn.action_type === "none"
    ? "Elige primero qué hace el botón: después podrás darle pulsación larga, doble toque o dos estados."
    : "Los monitores del PC solo muestran datos: no tienen más opciones."}</p>`;
  renderTabDesign(document.getElementById("inspector-look-content"), btn, index);
  const statesBox = document.getElementById("inspector-states-content");
  if (statesBox) renderToggleSection(statesBox, btn, index);

  document.getElementById("btn-choose-action")?.addEventListener("click", () => openActionPicker(btn, index));
  if (wantedPicker) openActionPicker(btn, index, wantedPicker);

  document.getElementById("btn-delete-slot")?.addEventListener("click", () => emptySlotByIndex(index));
}

// One dialog to choose what a button does: an app to open, the actions inside a program (connectors),
// keyboard shortcuts, or system actions. Replaces the separate Apps and Connectors tabs.
let actionPicker = null;
// When the dialog is opened to choose the action of a long press, a second state... (not the key's own), the choice
// goes to `onPick` instead of replacing the key: {onPick(action), onCancel()}.
let pickerSession = null;
function closeActionPicker() {
  if (actionPicker) { const picker = actionPicker; actionPicker = null; picker.close(); }
}

function openActionPicker(btn, index, startTab = "apps", session = null) {
  closeActionPicker();
  pickerSession = session;
  // Choosing for a gesture must not be narrowed to the app this key opens, nor place sounds on the key itself.
  const scopeBtn = session ? { action_type: "none" } : btn;
  const tabs = [["apps", "Abrir una app"], ["programs", "Programas"], ["shortcuts", "Atajos y texto"], ["system", "Sistema"]];
  let current = startTab;
  const modal = openModal({
    title: session?.title || "Elegir qué hace este botón",
    description: session ? "El botón no cambia: solo se añade esta acción." : "",
    body: `
      <div class="picker-tabs" role="tablist">
        ${tabs.map(([id, name]) => `<button class="picker-tab ${id === current ? "active" : ""}" role="tab" data-picker-tab="${id}">${name}</button>`).join("")}
      </div>
      <p class="tab-hint" id="picker-hint"></p>
      <div class="picker-body" id="picker-body"></div>`,
    actions: [{ label: "Cerrar", kind: "secondary" }],
    onMount: () => {},
  });
  modal.el.querySelector(".modal-card").classList.add("picker-card");
  actionPicker = modal;
  const previousClose = modal.close;
  modal.onClose = () => {
    if (actionPicker === modal) actionPicker = null;
    if (session && pickerSession === session) { pickerSession = null; session.onCancel?.(); }
  };

  const hints = {
    apps: "Solo abre el programa que elijas.",
    programs: "Acciones dentro de un programa: OBS, Discord, Spotify y Windows (conectados), y los atajos de más de 30 programas (VLC, DaVinci, Excel, Chrome...). Los atajos van a la ventana que esté a la vista: el programa tiene que estar delante.",
    shortcuts: "Pulsa teclas, escribe un texto, abre una web o una carpeta, o encadena varias acciones.",
    system: "Volumen, bloqueo del PC, comandos de consola, monitores del PC y navegación entre páginas.",
  };
  const body = modal.el.querySelector("#picker-body");
  const hint = modal.el.querySelector("#picker-hint");

  const libraryGroups = (names, host) => {
    host.innerHTML = `<input type="search" id="picker-search" placeholder="Buscar una acción" aria-label="Buscar una acción">` + `<div id="picker-list"></div>`;
    const list = host.querySelector("#picker-list");
    const draw = (term) => {
      const t = term.trim().toLowerCase();
      list.innerHTML = libraryCategories
        .filter(c => names.some(n => c.category.toLowerCase().startsWith(n.toLowerCase())))
        .map(c => {
          const items = c.items.filter(i => !i.opensTab && (!t || `${i.label} ${i.sub}`.toLowerCase().includes(t)));
          if (!items.length) return "";
          return `<div class="picker-category">${escapeHtml(c.category)}</div><div class="picker-items">${items.map(i => `
            <button class="picker-item" data-pick="${escapeHtml(i.id)}"><img src="${escapeHtml(i.icon)}" alt=""><div><strong>${escapeHtml(i.label)}</strong><span>${escapeHtml(i.sub || "")}</span></div></button>`).join("")}</div>`;
        }).join("") || `<div class="empty-note">Ninguna acción coincide.</div>`;
      list.querySelectorAll("[data-pick]").forEach(el => el.addEventListener("click", () => {
        const item = libraryCategories.flatMap(c => c.items).find(i => i.id === el.dataset.pick);
        assignFromTemplate(btn, index, {
          label: item.label, sublabel: item.sub || "", icon: item.icon, color: item.color,
          action_type: item.action_type, target: item.target, extra: item.extra,
          configure: item.configure, confirm_default: item.confirm_default,
        });
      }));
    };
    host.querySelector("#picker-search").addEventListener("input", (e) => draw(e.target.value));
    draw("");
  };

  const show = (tab) => {
    current = tab;
    modal.el.querySelectorAll(".picker-tab").forEach(b => b.classList.toggle("active", b.dataset.pickerTab === tab));
    hint.textContent = hints[tab];
    // A fresh holder per tab: a slow tab (connectors) that finishes later draws into a detached node and is ignored.
    body.innerHTML = "";
    const host = document.createElement("div");
    body.appendChild(host);
    if (tab === "apps") renderTabApps(host, scopeBtn, index);
    else if (tab === "programs") renderTabPrograms(host, scopeBtn, index, Boolean(session));
    else if (tab === "shortcuts") libraryGroups(["Sistema", "Reuniones", "Vídeo", "Creación", "Navegador", "Atajos de Windows", "Edición", "Música"], host);
    else libraryGroups(["Windows", "Páginas", "Multimedia", "Monitores", "Contadores", "Conexiones web"], host);
  };
  modal.el.querySelectorAll(".picker-tab").forEach(b => b.addEventListener("click", () => show(b.dataset.pickerTab)));
  show(startTab);
  return modal;
}

// The programs tab: the connected programs (OBS, Discord, Spotify, Windows) and the shortcuts of many more,
// by program. A program opens to its actions; "Programas" goes back to the list.
let programCatalog = null;
const CONNECTOR_CARDS = [
  { id: "obs", name: "OBS Studio", sub: "Escenas, grabar, directo, filtros, volumen...", icon: "/static/icons/obs.svg", actionType: "obs_action" },
  { id: "discord", name: "Discord", sub: "Silenciar, ensordecer y soundboard", icon: "/static/icons/discord.svg", actionType: "discord_hotkey" },
  { id: "spotify", name: "Spotify", sub: "Playlists y canciones", icon: "/static/icons/spotify.svg", actionType: "spotify_uri" },
  { id: "windows", name: "Windows", sub: "Micrófono, energía, pantallas, volumen, captura", icon: "/static/icons/volume_up.svg", actionType: "windows" },
];

function renderTabPrograms(host, btn, index, pick) {
  host.innerHTML = `
    <input type="search" id="prog-search" placeholder="Buscar un programa: VLC, Excel, DaVinci, Chrome..." aria-label="Buscar un programa">
    <div id="prog-body"><div class="empty-note">Cargando programas...</div></div>`;
  const body = host.querySelector("#prog-body");
  const search = host.querySelector("#prog-search");
  let packs = [];

  const showConnector = (card) => {
    search.hidden = true;
    body.innerHTML = `<button type="button" class="btn-secondary prog-back" data-back>← Programas</button><div id="prog-connector"></div>`;
    body.querySelector("[data-back]").addEventListener("click", showList);
    // The connectors panel, narrowed to this connector by the type of action it would run.
    openConnectorId = card.id;
    renderTabConnectors(body.querySelector("#prog-connector"), { action_type: card.actionType }, index, pick);
  };

  const showPack = (pack) => {
    search.hidden = false;
    search.value = "";
    const draw = (term) => {
      const t = term.trim().toLowerCase();
      const actions = pack.actions.filter(a => !t || `${a.label} ${a.sub}`.toLowerCase().includes(t));
      body.querySelector("#prog-actions").innerHTML = actions.length ? actions.map(a => `
        <button type="button" class="picker-item" data-action="${escapeHtml(a.id)}">
          <img src="/static/icons/${escapeHtml(a.icon)}.svg" alt=""><div><strong>${escapeHtml(a.label)}</strong><span>${escapeHtml(a.sub)}</span></div>
        </button>`).join("") : `<div class="empty-note">Ninguna acción coincide.</div>`;
    };
    body.innerHTML = `
      <div class="prog-head">
        <button type="button" class="btn-secondary prog-back" data-back>← Programas</button>
        <strong>${escapeHtml(pack.name)}</strong>
      </div>
      <p class="integration-hint">Atajos de teclado de ${escapeHtml(pack.name)}: van a la ventana que esté en primer plano, así que ${escapeHtml(pack.name)} tiene que estar a la vista. Son los atajos que trae por defecto; si los cambiaste en el programa, edítalos en la casilla.</p>
      <div class="picker-items" id="prog-actions"></div>`;
    body.querySelector("[data-back]").addEventListener("click", showList);
    body.querySelector("#prog-actions").addEventListener("click", (event) => {
      const chosen = pack.actions.find(a => a.id === event.target.closest("[data-action]")?.dataset.action);
      if (!chosen) return;
      assignFromTemplate(btn, index, {
        label: chosen.label, sublabel: chosen.sub, icon: `/static/icons/${chosen.icon}.svg`, color: pack.color,
        action_type: "hotkey", target: chosen.keys, extra: {},
      });
    });
    draw("");
    search.oninput = (event) => draw(event.target.value);
  };

  const showList = () => {
    search.hidden = false;
    const draw = (term) => {
      const t = term.trim().toLowerCase();
      const connectors = CONNECTOR_CARDS.filter(c => !t || `${c.name} ${c.sub}`.toLowerCase().includes(t));
      const groups = (programCatalog?.categories || []).map(category => ({
        category, items: packs.filter(p => p.category === category && (!t || `${p.name} ${p.id}`.toLowerCase().includes(t))),
      })).filter(g => g.items.length);
      body.innerHTML = [
        connectors.length ? `<div class="picker-category">Conectados a StreamDesk</div><div class="apps-cards-grid">${connectors.map(c => `
          <div class="app-card-item" role="button" tabindex="0" data-connector="${c.id}">
            <div class="app-card-left"><img src="${c.icon}" class="app-card-icon" alt=""><div><div class="app-card-name">${escapeHtml(c.name)}</div><div class="app-card-cat">${escapeHtml(c.sub)}</div></div></div>
            <span class="app-card-badge">Conectar</span></div>`).join("")}</div>` : "",
        ...groups.map(g => `<div class="picker-category">${escapeHtml(g.category)}</div><div class="apps-cards-grid">${g.items.map(p => `
          <div class="app-card-item" role="button" tabindex="0" data-pack="${escapeHtml(p.id)}">
            <div class="app-card-left"><img src="/static/icons/${escapeHtml(p.icon)}.svg" class="app-card-icon" alt="" style="background: ${escapeHtml(p.color)}33"><div><div class="app-card-name">${escapeHtml(p.name)}</div><div class="app-card-cat">${p.actions.length} atajos</div></div></div>
            <span class="app-card-badge">Ver</span></div>`).join("")}</div>`),
      ].join("") || `<div class="empty-note">Ningún programa coincide.</div>`;
    };
    draw(search.value || "");
    search.oninput = (event) => draw(event.target.value);
  };

  body.addEventListener("click", (event) => {
    const card = event.target.closest("[data-connector], [data-pack]");
    if (!card) return;
    if (card.dataset.connector) showConnector(CONNECTOR_CARDS.find(c => c.id === card.dataset.connector));
    else showPack(packs.find(p => p.id === card.dataset.pack));
  });
  body.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      const card = event.target.closest("[data-connector], [data-pack]");
      if (card) { event.preventDefault(); card.click(); }
    }
  });

  (async () => {
    try {
      programCatalog ??= await apiJson("/api/programs");
    } catch (err) {
      body.innerHTML = `<div class="empty-note">No se pudo cargar la lista de programas (${escapeHtml(err.message)}).</div>`;
      return;
    }
    packs = programCatalog.programs;
    // A key that opens one of these programs goes straight to its actions.
    const own = !pick && ["preset_app", "launch"].includes(btn.action_type) ? packs.find(p => p.id === String(btn.target || "").toLowerCase()) : null;
    const ownConnector = !pick && CONNECTOR_CARDS.find(c => c.id === String(btn.target || "").toLowerCase() && ["preset_app", "launch"].includes(btn.action_type));
    if (own) showPack(own); else if (ownConnector) showConnector(ownConnector); else showList();
  })();
}

// Apps installed on this PC, found by the scanner. One click links the button.
function renderTabApps(container, btn, index) {
  const apps = detectedSystemApps.length > 0 ? detectedSystemApps : [
    { id: "discord", name: "Discord", icon: "/static/icons/discord.svg", color: "#5865f2", category: "Voz y chat" },
    { id: "spotify", name: "Spotify", icon: "/static/icons/spotify.svg", color: "#1db954", category: "Música" },
    { id: "obs", name: "OBS Studio", icon: "/static/icons/obs.svg", color: "#302e31", category: "Directo" },
    { id: "steam", name: "Steam", icon: "/static/icons/steam.svg", color: "#171a21", category: "Juegos" },
    { id: "chrome", name: "Chrome", icon: "/static/icons/chrome.svg", color: "#ea4335", category: "Navegador" }
  ];

  container.innerHTML = `
    <div class="search-input-wrapper">
      <img src="/static/icons/power.svg" class="search-icon-svg" alt="">
      <input type="search" id="app-search-input" class="search-input" placeholder="Busca una app de tu PC">
    </div>
    <div class="apps-cards-grid" id="apps-list-grid"></div>
  `;

  const listGrid = document.getElementById("apps-list-grid");
  const searchInput = document.getElementById("app-search-input");

  function populateApps(filter = "") {
    listGrid.innerHTML = "";
    const term = filter.toLowerCase().trim();
    const filtered = apps.filter(a => a.name.toLowerCase().includes(term) || (a.category && a.category.toLowerCase().includes(term)));

    if (filtered.length === 0) {
      listGrid.innerHTML = `<div class="empty-note">No se encontró ninguna app con ese nombre</div>`;
      return;
    }

    filtered.forEach(app => {
      const card = document.createElement("div");
      card.className = "app-card-item";
      card.innerHTML = `
        <div class="app-card-left">
          <img src="${escapeHtml(app.icon || '/static/icons/power.svg')}" class="app-card-icon" alt="">
          <div>
            <div class="app-card-name">${escapeHtml(app.name)}</div>
            <div class="app-card-cat">${escapeHtml(app.category || 'App')}</div>
          </div>
        </div>
        <span class="app-card-badge">Usar</span>
      `;
      card.addEventListener("click", () => assignFromTemplate(btn, index, {
        label: app.name, sublabel: app.category || "App", icon: app.icon || "/static/icons/power.svg",
        color: app.color || "#f8c700", action_type: "preset_app", target: app.id || app.name,
      }));
      listGrid.appendChild(card);
    });
  }

  searchInput.addEventListener("input", (e) => populateApps(e.target.value));
  populateApps();
}

// 5. Tab Connectors: Windows, OBS, Spotify and Discord, set up and assigned in one place
let connectorCache = null;
let openConnectorId = "windows";
const STATUS_LABELS = { ready: "Listo", needs_setup: "Falta configurar", limited: "Limitado", offline: "No disponible" };
const SPOTIFY_DASHBOARD = "https://developer.spotify.com/dashboard";

// Names of scenes, playlists and devices come from other programs: never put them in innerHTML raw.
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

async function connectorApi(path, body) {
  const options = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(`/api/connectors${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo completar la acción");
  return data;
}

function assignFromTemplate(btn, index, template, overrides = {}) {
  const t = { ...template, ...overrides };
  if (pickerSession?.onPick) {
    // The dialog was opened for a gesture or a second state: hand over just the action.
    const session = pickerSession;
    pickerSession = null;
    closeActionPicker();
    session.onPick({ action_type: t.action_type, target: t.target, extra: JSON.parse(JSON.stringify(t.extra || {})) });
    return;
  }
  btn.label = String(t.label || "Acción").slice(0, 32);
  btn.sublabel = String(t.sublabel || "").slice(0, 36);
  btn.image = t.icon;
  btn.icon = "";
  btn.color = t.color;
  btn.action_type = t.action_type;
  btn.target = t.target;
  btn.extra = JSON.parse(JSON.stringify(t.extra || {}));
  if (t.confirm_default) btn.confirm = true; // e.g. console commands: ask before running
  activeInspectorTab = "action"; // show what the button now does, and its settings
  if (typeof closeActionPicker === "function") closeActionPicker();
  renderPhoneScreen();
  renderButtonInspector(btn, index);
  saveConfigToServer();
  showToast(`"${btn.label}" asignado a la casilla ${index + 1}`);
}

function actionTilesHtml(actions) {
  return `<div class="quick-actions-grid">${actions.map((a, i) => `
    <div class="quick-action-card" data-tile="${i}">
      <img src="${escapeHtml(a.icon)}" alt="">
      <div class="quick-action-name">${escapeHtml(a.label)}</div>
      <div class="quick-action-sub">${escapeHtml(a.sublabel)}</div>
    </div>`).join("")}</div>`;
}

function wireTiles(body, actions, ctx) {
  body.querySelectorAll("[data-tile]").forEach(tile => {
    tile.addEventListener("click", () => assignFromTemplate(ctx.btn, ctx.index, actions[Number(tile.dataset.tile)]));
  });
}

function statusLine(c) {
  return `<p class="integration-hint">${escapeHtml(c.status.detail)}</p>`;
}

// Runs a request from a button, showing the reason when it fails.
async function withToast(work, success) {
  try {
    await work();
    if (success) showToast(success);
  } catch (err) {
    showToast(err.message);
  }
}

function connectorBodyWindows(c, body, ctx) {
  const sessions = [...new Map((audioSessions || []).map(s => [s.process_name, s])).values()]
    .filter(s => s.process_name && s.process_name !== "System Sounds");
  body.innerHTML = `
    ${statusLine(c)}
    ${actionTilesHtml(c.actions)}
    <label>Silenciar una app concreta</label>
    <div class="inline-row">
      <select id="win-app-select" ${sessions.length ? "" : "disabled"}>
        ${sessions.length ? sessions.map(s => `<option value="${escapeHtml(s.process_name)}">${escapeHtml(s.display_name || s.process_name)}</option>`).join("") : "<option>Abre la app y reproduce algo</option>"}
      </select>
      <button class="btn-secondary" id="win-app-assign" ${sessions.length ? "" : "disabled"}>Asignar</button>
    </div>
    <label>Cambiar la salida de audio</label>
    <div class="option-list" id="win-outputs"><span class="integration-hint">Buscando dispositivos...</span></div>`;
  wireTiles(body, c.actions, ctx);

  body.querySelector("#win-app-assign")?.addEventListener("click", () => {
    const select = body.querySelector("#win-app-select");
    const name = select.selectedOptions[0].textContent;
    assignFromTemplate(ctx.btn, ctx.index, {
      label: `Mute ${name}`, sublabel: "Windows", icon: "/static/icons/mute.svg", color: "#ef4444",
      action_type: "windows", target: "app_mute", extra: { process: select.value },
    });
  });

  connectorApi("/windows/options/outputs").then(({ options }) => {
    const list = body.querySelector("#win-outputs");
    if (!list) return;
    list.innerHTML = options.map((d, i) => `
      <div class="option-row">
        <span>${escapeHtml(d.name)}</span>
        ${d.default ? '<span class="status-pill status-ready">En uso</span>' : `<button class="btn-secondary" data-output="${i}">Usar</button>`}
      </div>`).join("");
    list.querySelectorAll("[data-output]").forEach(button => button.addEventListener("click", () => {
      const device = options[Number(button.dataset.output)];
      assignFromTemplate(ctx.btn, ctx.index, {
        label: device.name.replace(/\s*\(.*$/, "") || "Salida", sublabel: "Salida de audio", icon: "/static/icons/volume_up.svg",
        color: "#0ea5e9", action_type: "windows", target: "output_device", extra: { device_id: device.id },
      });
    }));
  }).catch(err => {
    const list = body.querySelector("#win-outputs");
    if (list) list.innerHTML = `<span class="integration-hint">${escapeHtml(err.message)}</span>`;
  });
}

function connectorBodyObs(c, body, ctx) {
  const s = c.settings || {};
  body.innerHTML = `
    ${statusLine(c)}
    <label for="obs-password">Contraseña del servidor WebSocket</label>
    <input id="obs-password" type="password" autocomplete="off" placeholder="${s.password_set ? "Guardada (escribe para cambiarla)" : "Vacío si OBS no pide contraseña"}">
    <label for="obs-port">Puerto</label>
    <input id="obs-port" type="number" min="1024" max="65535" value="${Number(s.port) || 4455}">
    <button class="btn-primary" id="obs-save">Guardar y probar</button>
    ${actionTilesHtml(c.actions)}
    <div id="obs-live"></div>`;
  wireTiles(body, c.actions, ctx);

  body.querySelector("#obs-save").addEventListener("click", () => withToast(async () => {
    const values = { port: Number(body.querySelector("#obs-port").value) };
    const password = body.querySelector("#obs-password").value;
    if (password) values.password = password;
    await connectorApi("/obs/configure", values);
    await ctx.refresh();
  }, "Ajustes de OBS guardados"));

  const live = body.querySelector("#obs-live");
  if (c.status.state !== "ready") {
    live.innerHTML = `<p class="integration-hint">Para ver tus escenas y fuentes, abre OBS y activa Herramientas &gt; Ajustes del servidor WebSocket.</p>
      <button class="btn-secondary" id="obs-retry">Volver a comprobar</button>`;
    live.querySelector("#obs-retry").addEventListener("click", () => ctx.refresh());
    return;
  }
  live.innerHTML = '<label>Cambiar a una escena</label><div class="chip-list" id="obs-scenes"></div><label>Silenciar un micrófono de OBS</label><div class="inline-row" id="obs-inputs"></div>';
  Promise.all([connectorApi("/obs/options/scenes"), connectorApi("/obs/options/inputs")]).then(([scenes, inputs]) => {
    const chips = live.querySelector("#obs-scenes");
    if (!chips) return;
    chips.innerHTML = scenes.options.map((o, i) => `<button class="chip" data-scene="${i}">${escapeHtml(o.name)}</button>`).join("") || '<span class="integration-hint">OBS no tiene escenas</span>';
    chips.querySelectorAll("[data-scene]").forEach(chip => chip.addEventListener("click", () => {
      const name = scenes.options[Number(chip.dataset.scene)].name;
      assignFromTemplate(ctx.btn, ctx.index, {
        label: name, sublabel: "Escena", icon: "/static/icons/gamepad.svg", color: "#10b981",
        action_type: "obs_action", target: `scene_${name}`, extra: { scene_name: name },
      });
    }));
    const row = live.querySelector("#obs-inputs");
    row.innerHTML = `<select id="obs-input-select">${inputs.options.map(i => `<option value="${escapeHtml(i.name)}">${escapeHtml(i.name)}</option>`).join("")}</select>
      <button class="btn-secondary" id="obs-input-assign">Asignar</button>`;
    row.querySelector("#obs-input-assign").addEventListener("click", () => {
      const source = row.querySelector("#obs-input-select").value;
      assignFromTemplate(ctx.btn, ctx.index, {
        label: `Mute ${source}`, sublabel: "OBS", icon: "/static/icons/mute.svg", color: "#ef4444",
        action_type: "obs_action", target: "mute_mic", extra: { source_name: source },
      });
    });
  }).catch(err => { live.innerHTML = `<p class="integration-hint">${escapeHtml(err.message)}</p>`; });
}

function connectorBodySpotify(c, body, ctx) {
  const s = c.settings || {};
  const setup = s.connected ? "" : `
    <ol class="setup-steps">
      <li>Entra en <code class="copyable">${SPOTIFY_DASHBOARD}</code> y crea una app (el nombre da igual).</li>
      <li>En <strong>Redirect URIs</strong> añade exactamente: <code class="copyable">${escapeHtml(s.redirect_uri)}</code></li>
      <li>Pega aquí el <strong>Client ID</strong> de esa app:
        <input id="sp-client-id" type="text" maxlength="32" value="${escapeHtml(s.client_id || "")}" placeholder="32 caracteres">
        <button class="btn-secondary" id="sp-save-id">Guardar</button></li>
      <li>Pulsa conectar y acepta en el navegador. <button class="btn-primary" id="sp-connect" ${s.client_id ? "" : "disabled"}>Conectar cuenta</button>
        <button class="btn-secondary" id="sp-check">Ya acepté</button></li>
    </ol>`;
  body.innerHTML = `
    ${statusLine(c)}
    ${setup}
    ${s.connected ? '<div class="option-list" id="sp-playlists"><span class="integration-hint">Cargando tus playlists...</span></div>' : ""}
    <label for="spotify-uri-input">O pega el enlace de una playlist, álbum, artista o canción</label>
    <div class="inline-row"><input id="spotify-uri-input" type="url" placeholder="https://open.spotify.com/playlist/..."><button class="btn-secondary" id="sp-link-assign">Asignar</button></div>
    <p class="integration-hint">Sin cuenta conectada (o sin Premium) el botón abre la lista en la app de Spotify de tu PC y pulsa Reproducir por ti: la app debe estar abierta y a la vista, no minimizada. Una cuenta gratuita reproduce en modo aleatorio y con anuncios, como la propia app. Con Premium y la cuenta conectada se reproduce sin tocar la app.</p>
    ${s.connected ? '<button class="btn-secondary" id="sp-disconnect">Desconectar cuenta</button>' : ""}`;

  const spotifyTemplate = (name, uri) => ({
    label: name, sublabel: "Spotify", icon: "/static/icons/spotify.svg", color: "#1db954", action_type: "spotify_uri", target: uri,
  });
  body.querySelector("#sp-save-id")?.addEventListener("click", () => withToast(async () => {
    await connectorApi("/spotify/configure", { client_id: body.querySelector("#sp-client-id").value.trim() });
    await ctx.refresh();
  }, "Client ID guardado"));
  body.querySelector("#sp-connect")?.addEventListener("click", () => withToast(
    () => connectorApi("/spotify/connect", {}), "Se abrió Spotify en tu navegador. Acepta y vuelve aquí."));
  body.querySelector("#sp-check")?.addEventListener("click", () => ctx.refresh());
  body.querySelector("#sp-disconnect")?.addEventListener("click", () => withToast(async () => {
    await connectorApi("/spotify/disconnect", {});
    await ctx.refresh();
  }, "Cuenta de Spotify desconectada"));
  body.querySelector("#sp-link-assign").addEventListener("click", () => {
    const raw = body.querySelector("#spotify-uri-input").value.trim();
    const match = raw.match(/^spotify:(playlist|album|artist|track):([A-Za-z0-9]{10,64})$/)
      || raw.match(/^https:\/\/(?:www\.)?open\.spotify\.com\/(playlist|album|artist|track)\/([A-Za-z0-9]{10,64})/);
    if (!match) return showToast("Pega un enlace válido de Spotify");
    const kinds = { playlist: "Playlist", album: "Álbum", artist: "Artista", track: "Canción" };
    assignFromTemplate(ctx.btn, ctx.index, spotifyTemplate(kinds[match[1]], `spotify:${match[1]}:${match[2]}`));
  });

  if (s.connected) {
    connectorApi("/spotify/options/playlists").then(({ options }) => {
      const list = body.querySelector("#sp-playlists");
      if (!list) return;
      list.innerHTML = options.map((p, i) => `
        <div class="option-row playlist-row" data-playlist="${i}">
          ${p.image ? `<img src="${escapeHtml(p.image)}" alt="" referrerpolicy="no-referrer">` : '<img src="/static/icons/spotify.svg" alt="">'}
          <span>${escapeHtml(p.name)}</span>
        </div>`).join("") || '<span class="integration-hint">No hay playlists en tu cuenta</span>';
      list.querySelectorAll("[data-playlist]").forEach(row => row.addEventListener("click", () => {
        const playlist = options[Number(row.dataset.playlist)];
        assignFromTemplate(ctx.btn, ctx.index, spotifyTemplate(playlist.name, playlist.uri));
      }));
    }).catch(err => {
      const list = body.querySelector("#sp-playlists");
      if (list) list.innerHTML = `<span class="integration-hint">${escapeHtml(err.message)}</span>`;
    });
  }
}

// The sounds read from the user's own Discord window. Kept while Studio is open, so the list is there next time.
let discordSounds = null;

function renderDiscordSounds(area, ctx) {
  const sections = [...new Set(discordSounds.map(s => s.section))];
  const currentSection = discordSounds.find(s => s.current)?.section || "";
  const cached = discordSounds.find(s => s.cached);
  const picked = new Map(sections.map(name => [name, new Set()]));
  const actionOf = (sound) => ({ action_type: "discord_sound", target: sound.label, extra: { section: sound.section } });
  const soundsOf = (server) => discordSounds.filter(s => s.section === server);
  const pickedSounds = (server) => soundsOf(server).filter(s => picked.get(server).has(s.label));

  area.innerHTML = `
    ${cached ? `<div class="inspector-note dc-cache-note"><strong>Sonidos guardados${cached.scanned_at ? ` el ${escapeHtml(cached.scanned_at)}` : ""}.</strong>
      ${cached.reason ? escapeHtml(cached.reason) : "Discord no se ha leído ahora."} Puedes elegirlos y asignarlos igualmente; se reproducen cuando estés en un canal de voz. Entra en uno y pulsa «Actualizar mis sonidos» para refrescar la lista.</div>` : ""}
    <input type="search" id="dc-filter" placeholder="Buscar un sonido en todos tus servidores" aria-label="Buscar un sonido">
    <div class="dc-servers" id="dc-servers"></div>
    <p class="integration-hint">Pulsa un sonido para marcarlo (hasta ${gridTotal()} por servidor), o ▶ para oírlo y + para asignarlo a este botón. Con varios marcados puedes crear una página que se abre sola cuando entras a un canal de voz de ese servidor, repartirlos en casillas libres o juntarlos en un solo botón.</p>`;
  const host = area.querySelector("#dc-servers");
  const filter = area.querySelector("#dc-filter");
  const openState = new Map(sections.map(name => [name, name === currentSection || sections.length === 1]));

  const draw = () => {
    const term = filter.value.trim().toLowerCase();
    host.innerHTML = sections.map(server => {
      const all = soundsOf(server);
      const shown = term ? all.filter(s => `${s.name} ${s.label}`.toLowerCase().includes(term)) : all;
      if (!shown.length) return "";
      const count = picked.get(server).size;
      const open = term ? true : openState.get(server);
      return `
        <details class="dc-server" data-server="${escapeHtml(server)}" ${open ? "open" : ""}>
          <summary><span class="dc-server-name">${escapeHtml(server)}</span>
            ${server === currentSection ? `<span class="dc-here">donde estás</span>` : ""}
            <span class="dc-count">${term ? `${shown.length} de ${all.length}` : all.length}${count ? ` · ${count} marcados` : ""}</span></summary>
          <div class="dc-grid">${shown.map(sound => `
            <div class="dc-tile ${picked.get(server).has(sound.label) ? "picked" : ""}" data-label="${escapeHtml(sound.label)}">
              <button type="button" class="dc-tile-main" data-pick aria-pressed="${picked.get(server).has(sound.label)}" title="${escapeHtml(sound.label)}">
                <span class="dc-emoji">${escapeHtml(sound.emoji || "🔊")}</span>
                <span class="dc-name">${escapeHtml(sound.name)}</span>
              </button>
              <span class="dc-tile-tools">
                <button type="button" data-test title="Probar este sonido" aria-label="Probar ${escapeHtml(sound.name)}">▶</button>
                <button type="button" data-assign title="Asignarlo a este botón" aria-label="Asignar ${escapeHtml(sound.name)} a este botón">+</button>
              </span>
            </div>`).join("")}</div>
          ${count ? `<div class="dc-bar">
            <button type="button" class="btn-primary" data-make-page>${count === 1 ? `Crear página de «${escapeHtml(server)}» con 1 sonido` : `Crear página con estos sonidos (${count})`}</button>
            ${count > 1 && !ctx.pick ? `<button type="button" class="btn-secondary" data-fill>Poner en casillas libres desde la elegida</button>
            <button type="button" class="btn-secondary" data-one>Un solo botón con todos en orden</button>` : ""}
          </div>` : ""}
        </details>`;
    }).join("") || `<div class="empty-note">Ningún sonido coincide.</div>`;
    if (ctx.pick) host.querySelectorAll("[data-make-page]").forEach(b => { b.hidden = true; });
  };

  const createPage = async (server, replace) => {
    try {
      await flushSave();
      const result = await postJson("/api/discord/server-page", { server, sounds: [...picked.get(server)], replace });
      await loadConfig();
      await switchPage(result.index);
      showToast(`Página «${server}» ${result.replaced ? "actualizada" : "creada"}. Se abrirá sola cuando entres a un canal de voz de ese servidor.`);
    } catch (err) {
      if (!replace && err.message.startsWith("Ya hay una página")) {
        const ok = await askConfirm({ title: "Reemplazar la página", message: `Ya tienes una página para «${server}». Se cambiarán sus botones por estos sonidos.`, confirmLabel: "Reemplazar" });
        if (ok) await createPage(server, true);
      } else {
        showToast(err.message);
      }
    }
  };

  // Each ticked sound becomes its own button, in order, from the chosen cell on. Filled cells and cells under a fader are skipped.
  const fillCells = (server) => {
    const sounds = pickedSounds(server);
    const slots = config.pages[activePageIndex].slots;
    let placed = 0;
    for (let i = ctx.index; i < gridTotal() && placed < sounds.length; i++) {
      const slot = slots[i];
      const free = i === ctx.index || slot?.type === "empty";
      if (!free || inFaderColumn(slots, i)) continue;
      const sound = sounds[placed];
      slots[i] = {
        index: i, type: "button", id: `btn_${Date.now()}_${placed}`,
        label: sound.name.slice(0, 32), sublabel: sound.section.slice(0, 36), icon: "", image: "/static/icons/soundboard.svg",
        color: "#5865f2", ...actionOf(sound),
      };
      placed++;
    }
    const left = sounds.length - placed;
    renderPhoneScreen();
    selectSlot(ctx.index);
    saveConfigToServer();
    showToast(left ? `${placed} sonidos puestos. ${left} no cabían en las casillas libres que quedan` : `${placed} sonidos puestos en casillas libres`);
  };

  // One button that plays them one after another (a multi-action of at most 8 steps).
  const oneButton = (server) => {
    const sounds = pickedSounds(server);
    const steps = sounds.slice(0, 8);
    assignFromTemplate(ctx.btn, ctx.index, {
      label: `${steps.length} sonidos`, sublabel: server, icon: "/static/icons/soundboard.svg", color: "#5865f2",
      action_type: "multi", target: "macro",
      extra: { actions: steps.map(sound => ({ ...actionOf(sound), delay_ms: 1500 })) },
    });
    // After the assignment: it shows its own toast, which would hide this one.
    showToast(sounds.length > 8
      ? `Una multiacción admite 8 pasos: se usan los 8 primeros de los ${sounds.length} que marcaste`
      : `Botón con ${steps.length} sonidos en orden, 1,5 s entre uno y otro`);
  };

  host.addEventListener("toggle", (event) => {
    const details = event.target.closest?.(".dc-server");
    if (details && !filter.value.trim()) openState.set(details.dataset.server, details.open);
  }, true);
  filter.addEventListener("input", draw);
  host.addEventListener("click", (event) => {
    const details = event.target.closest(".dc-server");
    if (!details) return;
    const server = details.dataset.server;
    const tile = event.target.closest(".dc-tile");
    const sound = tile && soundsOf(server).find(s => s.label === tile.dataset.label);
    if (event.target.closest("[data-pick]") && sound) {
      const set = picked.get(server);
      if (set.has(sound.label)) set.delete(sound.label);
      else if (set.size >= gridTotal()) return showToast(`Una página tiene ${gridTotal()} casillas: quita algún sonido antes de añadir otro`);
      else set.add(sound.label);
      draw();
    } else if (event.target.closest("[data-assign]") && sound) {
      assignFromTemplate(ctx.btn, ctx.index, {
        label: sound.name, sublabel: sound.section, icon: "/static/icons/soundboard.svg", color: "#5865f2", ...actionOf(sound),
      });
    } else if (event.target.closest("[data-test]") && sound) {
      withToast(async () => {
        const result = await postJson("/api/actions/test", actionOf(sound));
        if (!result.success) throw new Error(result.error || "No se pudo reproducir");
      }, "Sonido enviado a tu canal de voz");
    } else if (event.target.closest("[data-make-page]")) {
      createPage(server, false);
    } else if (event.target.closest("[data-fill]")) {
      fillCells(server);
    } else if (event.target.closest("[data-one]")) {
      oneButton(server);
    }
  });
  draw();
}

function connectorBodyDiscord(c, body, ctx) {
  const s = c.settings || {};
  const method = s.method === "hotkey" ? "hotkey" : "button";
  body.innerHTML = `
    ${statusLine(c)}
    <span class="section-label">Silenciar y ensordecer</span>
    <label class="check-row"><input type="radio" name="dc-method" value="button" ${method === "button" ? "checked" : ""}> Pulsando el botón de Discord (recomendado)</label>
    <label class="check-row"><input type="radio" name="dc-method" value="hotkey" ${method === "hotkey" ? "checked" : ""}> Con un atajo global que creas en Discord</label>
    <p class="integration-hint" id="dc-method-hint">${method === "button"
      ? "No hay que configurar nada, y la tecla se ilumina cuando estás silenciado. Discord tiene que estar abierto y a la vista (puede quedar detrás de otras ventanas, pero no minimizado)."
      : "Funciona con Discord minimizado, pero tienes que crear en Discord un atajo para cada acción (pasos abajo)."}</p>
    ${actionTilesHtml(c.actions)}
    <div id="dc-hotkeys" ${method === "hotkey" ? "" : "hidden"}>
      <label for="dc-mute">Atajo para silenciar</label>
      <input id="dc-mute" type="text" maxlength="40" value="${escapeHtml(s.mute_hotkey)}">
      <label for="dc-deafen">Atajo para ensordecer</label>
      <input id="dc-deafen" type="text" maxlength="40" value="${escapeHtml(s.deafen_hotkey)}">
      <button class="btn-primary" id="dc-save">Guardar atajos</button>
      <ol class="setup-steps">
        <li>En Discord abre Ajustes de usuario &gt; Atajos de teclado y pulsa Añadir un atajo.</li>
        <li>Elige la acción "Alternar silenciar" (o "Alternar ensordecer") y pulsa la misma combinación que guardaste arriba.</li>
      </ol>
    </div>
    <span class="section-label">Soundboard de tus servidores</span>
    <p class="integration-hint">StreamDesk lee el panel de sonidos de tu Discord y pulsa el sonido que elijas, como harías tú con el ratón. Por eso Discord debe estar abierto, sin minimizar, y tú dentro de un canal de voz: Discord solo ofrece ese panel en una llamada, y no permite reproducir sonidos desde fuera. Después de leerlos una vez, los sonidos quedan guardados y los puedes elegir sin estar en voz.</p>
    <p class="integration-hint"><strong>Sin abrir el panel:</strong> si en Discord (Ajustes &gt; Atajos de teclado) puedes asignar un atajo a un sonido, pégalo en el botón del sonido («Atajo de este sonido»): se reproducirá pulsando solo esa tecla, con Discord en segundo plano.</p>
    <p class="integration-hint" id="dc-voice">Mirando en qué canal de voz estás...</p>
    <button class="btn-primary" id="dc-scan">${discordSounds && !discordSounds.some(x => x.cached) ? "Actualizar mis sonidos" : "Leer mis sonidos desde Discord"}</button>
    <div id="dc-sounds-area"></div>`;
  wireTiles(body, c.actions, ctx);
  body.querySelectorAll('input[name="dc-method"]').forEach(radio => radio.addEventListener("change", () => withToast(async () => {
    await connectorApi("/discord/configure", { method: radio.value });
    body.querySelector("#dc-hotkeys").hidden = radio.value !== "hotkey";
    body.querySelector("#dc-method-hint").textContent = radio.value === "button"
      ? "No hay que configurar nada, y la tecla se ilumina cuando estás silenciado. Discord tiene que estar abierto y a la vista (puede quedar detrás de otras ventanas, pero no minimizado)."
      : "Funciona con Discord minimizado, pero tienes que crear en Discord un atajo para cada acción (pasos abajo).";
  }, radio.value === "button" ? "Silenciar y ensordecer pulsan el botón de Discord" : "Silenciar y ensordecer usan atajos")));
  body.querySelector("#dc-save").addEventListener("click", () => withToast(async () => {
    await connectorApi("/discord/configure", {
      mute_hotkey: body.querySelector("#dc-mute").value, deafen_hotkey: body.querySelector("#dc-deafen").value,
    });
    await ctx.refresh();
  }, "Atajos guardados"));

  connectorApi("/discord/options/voice").then(({ options }) => {
    const line = body.querySelector("#dc-voice");
    if (line) line.textContent = options.length ? `Ahora estás en un canal de voz de «${options[0].server}».` : "Ahora no estás en ningún canal de voz (o Discord está minimizado).";
  }).catch(() => {});

  const area = body.querySelector("#dc-sounds-area");
  if (discordSounds) renderDiscordSounds(area, ctx);
  else {
    // The last reading is on disk: show it without touching Discord.
    apiJson("/api/discord/sounds/cache").then(({ options }) => {
      if (!discordSounds && options.length && area.isConnected) { discordSounds = options; renderDiscordSounds(area, ctx); }
    }).catch(() => {});
  }
  const scan = body.querySelector("#dc-scan");
  scan.addEventListener("click", async () => {
    scan.disabled = true;
    area.innerHTML = '<p class="integration-hint">Leyendo el panel de sonidos de Discord, unos segundos. Verás cómo cambia de servidor: es normal.</p>';
    try {
      discordSounds = (await connectorApi("/discord/options/sounds")).options;
      if (area.isConnected) renderDiscordSounds(area, ctx);
      scan.textContent = discordSounds.some(x => x.cached) ? "Leer mis sonidos desde Discord" : "Actualizar mis sonidos";
    } catch (err) {
      if (area.isConnected) area.innerHTML = `<p class="integration-hint">${escapeHtml(err.message)}</p>`;
    }
    scan.disabled = false;
  });
}

const CONNECTOR_BODIES = { windows: connectorBodyWindows, obs: connectorBodyObs, spotify: connectorBodySpotify, discord: connectorBodyDiscord };

// Which connector belongs to a button. An app launcher belongs to the connector of that app (or to none).
// A button that already runs an action of a connector belongs to it. Anything else belongs to no one.
const APP_CONNECTORS = { discord: "discord", spotify: "spotify", obs: "obs", obs64: "obs", obs32: "obs" };
const ACTION_CONNECTORS = { obs_action: "obs", discord_hotkey: "discord", discord_sound: "discord", spotify_uri: "spotify", windows: "windows", command: "windows" };

function connectorScope(btn) {
  if (btn.action_type === "preset_app" || btn.action_type === "launch") {
    return { connector: APP_CONNECTORS[String(btn.target || "").toLowerCase()] || null, app: String(btn.label || btn.target || "esta aplicación") };
  }
  if (ACTION_CONNECTORS[btn.action_type]) return { connector: ACTION_CONNECTORS[btn.action_type], app: null };
  return null; // an empty or generic button: every connector
}

function renderTabConnectors(container, btn, index, pick = false) {
  const ctx = { btn, index, refresh: null, pick };
  const scope = connectorScope(btn);
  let showAll = !scope;
  if (scope?.connector) openConnectorId = scope.connector;

  const draw = (allConnectors) => {
    if (!container.isConnected) return;
    const connectors = showAll || !scope ? allConnectors : allConnectors.filter(c => c.id === scope.connector);
    const scopeNote = !scope ? "" : showAll
      ? `<button class="btn-secondary" id="conn-only-app">Ver solo los de ${escapeHtml(scope.connector ? (allConnectors.find(c => c.id === scope.connector)?.name || scope.connector) : "esta app")}</button>`
      : `${scope.connector ? "" : `<p class="integration-hint">${escapeHtml(scope.app)}: esta aplicación no tiene acciones propias en StreamDesk. Solo se puede abrir (pestaña Apps).</p>`}
         <button class="btn-secondary" id="conn-show-all">Ver todos los conectores</button>`;
    container.innerHTML = `
      <div class="integration-intro">
        <strong>${scope && !showAll ? "Acciones de esta app" : "Conecta tus apps"}</strong>
        <span>Elige un servicio, configúralo una vez y asigna sus acciones a esta casilla con un clic.</span>
      </div>
      ${scopeNote}
      ${connectors.map(c => `
        <section class="connector-card ${c.id === openConnectorId ? "open" : ""}">
          <button class="connector-head" data-connector="${escapeHtml(c.id)}">
            <img src="${escapeHtml(c.icon)}" alt="">
            <span class="connector-name">${escapeHtml(c.name)}</span>
            <span class="status-pill status-${escapeHtml(c.status.state)}">${STATUS_LABELS[c.status.state] || ""}</span>
          </button>
          ${c.id === openConnectorId ? `<div class="connector-body" id="connector-body-${escapeHtml(c.id)}"></div>` : ""}
        </section>`).join("")}`;
    container.querySelector("#conn-show-all")?.addEventListener("click", () => { showAll = true; draw(connectorCache); });
    container.querySelector("#conn-only-app")?.addEventListener("click", () => { showAll = false; draw(connectorCache); });
    container.querySelectorAll("[data-connector]").forEach(head => head.addEventListener("click", () => {
      openConnectorId = openConnectorId === head.dataset.connector ? null : head.dataset.connector;
      draw(connectorCache);
    }));
    const open = connectors.find(c => c.id === openConnectorId);
    const body = open && container.querySelector(`#connector-body-${open.id}`);
    if (body && CONNECTOR_BODIES[open.id]) CONNECTOR_BODIES[open.id](open, body, ctx);
  };

  ctx.refresh = async () => {
    const data = await connectorApi("");
    connectorCache = data.connectors;
    draw(connectorCache);
  };

  if (connectorCache) draw(connectorCache);
  else container.innerHTML = '<p class="integration-hint" style="padding:12px">Comprobando tus conectores...</p>';
  // Statuses can take a second (OBS, Spotify): show the cached cards now and refresh behind them.
  ctx.refresh().catch(() => {
    if (!connectorCache) container.innerHTML = '<p class="integration-hint" style="padding:12px">No se pudo cargar la lista de conectores.</p>';
  });
}

// The colour palette as labelled rows, the current colour marked.
function colorSwatchesHtml(current) {
  const now = String(current || "").toLowerCase();
  return COLOR_GROUPS.map(([name, colours]) => `
    <div class="swatch-group">
      <span class="swatch-group-name">${escapeHtml(name)}</span>
      <div class="swatch-row">${colours.map(c => `<button class="color-swatch-btn ${now === c ? "active" : ""}" data-color="${c}" style="background: ${c};" title="${c}" aria-label="${c}"></button>`).join("")}</div>
    </div>`).join("");
}

// Aspect tab: title, colour and icon.
function renderTabDesign(container, btn, index) {
  const swatchesHtml = colorSwatchesHtml(btn.color);

  const iconsHtml = SVG_ICONS.map(ic => `
    <button class="icon-choice-btn ${btn.image === `/static/icons/${ic}.svg` ? 'active' : ''}" data-icon="/static/icons/${ic}.svg" title="${ic}">
      <img src="/static/icons/${ic}.svg" alt="${ic}">
    </button>
  `).join("");

  container.innerHTML = `
    <div class="form-group">
      <label for="edit-btn-label">Título</label>
      <input type="text" id="edit-btn-label" maxlength="32" value="${escapeHtml(btn.label || '')}" placeholder="Ej. Discord">
    </div>

    <div class="form-group">
      <label for="edit-btn-sublabel">Subtítulo</label>
      <input type="text" id="edit-btn-sublabel" maxlength="36" value="${escapeHtml(btn.sublabel || '')}" placeholder="Ej. Voz">
    </div>

    <div class="form-group">
      <label>Color</label>
      <div class="color-swatches-grid">${swatchesHtml}</div>
      <input type="color" id="edit-btn-color-picker" value="${escapeHtml(btn.color || '#f8c700')}">
    </div>

    <div class="form-group">
      <label>Icono</label>
      <div class="icon-picker-grid">${iconsHtml}</div>
    </div>

    <div class="form-group">
      <label for="btn-custom-icon-upload">O sube tu propia imagen (PNG, JPG o WEBP, máx. 2 MB)</label>
      <input type="file" id="btn-custom-icon-upload" accept="image/png,image/jpeg,image/webp">
    </div>
  `;

  const labelInput = document.getElementById("edit-btn-label");
  const sublabelInput = document.getElementById("edit-btn-sublabel");
  const colorPicker = document.getElementById("edit-btn-color-picker");

  labelInput.addEventListener("input", (e) => {
    btn.label = e.target.value;
    document.getElementById("inspector-preview-title").textContent = btn.label;
    renderPhoneScreen();
    saveConfigToServer();
  });

  sublabelInput.addEventListener("input", (e) => {
    btn.sublabel = e.target.value;
    document.getElementById("inspector-preview-sub").textContent = btn.sublabel;
    renderPhoneScreen();
    saveConfigToServer();
  });

  colorPicker.addEventListener("input", (e) => {
    btn.color = e.target.value;
    // Mark the swatch with this exact colour, or none when it is a custom one.
    container.querySelectorAll(".color-swatch-btn").forEach(s => s.classList.toggle("active", s.dataset.color.toLowerCase() === e.target.value.toLowerCase()));
    renderPhoneScreen();
    saveConfigToServer();
  });

  container.querySelectorAll(".color-swatch-btn").forEach(s => {
    s.addEventListener("click", () => {
      btn.color = s.dataset.color;
      container.querySelectorAll(".color-swatch-btn").forEach(other => other.classList.toggle("active", other === s));
      colorPicker.value = btn.color;
      const accent = document.querySelector(".inspector-preview-card .slot-accent");
      if (accent) accent.style.background = btn.color;
      renderPhoneScreen();
      saveConfigToServer();
    });
  });

  container.querySelectorAll(".icon-choice-btn").forEach(ib => {
    ib.addEventListener("click", () => {
      btn.image = ib.dataset.icon;
      btn.icon = "";
      container.querySelectorAll(".icon-choice-btn").forEach(other => other.classList.toggle("active", other === ib));
      const preview = document.getElementById("inspector-preview-img");
      if (preview) preview.src = btn.image;
      renderPhoneScreen();
      saveConfigToServer();
    });
  });

  document.getElementById("btn-custom-icon-upload")?.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      showToast("Subiendo imagen...");
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.success && data.url) {
        btn.image = data.url;
        btn.icon = "";
        renderPhoneScreen();
        renderButtonInspector(btn, index);
        saveConfigToServer();
        showToast("Imagen añadida");
      } else {
        showToast(data.detail || "No se pudo subir la imagen");
      }
    } catch (err) {
      showToast("No se pudo subir la imagen");
    }
  });
}

// Fader inspector: master volume or one app's volume.
function renderSliderInspector(slider, index) {
  const isMaster = slider.slider_type === "master" || slider.type === "master";
  const col = index % gridCols();
  const currentSlots = config.pages[activePageIndex].slots;

  const sessions = [...new Map(audioSessions.map(s => [s.process_name, s])).values()];
  const sessionsHtml = sessions.length === 0
    ? `<div class="empty-note">Ninguna app está sonando ahora. Reproduce algo y vuelve a mirar.</div>`
    : sessions.map(s => `
      <div class="app-card-item ${slider.target_app?.toLowerCase() === s.process_name?.toLowerCase() ? 'selected' : ''}" data-proc="${escapeHtml(s.process_name)}" data-name="${escapeHtml(s.display_name)}">
        <div class="app-card-left">
          <span class="badge-live-dot"></span>
          <div>
            <div class="app-card-name">${escapeHtml(s.display_name)}</div>
            <div class="app-card-cat">${escapeHtml(s.process_name)}</div>
          </div>
        </div>
        <span class="app-card-badge">${Number(s.volume)}%</span>
      </div>`).join("");

  const swatchesHtml = colorSwatchesHtml(slider.color);

  inspectorContent.innerHTML = `
    <div class="inspector-preview-card">
      <div class="fader-preview">
        <strong>${escapeHtml(slider.label || 'Fader')}</strong>
        <div class="slot-fader-track"><div class="slot-fader-fill" style="height: 65%; background: ${escapeHtml(slider.color || '#f8c700')};"></div></div>
        <span class="slot-fader-val">65%</span>
      </div>
    </div>

    <div class="form-group">
      <label>Qué controla</label>
      <div class="segmented">
        <button class="${isMaster ? 'active' : ''}" id="btn-set-master">Volumen del PC</button>
        <button class="${!isMaster ? 'active' : ''}" id="btn-set-app">Una app</button>
      </div>
    </div>

    ${!isMaster ? `
      <div class="form-group">
        <label>Elige la app</label>
        <div class="apps-cards-grid" style="max-height: 200px;">${sessionsHtml}</div>
      </div>
    ` : ''}

    <div class="form-group">
      <label for="fader-span-value">Alto del fader</label>
      <div class="stepper">
        <button type="button" id="fader-shorter" aria-label="Fader más bajo" ${faderSpan(slider) <= 1 ? "disabled" : ""}>−</button>
        <strong id="fader-span-value">${faderSpan(slider)} ${faderSpan(slider) === 1 ? "fila" : "filas"}</strong>
        <button type="button" id="fader-taller" aria-label="Fader más alto" ${faderSpan(slider) >= gridRows() ? "disabled" : ""}>+</button>
      </div>
      <p class="integration-hint">Más alto da más recorrido para ajustar el volumen. También puedes arrastrar el borde inferior del fader en la vista previa. Para crecer necesita libres las casillas de debajo.</p>
    </div>

    <div class="form-group">
      <label for="edit-slider-label">Título</label>
      <input type="text" id="edit-slider-label" maxlength="32" value="${escapeHtml(slider.label || '')}" placeholder="Ej. Master o Spotify">
    </div>

    <div class="form-group">
      <label>Color</label>
      <div class="color-swatches-grid">${swatchesHtml}</div>
    </div>

    <button class="btn-danger" id="btn-delete-slider">
      <img src="/static/icons/trash.svg" alt=""> Quitar el fader de la columna ${col + 1}
    </button>
  `;

  document.getElementById("btn-set-master")?.addEventListener("click", () => {
    slider.slider_type = "master";
    slider.target_app = null;
    slider.label = "Master";
    slider.sublabel = "PC";
    slider.image = "/static/icons/volume_up.svg";
    slider.icon = "/static/icons/volume_up.svg";
    slider.color = "#f8c700";
    renderPhoneScreen();
    renderSliderInspector(slider, index);
    saveConfigToServer();
  });

  document.getElementById("btn-set-app")?.addEventListener("click", () => {
    slider.slider_type = "app_dynamic";
    slider.target_app = audioSessions[0] ? audioSessions[0].process_name : "Spotify.exe";
    slider.label = audioSessions[0] ? audioSessions[0].display_name : "Spotify";
    slider.sublabel = "App";
    slider.image = "/static/icons/spotify.svg";
    slider.icon = "/static/icons/spotify.svg";
    slider.color = "#1db954";
    renderPhoneScreen();
    renderSliderInspector(slider, index);
    saveConfigToServer();
  });

  inspectorContent.querySelectorAll(".app-card-item[data-proc]").forEach(item => {
    item.addEventListener("click", () => {
      const proc = item.dataset.proc;
      slider.target_app = proc;
      slider.label = item.dataset.name;
      slider.sublabel = "App";
      slider.image = proc.toLowerCase().includes("spotify") ? "/static/icons/spotify.svg" : (proc.toLowerCase().includes("discord") ? "/static/icons/discord.svg" : "/static/icons/fader.svg");
      renderPhoneScreen();
      renderSliderInspector(slider, index);
      saveConfigToServer();
      showToast(`Fader vinculado a ${item.dataset.name}`);
    });
  });

  document.getElementById("edit-slider-label")?.addEventListener("input", (e) => {
    slider.label = e.target.value;
    renderPhoneScreen();
    saveConfigToServer();
  });

  inspectorContent.querySelectorAll(".color-swatch-btn").forEach(s => {
    s.addEventListener("click", () => {
      slider.color = s.dataset.color;
      renderPhoneScreen();
      renderSliderInspector(slider, index);
      saveConfigToServer();
    });
  });

  const changeSpan = (delta) => { if (resizeFader(col, faderSpan(slider) + delta)) renderSliderInspector(slider, index); };
  document.getElementById("fader-shorter")?.addEventListener("click", () => changeSpan(-1));
  document.getElementById("fader-taller")?.addEventListener("click", () => changeSpan(1));

  document.getElementById("btn-delete-slider")?.addEventListener("click", () => {
    removeFader(currentSlots, col);
    renderPhoneScreen();
    selectSlot(col);
    saveConfigToServer();
    showUndoToast(`Fader quitado de la columna ${col + 1}`);
  });
}

// Save Configuration to Server. Small edits are batched so typing a title does
// not produce a network request for every character.
let saveTimer = null;
let pendingSave = null;
let resolvePendingSave = null;

function setSaveStatus(state, text) {
  const pill = document.getElementById("save-status");
  if (!pill) return;
  pill.dataset.state = state;
  document.getElementById("save-status-text").textContent = text;
}

async function persistConfig() {
  if (!config) return false;
  setSaveStatus("saving", "Guardando...");
  try {
    if (config.pages && config.pages[activePageIndex]) {
      config.slots = config.pages[activePageIndex].slots;
    }
    const response = await fetch("/api/deck/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      setSaveStatus("error", "No se guardó");
      showToast(typeof error.detail === "string" ? error.detail : "No se pudieron guardar los cambios");
      return false;
    }
    setSaveStatus("saved", "Guardado");
    return true;
  } catch (e) {
    console.error("Error saving config", e);
    setSaveStatus("error", "Sin conexión");
    showToast("No se pudo conectar para guardar");
    return false;
  }
}

function saveConfigToServer(options = {}) {
  if (!config) return Promise.resolve(false);
  if (saveTimer) clearTimeout(saveTimer);
  if (options.immediate === true) {
    if (resolvePendingSave) resolvePendingSave(false);
    pendingSave = null;
    resolvePendingSave = null;
    return persistConfig();
  }
  if (!pendingSave) {
    pendingSave = new Promise(resolve => { resolvePendingSave = resolve; });
  }
  saveTimer = setTimeout(async () => {
    const result = await persistConfig();
    const resolve = resolvePendingSave;
    pendingSave = null;
    resolvePendingSave = null;
    resolve?.(result);
  }, 350);
  return pendingSave;
}

let toastTimer = null;
// A message at the bottom. With {action: {label, run}} it carries a button (for example "Deshacer") and stays longer.
function showToast(msg, options = {}) {
  toast.textContent = msg;
  toast.classList.toggle("has-action", Boolean(options.action));
  if (options.action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = options.action.label;
    button.addEventListener("click", () => { toast.classList.remove("show"); options.action.run(); });
    toast.appendChild(document.createTextNode(" "));
    toast.appendChild(button);
  }
  toast.classList.add("show");
  clearTimeout(toastTimer);
  const wait = options.action ? 7000 : Math.max(2800, 60 * String(msg).length);
  toastTimer = setTimeout(() => toast.classList.remove("show"), wait);
}

// What was just removed can be brought back: the message says so with a button, not with a keyboard hint nobody reads.
function showUndoToast(msg) {
  showToast(msg, { action: { label: "Deshacer", run: undoLastDelete } });
}

// Saves what is waiting to be saved, now. Anything that reads the profile from the PC (adding a page from the
// library, duplicating one) must call it first, or the PC's copy is older than the screen's.
async function flushSave() {
  if (!pendingSave) return;
  clearTimeout(saveTimer);
  const resolve = resolvePendingSave;
  pendingSave = null;
  resolvePendingSave = null;
  const ok = await persistConfig();
  resolve?.(ok);
}

// Closing the window within the half second before a change is saved must not lose it.
window.addEventListener("pagehide", () => {
  if (!pendingSave || !config) return;
  try {
    if (config.pages && config.pages[activePageIndex]) config.slots = config.pages[activePageIndex].slots;
    fetch("/api/deck/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config), keepalive: true });
  } catch (e) { /* nothing more can be done while closing */ }
});

// Startup
window.addEventListener("DOMContentLoaded", () => {
  loadAuthInfo();
  loadConfig();
  loadSystemApps();
  loadAudioSessions();
  setupTrashDropZone();
  checkGitHubUpdates();
  connectStudioSocket();
  setInterval(loadAudioSessions, 15000); // safety net: the live feed does the real work
});
