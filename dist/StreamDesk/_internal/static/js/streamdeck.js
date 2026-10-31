// StreamDesk Mobile Client Pro (6x2 Grid + 2-Height Vertical Faders + PWA)
let ws = null;
let token = localStorage.getItem("streamdesk_token") || null;
let wakeLock = null;
let currentConfig = null;
let currentSessions = [];
let targetAppMap = {}; // sliderId -> process_name
let isDraggingMap = {}; // sliderId -> boolean
let deferredInstallPrompt = null;

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const pinModal = document.getElementById("pin-modal");
const btnClosePinModal = document.getElementById("btn-close-pin-modal");
const appModal = document.getElementById("app-modal");
const appListItems = document.getElementById("app-list-items");
const deckGrid = document.getElementById("deck-grid");
const btnInstallPwa = document.getElementById("btn-install-pwa");
const iosInstallModal = document.getElementById("ios-install-modal");

// Register Service Worker for PWA
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
      .then(reg => console.log('SW registrado:', reg.scope))
      .catch(err => console.error('Error SW:', err));
  });
}

// PWA Install Event Handler
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  if (btnInstallPwa) btnInstallPwa.style.display = 'flex';
});

btnInstallPwa?.addEventListener('click', async () => {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    if (outcome === 'accepted') {
      btnInstallPwa.style.display = 'none';
    }
    deferredInstallPrompt = null;
  } else {
    // Show iOS instructions or manual guide
    if (iosInstallModal) iosInstallModal.style.display = 'flex';
  }
});

document.getElementById('btn-close-ios-modal')?.addEventListener('click', () => {
  if (iosInstallModal) iosInstallModal.style.display = 'none';
});

// Screen Wake Lock
async function initWakeLock() {
  if ("wakeLock" in navigator) {
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      document.addEventListener("visibilitychange", async () => {
        if (wakeLock !== null && document.visibilityState === "visible") {
          wakeLock = await navigator.wakeLock.request("screen");
        }
      });
    } catch (err) {}
  }
}

function haptic(ms = 25) {
  if (navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) {}
  }
}

// WebSocket Connection
function connectWebSocket() {
  if (!token) {
    // Show PIN modal upfront if not paired
    showPinModal(false);
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`;

  statusDot.className = "dot connecting";
  statusText.textContent = "Conectando...";

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusDot.className = "dot connected";
    statusText.textContent = "Conectado";
    pinModal.style.display = "none";
    initWakeLock();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  ws.onclose = (event) => {
    statusDot.className = "dot";
    statusText.textContent = "Desconectado";
    if (event.code === 1008) {
      // Token invalid or revoked: clear and prompt PIN upfront
      localStorage.removeItem("streamdesk_token");
      token = null;
      showPinModal(false);
    } else {
      setTimeout(connectWebSocket, 2000);
    }
  };

  ws.onerror = () => {
    statusDot.className = "dot";
    statusText.textContent = "Error de red";
  };
}

function sendWS(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

// Server Message Handler
function handleServerMessage(data) {
  switch (data.type) {
    case "config_sync":
      currentConfig = data.config;
      renderDeck(currentConfig);
      break;

    case "initial_state":
      currentConfig = data.config;
      currentSessions = data.audio_sessions || [];
      renderDeck(currentConfig);
      updateMasterVolume(data.master_volume, data.master_muted);
      updateAppVolumes();
      break;

    case "master_volume_update":
      updateMasterVolume(data.volume, data.muted);
      break;

    case "master_mute_update":
      updateMasterMute(data.muted);
      break;

    case "app_volume_update":
      updateSpecificAppVolume(data.process, data.volume);
      break;

    case "app_mute_update":
      updateAppMuteState(data.process, data.muted);
      break;

    case "sessions_update":
      currentSessions = data.sessions || [];
      updateAppModalList();
      break;
  }
}

// Render dynamic 6x2 grid (12 slots) with 2-height vertical faders
function renderDeck(config) {
  if (!config) return;
  deckGrid.innerHTML = "";

  const slots = config.slots || [];

  for (let idx = 0; idx < 12; idx++) {
    const slot = slots[idx] || { index: idx, type: "empty" };
    const col = (idx % 6) + 1; // 1 to 6
    const row = Math.floor(idx / 6) + 1; // 1 or 2

    // If occupied by a 2-height vertical fader spanning from row 1, skip rendering an extra cell
    if (slot.type === "occupied_by_slider") {
      continue;
    }

    if (slot.type === "button") {
      const btnEl = createButtonElement(slot);
      btnEl.style.gridColumn = `${col}`;
      btnEl.style.gridRow = `${row}`;
      deckGrid.appendChild(btnEl);
    } else if (slot.type === "slider") {
      const faderEl = createFaderElement(slot);
      faderEl.style.gridColumn = `${col}`;
      faderEl.style.gridRow = "1 / span 2"; // Spans both vertical rows!
      deckGrid.appendChild(faderEl);
    } else {
      // Empty slot
      const emptyEl = document.createElement("div");
      emptyEl.className = "deck-slot-empty";
      emptyEl.style.gridColumn = `${col}`;
      emptyEl.style.gridRow = `${row}`;
      deckGrid.appendChild(emptyEl);
    }
  }
}

function createButtonElement(btn) {
  const keycap = document.createElement("div");
  keycap.className = "deck-btn";
  keycap.id = btn.id || `slot_btn_${btn.index}`;

  const inner = document.createElement("div");
  inner.className = "deck-btn-inner";

  const accent = document.createElement("div");
  accent.className = "deck-btn-accent";
  accent.style.background = btn.color || "var(--accent-blue)";
  inner.appendChild(accent);

  const iconWrap = document.createElement("div");
  iconWrap.className = "deck-btn-icon-wrapper";

  if (btn.image) {
    const img = document.createElement("img");
    img.src = btn.image;
    img.className = "deck-btn-img";
    img.alt = btn.label || "";
    iconWrap.appendChild(img);
  } else if (btn.icon && (btn.icon.startsWith("/") || btn.icon.endsWith(".svg"))) {
    const img = document.createElement("img");
    img.src = btn.icon;
    img.className = "deck-btn-img";
    img.alt = btn.label || "";
    iconWrap.appendChild(img);
  } else if (btn.icon) {
    const emoji = document.createElement("span");
    emoji.className = "deck-btn-emoji";
    emoji.textContent = btn.icon;
    iconWrap.appendChild(emoji);
  } else {
    const img = document.createElement("img");
    img.src = "/static/icons/power.svg";
    img.className = "deck-btn-img";
    iconWrap.appendChild(img);
  }
  inner.appendChild(iconWrap);

  const textWrap = document.createElement("div");
  textWrap.className = "deck-btn-text-wrapper";

  const title = document.createElement("div");
  title.className = "deck-btn-title";
  title.textContent = btn.label || "Botón";
  textWrap.appendChild(title);

  if (btn.sublabel) {
    const sub = document.createElement("div");
    sub.className = "deck-btn-sub";
    sub.textContent = btn.sublabel;
    textWrap.appendChild(sub);
  }
  inner.appendChild(textWrap);

  keycap.appendChild(inner);

  // Touch and trigger handlers (snappy micro-animation)
  keycap.addEventListener("pointerdown", () => {
    haptic(25);
    keycap.classList.add("triggered");
    sendWS({ type: "trigger_button", id: btn.id });
  });

  const resetBtn = () => keycap.classList.remove("triggered");
  keycap.addEventListener("pointerup", resetBtn);
  keycap.addEventListener("pointercancel", resetBtn);
  keycap.addEventListener("pointerleave", resetBtn);

  return keycap;
}

function createFaderElement(slider) {
  const isMaster = slider.slider_type === "master" || slider.type === "master";
  const card = document.createElement("div");
  card.className = `deck-fader-card ${isMaster ? 'master-fader' : 'app-fader'}`;
  card.id = `fader-card-${slider.id}`;

  let targetProcess = slider.target_app || (currentSessions[0] ? currentSessions[0].process_name : "Spotify.exe");
  targetAppMap[slider.id] = targetProcess;
  isDraggingMap[slider.id] = false;

  const headerIcon = slider.image 
    ? `<img src="${slider.image}" class="fader-header-icon" alt="">` 
    : `<img src="/static/icons/${isMaster ? 'volume_up' : 'spotify'}.svg" class="fader-header-icon" alt="">`;

  card.innerHTML = `
    <div class="fader-header">
      <div class="fader-header-title">
        ${headerIcon}
        <span>${slider.label || (isMaster ? "Master" : "App")}</span>
      </div>
      ${!isMaster ? `<button class="app-select-btn" id="select-app-${slider.id}">${cleanAppName(targetProcess)}</button>` : ''}
    </div>
    <div class="fader-track-container" id="track-${slider.id}">
      <div class="fader-fill" id="fill-${slider.id}" style="height: 50%;">
        <div class="fader-thumb"></div>
      </div>
    </div>
    <div class="fader-footer">
      <div class="fader-val" id="val-${slider.id}">50%</div>
      <button class="mute-btn" id="mute-${slider.id}">
        <img src="/static/icons/volume_up.svg" class="mute-svg-icon" alt="Vol">
      </button>
    </div>
  `;

  const track = card.querySelector(`#track-${slider.id}`);
  attachFaderDrag(track, slider.id, isMaster);

  const muteBtn = card.querySelector(`#mute-${slider.id}`);
  muteBtn.addEventListener("pointerdown", () => {
    haptic(20);
    if (isMaster) {
      sendWS({ type: "toggle_master_mute" });
    } else {
      const proc = targetAppMap[slider.id];
      sendWS({ type: "toggle_app_mute", process: proc });
    }
  });

  if (!isMaster) {
    const appBtn = card.querySelector(`#select-app-${slider.id}`);
    appBtn?.addEventListener("pointerdown", () => {
      openAppModal(slider.id);
    });
  }

  return card;
}

function cleanAppName(name) {
  if (!name) return "App";
  return name.replace(".exe", "").capitalizeFirst();
}

String.prototype.capitalizeFirst = function() {
  return this.charAt(0).toUpperCase() + this.slice(1);
}

function setMuteBtnVisual(muteBtn, isMuted) {
  if (!muteBtn) return;
  const iconSrc = isMuted ? '/static/icons/mute.svg' : '/static/icons/volume_up.svg';
  muteBtn.innerHTML = `<img src="${iconSrc}" class="mute-svg-icon" alt="Mute">`;
  muteBtn.classList.toggle("active", Boolean(isMuted));
}

// Robust Fader Drag (Never jumps to 0 on fast swipes!)
function attachFaderDrag(trackEl, sliderId, isMaster) {
  let lastSent = 0;

  function handleCoord(clientY) {
    const rect = trackEl.getBoundingClientRect();
    if (rect.height <= 0) return;

    let percent = Math.round(((rect.bottom - clientY) / rect.height) * 100);
    percent = Math.max(0, Math.min(100, percent));

    const fillEl = document.getElementById(`fill-${sliderId}`);
    const valEl = document.getElementById(`val-${sliderId}`);
    if (fillEl) fillEl.style.height = `${percent}%`;
    if (valEl) valEl.textContent = `${percent}%`;

    const now = Date.now();
    if (now - lastSent > 30) {
      lastSent = now;
      if (isMaster) {
        sendWS({ type: "set_master_volume", volume: percent });
      } else {
        const proc = targetAppMap[sliderId];
        sendWS({ type: "set_app_volume", process: proc, volume: percent });
      }
    }
  }

  trackEl.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    isDraggingMap[sliderId] = true;
    try { trackEl.setPointerCapture(e.pointerId); } catch (err) {}
    haptic(15);
    handleCoord(e.clientY);
  });

  trackEl.addEventListener("pointermove", (e) => {
    if (isDraggingMap[sliderId]) {
      e.preventDefault();
      handleCoord(e.clientY);
    }
  });

  const stopDrag = (e) => {
    if (isDraggingMap[sliderId]) {
      handleCoord(e.clientY);
      setTimeout(() => {
        isDraggingMap[sliderId] = false;
      }, 120);
    }
  };

  trackEl.addEventListener("pointerup", stopDrag);
  trackEl.addEventListener("pointercancel", stopDrag);
  trackEl.addEventListener("lostpointercapture", stopDrag);
}

// Volume UI Updates from Server
function updateMasterVolume(vol, muted) {
  if (vol === undefined) return;
  if (isDraggingMap["slider_master"]) return;

  const fill = document.getElementById("fill-slider_master");
  const val = document.getElementById("val-slider_master");
  const muteBtn = document.getElementById("mute-slider_master");

  if (fill) fill.style.height = `${vol}%`;
  if (val) val.textContent = `${vol}%`;
  if (muteBtn) {
    setMuteBtnVisual(muteBtn, muted);
  }
}

function updateMasterMute(muted) {
  const muteBtn = document.getElementById("mute-slider_master");
  if (muteBtn) {
    setMuteBtnVisual(muteBtn, muted);
  }
}

function updateAppVolumes() {
  Object.keys(targetAppMap).forEach((sliderId) => {
    if (isDraggingMap[sliderId]) return;

    const proc = targetAppMap[sliderId];
    const session = currentSessions.find(s => s.process_name?.toLowerCase() === proc?.toLowerCase());
    if (session) {
      const fill = document.getElementById(`fill-${sliderId}`);
      const val = document.getElementById(`val-${sliderId}`);
      const muteBtn = document.getElementById(`mute-${sliderId}`);
      if (fill) fill.style.height = `${session.volume}%`;
      if (val) val.textContent = `${session.volume}%`;
      if (muteBtn) {
        setMuteBtnVisual(muteBtn, session.muted);
      }
    }
  });
}

function updateSpecificAppVolume(processName, vol) {
  Object.keys(targetAppMap).forEach((sliderId) => {
    if (isDraggingMap[sliderId]) return;

    if (targetAppMap[sliderId]?.toLowerCase() === processName?.toLowerCase()) {
      const fill = document.getElementById(`fill-${sliderId}`);
      const val = document.getElementById(`val-${sliderId}`);
      if (fill) fill.style.height = `${vol}%`;
      if (val) val.textContent = `${vol}%`;
    }
  });
}

function updateAppMuteState(processName, muted) {
  Object.keys(targetAppMap).forEach((sliderId) => {
    if (targetAppMap[sliderId]?.toLowerCase() === processName?.toLowerCase()) {
      const muteBtn = document.getElementById(`mute-${sliderId}`);
      if (muteBtn) {
        setMuteBtnVisual(muteBtn, muted);
      }
    }
  });
}

// App Selection Modal
let activeSelectingSliderId = null;

function openAppModal(sliderId) {
  activeSelectingSliderId = sliderId;
  updateAppModalList();
  appModal.classList.add("open");
}

document.getElementById("close-app-modal")?.addEventListener("click", () => {
  appModal.classList.remove("open");
});

function updateAppModalList() {
  if (!appListItems) return;
  appListItems.innerHTML = "";

  if (currentSessions.length === 0) {
    appListItems.innerHTML = `<div class="empty-sessions">No hay aplicaciones reproduciendo audio en el PC</div>`;
    return;
  }

  currentSessions.forEach((s) => {
    const item = document.createElement("div");
    item.className = "app-item";
    item.innerHTML = `
      <div class="app-item-info">
        <span class="app-item-name">${s.display_name}</span>
        <span class="app-item-proc">${s.process_name}</span>
      </div>
      <span class="app-item-vol">${s.volume}%</span>
    `;

    item.addEventListener("click", () => {
      if (activeSelectingSliderId) {
        targetAppMap[activeSelectingSliderId] = s.process_name;
        const btn = document.getElementById(`select-app-${activeSelectingSliderId}`);
        if (btn) btn.textContent = cleanAppName(s.process_name);

        const fill = document.getElementById(`fill-${activeSelectingSliderId}`);
        const val = document.getElementById(`val-${activeSelectingSliderId}`);
        if (fill) fill.style.height = `${s.volume}%`;
        if (val) val.textContent = `${s.volume}%`;

        const muteBtn = document.getElementById(`mute-${activeSelectingSliderId}`);
        setMuteBtnVisual(muteBtn, s.muted);

        appModal.classList.remove("open");
        haptic(20);
      }
    });

    appListItems.appendChild(item);
  });
}

// PIN Modal
function showPinModal(canClose = true) {
  pinModal.style.display = "flex";
  if (btnClosePinModal) {
    btnClosePinModal.style.display = canClose ? "block" : "none";
  }
  document.getElementById("pin-input")?.focus();
}

document.getElementById("btn-status-badge")?.addEventListener("click", () => {
  showPinModal(true);
});

document.getElementById("btn-open-settings")?.addEventListener("click", () => {
  showPinModal(true);
});

document.getElementById("btn-fullscreen")?.addEventListener("click", () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
});

btnClosePinModal?.addEventListener("click", () => {
  pinModal.style.display = "none";
});

document.getElementById("btn-verify-pin")?.addEventListener("click", async () => {
  const pinInput = document.getElementById("pin-input");
  const pinError = document.getElementById("pin-error");
  const enteredPin = pinInput.value.trim();

  if (enteredPin.length < 6) {
    pinError.textContent = "El PIN debe tener 6 dígitos";
    pinError.style.display = "block";
    return;
  }

  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: enteredPin })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      token = data.token;
      localStorage.setItem("streamdesk_token", token);
      pinModal.style.display = "none";
      pinError.style.display = "none";
      connectWebSocket();
    } else {
      pinError.textContent = data.detail || "PIN incorrecto";
      pinError.style.display = "block";
    }
  } catch (err) {
    pinError.textContent = "Error de conexión con el PC";
    pinError.style.display = "block";
  }
});

// Auto-connect on startup
window.addEventListener("DOMContentLoaded", () => {
  connectWebSocket();
});
