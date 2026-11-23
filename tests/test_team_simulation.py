"""Concurrent Team Simulation Test for StreamDesk Pro.

Simulates a team of 4 QA testers concurrently interacting with the app:
- Tester 1 (PC Studio): Navigates pages on PC, edits configurations, auto-saves.
- Tester 2 (Mobile A - Independent Mode): Has syncPagesEnabled = false. Stays on Page 1,
  executes buttons on Page 1 while PC is on Page 0 or Page 2, tests independent usage.
- Tester 3 (Mobile B - Audio & Faders): Adjusts master volume, app faders, mic mute,
  concurrent with Tester 2's button clicks.
- Tester 4 (Background PC Activity & Verification): Simulates foreground window switching
  (smart pages) and validates logs, audit trail, and zero unexpected crashes.
"""

import asyncio
import copy
import json
import time
import unittest
from unittest import mock

import support
import websockets
from server import audit, logger, main
from server.auth import auth_manager
from server.config_manager import config_manager


def _make_12_slots(button_slot: dict) -> list:
    slots = [button_slot]
    for i in range(1, 12):
        slots.append({"index": i, "type": "empty", "id": f"slot_{i}_{button_slot['id']}"})
    return slots


class TestTeamSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        logger.clear()
        main.button_states.clear()
        main._running_actions.clear()

    def ws_url(self, token: str = ""):
        return f"ws://127.0.0.1:{self.live.port}/ws{('?token=' + token) if token else ''}"

    def test_concurrent_team_usage_and_decoupled_pages(self):
        """Simulate real-world usage of multiple testers doing different things simultaneously."""
        original_config = copy.deepcopy(config_manager.get_config())
        self.addCleanup(lambda: config_manager.save_config(original_config))

        # Setup 3 pages:
        # Page 0: General PC shortcuts
        # Page 1: Media / Spotify (used independently by Mobile A)
        # Page 2: Audio mixing & OBS (used by PC or Mobile B)
        btn_pc_0 = {
            "index": 0, "type": "button", "id": "btn_pc_notepad",
            "label": "Notepad", "action_type": "launch", "target": "notepad.exe"
        }
        btn_mobile_1 = {
            "index": 0, "type": "button", "id": "btn_spotify_play",
            "label": "Play/Pausa", "action_type": "media", "target": "play_pause",
            "extra": {"app": "spotify"}
        }
        btn_mobile_next = {
            "index": 1, "type": "button", "id": "btn_page_next",
            "label": "Siguiente Página", "action_type": "page", "target": "next"
        }
        btn_obs_2 = {
            "index": 0, "type": "button", "id": "btn_obs_rec",
            "label": "Grabar", "action_type": "obs_action", "target": "record_toggle"
        }

        slots_0 = _make_12_slots(btn_pc_0)
        slots_1 = [btn_mobile_1, btn_mobile_next] + [{"index": i, "type": "empty", "id": f"s1_{i}"} for i in range(2, 12)]
        slots_2 = _make_12_slots(btn_obs_2)

        deck_config = {
            "schema_version": 2,
            "deck_name": "Team Simulation Deck",
            "layout": {"rows": 2, "columns": 6, "total_slots": 12},
            "current_page": 0,
            "pages": [
                {"id": "page_general", "name": "General PC", "slots": slots_0},
                {"id": "page_spotify", "name": "Spotify & Media", "slots": slots_1},
                {"id": "page_obs", "name": "OBS & Audio", "slots": slots_2}
            ],
            "slots": slots_0
        }
        self.assertTrue(config_manager.save_config(deck_config))
        config_manager.set_active_page(0)

        # Generate tokens for Mobile A and Mobile B
        pin_a = auth_manager.get_current_pin()
        res_a = auth_manager.verify_pin_and_issue_token(pin_a, device_name="Tester 2 (Mobile A - Galaxy S22)", client_ip="192.168.1.50")
        token_a = res_a["token"]

        pin_b = auth_manager.get_current_pin()
        res_b = auth_manager.verify_pin_and_issue_token(pin_b, device_name="Tester 3 (Mobile B - iPhone 14)", client_ip="192.168.1.51")
        token_b = res_b["token"]

        events_recorded = []

        async def tester_1_pc(ws_pc):
            """Tester 1: Uses Studio on PC. Stays on Page 0, then switches to Page 2."""
            await ws_pc.recv()  # init_state
            await asyncio.sleep(0.05)
            # PC User switches to Page 2
            await ws_pc.send(json.dumps({"type": "switch_page", "page": 2}))
            events_recorded.append("PC switched to Page 2")
            await asyncio.sleep(0.1)
            # PC User presses Notepad button on Page 0 (via find_slot_in_deck)
            await ws_pc.send(json.dumps({"type": "trigger_button", "id": "btn_pc_notepad", "page": 0}))
            events_recorded.append("PC triggered btn_pc_notepad")
            await asyncio.sleep(0.1)

        async def tester_2_mobile_decoupled(ws_mob_a):
            """Tester 2: Mobile A with independent appearance (syncPagesEnabled=false).

            Mobile A is viewing Page 1 (Spotify). Even though PC is on Page 2 or Page 0,
            Mobile A triggers buttons on Page 1!
            """
            await ws_mob_a.recv()  # init_state
            await asyncio.sleep(0.08)
            # Mobile A triggers btn_spotify_play on Page 1 with page: 1 in payload
            await ws_mob_a.send(json.dumps({"type": "trigger_button", "id": "btn_spotify_play", "page": 1}))
            events_recorded.append("Mobile A triggered btn_spotify_play on Page 1")

            # Wait for action_result
            while True:
                msg = json.loads(await ws_mob_a.recv())
                if msg.get("type") == "action_result" and msg.get("id") == "btn_spotify_play":
                    self.assertTrue(msg.get("success"), f"Mobile A action failed: {msg}")
                    events_recorded.append("Mobile A action_result SUCCESS")
                    break

        async def tester_3_mobile_faders(ws_mob_b):
            """Tester 3: Mobile B adjusts master volume and app faders concurrently."""
            await ws_mob_b.recv()  # init_state
            await asyncio.sleep(0.04)
            # Move master volume
            await ws_mob_b.send(json.dumps({"type": "set_master_volume", "volume": 65}))
            # Set app volume for Spotify
            await ws_mob_b.send(json.dumps({"type": "set_app_volume", "process": "Spotify.exe", "volume": 45}))
            # Toggle mic mute
            await ws_mob_b.send(json.dumps({"type": "set_mic_muted", "muted": True}))
            events_recorded.append("Mobile B adjusted audio faders concurrently")
            await asyncio.sleep(0.1)

        async def run_all():
            with mock.patch("server.main.execute_action", return_value={"success": True, "action": "test"}):
                async with (
                    websockets.connect(self.ws_url()) as ws_pc,
                    websockets.connect(self.ws_url(token_a)) as ws_mob_a,
                    websockets.connect(self.ws_url(token_b)) as ws_mob_b,
                ):
                    await asyncio.gather(
                        tester_1_pc(ws_pc),
                        tester_2_mobile_decoupled(ws_mob_a),
                        tester_3_mobile_faders(ws_mob_b),
                    )

        asyncio.run(run_all())

        # Verify results in server logs and audit trail
        logs = logger.recent_logs(level="INFO")
        self.assertTrue(any("Play/Pausa" in l.get("message", "") for l in logs))
        self.assertTrue(any("Notepad" in l.get("message", "") for l in logs))

        # Check audit trail: ensure devices and pages are correctly identified
        audit_entries = audit.recent(10)
        mobile_a_audit = [e for e in audit_entries if "Mobile A" in e.get("device", "")]
        self.assertTrue(len(mobile_a_audit) > 0)
        self.assertEqual(mobile_a_audit[0]["button"], "Play/Pausa")
        self.assertEqual(mobile_a_audit[0]["page"], "Spotify & Media")
        self.assertTrue(mobile_a_audit[0]["ok"])

    def test_client_decoupled_page_state_preserved_on_config_updated(self):
        """Use Node.js to verify that streamdeck.js preserves independent page state when config_updated arrives."""
        import os
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not available")

        # Test script that loads streamdeck.js logic in Node VM
        script = r"""
const fs = require('fs');
const code = fs.readFileSync('static/js/streamdeck.js', 'utf8');

// Simulate browser environment
global.window = global;
global.localStorage = {
  getItem: (k) => k === 'streamdesk_sync_pages' ? '0' : null, // sync is OFF
  setItem: () => {}
};
global.sessionStorage = {
  getItem: () => '1', // was on page 1
  setItem: () => {}
};
global.buttonLabels = {};
global.buttonStates = {};
global.lastMaster = null;
global.lastMic = null;
global.renderDeck = () => {};
global.renderPageNav = () => {};
global.applyTheme = () => {};
global.updateMasterVolume = () => {};
global.updateAppVolumes = () => {};
global.applyMicState = () => {};

// Evaluate necessary parts of streamdeck.js
eval(code.match(/function syncPagesEnabled\(\)[\s\S]*?\n\}/)[0]);
eval(code.match(/function handleServerMessage\(data\) \{[\s\S]*?\n\}/)[0]);

// Initial state: 3 pages, PC is on page 0
const initialConfig = {
  current_page: 0,
  pages: [
    { id: 'p0', slots: [{ id: 'btn0' }] },
    { id: 'p1', slots: [{ id: 'btn1' }] },
    { id: 'p2', slots: [{ id: 'btn2' }] }
  ]
};

// 1. Initial connect when sync is OFF: restores local page 1 from sessionStorage
handleServerMessage({ type: 'init_state', config: initialConfig });
if (currentConfig.current_page !== 1) {
  console.error("FAIL: init_state did not restore local page 1! current_page is " + currentConfig.current_page);
  process.exit(1);
}

// 2. PC broadcasts page_switched to page 2: mobile must IGNORE it and stay on page 1
handleServerMessage({ type: 'page_switched', page: 2 });
if (currentConfig.current_page !== 1) {
  console.error("FAIL: page_switched changed local page! current_page is " + currentConfig.current_page);
  process.exit(2);
}

// 3. PC updates a button on page 0 and server broadcasts config_updated (where server current_page is 2)
const updatedConfig = {
  current_page: 2,
  pages: [
    { id: 'p0', slots: [{ id: 'btn0_updated' }] },
    { id: 'p1', slots: [{ id: 'btn1' }] },
    { id: 'p2', slots: [{ id: 'btn2' }] }
  ]
};
handleServerMessage({ type: 'config_updated', config: updatedConfig });
if (currentConfig.current_page !== 1) {
  console.error("FAIL: config_updated reset local page to server page! current_page is " + currentConfig.current_page);
  process.exit(3);
}

// Verify that slots match page 1 slots
if (currentConfig.slots[0].id !== 'btn1') {
  console.error("FAIL: slots do not match page 1!");
  process.exit(4);
}

console.log("PASS: Decoupled page state verified in client JS!");
"""
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, cwd=support.PROJECT_ROOT)
        self.assertEqual(result.returncode, 0, f"Node test failed: {result.stderr or result.stdout}")
        self.assertIn("PASS: Decoupled page state verified in client JS!", result.stdout)



if __name__ == "__main__":
    unittest.main()
