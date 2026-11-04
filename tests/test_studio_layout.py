"""Studio's right panel: its width is the user's to change, and the choice survives a restart."""

import json
import os
import re
import shutil
import subprocess
import unittest

import support  # noqa: F401  (paths and a throwaway data directory)
from server.paths import STATIC_DIR

NODE = shutil.which("node")


def read(path):
    with open(os.path.join(STATIC_DIR, path), encoding="utf-8") as handle:
        return handle.read()


class MarkupTests(unittest.TestCase):
    def test_the_panel_has_a_drag_handle_and_an_expand_button(self):
        html = read("studio.html")
        for fragment in ('id="inspector-resizer"', 'role="separator"', 'id="inspector-expand"'):
            self.assertIn(fragment, html)

    def test_every_width_of_the_layout_goes_through_the_variable(self):
        css = read("css/studio.css")
        self.assertEqual(len(re.findall(r"min\(var\(--inspector-width, \d+px\), 62vw\)", css)), 3)  # normal, narrow, and narrower windows
        self.assertNotRegex(css, r"grid-template-columns: [^;]*minmax\(0, 1fr\) \d+px;")  # no fixed right column left behind

    def test_option_lists_are_not_stuck_at_a_small_fixed_height(self):
        self.assertNotIn("max-height: 240px", read("css/studio.css"))


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class WidthLogicTests(unittest.TestCase):
    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const grab = (re) => { const m = re.exec(source); if (!m) throw new Error("not found " + re); return m[0]; };
const code = [
  grab(/const INSPECTOR_KEY = [^\r\n]*;/), grab(/const INSPECTOR_MIN = [^\r\n]*;/), grab(/const INSPECTOR_WIDE = [^\r\n]*;/),
  grab(/function inspectorLimits\(\) \{[\s\S]*?\r?\n\}\r?\n/), grab(/function currentInspectorWidth\(\) \{[\s\S]*?\r?\n\}\r?\n/),
  grab(/function setInspectorWidth\([\s\S]*?\r?\n\}\r?\n/),
].join("\n");

function scenario(windowWidth, storageThrows) {
  const stored = {}, style = {}, button = { textContent: "" };
  let drawer = 380;
  const context = {
    window: { innerWidth: windowWidth },
    document: {
      documentElement: { style: {
        setProperty: (k, v) => { style[k] = v; drawer = parseInt(v, 10); },
        removeProperty: (k) => { delete style[k]; drawer = 380; } } },
      getElementById: (id) => (id === "editor-drawer" ? { getBoundingClientRect: () => ({ width: drawer }) } : id === "inspector-expand" ? button : null),
    },
    localStorage: { setItem: (k, v) => { if (storageThrows) throw new Error("blocked"); stored[k] = v; },
                    removeItem: (k) => { if (storageThrows) throw new Error("blocked"); delete stored[k]; } },
  };
  vm.runInNewContext(code + "\n;this.set = setInspectorWidth; this.limits = inspectorLimits;", context);
  return { context, stored, style, button };
}
const out = {};
let s = scenario(1280, false);
s.context.set(600); out.set = [s.style["--inspector-width"], s.stored["streamdesk_inspector_width"], s.button.textContent];
s.context.set(100); out.tooNarrow = s.style["--inspector-width"];
s.context.set(5000); out.tooWide = s.style["--inspector-width"];
s.context.set(500, ); s.context.set(null); out.reset = [s.style["--inspector-width"], s.stored["streamdesk_inspector_width"], s.button.textContent];
s.context.set(700, ); out.notSaved = (() => { const t = scenario(1280, false); t.context.set(700, { save: false }); return t.stored["streamdesk_inspector_width"] ?? null; })();
out.smallWindow = scenario(900, false).context.limits();
out.bigWindow = scenario(3000, false).context.limits();
const blocked = scenario(1280, true);
blocked.context.set(640); out.blocked = blocked.style["--inspector-width"];
console.log(JSON.stringify(out));
"""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run([NODE, "-e", cls.SCRIPT, os.path.join(STATIC_DIR, "js", "studio-ui.js")],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stderr
        cls.out = json.loads(result.stdout)

    def test_the_width_is_applied_remembered_and_the_button_follows(self):
        self.assertEqual(self.out["set"], ["600px", "600", "⤡"])

    def test_it_never_gets_too_narrow_or_too_wide(self):
        self.assertEqual(self.out["tooNarrow"], "340px")
        self.assertEqual(self.out["tooWide"], "794px")  # 62% of a 1280 px window, rounded
        self.assertEqual(self.out["smallWindow"], {"min": 340, "max": 558})
        self.assertEqual(self.out["bigWindow"], {"min": 340, "max": 960})

    def test_resetting_goes_back_to_the_stylesheets_width_and_forgets_the_choice(self):
        self.assertEqual(self.out["reset"], [None, None, "⤢"])

    def test_dragging_does_not_write_to_storage_until_it_ends(self):
        self.assertIsNone(self.out["notSaved"])

    def test_a_browser_that_blocks_storage_still_resizes(self):
        self.assertEqual(self.out["blocked"], "640px")


if __name__ == "__main__":
    unittest.main()
