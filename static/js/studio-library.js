// Action library and action editor, modelled on Elgato's Stream Deck: a searchable library of
// actions you drag onto a key, and an editor for what the selected key does (hotkey, text, web,
// page jump, multi-action). Loaded after studio.js, whose globals it uses.

const LIBRARY_ACCENT = "#f8c700";

// A shortcut of a program. It goes to whatever window has the focus, so that program has to be in front
// (the category name says so in Studio).
function appKey(id, label, sub, keys, icon) {
  return { id, label, sub, icon: `/static/icons/${icon}.svg`, color: LIBRARY_ACCENT, action_type: "hotkey", target: keys };
}

// Built-in actions. Those of OBS, Windows and Discord come from the connectors (see loadLibrary).
function builtInLibrary() {
  const media = MEDIA_PRESETS.map(p => ({
    id: `media_${p.id}`, label: p.name, sub: "Multimedia", icon: p.icon, color: p.color, action_type: "media", target: p.target,
  }));
  const monitors = TELEMETRY_PRESETS.filter(p => p.target !== "taskmgr").map(p => ({
    id: `monitor_${p.id}`, label: p.name.replace("Monitor ", ""), sub: p.sub, icon: p.icon, color: p.color,
    action_type: "hardware_monitor", target: p.target,
  }));
  return [
    { category: "Sistema", items: [
      { id: "hotkey", label: "Atajo de teclado", sub: "Pulsa una combinación", icon: "/static/icons/keyboard.svg", color: LIBRARY_ACCENT, action_type: "hotkey", target: "CTRL+SHIFT+M", configure: true },
      { id: "text", label: "Escribir texto", sub: "Teclea un texto por ti", icon: "/static/icons/notes.svg", color: LIBRARY_ACCENT, action_type: "text", target: "Hola", extra: { press_enter: false }, configure: true },
      { id: "website", label: "Abrir una web", sub: "En tu navegador", icon: "/static/icons/link.svg", color: LIBRARY_ACCENT, action_type: "url", target: "https://www.example.com", configure: true },
      { id: "folder", label: "Abrir una carpeta", sub: "En el Explorador", icon: "/static/icons/folder.svg", color: LIBRARY_ACCENT, action_type: "folder", target: "C:\\Users", configure: true },
      { id: "macro", label: "Multiacción", sub: "Varias acciones en una", icon: "/static/icons/macro.svg", color: "#a855f7", action_type: "multi", target: "macro", extra: { actions: [{ action_type: "sound", target: "beep", delay_ms: 150 }] }, configure: true },
      { id: "taskmgr", label: "Administrador de tareas", sub: "Abrir", icon: "/static/icons/sliders.svg", color: LIBRARY_ACCENT, action_type: "preset_app", target: "taskmgr" },
    ] },
    { category: "Páginas", items: [
      { id: "page_next", label: "Página siguiente", sub: "Navegación", icon: "/static/icons/chevron_right.svg", color: LIBRARY_ACCENT, action_type: "page", target: "next" },
      { id: "page_prev", label: "Página anterior", sub: "Navegación", icon: "/static/icons/chevron_left.svg", color: LIBRARY_ACCENT, action_type: "page", target: "prev" },
      { id: "page_first", label: "Primera página", sub: "Inicio", icon: "/static/icons/folder.svg", color: LIBRARY_ACCENT, action_type: "page", target: "first" },
      { id: "page_goto", label: "Ir a una página", sub: "Elige cuál", icon: "/static/icons/folder.svg", color: LIBRARY_ACCENT, action_type: "page", target: "first", configure: true },
    ] },
    { category: "Multimedia", items: media },
    { category: "Monitores del PC", items: monitors },
    { category: "Atajos de Windows", items: [
      appKey("win_screenshot", "Captura de pantalla", "Win+Mayús+S", "WIN+SHIFT+S", "video"),
      appKey("win_desktop", "Mostrar el escritorio", "Win+D", "WIN+D", "folder"),
      appKey("win_explorer", "Abrir el Explorador", "Win+E", "WIN+E", "folder"),
      appKey("win_tasks", "Vista de tareas", "Win+Tab", "WIN+TAB", "sliders"),
      appKey("win_desk_next", "Escritorio virtual siguiente", "Win+Ctrl+Flecha der.", "WIN+CTRL+RIGHT", "chevron_right"),
      appKey("win_desk_prev", "Escritorio virtual anterior", "Win+Ctrl+Flecha izq.", "WIN+CTRL+LEFT", "chevron_left"),
      appKey("win_settings", "Ajustes de Windows", "Win+I", "WIN+I", "gear"),
      appKey("win_switch", "Cambiar de ventana", "Alt+Tab", "ALT+TAB", "next"),
      appKey("win_close", "Cerrar la ventana", "Alt+F4", "ALT+F4", "power"),
    ] },
    { category: "Edición y portapapeles", items: [
      appKey("edit_copy", "Copiar", "Ctrl+C", "CTRL+C", "notes"),
      appKey("edit_cut", "Cortar", "Ctrl+X", "CTRL+X", "trash"),
      appKey("edit_paste", "Pegar", "Ctrl+V", "CTRL+V", "plus"),
      appKey("edit_undo", "Deshacer", "Ctrl+Z", "CTRL+Z", "prev"),
      appKey("edit_redo", "Rehacer", "Ctrl+Y", "CTRL+Y", "next"),
      appKey("edit_all", "Seleccionar todo", "Ctrl+A", "CTRL+A", "macro"),
      appKey("edit_save", "Guardar", "Ctrl+S", "CTRL+S", "notes"),
      appKey("edit_find", "Buscar", "Ctrl+F", "CTRL+F", "link"),
    ] },
    { category: "Música y reproductores", items: [
      appKey("mp_vol_up", "Subir volumen (ventana activa)", "Flecha arriba", "UP", "volume_up"),
      appKey("mp_vol_down", "Bajar volumen (ventana activa)", "Flecha abajo", "DOWN", "mute"),
      appKey("mp_seek_fwd", "Adelantar (ventana activa)", "Flecha derecha", "RIGHT", "next"),
      appKey("mp_seek_back", "Atrasar (ventana activa)", "Flecha izquierda", "LEFT", "prev"),
      appKey("mp_mute", "Silenciar (ventana activa)", "M", "M", "mute"),
    ] },
    { category: "Reuniones (app a la vista)", items: [
      appKey("zoom_mute", "Zoom: micrófono", "Alt+A", "ALT+A", "mic_off"),
      appKey("zoom_video", "Zoom: cámara", "Alt+V", "ALT+V", "video"),
      appKey("zoom_share", "Zoom: compartir pantalla", "Alt+S", "ALT+S", "broadcast"),
      appKey("teams_mute", "Teams: micrófono", "Ctrl+Mayús+M", "CTRL+SHIFT+M", "mic_off"),
      appKey("teams_video", "Teams: cámara", "Ctrl+Mayús+O", "CTRL+SHIFT+O", "video"),
      appKey("teams_share", "Teams: compartir pantalla", "Ctrl+Mayús+E", "CTRL+SHIFT+E", "broadcast"),
      appKey("teams_hand", "Teams: levantar la mano", "Ctrl+Mayús+K", "CTRL+SHIFT+K", "gamepad"),
      appKey("teams_leave", "Teams: colgar", "Ctrl+Mayús+H", "CTRL+SHIFT+H", "power"),
      appKey("meet_mute", "Meet: micrófono", "Ctrl+D", "CTRL+D", "mic_off"),
      appKey("meet_video", "Meet: cámara", "Ctrl+E", "CTRL+E", "video"),
    ] },
    { category: "Vídeo y slides (app a la vista)", items: [
      appKey("vlc_play", "VLC: play/pausa", "Espacio", "SPACE", "play_pause"),
      appKey("vlc_next", "VLC: siguiente", "N", "N", "next"),
      appKey("vlc_prev", "VLC: anterior", "P", "P", "prev"),
      appKey("vlc_full", "VLC: pantalla completa", "F", "F", "video"),
      appKey("vlc_volup", "VLC: subir volumen", "Ctrl+Flecha arriba", "CTRL+UP", "volume_up"),
      appKey("vlc_voldown", "VLC: bajar volumen", "Ctrl+Flecha abajo", "CTRL+DOWN", "mute"),
      appKey("ppt_next", "PowerPoint: siguiente", "Flecha derecha", "RIGHT", "chevron_right"),
      appKey("ppt_prev", "PowerPoint: anterior", "Flecha izquierda", "LEFT", "chevron_left"),
      appKey("ppt_start", "PowerPoint: iniciar", "F5", "F5", "play"),
      appKey("ppt_black", "PowerPoint: pantalla negra", "B", "B", "pause"),
      appKey("ppt_end", "PowerPoint: salir", "Esc", "ESC", "power"),
    ] },
    { category: "Creación (app a la vista)", items: [
      appKey("resolve_play", "Resolve: play/pausa", "Espacio", "SPACE", "play_pause"),
      appKey("resolve_cut", "Resolve: cortar clip", "Ctrl+B", "CTRL+B", "macro"),
      appKey("resolve_save", "Resolve: guardar", "Ctrl+S", "CTRL+S", "notes"),
      appKey("ps_undo", "Photoshop: deshacer", "Ctrl+Z", "CTRL+Z", "prev"),
      appKey("ps_save", "Photoshop: guardar", "Ctrl+S", "CTRL+S", "notes"),
      appKey("ps_brush", "Photoshop: pincel", "B", "B", "sliders"),
      appKey("ps_eraser", "Photoshop: borrador", "E", "E", "trash"),
      appKey("audacity_rec", "Audacity: grabar", "R", "R", "mic"),
      appKey("audacity_play", "Audacity: play/parar", "Espacio", "SPACE", "play_pause"),
      appKey("audacity_pause", "Audacity: pausa", "P", "P", "pause"),
    ] },
    { category: "Navegador (a la vista)", items: [
      appKey("web_tab", "Pestaña nueva", "Ctrl+T", "CTRL+T", "plus"),
      appKey("web_close", "Cerrar pestaña", "Ctrl+W", "CTRL+W", "trash"),
      appKey("web_next", "Pestaña siguiente", "Ctrl+Tab", "CTRL+TAB", "chevron_right"),
      appKey("web_prev", "Pestaña anterior", "Ctrl+Mayús+Tab", "CTRL+SHIFT+TAB", "chevron_left"),
      appKey("web_reload", "Recargar", "F5", "F5", "play"),
    ] },
    { category: "Aplicaciones", items: [
      { id: "open_app", label: "Abrir una aplicación", sub: "Elige de tu PC", icon: "/static/icons/power.svg", color: LIBRARY_ACCENT, action_type: "sound", target: "beep", opensTab: "apps" },
    ] },
  ];
}

let libraryCategories = [];
let libraryFilter = "";

async function loadLibrary() {
  libraryCategories = builtInLibrary();
  renderLibrary();
  try {
    const { connectors } = await connectorApi("/catalog");
    const fromConnectors = connectors
      .filter(c => c.actions.length)
      .map(c => ({
        category: c.name,
        items: c.actions.map(a => ({
          id: `${c.id}_${a.id}`, label: a.label, sub: a.sublabel, icon: a.icon, color: a.color,
          action_type: a.action_type, target: a.target, extra: a.extra,
          connector: c.id, configure: a.configure, confirm_default: a.confirm_default, fields: a.fields,
        })),
      }));
    // Spotify and the Discord soundboard need a choice, so they open the Connectors tab.
    const spotify = fromConnectors.find(c => c.category === "Spotify");
    const extra = [
      { category: "Spotify", items: [{ id: "spotify_pick", label: "Playlist o canción", sub: "Elige o pega un enlace", icon: "/static/icons/spotify.svg", color: "#1db954", action_type: "sound", target: "beep", opensTab: "integrations", openConnector: "spotify" }] },
    ];
    const discord = fromConnectors.find(c => c.category === "Discord");
    if (discord) {
      discord.items.push({ id: "discord_sound", label: "Sonido del soundboard", sub: "Elige de tus servidores", icon: "/static/icons/soundboard.svg", color: "#5865f2", action_type: "sound", target: "beep", opensTab: "integrations", openConnector: "discord" });
    }
    libraryCategories = [...libraryCategories, ...fromConnectors.filter(c => c !== spotify), ...extra];
    renderLibrary();
  } catch (e) {
    console.error("Library connectors", e);
  }
}

function libraryMatches(item) {
  const term = libraryFilter.trim().toLowerCase();
  return !term || `${item.label} ${item.sub}`.toLowerCase().includes(term);
}

function renderLibrary() {
  const container = document.getElementById("library-list");
  if (!container) return;
  const searching = libraryFilter.trim() !== "";
  const html = libraryCategories.map((cat, index) => {
    const items = cat.items.filter(libraryMatches);
    if (!items.length) return "";
    return `
      <details class="library-category" ${searching || index === 0 ? "open" : ""}>
        <summary>${escapeHtml(cat.category)} <span class="library-count">${items.length}</span></summary>
        <div class="library-items">
          ${items.map(item => `
            <div class="library-item" draggable="true" data-item="${escapeHtml(item.id)}" title="Arrástralo a una casilla, o pulsa para ponerlo en la casilla elegida">
              <img src="${escapeHtml(item.icon)}" alt="">
              <div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.sub)}</span></div>
            </div>`).join("")}
        </div>
      </details>`;
  }).join("");
  container.innerHTML = html || `<div class="empty-note">Ninguna acción coincide con "${escapeHtml(libraryFilter)}"</div>`;

  container.querySelectorAll(".library-item").forEach(el => {
    const item = libraryCategories.flatMap(c => c.items).find(i => i.id === el.dataset.item);
    el.addEventListener("dragstart", (event) => {
      dragSourceType = "library";
      draggedLibraryItem = item;
      event.dataTransfer.effectAllowed = "copy";
      setDragGhost(event, "button", { label: item.label, sublabel: item.sub, image: item.icon, color: item.color });
      event.dataTransfer.setData("text/plain", item.label);
    });
    el.addEventListener("dragend", () => {
      dragSourceType = null;
      draggedLibraryItem = null;
      clearAllDragHighlights();
    });
    el.addEventListener("click", () => {
      if (selectedSlotIndex === null) return showToast("Selecciona una casilla, o arrastra la acción hasta ella");
      const slot = config.pages[activePageIndex].slots[selectedSlotIndex];
      if (slot && slot.type === "occupied_by_slider") return showToast("Esa casilla la ocupa un fader");
      placeLibraryItem(selectedSlotIndex, item);
    });
  });
}

// Puts a library action on a key. A fader in that column is replaced, as with any other drop.
function placeLibraryItem(index, item) {
  const slots = config.pages[activePageIndex].slots;
  const col = index % gridCols();
  if (inFaderColumn(slots, index)) clearColumn(slots, col);
  slots[index] = {
    index, type: "button", id: `btn_${Date.now()}`,
    label: item.label.slice(0, 32), sublabel: (item.sub || "").slice(0, 36), icon: "", image: item.icon,
    color: item.color, action_type: item.action_type, target: item.target,
    extra: JSON.parse(JSON.stringify(item.extra || {})),
  };
  if (item.confirm_default) slots[index].confirm = true; // e.g. console commands: ask before running
  if (item.opensTab) {
    activeInspectorTab = item.opensTab;
    if (item.openConnector) openConnectorId = item.openConnector;
  } else if (item.configure) {
    activeInspectorTab = "action";
  }
  renderPhoneScreen();
  selectSlot(index);
  triggerDropBounce(index);
  saveConfigToServer();
  showToast(item.opensTab ? "Elige a la derecha lo que quieres usar" : `"${item.label}" colocado en la casilla ${index + 1}`);
}

// ---------------------------------------------------------------- the "Acción" tab

function describeAction(a) {
  const pages = (config?.pages || []);
  const t = String(a.target ?? "");
  switch (a.action_type) {
    case "hotkey": return `Pulsa ${t}`;
    case "text": return `Escribe «${t.length > 28 ? t.slice(0, 28) + "…" : t}»${a.extra?.press_enter ? " y Enter" : ""}`;
    case "url": return `Abre ${t.replace(/^https?:\/\//, "")}`;
    case "folder": return `Abre la carpeta ${t}`;
    case "command": {
      const count = a.extra?.commands?.length || 0;
      return `Ejecuta ${count} comando${count === 1 ? "" : "s"} de ${t === "cmd" ? "cmd" : "PowerShell"}`;
    }
    case "page": {
      const names = { next: "la página siguiente", prev: "la página anterior", first: "la primera página" };
      return `Va a ${names[t] || `«${pages.find(p => p.id === t)?.name || "página borrada"}»`}`;
    }
    case "media": return `Multimedia: ${t.replace("_", " ")}`;
    case "preset_app": case "launch": return `Abre ${t}`;
    case "obs_action": return `OBS: ${t.replace("_", " ")}`;
    case "discord_hotkey": return t === "sound" ? `Sonido de Discord (${a.extra?.sound_name || "sin nombre"})` : `Discord: ${t}`;
    case "discord_sound": return `Reproduce «${a.extra?.sound_name || "un sonido"}» en tu canal de voz`;
    case "windows": return `Windows: ${t.replace("_", " ")}`;
    case "spotify_uri": return `Spotify: ${t}`;
    case "hardware_monitor": return `Muestra ${t.toUpperCase()} en vivo`;
    case "sound": return `Sonido ${t}`;
    case "multi": return `Multiacción de ${a.extra?.actions?.length || 0} pasos`;
    default: return a.action_type || "";
  }
}

// Updates the preview and saves, without redrawing the editor (typing must not lose focus).
function commitAction(btn) {
  renderPhoneScreen();
  saveConfigToServer();
  const summary = document.getElementById("action-summary");
  if (summary) summary.textContent = describeAction(btn);
  const top = document.getElementById("inspector-summary-action");
  if (top) top.textContent = describeAction(btn) || "Nada todavía";
}

function hotkeyFromEvent(event) {
  const names = { " ": "SPACE", Tab: "TAB", Enter: "ENTER", Escape: "ESC", Backspace: "BACKSPACE", Delete: "DELETE", Home: "HOME", End: "END",
    ArrowUp: "UP", ArrowDown: "DOWN", ArrowLeft: "LEFT", ArrowRight: "RIGHT", Insert: "INSERT", PageUp: "PAGEUP", PageDown: "PAGEDOWN", PrintScreen: "PRINTSCREEN" };
  let key = names[event.key];
  if (!key && /^F([1-9]|1\d|2[0-4])$/.test(event.key)) key = event.key;
  if (!key && /^[a-z0-9]$/i.test(event.key)) key = event.key.toUpperCase();
  if (!key && /^Key[A-Z]$/.test(event.code)) key = event.code.slice(3); // a letter typed with Alt or a dead key
  if (!key && /^Digit\d$/.test(event.code)) key = event.code.slice(5);
  if (!key) return "";
  const mods = [event.ctrlKey && "CTRL", event.altKey && "ALT", event.shiftKey && "SHIFT", event.metaKey && "WIN"].filter(Boolean);
  return [...mods, key].join("+");
}

const ACTION_EDITORS = {
  hotkey(el, btn) {
    el.innerHTML = `
      <label for="hk-input">Atajo</label>
      <div class="inline-row"><input id="hk-input" type="text" maxlength="60" value="${escapeHtml(btn.target)}"><button class="btn-secondary" id="hk-record">Grabar</button></div>
      <p class="integration-hint">Pulsa «Grabar» y después la combinación en tu teclado. Se envía al PC como si la pulsaras tú.</p>`;
    const input = el.querySelector("#hk-input");
    const record = el.querySelector("#hk-record");
    input.addEventListener("input", () => { btn.target = input.value.trim(); commitAction(btn); });
    const stop = () => { document.removeEventListener("keydown", onKey, true); record.textContent = "Grabar"; };
    const onKey = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (["Control", "Shift", "Alt", "Meta"].includes(event.key)) return; // wait for the real key
      const combo = hotkeyFromEvent(event);
      if (!combo) return showToast("Esa tecla no se puede usar en un atajo");
      input.value = btn.target = combo;
      commitAction(btn);
      stop();
    };
    record.addEventListener("click", () => {
      if (record.textContent !== "Grabar") return stop();
      record.textContent = "Pulsa el atajo...";
      document.addEventListener("keydown", onKey, true);
    });
  },

  text(el, btn) {
    btn.extra = btn.extra || {};
    el.innerHTML = `
      <label for="tx-input">Texto que se escribirá</label>
      <textarea id="tx-input" maxlength="300" rows="4">${escapeHtml(btn.target)}</textarea>
      <div class="integration-hint"><span id="tx-count">${btn.target.length}</span>/300 caracteres. Admite acentos, emojis y varias líneas.</div>
      <label class="check-row"><input type="checkbox" id="tx-enter" ${btn.extra.press_enter ? "checked" : ""}> Pulsar Enter al terminar</label>`;
    el.querySelector("#tx-input").addEventListener("input", (event) => {
      btn.target = event.target.value;
      el.querySelector("#tx-count").textContent = btn.target.length;
      commitAction(btn);
    });
    el.querySelector("#tx-enter").addEventListener("change", (event) => { btn.extra.press_enter = event.target.checked; commitAction(btn); });
  },

  url(el, btn) {
    el.innerHTML = `
      <label for="url-input">Dirección web</label>
      <input id="url-input" type="url" maxlength="300" value="${escapeHtml(btn.target)}" placeholder="https://...">
      <p class="integration-hint">Se abre en el navegador predeterminado de tu PC. Tiene que empezar por http:// o https://.</p>`;
    el.querySelector("#url-input").addEventListener("input", (event) => { btn.target = event.target.value.trim(); commitAction(btn); });
  },

  command(el, btn) { renderCommandEditor(el, btn); },

  folder(el, btn) {
    el.innerHTML = `
      <label for="fd-input">Carpeta del PC</label>
      <input id="fd-input" type="text" maxlength="240" value="${escapeHtml(btn.target)}" placeholder="D:\\Proyectos">
      <p class="integration-hint">Ruta de un disco del PC, por ejemplo C:\\Users\\tu-nombre\\Documents. Se abre en el Explorador. No se admiten rutas de red.</p>`;
    el.querySelector("#fd-input").addEventListener("input", (event) => { btn.target = event.target.value.trim(); commitAction(btn); });
  },

  page(el, btn) {
    const options = [["next", "Página siguiente"], ["prev", "Página anterior"], ["first", "Primera página"],
      ...(config.pages || []).map(p => [p.id, `Ir a «${p.name}»`])];
    el.innerHTML = `
      <label for="pg-select">Dónde lleva este botón</label>
      <select id="pg-select">${options.map(([value, text]) => `<option value="${escapeHtml(value)}" ${btn.target === value ? "selected" : ""}>${escapeHtml(text)}</option>`).join("")}</select>
      <p class="integration-hint">Úsalo para montar carpetas: una página con un botón que vuelve a la primera.</p>`;
    el.querySelector("#pg-select").addEventListener("change", (event) => { btn.target = event.target.value; commitAction(btn); });
  },

  multi(el, btn) { renderMacroEditor(el, btn); },
};

function renderTabAction(container, btn, index) {
  const fieldSpec = fieldsForButton(btn);
  const editor = ACTION_EDITORS[btn.action_type] || (fieldSpec ? (el, b) => renderFieldsEditor(el, b, fieldSpec) : null);
  container.innerHTML = `
    <div class="action-summary">
      <span class="section-label" style="margin: 0 0 4px;">Este botón</span>
      <strong id="action-summary">${escapeHtml(describeAction(btn))}</strong>
    </div>
    <div id="action-editor"></div>
    ${editor ? "" : `<p class="integration-hint" style="margin-top: 12px;">Esta acción no necesita ajustes. Para cambiarla, elige otra en la biblioteca, en Apps o en Conectores.</p>`}
    ${btn.action_type === "hardware_monitor" ? "" : `<div id="gesture-section"></div>`}`;
  editor?.(container.querySelector("#action-editor"), btn, index);
  const gestures = container.querySelector("#gesture-section");
  if (gestures) renderGestureSection(gestures, btn);
}

// ---------------------------------------------------------------- console commands

const COMMANDS_MAX = 8;

// The opt-in switch. Commands do nothing until it is on, and it is off by default.
function commandsSwitchHtml(suffix) {
  return `
    <label class="check-row"><input type="checkbox" data-commands-switch id="cmd-allow-${suffix}"> Permitir comandos de consola en este PC</label>
    <p class="integration-hint command-warning">Un comando se ejecuta con los permisos de tu usuario de Windows, sin preguntar nada más. Cualquiera que pueda pulsar el botón (cualquier móvil emparejado) lo lanza. Actívalo solo si confías en tus móviles y en los perfiles que cargues.</p>`;
}

async function wireCommandsSwitch(root) {
  const boxes = root.querySelectorAll("[data-commands-switch]");
  if (!boxes.length) return;
  try {
    const { enabled } = await apiJson("/api/settings/commands");
    boxes.forEach(box => { box.checked = Boolean(enabled); });
  } catch (err) {
    boxes.forEach(box => { box.disabled = true; });
  }
  boxes.forEach(box => box.addEventListener("change", async () => {
    try {
      const result = await postJson("/api/settings/commands", { enabled: box.checked });
      const enabled = result.enabled ?? box.checked;
      document.querySelectorAll("[data-commands-switch]").forEach(other => { other.checked = Boolean(enabled); });
      showToast(enabled ? "Comandos de consola activados" : "Comandos de consola desactivados");
    } catch (err) {
      box.checked = !box.checked;
      showToast(err.message);
    }
  }));
}

function renderCommandEditor(el, btn) {
  btn.extra = btn.extra || {};
  // The rows being edited. Empty rows are only kept here: the profile only ever holds filled-in commands.
  const rows = Array.isArray(btn.extra.commands) && btn.extra.commands.length ? [...btn.extra.commands] : ["Get-Date"];
  if (btn.target !== "cmd") btn.target = "powershell";

  const sync = () => {
    const filled = rows.map(r => r.trim()).filter(Boolean);
    const hint = el.querySelector("#cmd-empty-hint");
    if (hint) hint.hidden = filled.length > 0;
    if (!filled.length) return; // keep the last valid list until there is a command to save
    btn.extra.commands = filled;
    commitAction(btn);
  };

  const draw = () => {
    el.innerHTML = `
      <label for="cmd-shell">Se ejecuta con</label>
      <select id="cmd-shell">
        <option value="powershell" ${btn.target === "powershell" ? "selected" : ""}>PowerShell</option>
        <option value="cmd" ${btn.target === "cmd" ? "selected" : ""}>Símbolo del sistema (cmd)</option>
      </select>
      <label style="margin-top: 12px;">Comandos (en este orden)</label>
      <div class="step-list">
        ${rows.map((row, i) => `
          <div class="step-row">
            <span class="step-num">${i + 1}</span>
            <div class="step-body"><input class="step-input command-input" data-row="${i}" value="${escapeHtml(row)}" maxlength="500" spellcheck="false" aria-label="Comando ${i + 1}" placeholder="Escribe un comando"></div>
            <div class="step-controls">
              <button class="icon-mini" data-up="${i}" ${i === 0 ? "disabled" : ""} title="Subir">↑</button>
              <button class="icon-mini" data-down="${i}" ${i === rows.length - 1 ? "disabled" : ""} title="Bajar">↓</button>
              <button class="icon-mini" data-remove="${i}" ${rows.length === 1 ? "disabled" : ""} title="Quitar">✕</button>
            </div>
          </div>`).join("")}
      </div>
      <button class="btn-secondary" id="cmd-add" ${rows.length >= COMMANDS_MAX ? "disabled" : ""}>+ Añadir otro comando</button>
      <p class="integration-hint">Se ejecutan en este orden; si uno falla, se detiene y el móvil dice cuál. Máximo ${COMMANDS_MAX}, de hasta 500 caracteres cada uno.</p>
      <p class="integration-hint command-warning" id="cmd-empty-hint" hidden>Escribe al menos un comando para guardar el botón.</p>
      ${commandsSwitchHtml("action")}`;

    el.querySelector("#cmd-shell").addEventListener("change", (event) => { btn.target = event.target.value; sync(); });
    el.querySelectorAll("[data-row]").forEach(input => input.addEventListener("input", () => { rows[Number(input.dataset.row)] = input.value; sync(); }));
    const move = (from, to) => { [rows[from], rows[to]] = [rows[to], rows[from]]; sync(); draw(); };
    el.querySelectorAll("[data-up]").forEach(b => b.addEventListener("click", () => move(Number(b.dataset.up), Number(b.dataset.up) - 1)));
    el.querySelectorAll("[data-down]").forEach(b => b.addEventListener("click", () => move(Number(b.dataset.down), Number(b.dataset.down) + 1)));
    el.querySelectorAll("[data-remove]").forEach(b => b.addEventListener("click", () => { rows.splice(Number(b.dataset.remove), 1); sync(); draw(); }));
    el.querySelector("#cmd-add").addEventListener("click", () => { if (rows.length < COMMANDS_MAX) { rows.push(""); draw(); el.querySelectorAll("[data-row]")[rows.length - 1]?.focus(); } });
    wireCommandsSwitch(el);
  };
  draw();
}

// ---------------------------------------------------------------- the fields an action asks for

// What the server keeps in `extra` until the user chooses (so the profile is valid meanwhile).
const NOT_CHOSEN = "Elige";

// The catalog item behind a button that needs choices (a scene, a source...), with the connector it belongs to.
function fieldsForButton(btn) {
  const item = libraryCategories.flatMap(c => c.items).find(i => i.fields && i.action_type === btn.action_type && i.target === btn.target);
  return item ? { fields: item.fields, connector: item.connector } : null;
}

function renderFieldsEditor(el, btn, { fields, connector }) {
  btn.extra = btn.extra || {};
  const loaded = {}; // options name -> promise of its list, asked once per editor
  const optionsOf = (name) => (loaded[name] ??= connectorApi(`/${connector}/options/${name}`).then(data => data.options));

  el.innerHTML = fields.map(f => `
      <label for="fld-${escapeHtml(f.name)}">${escapeHtml(f.label)}</label>
      <div id="fld-box-${escapeHtml(f.name)}"></div>`).join("") + `<p class="integration-hint" id="fld-missing"></p>`;

  const chosen = (name) => (btn.extra[name] && btn.extra[name] !== NOT_CHOSEN ? btn.extra[name] : "");
  const updateMissing = () => {
    const missing = fields.filter(f => f.required && !chosen(f.name)).map(f => f.label);
    const line = el.querySelector("#fld-missing");
    if (line) line.textContent = missing.length ? `Falta elegir: ${missing.join(", ")}.` : "";
  };
  const set = (field, value) => {
    btn.extra[field.name] = value || NOT_CHOSEN;
    // A choice that depends on this one (the sources of a scene) starts over.
    fields.filter(f => f.filter_by === field.name).forEach(dep => { btn.extra[dep.name] = NOT_CHOSEN; draw(dep); });
    commitAction(btn);
    updateMissing();
  };

  async function draw(field) {
    const box = el.querySelector(`#fld-box-${field.name}`);
    if (!box) return;
    const current = chosen(field.name);
    const asText = (reason) => {
      box.innerHTML = `<input type="text" id="fld-${escapeHtml(field.name)}" maxlength="80" value="${escapeHtml(current)}" placeholder="Escríbelo aquí">
        ${reason ? `<p class="integration-hint">${escapeHtml(reason)}</p>` : ""}`;
      box.querySelector("input").addEventListener("input", (event) => set(field, event.target.value.trim()));
    };
    if (!field.options) return asText("");
    box.innerHTML = `<select disabled><option>Cargando...</option></select>`;
    try {
      let options = await optionsOf(field.options);
      if (field.filter_by) {
        const parent = chosen(field.filter_by);
        options = parent ? options.filter(o => o.scene === parent) : [];
      }
      const names = [...new Set(options.map(o => o.name))];
      if (current && !names.includes(current)) names.unshift(current); // keep a choice OBS no longer lists
      box.innerHTML = `<select id="fld-${escapeHtml(field.name)}">
        <option value="">${field.filter_by && !chosen(field.filter_by) ? "Elige antes la opción anterior" : "Elige..."}</option>
        ${names.map(n => `<option value="${escapeHtml(n)}" ${n === current ? "selected" : ""}>${escapeHtml(n)}</option>`).join("")}
      </select>`;
      box.querySelector("select").addEventListener("change", (event) => set(field, event.target.value));
    } catch (err) {
      asText(`No se pudo leer la lista (${err.message}). Escríbelo a mano.`);
    }
  }
  fields.forEach(draw);
  updateMissing();
}

// ---------------------------------------------------------------- long press, double tap, confirm, off

const GESTURE_LABELS = { long_press: "Pulsación larga", double_tap: "Doble toque" };

// What a gesture can run: the simple, self-contained actions (the same ones a macro step can use).
function gestureChoices() {
  return macroStepChoices();
}

function renderGestureSection(el, btn) {
  const redraw = () => renderGestureSection(el, btn);
  const gestureRow = (gesture) => {
    const action = btn[gesture];
    const choices = gestureChoices();
    const inline = action && ["hotkey", "text", "url", "folder"].includes(action.action_type)
      ? `<input class="step-input" data-gesture="${gesture}" value="${escapeHtml(action.target)}" maxlength="300" aria-label="${GESTURE_LABELS[gesture]}">` : "";
    return `
      <div class="gesture-row">
        <label class="check-row"><input type="checkbox" data-toggle="${gesture}" ${action ? "checked" : ""}> ${GESTURE_LABELS[gesture]}</label>
        ${action ? `
          <select data-pick="${gesture}" aria-label="Acción de ${GESTURE_LABELS[gesture].toLowerCase()}">
            <option value="">${escapeHtml(describeAction(action))}</option>
            ${choices.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label)}</option>`).join("")}
          </select>${inline}` : ""}
      </div>`;
  };
  el.innerHTML = `
    <span class="section-label" style="margin: 16px 0 6px;">Más formas de usar este botón</span>
    ${gestureRow("long_press")}
    ${gestureRow("double_tap")}
    <label class="check-row"><input type="checkbox" id="g-confirm" ${btn.confirm ? "checked" : ""}> Pedir confirmación antes de ejecutar</label>
    <label class="check-row"><input type="checkbox" id="g-disabled" ${btn.disabled ? "checked" : ""}> Desactivar el botón (no se borra)</label>
    <p class="integration-hint">Con una pulsación larga o un doble toque, el toque normal espera unas décimas de segundo para saber cuál de los gestos haces. Se avisa con dos puntitos en el botón del móvil.</p>`;

  el.querySelectorAll("[data-toggle]").forEach(box => box.addEventListener("change", () => {
    const gesture = box.dataset.toggle;
    if (box.checked) btn[gesture] = { action_type: "hotkey", target: "CTRL+SHIFT+M", extra: {} };
    else delete btn[gesture];
    commitAction(btn);
    redraw();
  }));
  el.querySelectorAll("[data-pick]").forEach(select => select.addEventListener("change", () => {
    const choice = gestureChoices().find(c => c.id === select.value);
    if (!choice) return;
    btn[select.dataset.pick] = choice.build();
    commitAction(btn);
    redraw();
  }));
  el.querySelectorAll("[data-gesture]").forEach(input => input.addEventListener("input", () => {
    btn[input.dataset.gesture].target = input.value;
    commitAction(btn);
  }));
  el.querySelector("#g-confirm").addEventListener("change", (event) => {
    if (event.target.checked) btn.confirm = true; else delete btn.confirm;
    commitAction(btn);
  });
  el.querySelector("#g-disabled").addEventListener("change", (event) => {
    if (event.target.checked) btn.disabled = true; else delete btn.disabled;
    commitAction(btn);
  });
}

// ---------------------------------------------------------------- multi-action editor

const MACRO_MAX_STEPS = 8;

function macroStepChoices() {
  const fixed = libraryCategories.flatMap(c => c.items).filter(i => !i.configure && !i.opensTab && !["page", "multi"].includes(i.action_type));
  return [
    { id: "__hotkey", label: "Atajo de teclado", build: () => ({ action_type: "hotkey", target: "CTRL+C", extra: {} }) },
    { id: "__text", label: "Escribir texto", build: () => ({ action_type: "text", target: "Hola", extra: { press_enter: false } }) },
    { id: "__url", label: "Abrir una web", build: () => ({ action_type: "url", target: "https://www.example.com", extra: {} }) },
    { id: "__folder", label: "Abrir una carpeta", build: () => ({ action_type: "folder", target: "C:\\Users", extra: {} }) },
    { id: "__app", label: "Abrir una aplicación", build: () => ({ action_type: "preset_app", target: (detectedSystemApps[0]?.id || "calc"), extra: {} }) },
    ...fixed.map(i => ({ id: i.id, label: `${i.sub}: ${i.label}`, build: () => ({ action_type: i.action_type, target: i.target, extra: JSON.parse(JSON.stringify(i.extra || {})) }) })),
  ];
}

function renderMacroEditor(el, btn) {
  btn.extra = btn.extra || {};
  btn.extra.actions = btn.extra.actions || [];
  const steps = btn.extra.actions;
  const choices = macroStepChoices();

  const inlineEditor = (step, i) => {
    if (step.action_type === "hotkey") return `<input class="step-input" data-field="target" data-i="${i}" value="${escapeHtml(step.target)}" maxlength="60" aria-label="Atajo">`;
    if (step.action_type === "text") return `<input class="step-input" data-field="target" data-i="${i}" value="${escapeHtml(step.target)}" maxlength="300" aria-label="Texto">`;
    if (step.action_type === "folder") return `<input class="step-input" data-field="target" data-i="${i}" value="${escapeHtml(step.target)}" maxlength="240" aria-label="Carpeta">`;
    if (step.action_type === "url") return `<input class="step-input" data-field="target" data-i="${i}" value="${escapeHtml(step.target)}" maxlength="300" aria-label="Dirección">`;
    if (step.action_type === "preset_app") {
      const apps = detectedSystemApps.length ? detectedSystemApps : [{ id: step.target, name: step.target }];
      return `<select class="step-input" data-field="target" data-i="${i}" aria-label="Aplicación">${apps.map(a => `<option value="${escapeHtml(a.id)}" ${a.id === step.target ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("")}</select>`;
    }
    return "";
  };

  el.innerHTML = `
    <p class="integration-hint" style="margin-bottom: 10px;">Los pasos se ejecutan de arriba abajo. El tiempo es la espera después de cada paso.</p>
    <div class="step-list">
      ${steps.map((step, i) => `
        <div class="step-row">
          <span class="step-num">${i + 1}</span>
          <div class="step-body"><strong>${escapeHtml(describeAction(step))}</strong>${inlineEditor(step, i)}</div>
          <div class="step-controls">
            <label class="step-delay">espera <input type="number" min="0" max="5000" step="50" value="${Number(step.delay_ms ?? 150)}" data-delay="${i}"> ms</label>
            <button class="icon-mini" data-move="-1" data-i="${i}" ${i === 0 ? "disabled" : ""} title="Subir">↑</button>
            <button class="icon-mini" data-move="1" data-i="${i}" ${i === steps.length - 1 ? "disabled" : ""} title="Bajar">↓</button>
            <button class="icon-mini" data-del="${i}" ${steps.length === 1 ? "disabled" : ""} title="Quitar">✕</button>
          </div>
        </div>`).join("")}
    </div>
    <div class="inline-row" style="margin-top: 10px;">
      <select id="macro-add" ${steps.length >= MACRO_MAX_STEPS ? "disabled" : ""}>
        <option value="">Añadir un paso...</option>
        ${choices.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label)}</option>`).join("")}
      </select>
    </div>
    ${steps.length >= MACRO_MAX_STEPS ? `<p class="integration-hint">Máximo ${MACRO_MAX_STEPS} pasos.</p>` : ""}`;

  const redraw = () => { commitAction(btn); renderMacroEditor(el, btn); };
  el.querySelectorAll("[data-delay]").forEach(input => input.addEventListener("input", () => {
    steps[Number(input.dataset.delay)].delay_ms = Math.max(0, Math.min(5000, Number(input.value) || 0));
    commitAction(btn);
  }));
  el.querySelectorAll(".step-input").forEach(input => input.addEventListener("input", () => {
    steps[Number(input.dataset.i)].target = input.value;
    commitAction(btn);
    const label = input.closest(".step-body").querySelector("strong");
    label.textContent = describeAction(steps[Number(input.dataset.i)]);
  }));
  el.querySelectorAll("[data-move]").forEach(button => button.addEventListener("click", () => {
    const i = Number(button.dataset.i), j = i + Number(button.dataset.move);
    [steps[i], steps[j]] = [steps[j], steps[i]];
    redraw();
  }));
  el.querySelectorAll("[data-del]").forEach(button => button.addEventListener("click", () => {
    if (steps.length > 1) { steps.splice(Number(button.dataset.del), 1); redraw(); }
  }));
  el.querySelector("#macro-add").addEventListener("change", (event) => {
    const choice = choices.find(c => c.id === event.target.value);
    if (choice && steps.length < MACRO_MAX_STEPS) { steps.push({ ...choice.build(), delay_ms: 150 }); redraw(); }
  });
}

// Drops from the library are handled by studio.js through this hook.
window.addEventListener("DOMContentLoaded", () => {
  loadLibrary();
  document.getElementById("library-search")?.addEventListener("input", (event) => {
    libraryFilter = event.target.value;
    renderLibrary();
  });
  // Opening the editor tab needs the pages (for "go to page"): nothing else to prepare.
});
