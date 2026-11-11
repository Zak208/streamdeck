import ctypes
import json
import unittest
import urllib.error
import urllib.request
import uuid
import winreg
from unittest import mock

import support
from server import desktop
from server.settings_store import settings


def call(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                     method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


class AutostartTests(unittest.TestCase):
    """Uses a throwaway registry key, never the real Windows start-up list."""

    def setUp(self):
        self.key = rf"Software\StreamDeskTest-{uuid.uuid4().hex}\Run"
        patcher = mock.patch.object(desktop, "RUN_KEY", self.key)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.drop_key)

    def drop_key(self):
        for path in (self.key, self.key.rsplit("\\", 1)[0]):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass

    def test_it_is_off_until_turned_on_and_off_again_after(self):
        self.assertFalse(desktop.autostart_enabled())
        desktop.set_autostart(True)
        self.assertTrue(desktop.autostart_enabled())
        desktop.set_autostart(False)
        self.assertFalse(desktop.autostart_enabled())
        desktop.set_autostart(False)  # turning off what is already off is not an error

    def test_windows_starts_it_hidden_in_the_tray(self):
        desktop.set_autostart(True)
        self.assertTrue(desktop._read_run_value().endswith(" " + desktop.BACKGROUND_FLAG))

    def test_a_fresh_install_starts_with_windows_but_an_existing_one_is_left_alone(self):
        with mock.patch.object(desktop, "FROZEN", True), mock.patch.object(desktop, "settings") as store:
            store.get.return_value = {}
            desktop.prepare_autostart()
            self.assertTrue(desktop.autostart_enabled())
            desktop.set_autostart(False)
            store.get.return_value = {"first_run_completed": True}  # someone who was already using it
            desktop.prepare_autostart()
            self.assertFalse(desktop.autostart_enabled())
            store.get.return_value = {"autostart_decided": True}  # a fresh install whose owner switched it off
            desktop.prepare_autostart()
            self.assertFalse(desktop.autostart_enabled())

    def test_running_from_source_never_registers_itself(self):
        with mock.patch.object(desktop, "FROZEN", False), mock.patch.object(desktop, "settings") as store:
            store.get.return_value = {}
            desktop.prepare_autostart()
        self.assertFalse(desktop.autostart_enabled())

    def test_a_moved_install_is_repointed(self):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, desktop.RUN_VALUE, 0, winreg.REG_SZ, r'"C:\old place\StreamDesk.exe" --background')
        desktop.prepare_autostart()
        self.assertEqual(desktop._read_run_value(), desktop.launch_command())


class SingleInstanceTests(unittest.TestCase):
    def test_a_second_copy_is_refused_and_the_first_can_be_found(self):
        name = r"Local\StreamDeskPro.Test." + uuid.uuid4().hex
        with mock.patch.object(desktop, "MUTEX_NAME", name), mock.patch.object(desktop, "_mutex_handle", None):
            self.assertTrue(desktop.acquire_single_instance())
            self.assertFalse(desktop.acquire_single_instance())

    def test_asking_a_copy_that_is_not_running_just_says_no(self):
        self.assertFalse(desktop.ask_running_instance_to_show(port=support.free_port()))


class BusyPortTests(unittest.TestCase):
    """The warning a user sees instead of a blank window when something else holds the port. No window is shown."""

    def setUp(self):
        import app_desktop
        self.app = app_desktop

    def test_a_free_port_is_not_reported(self):
        with mock.patch.object(self.app, "PORT", support.free_port()):
            self.assertFalse(self.app.explain_busy_port())

    def test_a_busy_port_is_reported_with_who_holds_it(self):
        import socket
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen()
            port = holder.getsockname()[1]
            with mock.patch.object(self.app, "PORT", port),                     mock.patch.object(self.app, "port_owner", return_value="obs64.exe"),                     mock.patch.object(ctypes, "windll") as windll:
                self.assertTrue(self.app.explain_busy_port())
            text = windll.user32.MessageBoxW.call_args.args[1]
        self.assertIn("obs64.exe", text)
        self.assertIn(str(port), text)

    def test_the_owner_of_a_port_is_found_by_name(self):
        import socket
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen()
            name = self.app.port_owner(holder.getsockname()[1])
        self.assertTrue(name.lower().startswith("python"), name)


class DesktopApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = support.LiveServer().__enter__()
        cls.addClassCleanup(cls.server.__exit__, None, None, None)

    def setUp(self):
        self.url = self.server.base_url
        self.addCleanup(settings.clear, "app")
        for name in ("show", "quit"):
            self.addCleanup(setattr, desktop.controller, name, None)

    def test_keeping_running_is_on_by_default_and_can_be_turned_off(self):
        status, state = call(f"{self.url}/api/settings/desktop")
        self.assertEqual(status, 200)
        self.assertTrue(state["keep_running"])
        status, state = call(f"{self.url}/api/settings/desktop", {"keep_running": False})
        self.assertFalse(state["keep_running"])
        self.assertFalse(desktop.keep_running())

    def test_the_settings_only_take_true_or_false(self):
        status, _ = call(f"{self.url}/api/settings/desktop", {"keep_running": "no"})
        self.assertEqual(status, 422)
        status, _ = call(f"{self.url}/api/settings/desktop", {"autostart": 1})
        self.assertEqual(status, 422)

    def test_without_a_window_the_show_and_quit_calls_do_nothing(self):
        self.assertEqual(call(f"{self.url}/api/desktop/show", {})[1], {"shown": False})
        self.assertEqual(call(f"{self.url}/api/desktop/quit", {})[1], {"quitting": False})
        self.assertFalse(call(f"{self.url}/api/settings/desktop")[1]["window"])

    def test_with_a_window_they_reach_it(self):
        shown, quit_ = mock.Mock(), mock.Mock()
        desktop.controller.show, desktop.controller.quit = shown, quit_
        self.assertTrue(call(f"{self.url}/api/settings/desktop")[1]["window"])
        self.assertEqual(call(f"{self.url}/api/desktop/show", {})[1], {"shown": True})
        shown.assert_called_once()
        quit_.assert_not_called()
        self.assertEqual(call(f"{self.url}/api/desktop/quit", {})[1], {"quitting": True})
        quit_.assert_called_once()

    def test_a_page_in_the_browser_cannot_close_or_reconfigure_the_app(self):
        for path in ("/api/desktop/quit", "/api/desktop/show", "/api/settings/desktop"):
            request = urllib.request.Request(self.url + path, data=b"{}", method="POST", headers={
                "Content-Type": "application/json", "Host": "evil.example", "Origin": "http://evil.example"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=10)
            self.assertEqual(caught.exception.code, 403, path)


if __name__ == "__main__":
    unittest.main()
