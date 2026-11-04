// What each system gauge reads and how it is drawn. Loaded by the phone and by Studio, so a CPU
// gauge cannot look one way on the phone and another in the preview.

const MONITORS = {
  cpu: { name: "CPU", kind: "percent", read: t => t.cpu },
  ram: { name: "RAM", kind: "percent", read: t => t.ram },
  disk: { name: "Disco", kind: "percent", read: t => t.disk }, // space used: kept for profiles made before disk speed existed
  gpu: { name: "GPU", kind: "percent", read: t => t.gpu },
  vram: {
    name: "VRAM", kind: "percent", read: t => t.vram,
    detail: t => (t.vram_used == null ? "" : `${formatBytes(t.vram_used)} / ${formatBytes(t.vram_total)}`),
  },
  net: {
    name: "Red", kind: "rate",
    rows: [{ label: "↓", read: t => t.net_down }, { label: "↑", read: t => t.net_up }],
  },
  disk_speed: {
    name: "Disco", kind: "rate",
    rows: [{ label: "Lee", read: t => t.disk_read }, { label: "Escribe", read: t => t.disk_write }],
  },
};

const NO_GPU_HINT = "StreamDesk solo puede leer la GPU y la VRAM de tarjetas NVIDIA.";

// Bytes per second as a short number and a unit that keeps it readable at a glance.
function formatRate(bytesPerSecond) {
  const bytes = Number(bytesPerSecond) || 0;
  if (bytes <= 0) return { value: "0", unit: "KB/s" };
  for (const [unit, size] of [["GB/s", 1e9], ["MB/s", 1e6], ["KB/s", 1e3]]) {
    if (bytes >= size) {
      const value = bytes / size;
      return { value: value < 10 ? value.toFixed(1) : String(Math.round(value)), unit };
    }
  }
  return { value: (bytes / 1e3).toFixed(1), unit: "KB/s" };
}

function formatBytes(bytes) {
  return `${(Number(bytes) / 2 ** 30).toFixed(1)} GB`;
}

// Every reading as text, for the sheet that opens when a gauge is tapped. `undefined` means no data yet, `null` no sensor.
function monitorDetailRows(t) {
  const percent = (v) => (v === undefined ? "--" : v === null ? "N/D" : `${v} %`);
  const rate = (v) => { const r = formatRate(v); return `${r.value} ${r.unit}`; };
  const speed = (a, b, la, lb) => (a === undefined && b === undefined ? "--" : `${la} ${rate(a)} · ${lb} ${rate(b)}`);
  const vramText = t.vram === undefined ? "--" : t.vram === null ? "N/D"
    : `${t.vram} %${t.vram_used == null ? "" : ` · ${formatBytes(t.vram_used)} / ${formatBytes(t.vram_total)}`}`;
  return [
    { name: "CPU", text: percent(t.cpu) },
    { name: "RAM", text: percent(t.ram) },
    { name: "GPU", text: percent(t.gpu) },
    { name: "VRAM", text: vramText },
    { name: "Red", text: speed(t.net_down, t.net_up, "↓", "↑") },
    { name: "Disco", text: speed(t.disk_read, t.disk_write, "Lee", "Escribe") },
    { name: "Espacio del disco", text: percent(t.disk) },
  ];
}

function monitorLevel(percent) {
  return percent >= 85 ? "high" : percent >= 60 ? "warn" : "ok";
}

// The inside of a gauge. `prefix` is the CSS class family of the page ("deck-monitor" or "slot-monitor").
function monitorInnerHtml(prefix, target) {
  const def = MONITORS[target] || { name: target, kind: "percent" };
  if (def.kind === "rate") {
    return `<div class="${prefix}-name"></div>` + def.rows.map((row, i) => `
      <div class="${prefix}-rate" data-row="${i}">
        <b>${row.label}</b><span>--</span><small>KB/s</small>
        <i class="${prefix}-ratebar"><u></u></i>
      </div>`).join("");
  }
  return `
    <div class="${prefix}-name"></div>
    <div class="${prefix}-value"><span>--</span><small>%</small></div>
    ${def.detail ? `<div class="${prefix}-detail"></div>` : ""}
    <div class="${prefix}-bar"><i></i></div>`;
}

// Throughput has no natural maximum, so each bar is scaled to the recent peak (at least 1 MB/s).
const monitorPeaks = {};

function paintMonitor(el, prefix, target, telemetry) {
  const def = MONITORS[target];
  if (!def || !telemetry) return;

  if (def.kind === "rate") {
    def.rows.forEach((row, i) => {
      const line = el.querySelector(`.${prefix}-rate[data-row="${i}"]`);
      if (!line) return;
      const bytes = Number(row.read(telemetry)) || 0;
      const { value, unit } = formatRate(bytes);
      line.querySelector("span").textContent = value;
      line.querySelector("small").textContent = unit;
      const key = `${target}:${i}`;
      monitorPeaks[key] = Math.max(bytes, (monitorPeaks[key] || 0) * 0.97, 1e6);
      line.querySelector("u").style.width = `${Math.min(100, (bytes / monitorPeaks[key]) * 100)}%`;
    });
    return;
  }

  const value = def.read(telemetry);
  const number = el.querySelector(`.${prefix}-value span`);
  const unit = el.querySelector(`.${prefix}-value small`);
  const bar = el.querySelector(`.${prefix}-bar i`);
  const detail = el.querySelector(`.${prefix}-detail`);
  if (value === null || value === undefined) {
    // null means this PC has no reading to give (not an NVIDIA GPU); undefined means no data has arrived yet.
    number.textContent = value === null ? "N/D" : "--";
    unit.hidden = true;
    bar.style.width = "0%";
    el.dataset.level = "na";
    el.title = value === null && (target === "gpu" || target === "vram") ? NO_GPU_HINT : "";
    if (detail) detail.textContent = "";
    return;
  }
  number.textContent = value;
  unit.hidden = false;
  bar.style.width = `${Math.min(100, value)}%`;
  el.dataset.level = monitorLevel(value);
  el.title = "";
  if (detail && def.detail) detail.textContent = def.detail(telemetry);
}
