"""Live readings of the PC for the gauge buttons: CPU, RAM, disk, GPU, VRAM, network and disk speed.

GPU and VRAM come from NVIDIA's NVML library, which ships with every NVIDIA driver (nvml.dll). Other
vendors expose no equivalent we can read without extra software, so for them those two read as None and
the gauges say "N/D" instead of inventing a number. Network and disk speed are rates computed from
psutil's byte counters between two samples.
"""

import ctypes
import os
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional

import psutil

NVML_CANDIDATES = ("nvml.dll", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll")


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class Nvml:
    """The first NVIDIA GPU. Loads lazily and stays quiet when there is no NVIDIA driver."""

    def __init__(self) -> None:
        self._lib = None
        self._handle = None
        self._tried = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        self._tried = True
        for path in NVML_CANDIDATES:
            try:
                lib = ctypes.CDLL(path)
            except OSError:
                continue
            try:
                lib.nvmlInit_v2.restype = ctypes.c_int
                lib.nvmlInit_v2.argtypes = []
                lib.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
                lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
                lib.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
                lib.nvmlDeviceGetUtilizationRates.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Utilization)]
                lib.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
                lib.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Memory)]

                handle = ctypes.c_void_p()
                if lib.nvmlInit_v2() == 0 and lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                    self._lib, self._handle = lib, handle
                    return
            except Exception:
                continue

    def read(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._tried:
                self._load()
            if self._lib is None or self._handle is None:
                return None
            try:
                usage, memory = _Utilization(), _Memory()
                if self._lib.nvmlDeviceGetUtilizationRates(self._handle, ctypes.byref(usage)) != 0:
                    return None
                if self._lib.nvmlDeviceGetMemoryInfo(self._handle, ctypes.byref(memory)) != 0:
                    return None
                return {
                    "gpu": int(usage.gpu),
                    "vram": round(memory.used * 100 / memory.total) if memory.total else 0,
                    "vram_used": int(memory.used),
                    "vram_total": int(memory.total),
                }
            except Exception:
                return None


class Telemetry:
    def __init__(self, local_ip: Callable[[], str], gpu: Optional[Nvml] = None) -> None:
        self._local_ip = local_ip
        self._gpu = gpu or Nvml()
        self._last_time: Optional[float] = None
        self._last_net: Optional[tuple] = None
        self._last_disk: Optional[tuple] = None
        self._nic: Optional[str] = None
        self._nic_checked = 0.0

    def _network_card(self) -> Optional[str]:
        """The card the PC reaches the network through. Counting every adapter would double count
        traffic that also crosses a virtual one (WSL, VPN) and add the loopback."""
        now = time.monotonic()
        if now - self._nic_checked > 30:
            self._nic_checked = now
            self._nic = None
            try:
                ip = self._local_ip()
                for name, addresses in psutil.net_if_addrs().items():
                    if any(a.family == socket.AF_INET and a.address == ip for a in addresses):
                        self._nic = name
                        break
            except Exception:
                self._nic = None
        return self._nic

    def _net_counters(self) -> tuple:
        card = self._network_card()
        if card:
            counters = psutil.net_io_counters(pernic=True).get(card)
            if counters:
                return counters.bytes_recv, counters.bytes_sent
        total = psutil.net_io_counters()
        return total.bytes_recv, total.bytes_sent

    def sample(self) -> Dict[str, Any]:
        now = time.monotonic()
        net = self._net_counters()
        disk_io = psutil.disk_io_counters()
        disk = (disk_io.read_bytes, disk_io.write_bytes) if disk_io else (0, 0)

        elapsed = (now - self._last_time) if self._last_time is not None else 0
        def rate(current: int, previous: Optional[int]) -> int:
            if previous is None or elapsed <= 0:
                return 0
            return max(0, int((current - previous) / elapsed))  # a counter that reset must not read as negative

        reading: Dict[str, Any] = {
            "cpu": int(psutil.cpu_percent()),
            "ram": int(psutil.virtual_memory().percent),
            "disk": int(psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").percent),
            "net_down": rate(net[0], self._last_net[0] if self._last_net else None),
            "net_up": rate(net[1], self._last_net[1] if self._last_net else None),
            "disk_read": rate(disk[0], self._last_disk[0] if self._last_disk else None),
            "disk_write": rate(disk[1], self._last_disk[1] if self._last_disk else None),
        }
        gpu = self._gpu.read()
        reading.update(gpu if gpu else {"gpu": None, "vram": None, "vram_used": None, "vram_total": None})
        self._last_time, self._last_net, self._last_disk = now, net, disk
        return reading
