// The phone's settings sheet: pages, panel options, installing the app and the connection to the PC.
// Loaded after streamdeck.js, whose globals (currentConfig, switchPage, token, ws, swipeEnabled...) it uses.

const settingsSheet = document.getElementById("settings-sheet");

// Where the Android app is published (kept equal to ANDROID_APK_URL in server/paths.py by a test).
const ANDROID_APK_URL = "https://github.com/Zak208/streamdeck/releases/latest/download/StreamDesk.apk";

function phoneEnvironment() {
  const agent = navigator.userAgent;
  return {
    ios: /iPhone|iPad|iPod/.test(agent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
    android: /Android/.test(agent),
    // The StreamDesk Android app (a WebView with a bridge), which is already "installed" by definition.
    app: typeof window.AndroidApp !== "undefined",
    // Opened from the home screen icon rather than from a browser tab.
    standalone: matchMedia("(display-mode: standalone)").matches || matchMedia("(display-mode: fullscreen)").matches || navigator.standalone === true,
    // Chrome only offers to install, and only allows service workers, on https (or localhost).
    secure: window.isSecureContext,
  };
}

function escapeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// ------------------------------------------------------------------ install

// Empty when there is nothing to offer (already the app or installed): the whole section is then hidden.
function installSectionHtml() {
  const env = phoneEnvironment();
  if (env.app || env.standalone) return "";

  if (deferredInstallPrompt) {
    return `<p class="sheet-note">Tu navegador puede instalar StreamDesk ahora mismo.</p>
      <button class="btn-primary" id="sheet-install-now">Instalar app</button>`;
  }

  if (env.ios) {
    return `<ol class="sheet-steps">
      <li>Abre esta página en <strong>Safari</strong>.</li>
      <li>Pulsa <strong>Compartir</strong> (el cuadrado con una flecha hacia arriba).</li>
      <li>Elige <strong>Añadir a pantalla de inicio</strong> y pulsa <strong>Añadir</strong>.</li>
    </ol>
    <p class="sheet-note">La app instalada guarda sus datos aparte de Safari, así que la primera vez te pedirá el PIN otra vez.</p>`;
  }

  if (env.android) {
    return `<p class="sheet-note">La app de Android recuerda tu PC y lo busca sola al cambiar de Wi-Fi. Un acceso directo del navegador deja de funcionar al cambiar de red.</p>
      <a class="btn-primary sheet-download" id="sheet-download-apk" href="${escapeText(ANDROID_APK_URL)}" rel="noopener">Descargar la app (APK)</a>
      <p class="sheet-note">Ábrela al terminar la descarga. Si Android avisa de «instalar apps desconocidas», permítelo a Chrome solo para este paso.</p>`;
  }

  return `<p class="sheet-note">Abre el menú del navegador y elige <strong>Instalar app</strong> o <strong>Añadir a la pantalla de inicio</strong>.</p>`;
}

function renderInstall() {
  const section = document.getElementById("sheet-install")?.closest(".sheet-section");
  const container = document.getElementById("sheet-install");
  const html = installSectionHtml();
  if (section) section.hidden = !html;
  container.innerHTML = html;
  container.querySelector("#sheet-install-now")?.addEventListener("click", async () => {
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    renderInstall();
  });
}

// ------------------------------------------------------------------ pages, panel options and connection

function renderPages() {
  const container = document.getElementById("sheet-pages");
  const pages = currentConfig?.pages || [];
  const current = currentConfig?.current_page || 0;
  if (!pages.length) {
    container.innerHTML = `<p class="sheet-note">Todavía no hay páginas: conecta con tu PC.</p>`;
    return;
  }
  container.innerHTML = pages.map((page, index) =>
    `<button class="sheet-page ${index === current ? "active" : ""}" data-page="${index}">${escapeText(page.name || `Página ${index + 1}`)}</button>`).join("");
  container.querySelectorAll("[data-page]").forEach(button => button.addEventListener("click", () => {
    switchPage(Number(button.dataset.page));
    closeSettingsSheet();
  }));
}

function renderPanelOptions() {
  const container = document.getElementById("sheet-screen");
  const hapticLevel = localStorage.getItem("streamdesk_haptic") || "medium";
  const levels = [["off", "No"], ["soft", "Suave"], ["medium", "Media"], ["strong", "Fuerte"]];
  container.innerHTML = `
    <label class="sheet-switch">
      <span><strong>Cambiar de página deslizando</strong><small>Desliza el dedo a los lados sobre el panel</small></span>
      <input type="checkbox" role="switch" id="sheet-swipe" ${swipeEnabled() ? "checked" : ""}>
      <i aria-hidden="true"></i>
    </label>
    <label class="sheet-switch" style="margin-top: 10px;">
      <span><strong>Sincronizar páginas con el PC</strong><small>Al moverte en el PC cambia el móvil, y viceversa</small></span>
      <input type="checkbox" role="switch" id="sheet-sync-pages" ${syncPagesEnabled() ? "checked" : ""}>
      <i aria-hidden="true"></i>
    </label>
    <div class="sheet-field">
      <span class="sheet-label">Vibración al tocar</span>
      <div class="sheet-segment">
        ${levels.map(([value, label]) => `<button type="button" class="sheet-haptic-btn ${hapticLevel === value ? "active" : ""}" data-haptic="${value}">${label}</button>`).join("")}
      </div>
    </div>
    <p class="sheet-note">Los botones con dos puntitos arriba a la derecha hacen otra cosa si los mantienes pulsados o los tocas dos veces.</p>`;
  container.querySelector("#sheet-swipe").addEventListener("change", (event) => {
    try { localStorage.setItem("streamdesk_swipe", event.target.checked ? "1" : "0"); } catch (e) { /* private mode */ }
    if (typeof showMobileToast === "function") showMobileToast(event.target.checked ? "Deslizar para cambiar de página: activado" : "Deslizar para cambiar de página: desactivado");
  });
  container.querySelector("#sheet-sync-pages")?.addEventListener("change", (event) => {
    try { localStorage.setItem("streamdesk_sync_pages", event.target.checked ? "1" : "0"); } catch (e) { /* private mode */ }
    if (typeof showMobileToast === "function") {
      showMobileToast(event.target.checked ? "Sincronización con el PC activada" : "Sincronización con el PC desactivada (independiente)");
    }
  });
  container.querySelectorAll(".sheet-haptic-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const level = btn.dataset.haptic;
      localStorage.setItem("streamdesk_haptic", level);
      container.querySelectorAll(".sheet-haptic-btn").forEach(b => b.classList.toggle("active", b === btn));
      if (typeof haptic === "function") haptic(level === "soft" ? 12 : (level === "strong" ? 45 : 25));
    });
  });
}

function renderConnection() {
  const container = document.getElementById("sheet-connection");
  const inApp = typeof window.AndroidApp !== "undefined";
  container.innerHTML = `
    <p class="sheet-note">Estado: <strong>${escapeText(document.getElementById("status-text")?.textContent || "")}</strong><br>PC: <code>${escapeText(location.host)}</code></p>
    <div class="sheet-buttons">
      <button class="btn-secondary" id="sheet-reconnect">Reconectar ahora</button>
      <button class="btn-danger" id="sheet-forget">${inApp ? "Cambiar de PC" : "Vincular con otro PC"}</button>
    </div>`;
  container.querySelector("#sheet-reconnect").addEventListener("click", () => {
    closeSettingsSheet();
    connectWebSocket();
  });
  const forget = container.querySelector("#sheet-forget");
  // In the app, the app's own screen searches, scans and keeps every PC's pairing, so nothing is forgotten.
  if (inApp) {
    forget.addEventListener("click", () => { closeSettingsSheet(); nativeCall("showConnect"); });
    return;
  }
  let armed = false;
  forget.addEventListener("click", () => {
    if (!armed) {
      armed = true;
      forget.textContent = "Pulsa otra vez para olvidar este PC";
      setTimeout(() => { armed = false; forget.textContent = "Vincular con otro PC"; }, 4000);
      return;
    }
    forgetToken();
    try { ws && ws.close(); } catch (e) { /* already closed */ }
    closeSettingsSheet();
    showPinModal(false);
  });
}

async function renderLogs() {
  const container = document.getElementById("sheet-logs");
  if (!container) return;
  container.innerHTML = `<span class="sheet-note">Cargando registro...</span>`;
  try {
    const t = (typeof window !== "undefined" && window.token) ? window.token : (localStorage.getItem("streamdesk_token") || "");
    const res = await fetch(`/api/logs/mobile?token=${encodeURIComponent(t)}`);
    if (!res.ok) {
      container.innerHTML = `<span class="sheet-note">Solo visible con el móvil conectado y autorizado.</span>`;
      return;
    }
    const data = await res.json();
    const logs = data.logs || [];
    if (!logs.length) {
      container.innerHTML = `<span class="sheet-note" style="color:var(--text-3, #888);">No hay errores recientes. Todo funciona correctamente.</span>`;
      return;
    }
    container.innerHTML = logs.slice(0, 10).map(e => `
      <div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; border-radius: 4px; padding: 6px 8px; margin-bottom: 6px; font-size: 12px;">
        <div style="display:flex; justify-content:space-between; color: #ef4444; font-weight:600; font-size: 11px;">
          <span>${escapeText(e.source || "BOTÓN")}</span>
          <span style="color:var(--text-3, #888); font-weight:normal;">${escapeText(e.time)}</span>
        </div>
        <div style="color: var(--text-1, #fff); margin-top: 2px;">${escapeText(e.message)}</div>
        ${e.details?.page ? `<div style="color: var(--text-3, #aaa); font-size: 10px; margin-top: 2px;">Página: ${escapeText(e.details.page)}</div>` : ""}
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<span class="sheet-note">No se pudo cargar el registro: ${escapeText(err.message)}</span>`;
  }
}

// ------------------------------------------------------------------ open / close

function openSettingsSheet(section) {
  renderPages();
  renderPanelOptions();
  renderInstall();
  renderConnection();
  renderLogs();
  settingsSheet.hidden = false;
  if (section) document.getElementById(`sheet-${section}`)?.closest(".sheet-section")?.scrollIntoView({ block: "start" });
}

function closeSettingsSheet() {
  settingsSheet.hidden = true;
}

document.getElementById("btn-close-sheet")?.addEventListener("click", closeSettingsSheet);
document.getElementById("btn-sheet-refresh-logs")?.addEventListener("click", renderLogs);
settingsSheet?.addEventListener("pointerdown", (event) => { if (event.target === settingsSheet) closeSettingsSheet(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !settingsSheet.hidden) closeSettingsSheet(); });
document.getElementById("current-page-name")?.addEventListener("click", () => openSettingsSheet("pages"));
window.addEventListener("beforeinstallprompt", () => { if (!settingsSheet.hidden) renderInstall(); });
