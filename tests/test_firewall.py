import json
import subprocess
import unittest
import urllib.request
from unittest import mock

import support
from server import diagnostics, firewall
from server.paths import PORT


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode())


def post_json(url):
    request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


class FirewallTests(unittest.TestCase):
    """None of these touch the real firewall: the elevated command is never run."""

    def test_rule_only_opens_the_streamdesk_port_to_the_local_network(self):
        arguments = firewall.rule_arguments()
        self.assertIn(f"localport={PORT}", arguments)
        self.assertIn("remoteip=localsubnet", arguments)  # nothing outside the user's own network
        self.assertIn("dir=in", arguments)
        self.assertIn("protocol=TCP", arguments)
        self.assertTrue(firewall.RULE_NAME.isascii())

    def test_rule_exists_follows_the_netsh_result(self):
        for code, expected in ((0, True), (1, False)):
            with self.subTest(code=code), mock.patch.object(firewall.subprocess, "run", return_value=mock.Mock(returncode=code)):
                self.assertIs(firewall.rule_exists(), expected)
        with mock.patch.object(firewall.subprocess, "run", side_effect=subprocess.TimeoutExpired("netsh", 10)):
            self.assertIs(firewall.rule_exists(), False)

    def test_pressing_the_button_asks_windows_for_permission(self):
        windll = mock.Mock()
        windll.shell32.ShellExecuteW.return_value = 42  # ShellExecute reports success above 32
        with mock.patch.object(firewall, "rule_exists", return_value=False), mock.patch.object(firewall.ctypes, "windll", windll):
            result = firewall.request_rule()
        self.assertEqual(result, {"requested": True})
        verb, program, arguments = windll.shell32.ShellExecuteW.call_args.args[1:4]
        self.assertEqual((verb, program), ("runas", "netsh"))  # runas = Windows shows its own confirmation
        self.assertEqual(arguments, firewall.rule_arguments())

    def test_declining_the_windows_prompt_is_explained(self):
        windll = mock.Mock()
        windll.shell32.ShellExecuteW.return_value = firewall.SE_ERR_ACCESSDENIED
        with mock.patch.object(firewall, "rule_exists", return_value=False), mock.patch.object(firewall.ctypes, "windll", windll):
            result = firewall.request_rule()
        self.assertIs(result["requested"], False)
        self.assertIn("Sí", result["error"])

    def test_nothing_is_asked_when_the_rule_already_exists(self):
        windll = mock.Mock()
        with mock.patch.object(firewall, "rule_exists", return_value=True), mock.patch.object(firewall.ctypes, "windll", windll):
            self.assertEqual(firewall.request_rule(), {"requested": False, "already": True})
        windll.shell32.ShellExecuteW.assert_not_called()

    def test_endpoints_report_and_request_without_changing_anything(self):
        with support.LiveServer() as server, \
                mock.patch.object(firewall, "rule_exists", return_value=False), \
                mock.patch.object(firewall, "request_rule", return_value={"requested": True}) as request:
            diagnostics.clear()
            self.assertEqual(get_json(f"{server.base_url}/api/system/firewall"), {"allowed": False, "rule": False, "port": PORT})
            self.assertEqual(post_json(f"{server.base_url}/api/system/firewall/allow"), {"requested": True})
        request.assert_called_once()


    def test_no_warning_once_a_phone_has_got_through(self):
        # Windows can create its own rule under another name; a phone that connected proves it is open.
        with support.LiveServer() as server, mock.patch.object(firewall, "rule_exists", return_value=False):
            diagnostics.clear()
            self.assertFalse(get_json(f"{server.base_url}/api/system/firewall")["allowed"])
            diagnostics.record("ok", "Móvil conectado", "192.168.2.84", "Android")
            status = get_json(f"{server.base_url}/api/system/firewall")
            self.assertEqual((status["allowed"], status["rule"]), (True, False))
            diagnostics.clear()


if __name__ == "__main__":
    unittest.main()
