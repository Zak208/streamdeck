"""Updating the installed app from the project's GitHub releases."""

import hashlib
import json
import os
import time
import unittest
import urllib.request
from unittest import mock

import support
from server import main, updater
from server.updater import Updater, UpdateError, parse_version

INSTALLER = b"MZ fake installer bytes" * 100
GOOD_HASH = hashlib.sha256(INSTALLER).hexdigest()
BASE = "https://github.com/Zak208/streamdeck/releases/download/v9.0.0/"


def release(tag="v9.0.0", url=None, digest="sha256:" + GOOD_HASH, with_hash_asset=False, with_installer=True):
    assets = []
    if with_installer:
        asset = {"name": "instalador_streamdeck.exe", "size": len(INSTALLER),
                 "browser_download_url": url or BASE + "instalador_streamdeck.exe"}
        if digest:
            asset["digest"] = digest
        assets.append(asset)
    if with_hash_asset:
        assets.append({"name": "instalador_streamdeck.exe.sha256", "browser_download_url": BASE + "instalador_streamdeck.exe.sha256"})
    return {"tag_name": tag, "body": "Novedades", "html_url": "https://github.com/Zak208/streamdeck/releases/tag/" + tag, "assets": assets}


class VersionTests(unittest.TestCase):
    def test_versions_parse_and_compare_as_numbers(self):
        self.assertEqual(parse_version("v2.12.0"), (2, 12, 0))
        self.assertEqual(parse_version("2.9.1"), (2, 9, 1))
        self.assertGreater(parse_version("2.12.0"), parse_version("2.9.9"))  # not a text comparison
        for bad in ("", None, "latest", "v2.12", "2.12.0-beta", "v2.12.0.1", "v2.x.0", "<b>"):
            self.assertIsNone(parse_version(bad), bad)


class CheckTests(unittest.TestCase):
    def check(self, data, current="2.12.0"):
        with mock.patch.object(updater, "_fetch_json", return_value=data):
            return Updater().release_info(current)

    def test_a_newer_release_with_an_installer_is_an_update(self):
        info = self.check(release("v2.13.0"))
        self.assertTrue(info["update_available"])
        self.assertEqual((info["latest_version"], info["current_version"]), ("2.13.0", "2.12.0"))
        self.assertEqual(info["notes"], "Novedades")

    def test_the_same_or_an_older_release_is_not(self):
        for tag in ("v2.12.0", "v2.11.9", "v1.0.0"):
            with self.subTest(tag=tag):
                self.assertFalse(self.check(release(tag))["update_available"])

    def test_a_release_without_the_installer_is_not_offered(self):
        info = self.check(release("v3.0.0", with_installer=False))
        self.assertFalse(info["update_available"])
        self.assertEqual(info["status"], "release_without_installer")

    def test_a_tag_that_is_not_a_version_is_ignored(self):
        self.assertFalse(self.check(release("nightly"))["update_available"])

    def test_github_is_asked_once_in_ten_minutes(self):
        fetch = mock.Mock(return_value=release("v2.13.0"))
        checker = Updater()
        with mock.patch.object(updater, "_fetch_json", fetch):
            checker.release_info("2.12.0")
            checker.release_info("2.12.0")
            self.assertEqual(fetch.call_count, 1)
            checker.release_info("2.12.0", force=True)
            self.assertEqual(fetch.call_count, 2)


class ReleaseFilesTests(unittest.TestCase):
    def files(self, data, text=None):
        checker = Updater()
        with mock.patch.object(updater, "_fetch_json", return_value=data), mock.patch.object(updater, "_fetch_text", return_value=text or ""):
            checker.release_info("2.12.0")
            return checker._release_files()

    def test_the_hash_comes_from_github_digest(self):
        url, expected, tag = self.files(release())
        self.assertEqual((url, expected, tag), (BASE + "instalador_streamdeck.exe", GOOD_HASH, "v9.0.0"))

    def test_or_from_the_sha256_file_of_the_release(self):
        _, expected, _ = self.files(release(digest=None, with_hash_asset=True), text=GOOD_HASH + "  instalador_streamdeck.exe\n")
        self.assertEqual(expected, GOOD_HASH)

    def test_without_any_hash_nothing_is_installed(self):
        with self.assertRaises(UpdateError):
            self.files(release(digest=None))
        with self.assertRaises(UpdateError):
            self.files(release(digest="sha256:nothex"))
        with self.assertRaises(UpdateError):
            self.files(release(digest=None, with_hash_asset=True), text="not a hash")

    def test_only_the_projects_own_download_address_is_used(self):
        for url in ("https://evil.example/instalador_streamdeck.exe",
                    "https://github.com/OtroUsuario/streamdeck/releases/download/v9.0.0/instalador_streamdeck.exe",
                    "http://github.com/Zak208/streamdeck/releases/download/v9.0.0/instalador_streamdeck.exe",
                    "https://github.com/Zak208/streamdeck/releases/download/v9.0.0/otro.exe",
                    "https://github.com.evil.example/Zak208/streamdeck/releases/download/v9.0.0/instalador_streamdeck.exe",
                    "https://github.com/Zak208/streamdeck/releases/download/v9.0.0/instalador_streamdeck.exe?x=1",
                    "file:///C:/Windows/System32/cmd.exe"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                self.files(release(url=url))


class InstallFlowTests(unittest.TestCase):
    def run_flow(self, installer_bytes=INSTALLER, data=None, current="2.12.0"):
        checker = Updater()
        launched = []

        def fake_download(url, destination, progress):
            progress(0.5)
            with open(destination, "wb") as handle:
                handle.write(installer_bytes)

        with mock.patch.object(updater, "_fetch_json", return_value=data or release()), \
                mock.patch.object(updater, "_download", fake_download), \
                mock.patch.object(updater, "_launch", lambda path: launched.append(path)), \
                mock.patch.object(updater, "_exit_soon") as exit_soon:
            checker._run(current)
        return checker.status(), launched, exit_soon

    def test_a_good_download_is_checked_and_the_installer_is_started(self):
        status, launched, exit_soon = self.run_flow()
        self.assertEqual(status["state"], "installing")
        self.assertEqual(len(launched), 1)
        self.assertTrue(launched[0].endswith("instalador_streamdeck.exe"))
        exit_soon.assert_called_once()

    def test_a_download_that_does_not_match_the_hash_is_discarded_and_never_run(self):
        status, launched, exit_soon = self.run_flow(installer_bytes=INSTALLER + b"tampered")
        self.assertEqual(status["state"], "error")
        self.assertIn("SHA-256", status["message"])
        self.assertEqual(launched, [])
        exit_soon.assert_not_called()

    def test_no_update_means_nothing_is_downloaded(self):
        status, launched, _ = self.run_flow(data=release("v2.12.0"))
        self.assertEqual(status["state"], "error")
        self.assertIn("última versión", status["message"])
        self.assertEqual(launched, [])

    def test_a_network_failure_is_reported_not_raised(self):
        checker = Updater()
        with mock.patch.object(updater, "_fetch_json", side_effect=OSError("sin red")):
            checker._run("2.12.0")
        self.assertEqual(checker.status()["state"], "error")
        self.assertIn("sin red", checker.status()["message"])

    def test_a_second_click_while_it_runs_does_not_start_another(self):
        checker = Updater()
        checker.state = {"state": "downloading", "progress": 0.2, "message": ""}
        with mock.patch("threading.Thread") as thread:
            self.assertFalse(checker.start("2.12.0"))
        thread.assert_not_called()

    def test_the_installer_is_started_silently_and_closes_the_running_app(self):
        with mock.patch.object(updater.subprocess, "Popen") as popen:
            updater._launch("C:\\Temp\\instalador_streamdeck.exe")
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "C:\\Temp\\instalador_streamdeck.exe")
        self.assertIn("/VERYSILENT", command)
        self.assertIn("/CLOSEAPPLICATIONS", command)


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def get(self, path):
        with urllib.request.urlopen(self.live.base_url + path, timeout=10) as response:
            return json.loads(response.read().decode())

    def test_the_installed_app_reports_releases(self):
        with mock.patch.object(main, "FROZEN", True), mock.patch.object(updater, "_fetch_json", return_value=release("v99.0.0")):
            main.updater.updater._cache = None
            body = self.get("/api/system/check-update")
        self.assertEqual((body["mode"], body["update_available"], body["latest_version"]), ("release", True, "99.0.0"))
        self.assertTrue(body["can_update"])

    def test_offline_is_reported_without_an_error(self):
        with mock.patch.object(main, "FROZEN", True), mock.patch.object(updater, "_fetch_json", side_effect=OSError("sin red")):
            main.updater.updater._cache = None
            body = self.get("/api/system/check-update")
        self.assertFalse(body["update_available"])
        self.assertEqual(body["status"], "offline")

    def test_the_status_route_exists_and_is_idle_at_first(self):
        self.assertIn(self.get("/api/system/update-status")["state"], ("idle", "error"))

    def test_the_update_routes_are_closed_to_the_network(self):
        paths = {route.path: route for route in main.app.routes if hasattr(route, "path")}
        for path in ("/api/system/check-update", "/api/system/apply-update", "/api/system/update-status"):
            deps = [d.call.__name__ for d in paths[path].dependant.dependencies]
            self.assertIn("require_local_request", deps, path)


if __name__ == "__main__":
    unittest.main()
