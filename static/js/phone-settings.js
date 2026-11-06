// The phone's settings sheet: pages, screen, "install as an app" and the connection to the PC.
// Loaded after streamdeck.js, whose globals (currentConfig, switchPage, token, ws...) it uses.

const settingsSheet = document.getElementById("settings-sheet");

function phoneEnvironment() {
  const agent = navigator.userAgent;
  return {
    ios: /iPhone|iPad|iPod/.test(agent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
    android: /Android/.test(agent),
    // Opened from the home screen icon rather than from a browser tab.
    standalone: matchMedia("(display-mode: standalone)").matches || matchMedia("(display-mode: fullscreen)").matches || navigator.standalone === true,
    // Chrome only offers to install, and only allows service workers and wake lock, on https (or localhost).
    secure: window.isSecureContext,
  };
}

function escapeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

// navigator.clipboard does not exist on http pages, which is exactly where the install steps are needed.
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) { /* fall through to the old way */ }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.cssText = "position: fixed; opacity: 0; top: 0;";
  document.body.appendChild(box);
  box.select();
  let copied = false;
  try { copied = document.execCommand("copy"); } catch (e) { copied = false; }
  box.remove();
  return copied;
}

function wantsFullscreen() {
  try { return localStorage.getItem("streamdesk_fullscreen") === "1"; } catch (e) { return false; }
}

function copyButton(label, text) {
  return `<div class="sheet-copy"><code>${escapeText(text)}</code><button class="btn-secondary" data-copy="${escapeText(text)}">${label}</button></div>`;
}

// ------------------------------------------------------------------ install check

// Chrome offers "Install" only when every one of these holds. Showing them (and a report to copy)
// turns "it does not let me" into something we can read.
async function runInstallChecks() {
  const env = phoneEnvironment();
  const checks = [];
  const add = (ok, label, detail) => checks.push({ ok, label, detail });

  add(env.secure, "Dirección segura", env.secure ? location.origin : `${location.origin} es http: Chrome no ofrece instalar`);

  if (!("serviceWorker" in navigator)) {
    add(false, "Service worker", "El navegador no lo ofrece en esta dirección");
  } else {
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) add(true, "Service worker", registration.active ? "Activo" : "Registrado, aún sin activar");
      else add(false, "Service worker", swState && !swState.ok ? `No se registró: ${swState.message}` : "Sin registrar todavía");
    } catch (error) {
      add(false, "Service worker", String(error && error.message || error));
    }
  }

  let manifest = null;
  try {
    const link = document.querySelector('link[rel="manifest"]');
    const response = await fetch(link.href);
    manifest = await response.json();
    add(true, "Manifiesto", `${manifest.name}, ${manifest.display}, ${manifest.icons.length} iconos`);
  } catch (error) {
    add(false, "Manifiesto", "No se pudo leer");
  }

  if (manifest) {
    const loads = await Promise.all(manifest.icons.map(icon => new Promise((resolve) => {
      const image = new Image();
      image.onload = () => resolve(true);
      image.onerror = () => resolve(false);
      image.src = icon.src;
    })));
    add(loads.every(Boolean), "Iconos", `${loads.filter(Boolean).length} de ${loads.length} cargan`);
  }

  add(Boolean(deferredInstallPrompt), "Chrome ofrece instalar", deferredInstallPrompt ? "Sí" : "Todavía no lo ha ofrecido");
  add(env.standalone, "Abierta como app", env.standalone ? "Sí" : "No, estás en una pestaña del navegador");
  return checks;
}

function installReportText(checks) {
  return [
    "Informe de instalación de StreamDesk",
    `Navegador: ${navigator.userAgent}`,
    ...checks.map(c => `${c.ok ? "OK   " : "FALLA"} ${c.label}: ${c.detail}`),
  ].join("\n");
}

function installReportHtml(checks) {
  return `<ul class="sheet-checks">${checks.map(c =>
    `<li class="${c.ok ? "ok" : "bad"}"><strong>${escapeText(c.label)}</strong><span>${escapeText(c.detail)}</span></li>`).join("")}</ul>
    <button class="btn-secondary" id="sheet-install-copy">Copiar informe</button>
    <p class="sheet-note">Si «Instalar» aparece pero no se completa, las causas más habituales son: sin conexión a internet (Android genera la app a través de los servidores de Google), Chrome desactualizado o sin Google Play Services. Si pasa, pégame el informe.</p>`;
}

// ------------------------------------------------------------------ install assistant

function installSectionHtml() {
  const env = phoneEnvironment();
  if (env.standalone) return `<p class="sheet-note ok">Estás usando StreamDesk como app instalada.</p>`;

  const checkButton = `<button class="btn-secondary sheet-check-button" id="sheet-install-check">Comprobar por qué no se instala</button><div id="sheet-install-report"></div>`;

  if (deferredInstallPrompt) {
    return `<p class="sheet-note">Tu navegador puede instalar StreamDesk ahora mismo.</p>
      <button class="btn-primary" id="sheet-install-now">Instalar app</button>${checkButton}`;
  }

  if (env.ios) {
    return `<ol class="sheet-steps">
      <li>Abre esta página en <strong>Safari</strong>.</li>
      <li>Pulsa <strong>Compartir</strong> (el cuadrado con una flecha hacia arriba).</li>
      <li>Elige <strong>Añadir a pantalla de inicio</strong> y pulsa <strong>Añadir</strong>.</li>
    </ol>
    <p class="sheet-note">La app instalada guarda sus datos aparte de Safari, así que la primera vez te pedirá el PIN otra vez.</p>${checkButton}`;
  }

  if (env.android && !env.secure) {
    return `<p class="sheet-note">Chrome solo deja instalar webs seguras (https). Tu PC ofrece StreamDesk por http dentro de tu red, por eso no aparece «Instalar». Se arregla una vez, en 1 minuto:</p>
      <ol class="sheet-steps">
        <li>Copia la dirección de esta página:${copyButton("Copiar", location.origin)}</li>
        <li>Abre una pestaña nueva en Chrome, pega esto en la barra de direcciones y ábrelo:${copyButton("Copiar", "chrome://flags/#unsafely-treat-insecure-origin-as-secure")}</li>
        <li>En <strong>Insecure origins treated as secure</strong>, pega la dirección del paso 1, elige <strong>Enabled</strong> y pulsa <strong>Relaunch</strong>.</li>
        <li>Vuelve a abrir StreamDesk: en el menú ⋮ de Chrome aparecerá <strong>Instalar app</strong>, y aquí el botón «Instalar app».</li>
      </ol>
      <p class="sheet-note">Si la dirección de tu PC cambia, repite el paso 3 con la nueva. Mientras tanto, menú ⋮ → «Añadir a la pantalla de inicio» crea un acceso directo, y con «Pantalla completa» se ve sin barras.</p>${checkButton}`;
  }

  const caHelper = `<p class="sheet-note">Si tu móvil muestra advertencia de certificado: <a href="/ca.crt" download="streamdesk-ca.crt" style="color:var(--accent);text-decoration:underline;">Descargar Certificado CA</a> (Instálalo en Ajustes de Android → Seguridad → Certificados de CA para que Chrome active la PWA).</p>`;
  return `<ol class="sheet-steps">
    <li>Abre el menú del navegador (⋮ o los tres puntos).</li>
    <li>Elige <strong>Instalar app</strong> o <strong>Añadir a la pantalla de inicio</strong>.</li>
  </ol>${caHelper}${checkButton}`;
}

function renderInstall() {
  const container = document.getElementById("sheet-install");
  container.innerHTML = installSectionHtml();
  container.querySelector("#sheet-install-now")?.addEventListener("click", async () => {
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    renderInstall();
  });
  container.querySelector("#sheet-install-check")?.addEventListener("click", async (event) => {
    event.target.disabled = true;
    event.target.textContent = "Comprobando...";
    const checks = await runInstallChecks();
    const report = container.querySelector("#sheet-install-report");
    report.innerHTML = installReportHtml(checks);
    report.querySelector("#sheet-install-copy").addEventListener("click", async (click) => {
      const copied = await copyText(installReportText(checks));
      click.target.textContent = copied ? "Informe copiado" : "No se pudo copiar";
    });
    event.target.textContent = "Volver a comprobar";
    event.target.disabled = false;
  });
  container.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
    const copied = await copyText(button.dataset.copy);
    button.textContent = copied ? "Copiado" : "Mantén pulsado el texto para copiarlo";
  }));
}

// ------------------------------------------------------------------ pages, screen and connection

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

function renderScreen() {
  const container = document.getElementById("sheet-screen");
  const canFullscreen = Boolean(document.fullscreenEnabled);
  container.innerHTML = `
    ${canFullscreen
      ? `<button class="btn-secondary" id="sheet-fullscreen">${document.fullscreenElement ? "Salir de pantalla completa" : "Pantalla completa"}</button>
         <label class="sheet-check"><input type="checkbox" id="sheet-fullscreen-pref" ${wantsFullscreen() ? "checked" : ""}> Abrir siempre en pantalla completa (al primer toque)</label>`
      : `<p class="sheet-note">Este móvil no permite pantalla completa desde la web. Instala la app y se verá sin barras.</p>`}
    ${"wakeLock" in navigator
      ? `<p class="sheet-note">La pantalla no se apaga mientras StreamDesk está abierto.</p>`
      : `<p class="sheet-note">En http el navegador no deja mantener la pantalla encendida: se apagará sola según tu ajuste de pantalla. Con la app instalada por https no pasa.</p>`}`;
  container.querySelector("#sheet-fullscreen")?.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    } catch (e) { /* the browser said no */ }
    renderScreen();
  });
  container.querySelector("#sheet-fullscreen-pref")?.addEventListener("change", (event) => {
    try { localStorage.setItem("streamdesk_fullscreen", event.target.checked ? "1" : "0"); } catch (e) { /* private mode */ }
  });
}

function renderConnection() {
  const container = document.getElementById("sheet-connection");
  container.innerHTML = `
    <p class="sheet-note">Estado: <strong>${escapeText(document.getElementById("status-text")?.textContent || "")}</strong><br>PC: <code>${escapeText(location.host)}</code></p>
    <div class="sheet-buttons">
      <button class="btn-secondary" id="sheet-reconnect">Reconectar ahora</button>
      <button class="btn-danger" id="sheet-forget">Vincular con otro PC</button>
    </div>`;
  container.querySelector("#sheet-reconnect").addEventListener("click", () => {
    closeSettingsSheet();
    connectWebSocket();
  });
  const forget = container.querySelector("#sheet-forget");
  let armed = false;
  forget.addEventListener("click", () => {
    if (!armed) {
      armed = true;
      forget.textContent = "Pulsa otra vez para olvidar este PC";
      setTimeout(() => { armed = false; forget.textContent = "Vincular con otro PC"; }, 4000);
      return;
    }
    try { localStorage.removeItem("streamdesk_token"); } catch (e) { /* private mode */ }
    token = null;
    try { ws && ws.close(); } catch (e) { /* already closed */ }
    closeSettingsSheet();
    showPinModal(false);
  });
}

// ------------------------------------------------------------------ open / close

function openSettingsSheet(section) {
  renderPages();
  renderScreen();
  renderInstall();
  renderConnection();
  settingsSheet.hidden = false;
  if (section) document.getElementById(`sheet-${section}`)?.closest(".sheet-section")?.scrollIntoView({ block: "start" });
}

function closeSettingsSheet() {
  settingsSheet.hidden = true;
}

document.getElementById("btn-close-sheet")?.addEventListener("click", closeSettingsSheet);
settingsSheet?.addEventListener("pointerdown", (event) => { if (event.target === settingsSheet) closeSettingsSheet(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !settingsSheet.hidden) closeSettingsSheet(); });
document.getElementById("current-page-name")?.addEventListener("click", () => openSettingsSheet("pages"));
window.addEventListener("beforeinstallprompt", () => { if (!settingsSheet.hidden) renderInstall(); });
document.addEventListener("fullscreenchange", () => { if (!settingsSheet.hidden) renderScreen(); });

// "Always open full screen": browsers only allow it from a touch, so it happens on the first one.
document.addEventListener("pointerup", () => {
  if (wantsFullscreen() && document.fullscreenEnabled && !document.fullscreenElement) {
    document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
  }
}, { once: true });
