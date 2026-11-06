// The library of pages: a page of its own with every ready-made page, a thumbnail drawn at its real size, and one click to add it.

const grid = document.getElementById("lib-grid");
const filters = document.getElementById("lib-filters");
const search = document.getElementById("lib-search");
const count = document.getElementById("lib-count");
const toastEl = document.getElementById("lib-toast");

let templates = [];
let categories = [];
let category = "Todas";
const added = new Map(); // template id -> index of the page it created, for this visit
let toastTimer = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), Math.max(2800, 60 * message.length));
}

async function api(path, body) {
  const options = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo completar la acción");
  return data;
}

// The page as it will look: its own columns and rows, faders as tall cells, keys with their icon and colour.
function deckThumb(t) {
  const { rows, columns } = t.layout;
  const taken = new Set();
  const cells = (t.preview || []).map(item => {
    const row = Math.floor(item.index / columns) + 1;
    const col = (item.index % columns) + 1;
    const span = item.kind === "slider" ? Math.max(1, item.span || 2) : 1;
    for (let k = 0; k < span; k++) taken.add(item.index + k * columns);
    return `<span class="lib-cell ${item.kind === "slider" ? "is-fader" : ""}" style="--tc: ${escapeHtml(item.color || "#f8c700")}; grid-column: ${col}; grid-row: ${row} / span ${span}">
      <img src="${escapeHtml(item.image)}" alt="" loading="lazy"></span>`;
  });
  const blanks = [];
  for (let i = 0; i < rows * columns; i++) {
    if (!taken.has(i)) blanks.push(`<span class="lib-cell is-blank" style="grid-column: ${(i % columns) + 1}; grid-row: ${Math.floor(i / columns) + 1}"></span>`);
  }
  return `<span class="lib-deck" style="--cols: ${columns}; --rows: ${rows}; aspect-ratio: ${columns * 1.1} / ${rows}" aria-hidden="true">${blanks.join("")}${cells.join("")}</span>`;
}

function draw() {
  const term = search.value.trim().toLowerCase();
  const shown = templates.filter(t => (category === "Todas" || t.category === category)
    && (!term || `${t.name} ${t.description} ${t.app || ""} ${t.category}`.toLowerCase().includes(term)));
  count.textContent = `${shown.length} de ${templates.length} páginas`;
  if (!shown.length) {
    grid.innerHTML = `<div class="lib-empty">Ninguna página coincide con esa búsqueda.</div>`;
    return;
  }
  grid.innerHTML = shown.map(t => {
    const done = added.get(t.id);
    return `
      <article class="lib-card" data-id="${escapeHtml(t.id)}">
        <header class="lib-card-head">
          <img src="${escapeHtml(t.icon)}" alt="">
          <h2>${escapeHtml(t.name)}</h2>
          <span class="lib-size" title="Tamaño de la cuadrícula de esta página">${t.layout.columns}x${t.layout.rows}</span>
        </header>
        ${deckThumb(t)}
        <p class="lib-desc">${escapeHtml(t.description)}</p>
        <footer class="lib-card-foot">
          ${t.app ? `<span class="lib-badge" title="Se abre sola en el móvil cuando ${escapeHtml(t.app)} está a la vista">se abre sola</span>` : `<span class="lib-badge is-plain">${escapeHtml(t.category)}</span>`}
          ${done === undefined
            ? `<button type="button" class="lib-add" data-add>Añadir a mi perfil</button>`
            : `<button type="button" class="lib-add is-done" data-open="${done}">Añadida · Abrir en Studio</button>`}
        </footer>
      </article>`;
  }).join("");
}

function drawFilters() {
  filters.innerHTML = ["Todas", ...categories].map(name => `
    <button type="button" class="lib-filter ${name === category ? "active" : ""}" role="tab" aria-selected="${name === category}" data-category="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
}

filters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-category]");
  if (!button) return;
  category = button.dataset.category;
  drawFilters();
  draw();
});
search.addEventListener("input", draw);

grid.addEventListener("click", async (event) => {
  const open = event.target.closest("[data-open]");
  if (open) {
    try { await api("/api/deck/page/switch", { page_index: Number(open.dataset.open) }); } catch (e) { /* Studio opens on its last page */ }
    location.href = "/studio";
    return;
  }
  const add = event.target.closest("[data-add]");
  if (!add) return;
  const card = add.closest("[data-id]");
  const template = templates.find(t => t.id === card.dataset.id);
  add.disabled = true;
  try {
    const result = await api("/api/templates/apply", { template_id: template.id, name: template.name });
    added.set(template.id, result.index);
    const notes = [];
    if (result.dropped) notes.push(`En esta cuadrícula no caben ${result.dropped} elementos`);
    if (template.app && !result.auto_app) notes.push(`Ya tenías una página que se abre con ${template.app}: esta no se abre sola`);
    toast([`«${template.name}» añadida a tu perfil`, ...notes].join(". "));
    draw();
  } catch (err) {
    add.disabled = false;
    toast(err.message);
  }
});

(async () => {
  try {
    const data = await api("/api/templates");
    templates = data.templates;
    categories = data.categories;
    drawFilters();
    draw();
  } catch (err) {
    grid.innerHTML = `<div class="lib-empty">No se pudo cargar la biblioteca (${escapeHtml(err.message)}). Ábrela desde StreamDesk Studio.</div>`;
  }
})();
