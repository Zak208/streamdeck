// StreamDesk Mobile Client Pro (6x2 Grid + Multi-Page Swipe + Telemetry Widgets)
let ws = null;

// Inside the Android app (a WebView with a bridge called AndroidApp) the pairing is also kept by the app, one per PC.
// The page's localStorage belongs to one address, so a PC that changes network would otherwise ask for the PIN again.
const nativeApp = (typeof window.AndroidApp !== "undefined" && typeof window.AndroidApp.scanQr === "function") ? window.AndroidApp : null;
function nativeCall(name, ...args) {
  try { return nativeApp && typeof nativeApp[name] === "function" ? nativeApp[name](...args) : undefined; } catch (e) { return undefined; }
}
function readStoredToken() {
  let stored = null;
  try { stored = localStorage.getItem("streamdesk_token"); } catch (e) { /* private mode */ }
  if (stored) nativeCall("saveToken", stored); // pairings made before the app existed or by an older version
  else if (nativeApp) stored = nativeCall("getToken") || null;
  return stored || null;
}
function storeToken(value) {
  token = value;
  try { localStorage.setItem("streamdesk_token", value); } catch (e) { /* private mode */ }
  nativeCall("saveToken", value);
}
function forgetToken() {
  token = null;
  try { localStorage.removeItem("streamdesk_token"); } catch (e) { /* private mode */ }
  nativeCall("clearToken");
}
let token = readStoredToken();
let wakeLock = null;
let currentConfig = null;
let currentSessions = [];
let targetAppMap = {}; // sliderId -> process_name
let isDraggingMap = {}; // sliderId -> boolean
let masterSliderIds = new Set(); // every master fader on the current page (ids differ per page)
let lastMaster = null; // last master volume received, to paint faders that are created later
let lastMic = null;
let buttonLabels = {}; // button id -> live text under the key (a counter's value, a timer's countdown)
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
const currentPageName = document.getElementById("current-page-name");
const pageDots = document.getElementById("page-dots");
const btnPrevPage = document.getElementById("btn-prev-page");
const btnNextPage = document.getElementById("btn-next-page");

// Register Service Worker for PWA. The outcome is kept so Settings can show why installing fails.
let swState = null;
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
      .then(reg => { swState = { ok: true, scope: reg.scope }; })
      .catch(err => { swState = { ok: false, message: String(err && err.message || err) }; console.error('Error SW:', err); });
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
    openSettingsSheet("install");
  }
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  if (btnInstallPwa) btnInstallPwa.style.display = 'none';
  showMobileToast("StreamDesk instalado. Ábrelo desde tu pantalla de inicio.");
});

// Screen Wake Lock
let wakeLockListening = false;
async function initWakeLock() {
  if ("wakeLock" in navigator) {
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      if (!wakeLockListening) {
        wakeLockListening = true;
        document.addEventListener("visibilitychange", async () => {
          if (wakeLock !== null && document.visibilityState === "visible") {
            try { wakeLock = await navigator.wakeLock.request("screen"); } catch (err) {}
          }
        });
      }
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
  const pref = localStorage.getItem("streamdesk_haptic") || "medium";
  if (pref === "off") return;
  const duration = pref === "soft" ? 12 : (pref === "strong" ? 45 : (typeof ms === "number" ? ms : 25));
  if (navigator.vibrate) {
    try { navigator.vibrate(duration); } catch (e) {}
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
let reconnectTimer = null;

// One pending reconnect at a time, however many things ask for it. The wait grows (0.3 s to 8 s) while it keeps
// failing, and starts over as soon as the connection works or the phone comes back to the screen.
const RECONNECT_WAITS = [300, 1000, 2000, 4000, 8000];
let reconnectAttempt = 0;
let everOpened = false;
let lostReported = false; // the Android app was told once that the PC does not answer
let lastMessageAt = Date.now();

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  const wait = RECONNECT_WAITS[Math.min(reconnectAttempt, RECONNECT_WAITS.length - 1)];
  reconnectAttempt++;
  reconnectTimer = setTimeout(connectWebSocket, wait);
}

function setOffline(offline) {
  document.body.classList.toggle("offline", offline);
}

// A connection that died without saying so (screen off, Wi-Fi changed) looks open but nothing arrives: the PC
// sends something at least every second, so silence means it is gone.
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN && Date.now() - lastMessageAt > 6000) {
    try { ws.close(); } catch (e) {}
  }
}, 2000);

function reconnectNow() {
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    reconnectAttempt = 0;
    connectWebSocket();
  }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) reconnectNow(); });
window.addEventListener("online", reconnectNow);
window.addEventListener("pageshow", reconnectNow);

function connectWebSocket() {
  clearTimeout(reconnectTimer);
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

  // Replacing a socket must not look like a dropped connection. If the old socket kept its
  // handlers, closing it here would schedule a reconnect that closes the new socket, which
  // schedules another, forever (the phone connected and disconnected every second).
  if (ws) {
    const old = ws;
    old.onopen = old.onmessage = old.onerror = old.onclose = null;
    try { old.close(); } catch (e) {}
  }

  let socket;
  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    console.error("WS error:", err);
    statusDot.className = "dot";
    statusText.textContent = "Error de red";
    scheduleReconnect();
    return;
  }
  ws = socket;
  // A connection to an address that does not answer can stay "connecting" for a long time without ever failing.
  setTimeout(() => { if (socket === ws && socket.readyState === WebSocket.CONNECTING) { try { socket.close(); } catch (e) {} } }, 4000);

  socket.onopen = () => {
    statusDot.className = "dot connected";
    statusText.textContent = "Conectado";
    everOpened = true;
    lostReported = false;
    reconnectAttempt = 0;
    lastMessageAt = Date.now();
    setOffline(false);
    saveRecentIp(window.location.host);
    const banner = document.getElementById("reconnect-banner");
    if (banner) banner.style.display = "none";
    if (pinModal) pinModal.style.display = "none";
    initWakeLock();
  };

  socket.onmessage = (event) => {
    lastMessageAt = Date.now();
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  socket.onclose = (event) => {
    if (socket !== ws) return; // an old socket closing after it was replaced
    statusDot.className = "dot";
    statusText.textContent = "Desconectado";
    setOffline(true);
    const banner = document.getElementById("reconnect-banner");
    if (banner) {
      banner.style.display = "flex";
      // Never connected since the page opened and still failing: say what can be wrong instead of "reconnecting" forever.
      const text = banner.querySelector("[data-banner-text]");
      if (text) {
        text.textContent = !everOpened && reconnectAttempt >= 3
          ? "No se puede conectar con tu PC. Comprueba que StreamDesk está abierto y que estás en la misma Wi-Fi. Si cambió la IP del PC, vincula de nuevo desde Ajustes."
          : "Reconectando con tu PC... Comprueba que estás en la misma red Wi-Fi";
      }
    }
    if (event.code === 1008) {
      console.warn("WS 1008: No autorizado");
      forgetToken();
      showPinModal(false);
    } else {
      scheduleReconnect();
      // In the app, a PC that stays unreachable is usually a PC on another network: the app looks for it again
      // (and offers the QR scanner) instead of leaving this page retrying an address that no longer answers.
      if (nativeApp && reconnectAttempt >= 5 && !lostReported) {
        lostReported = true;
        nativeCall("connectionLost");
      }
    }
  };

  socket.onerror = () => {
    statusDot.className = "dot";
    statusText.textContent = "Error de red";
  };
}

function sendWS(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
    return;
  }
  // A button tapped while the connection is down would do nothing and say nothing.
  if (payload.type === "trigger_button") {
    haptic([40, 60, 40]);
    showMobileToast("Sin conexión con el PC. Reconectando...", true);
    if (!ws || ws.readyState === WebSocket.CLOSED) connectWebSocket();
  }
}

// Server Message Handler
function handleServerMessage(data) {
  switch (data.type) {
    case "config_sync":
    case "config_updated":
      if (data.button_labels) buttonLabels = { ...buttonLabels, ...data.button_labels };
      currentConfig = data.config;
      renderDeck(currentConfig);
      renderPageNav(currentConfig);
      break;

    case "initial_state":
    case "init_state":
      currentConfig = data.config;
      currentSessions = data.audio_sessions || data.sessions || [];
      buttonStates = data.button_states || {};
      buttonLabels = data.button_labels || {};
      applyTheme(data.theme);
      renderDeck(currentConfig);
      renderPageNav(currentConfig);
      lastMaster = data.master || lastMaster;
      lastMic = data.mic || lastMic;
      if (data.master) updateMasterVolume(data.master.volume, data.master.muted);
      updateAppVolumes();
      applyMicState(data.mic);
      break;

    case "theme":
      applyTheme(data.theme);
      break;

    case "audio_state":
      // Pushed by the PC whenever master or any app volume/mute changes there.
      currentSessions = data.sessions || [];
      lastMaster = data.master || lastMaster;
      lastMic = data.mic || lastMic;
      if (data.master) updateMasterVolume(data.master.volume, data.master.muted);
      updateAppVolumes();
      applyMicState(data.mic);
      break;

    case "button_state":
      buttonStates[data.id] = Boolean(data.active);
      applyButtonState(data.id);
      break;

    case "button_label":
      if (data.sublabel === null || data.sublabel === undefined) delete buttonLabels[data.id];
      else buttonLabels[data.id] = String(data.sublabel);
      applyButtonState(data.id);
      break;

    case "telemetry_update":
      updateTelemetryWidgets(data);
      break;

    case "master_volume_updated":
    case "master_volume_update":
      lastMaster = { volume: data.volume, muted: data.muted };
      updateMasterVolume(data.volume, data.muted);
      break;

    case "master_mute_updated":
    case "master_mute_update":
      if (lastMaster) lastMaster.muted = data.muted;
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
  lastTelemetry = data;
  if (detailSheet && !detailSheet.hidden) renderDetailRows();
  document.querySelectorAll(".deck-monitor").forEach((el) => paintMonitor(el, "deck-monitor", el.dataset.monitor, data));
}

// Render the deck in the size the profile has (6 x 2 by default), with 2-height vertical faders
function renderDeck(config) {
  if (!config) return;
  deckGrid.innerHTML = "";
  masterSliderIds = new Set();

  const slots = config.slots || [];
  const columns = config.layout?.columns || 6;
  const rows = config.layout?.rows || 2;
  const total = config.layout?.total_slots || columns * rows;
  deckGrid.style.setProperty("--cols", columns);
  deckGrid.style.setProperty("--rows", rows);
  // The original 6 x 2 deck flows into 3 wide columns in portrait. Any other size keeps its own columns there,
  // with smaller cells (see style.css).
  const isDefault = columns === 6 && rows === 2;
  deckGrid.style.setProperty("--pcols", columns);
  deckGrid.style.setProperty("--prows", rows);
  deckGrid.toggleAttribute("data-custom", !isDefault);
  // A big deck (many columns or rows) keeps usable cells and scrolls when they do not fit the screen.
  deckGrid.toggleAttribute("data-big", columns > 6 || rows > 4);
  // Up to 8 columns the cells shrink to fit a 390 px screen; only 9 or 10 columns scroll sideways.
  deckGrid.style.setProperty("--min-col", columns > 8 ? "42px" : "36px");
  deckGrid.style.setProperty("--min-row", rows > 4 ? "56px" : "60px");

  for (let idx = 0; idx < total; idx++) {
    const slot = slots[idx] || { index: idx, type: "empty" };
    const col = (idx % columns) + 1;
    const row = Math.floor(idx / columns) + 1;

    // If occupied by a 2-height vertical fader spanning from row 1, skip rendering an extra cell
    if (slot.type === "occupied_by_slider") {
      continue;
    }

    // Position goes in CSS variables rather than inline grid styles: in landscape the cells use
    // them as they are (columns x rows), and in portrait the stylesheet lets them flow into 3 columns.
    let cell;
    let rowStart = row;
    let span = 1;
    if (slot.type === "button") {
      cell = createButtonElement(slot);
    } else if (slot.type === "slider") {
      cell = createFaderElement(slot);
      rowStart = 1;
      span = Math.max(1, Math.min(Number.isInteger(slot.row_span) ? slot.row_span : 2, rows)); // its own height, 2 rows by default
    } else {
      cell = document.createElement("div");
      cell.className = "deck-slot-empty";
    }
    cell.style.setProperty("--col", col);
    cell.style.setProperty("--row", rowStart);
    cell.style.setProperty("--span", span);
    deckGrid.appendChild(cell);
  }

  // The faders were just created with placeholder values. Paint what the PC is doing now, otherwise
  // changing page (or reconnecting) shows 50% everywhere until some volume happens to change.
  if (lastMaster) updateMasterVolume(lastMaster.volume, lastMaster.muted);
  updateAppVolumes();
  applyMicState(lastMic);
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

// Studio owns the theme. The phone follows it and remembers it for the next load.
const KNOWN_THEMES = ["ctma", "cian", "violeta", "verde", "rojo", "rosa", "naranja"];
function applyTheme(theme) {
  if (!KNOWN_THEMES.includes(theme)) return;
  document.documentElement.dataset.theme = theme;
  // The browser bar takes the page background, whichever palette that is.
  const background = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  if (background) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", background);
  try { localStorage.setItem("streamdesk_theme", theme); } catch (e) {}
}

// What a button says while it is on, so the state is readable at arm's length.
const STATE_LABELS = {
  "obs_action:record_toggle": "Grabando",
  "obs_action:stream_toggle": "En directo",
  "obs_action:mute_mic": "Silenciado",
  "windows:mic_mute": "Silenciado",
  "windows:app_mute": "Silenciado",
};

// Keys with two looks: the microphone shows its muted icon while it is muted.
const STATE_ICONS = { "windows:mic_mute": ["/static/icons/mic.svg", "/static/icons/mic_off.svg"] };

// A two-state key shows its "alt" look while it is lit.
function lookOf(slot) {
  return slot.toggle && slot.alt && buttonStates[slot.id] ? slot.alt : slot;
}

function iconFor(slot) {
  const look = lookOf(slot);
  const base = look.image || look.icon || slot.image || slot.icon || "/static/icons/power.svg";
  const pair = STATE_ICONS[`${slot.action_type}:${slot.target}`];
  return pair && base === pair[0] && buttonStates[slot.id] ? pair[1] : base;
}

function subLabelFor(slot) {
  if (buttonLabels[slot.id] !== undefined) return buttonLabels[slot.id];
  if (slot.toggle && slot.alt && buttonStates[slot.id]) return slot.alt.sublabel || "";
  if (buttonStates[slot.id]) return STATE_LABELS[`${slot.action_type}:${slot.target}`] || slot.sublabel || "";
  return slot.sublabel || "";
}

function applyButtonState(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("is-active", Boolean(buttonStates[id]));
  const slot = (currentConfig?.slots || []).find(s => s.id === id);
  const sub = el.querySelector(".deck-btn-sub");
  if (slot && sub) sub.textContent = subLabelFor(slot);
  const img = el.querySelector(".deck-btn-img");
  if (slot && img) img.src = iconFor(slot);
  if (slot) {
    const look = lookOf(slot);
    const title = el.querySelector(".deck-btn-title");
    if (title) title.textContent = look.label || slot.label || "Botón";
    const accent = el.querySelector(".deck-btn-accent");
    const colour = look.color || slot.color;
    if (accent && colour) {
      accent.style.background = colour;
      accent.style.boxShadow = `0 0 8px ${colour}`;
    }
  }
}

// System gauges are drawn by monitors.js (shared with Studio). The phone only keeps the last reading,
// so a gauge created later (page change, reconnect) shows a real value at once.
let lastTelemetry = null;

// Tapping a gauge opens a sheet with every reading. It touches nothing on the PC, so it cannot pull the user
// out of the program they are using.
const detailSheet = document.getElementById("detail-sheet");

function renderDetailRows() {
  const box = document.getElementById("detail-rows");
  if (!box) return;
  box.innerHTML = monitorDetailRows(lastTelemetry || {}).map(row =>
    `<div class="detail-row"><b>${row.name}</b><span>${row.text}</span></div>`).join("");
}

function openSystemDetail() {
  if (!detailSheet) return;
  renderDetailRows();
  detailSheet.hidden = false;
}

function closeSystemDetail() {
  if (detailSheet) detailSheet.hidden = true;
}

document.getElementById("btn-close-detail")?.addEventListener("click", closeSystemDetail);
detailSheet?.addEventListener("click", (event) => { if (event.target === detailSheet) closeSystemDetail(); });

function createMonitorElement(btn, keycap) {
  keycap.classList.add("deck-monitor");
  keycap.addEventListener("pointerdown", () => { haptic(15); openSystemDetail(); });
  keycap.dataset.monitor = btn.target;
  keycap.innerHTML = `<div class="deck-btn-inner"><div class="deck-btn-accent"></div>${monitorInnerHtml("deck-monitor", btn.target)}</div>`;
  keycap.querySelector(".deck-btn-accent").style.background = btn.color || "var(--accent)";
  keycap.querySelector(".deck-monitor-name").textContent = btn.label || MONITORS[btn.target]?.name || "Sistema";
  keycap.classList.add(`kind-${MONITORS[btn.target]?.kind || "percent"}`);
  if (lastTelemetry) paintMonitor(keycap, "deck-monitor", btn.target, lastTelemetry);
  return keycap;
}

// Text from the profile or from Windows goes into markup through this: quotes and angle brackets become entities.
function escapeAttr(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

const LONG_PRESS_MS = 500;
const DOUBLE_TAP_MS = 280;

// A small yes/no sheet. Resolves true when the user confirms.
function askConfirm(message) {
  return new Promise((resolve) => {
    if (document.querySelector(".confirm-overlay")) return resolve(false); // one question at a time
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay confirm-overlay";
    overlay.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true">
        <p class="modal-title"></p>
        <div class="modal-actions">
          <button class="btn-secondary" data-answer="no">Cancelar</button>
          <button class="btn-primary" data-answer="yes">Ejecutar</button>
        </div>
      </div>`;
    overlay.querySelector(".modal-title").textContent = message;
    const shownAt = Date.now();
    overlay.addEventListener("click", (event) => {
      const answer = event.target.closest("[data-answer]")?.dataset.answer;
      // The click that follows the touch which opened the sheet must not close it again.
      if (answer || (event.target === overlay && Date.now() - shownAt > 400)) {
        overlay.remove();
        resolve(answer === "yes");
      }
    });
    document.body.appendChild(overlay);
  });
}

function createButtonElement(btn) {
  const keycap = document.createElement("div");
  keycap.className = "deck-btn";
  keycap.id = btn.id || `slot_btn_${btn.index}`;
  if (buttonStates[keycap.id]) keycap.classList.add("is-active");
  if (btn.action_type === "hardware_monitor") return createMonitorElement(btn, keycap);

  const inner = document.createElement("div");
  inner.className = "deck-btn-inner";

  const btnColor = lookOf(btn).color || btn.color || "var(--accent-blue)";
  const accent = document.createElement("div");
  accent.className = "deck-btn-accent";
  accent.style.background = btnColor;
  accent.style.boxShadow = `0 0 8px ${btnColor}`;
  inner.appendChild(accent);

  const iconWrap = document.createElement("div");
  iconWrap.className = "deck-btn-icon-wrapper";

  const iconSrc = iconFor(btn);
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
  title.textContent = lookOf(btn).label || btn.label || "Botón";
  textWrap.appendChild(title);

  const sub = document.createElement("div");
  sub.className = "deck-btn-sub";
  sub.textContent = subLabelFor(btn);
  textWrap.appendChild(sub);

  inner.appendChild(textWrap);
  keycap.appendChild(inner);

  // A button can also have a long-press and a double-tap action, can ask before running, or be switched off.
  const longAction = !!btn.long_press;
  const doubleAction = !!btn.double_tap;
  const fire = async (gesture) => {
    if (btn.disabled) return showMobileToast("Este botón está desactivado", true);
    if (btn.confirm && !(await askConfirm(`¿Ejecutar «${btn.label || "este botón"}»?`))) return;
    sendWS(gesture === "tap" ? { type: "trigger_button", id: btn.id } : { type: "trigger_button", id: btn.id, gesture });
  };
  if (btn.disabled) keycap.classList.add("is-disabled");
  if (btn.action_type === "none") keycap.classList.add("is-blank");
  const plain = !btn.long_press && !btn.double_tap; // no gestures: the touch only has one meaning
  if (longAction || doubleAction) keycap.classList.add("has-gestures");

  // Tactile touch & trigger micro-animation
  let holdTimer = null, tapTimer = null, longFired = false, secondPress = false, moved = false, startX = 0, startY = 0, pressed = false;
  keycap.addEventListener("pointerdown", (event) => {
    if (btn.action_type === "none") return; // an empty key: nothing to press yet
    if (!plain) haptic(25);
    keycap.classList.add("triggered");
    keycap.style.borderColor = btnColor;
    keycap.style.boxShadow = `0 0 16px ${btnColor}`;
    startX = event.clientX;
    startY = event.clientY;
    moved = false;
    pressed = true;
    if (plain) return; // acts when the finger lifts (see pointerup), not when it lands: a swipe must not press it
    longFired = false;
    secondPress = false;
    moved = false;
    startX = event.clientX;
    startY = event.clientY;
    clearTimeout(holdTimer); // a second finger must not leave the first timer running unattended
    if (tapTimer) { // a second press while the first tap is still waiting: this is a double tap (or a hold)
      clearTimeout(tapTimer);
      tapTimer = null;
      secondPress = true;
    }
    if (longAction) {
      holdTimer = setTimeout(() => { longFired = true; haptic([30, 40, 30]); fire("long_press"); }, LONG_PRESS_MS);
    }
  });
  // A swipe across the key (to change page) is not a press: cancel the hold and do not fire on release.
  keycap.addEventListener("pointermove", (event) => {
    if (!moved && Math.hypot(event.clientX - startX, event.clientY - startY) > 12) {
      moved = true;
      clearTimeout(holdTimer);
    }
  });
  keycap.addEventListener("contextmenu", (event) => event.preventDefault()); // no image menu competing with a long press
  keycap.addEventListener("pointerup", () => {
    clearTimeout(holdTimer);
    if (plain) {
      if (pressed && !moved) { haptic(25); fire("tap"); }
      pressed = false;
      return;
    }
    if (moved || longFired) return;
    if (!doubleAction) return void fire("tap");
    if (secondPress) {
      secondPress = false;
      return void fire("double_tap");
    }
    clearTimeout(tapTimer); // another finger may have left a tap waiting: one tap per gesture
    tapTimer = setTimeout(() => { tapTimer = null; fire("tap"); }, DOUBLE_TAP_MS);
  });
  const cancelHold = () => { clearTimeout(holdTimer); pressed = false; };
  keycap.addEventListener("pointercancel", cancelHold);
  keycap.addEventListener("pointerleave", cancelHold);

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
  // Only app faders have a target app. A master fader listed here got the first session's
  // volume painted over it on every audio update, which looked like a broken sync.
  if (!isMaster) targetAppMap[slider.id] = targetProcess;
  isDraggingMap[slider.id] = false;
  if (isMaster) masterSliderIds.add(slider.id);

  const headerIcon = slider.image 
    ? `<img src="${escapeAttr(slider.image)}" class="fader-header-icon" alt="">` 
    : `<img src="/static/icons/${isMaster ? 'volume_up' : 'spotify'}.svg" class="fader-header-icon" alt="">`;

  const faderColor = slider.color || (isMaster ? "var(--accent-blue)" : "var(--accent-purple)");

  card.innerHTML = `
    <div class="fader-header">
      <div class="fader-header-title">
        ${headerIcon}
        <span>${escapeAttr(slider.label || (isMaster ? "Master" : "App"))}</span>
      </div>
      ${!isMaster ? `<button class="app-select-btn" id="select-app-${slider.id}">${cleanAppName(targetProcess)}</button>` : ''}
    </div>
    <div class="fader-track-container" id="track-${slider.id}">
      <div class="fader-fill" id="fill-${slider.id}" style="height: 50%; background: ${faderColor}; box-shadow: 0 0 10px ${faderColor};">
        <div class="fader-thumb"></div>
      </div>
    </div>
    <div class="fader-footer">
      ${!isMaster ? '<div class="fader-idle-note">Sin sonido</div>' : ''}
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
  let lastPercent = null;   // the value the finger last chose: what is sent when it lifts
  let active = false;       // a touch is on this fader
  let engaged = false;      // the finger moved (or grabbed the thumb): only then does the volume change
  let startY = 0;
  let grabOffset = 0;

  function handleCoord(clientY, forceSend = false) {
    const rect = trackEl.getBoundingClientRect();
    if (rect.height <= 0) return;

    let percent = Math.round(((rect.bottom - clientY) / rect.height) * 100);
    percent = Math.max(0, Math.min(100, percent));
    lastPercent = percent;

    const fillEl = document.getElementById(`fill-${sliderId}`);
    const valEl = document.getElementById(`val-${sliderId}`);
    if (fillEl) fillEl.style.height = `${percent}%`;
    if (valEl) valEl.textContent = `${percent}%`;

    const now = Date.now();
    if (forceSend || now - lastSent > 50) {
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
    active = true;
    lastPercent = null;
    startY = e.clientY;
    try { trackEl.setPointerCapture(e.pointerId); } catch (err) {}
    haptic(15);
    // Touching near the thumb grabs it where it is. Touching far from it changes nothing until the finger slides:
    // a palm or a stray touch on the track must not throw the volume to 100%.
    const rect = trackEl.getBoundingClientRect();
    const current = parseFloat(document.getElementById(`fill-${sliderId}`)?.style.height) || 0;
    const thumbY = rect.bottom - (current / 100) * rect.height;
    if (Math.abs(e.clientY - thumbY) <= 40) {
      grabOffset = thumbY - e.clientY;
      engaged = true;
    } else {
      grabOffset = 0;
      engaged = false;
    }
  });

  trackEl.addEventListener("pointermove", (e) => {
    if (!active) return;
    e.preventDefault();
    if (!engaged) {
      if (Math.abs(e.clientY - startY) < 6) return;
      engaged = true;
    }
    handleCoord(e.clientY + grabOffset);
  });

  const stopDrag = () => {
    if (!active) return; // pointerup, pointercancel and lostpointercapture all end here: only the first counts
    active = false;
    // Send the last value the finger chose, never a coordinate read from the closing event (it can be 0).
    if (engaged && lastPercent !== null) handleCoord(trackEl.getBoundingClientRect().bottom - (lastPercent / 100) * trackEl.getBoundingClientRect().height, true);
    // Keep ignoring server echoes briefly so the thumb does not snap back to an older value.
    setTimeout(() => {
      isDraggingMap[sliderId] = false;
    }, 400);
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
    if (isDraggingMap[sliderId] || masterSliderIds.has(sliderId)) return;

    const proc = targetAppMap[sliderId];
    const session = currentSessions.find(s => s.process_name?.toLowerCase() === proc?.toLowerCase());
    // Windows only has an audio session for an app while it plays, so an app that is silent
    // cannot be read. Say so instead of showing a stale value; a volume set meanwhile is applied later.
    document.getElementById(`fader-card-${sliderId}`)?.classList.toggle("is-idle", !session);
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
        <span class="app-item-name">${escapeAttr(s.display_name)}</span>
        <span class="app-item-proc">${escapeAttr(s.process_name)}</span>
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

// --- QR Scanner & Roaming IP Management ---
let qrStream = null;
let qrScanInterval = null;

function saveRecentIp(hostStr) {
  if (!hostStr || hostStr.startsWith("localhost") || hostStr.startsWith("127.0.0.1")) return;
  try {
    let recent = JSON.parse(localStorage.getItem("streamdesk_recent_ips") || "[]");
    recent = [hostStr, ...recent.filter(h => h !== hostStr)].slice(0, 5);
    localStorage.setItem("streamdesk_recent_ips", JSON.stringify(recent));
  } catch (e) {}
}

function renderRecentIps() {
  const container = document.getElementById("recent-ips-container");
  const list = document.getElementById("recent-ips-list");
  if (!container || !list) return;
  try {
    const recent = JSON.parse(localStorage.getItem("streamdesk_recent_ips") || "[]");
    if (!recent.length) { container.style.display = "none"; return; }
    container.style.display = "block";
    list.innerHTML = recent.map(host => `
      <button type="button" class="btn-secondary" style="font-size: 11px; padding: 4px 8px; border-radius: 4px;" data-recent-ip="${escapeAttr(host)}">
        ${escapeAttr(host)}
      </button>
    `).join("");
    list.querySelectorAll("[data-recent-ip]").forEach(btn => {
      btn.addEventListener("click", () => {
        navigateToHost(btn.dataset.recentIp);
      });
    });
  } catch (e) { container.style.display = "none"; }
}

function navigateToHost(hostStr, pin) {
  let cleanHost = hostStr.trim().replace(/^https?:\/\//i, "").replace(/\/$/, "");
  if (!cleanHost.includes(":")) cleanHost += ":48291";
  saveRecentIp(cleanHost);
  const target = pin ? `http://${cleanHost}/?pin=${encodeURIComponent(pin)}` : `http://${cleanHost}/`;
  // The app opens it itself, so it can tell which PC it is (and hand over that PC's pairing).
  if (nativeApp) { nativeCall("openUrl", target); return; }
  window.location.href = target;
}

async function startQrScanner() {
  const box = document.getElementById("qr-scanner-box");
  const pinControls = document.getElementById("pin-controls-box");
  const video = document.getElementById("qr-video");
  const status = document.getElementById("qr-scan-status");
  if (!box || !video) return;

  box.style.display = "block";
  if (pinControls) pinControls.style.display = "none";
  if (status) status.textContent = "Iniciando cámara...";

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (status) status.textContent = "Tu navegador no permite acceso a la cámara. Introduce la IP manualmente.";
    return;
  }

  try {
    qrStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }
    });
    video.srcObject = qrStream;
    await video.play();
    if (status) status.textContent = "Apunta con la cámara al código QR de Studio...";

    let detector = null;
    if ("BarcodeDetector" in window) {
      try {
        detector = new BarcodeDetector({ formats: ["qr_code"] });
      } catch (e) {}
    }

    qrScanInterval = setInterval(async () => {
      if (!qrStream || video.readyState < 2) return;
      try {
        if (detector) {
          const barcodes = await detector.detect(video);
          if (barcodes && barcodes.length > 0) {
            handleScannedQr(barcodes[0].rawValue);
          }
        }
      } catch (e) {}
    }, 250);
  } catch (err) {
    console.error("Camera access error:", err);
    if (status) status.textContent = "No se pudo acceder a la cámara. Introduce la IP abajo.";
  }
}

function stopQrScanner() {
  if (qrScanInterval) { clearInterval(qrScanInterval); qrScanInterval = null; }
  if (qrStream) {
    qrStream.getTracks().forEach(t => t.stop());
    qrStream = null;
  }
  const box = document.getElementById("qr-scanner-box");
  const pinControls = document.getElementById("pin-controls-box");
  if (box) box.style.display = "none";
  if (pinControls) pinControls.style.display = "block";
}

function handleScannedQr(rawText) {
  stopQrScanner();
  showMobileToast("¡Código QR detectado!");
  haptic([30, 50]);

  try {
    if (rawText.startsWith("http://") || rawText.startsWith("https://")) {
      const url = new URL(rawText);
      saveRecentIp(url.host);
      if (nativeApp) nativeCall("openUrl", rawText); else window.location.href = rawText;
      return;
    }
    if (/^\d{6}$/.test(rawText.trim())) {
      autoPairWithPin(rawText.trim());
      return;
    }
  } catch (e) {
    console.error("QR Parse error", e);
  }
}

// PIN Modal & Authentication Handlers
function showPinModal(canClose = true) {
  if (pinModal) {
    pinModal.style.display = "flex";
  }
  if (btnClosePinModal) {
    btnClosePinModal.style.display = canClose ? "block" : "none";
  }
  const customIpInput = document.getElementById("custom-ip-input");
  if (customIpInput && !customIpInput.value) {
    customIpInput.value = window.location.host;
  }
  renderRecentIps();
  updateScanButton();
  setTimeout(() => {
    document.getElementById("pin-input")?.focus();
  }, 100);
}

document.getElementById("btn-status-badge")?.addEventListener("click", () => openSettingsSheet());
document.getElementById("btn-open-settings")?.addEventListener("click", () => openSettingsSheet());

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
      storeToken(data.token);
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
      pinError.textContent = "Escribe el PIN de 6 dígitos que muestra StreamDesk Studio.";
      pinError.style.display = "block";
      pinError.scrollIntoView({ block: "nearest" });
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
      storeToken(data.token);
      if (pinModal) pinModal.style.display = "none";
      if (pinError) pinError.style.display = "none";
      try {
        window.history.replaceState({}, document.title, window.location.pathname);
      } catch (e) {}
      showMobileToast("Vinculado con tu PC");
      connectWebSocket();
    } else {
      if (pinError) {
        pinError.textContent = data.detail || data.error || "PIN incorrecto. Revisa el código en tu PC.";
        pinError.style.display = "block";
        pinError.scrollIntoView({ block: "nearest" });
      }
      haptic([40, 60, 40]);
    }
  } catch (err) {
    if (pinError) {
      pinError.textContent = "No se pudo contactar con el PC. Comprueba que estáis en la misma Wi-Fi y que StreamDesk está abierto.";
      pinError.style.display = "block";
      pinError.scrollIntoView({ block: "nearest" });
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

// Event Listeners for QR & IP Switching
// The browser only gives a page the camera on https (or localhost), so on the plain-http address of a PC in the
// network the scanner below can never start: say so instead of showing a button that does nothing. The Android app
// scans with its own camera screen, which works everywhere.
function canScanQr() {
  return Boolean(nativeApp) || Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}
function updateScanButton() {
  const button = document.getElementById("btn-start-qr");
  const hint = document.getElementById("scan-hint");
  const can = canScanQr();
  if (button) button.style.display = can ? "inline-flex" : "none";
  if (hint) hint.hidden = can;
}
document.getElementById("btn-start-qr")?.addEventListener("click", () => {
  if (nativeApp) nativeCall("scanQr"); else startQrScanner();
});
document.getElementById("btn-cancel-qr")?.addEventListener("click", stopQrScanner);

document.getElementById("btn-toggle-custom-ip")?.addEventListener("click", () => {
  const customIpBox = document.getElementById("custom-ip-box");
  if (customIpBox) {
    const isHidden = customIpBox.style.display === "none";
    customIpBox.style.display = isHidden ? "block" : "none";
    if (isHidden) {
      renderRecentIps();
      document.getElementById("custom-ip-input")?.focus();
    }
  }
});

document.getElementById("btn-connect-custom-ip")?.addEventListener("click", () => {
  const customIpInput = document.getElementById("custom-ip-input");
  const host = (customIpInput?.value || "").trim();
  if (host) {
    navigateToHost(host);
  }
});

document.getElementById("custom-ip-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    document.getElementById("btn-connect-custom-ip")?.click();
  }
});

// In the app this goes to its own screen (search for the PC, scan the QR, type the address); in a browser, the pairing window.
function openConnectOptions() {
  if (nativeApp) { nativeCall("showConnect"); return; }
  showPinModal(true);
}

document.getElementById("btn-banner-reconnect")?.addEventListener("click", (e) => {
  e.stopPropagation();
  openConnectOptions();
});

document.getElementById("reconnect-banner")?.addEventListener("click", openConnectOptions);

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
