// StreamDesk Studio Pro — 6x2 Multi-Page Editor & Telemetry Presets
let config = null;
let activePageIndex = 0;
let selectedSlotIndex = null;
let audioSessions = [];
let dragSourceType = null; // 'palette_btn' | 'palette_slider' | 'slot'
let draggedSlotIndex = null;

const phoneScreen = document.getElementById("phone-screen");
const inspectorTitle = document.getElementById("inspector-title");
const inspectorContent = document.getElementById("inspector-content");
const toast = document.getElementById("toast");
const updateCylinder = document.getElementById("update-cylinder");
const updateStatusIcon = document.getElementById("update-status-icon");
const updateStatusText = document.getElementById("update-status-text");
const btnApplyUpdate = document.getElementById("btn-apply-update");
const pageTabs = document.getElementById("page-tabs");
const btnAddPage = document.getElementById("btn-add-page");

// Complete 1-Click Clean Presets with Vector SVGs
const ONE_CLICK_PRESETS = [
  // Apps
  { id: "discord", name: "Discord", icon: "", image: "/static/icons/discord.svg", color: "#5865f2", type: "preset_app", target: "discord", sub: "Voz / Chat" },
  { id: "spotify", name: "Spotify", icon: "", image: "/static/icons/spotify.svg", color: "#1db954", type: "preset_app", target: "spotify", sub: "Música" },
  { id: "obs", name: "OBS Studio", icon: "", image: "/static/icons/obs.svg", color: "#302e31", type: "preset_app", target: "obs", sub: "Directo" },
  { id: "steam", name: "Steam", icon: "", image: "/static/icons/steam.svg", color: "#171a21", type: "preset_app", target: "steam", sub: "Juegos" },
  { id: "chrome", name: "Chrome", icon: "", image: "/static/icons/chrome.svg", color: "#ea4335", type: "preset_app", target: "chrome", sub: "Navegador" },
  { id: "valorant", name: "Valorant", icon: "", image: "/static/icons/gamepad.svg", color: "#d13639", type: "preset_app", target: "valorant", sub: "Riot Games" },

  // OBS Studio
  { id: "obs_rec", name: "OBS Grabar", icon: "", image: "/static/icons/video.svg", color: "#ef4444", type: "obs_action", target: "record_toggle", sub: "Toggle Rec" },
  { id: "obs_stream", name: "OBS Stream", icon: "", image: "/static/icons/broadcast.svg", color: "#8b5cf6", type: "obs_action", target: "stream_toggle", sub: "En Vivo" },
  { id: "obs_next", name: "OBS Escena +", icon: "", image: "/static/icons/next.svg", color: "#38bdf8", type: "obs_action", target: "next_scene", sub: "Siguiente" },
  { id: "obs_mute", name: "Mute Micro OBS", icon: "", image: "/static/icons/mute.svg", color: "#ef4444", type: "obs_action", target: "mute_mic", sub: "Audio OBS" },

  // Telemetry & Hardware Monitors
  { id: "mon_cpu", name: "Monitor CPU", icon: "", image: "/static/icons/cpu.svg", color: "#0ea5e9", type: "hardware_monitor", target: "cpu", sub: "Carga %" },
  { id: "mon_ram", name: "Monitor RAM", icon: "", image: "/static/icons/ram.svg", color: "#8b5cf6", type: "hardware_monitor", target: "ram", sub: "Memoria %" },
  { id: "mon_disk", name: "Monitor SSD", icon: "", image: "/static/icons/disk.svg", color: "#10b981", type: "hardware_monitor", target: "disk", sub: "Espacio C:" },
  { id: "taskmgr", name: "Administrador Tareas", icon: "", image: "/static/icons/sliders.svg", color: "#f59e0b", type: "launch", target: "taskmgr", sub: "Monitor Windows" },

  // Media
  { id: "play_pause", name: "Play / Pausa", icon: "", image: "/static/icons/play_pause.svg", color: "#22c55e", type: "media", target: "play_pause", sub: "Multimedia" },
  { id: "next", name: "Siguiente Pista", icon: "", image: "/static/icons/next.svg", color: "#38bdf8", type: "media", target: "next", sub: "Audio" },
  { id: "prev", name: "Anterior Pista", icon: "", image: "/static/icons/prev.svg", color: "#38bdf8", type: "media", target: "prev", sub: "Audio" },
  { id: "mute", name: "Mute Master", icon: "", image: "/static/icons/mute.svg", color: "#ef4444", type: "media", target: "mute", sub: "Silenciar PC" },

  // Utilities
  { id: "calc", name: "Calculadora", icon: "", image: "/static/icons/calc.svg", color: "#f59e0b", type: "launch", target: "calc", sub: "Utilidad" },
  { id: "notepad", name: "Notas", icon: "", image: "/static/icons/notes.svg", color: "#06b6d4", type: "launch", target: "notepad", sub: "Editor" },
  { id: "macro", name: "Modo Stream", icon: "", image: "/static/icons/macro.svg", color: "#a855f7", type: "multi", target: "stream", sub: "Macro OBS+Discord" },
  { id: "youtube", name: "YouTube", icon: "", image: "/static/icons/youtube.svg", color: "#e11d48", type: "url", target: "https://www.youtube.com", sub: "Web" }
];

// Load Pairing Info
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

// Check GitHub Updates
async function checkGitHubUpdates() {
  try {
    const res = await fetch("/api/system/check-update");
    const data = await res.json();
    if (data.update_available) {
      updateCylinder.className = "update-cylinder update-ready";
      updateStatusIcon.textContent = "🟡";
      updateStatusText.textContent = `¡Actualización en GitHub! (${data.commit_message || 'Nueva versión'})`;
      btnApplyUpdate.style.display = "inline-block";
    } else {
      updateCylinder.className = "update-cylinder";
      updateStatusIcon.textContent = "🟢";
      updateStatusText.textContent = `StreamDesk v${data.current_version || '2.2.0'} (Al día)`;
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

// Load Audio Sessions
async function loadAudioSessions() {
  try {
    const res = await fetch("/api/audio/sessions");
    const data = await res.json();
    audioSessions = data.sessions || [];
    renderAudioSessionsList();
  } catch (e) {}
}

function renderAudioSessionsList() {
  const container = document.getElementById("audio-sessions-list");
  if (!container) return;
  container.innerHTML = "";

  if (audioSessions.length === 0) {
    container.innerHTML = `<div style="font-size: 0.75rem; color: var(--text-muted);">Sin audio activo</div>`;
    return;
  }

  audioSessions.forEach(s => {
    const div = document.createElement("div");
    div.style.cssText = "display: flex; justify-content: space-between; padding: 4px 8px; background: #080b12; border-radius: 6px; font-size: 0.72rem;";
    div.innerHTML = `
      <span>${s.display_name}</span>
      <span style="color: var(--accent-cyan); font-weight: 700;">${s.volume}%</span>
    `;
    container.appendChild(div);
  });
}

// Load Configuration (6x2 Grid Multi-Page)
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    config = await res.json();
    activePageIndex = config.current_page || 0;
    renderPageTabs();
    renderPhoneScreen();
  } catch (e) {
    console.error("Error loading config", e);
  }
}

// Page Tabs Management
function renderPageTabs() {
  if (!pageTabs || !config) return;
  pageTabs.innerHTML = "";

  const pages = config.pages || [{ id: "page_main", name: "Principal", slots: config.slots || [] }];

  pages.forEach((p, idx) => {
    const btn = document.createElement("button");
    btn.className = `page-tab-btn ${idx === activePageIndex ? 'active' : ''}`;
    btn.textContent = p.name || `Pág ${idx + 1}`;
    btn.addEventListener("click", () => switchPage(idx));
    pageTabs.appendChild(btn);
  });
}

async function switchPage(pageIdx) {
  if (!config) return;
  const pages = config.pages || [];
  if (pageIdx >= 0 && pageIdx < pages.length) {
    activePageIndex = pageIdx;
    config.current_page = pageIdx;
    config.slots = pages[pageIdx].slots;
    selectedSlotIndex = null;
    renderPageTabs();
    renderPhoneScreen();
    // Sync with server
    try {
      await fetch("/api/deck/page/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_index: pageIdx })
      });
    } catch (e) {}
  }
}

btnAddPage?.addEventListener("click", async () => {
  const pageName = prompt("Nombre de la nueva página:", `Página ${(config.pages || []).length + 1}`);
  if (!pageName) return;

  try {
    const res = await fetch("/api/deck/page/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: pageName })
    });
    const data = await res.json();
    if (data.success) {
      config.pages = data.pages;
      await switchPage(config.pages.length - 1);
      showToast(`¡Página "${pageName}" creada!`);
    }
  } catch (e) {
    showToast("Error al crear la página");
  }
});

// Render the 6x2 Phone Screen Simulator for Active Page
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
      cell.classList.add("drag-over");
    });

    cell.addEventListener("dragleave", () => {
      cell.classList.remove("drag-over");
    });

    cell.addEventListener("drop", (e) => {
      e.preventDefault();
      cell.classList.remove("drag-over");
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

function createStudioButtonKeycap(btn, index) {
  const wrap = document.createElement("div");
  wrap.className = "slot-keycap";
  wrap.draggable = true;

  wrap.addEventListener("dragstart", (e) => {
    dragSourceType = "slot";
    draggedSlotIndex = index;
    e.dataTransfer.effectAllowed = "move";
  });

  let iconHtml = "";
  if (btn.image) {
    iconHtml = `<img src="${btn.image}" class="slot-keycap-img" alt="${btn.label}">`;
  } else if (btn.icon && (btn.icon.startsWith("/") || btn.icon.endsWith(".svg"))) {
    iconHtml = `<img src="${btn.icon}" class="slot-keycap-img" alt="${btn.label}">`;
  } else if (btn.icon) {
    iconHtml = `<span class="slot-keycap-emoji">${btn.icon}</span>`;
  } else {
    iconHtml = `<img src="/static/icons/power.svg" class="slot-keycap-img" alt="">`;
  }

  wrap.innerHTML = `
    <div class="slot-keycap-inner">
      <div class="slot-accent" style="background: ${btn.color || 'var(--accent-blue)'}"></div>
      ${iconHtml}
      <div class="slot-keycap-title">${btn.label || 'Botón'}</div>
      <div style="font-size: 0.55rem; color: var(--text-muted);">${btn.sublabel || ''}</div>
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
  });

  const headerIcon = slider.image 
    ? `<img src="${slider.image}" style="width: 14px; height: 14px; margin-bottom: 2px;">` 
    : `<img src="/static/icons/${isMaster ? 'volume_up' : 'spotify'}.svg" style="width: 14px; height: 14px; margin-bottom: 2px;">`;

  wrap.innerHTML = `
    <div style="font-size: 0.68rem; font-weight: 700; color: #fff; text-align: center; display: flex; flex-direction: column; align-items: center;">
      ${headerIcon}
      <span>${slider.label || (isMaster ? 'Master' : 'App')}</span>
    </div>
    <div class="slot-fader-track">
      <div class="slot-fader-fill" style="height: 50%; background: ${slider.color || (isMaster ? 'var(--accent-blue)' : 'var(--accent-purple)')};"></div>
    </div>
    <div style="font-size: 0.72rem; font-weight: 800; color: var(--text-main);">50%</div>
  `;

  return wrap;
}

// Drag & Drop Handling on Slots
function handleDropOnSlot(targetIndex) {
  const col = targetIndex % 6;
  const topSlot = col;
  const bottomSlot = col + 6;
  const currentSlots = config.pages[activePageIndex].slots;

  if (dragSourceType === "palette_slider") {
    // Add new vertical volume slider occupying 2 vertical spaces in column 'col'
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
    saveConfigToServer();
    showToast("Fader de volumen colocado (2 casillas)");

  } else if (dragSourceType === "palette_btn") {
    // If target column was previously a slider, free both slots
    if (currentSlots[topSlot]?.type === "slider") {
      currentSlots[topSlot] = { index: topSlot, type: "empty" };
      currentSlots[bottomSlot] = { index: bottomSlot, type: "empty" };
    }

    currentSlots[targetIndex] = {
      index: targetIndex,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Acción",
      sublabel: "",
      icon: "",
      image: "/static/icons/discord.svg",
      color: "#5865f2",
      action_type: "preset_app",
      target: "discord"
    };

    renderPhoneScreen();
    selectSlot(targetIndex);
    saveConfigToServer();
    showToast("Botón colocado en la cuadrícula");

  } else if (dragSourceType === "slot" && draggedSlotIndex !== null) {
    if (draggedSlotIndex !== targetIndex) {
      const sourceSlot = currentSlots[draggedSlotIndex];
      const targetSlot = currentSlots[targetIndex];

      // If moving a slider, swap or place whole column
      if (sourceSlot?.type === "slider") {
        const sCol = draggedSlotIndex % 6;
        const tCol = targetIndex % 6;
        
        // Free old column
        currentSlots[sCol] = { index: sCol, type: "empty" };
        currentSlots[sCol + 6] = { index: sCol + 6, type: "empty" };

        // Set in new column
        sourceSlot.index = tCol;
        currentSlots[tCol] = sourceSlot;
        currentSlots[tCol + 6] = {
          index: tCol + 6,
          type: "occupied_by_slider",
          id: `slot_${tCol + 6}`,
          parent_slot: tCol
        };
        renderPhoneScreen();
        selectSlot(tCol);
        saveConfigToServer();
        showToast("Fader reubicado");
      } else {
        // Swap standard slots
        currentSlots[draggedSlotIndex] = targetSlot || { index: draggedSlotIndex, type: "empty" };
        currentSlots[targetIndex] = sourceSlot;

        if (currentSlots[draggedSlotIndex]) currentSlots[draggedSlotIndex].index = draggedSlotIndex;
        if (currentSlots[targetIndex]) currentSlots[targetIndex].index = targetIndex;

        renderPhoneScreen();
        selectSlot(targetIndex);
        saveConfigToServer();
        showToast("Posiciones actualizadas");
      }
    }
  }

  dragSourceType = null;
  draggedSlotIndex = null;
}

// Palette Drag Events
document.getElementById("palette-new-btn")?.addEventListener("dragstart", (e) => {
  dragSourceType = "palette_btn";
  e.dataTransfer.effectAllowed = "copy";
});

document.getElementById("palette-new-slider")?.addEventListener("dragstart", (e) => {
  dragSourceType = "palette_slider";
  e.dataTransfer.effectAllowed = "copy";
});

// Select Slot and Open Right Inspector
function selectSlot(index) {
  selectedSlotIndex = index;
  renderPhoneScreen();

  const currentSlots = config.pages[activePageIndex].slots;
  const slot = currentSlots[index];

  if (!slot || slot.type === "empty") {
    inspectorTitle.textContent = `Casilla #${index + 1} (Vacía)`;
    renderEmptySlotInspector(index);
  } else if (slot.type === "button") {
    inspectorTitle.textContent = `Configurar Botón (Casilla #${index + 1})`;
    renderButtonInspector(slot, index);
  } else if (slot.type === "slider") {
    inspectorTitle.textContent = `Configurar Fader (Columna #${(index % 6) + 1})`;
    renderSliderInspector(slot, index);
  }
}

// Empty Slot Inspector
function renderEmptySlotInspector(index) {
  const col = index % 6;
  const currentSlots = config.pages[activePageIndex].slots;

  inspectorContent.innerHTML = `
    <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 14px;">
      Esta casilla está vacía. Selecciona una acción o crea un fader:
    </p>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <button class="btn-primary" id="btn-create-button-here" style="justify-content: center;">
        <img src="/static/icons/power.svg" style="width: 16px; height: 16px;"> Crear Botón Aquí (1 Casilla)
      </button>
      <button class="btn-primary" id="btn-create-slider-here" style="justify-content: center; background: var(--accent-purple);">
        <img src="/static/icons/fader.svg" style="width: 16px; height: 16px;"> Crear Fader en Columna #${col + 1} (2 Casillas)
      </button>
    </div>
  `;

  document.getElementById("btn-create-button-here")?.addEventListener("click", () => {
    currentSlots[index] = {
      index,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Nuevo Botón",
      sublabel: "",
      icon: "",
      image: "/static/icons/discord.svg",
      color: "#5865f2",
      action_type: "preset_app",
      target: "discord"
    };
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

// Ultra Simple Button Inspector (1-Click Presets with SVGs)
function renderButtonInspector(btn, index) {
  let presetButtonsHtml = ONE_CLICK_PRESETS.map(p => `
    <button class="quick-app-btn" data-preset-id="${p.id}">
      <img src="${p.image}" alt="${p.name}">
      <div>
        <div class="quick-app-label">${p.name}</div>
        <div style="font-size: 0.65rem; color: var(--text-muted);">${p.sub}</div>
      </div>
    </button>
  `).join("");

  inspectorContent.innerHTML = `
    <div class="form-group">
      <label>Asignar Acción Rápida (1 Clic)</label>
      <div class="quick-apps-grid" style="max-height: 220px; overflow-y: auto;">
        ${presetButtonsHtml}
      </div>
    </div>

    <div style="border-top: 1px solid var(--border); margin: 12px 0;"></div>

    <div class="form-group">
      <label>Título del Botón</label>
      <input type="text" id="edit-btn-label" value="${btn.label || ''}">
    </div>

    <div class="form-group">
      <label>Subtítulo</label>
      <input type="text" id="edit-btn-sublabel" value="${btn.sublabel || ''}">
    </div>

    <div class="form-group">
      <label>Color de Acento</label>
      <input type="color" id="edit-btn-color" value="${btn.color || '#0ea5e9'}" style="height: 38px; padding: 2px;">
    </div>

    <button class="btn-danger" id="btn-delete-slot">
      Vaciar esta Casilla
    </button>
  `;

  // 1-Click Preset Click Handler
  inspectorContent.querySelectorAll(".quick-app-btn").forEach(b => {
    b.addEventListener("click", () => {
      const pid = b.dataset.presetId;
      const preset = ONE_CLICK_PRESETS.find(p => p.id === pid);
      if (preset) {
        btn.label = preset.name;
        btn.sublabel = preset.sub;
        btn.icon = preset.icon || "";
        btn.image = preset.image;
        btn.color = preset.color;
        btn.action_type = preset.type;
        btn.target = preset.target;
        renderPhoneScreen();
        renderButtonInspector(btn, index);
        saveConfigToServer();
        showToast(`¡Configurado con ${preset.name}!`);
      }
    });
  });

  document.getElementById("edit-btn-label")?.addEventListener("input", (e) => {
    btn.label = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("edit-btn-sublabel")?.addEventListener("input", (e) => {
    btn.sublabel = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("edit-btn-color")?.addEventListener("input", (e) => {
    btn.color = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("btn-delete-slot")?.addEventListener("click", () => {
    config.pages[activePageIndex].slots[index] = { index, type: "empty" };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
    showToast("Casilla vaciada");
  });
}

// Slider Inspector
function renderSliderInspector(slider, index) {
  const isMaster = slider.slider_type === "master" || slider.type === "master";
  const col = index % 6;
  const currentSlots = config.pages[activePageIndex].slots;

  inspectorContent.innerHTML = `
    <div class="form-group">
      <label>Tipo de Fader</label>
      <select id="edit-slider-type">
        <option value="master" ${isMaster ? 'selected' : ''}>Volumen Maestro (Todo el PC)</option>
        <option value="app_dynamic" ${!isMaster ? 'selected' : ''}>Volumen de Aplicación Específica</option>
      </select>
    </div>

    <div class="form-group">
      <label>Nombre del Fader</label>
      <input type="text" id="edit-slider-label" value="${slider.label || ''}">
    </div>

    <div class="form-group" id="group-target-app" style="${isMaster ? 'display: none;' : ''}">
      <label>Aplicación Asignada</label>
      <select id="edit-slider-app">
        <option value="Spotify.exe">Spotify</option>
        <option value="Discord.exe">Discord</option>
        <option value="chrome.exe">Google Chrome</option>
        <option value="obs64.exe">OBS Studio</option>
        <option value="VALORANT-Win64-Shipping.exe">Valorant</option>
      </select>
    </div>

    <div class="form-group">
      <label>Color del Fader</label>
      <input type="color" id="edit-slider-color" value="${slider.color || (isMaster ? '#0ea5e9' : '#a855f7')}" style="height: 38px; padding: 2px;">
    </div>

    <button class="btn-danger" id="btn-delete-slider">
      Eliminar Fader de la Columna #${col + 1}
    </button>
  `;

  document.getElementById("edit-slider-type")?.addEventListener("change", (e) => {
    const val = e.target.value;
    slider.slider_type = val;
    if (val === "master") {
      slider.label = "Master";
      slider.sublabel = "PC";
      slider.color = "#0ea5e9";
      slider.target_app = null;
      slider.image = "/static/icons/volume_up.svg";
    } else {
      slider.label = "Spotify";
      slider.sublabel = "App";
      slider.color = "#a855f7";
      slider.target_app = "Spotify.exe";
      slider.image = "/static/icons/spotify.svg";
    }
    renderPhoneScreen();
    renderSliderInspector(slider, index);
    saveConfigToServer();
  });

  document.getElementById("edit-slider-label")?.addEventListener("input", (e) => {
    slider.label = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("edit-slider-app")?.addEventListener("change", (e) => {
    slider.target_app = e.target.value;
    slider.label = e.target.options[e.target.selectedIndex].text;
    saveConfigToServer();
  });

  document.getElementById("edit-slider-color")?.addEventListener("input", (e) => {
    slider.color = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("btn-delete-slider")?.addEventListener("click", () => {
    currentSlots[col] = { index: col, type: "empty" };
    currentSlots[col + 6] = { index: col + 6, type: "empty" };
    renderPhoneScreen();
    selectSlot(col);
    saveConfigToServer();
    showToast(`Fader eliminado de la Columna #${col + 1}`);
  });
}

// Save Configuration to Server
async function saveConfigToServer() {
  if (!config) return;
  try {
    // Keep slots in sync with active page
    if (config.pages && config.pages[activePageIndex]) {
      config.slots = config.pages[activePageIndex].slots;
    }
    await fetch("/api/deck/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
  } catch (e) {
    console.error("Error saving config", e);
  }
}

document.getElementById("btn-save-all")?.addEventListener("click", async () => {
  await saveConfigToServer();
  showToast("¡Configuración guardada y sincronizada en el móvil!");
});

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

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

// Startup
window.addEventListener("DOMContentLoaded", () => {
  loadAuthInfo();
  loadConfig();
  loadAudioSessions();
  checkGitHubUpdates();
  setInterval(loadAudioSessions, 3000);
});
