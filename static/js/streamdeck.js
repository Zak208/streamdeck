// StreamDesk Mobile Client Pro (2x12 Grid + PWA Support)
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
    iosInstallModal.style.display = 'flex';
  }
});

document.getElementById('btn-close-ios-modal')?.addEventListener('click', () => {
  iosInstallModal.style.display = 'none';
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
    ws.close();
  };
}

// Handle Messages from PC
function handleServerMessage(data) {
  switch (data.type) {
    case "init_state":
      currentConfig = data.config;
      currentSessions = data.sessions || [];
      renderDeck(currentConfig);
      updateMasterVolume(data.master?.volume, data.master?.muted);
      break;

    case "config_updated":
      currentConfig = data.config;
      renderDeck(currentConfig);
      break;

    case "audio_state":
      currentSessions = data.sessions || [];
      if (data.master) {
        updateMasterVolume(data.master.volume, data.master.muted);
      }
      updateAppVolumes();
      break;

    case "master_volume_updated":
      updateMasterVolume(data.volume, data.muted);
      break;

    case "master_mute_updated":
      updateMasterMute(data.muted);
      break;

    case "app_volume_updated":
      updateSpecificAppVolume(data.process, data.volume);
      break;

    case "sessions_update":
      currentSessions = data.sessions || [];
      updateAppModalList();
      break;
  }
}

// Render dynamic 2x12 grid (24 slots)
function renderDeck(config) {
  if (!config) return;
  deckGrid.innerHTML = "";

  const slots = config.slots || [];

  slots.forEach((slot, idx) => {
    if (slot.type === "button") {
      const btnEl = createButtonElement(slot);
      deckGrid.appendChild(btnEl);
    } else if (slot.type === "slider") {
      const faderEl = createFaderElement(slot);
      deckGrid.appendChild(faderEl);
    } else {
      // Empty slot
      const emptyEl = document.createElement("div");
      emptyEl.className = "deck-slot-empty";
      deckGrid.appendChild(emptyEl);
    }
  });
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
  } else {
    const emoji = document.createElement("span");
    emoji.className = "deck-btn-emoji";
    emoji.textContent = btn.icon || "⚡";
    iconWrap.appendChild(emoji);
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

  // Trigger handlers
  keycap.addEventListener("pointerdown", () => {
    haptic(30);
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

  card.innerHTML = `
    <div class="fader-header">
      <span>${slider.label || (isMaster ? "Master" : "App")}</span>
      ${!isMaster ? `<button class="app-select-btn" id="select-app-${slider.id}">${cleanAppName(targetProcess)}</button>` : ''}
    </div>
    <div class="fader-track-container" id="track-${slider.id}">
      <div class="fader-fill" id="fill-${slider.id}" style="height: 50%;">
        <div class="fader-thumb"></div>
      </div>
    </div>
    <div class="fader-footer">
      <div class="fader-val" id="val-${slider.id}">50%</div>
      <button class="mute-btn" id="mute-${slider.id}">🔊</button>
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
      }, 150);
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
    muteBtn.textContent = muted ? "🔇" : "🔊";
    muteBtn.classList.toggle("active", Boolean(muted));
  }
}

function updateMasterMute(muted) {
  const muteBtn = document.getElementById("mute-slider_master");
  if (muteBtn) {
    muteBtn.textContent = muted ? "🔇" : "🔊";
    muteBtn.classList.toggle("active", Boolean(muted));
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
        muteBtn.textContent = session.muted ? "🔇" : "🔊";
        muteBtn.classList.toggle("active", Boolean(session.muted));
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
    appListItems.innerHTML = `<div style="color: #64748b; padding: 12px; text-align: center;">No hay apps con audio activo</div>`;
    return;
  }

  currentSessions.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "app-item-btn";
    btn.innerHTML = `
      <span>${s.display_name}</span>
      <span style="color: var(--accent-purple); font-weight: 700;">${s.volume}%</span>
    `;
    btn.addEventListener("click", () => {
      if (activeSelectingSliderId) {
        targetAppMap[activeSelectingSliderId] = s.process_name;
        const selectorBtn = document.getElementById(`select-app-${activeSelectingSliderId}`);
        if (selectorBtn) selectorBtn.textContent = s.display_name;

        const fill = document.getElementById(`fill-${activeSelectingSliderId}`);
        const val = document.getElementById(`val-${activeSelectingSliderId}`);
        if (fill) fill.style.height = `${s.volume}%`;
        if (val) val.textContent = `${s.volume}%`;
      }
      appModal.classList.remove("open");
    });
    appListItems.appendChild(btn);
  });
}

function sendWS(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// Settings & PIN Modal Logic
function showPinModal(canClose = true) {
  pinModal.style.display = "flex";
  btnClosePinModal.style.display = canClose ? "block" : "none";
  const inputs = document.querySelectorAll(".pin-input");
  inputs[0]?.focus();
}

document.getElementById("btn-open-settings")?.addEventListener("click", () => {
  showPinModal(true);
});

document.getElementById("status-badge")?.addEventListener("click", () => {
  showPinModal(true);
});

btnClosePinModal?.addEventListener("click", () => {
  pinModal.style.display = "none";
});

// Fullscreen Toggle
document.getElementById("btn-fullscreen")?.addEventListener("click", () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
});

const pinInputs = document.querySelectorAll(".pin-input");
pinInputs.forEach((input, index) => {
  input.addEventListener("input", (e) => {
    if (e.target.value.length === 1 && index < pinInputs.length - 1) {
      pinInputs[index + 1].focus();
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !e.target.value && index > 0) {
      pinInputs[index - 1].focus();
    }
  });
});

document.getElementById("btn-pair")?.addEventListener("click", async () => {
  const pin = Array.from(pinInputs).map(i => i.value).join("");
  const errEl = document.getElementById("pin-error");
  errEl.style.display = "none";

  if (pin.length !== 6) {
    errEl.textContent = "Introduce los 6 dígitos del PIN";
    errEl.style.display = "block";
    return;
  }

  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin, device_name: navigator.userAgent.includes("iPhone") ? "iPhone" : "Android" })
    });
    const data = await res.json();
    if (data.valid && data.token) {
      localStorage.setItem("streamdesk_token", data.token);
      token = data.token;
      pinModal.style.display = "none";
      connectWebSocket();
    } else {
      errEl.textContent = data.detail || "PIN incorrecto";
      errEl.style.display = "block";
    }
  } catch (err) {
    errEl.textContent = "Error de conexión con el PC";
    errEl.style.display = "block";
  }
});

// Auto-pair if PIN in URL query (?pin=123456)
async function checkUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const pinParam = params.get("pin");
  if (pinParam && pinParam.length === 6) {
    try {
      const res = await fetch("/api/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pinParam, device_name: "Auto-QR Paired Device" })
      });
      const data = await res.json();
      if (data.valid && data.token) {
        localStorage.setItem("streamdesk_token", data.token);
        token = data.token;
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    } catch (e) {}
  }
}

// Start
(async () => {
  await checkUrlParams();
  connectWebSocket();
})();
