// StreamDesk Mobile Client Pro (6x2 Grid + Multi-Page Swipe + Telemetry Widgets)
let ws = null;
let token = localStorage.getItem("streamdesk_token") || null;
let wakeLock = null;
let currentConfig = null;
let currentSessions = [];
let targetAppMap = {}; // sliderId -> process_name
let isDraggingMap = {}; // sliderId -> boolean
let masterSliderIds = new Set(); // every master fader on the current page (ids differ per page)
let buttonStates = {}; // button id -> last known on/off state (OBS recording / streaming)
let deferredInstallPrompt = null;

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const pinModal = document.getElementById("pin-modal");
const btnClosePinModal = document.getElementById("btn-close-pin-modal");
const appModal = document.getElementById("app-modal");
const appListItems = document.getElementById("app-list-items");
const deckGrid = document.getElementById("deck-grid");
const deckContainer = document.getElementById("deck-container");
const btnInstallPwa = document.getElementById("btn-install-pwa");
const iosInstallModal = document.getElementById("ios-install-modal");
const currentPageName = document.getElementById("current-page-name");
const pageDots = document.getElementById("page-dots");
const btnPrevPage = document.getElementById("btn-prev-page");
const btnNextPage = document.getElementById("btn-next-page");

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

function showMobileToast(msg, isError = false) {
  const t = document.getElementById("mobile-toast");
  if (!t) return;
  t.textContent = msg;
  t.className = isError ? "mobile-toast error show" : "mobile-toast show";
  setTimeout(() => {
    t.classList.remove("show");
  }, 2600);
}

function haptic(ms = 25) {
  if (navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) {}
  }
}

// Multi-Page Navigation Handlers
function renderPageNav(config) {
  if (!config) return;
  const pages = config.pages || [];
  const curIdx = config.current_page || 0;

  if (currentPageName && pages[curIdx]) {
    currentPageName.textContent = pages[curIdx].name || `Pág ${curIdx + 1}`;
  }

  if (pageDots) {
    pageDots.innerHTML = "";
    pages.forEach((p, i) => {
      const dot = document.createElement("div");
      dot.className = `page-dot ${i === curIdx ? 'active' : ''}`;
      dot.addEventListener("click", () => switchPage(i));
      pageDots.appendChild(dot);
    });
  }
}

function switchPage(pageIdx) {
  if (!currentConfig) return;
  const pages = currentConfig.pages || [];
  if (pageIdx >= 0 && pageIdx < pages.length) {
    haptic(20);
    sendWS({ type: "switch_page", page: pageIdx });
  }
}

function goToPrevPage() {
  if (!currentConfig) return;
  const curIdx = currentConfig.current_page || 0;
  const total = (currentConfig.pages || []).length;
  if (total > 1) {
    const nextIdx = (curIdx - 1 + total) % total;
    switchPage(nextIdx);
  }
}

function goToNextPage() {
  if (!currentConfig) return;
  const curIdx = currentConfig.current_page || 0;
  const total = (currentConfig.pages || []).length;
  if (total > 1) {
    const nextIdx = (curIdx + 1) % total;
    switchPage(nextIdx);
  }
}

btnPrevPage?.addEventListener("click", goToPrevPage);
btnNextPage?.addEventListener("click", goToNextPage);

// Touch Swipe Gesture Detection on Mobile
let touchStartX = 0;
let touchStartY = 0;

deckContainer?.addEventListener("touchstart", (e) => {
  if (e.touches.length === 1) {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
  }
}, { passive: true });

deckContainer?.addEventListener("touchend", (e) => {
  if (Object.values(isDraggingMap).some(Boolean)) {
    return;
  }
  if (e.changedTouches.length === 1) {
    const diffX = e.changedTouches[0].clientX - touchStartX;
    const diffY = e.changedTouches[0].clientY - touchStartY;
    // Horizontal swipe threshold: 50px and mostly horizontal
    if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY) * 1.4) {
      if (diffX < 0) {
        goToNextPage();
      } else {
        goToPrevPage();
      }
    }
  }
}, { passive: true });

// WebSocket Connection
function connectWebSocket() {
  const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

  if (!token && !isLocalhost) {
    const urlParams = new URLSearchParams(window.location.search);
    const pinParam = urlParams.get("pin");
    if (pinParam) {
      autoPairWithPin(pinParam);
      return;
    }
    showPinModal(false);
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsTokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
  const wsUrl = `${protocol}//${window.location.host}/ws${wsTokenParam}`;

  statusDot.className = "dot connecting";
  statusText.textContent = "Conectando...";

  try {
    if (ws) {
      try { ws.close(); } catch (e) {}
    }
    ws = new WebSocket(wsUrl);
  } catch (err) {
    console.error("WS error:", err);
    statusDot.className = "dot";
    statusText.textContent = "Error de red";
    setTimeout(connectWebSocket, 2000);
    return;
  }

  ws.onopen = () => {
    statusDot.className = "dot connected";
    statusText.textContent = "Conectado";
    const banner = document.getElementById("reconnect-banner");
    if (banner) banner.style.display = "none";
    if (pinModal) pinModal.style.display = "none";
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
    const banner = document.getElementById("reconnect-banner");
    if (banner) banner.style.display = "flex";
    if (event.code === 1008) {
      console.warn("WS 1008: No autorizado");
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
    case "config_updated":
      currentConfig = data.config;
      renderDeck(currentConfig);
      renderPageNav(currentConfig);
      break;

    case "initial_state":
    case "init_state":
      currentConfig = data.config;
      currentSessions = data.audio_sessions || data.sessions || [];
      buttonStates = data.button_states || {};
      renderDeck(currentConfig);
      renderPageNav(currentConfig);
      if (data.master) updateMasterVolume(data.master.volume, data.master.muted);
      updateAppVolumes();
      applyMicState(data.mic);
      break;

    case "audio_state":
      // Pushed by the PC whenever master or any app volume/mute changes there.
      currentSessions = data.sessions || [];
      if (data.master) updateMasterVolume(data.master.volume, data.master.muted);
      updateAppVolumes();
      applyMicState(data.mic);
      break;

    case "button_state":
      buttonStates[data.id] = Boolean(data.active);
      applyButtonState(data.id);
      break;

    case "telemetry_update":
      updateTelemetryWidgets(data);
      break;

    case "master_volume_updated":
    case "master_volume_update":
      updateMasterVolume(data.volume, data.muted);
      break;

    case "master_mute_updated":
    case "master_mute_update":
      updateMasterMute(data.muted);
      break;

    case "app_volume_updated":
    case "app_volume_update":
      updateSpecificAppVolume(data.process, data.volume);
      break;

    case "app_mute_updated":
    case "app_mute_update":
      updateAppMuteState(data.process, data.muted);
      break;

    case "action_result":
      if (data.status === "error" || data.success === false) {
        haptic([40, 60, 40]);
        showMobileToast(data.message || data.error || "Error al ejecutar acción", true);
        if (data.slot_id) {
          const btnEl = document.getElementById(data.slot_id);
          if (btnEl) {
            btnEl.classList.remove("btn-shake-error");
            void btnEl.offsetWidth;
            btnEl.classList.add("btn-shake-error");
            setTimeout(() => btnEl.classList.remove("btn-shake-error"), 400);
          }
        }
      }
      break;

    case "sessions_update":
      currentSessions = data.sessions || [];
      updateAppModalList();
      break;
  }
}

// Live Hardware Telemetry Updates
function updateTelemetryWidgets(data) {
  if (!currentConfig) return;
  const slots = currentConfig.slots || [];

  slots.forEach((s) => {
    if (s.action_type === "hardware_monitor" || s.target === "cpu" || s.target === "ram" || s.target === "disk") {
      const btnEl = document.getElementById(s.id || `slot_btn_${s.index}`);
      if (!btnEl) return;

      const subEl = btnEl.querySelector(".deck-btn-sub");
      if (subEl) {
        if (s.target === "cpu") subEl.textContent = `${data.cpu}% Uso`;
        else if (s.target === "ram") subEl.textContent = `${data.ram}% RAM`;
        else if (s.target === "disk") subEl.textContent = `${data.disk}% Usado`;
      }
    }
  });
}

// Render dynamic 6x2 grid (12 slots) with 2-height vertical faders
function renderDeck(config) {
  if (!config) return;
  deckGrid.innerHTML = "";
  masterSliderIds = new Set();

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

// The Windows microphone can be muted outside StreamDesk, so its buttons follow the real state.
function applyMicState(mic) {
  if (!mic || mic.muted === null || mic.muted === undefined || !currentConfig) return;
  (currentConfig.slots || []).forEach((slot) => {
    if (slot.type === "button" && slot.action_type === "windows" && slot.target === "mic_mute") {
      buttonStates[slot.id] = Boolean(mic.muted);
      applyButtonState(slot.id);
    }
  });
}

function applyButtonState(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle("is-active", Boolean(buttonStates[id]));
}

function createButtonElement(btn) {
  const keycap = document.createElement("div");
  keycap.className = "deck-btn";
  keycap.id = btn.id || `slot_btn_${btn.index}`;
  if (buttonStates[keycap.id]) keycap.classList.add("is-active");

  const inner = document.createElement("div");
  inner.className = "deck-btn-inner";

  const btnColor = btn.color || "var(--accent-blue)";
  const accent = document.createElement("div");
  accent.className = "deck-btn-accent";
  accent.style.background = btnColor;
  accent.style.boxShadow = `0 0 8px ${btnColor}`;
  inner.appendChild(accent);

  const iconWrap = document.createElement("div");
  iconWrap.className = "deck-btn-icon-wrapper";

  const iconSrc = btn.image || btn.icon || "/static/icons/power.svg";
  const img = document.createElement("img");
  img.src = iconSrc;
  img.className = "deck-btn-img";
  img.alt = btn.label || "";
  iconWrap.appendChild(img);
  inner.appendChild(iconWrap);

  const textWrap = document.createElement("div");
  textWrap.className = "deck-btn-text-wrapper";

  const title = document.createElement("div");
  title.className = "deck-btn-title";
  title.textContent = btn.label || "Botón";
  textWrap.appendChild(title);

  const sub = document.createElement("div");
  sub.className = "deck-btn-sub";
  sub.textContent = btn.sublabel || "";
  textWrap.appendChild(sub);

  inner.appendChild(textWrap);
  keycap.appendChild(inner);

  // Tactile touch & trigger micro-animation
  keycap.addEventListener("pointerdown", () => {
    haptic(25);
    keycap.classList.add("triggered");
    keycap.style.borderColor = btnColor;
    keycap.style.boxShadow = `0 0 16px ${btnColor}`;
    sendWS({ type: "trigger_button", id: btn.id });
  });

  const resetBtn = () => {
    keycap.classList.remove("triggered");
    keycap.style.borderColor = "";
    keycap.style.boxShadow = "";
  };
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
  if (isMaster) masterSliderIds.add(slider.id);

  const headerIcon = slider.image 
    ? `<img src="${slider.image}" class="fader-header-icon" alt="">` 
    : `<img src="/static/icons/${isMaster ? 'volume_up' : 'spotify'}.svg" class="fader-header-icon" alt="">`;

  const faderColor = slider.color || (isMaster ? "var(--accent-blue)" : "var(--accent-purple)");

  card.innerHTML = `
    <div class="fader-header">
      <div class="fader-header-title">
        ${headerIcon}
        <span>${slider.label || (isMaster ? "Master" : "App")}</span>
      </div>
      ${!isMaster ? `<button class="app-select-btn" id="select-app-${slider.id}">${cleanAppName(targetProcess)}</button>` : ''}
    </div>
    <div class="fader-track-container" id="track-${slider.id}">
      <div class="fader-fill" id="fill-${slider.id}" style="height: 50%; background: ${faderColor}; box-shadow: 0 0 10px ${faderColor};">
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

  function handleCoord(clientY, forceSend = false) {
    const rect = trackEl.getBoundingClientRect();
    if (rect.height <= 0) return;

    let percent = Math.round(((rect.bottom - clientY) / rect.height) * 100);
    percent = Math.max(0, Math.min(100, percent));

    const fillEl = document.getElementById(`fill-${sliderId}`);
    const valEl = document.getElementById(`val-${sliderId}`);
    if (fillEl) fillEl.style.height = `${percent}%`;
    if (valEl) valEl.textContent = `${percent}%`;

    const now = Date.now();
    if (forceSend || now - lastSent > 25) {
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
      handleCoord(e.clientY, true);
      // Keep ignoring server echoes briefly so the thumb does not snap back to an older value.
      setTimeout(() => {
        isDraggingMap[sliderId] = false;
      }, 400);
    }
  };

  trackEl.addEventListener("pointerup", stopDrag);
  trackEl.addEventListener("pointercancel", stopDrag);
  trackEl.addEventListener("lostpointercapture", stopDrag);
}

// Volume UI Updates from Server
function updateMasterVolume(vol, muted) {
  if (vol === undefined) return;

  masterSliderIds.forEach((sliderId) => {
    if (isDraggingMap[sliderId]) return;

    const fill = document.getElementById(`fill-${sliderId}`);
    const val = document.getElementById(`val-${sliderId}`);
    const muteBtn = document.getElementById(`mute-${sliderId}`);

    if (fill) fill.style.height = `${vol}%`;
    if (val) val.textContent = `${vol}%`;
    if (muteBtn) {
      setMuteBtnVisual(muteBtn, muted);
    }
  });
}

function updateMasterMute(muted) {
  masterSliderIds.forEach((sliderId) => {
    const muteBtn = document.getElementById(`mute-${sliderId}`);
    if (muteBtn) {
      setMuteBtnVisual(muteBtn, muted);
    }
  });
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

// PIN Modal & Authentication Handlers
function showPinModal(canClose = true) {
  if (pinModal) {
    pinModal.style.display = "flex";
  }
  if (btnClosePinModal) {
    btnClosePinModal.style.display = canClose ? "block" : "none";
  }
  setTimeout(() => {
    document.getElementById("pin-input")?.focus();
  }, 100);
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
  if (pinModal) pinModal.style.display = "none";
});

// Automatic 1-touch pairing when opening URL via QR Code (?pin=XXXXXX)
async function autoPairWithPin(pinCode) {
  const pinInput = document.getElementById("pin-input");
  const pinError = document.getElementById("pin-error");
  if (pinInput) pinInput.value = pinCode;

  statusDot.className = "dot connecting";
  statusText.textContent = "Emparejando...";

  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pin: pinCode.trim(),
        device_name: /iPhone|iPad/i.test(navigator.userAgent) ? "iPhone" : (/Android/i.test(navigator.userAgent) ? "Android" : "Móvil")
      })
    });

    const data = await res.json();
    if (res.ok && (data.success || data.valid) && data.token) {
      token = data.token;
      localStorage.setItem("streamdesk_token", token);
      if (pinModal) pinModal.style.display = "none";
      if (pinError) pinError.style.display = "none";
      try {
        window.history.replaceState({}, document.title, window.location.pathname);
      } catch (e) {}
      connectWebSocket();
      return true;
    } else {
      if (pinError) {
        pinError.textContent = data.detail || data.error || "El PIN del enlace ha expirado o no coincide";
        pinError.style.display = "block";
      }
      showPinModal(false);
      return false;
    }
  } catch (err) {
    console.error("Auto pair error:", err);
    showPinModal(false);
    return false;
  }
}

// Manual PIN Verification Form
document.getElementById("btn-verify-pin")?.addEventListener("click", async () => {
  const pinInput = document.getElementById("pin-input");
  const pinError = document.getElementById("pin-error");
  const enteredPin = (pinInput?.value || "").trim();

  if (enteredPin.length < 4) {
    if (pinError) {
      pinError.textContent = "El PIN debe tener al menos 6 dígitos";
      pinError.style.display = "block";
    }
    return;
  }

  const btnVerify = document.getElementById("btn-verify-pin");
  if (btnVerify) {
    btnVerify.disabled = true;
    btnVerify.textContent = "Verificando...";
  }

  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pin: enteredPin,
        device_name: /iPhone|iPad/i.test(navigator.userAgent) ? "iPhone" : (/Android/i.test(navigator.userAgent) ? "Android" : "Móvil")
      })
    });

    const data = await res.json();
    if (res.ok && (data.success || data.valid) && data.token) {
      token = data.token;
      localStorage.setItem("streamdesk_token", token);
      if (pinModal) pinModal.style.display = "none";
      if (pinError) pinError.style.display = "none";
      try {
        window.history.replaceState({}, document.title, window.location.pathname);
      } catch (e) {}
      connectWebSocket();
    } else {
      if (pinError) {
        pinError.textContent = data.detail || data.error || "PIN incorrecto. Revisa el código en tu PC.";
        pinError.style.display = "block";
      }
    }
  } catch (err) {
    if (pinError) {
      pinError.textContent = "Error de conexión con el PC. Verifica que estás en la misma Wi-Fi.";
      pinError.style.display = "block";
    }
  } finally {
    if (btnVerify) {
      btnVerify.disabled = false;
      btnVerify.textContent = "Conectar con PC";
    }
  }
});

// Enable pressing Enter in PIN input field
document.getElementById("pin-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    document.getElementById("btn-verify-pin")?.click();
  }
});

// Startup Hook: auto-pair if ?pin= is present, else connect
window.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const pinParam = urlParams.get("pin");
  if (pinParam) {
    autoPairWithPin(pinParam);
  } else {
    connectWebSocket();
  }
});
