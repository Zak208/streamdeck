import unittest
from unittest import mock
import psutil

from server.audio_controller import AudioController
from server import actions


class FakeProcess:
    def __init__(self, name=None, pid=1234, raise_error=None):
        self._name = name
        self.pid = pid
        self._error = raise_error

    def name(self):
        if self._error:
            raise self._error
        return self._name


class FakeSimpleAudioVolume:
    def __init__(self, volume=0.5, muted=False):
        self._volume = volume
        self._muted = muted

    def GetMasterVolume(self):
        return self._volume

    def SetMasterVolume(self, vol, _):
        self._volume = vol

    def GetMute(self):
        return self._muted

    def SetMute(self, muted, _):
        self._muted = muted


class FakeSession:
    def __init__(self, proc=None, volume=0.5, muted=False):
        self.Process = proc
        self.volume_ctrl = FakeSimpleAudioVolume(volume, muted)

    @property
    def _ctl(self):
        m = mock.Mock()
        m.QueryInterface.return_value = self.volume_ctrl
        return m


class AudioResilienceTests(unittest.TestCase):
    def test_get_audio_sessions_ignores_dead_or_denied_processes(self):
        dead_proc = FakeProcess(raise_error=psutil.NoSuchProcess(15512))
        denied_proc = FakeProcess(raise_error=psutil.AccessDenied(9999))
        live_proc1 = FakeProcess(name="Spotify.exe", pid=2000)
        live_proc2 = FakeProcess(name="Discord.exe", pid=3000)

        sessions = [
            FakeSession(proc=dead_proc),
            FakeSession(proc=denied_proc),
            FakeSession(proc=live_proc1, volume=0.25),
            FakeSession(proc=live_proc2, volume=0.8),
        ]

        controller = AudioController()
        with mock.patch("server.audio_controller.AudioUtilities.GetAllSessions", return_value=sessions):
            result = controller.get_audio_sessions()

        self.assertEqual(len(result), 2)
        names = [r["process_name"] for r in result]
        self.assertIn("Spotify.exe", names)
        self.assertIn("Discord.exe", names)
        spotify_entry = next(r for r in result if r["process_name"] == "Spotify.exe")
        self.assertEqual(spotify_entry["volume"], 25)

    def test_set_app_volume_matches_with_or_without_extension_and_skips_dead_processes(self):
        dead_proc = FakeProcess(raise_error=psutil.NoSuchProcess(15512))
        spot1 = FakeSession(proc=FakeProcess(name="Spotify.exe", pid=101), volume=0.1)
        spot2 = FakeSession(proc=FakeProcess(name="Spotify.exe", pid=102), volume=0.1)
        discord = FakeSession(proc=FakeProcess(name="Discord.exe", pid=201), volume=0.5)

        sessions = [FakeSession(proc=dead_proc), spot1, discord, spot2]
        controller = AudioController()

        with mock.patch("server.audio_controller.AudioUtilities.GetAllSessions", return_value=sessions):
            # Target without extension
            res = controller.set_app_volume("spotify", 45)
            self.assertTrue(res["success"])
            self.assertEqual(round(spot1.volume_ctrl._volume * 100), 45)
            self.assertEqual(round(spot2.volume_ctrl._volume * 100), 45)
            self.assertEqual(round(discord.volume_ctrl._volume * 100), 50)

            # Target with extension
            res2 = controller.set_app_volume("Spotify.exe", 70)
            self.assertTrue(res2["success"])
            self.assertEqual(round(spot1.volume_ctrl._volume * 100), 70)
            self.assertEqual(round(spot2.volume_ctrl._volume * 100), 70)

    def test_toggle_app_mute_mutes_all_matching_sessions(self):
        dead_proc = FakeProcess(raise_error=psutil.NoSuchProcess(15512))
        spot1 = FakeSession(proc=FakeProcess(name="Spotify.exe", pid=101), muted=False)
        spot2 = FakeSession(proc=FakeProcess(name="Spotify.exe", pid=102), muted=False)

        sessions = [FakeSession(proc=dead_proc), spot1, spot2]
        controller = AudioController()

        with mock.patch("server.audio_controller.AudioUtilities.GetAllSessions", return_value=sessions):
            res = controller.toggle_app_mute("spotify")
            self.assertTrue(res["success"])
            self.assertTrue(res["muted"])
            self.assertTrue(spot1.volume_ctrl._muted)
            self.assertTrue(spot2.volume_ctrl._muted)


class MediaCommandTests(unittest.TestCase):
    def test_media_action_sends_vk_and_posts_to_spotify(self):
        with mock.patch.object(actions, "send_vk_key", return_value=True) as mock_vk, \
             mock.patch.object(actions, "_post_spotify_media_command") as mock_spotify:
            res = actions.execute_action("media", "play_pause")
            self.assertTrue(res["success"])
            mock_vk.assert_called_once_with(actions.VK_MEDIA_PLAY_PAUSE)
            mock_spotify.assert_called_once_with("play_pause")


class ForegroundIndependenceTests(unittest.TestCase):
    def test_hotkey_alt_shift_b_intercepted_without_sending_keys(self):
        """Verifies that pressing 'Me gusta' bound to ALT+SHIFT+B never sends 'B' to the active window (e.g. Valorant buy menu)."""
        with mock.patch.object(actions, "send_hotkey") as mock_send_hotkey, \
             mock.patch("server.connectors.spotify.toggle_like", return_value={"success": True, "action": "spotify_action"}) as mock_like:
            res = actions.execute_action("hotkey", "ALT+SHIFT+B")
            self.assertTrue(res["success"])
            mock_like.assert_called_once()
            mock_send_hotkey.assert_not_called()

    def test_hotkey_permutations_intercepted(self):
        """Checks various case and ordering permutations of ALT+SHIFT+B."""
        for combo in ("SHIFT+ALT+B", "alt+shift+b", "B+SHIFT+ALT", "Alt+Shift+B"):
            with self.subTest(combo=combo):
                with mock.patch.object(actions, "send_hotkey") as mock_send_hotkey, \
                     mock.patch("server.connectors.spotify.toggle_like", return_value={"success": True, "action": "spotify_action"}) as mock_like:
                    res = actions.execute_action("hotkey", combo)
                    self.assertTrue(res["success"])
                    mock_like.assert_called_once()
                    mock_send_hotkey.assert_not_called()

    def test_other_hotkeys_still_sent(self):
        """Verifies that non-intercepted hotkeys still use send_hotkey."""
        with mock.patch.object(actions, "send_hotkey", return_value=True) as mock_send_hotkey, \
             mock.patch("server.connectors.spotify.toggle_like") as mock_like:
            res = actions.execute_action("hotkey", "CTRL+SHIFT+M")
            self.assertTrue(res["success"])
            mock_send_hotkey.assert_called_once_with("CTRL+SHIFT+M", require_modifier=False)
            mock_like.assert_not_called()

    def test_spotify_action_like_calls_toggle_like(self):
        """Verifies native spotify_action:like calls toggle_like directly."""
        with mock.patch.object(actions, "send_hotkey") as mock_send_hotkey, \
             mock.patch("server.connectors.spotify.toggle_like", return_value={"success": True, "action": "spotify_action"}) as mock_like:
            res = actions.execute_action("spotify_action", "like")
            self.assertTrue(res["success"])
            mock_like.assert_called_once()
            mock_send_hotkey.assert_not_called()

    def test_spotify_ui_toggle_like_handles_liked_songs_checkbox(self):
        """Verifies that _toggle_like toggles the 'Canciones que te gustan' checkbox in the playlist popup and clicks Hecho."""
        from server import spotify_ui

        mock_elem = mock.MagicMock()
        mock_toggle = mock.MagicMock()
        mock_elem.GetCurrentPattern.return_value.QueryInterface.return_value = mock_toggle

        mock_hecho = mock.MagicMock()
        mock_window = mock.MagicMock()
        mock_window.hwnd = 1234
        # Return bottom button, then checkbox and hecho button
        mock_window._all.side_effect = [
            [],  # initial check for open cb
            [(mock.MagicMock(), "Añadir a lista", (-2395, 1337, -2379, 1367))],  # bottom bar button
            [(mock_elem, "Canciones que te gustan", (-2384, 1232, -2138, 1284))],  # popup checkbox
            [(mock_hecho, "Hecho", (-2217, 1290, -2149, 1321))],  # hecho button
        ]

        with mock.patch.object(spotify_ui, "_running", return_value=True), \
             mock.patch.object(spotify_ui, "_Window", return_value=mock_window), \
             mock.patch.object(spotify_ui, "_post_click") as mock_post_click, \
             mock.patch("ctypes.windll.user32.GetWindowRect", side_effect=lambda hwnd, rect: None):
            res = spotify_ui._toggle_like()
            self.assertTrue(res)
            mock_post_click.assert_called_once()
            mock_toggle.Toggle.assert_called_once()
            mock_window._invoke.assert_called_with(mock_hecho)



if __name__ == "__main__":
    unittest.main()
