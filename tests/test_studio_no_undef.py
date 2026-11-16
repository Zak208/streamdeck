import os
import shutil
import subprocess
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StudioUndefinedFunctionsTests(unittest.TestCase):
    def test_no_undefined_variables_or_functions_in_static_js(self):
        """ESLint no-undef check across static/js/ to catch undefined function calls like rememberDeleted/clearInspector."""
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            self.skipTest("npx not available in environment")

        result = subprocess.run(
            [npx, "eslint", "static/js/"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            shell=True,
        )
        if result.returncode != 0:
            self.fail(
                f"ESLint found undefined references in static/js:\n{result.stdout}\n{result.stderr}"
            )
