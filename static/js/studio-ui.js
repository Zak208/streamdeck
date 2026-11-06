// Studio dialogs: new page from a template, settings and the welcome guide.
// Loaded after studio.js, whose globals (config, loadConfig, switchPage, showToast...) it uses.

const THEMES = [
  { id: "ctma", name: "Negro y amarillo", swatches: ["#0a0a0a", "#555555", "#ffffff", "#f8c700"] },
  { id: "cian", name: "Azul noche y cian", swatches: ["#080a10", "#41536a", "#f4f7fb", "#38bdf8"] },
  { id: "violeta", name: "Noche y violeta", swatches: ["#0b0912", "#4f4478", "#f6f3ff", "#a78bfa"] },
  { id: "verde", name: "Bosque y verde", swatches: ["#08100c", "#3f6652", "#f1faf5", "#22c55e"] },
  { id: "rojo", name: "Carbón y rojo", swatches: ["#100808", "#6e3a3a", "#fdf3f3", "#ef4444"] },
  { id: "rosa", name: "Ciruela y rosa", swatches: ["#120912", "#744478", "#fff3fb", "#ec4899"] },
  { id: "naranja", name: "Café y naranja", swatches: ["#100b06", "#6e4d2a", "#fff7ee", "#f97316"] },
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
  openModal({
    title: "Nueva página",
    description: "Ponle un nombre y empieza en blanco, o abre la biblioteca, que tiene decenas de páginas ya montadas.",
    body: `
      <div class="dialog-field" style="margin-bottom: 16px;">
        <label for="new-page-name" class="section-label" style="margin: 0;">Nombre (opcional)</label>
        <input type="text" id="new-page-name" maxlength="40" placeholder="Por ejemplo: Directo">
      </div>
      <div class="new-page-choices">
        <button type="button" class="template-card" id="new-page-blank">
          <span class="template-card-head"><img src="/static/icons/plus.svg" alt=""><strong>En blanco</strong></span>
          <span class="template-desc">Una página vacía con el volumen de Windows, para montarla a tu manera.</span>
        </button>
        <a class="template-card" id="new-page-library" href="/library">
          <span class="template-card-head"><img src="/static/icons/folder.svg" alt=""><strong>Abrir la biblioteca</strong></span>
          <span class="template-desc">Spotify, OBS, Discord, Excel, Premiere, atajos de Windows y muchas más, cada una con su propio tamaño.</span>
        </a>
      </div>`,
    actions: [{ label: "Cancelar", kind: "secondary" }],
    onMount: (modal) => {
      modal.el.querySelector("#new-page-blank").addEventListener("click", async () => {
        const name = modal.el.querySelector("#new-page-name").value.trim() || "Página nueva";
        try {
          await flushSave();
          const result = await postJson("/api/templates/apply", { template_id: "blank", name });
          modal.close();
          await loadConfig();
          await switchPage(result.index);
          showToast(`Página "${name}" creada`);
        } catch (err) {
          showToast(err.message);
        }
      });
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
          await flushSave();
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

// How many actions of a profile file act on the PC itself (keys, typed text, folders), looking inside
// macros and long-press / double-tap actions. A profile from someone else could use them to run things.
function riskyActionsIn(profile) {
  const risky = new Set(["hotkey", "text", "folder", "command", "webhook", "url", "steam"]);
  const isRisky = (action) => risky.has(action.action_type) || (action.action_type === "windows" && ["power", "power_plan", "display_mode"].includes(action.target));
  const count = (action) => {
    if (!action || typeof action !== "object") return 0;
    let total = isRisky(action) ? 1 : 0;
    for (const step of Array.isArray(action.extra?.actions) ? action.extra.actions : []) total += count(step);
    return total;
  };
  let total = 0;
  for (const page of Array.isArray(profile?.pages) ? profile.pages : []) {
    for (const slot of Array.isArray(page?.slots) ? page.slots : []) {
      // The key itself, its gestures, and what its second state does.
      total += count(slot) + count(slot?.long_press) + count(slot?.double_tap) + count(slot?.alt?.action);
    }
  }
  return total;
}

async function loadProfileCopy(file) {
  let profile;
  try {
    profile = JSON.parse(await file.text());
  } catch (e) {
    return showToast("Ese archivo no es un perfil de StreamDesk");
  }
  const risky = riskyActionsIn(profile);
  const warning = risky ? ` ATENCIÓN: contiene ${risky} acciones que pulsan teclas, escriben texto (teclas y texto bastan para abrir y ejecutar programas), abren webs y carpetas, llaman a webhooks, apagan o reinician el PC o ejecutan comandos, y funcionarán en tu PC cuando se pulsen desde el móvil. Cárgalo solo si confías en quien te lo dio.` : "";
  const confirmed = await askConfirm({
    title: "Cargar este perfil",
    message: `Se reemplazarán todas tus páginas y botones por los de "${file.name}". Antes se guarda una copia de los actuales.${warning}`,
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

// ---------- Deck size ----------

// Name is "columns x rows", as the server calls them.
const GRID_PRESETS = [
  { id: "6x2", columns: 6, rows: 2 },
  { id: "5x3", columns: 5, rows: 3 },
  { id: "4x3", columns: 4, rows: 3 },
  { id: "3x3", columns: 3, rows: 3 },
  { id: "4x2", columns: 4, rows: 2 },
];

function gridPresetLabel(p) {
  return `${p.columns} columnas x ${p.rows} filas (${p.columns * p.rows})`;
}

// Limits of a custom size; the server sends the real ones with GET /api/layouts.
let gridLimits = { min_columns: 2, max_columns: 10, min_rows: 2, max_rows: 8, max_total: 64 };

// The size controls work on one page (`pageIndex`) or, with null, on every page and on the size new pages start with.
function sizeNow(pageIndex) {
  if (pageIndex === null || pageIndex === undefined) return config?.default_layout || config?.layout || { columns: 6, rows: 2 };
  return pageLayout(pageIndex) || { columns: 6, rows: 2 };
}

// `spec` is a preset name ("6x2") or { columns, rows }. `restore` puts the controls back if nothing changes.
async function changeGridLayout(spec, restore, pageIndex = null) {
  const now = sizeNow(pageIndex);
  const current = `${now.columns}x${now.rows}`;
  const body = typeof spec === "string" ? { layout: spec } : { columns: spec.columns, rows: spec.rows };
  if (pageIndex !== null) body.page = pageIndex;
  const wanted = typeof spec === "string" ? spec : `${spec.columns}x${spec.rows}`;
  if (wanted === current) return restore?.();
  const confirmed = await askConfirm({
    title: pageIndex === null ? "Cambiar la cuadrícula de todas las páginas" : "Cambiar el tamaño de esta página",
    message: "Cada botón conserva su fila y columna si existen en la nueva cuadrícula; si no, pasa a la primera casilla libre. Los faders conservan su alto, y si pierden su columna pasan a las de más a la derecha. Se guarda una copia del perfil anterior.",
    confirmLabel: "Cambiar",
  });
  if (!confirmed) return restore?.();
  try {
    await flushSave();
    const result = await postJson("/api/layout", body);
    const keepPage = activePageIndex;
    config = result.config;
    activePageIndex = pageIndex === null ? Math.min(config.current_page || 0, (config.pages || []).length - 1) : Math.min(keepPage, (config.pages || []).length - 1);
    selectedSlotIndex = null;
    renderPageTabs();
    renderPhoneScreen();
    resetInspectorDrawer();
    showToast(result.dropped > 0
      ? `Cuadrícula cambiada. ${result.dropped} elemento${result.dropped === 1 ? "" : "s"} no cabía${result.dropped === 1 ? "" : "n"} y se ${result.dropped === 1 ? "quitó" : "quitaron"}. Tienes una copia del perfil anterior`
      : "Cuadrícula cambiada");
    restore?.();
  } catch (err) {
    restore?.();
    showToast(err.message);
  }
}

// The size controls of Ajustes: the presets, plus any columns x rows within the limits.
function wireGridControls(root, pageIndex = null) {
  const select = root.querySelector("#settings-grid");
  const columns = root.querySelector("#grid-cols");
  const rows = root.querySelector("#grid-rows");
  const apply = root.querySelector("#grid-apply");
  const hint = root.querySelector("#grid-hint");
  const customOption = `<option value="custom">Personalizada</option>`;

  const sync = () => {
    const now = sizeNow(pageIndex);
    const current = `${now.columns}x${now.rows}`;
    columns.value = now.columns;
    rows.value = now.rows;
    select.value = [...select.options].some(o => o.value === current) ? current : "custom";
    check();
  };
  const check = () => {
    const c = Number(columns.value), r = Number(rows.value);
    const L = gridLimits;
    let problem = "";
    if (!Number.isInteger(c) || c < L.min_columns || c > L.max_columns) problem = `Columnas: entre ${L.min_columns} y ${L.max_columns}.`;
    else if (!Number.isInteger(r) || r < L.min_rows || r > L.max_rows) problem = `Filas: entre ${L.min_rows} y ${L.max_rows}.`;
    else if (c * r > L.max_total) problem = `Como mucho ${L.max_total} casillas en total.`;
    hint.textContent = problem || `${c} columnas x ${r} filas = ${c * r} casillas`;
    hint.classList.toggle("command-warning", Boolean(problem));
    const now = sizeNow(pageIndex);
    apply.disabled = Boolean(problem) || `${c}x${r}` === `${now.columns}x${now.rows}`;
  };
  columns.addEventListener("input", check);
  rows.addEventListener("input", check);
  select.addEventListener("change", () => {
    if (select.value === "custom") return columns.focus();
    changeGridLayout(select.value, sync, pageIndex);
  });
  apply.addEventListener("click", () => changeGridLayout({ columns: Number(columns.value), rows: Number(rows.value) }, sync, pageIndex));

  // Presets and limits come from the server; the built-in list is the fallback when it does not answer.
  apiJson("/api/layouts").then(data => {
    if (data.limits) gridLimits = data.limits;
    columns.min = gridLimits.min_columns; columns.max = gridLimits.max_columns;
    rows.min = gridLimits.min_rows; rows.max = gridLimits.max_rows;
    const presets = (data.presets || []).map(p => ({ id: p.id, columns: p.columns, rows: p.rows }));
    if (presets.length) select.innerHTML = presets.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(gridPresetLabel(p))}</option>`).join("") + customOption;
    sync();
  }).catch(() => sync());
  sync();
}

// The size button above the preview: shows the current grid and opens the same controls as Ajustes.
function updateGridChip() {
  const chip = document.getElementById("grid-chip-text");
  if (chip) chip.textContent = `${gridCols()}x${gridRows()} · ${gridTotal()} casillas`;
}

function gridControlsMarkup(pageIndex = null) {
  const now = sizeNow(pageIndex);
  return `
    <p class="modal-desc">${pageIndex === null
      ? "Cuántos botones caben en cada página, en el móvil y aquí. Al cambiarla se convierten todas tus páginas y las páginas nuevas empiezan con este tamaño."
      : "Cuántos botones caben en esta página, en el móvil y aquí. Las demás páginas no cambian."}</p>
    <select id="settings-grid" aria-label="Tamaño de la cuadrícula">
      ${GRID_PRESETS.map(p => `<option value="${p.id}" ${p.id === `${now.columns}x${now.rows}` ? "selected" : ""}>${gridPresetLabel(p)}</option>`).join("")}
      <option value="custom">Personalizada</option>
    </select>
    <div class="grid-custom">
      <label>Columnas <input type="number" id="grid-cols" min="2" max="10" step="1" inputmode="numeric"></label>
      <label>Filas <input type="number" id="grid-rows" min="2" max="8" step="1" inputmode="numeric"></label>
      <button class="btn-secondary" id="grid-apply" type="button">Aplicar</button>
    </div>
    <p class="integration-hint" id="grid-hint"></p>`;
}

function openGridDialog() {
  const pageIndex = activePageIndex; // the button above the preview resizes the page you are looking at
  const modal = openModal({
    title: `Tamaño de «${config.pages[pageIndex]?.name || "esta página"}»`,
    body: gridControlsMarkup(pageIndex),
    actions: [{ label: "Cerrar", kind: "primary" }],
    onMount: (m) => wireGridControls(m.el, pageIndex),
  });
  return modal;
}
document.getElementById("btn-grid-open")?.addEventListener("click", openGridDialog);
updateGridChip();

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
        <h3>Cuadrícula de todas las páginas</h3>
        <p>Cuántos botones caben en cada página, en el móvil y aquí. Al cambiarla se convierten todas tus páginas: los botones que caben se quedan donde están y los faders conservan su alto desde la primera fila de su columna.</p>
        <select id="settings-grid" aria-label="Tamaño de la cuadrícula">
          ${GRID_PRESETS.map(p => `<option value="${p.id}" ${p.id === `${gridCols()}x${gridRows()}` ? "selected" : ""}>${gridPresetLabel(p)}</option>`).join("")}
          <option value="custom">Personalizada</option>
        </select>
        <div class="grid-custom">
          <label>Columnas <input type="number" id="grid-cols" min="2" max="10" step="1" inputmode="numeric"></label>
          <label>Filas <input type="number" id="grid-rows" min="2" max="8" step="1" inputmode="numeric"></label>
          <button class="btn-secondary" id="grid-apply" type="button">Aplicar</button>
        </div>
        <p class="integration-hint" id="grid-hint"></p>
      </section>
      <section class="settings-section">
        <h3>Comandos de consola</h3>
        <p>Los botones de PowerShell o cmd solo funcionan si lo permites aquí. Está desactivado por defecto.</p>
        ${commandsSwitchHtml("settings")}
      </section>
      <section class="settings-section">
        <h3>Apagar y reiniciar el PC</h3>
        <p>Los botones de apagar, reiniciar, suspender y cerrar sesión solo funcionan si lo permites aquí. Está desactivado por defecto.</p>
        ${powerSwitchHtml()}
      </section>
      <section class="settings-section">
        <h3>Webhooks permitidos</h3>
        <p>Un botón de webhook solo puede llamar a los destinos de esta lista (por ejemplo <code>192.168.1.20:8123</code>). Está vacía por defecto, porque un perfil que te pase otra persona podría llamar a lo que quisiera.</p>
        <div id="webhook-hosts"><span class="integration-hint">Cargando...</span></div>
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
        <div class="inline-row">
          <button class="btn-secondary" id="settings-check-update">Buscar actualizaciones</button>
          <button class="btn-primary" id="settings-apply-update" hidden>Actualizar</button>
        </div>
      </section>
      <section class="settings-section">
        <h3>Primeros pasos y Novedades</h3>
        <p>¿Quieres volver a ver la guía de bienvenida o las novedades de esta versión?</p>
        <div class="inline-row">
          <button class="btn-secondary" id="settings-welcome">Guía de bienvenida</button>
          <button class="btn-secondary" id="settings-tour">Novedades de la versión</button>
        </div>
      </section>`,
    actions: [{ label: "Cerrar", kind: "primary" }],
    onMount: (m) => {
      m.el.querySelectorAll("[data-theme-id]").forEach(option => option.addEventListener("click", async () => {
        applyTheme(option.dataset.themeId);
        m.el.querySelectorAll("[data-theme-id]").forEach(o => o.classList.toggle("active", o === option));
        try { await postJson("/api/ui", { theme: option.dataset.themeId }); } catch (err) { showToast(err.message); }
      }));
      wireGridControls(m.el);
      wireCommandsSwitch(m.el);
      wirePowerSwitch(m.el);
      wireWebhookList(m.el);
      m.el.querySelector("#settings-welcome")?.addEventListener("click", () => { m.close(); openWelcome(); });
      m.el.querySelector("#settings-tour")?.addEventListener("click", async () => {
        m.close();
        try {
          const data = await apiJson("/api/system/onboarding");
          openUpdateTour(data.tour);
        } catch (e) {
          showToast("No se pudieron cargar las novedades");
        }
      });
      const showVersion = () => {
        m.el.querySelector("#settings-version").textContent = updateStatusText.textContent;
        const ready = updateCylinder.classList.contains("update-ready");
        const apply = m.el.querySelector("#settings-apply-update");
        apply.hidden = !ready;
        apply.textContent = btnApplyUpdate.textContent || "Actualizar";
      };
      m.el.querySelector("#settings-check-update").addEventListener("click", async () => {
        await checkGitHubUpdates();
        showVersion();
      });
      m.el.querySelector("#settings-apply-update").addEventListener("click", () => { m.close(); btnApplyUpdate.click(); });
      showVersion();
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

// ---------- Welcome & Update Tour ----------

function openWelcome() {
  const markWelcomeCompleted = () => {
    try {
      localStorage.setItem("streamdesk_first_run_completed", "1");
      localStorage.setItem("streamdesk_welcome", "1");
    } catch (e) {}
    postJson("/api/system/onboarding/complete", { action: "welcome" }).catch(() => {});
  };

  const modal = openModal({
    title: "Bienvenido a StreamDesk",
    description: "Convierte tu móvil en un panel de control de tu PC en tres pasos.",
    body: `
      <ol class="steps-list">
        <li><strong>Enlaza tu móvil.</strong> Escanea el código QR del panel lateral con la cámara y escribe el PIN.</li>
        <li><strong>Elige un punto de partida.</strong> La biblioteca tiene decenas de páginas ya montadas (Streamer, Spotify, OBS, Excel...) para añadir con un clic.</li>
        <li><strong>Ajusta lo que quieras.</strong> Pulsa una casilla para cambiar su acción, conectar OBS, Spotify o Discord, o cambiar su aspecto.</li>
      </ol>`,
    actions: [
      {
        label: "Empezar sin plantilla",
        kind: "secondary",
        onClick: (m) => {
          markWelcomeCompleted();
          m.close();
        }
      },
      {
        label: "Abrir la biblioteca",
        kind: "primary",
        onClick: (m) => {
          markWelcomeCompleted();
          m.close();
          location.href = "/library";
        }
      },
    ],
  });
  modal.onClose = () => {
    markWelcomeCompleted();
  };
  return modal;
}

function openUpdateTour(tourData) {
  const steps = tourData?.steps || [];
  if (!steps.length) return null;

  let currentStep = 0;

  const markCompleted = () => {
    try {
      localStorage.setItem("streamdesk_first_run_completed", "1");
      localStorage.setItem("streamdesk_last_seen_version", tourData.version || "");
    } catch (e) {}
    postJson("/api/system/onboarding/complete", { action: "update_tour", version: tourData.version }).catch(() => {});
  };

  const renderStep = (modalEl, index) => {
    const step = steps[index];
    const total = steps.length;
    
    const tagEl = modalEl.querySelector(".tour-tag");
    const indicatorEl = modalEl.querySelector(".tour-indicator-text");
    const titleEl = modalEl.querySelector(".tour-step-title");
    const descEl = modalEl.querySelector(".tour-step-desc");
    const dotsEl = modalEl.querySelector(".tour-dots");
    const btnPrev = modalEl.querySelector("#tour-btn-prev");
    const btnNext = modalEl.querySelector("#tour-btn-next");

    if (tagEl) tagEl.textContent = step.tag || `Paso ${index + 1}`;
    if (indicatorEl) indicatorEl.textContent = `${index + 1} de ${total}`;
    if (titleEl) titleEl.textContent = step.title;
    if (descEl) descEl.textContent = step.description;

    if (dotsEl) {
      dotsEl.innerHTML = steps.map((_, i) => 
        `<span class="tour-dot ${i === index ? 'active' : ''}" data-step="${i}" title="${escapeHtml(steps[i].title)}"></span>`
      ).join("");
      dotsEl.querySelectorAll(".tour-dot").forEach(dot => {
        dot.addEventListener("click", () => {
          currentStep = parseInt(dot.dataset.step, 10);
          renderStep(modalEl, currentStep);
        });
      });
    }

    if (btnPrev) {
      btnPrev.disabled = index === 0;
      btnPrev.style.visibility = index === 0 ? "hidden" : "visible";
    }

    if (btnNext) {
      btnNext.textContent = (index === total - 1) ? "¡Entendido, empezar!" : "Siguiente";
    }
  };

  const modal = openModal({
    title: tourData.title || `Novedades de StreamDesk v${tourData.version}`,
    description: "Estas son las mejoras y novedades destacadas de esta actualización:",
    body: `
      <div class="tour-card-body">
        <div class="tour-header-meta">
          <span class="tour-tag"></span>
          <span class="tour-indicator-text"></span>
        </div>
        <h3 class="tour-step-title"></h3>
        <p class="tour-step-desc"></p>
        <div class="tour-dots-wrapper">
          <div class="tour-dots"></div>
        </div>
      </div>
    `,
    actions: [
      {
        label: "Saltar tour",
        kind: "secondary",
        onClick: (m) => {
          markCompleted();
          m.close();
        }
      },
      {
        label: "Anterior",
        kind: "secondary",
        onClick: (m) => {
          if (currentStep > 0) {
            currentStep--;
            renderStep(m.el, currentStep);
          }
        }
      },
      {
        label: "Siguiente",
        kind: "primary",
        onClick: (m) => {
          if (currentStep < steps.length - 1) {
            currentStep++;
            renderStep(m.el, currentStep);
          } else {
            markCompleted();
            m.close();
          }
        }
      }
    ],
    onMount: (m) => {
      const buttons = m.el.querySelectorAll(".modal-actions button");
      if (buttons[0]) buttons[0].id = "tour-btn-skip";
      if (buttons[1]) buttons[1].id = "tour-btn-prev";
      if (buttons[2]) buttons[2].id = "tour-btn-next";

      renderStep(m.el, currentStep);
    }
  });

  modal.onClose = () => {
    markCompleted();
  };

  return modal;
}

async function maybeCheckOnboarding() {
  try {
    const data = await apiJson("/api/system/onboarding");
    let localSeenVersion = "";
    let localFirstRun = false;
    try {
      localSeenVersion = localStorage.getItem("streamdesk_last_seen_version") || "";
      localFirstRun = localStorage.getItem("streamdesk_first_run_completed") === "1" || localStorage.getItem("streamdesk_welcome") === "1";
    } catch (e) {}

    // 1. First time ever opening app
    if (data.show_welcome && !localFirstRun) {
      openWelcome();
      return;
    }

    // 2. Right after an update
    if ((data.show_update_tour || localFirstRun) && localSeenVersion !== data.version) {
      openUpdateTour(data.tour);
      return;
    }
  } catch (e) {
    try {
      const seen = localStorage.getItem("streamdesk_welcome") === "1";
      if (!seen) openWelcome();
    } catch (err) {}
  }
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
  setTimeout(maybeCheckOnboarding, 700);
});

// ---------- Right panel width: drag its edge, or use the expand button; the choice is remembered ----------

const INSPECTOR_KEY = "streamdesk_inspector_width";
const INSPECTOR_MIN = 340;
const INSPECTOR_WIDE = 680;

function inspectorLimits() {
  return { min: INSPECTOR_MIN, max: Math.max(INSPECTOR_MIN, Math.min(960, Math.round(window.innerWidth * 0.62))) };
}

function currentInspectorWidth() {
  return Math.round(document.getElementById("editor-drawer")?.getBoundingClientRect().width || 0);
}

// `width` of null goes back to the stylesheet's own width.
function setInspectorWidth(width, { save = true } = {}) {
  const root = document.documentElement;
  if (width === null) {
    root.style.removeProperty("--inspector-width");
    if (save) { try { localStorage.removeItem(INSPECTOR_KEY); } catch (e) { /* private window: just not remembered */ } }
  } else {
    const { min, max } = inspectorLimits();
    const clamped = Math.max(min, Math.min(max, Math.round(width)));
    root.style.setProperty("--inspector-width", `${clamped}px`);
    if (save) { try { localStorage.setItem(INSPECTOR_KEY, String(clamped)); } catch (e) { /* idem */ } }
  }
  const button = document.getElementById("inspector-expand");
  if (button) button.textContent = currentInspectorWidth() >= 560 ? "⤡" : "⤢";
}

function initInspectorResize() {
  const handle = document.getElementById("inspector-resizer");
  const expand = document.getElementById("inspector-expand");
  if (!handle || !expand) return;
  try {
    const saved = Number(localStorage.getItem(INSPECTOR_KEY));
    if (saved) setInspectorWidth(saved, { save: false });
  } catch (e) { /* nothing remembered */ }

  handle.addEventListener("pointerdown", (event) => {
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
    document.body.classList.add("resizing-inspector");
  });
  handle.addEventListener("pointermove", (event) => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    setInspectorWidth(window.innerWidth - event.clientX, { save: false }); // the panel sits against the right edge
  });
  const finish = (event) => {
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
    handle.classList.remove("dragging");
    document.body.classList.remove("resizing-inspector");
    setInspectorWidth(currentInspectorWidth());
  };
  handle.addEventListener("pointerup", finish);
  handle.addEventListener("pointercancel", finish);
  handle.addEventListener("dblclick", () => setInspectorWidth(null));
  handle.addEventListener("keydown", (event) => {
    const step = event.shiftKey ? 80 : 24;
    if (event.key === "ArrowLeft") setInspectorWidth(currentInspectorWidth() + step);
    else if (event.key === "ArrowRight") setInspectorWidth(currentInspectorWidth() - step);
    else if (event.key === "Home") setInspectorWidth(null);
    else return;
    event.preventDefault();
  });
  expand.addEventListener("click", () => setInspectorWidth(currentInspectorWidth() >= 560 ? null : INSPECTOR_WIDE));
  window.addEventListener("resize", () => {
    const { max } = inspectorLimits();
    if (currentInspectorWidth() > max) setInspectorWidth(max, { save: false });
  });
}

document.addEventListener("DOMContentLoaded", initInspectorResize);
