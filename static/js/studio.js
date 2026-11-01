// StreamDesk Studio Pro — UI/UX Overhaul & 1-Click App Linking
let config = null;
let activePageIndex = 0;
let selectedSlotIndex = null;
let audioSessions = [];
let detectedSystemApps = [];
let dragSourceType = null; // 'palette_btn' | 'palette_slider' | 'slot'
let draggedSlotIndex = null;
let activeInspectorTab = "apps"; // apps | media | obs | telemetry | integrations | design

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

// Curated 8 Vibrant Color Swatches for instant styling
const COLOR_SWATCHES = [
  "#0ea5e9", // Electric Blue
  "#06b6d4", // Cyan
  "#a855f7", // Neon Purple
  "#10b981", // Emerald Green
  "#f59e0b", // Amber / Gold
  "#ef4444", // Crimson Red
  "#f43f5e", // Rose Pink
  "#64748b"  // Slate Dark
];

// Clean Vector SVG Library (30 Available Icons)
const SVG_ICONS = [
  "power", "play_pause", "play", "pause", "next", "prev", "mute", "volume_up",
  "spotify", "discord", "obs", "steam", "chrome", "gamepad", "video", "broadcast",
  "cpu", "ram", "disk", "sliders", "notes", "calc", "gear", "folder",
  "link", "macro", "plus", "trash", "youtube", "fader"
];

// Multimedia Preset Actions
const MEDIA_PRESETS = [
  { id: "play_pause", name: "Play / Pausa", icon: "/static/icons/play_pause.svg", color: "#22c55e", sub: "Reproducir / Pausar", target: "play_pause" },
  { id: "next", name: "Siguiente Pista", icon: "/static/icons/next.svg", color: "#38bdf8", sub: "Canción siguiente", target: "next" },
  { id: "prev", name: "Anterior Pista", icon: "/static/icons/prev.svg", color: "#38bdf8", sub: "Canción anterior", target: "prev" },
  { id: "mute", name: "Mute Master", icon: "/static/icons/mute.svg", color: "#ef4444", sub: "Silenciar ordenador", target: "mute" }
];

// Hardware Telemetry Presets
const TELEMETRY_PRESETS = [
  { id: "mon_cpu", name: "Monitor CPU", icon: "/static/icons/cpu.svg", color: "#0ea5e9", sub: "Uso de Procesador %", target: "cpu" },
  { id: "mon_ram", name: "Monitor RAM", icon: "/static/icons/ram.svg", color: "#8b5cf6", sub: "Memoria RAM %", target: "ram" },
  { id: "mon_disk", name: "Monitor SSD", icon: "/static/icons/disk.svg", color: "#10b981", sub: "Disco C: en vivo", target: "disk" },
  { id: "taskmgr", name: "Adm. Tareas", icon: "/static/icons/sliders.svg", color: "#f59e0b", sub: "Abrir TaskMgr", target: "taskmgr" }
];

// Load Pairing Info & QR
async function loadAuthInfo() {
  try {
    const res = await fetch("/api/auth/pin");
    const data = await res.json();
    document.getElementById("pin-code").textContent = data.pin;
    document.getElementById("qr-image").src = data.qr_code;
    document.getElementById("server-url").textContent = `http://${data.ip}:${data.port}`;
  } catch (e) {
    console.error("Error loading PIN", e);
  }
}

async function regenerateAuthPin() {
  try {
    const res = await fetch("/api/auth/regenerate-pin", { method: "POST" });
    const data = await res.json();
    document.getElementById("pin-code").textContent = data.pin;
    document.getElementById("qr-image").src = data.qr_code;
    document.getElementById("server-url").textContent = `http://${data.ip}:${data.port}`;
    showToast("¡Nuevo PIN y código QR generados!");
  } catch (e) {
    console.error("Error regenerating PIN", e);
  }
}

document.getElementById("btn-refresh-pin")?.addEventListener("click", () => {
  regenerateAuthPin();
});

// Check GitHub Updates
async function checkGitHubUpdates() {
  try {
    const res = await fetch("/api/system/check-update");
    const data = await res.json();
    if (data.update_available) {
      updateCylinder.className = "update-cylinder update-ready";
      updateStatusText.textContent = `Hay una versión nueva: ${data.commit_message || "actualización disponible"}`;
      btnApplyUpdate.style.display = "inline-block";
    } else {
      updateCylinder.className = "update-cylinder";
      const suffix = data.status === "offline" ? "sin conexión" : (data.can_update === false ? "" : "al día");
      updateStatusText.textContent = `v${data.current_version || ""}${suffix ? ` · ${suffix}` : ""}`;
      btnApplyUpdate.style.display = "none";
    }
  } catch (e) {
    console.log("Update check offline", e);
  }
}

btnApplyUpdate?.addEventListener("click", async () => {
  updateStatusText.textContent = "Actualizando desde GitHub...";
  try {
    const res = await fetch("/api/system/apply-update", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("¡Actualizado con éxito desde GitHub! Reiniciando...");
      setTimeout(() => window.location.reload(), 1500);
    } else {
      showToast("Aviso: " + (data.output || "Error al actualizar"));
    }
  } catch (err) {
    showToast("Error de conexión al actualizar");
  }
});

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
    renderAudioSessionsSidebar();
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
  pageTabs.innerHTML = "";

  const pages = config.pages || [];
  pages.forEach((p, idx) => {
    const btn = document.createElement("button");
    btn.className = `page-tab-btn ${idx === activePageIndex ? 'active' : ''}`;
    btn.textContent = p.name || `Pág ${idx + 1}`;
    btn.addEventListener("click", () => switchPage(idx));
    pageTabs.appendChild(btn);
  });

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
    const res = await fetch("/api/deck/page/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_index: activePageIndex })
    });
    const data = await res.json();
    if (data.success) {
      await loadConfig();
      const newPageIdx = Math.max(0, activePageIndex - 1);
      switchPage(newPageIdx);
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
      <p>Selecciona una casilla de la pantalla para asignarle una acción, conectar una app y cambiar su aspecto.</p>
    </div>
  `;
}

// Render the 6x2 Phone Screen Simulator
function renderPhoneScreen() {
  if (!config) return;
  phoneScreen.innerHTML = "";

  const pages = config.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config.slots) || [];

  for (let i = 0; i < 12; i++) {
    const slot = currentSlots[i] || { index: i, type: "empty" };
    const col = (i % 6) + 1; // 1 to 6
    const row = Math.floor(i / 6) + 1; // 1 or 2

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
      cell.style.gridRow = "1 / span 2"; // Occupies 2 vertical spaces!
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
      e.preventDefault();
      clearAllDragHighlights();
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

function clearAllDragHighlights() {
  document.querySelectorAll(".slot-cell").forEach(cell => {
    cell.classList.remove("drag-over", "drag-over-fader-top", "drag-over-fader-bottom");
  });
  document.getElementById("trash-dropzone")?.classList.remove("trash-drag-over");
}

function highlightCoordinatedFaderColumn(col) {
  clearAllDragHighlights();
  const topCell = document.getElementById(`cell_slot_${col}`);
  const bottomCell = document.getElementById(`cell_slot_${col + 6}`);
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
  slots[col] = { index: col, type: "empty" };
  slots[col + 6] = { index: col + 6, type: "empty" };
}

function emptySlotByIndex(idx) {
  const pages = config?.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
  const col = idx % 6;
  const slot = currentSlots[idx];
  if (!slot || slot.type === "empty") return;

  if (slot.type === "slider" || slot.type === "occupied_by_slider" || currentSlots[col]?.type === "slider") {
    clearColumn(currentSlots, col);
    showToast(`Columna #${col + 1} vaciada`);
  } else {
    currentSlots[idx] = { index: idx, type: "empty" };
    showToast(`Casilla #${idx + 1} vaciada`);
  }
  renderPhoneScreen();
  selectSlot(idx);
  saveConfigToServer();
}

function pasteCopiedSlot(targetIdx) {
  if (!copiedSlotConfig) return;
  const pages = config?.pages || [];
  const currentSlots = (pages[activePageIndex] ? pages[activePageIndex].slots : config?.slots) || [];
  const tCol = targetIdx % 6;

  if (copiedSlotConfig.type === "slider") {
    clearColumn(currentSlots, tCol);
    const pastedSlider = JSON.parse(JSON.stringify(copiedSlotConfig));
    pastedSlider.index = tCol;
    pastedSlider.id = `slider_${Date.now()}`;
    currentSlots[tCol] = pastedSlider;
    currentSlots[tCol + 6] = {
      index: tCol + 6,
      type: "occupied_by_slider",
      id: `slot_${tCol + 6}`,
      label: "Ocupado por Slider",
      parent_slot: tCol
    };
    renderPhoneScreen();
    selectSlot(tCol);
    triggerDropBounce(tCol);
    saveConfigToServer();
    showToast(`Fader pegado en Columna #${tCol + 1} (Ctrl+V)`);
  } else {
    if (currentSlots[tCol]?.type === "slider" || currentSlots[targetIdx]?.type === "occupied_by_slider") {
      clearColumn(currentSlots, tCol);
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

  wrap.addEventListener("dragstart", (e) => {
    dragSourceType = "slot";
    draggedSlotIndex = index;
    e.dataTransfer.effectAllowed = "move";
    wrap.classList.add("dragging");
    const cell = document.getElementById(`cell_slot_${index}`);
    if (cell) cell.classList.add("is-source-dragging");
  });

  wrap.addEventListener("dragend", () => {
    wrap.classList.remove("dragging");
    const cell = document.getElementById(`cell_slot_${index}`);
    if (cell) cell.classList.remove("is-source-dragging");
    clearAllDragHighlights();
  });

  let iconSrc = btn.image || btn.icon || "/static/icons/power.svg";

  wrap.innerHTML = `
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

  wrap.addEventListener("dragstart", (e) => {
    dragSourceType = "slot";
    draggedSlotIndex = index;
    e.dataTransfer.effectAllowed = "move";
    wrap.classList.add("dragging");
    const cell = document.getElementById(`cell_slot_${index}`);
    if (cell) cell.classList.add("is-source-dragging");
  });

  wrap.addEventListener("dragend", () => {
    wrap.classList.remove("dragging");
    const cell = document.getElementById(`cell_slot_${index}`);
    if (cell) cell.classList.remove("is-source-dragging");
    clearAllDragHighlights();
  });

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
  `;

  return wrap;
}

// Drag & Drop Handling on Slots
function handleDropOnSlot(targetIndex) {
  clearAllDragHighlights();
  const col = targetIndex % 6;
  const topSlot = col;
  const bottomSlot = col + 6;
  const currentSlots = config.pages[activePageIndex].slots;

  if (dragSourceType === "palette_slider") {
    clearColumn(currentSlots, col);
    currentSlots[topSlot] = {
      index: topSlot,
      type: "slider",
      id: `slider_${Date.now()}`,
      label: "Volumen",
      sublabel: "Master",
      slider_type: "master",
      target_app: null,
      row_span: 2,
      color: "#0ea5e9",
      icon: "/static/icons/volume_up.svg",
      image: "/static/icons/volume_up.svg"
    };
    currentSlots[bottomSlot] = {
      index: bottomSlot,
      type: "occupied_by_slider",
      id: `slot_${bottomSlot}`,
      label: "Ocupado por Slider",
      parent_slot: topSlot
    };

    renderPhoneScreen();
    selectSlot(topSlot);
    triggerDropBounce(topSlot);
    saveConfigToServer();
    showToast(`Fader de volumen colocado en Columna #${col + 1}`);

  } else if (dragSourceType === "palette_btn") {
    // If target column had a slider, clean up both slots cleanly!
    if (currentSlots[topSlot]?.type === "slider" || currentSlots[targetIndex]?.type === "occupied_by_slider") {
      clearColumn(currentSlots, col);
    }

    currentSlots[targetIndex] = {
      index: targetIndex,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Nueva Acción",
      sublabel: "App / Media",
      icon: "",
      image: "/static/icons/discord.svg",
      color: "#5865f2",
      action_type: "preset_app",
      target: "discord"
    };

    renderPhoneScreen();
    selectSlot(targetIndex);
    triggerDropBounce(targetIndex);
    saveConfigToServer();
    showToast("Botón colocado en la cuadrícula");

  } else if (dragSourceType === "slot" && draggedSlotIndex !== null) {
    if (draggedSlotIndex !== targetIndex) {
      const isSourceSlider = currentSlots[draggedSlotIndex]?.type === "slider";

      if (isSourceSlider) {
        const sCol = draggedSlotIndex % 6;
        const tCol = targetIndex % 6;
        if (sCol !== tCol) {
          const sourceSlider = JSON.parse(JSON.stringify(currentSlots[sCol]));
          clearColumn(currentSlots, sCol);
          clearColumn(currentSlots, tCol);

          sourceSlider.index = tCol;
          currentSlots[tCol] = sourceSlider;
          currentSlots[tCol + 6] = {
            index: tCol + 6,
            type: "occupied_by_slider",
            id: `slot_${tCol + 6}`,
            parent_slot: tCol
          };

          renderPhoneScreen();
          selectSlot(tCol);
          triggerDropBounce(tCol);
          saveConfigToServer();
          showToast(`Fader reubicado a Columna #${tCol + 1}`);
        }
      } else {
        const sIdx = draggedSlotIndex;
        const tIdx = targetIndex;
        const tCol = tIdx % 6;
        const sourceBtn = JSON.parse(JSON.stringify(currentSlots[sIdx]));

        // Check if target is in a slider column
        if (currentSlots[tCol]?.type === "slider" || currentSlots[tIdx]?.type === "occupied_by_slider") {
          clearColumn(currentSlots, tCol);
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
    paletteNewBtn.classList.add("is-dragging");
  });
  paletteNewBtn.addEventListener("dragend", () => {
    paletteNewBtn.classList.remove("is-dragging");
    clearAllDragHighlights();
  });
}

const paletteNewSlider = document.getElementById("palette-new-slider");
if (paletteNewSlider) {
  paletteNewSlider.addEventListener("dragstart", (e) => {
    dragSourceType = "palette_slider";
    e.dataTransfer.effectAllowed = "copy";
    paletteNewSlider.classList.add("is-dragging");
  });
  paletteNewSlider.addEventListener("dragend", () => {
    paletteNewSlider.classList.remove("is-dragging");
    clearAllDragHighlights();
  });
}

// Keyboard Shortcuts Controller
window.addEventListener("keydown", (e) => {
  const activeEl = document.activeElement;
  if (activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.isContentEditable)) {
    return;
  }

  if (e.key === "Delete" || e.key === "Backspace") {
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
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    const next = selectedSlotIndex === null ? 0 : (selectedSlotIndex + 1) % 12;
    selectSlot(next);
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    const prev = selectedSlotIndex === null ? 0 : (selectedSlotIndex + 11) % 12;
    selectSlot(prev);
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    const down = selectedSlotIndex === null ? 0 : (selectedSlotIndex + 6) % 12;
    selectSlot(down);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    const up = selectedSlotIndex === null ? 0 : (selectedSlotIndex + 6) % 12;
    selectSlot(up);
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
    inspectorTitle.textContent = `Configurar Fader (Col #${(index % 6) + 1})`;
    renderSliderInspector(slot, index);
  }
}

// Empty Slot Inspector
function renderEmptySlotInspector(index) {
  const col = index % 6;
  const currentSlots = config.pages[activePageIndex].slots;

  inspectorContent.innerHTML = `
    <p class="integration-hint" style="margin-bottom: 14px;">Esta casilla está vacía. ¿Qué quieres poner aquí?</p>
    <div class="inspector-actions">
      <button class="btn-primary" id="btn-create-button-here">
        <img src="/static/icons/power.svg" alt=""> Añadir un botón
      </button>
      <button class="btn-secondary" id="btn-create-slider-here">
        <img src="/static/icons/fader.svg" alt=""> Añadir un fader de volumen (columna ${col + 1})
      </button>
    </div>
  `;

  document.getElementById("btn-create-button-here")?.addEventListener("click", () => {
    currentSlots[index] = {
      index,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Acción",
      sublabel: "",
      icon: "",
      image: "/static/icons/power.svg",
      color: "#f8c700",
      action_type: "preset_app",
      target: "calc"
    };
    activeInspectorTab = "apps";
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
  });

  document.getElementById("btn-create-slider-here")?.addEventListener("click", () => {
    currentSlots[col] = {
      index: col,
      type: "slider",
      id: `slider_${Date.now()}`,
      label: "Volumen",
      sublabel: "Master",
      slider_type: "master",
      target_app: null,
      row_span: 2,
      color: "#0ea5e9",
      icon: "/static/icons/volume_up.svg",
      image: "/static/icons/volume_up.svg"
    };
    currentSlots[col + 6] = {
      index: col + 6,
      type: "occupied_by_slider",
      id: `slot_${col + 6}`,
      parent_slot: col
    };
    renderPhoneScreen();
    selectSlot(col);
    saveConfigToServer();
  });
}

// Button inspector: what it does (Apps, Controles, Conectores) and how it looks (Aspecto).
const INSPECTOR_TABS = [
  ["apps", "Apps"],
  ["controls", "Controles"],
  ["integrations", "Conectores"],
  ["design", "Aspecto"],
];

function renderButtonInspector(btn, index) {
  const currentSlots = config.pages[activePageIndex].slots;
  if (!INSPECTOR_TABS.some(([id]) => id === activeInspectorTab)) {
    // A tab remembered from an older layout (media, telemetry, obs).
    activeInspectorTab = activeInspectorTab === "obs" ? "integrations" : "controls";
  }

  inspectorContent.innerHTML = `
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

    <div class="inspector-tabs" role="tablist">
      ${INSPECTOR_TABS.map(([id, name]) => `<button class="inspector-tab-btn ${activeInspectorTab === id ? 'active' : ''}" role="tab" data-tab="${id}">${name}</button>`).join("")}
    </div>

    <div id="inspector-tab-content"></div>

    <button class="btn-danger" id="btn-delete-slot">
      <img src="/static/icons/trash.svg" alt=""> Vaciar esta casilla
    </button>
  `;

  inspectorContent.querySelectorAll(".inspector-tab-btn").forEach(t => {
    t.addEventListener("click", () => {
      activeInspectorTab = t.dataset.tab;
      renderButtonInspector(btn, index);
    });
  });

  const tabContainer = document.getElementById("inspector-tab-content");
  const renderers = {
    apps: renderTabApps,
    controls: renderTabControls,
    integrations: renderTabConnectors,
    design: renderTabDesign,
  };
  renderers[activeInspectorTab](tabContainer, btn, index);

  document.getElementById("btn-delete-slot")?.addEventListener("click", () => {
    currentSlots[index] = { index, type: "empty" };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
    showToast(`Casilla ${index + 1} vaciada`);
  });
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

// Media keys and live PC monitors.
function renderTabControls(container, btn, index) {
  const tile = (p, kind) => `
    <div class="quick-action-card" data-kind="${kind}" data-id="${p.id}">
      <img src="${p.icon}" alt="">
      <div class="quick-action-name">${p.name}</div>
      <div class="quick-action-sub">${p.sub}</div>
    </div>`;

  container.innerHTML = `
    <span class="section-label" style="margin-top: 0;">Multimedia</span>
    <div class="quick-actions-grid">${MEDIA_PRESETS.map(p => tile(p, "media")).join("")}</div>
    <span class="section-label">Sistema</span>
    <div class="quick-actions-grid">${TELEMETRY_PRESETS.map(p => tile(p, "system")).join("")}</div>
  `;

  container.querySelectorAll(".quick-action-card").forEach(card => {
    card.addEventListener("click", () => {
      if (card.dataset.kind === "media") {
        const preset = MEDIA_PRESETS.find(p => p.id === card.dataset.id);
        assignFromTemplate(btn, index, {
          label: preset.name, sublabel: "Multimedia", icon: preset.icon, color: preset.color,
          action_type: "media", target: preset.target,
        });
      } else {
        const preset = TELEMETRY_PRESETS.find(p => p.id === card.dataset.id);
        // The Task Manager tile opens an app; the others are live gauges. They are different action types.
        const opensApp = preset.target === "taskmgr";
        assignFromTemplate(btn, index, {
          label: preset.name, sublabel: opensApp ? "Abrir" : "En vivo", icon: preset.icon, color: preset.color,
          action_type: opensApp ? "preset_app" : "hardware_monitor", target: preset.target,
        });
      }
    });
  });
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
  btn.label = String(t.label || "Acción").slice(0, 32);
  btn.sublabel = String(t.sublabel || "").slice(0, 36);
  btn.image = t.icon;
  btn.icon = "";
  btn.color = t.color;
  btn.action_type = t.action_type;
  btn.target = t.target;
  btn.extra = t.extra || {};
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
    <p class="integration-hint">Reproducir directamente exige una cuenta Premium. Sin conectar, el botón abre la lista en Spotify.</p>
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

function connectorBodyDiscord(c, body, ctx) {
  const s = c.settings || {};
  body.innerHTML = `
    ${statusLine(c)}
    <label for="dc-mute">Atajo para silenciar</label>
    <input id="dc-mute" type="text" maxlength="40" value="${escapeHtml(s.mute_hotkey)}">
    <label for="dc-deafen">Atajo para ensordecer</label>
    <input id="dc-deafen" type="text" maxlength="40" value="${escapeHtml(s.deafen_hotkey)}">
    <button class="btn-primary" id="dc-save">Guardar atajos</button>
    ${actionTilesHtml(c.actions)}
    <ol class="setup-steps">
      <li>En Discord abre Ajustes de usuario &gt; Atajos de teclado y pulsa Añadir un atajo.</li>
      <li>Elige la acción "Alternar silenciar" (o "Alternar ensordecer") y pulsa la misma combinación que guardaste arriba.</li>
    </ol>
    <p class="integration-hint">Sin configurar nada en Discord: el botón "Mute micrófono" de Windows silencia el micro para todas las apps.</p>
    <p class="integration-hint">Sonidos del soundboard: todavía no disponibles, Discord no los permite sin un bot propio.</p>`;
  wireTiles(body, c.actions, ctx);
  body.querySelector("#dc-save").addEventListener("click", () => withToast(async () => {
    await connectorApi("/discord/configure", {
      mute_hotkey: body.querySelector("#dc-mute").value, deafen_hotkey: body.querySelector("#dc-deafen").value,
    });
    await ctx.refresh();
  }, "Atajos guardados"));
}

const CONNECTOR_BODIES = { windows: connectorBodyWindows, obs: connectorBodyObs, spotify: connectorBodySpotify, discord: connectorBodyDiscord };

function renderTabConnectors(container, btn, index) {
  const ctx = { btn, index, refresh: null };

  const draw = (connectors) => {
    if (!container.isConnected) return;
    container.innerHTML = `
      <div class="integration-intro">
        <strong>Conecta tus apps</strong>
        <span>Elige un servicio, configúralo una vez y asigna sus acciones a esta casilla con un clic.</span>
      </div>
      ${connectors.map(c => `
        <section class="connector-card ${c.id === openConnectorId ? "open" : ""}">
          <button class="connector-head" data-connector="${escapeHtml(c.id)}">
            <img src="${escapeHtml(c.icon)}" alt="">
            <span class="connector-name">${escapeHtml(c.name)}</span>
            <span class="status-pill status-${escapeHtml(c.status.state)}">${STATUS_LABELS[c.status.state] || ""}</span>
          </button>
          ${c.id === openConnectorId ? `<div class="connector-body" id="connector-body-${escapeHtml(c.id)}"></div>` : ""}
        </section>`).join("")}`;
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

// Aspect tab: title, colour and icon.
function renderTabDesign(container, btn, index) {
  const swatchesHtml = COLOR_SWATCHES.map(c => `
    <button class="color-swatch-btn ${btn.color === c ? 'active' : ''}" data-color="${c}" style="background: ${c};" title="${c}"></button>
  `).join("");

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
    renderPhoneScreen();
    saveConfigToServer();
  });

  container.querySelectorAll(".color-swatch-btn").forEach(s => {
    s.addEventListener("click", () => {
      btn.color = s.dataset.color;
      renderPhoneScreen();
      renderButtonInspector(btn, index);
      saveConfigToServer();
    });
  });

  container.querySelectorAll(".icon-choice-btn").forEach(ib => {
    ib.addEventListener("click", () => {
      btn.image = ib.dataset.icon;
      btn.icon = "";
      renderPhoneScreen();
      renderButtonInspector(btn, index);
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
  const col = index % 6;
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

  const swatchesHtml = COLOR_SWATCHES.map(c => `
    <button class="color-swatch-btn ${slider.color === c ? 'active' : ''}" data-color="${c}" style="background: ${c};" title="${c}"></button>
  `).join("");

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

  document.getElementById("btn-delete-slider")?.addEventListener("click", () => {
    currentSlots[col] = { index: col, type: "empty" };
    currentSlots[col + 6] = { index: col + 6, type: "empty" };
    renderPhoneScreen();
    selectSlot(col);
    saveConfigToServer();
    showToast(`Fader quitado de la columna ${col + 1}`);
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
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

// Startup
window.addEventListener("DOMContentLoaded", () => {
  loadAuthInfo();
  loadConfig();
  loadSystemApps();
  loadAudioSessions();
  setupTrashDropZone();
  checkGitHubUpdates();
  setInterval(loadAudioSessions, 3000);
});
