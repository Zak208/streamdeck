// StreamDesk Studio Pro — 2x12 Grid & GitHub Updater
let config = null;
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

// 1-Click App & Control Presets (Zero technical knowledge required!)
const ONE_CLICK_PRESETS = [
  { id: "discord", name: "Discord", icon: "", image: "/static/icons/discord.svg", color: "#5865f2", type: "preset_app", target: "discord", sub: "Voz / Chat" },
  { id: "spotify", name: "Spotify", icon: "", image: "/static/icons/spotify.svg", color: "#1db954", type: "preset_app", target: "spotify", sub: "Música" },
  { id: "obs", name: "OBS Studio", icon: "", image: "/static/icons/obs.svg", color: "#302e31", type: "preset_app", target: "obs", sub: "Directo" },
  { id: "steam", name: "Steam", icon: "", image: "/static/icons/steam.svg", color: "#171a21", type: "preset_app", target: "steam", sub: "Juegos" },
  { id: "chrome", name: "Chrome", icon: "", image: "/static/icons/chrome.svg", color: "#ea4335", type: "preset_app", target: "chrome", sub: "Navegador" },
  { id: "valorant", name: "Valorant", icon: "⚔️", image: "", color: "#d13639", type: "preset_app", target: "valorant", sub: "Riot Games" },
  { id: "calc", name: "Calculadora", icon: "🧮", image: "", color: "#f59e0b", type: "launch", target: "calc", sub: "Utilidad" },
  { id: "notepad", name: "Notas", icon: "📝", image: "", color: "#06b6d4", type: "launch", target: "notepad", sub: "Editor" },
  { id: "play_pause", name: "Play / Pausa", icon: "⏯️", image: "", color: "#22c55e", type: "media", target: "play_pause", sub: "Multimedia" },
  { id: "next", name: "Siguiente", icon: "⏭️", image: "", color: "#38bdf8", type: "media", target: "next", sub: "Pista" },
  { id: "prev", name: "Anterior", icon: "⏮️", image: "", color: "#38bdf8", type: "media", target: "prev", sub: "Pista" },
  { id: "mute", name: "Mute Master", icon: "🔇", image: "", color: "#ef4444", type: "media", target: "mute", sub: "Silenciar" },
  { id: "beep", name: "Beep Alerta", icon: "🔔", image: "", color: "#8b5cf6", type: "sound", target: "beep", sub: "Sonido PC" }
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
      updateStatusText.textContent = `StreamDesk v${data.current_version || '2.1.0'} (Al día)`;
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

// Load Configuration (2x12 Grid)
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    config = await res.json();
    renderPhoneScreen();
  } catch (e) {
    console.error("Error loading config", e);
  }
}

// Render the 2x12 Phone Screen Simulator
function renderPhoneScreen() {
  if (!config) return;
  phoneScreen.innerHTML = "";

  const slots = config.slots || [];

  for (let i = 0; i < 24; i++) {
    const slot = slots[i] || { index: i, type: "empty" };
    const cell = document.createElement("div");
    cell.className = `slot-cell ${selectedSlotIndex === i ? 'selected' : ''}`;
    cell.id = `cell_slot_${i}`;
    cell.dataset.index = i;

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

    // Direct Click to Select (NO 3 dots!)
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
  } else {
    iconHtml = `<span class="slot-keycap-emoji">${btn.icon || '⚡'}</span>`;
  }

  wrap.innerHTML = `
    <div class="slot-keycap-inner">
      <div class="slot-accent" style="background: ${btn.color || 'var(--accent-blue)'}"></div>
      ${iconHtml}
      <div class="slot-keycap-title">${btn.label || 'Botón'}</div>
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

  wrap.innerHTML = `
    <div style="font-size: 0.65rem; font-weight: 700; color: var(--text-muted); margin-bottom: 4px; text-align: center;">${slider.label || 'Volumen'}</div>
    <div style="flex: 1; width: 28px; background: #06080d; border-radius: 14px; border: 1px solid var(--border); display: flex; align-items: flex-end; overflow: hidden;">
      <div style="width: 100%; height: 50%; background: ${isMaster ? 'var(--accent-blue)' : 'var(--accent-purple)'}; border-radius: 0 0 14px 14px;"></div>
    </div>
    <div style="font-size: 0.7rem; font-weight: 800; margin-top: 4px;">50%</div>
  `;

  return wrap;
}

// Drag & Drop Handling on Slots
function handleDropOnSlot(targetIndex) {
  if (dragSourceType === "palette_btn") {
    // Add new button in target slot
    config.slots[targetIndex] = {
      index: targetIndex,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Nuevo Botón",
      sublabel: "",
      icon: "⚡",
      image: "",
      color: "#38bdf8",
      action_type: "preset_app",
      target: "discord"
    };
    renderPhoneScreen();
    selectSlot(targetIndex);
    saveConfigToServer();
    showToast("Botón colocado en la cuadrícula");

  } else if (dragSourceType === "palette_slider") {
    // Add new volume slider in target slot
    config.slots[targetIndex] = {
      index: targetIndex,
      type: "slider",
      id: `slider_${Date.now()}`,
      label: "Volumen",
      slider_type: "master",
      color: "#38bdf8"
    };
    renderPhoneScreen();
    selectSlot(targetIndex);
    saveConfigToServer();
    showToast("Fader de volumen colocado");

  } else if (dragSourceType === "slot" && draggedSlotIndex !== null) {
    if (draggedSlotIndex !== targetIndex) {
      // Swap or move slots
      const temp = config.slots[draggedSlotIndex];
      config.slots[draggedSlotIndex] = config.slots[targetIndex] || { index: draggedSlotIndex, type: "empty" };
      config.slots[targetIndex] = temp;

      // Update their index property
      if (config.slots[draggedSlotIndex]) config.slots[draggedSlotIndex].index = draggedSlotIndex;
      if (config.slots[targetIndex]) config.slots[targetIndex].index = targetIndex;

      renderPhoneScreen();
      selectSlot(targetIndex);
      saveConfigToServer();
      showToast("Posiciones actualizadas");
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

  const slot = config.slots[index];
  if (!slot || slot.type === "empty") {
    inspectorTitle.textContent = `Casilla #${index + 1} (Vacía)`;
    renderEmptySlotInspector(index);
  } else if (slot.type === "button") {
    inspectorTitle.textContent = `Configurar Botón (Casilla #${index + 1})`;
    renderButtonInspector(slot, index);
  } else if (slot.type === "slider") {
    inspectorTitle.textContent = `Configurar Fader (Casilla #${index + 1})`;
    renderSliderInspector(slot, index);
  }
}

// Empty Slot Inspector
function renderEmptySlotInspector(index) {
  inspectorContent.innerHTML = `
    <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 14px;">
      Esta casilla está vacía. Puedes arrastrar un elemento desde la izquierda o crearlo directamente con un clic:
    </p>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <button class="btn-primary" id="btn-create-button-here" style="justify-content: center;">
        🔲 Crear Botón Aquí
      </button>
      <button class="btn-primary" id="btn-create-slider-here" style="justify-content: center; background: linear-gradient(135deg, var(--accent-purple), #7e22ce);">
        🎚️ Crear Fader de Volumen Aquí
      </button>
    </div>
  `;

  document.getElementById("btn-create-button-here")?.addEventListener("click", () => {
    config.slots[index] = {
      index,
      type: "button",
      id: `btn_${Date.now()}`,
      label: "Nuevo Botón",
      sublabel: "",
      icon: "⚡",
      image: "",
      color: "#38bdf8",
      action_type: "preset_app",
      target: "discord"
    };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
  });

  document.getElementById("btn-create-slider-here")?.addEventListener("click", () => {
    config.slots[index] = {
      index,
      type: "slider",
      id: `slider_${Date.now()}`,
      label: "Volumen",
      slider_type: "master",
      color: "#38bdf8"
    };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
  });
}

// Ultra Simple Button Inspector (1-Click Presets, NO directory search!)
function renderButtonInspector(btn, index) {
  let presetButtonsHtml = ONE_CLICK_PRESETS.map(p => `
    <button class="quick-app-btn" data-preset-id="${p.id}">
      ${p.image ? `<img src="${p.image}" alt="${p.name}">` : `<span class="emoji">${p.icon}</span>`}
      <div>
        <div class="quick-app-label">${p.name}</div>
        <div style="font-size: 0.65rem; color: var(--text-muted);">${p.sub}</div>
      </div>
    </button>
  `).join("");

  inspectorContent.innerHTML = `
    <div class="form-group">
      <label>Asignar Acción Rápida (1 Clic)</label>
      <div class="quick-apps-grid">
        ${presetButtonsHtml}
      </div>
    </div>

    <div style="border-top: 1px solid var(--border); margin: 12px 0;"></div>

    <div class="form-group">
      <label>Título del Botón</label>
      <input type="text" id="edit-btn-label" value="${btn.label || ''}">
    </div>

    <div class="form-group">
      <label>Color de Acento</label>
      <input type="color" id="edit-btn-color" value="${btn.color || '#38bdf8'}" style="height: 38px; padding: 2px;">
    </div>

    <button class="btn-danger" id="btn-delete-slot">
      🗑️ Vaciar esta Casilla
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
        btn.icon = preset.icon;
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

  document.getElementById("edit-btn-label").addEventListener("input", (e) => {
    btn.label = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("edit-btn-color").addEventListener("input", (e) => {
    btn.color = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("btn-delete-slot").addEventListener("click", () => {
    config.slots[index] = { index, type: "empty" };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
    showToast("Casilla vaciada");
  });
}

// Slider Inspector
function renderSliderInspector(slider, index) {
  const isMaster = slider.slider_type === "master" || slider.type === "master";

  inspectorContent.innerHTML = `
    <div class="form-group">
      <label>Nombre del Fader</label>
      <input type="text" id="edit-slider-label" value="${slider.label || ''}">
    </div>

    <div class="form-group">
      <label>Tipo de Control</label>
      <select id="edit-slider-type">
        <option value="master" ${isMaster ? 'selected' : ''}>Volumen Global / Master de Windows</option>
        <option value="app_dynamic" ${!isMaster ? 'selected' : ''}>Selector Dinámico de Aplicación</option>
      </select>
    </div>

    <div class="form-group">
      <label>Color</label>
      <input type="color" id="edit-slider-color" value="${slider.color || (isMaster ? '#38bdf8' : '#a855f7')}" style="height: 38px; padding: 2px;">
    </div>

    <button class="btn-danger" id="btn-delete-slider">
      🗑️ Eliminar Fader de Volumen
    </button>
  `;

  document.getElementById("edit-slider-label").addEventListener("input", (e) => {
    slider.label = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("edit-slider-type").addEventListener("change", (e) => {
    slider.slider_type = e.target.value;
    slider.type = e.target.value;
    renderPhoneScreen();
    saveConfigToServer();
  });

  document.getElementById("edit-slider-color").addEventListener("input", (e) => {
    slider.color = e.target.value;
    renderPhoneScreen();
  });

  document.getElementById("btn-delete-slider").addEventListener("click", () => {
    config.slots[index] = { index, type: "empty" };
    renderPhoneScreen();
    selectSlot(index);
    saveConfigToServer();
    showToast("Fader eliminado");
  });
}

// Save config to PC server & broadcast to phone
async function saveConfigToServer() {
  try {
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
  } catch (err) {}
}

document.getElementById("btn-save-all")?.addEventListener("click", async () => {
  await saveConfigToServer();
  showToast("¡Configuración guardada y sincronizada al móvil!");
});

function showToast(msg) {
  toast.textContent = msg;
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.display = "none";
  }, 2500);
}

// Refresh PIN Button
document.getElementById("btn-refresh-pin")?.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/auth/regenerate-pin", { method: "POST" });
    const data = await res.json();
    document.getElementById("pin-code").textContent = data.pin;
    document.getElementById("qr-image").src = data.qr_code;
    showToast("Nuevo PIN generado");
  } catch (e) {
    await loadAuthInfo();
  }
});

// Init
(async () => {
  await loadAuthInfo();
  await loadConfig();
  await loadAudioSessions();
  await checkGitHubUpdates();
  setInterval(loadAudioSessions, 3000);
  setInterval(checkGitHubUpdates, 30000); // Check GitHub update every 30s
})();
