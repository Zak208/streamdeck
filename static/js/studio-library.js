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
  const editor = ACTION_EDITORS[btn.action_type];
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
