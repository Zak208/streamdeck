// Studio dialogs: new page from a template, settings and the welcome guide.
// Loaded after studio.js, whose globals (config, loadConfig, switchPage, showToast...) it uses.

const THEMES = [
  { id: "ctma", name: "Negro y amarillo", swatches: ["#0a0a0a", "#555555", "#ffffff", "#f8c700"] },
  { id: "cian", name: "Azul noche y cian", swatches: ["#080a10", "#41536a", "#f4f7fb", "#38bdf8"] },
];

// ---------- Modal helpers ----------

function openModal({ title, description = "", body = "", actions = [], dismissable = true, onMount }) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <h2 class="modal-title">${escapeHtml(title)}</h2>
      ${description ? `<p class="modal-desc">${escapeHtml(description)}</p>` : ""}
      <div class="modal-body">${body}</div>
      ${actions.length ? `<div class="modal-actions"></div>` : ""}
    </div>`;

  const previousFocus = document.activeElement;
  const close = (result) => {
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    previousFocus?.focus?.();
    modal.onClose?.(result);
  };
  const onKey = (event) => { if (event.key === "Escape" && dismissable) close(undefined); };
  const modal = { el: overlay, close, onClose: null };

  const actionsEl = overlay.querySelector(".modal-actions");
  actions.forEach(({ label, kind = "secondary", value, onClick }) => {
    const button = document.createElement("button");
    button.className = `btn-${kind}`;
    button.textContent = label;
    button.addEventListener("click", async () => {
      if (onClick) await onClick(modal);
      else close(value);
    });
    actionsEl.appendChild(button);
  });

  if (dismissable) overlay.addEventListener("mousedown", (event) => { if (event.target === overlay) close(undefined); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  onMount?.(modal);
  (overlay.querySelector("input, .btn-primary, button") || overlay.querySelector(".modal-card")).focus?.();
  return modal;
}

function askConfirm({ title, message, confirmLabel = "Aceptar", danger = false }) {
  return new Promise((resolve) => {
    const modal = openModal({
      title,
      description: message,
      actions: [
        { label: "Cancelar", kind: "secondary", value: false },
        { label: confirmLabel, kind: danger ? "danger" : "primary", value: true },
      ],
    });
    modal.onClose = (result) => resolve(result === true);
  });
}

async function apiJson(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo completar la acción");
  return data;
}

const postJson = (path, body) => apiJson(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

// ---------- New page (blank or from a template) ----------

async function openNewPageDialog() {
  let templates;
  try {
    templates = (await apiJson("/api/templates")).templates;
  } catch (err) {
    showToast(err.message);
    return;
  }

  openModal({
    title: "Nueva página",
    description: "Ponle un nombre y elige cómo empezar. Podrás cambiar cualquier botón después.",
    body: `
      <div class="dialog-field" style="margin-bottom: 16px;">
        <label for="new-page-name" class="section-label" style="margin: 0;">Nombre</label>
        <input type="text" id="new-page-name" maxlength="40" placeholder="Si lo dejas vacío usará el nombre de la plantilla">
      </div>
      <span class="section-label" style="margin-top: 0;">Empezar con</span>
      <div class="template-grid">
        ${templates.map(t => `
          <button class="template-card" data-template="${escapeHtml(t.id)}">
            <img src="${escapeHtml(t.icon)}" alt="">
            <strong>${escapeHtml(t.name)}</strong>
            <span>${escapeHtml(t.description)}</span>
          </button>`).join("")}
      </div>`,
    actions: [{ label: "Cancelar", kind: "secondary" }],
    onMount: (modal) => {
      modal.el.querySelectorAll("[data-template]").forEach(card => card.addEventListener("click", async () => {
        const template = templates.find(t => t.id === card.dataset.template);
        const name = modal.el.querySelector("#new-page-name").value.trim() || template.name;
        try {
          const result = await postJson("/api/templates/apply", { template_id: template.id, name });
          modal.close();
          await loadConfig();
          await switchPage(result.index);
          showToast(`Página "${name}" creada`);
        } catch (err) {
          showToast(err.message);
        }
      }));
    },
  });
}

// ---------- Page settings: name, program that opens it, duplicate ----------

function openPageSettings() {
  const page = config.pages[activePageIndex];
  const programs = [...new Set([...detectedSystemApps.map(a => a.exe_name), ...audioSessions.map(s => s.process_name)].filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  const servers = typeof discordSounds !== "undefined" && discordSounds ? [...new Set(discordSounds.map(s => s.section))] : [];
  openModal({
    title: "Ajustes de la página",
    body: `
      <div class="dialog-field" style="margin-bottom: 16px;">
        <label class="section-label" for="ps-name" style="margin: 0;">Nombre</label>
        <input type="text" id="ps-name" maxlength="40" value="${escapeHtml(page.name)}">
      </div>
      <div class="dialog-field">
        <label class="section-label" for="ps-app" style="margin: 0;">Abrir esta página sola cuando este programa esté en primer plano</label>
        <input type="text" id="ps-app" list="ps-programs" maxlength="128" value="${escapeHtml(page.auto_app || "")}" placeholder="Por ejemplo obs64.exe. Vacío para no usarlo.">
        <datalist id="ps-programs">${programs.map(p => `<option value="${escapeHtml(p)}"></option>`).join("")}</datalist>
        <p class="integration-hint">Es como los perfiles inteligentes de Stream Deck: al cambiar de programa en tu PC, el móvil salta a esta página. Si lo mueves tú a otra página, no te lo deshace hasta que cambies de programa.</p>
      </div>
      <div class="dialog-field" style="margin-top: 16px;">
        <label class="section-label" for="ps-discord" style="margin: 0;">Abrir esta página sola cuando estés en un canal de voz de este servidor de Discord</label>
        <input type="text" id="ps-discord" list="ps-servers" maxlength="80" value="${escapeHtml(page.auto_discord || "")}" placeholder="Nombre del servidor. Vacío para no usarlo.">
        <datalist id="ps-servers">${servers.map(name => `<option value="${escapeHtml(name)}"></option>`).join("")}</datalist>
        <p class="integration-hint">Escribe el nombre tal como lo ves en Discord (o busca tus sonidos en Conectores para que aparezcan aquí). Lo más fácil es crear la página desde la lista de sonidos de ese servidor.</p>
      </div>
      <div class="inline-row" style="margin-top: 16px;">
        <button class="btn-secondary" id="ps-duplicate">Duplicar página</button>
        <button class="btn-danger" id="ps-delete" style="width: auto; margin-top: 0;">Eliminar página</button>
      </div>`,
    actions: [
      { label: "Cancelar", kind: "secondary" },
      {
        label: "Guardar", kind: "primary",
        onClick: async (modal) => {
          const name = modal.el.querySelector("#ps-name").value.trim();
          const program = modal.el.querySelector("#ps-app").value.trim();
          const server = modal.el.querySelector("#ps-discord").value.trim();
          if (!name) return showToast("La página necesita un nombre");
          const serverClash = config.pages.find((p, i) => i !== activePageIndex && server && (p.auto_discord || "").toLowerCase() === server.toLowerCase());
          if (serverClash) return showToast(`"${serverClash.name}" ya se abre con ese servidor`);
          const clash = config.pages.find((p, i) => i !== activePageIndex && program && (p.auto_app || "").toLowerCase() === program.toLowerCase());
          if (clash) return showToast(`"${clash.name}" ya se abre con ese programa`);
          const before = { name: page.name, auto_app: page.auto_app, auto_discord: page.auto_discord };
          page.name = name;
          if (program) page.auto_app = program; else delete page.auto_app;
          if (server) page.auto_discord = server; else delete page.auto_discord;
          if (await saveConfigToServer({ immediate: true })) {
            renderPageTabs();
            modal.close();
            showToast("Página guardada");
          } else {
            // The server refused it. Do not keep the bad value, or every later autosave would fail too.
            page.name = before.name;
            if (before.auto_app) page.auto_app = before.auto_app; else delete page.auto_app;
            if (before.auto_discord) page.auto_discord = before.auto_discord; else delete page.auto_discord;
          }
        },
      },
    ],
    onMount: (modal) => {
      modal.el.querySelector("#ps-duplicate").addEventListener("click", async () => {
        try {
          const result = await postJson("/api/deck/page/duplicate", { page_index: activePageIndex });
          modal.close();
          await loadConfig();
          await switchPage(result.index);
          showToast("Página duplicada");
        } catch (err) {
          showToast(err.message);
        }
      });
      modal.el.querySelector("#ps-delete").addEventListener("click", () => {
        modal.close();
        document.getElementById("btn-delete-page")?.click();
      });
    },
  });
}

// ---------- Profile: save a copy, load a copy ----------

async function saveProfileCopy() {
  try {
    const { path } = await postJson("/api/profile/save-copy", {});
    showToast(`Copia guardada en ${path}`);
  } catch (err) {
    showToast(err.message);
  }
}

async function loadProfileCopy(file) {
  let profile;
  try {
    profile = JSON.parse(await file.text());
  } catch (e) {
    return showToast("Ese archivo no es un perfil de StreamDesk");
  }
  const confirmed = await askConfirm({
    title: "Cargar este perfil",
    message: `Se reemplazarán todas tus páginas y botones por los de "${file.name}". Antes se guarda una copia de los actuales.`,
    confirmLabel: "Cargar perfil", danger: true,
  });
  if (!confirmed) return;
  try {
    const result = await postJson("/api/profile/import", profile);
    await loadConfig();
    await switchPage(0);
    showToast(`Perfil cargado: ${result.pages} páginas`);
  } catch (err) {
    showToast(err.message);
  }
}

// ---------- Theme ----------

function applyTheme(theme) {
  if (!THEMES.some(t => t.id === theme)) return;
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("streamdesk_theme", theme); } catch (e) {}
}

async function loadTheme() {
  try {
    applyTheme((await apiJson("/api/ui")).theme);
  } catch (e) { /* keep the theme from localStorage */ }
}

// ---------- Settings ----------

function openSettings() {
  const currentTheme = document.documentElement.dataset.theme;
  const modal = openModal({
    title: "Ajustes",
    body: `
      <section class="settings-section">
        <h3>Apariencia</h3>
        <p>Se aplica también en tu móvil.</p>
        <div class="theme-options">
          ${THEMES.map(t => `
            <button class="theme-option ${t.id === currentTheme ? "active" : ""}" data-theme-id="${t.id}">
              <span class="theme-swatches">${t.swatches.map(c => `<i style="background: ${c};"></i>`).join("")}</span>
              <strong>${escapeHtml(t.name)}</strong>
            </button>`).join("")}
        </div>
      </section>
      <section class="settings-section">
        <h3>Móviles emparejados</h3>
        <p>Cada móvil que introdujo tu PIN queda aquí. Quita los que ya no uses.</p>
        <div id="settings-devices"><span class="integration-hint">Cargando...</span></div>
      </section>
      <section class="settings-section">
        <h3>Perfil</h3>
        <p>Guarda una copia de todas tus páginas y botones, o carga una en este u otro PC. No incluye contraseñas ni móviles emparejados, ni las imágenes que hayas subido.</p>
        <div class="inline-row">
          <button class="btn-secondary" id="settings-export">Guardar una copia</button>
          <button class="btn-secondary" id="settings-import">Cargar una copia</button>
        </div>
        <input type="file" id="settings-import-file" accept="application/json,.json" hidden>
      </section>
      <section class="settings-section">
        <h3>Conexión del móvil</h3>
        <p>Lo último que ha intentado un móvil. Si algo falla, aquí se ve en qué punto.</p>
        <div id="settings-diagnostics"><span class="integration-hint">Cargando...</span></div>
      </section>
      <section class="settings-section">
        <h3>Versión</h3>
        <p id="settings-version">Comprobando...</p>
        <button class="btn-secondary" id="settings-check-update">Buscar actualizaciones</button>
      </section>
      <section class="settings-section">
        <h3>Primeros pasos</h3>
        <p>¿Quieres volver a ver la guía de bienvenida?</p>
        <button class="btn-secondary" id="settings-welcome">Ver la guía</button>
      </section>`,
    actions: [{ label: "Cerrar", kind: "primary" }],
    onMount: (m) => {
      m.el.querySelectorAll("[data-theme-id]").forEach(option => option.addEventListener("click", async () => {
        applyTheme(option.dataset.themeId);
        m.el.querySelectorAll("[data-theme-id]").forEach(o => o.classList.toggle("active", o === option));
        try { await postJson("/api/ui", { theme: option.dataset.themeId }); } catch (err) { showToast(err.message); }
      }));
      m.el.querySelector("#settings-welcome").addEventListener("click", () => { m.close(); openWelcome(); });
      m.el.querySelector("#settings-check-update").addEventListener("click", async () => {
        await checkGitHubUpdates();
        m.el.querySelector("#settings-version").textContent = updateStatusText.textContent;
      });
      m.el.querySelector("#settings-version").textContent = updateStatusText.textContent;
      m.el.querySelector("#settings-export").addEventListener("click", saveProfileCopy);
      const importInput = m.el.querySelector("#settings-import-file");
      m.el.querySelector("#settings-import").addEventListener("click", () => importInput.click());
      importInput.addEventListener("change", () => {
        const file = importInput.files[0];
        if (file) { m.close(); loadProfileCopy(file); }
      });
      renderSettingsDevices(m.el.querySelector("#settings-devices"));
      renderSettingsDiagnostics(m.el.querySelector("#settings-diagnostics"));
    },
  });
  return modal;
}

async function renderSettingsDevices(container) {
  try {
    const { devices } = await apiJson("/api/auth/devices");
    if (!devices.length) {
      container.innerHTML = `<span class="integration-hint">Todavía no hay ningún móvil emparejado. Escanea el QR del panel lateral.</span>`;
      return;
    }
    container.innerHTML = devices.map(d => `
      <div class="device-row">
        <div><strong>${escapeHtml(d.name)}</strong><span>Emparejado el ${escapeHtml(d.created_at)}</span></div>
        <button class="btn-secondary" data-revoke="${escapeHtml(d.id)}">Quitar</button>
      </div>`).join("");
    container.querySelectorAll("[data-revoke]").forEach(button => button.addEventListener("click", async () => {
      const device = devices.find(d => d.id === button.dataset.revoke);
      const confirmed = await askConfirm({
        title: "Quitar móvil",
        message: `"${device.name}" dejará de poder controlar tu PC hasta que vuelva a introducir un PIN.`,
        confirmLabel: "Quitar", danger: true,
      });
      if (!confirmed) return;
      try {
        await postJson("/api/auth/devices/revoke", { id: device.id });
        showToast("Móvil quitado");
        renderSettingsDevices(container);
      } catch (err) {
        showToast(err.message);
      }
    }));
  } catch (err) {
    container.innerHTML = `<span class="integration-hint">${escapeHtml(err.message)}</span>`;
  }
}

async function renderSettingsDiagnostics(container) {
  try {
    const { events } = await apiJson("/api/diagnostics");
    if (!events.length) {
      container.innerHTML = `<span class="integration-hint">Todavía no ha intentado conectarse ningún móvil.</span>`;
      return;
    }
    container.innerHTML = events.slice(0, 8).map(e => `
      <div class="device-row">
        <div><strong>${escapeHtml(e.message)}</strong><span>${escapeHtml(e.time)} · ${escapeHtml(e.device)} · ${escapeHtml(e.ip)}</span></div>
      </div>`).join("");
  } catch (err) {
    container.innerHTML = `<span class="integration-hint">${escapeHtml(err.message)}</span>`;
  }
}

// ---------- Welcome ----------

function openWelcome() {
  const modal = openModal({
    title: "Bienvenido a StreamDesk",
    description: "Convierte tu móvil en un panel de control de tu PC en tres pasos.",
    body: `
      <ol class="steps-list">
        <li><strong>Enlaza tu móvil.</strong> Escanea el código QR del panel lateral con la cámara y escribe el PIN.</li>
        <li><strong>Elige un punto de partida.</strong> Una plantilla (Streamer, Gamer, Trabajo) te da una página lista para usar.</li>
        <li><strong>Ajusta lo que quieras.</strong> Pulsa una casilla para cambiar su acción, conectar OBS, Spotify o Discord, o cambiar su aspecto.</li>
      </ol>`,
    actions: [
      { label: "Empezar sin plantilla", kind: "secondary" },
      { label: "Elegir una plantilla", kind: "primary", onClick: (m) => { m.close(); openNewPageDialog(); } },
    ],
  });
  modal.onClose = () => { try { localStorage.setItem("streamdesk_welcome", "1"); } catch (e) {} };
  return modal;
}

function maybeShowWelcome() {
  let seen = false;
  try { seen = localStorage.getItem("streamdesk_welcome") === "1"; } catch (e) {}
  if (!seen) openWelcome();
}

// ---------- Windows firewall: let the phone in ----------

async function refreshFirewall() {
  try {
    const { allowed } = await apiJson("/api/system/firewall");
    document.getElementById("firewall-note").hidden = allowed;
    return allowed;
  } catch (e) {
    return true; // cannot tell: do not nag
  }
}

async function allowPhoneThroughFirewall() {
  const button = document.getElementById("btn-allow-firewall");
  button.disabled = true;
  try {
    const result = await postJson("/api/system/firewall/allow", {});
    if (result.error) return showToast(result.error);
    if (!result.already) showToast("Windows te pedirá permiso: elige Sí.");
    // The prompt is answered outside the app, so look for the rule until it appears.
    for (let attempt = 0; attempt < 30; attempt++) {
      if (await refreshFirewall()) return showToast("Listo: tu móvil ya puede conectarse.");
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  } catch (err) {
    showToast(err.message);
  } finally {
    button.disabled = false;
  }
}

// The QR panel is only needed until a phone is paired; folding it gives the action library the room.
// It stays open while the firewall warning is showing, because that is the thing to act on.
async function collapsePairingWhenDone() {
  try {
    const { devices } = await apiJson("/api/auth/devices");
    if (devices.length && document.getElementById("firewall-note").hidden) {
      document.getElementById("pairing-panel").open = false;
    }
  } catch (e) { /* leave it open */ }
}

// ---------- Startup ----------

window.addEventListener("DOMContentLoaded", () => {
  loadTheme();
  document.getElementById("btn-settings")?.addEventListener("click", openSettings);
  document.getElementById("btn-page-settings")?.addEventListener("click", openPageSettings);
  document.getElementById("btn-allow-firewall")?.addEventListener("click", allowPhoneThroughFirewall);
  refreshFirewall().then(collapsePairingWhenDone);
  setInterval(refreshFirewall, 20000);
  setTimeout(maybeShowWelcome, 700);
});
