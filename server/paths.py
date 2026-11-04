"""Where StreamDesk keeps its code-adjacent files and its per-user data.

Set STREAMDESK_DATA_DIR to relocate the config, tokens and uploads (the tests
do this so they never touch the real profile or the paired devices).
"""

import os
import sys

VERSION = "2.11.0"
PORT = 48291

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC_DIR = os.path.join(BASE_DIR, "static")

_override = os.environ.get("STREAMDESK_DATA_DIR")
if _override:
    DATA_DIR = os.path.abspath(_override)
elif FROZEN:
    DATA_DIR = os.path.expandvars(r"%APPDATA%\StreamDesk")
else:
    DATA_DIR = BASE_DIR

CONFIG_DIR = os.path.join(DATA_DIR, "config")
# In a source checkout uploads stay under static/ as before; elsewhere they live with the data.
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads") if DATA_DIR == BASE_DIR else os.path.join(DATA_DIR, "uploads")
