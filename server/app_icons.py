"""An icon for an app placed on a button.

A button can only show an image that lives in StreamDesk's own folders, so the icon is made once and kept in the
uploads folder: the program's real icon when Windows has one for its .exe, otherwise a dark square with its
first letter in yellow. The app comes from the scanner by id, never from a path sent by the browser.
"""

import os
import subprocess
import shutil
from html import escape
from typing import Optional

from server.system_scanner import CREATE_NO_WINDOW, GENERIC_ICON, system_scanner

_EXTRACT = (
    "Add-Type -AssemblyName System.Drawing; "
    "$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($env:SD_ICON_SOURCE); "
    "$icon.ToBitmap().Save($env:SD_ICON_TARGET, [System.Drawing.Imaging.ImageFormat]::Png)"
)


def letter_icon_svg(name: str) -> str:
    letter = next((c for c in name if c.isalnum()), "?").upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        '<rect width="96" height="96" rx="22" fill="#202020" stroke="#555555" stroke-width="2"/>'
        '<text x="48" y="64" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="52" '
        f'font-weight="700" fill="#f8c700">{escape(letter)}</text></svg>'
    )


def _extract_real_icon(source: str, target: str) -> bool:
    """Ask Windows for the icon of an .exe (what Explorer shows) and save it as a PNG. False if it cannot."""
    shell = shutil.which("powershell.exe")
    if not shell or not source.lower().endswith(".exe") or not os.path.isfile(source):
        return False
    try:
        env = dict(os.environ, SD_ICON_SOURCE=source, SD_ICON_TARGET=target)
        subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", _EXTRACT], env=env, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=20, creationflags=CREATE_NO_WINDOW)
    except Exception:
        return False
    return os.path.isfile(target) and os.path.getsize(target) > 0


def icon_for_app(app_id: str, uploads_dir: str) -> Optional[str]:
    """The /uploads/... address of the icon for this app, or its own icon when it already has a good one."""
    app = system_scanner.find(app_id)
    if not app:
        return None
    if app["icon"] != GENERIC_ICON:
        return app["icon"]  # one of StreamDesk's own drawn icons (Discord, Chrome, Steam...)
    name = f"appicon_{app['id']}"
    for extension in (".png", ".svg"):
        if os.path.isfile(os.path.join(uploads_dir, name + extension)):
            return f"/uploads/{name}{extension}"
    png = os.path.join(uploads_dir, name + ".png")
    source = app.get("icon_source") or ""
    if source and _extract_real_icon(source, png):
        return f"/uploads/{name}.png"
    with open(os.path.join(uploads_dir, name + ".svg"), "w", encoding="utf-8") as handle:
        handle.write(letter_icon_svg(app["name"]))
    return f"/uploads/{name}.svg"
