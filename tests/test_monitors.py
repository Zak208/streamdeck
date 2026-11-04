import json
import os
import re
import shutil
import socket
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import support
from server import telemetry as telemetry_module
from server.action_catalog import validate_action
from server.config_manager import DEFAULT_CONFIG
from server.paths import STATIC_DIR
from server.telemetry import Nvml, Telemetry

NODE = shutil.which("node")


def read(path):
    with open(os.path.join(STATIC_DIR, path), encoding="utf-8") as handle:
        return handle.read()


class FakeGpu:
    def __init__(self, reading):
        self.reading = reading

    def read(self):
        return self.reading


def address(ip):
    return SimpleNamespace(family=socket.AF_INET, address=ip)


class TelemetryTests(unittest.TestCase):
    def sample_twice(self, *, gpu=None, ip="192.168.2.81", nics=None, second_net=None, second_disk=None, elapsed=2.0):
        nics = nics or {"Ethernet": [address("192.168.2.81")], "vEthernet (WSL)": [address("172.20.0.1")]}
        per_nic_first = {"Ethernet": SimpleNamespace(bytes_recv=1_000_000, bytes_sent=500_000),
                         "vEthernet (WSL)": SimpleNamespace(bytes_recv=9_000_000_000, bytes_sent=9_000_000_000)}
        per_nic_second = second_net or {"Ethernet": SimpleNamespace(bytes_recv=3_000_000, bytes_sent=700_000),
                                        "vEthernet (WSL)": SimpleNamespace(bytes_recv=9_500_000_000, bytes_sent=9_500_000_000)}
        total = lambda d: SimpleNamespace(bytes_recv=sum(v.bytes_recv for v in d.values()), bytes_sent=sum(v.bytes_sent for v in d.values()))
        net_calls = iter([per_nic_first, per_nic_second])
        current = {}

        def net_io_counters(pernic=False):
            return current["net"] if pernic else total(current["net"])

        disk_first = SimpleNamespace(read_bytes=100_000_000, write_bytes=50_000_000)
        disk_second = second_disk or SimpleNamespace(read_bytes=160_000_000, write_bytes=54_000_000)
        disk_calls = iter([disk_first, disk_second])
        clock = iter([100.0, 100.0 + elapsed])
        meter = Telemetry(lambda: ip, gpu=FakeGpu(gpu))
        psutil = telemetry_module.psutil
        with mock.patch.object(telemetry_module.time, "monotonic", side_effect=lambda: next(clock) if False else None) as _:
            pass
        times = [100.0, 100.0 + elapsed, 100.0 + elapsed]  # the NIC cache also reads the clock
        results = []
        with mock.patch.object(psutil, "net_if_addrs", return_value=nics), \
                mock.patch.object(psutil, "net_io_counters", side_effect=net_io_counters), \
                mock.patch.object(psutil, "disk_io_counters", side_effect=lambda: current["disk"]), \
                mock.patch.object(psutil, "cpu_percent", return_value=12.7), \
                mock.patch.object(psutil, "virtual_memory", return_value=SimpleNamespace(percent=64.2)), \
                mock.patch.object(psutil, "disk_usage", return_value=SimpleNamespace(percent=91.0)):
            for index, (net, disk) in enumerate(((per_nic_first, disk_first), (per_nic_second, disk_second))):
                current["net"], current["disk"] = net, disk
                with mock.patch.object(telemetry_module.time, "monotonic", return_value=100.0 + index * elapsed):
                    results.append(meter.sample())
        return results

    def test_first_sample_has_no_rates_and_the_second_measures_them(self):
        first, second = self.sample_twice()
        self.assertEqual((first["net_down"], first["net_up"], first["disk_read"], first["disk_write"]), (0, 0, 0, 0))
        self.assertEqual(second["net_down"], 1_000_000)  # (3,000,000 - 1,000,000) bytes in 2 s
        self.assertEqual(second["net_up"], 100_000)
        self.assertEqual(second["disk_read"], 30_000_000)
        self.assertEqual(second["disk_write"], 2_000_000)

    def test_only_the_card_the_pc_uses_is_counted(self):
        # The WSL adapter moved 500 MB in the same time; adding it would have made the reading absurd.
        _, second = self.sample_twice()
        self.assertEqual(second["net_down"], 1_000_000)

    def test_without_a_matching_card_the_total_is_used(self):
        _, second = self.sample_twice(ip="10.9.9.9")
        self.assertGreater(second["net_down"], 100_000_000)

    def test_a_counter_that_resets_never_reads_negative(self):
        reset = {"Ethernet": SimpleNamespace(bytes_recv=10, bytes_sent=5), "vEthernet (WSL)": SimpleNamespace(bytes_recv=0, bytes_sent=0)}
        _, second = self.sample_twice(second_net=reset, second_disk=SimpleNamespace(read_bytes=0, write_bytes=0))
        self.assertEqual((second["net_down"], second["net_up"], second["disk_read"], second["disk_write"]), (0, 0, 0, 0))

    def test_percentages_are_integers_and_the_gpu_is_merged_in(self):
        gpu = {"gpu": 37, "vram": 25, "vram_used": 4 * 2 ** 30, "vram_total": 16 * 2 ** 30}
        _, second = self.sample_twice(gpu=gpu)
        self.assertEqual((second["cpu"], second["ram"], second["disk"]), (12, 64, 91))
        self.assertEqual((second["gpu"], second["vram"]), (37, 25))

    def test_a_pc_without_nvidia_reports_none_not_zero(self):
        _, second = self.sample_twice(gpu=None)
        self.assertEqual((second["gpu"], second["vram"], second["vram_used"], second["vram_total"]), (None, None, None, None))


class NvmlTests(unittest.TestCase):
    def test_without_an_nvidia_driver_it_reads_none_and_does_not_keep_trying(self):
        with mock.patch.object(telemetry_module.ctypes, "CDLL", side_effect=OSError) as load:
            nvml = Nvml()
            self.assertIsNone(nvml.read())
            self.assertIsNone(nvml.read())
        self.assertEqual(load.call_count, len(telemetry_module.NVML_CANDIDATES))  # looked once, then gave up

    def test_a_failing_call_reads_none(self):
        library = mock.Mock()
        library.nvmlInit_v2.return_value = 0
        library.nvmlDeviceGetHandleByIndex_v2.return_value = 0
        library.nvmlDeviceGetUtilizationRates.return_value = 999
        with mock.patch.object(telemetry_module.ctypes, "CDLL", return_value=library):
            self.assertIsNone(Nvml().read())


class MonitorTargetTests(unittest.TestCase):
    def test_every_monitor_is_a_valid_action_and_the_default_profile_uses_the_new_ones(self):
        for target in ("cpu", "ram", "disk", "gpu", "vram", "net", "disk_speed"):
            self.assertEqual(validate_action("hardware_monitor", target)["target"], target)
        with self.assertRaises(ValueError):
            validate_action("hardware_monitor", "temperature")
        system = DEFAULT_CONFIG["pages"][2]["slots"]
        shown = {s["target"] for s in system if s.get("action_type") == "hardware_monitor"}
        self.assertTrue({"gpu", "vram", "net", "disk_speed"} <= shown)
        self.assertNotIn("disk", shown)  # disk space was replaced by disk speed

    def test_the_service_reports_every_reading_over_the_live_feed(self):
        import asyncio
        import websockets

        async def scenario(live):
            async with websockets.connect(f"ws://127.0.0.1:{live.port}/ws") as ws:
                for _ in range(20):
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
                    if message["type"] == "telemetry_update":
                        return message

        with support.LiveServer() as live:
            message = asyncio.run(scenario(live))
        for key in ("cpu", "ram", "disk", "gpu", "vram", "vram_used", "vram_total", "net_down", "net_up", "disk_read", "disk_write"):
            self.assertIn(key, message)


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class MonitorModuleTests(unittest.TestCase):
    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const sandbox = { console, JSON, Math, Number, String, Object };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const run = (code) => vm.runInContext(code, sandbox);
const node = () => ({ textContent: "", hidden: false, style: {} });

const percentTile = () => {
  const parts = { span: node(), small: node(), bar: node(), detail: node() };
  const el = { dataset: {}, title: "", querySelector: (selector) => ({
    ".deck-monitor-value span": parts.span, ".deck-monitor-value small": parts.small,
    ".deck-monitor-bar i": parts.bar, ".deck-monitor-detail": parts.detail })[selector] };
  return { el, parts };
};
const rateTile = () => {
  const rows = [0, 1].map(() => ({ span: node(), small: node(), u: node() }));
  const el = { dataset: {}, title: "", querySelector: (selector) => {
    const match = /data-row="(\d)"/.exec(selector);
    if (!match) return undefined;
    const row = rows[Number(match[1])];
    return { querySelector: (inner) => row[inner === "u" ? "u" : inner] };
  } };
  return { el, rows };
};

const out = {};
out.rates = [0, 500, 12_000, 1_500_000, 25_000_000, 1_200_000_000, undefined, null, -5].map((b) => run(`formatRate(${JSON.stringify(b ?? null)})`));
out.levels = [10, 59, 60, 84, 85, 100].map((p) => run(`monitorLevel(${p})`));
out.bytes = run("formatBytes(4 * 2 ** 30)");

const gpu = percentTile();
run(`var gpuTile = null`);
sandbox.gpuEl = gpu.el;
run(`paintMonitor(gpuEl, "deck-monitor", "gpu", { gpu: 72 })`);
out.gpu = { text: gpu.parts.span.textContent, width: gpu.parts.bar.style.width, level: gpu.el.dataset.level, unitHidden: gpu.parts.small.hidden };

const noGpu = percentTile();
sandbox.noGpuEl = noGpu.el;
run(`paintMonitor(noGpuEl, "deck-monitor", "gpu", { gpu: null, vram: null })`);
out.noGpu = { text: noGpu.parts.span.textContent, width: noGpu.parts.bar.style.width, level: noGpu.el.dataset.level, unitHidden: noGpu.parts.small.hidden, title: noGpu.el.title };

const noData = percentTile();
sandbox.noDataEl = noData.el;
run(`paintMonitor(noDataEl, "deck-monitor", "cpu", {})`);
out.noData = { text: noData.parts.span.textContent, title: noData.el.title };

const vram = percentTile();
sandbox.vramEl = vram.el;
run(`paintMonitor(vramEl, "deck-monitor", "vram", { vram: 25, vram_used: 4 * 2 ** 30, vram_total: 16 * 2 ** 30 })`);
out.vram = { text: vram.parts.span.textContent, detail: vram.parts.detail.textContent, level: vram.el.dataset.level };

const net = rateTile();
sandbox.netEl = net.el;
run(`paintMonitor(netEl, "deck-monitor", "net", { net_down: 25_000_000, net_up: 120_000 })`);
out.net = net.rows.map((r) => ({ value: r.span.textContent, unit: r.small.textContent, width: r.u.style.width }));
run(`paintMonitor(netEl, "deck-monitor", "net", { net_down: 5_000_000, net_up: 0 })`);
out.netAfter = net.rows.map((r) => r.u.style.width);

const html = run(`monitorInnerHtml("deck-monitor", "net")`);
out.netHtml = { rows: (html.match(/data-row=/g) || []).length };
out.percentHtml = run(`monitorInnerHtml("slot-monitor", "vram")`);
out.defs = run("Object.keys(MONITORS)");
process.stdout.write(JSON.stringify(out));
"""

    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(["node", "-e", cls.SCRIPT, os.path.join(STATIC_DIR, "js", "monitors.js")],
                               capture_output=True, encoding="utf-8", timeout=30)
        assert probe.returncode == 0, probe.stderr[-600:]
        cls.out = json.loads(probe.stdout)

    def test_rates_use_a_unit_that_reads_at_a_glance(self):
        units = [(r["value"], r["unit"]) for r in self.out["rates"]]
        self.assertEqual(units, [("0", "KB/s"), ("0.5", "KB/s"), ("12", "KB/s"), ("1.5", "MB/s"), ("25", "MB/s"),
                                 ("1.2", "GB/s"), ("0", "KB/s"), ("0", "KB/s"), ("0", "KB/s")])

    def test_levels_turn_amber_at_60_and_red_at_85(self):
        self.assertEqual(self.out["levels"], ["ok", "ok", "warn", "warn", "high", "high"])

    def test_a_percentage_gauge_shows_number_bar_and_level(self):
        self.assertEqual(self.out["gpu"], {"text": 72, "width": "72%", "level": "warn", "unitHidden": False})

    def test_a_pc_without_a_readable_gpu_says_so_instead_of_showing_zero(self):
        self.assertEqual(self.out["noGpu"]["text"], "N/D")
        self.assertEqual((self.out["noGpu"]["width"], self.out["noGpu"]["level"], self.out["noGpu"]["unitHidden"]), ("0%", "na", True))
        self.assertIn("NVIDIA", self.out["noGpu"]["title"])

    def test_no_data_yet_is_not_the_same_as_no_gpu(self):
        self.assertEqual(self.out["noData"], {"text": "--", "title": ""})

    def test_vram_shows_used_and_total(self):
        self.assertEqual(self.out["vram"], {"text": 25, "detail": "4.0 GB / 16.0 GB", "level": "ok"})

    def test_network_gauge_shows_two_rates_with_bars_against_the_recent_peak(self):
        self.assertEqual(self.out["net"][0], {"value": "25", "unit": "MB/s", "width": "100%"})
        self.assertEqual(self.out["net"][1]["unit"], "KB/s")
        self.assertEqual(self.out["netHtml"]["rows"], 2)
        # The peak decays slowly: a drop to 5 MB/s shows as a short bar, not a full one.
        self.assertLess(float(self.out["netAfter"][0].rstrip("%")), 25)

    def test_every_supported_target_has_a_definition(self):
        self.assertEqual(set(self.out["defs"]), {"cpu", "ram", "disk", "gpu", "vram", "net", "disk_speed"})
        self.assertIn("slot-monitor-detail", self.out["percentHtml"])  # VRAM has a detail line

    def test_both_pages_load_the_module_before_their_own_script(self):
        for page, script in (("index.html", "streamdeck.js"), ("studio.html", "studio.js")):
            html = read(page)
            self.assertLess(html.index("/static/js/monitors.js"), html.index(f"/static/js/{script}"), page)


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class DetailSheetTests(unittest.TestCase):
    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const sandbox = { console, JSON, Math, Number, String, Object };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const rows = (t) => JSON.parse(vm.runInContext(`JSON.stringify(monitorDetailRows(${JSON.stringify(t)}))`, sandbox));
const full = { cpu: 12, ram: 53, gpu: 11, vram: 11, vram_used: 1.8 * 2 ** 30, vram_total: 15.9 * 2 ** 30,
  net_down: 4600, net_up: 7500, disk_read: 64000, disk_write: 179000, disk: 92 };
console.log(JSON.stringify({
  full: rows(full),
  noGpu: rows({ ...full, gpu: null, vram: null, vram_used: null, vram_total: null }),
  noData: rows({}),
  vramWithoutDetail: rows({ ...full, vram_used: null }),
}));
"""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run([NODE, "-e", cls.SCRIPT, os.path.join(STATIC_DIR, "js", "monitors.js")],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stderr
        cls.out = json.loads(result.stdout)

    def test_every_reading_is_listed_with_its_unit(self):
        self.assertEqual({row["name"]: row["text"] for row in self.out["full"]}, {
            "CPU": "12 %", "RAM": "53 %", "GPU": "11 %", "VRAM": "11 % · 1.8 GB / 15.9 GB",
            "Red": "↓ 4.6 KB/s · ↑ 7.5 KB/s", "Disco": "Lee 64 KB/s · Escribe 179 KB/s", "Espacio del disco": "92 %"})

    def test_a_pc_without_nvidia_says_so_instead_of_zero(self):
        by_name = {row["name"]: row["text"] for row in self.out["noGpu"]}
        self.assertEqual((by_name["GPU"], by_name["VRAM"]), ("N/D", "N/D"))

    def test_before_the_first_reading_nothing_is_invented(self):
        self.assertTrue(all(row["text"] == "--" for row in self.out["noData"]), self.out["noData"])

    def test_vram_without_sizes_shows_only_the_percentage(self):
        self.assertEqual({r["name"]: r["text"] for r in self.out["vramWithoutDetail"]}["VRAM"], "11 %")

    def test_tapping_a_gauge_on_the_phone_opens_the_sheet_without_calling_the_pc(self):
        js = read("js/streamdeck.js")
        body = js[js.index("function createMonitorElement"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("openSystemDetail()", body)
        self.assertNotIn("sendWS", body)  # a gauge never triggers anything on the PC: it must not pull the user out of a game
        self.assertIn('id="detail-sheet"', read("index.html"))


if __name__ == "__main__":
    unittest.main()
