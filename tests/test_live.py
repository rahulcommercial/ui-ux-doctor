"""Integration test for the runtime (live) scanner.

Skipped automatically when no Chrome/Edge/Chromium is available, so it never
breaks a headless CI box. To run it, make sure a browser is installed (or set
UXD_BROWSER), then:

    python3 -m unittest tests.test_live
"""
import os
import sys
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from cdp import find_browser  # noqa: E402
import scan_live  # noqa: E402

EXAMPLES = os.path.join(HERE, "..", "examples")


@unittest.skipUnless(find_browser() or os.environ.get("UXD_BROWSER"),
                     "no Chrome/Edge/Chromium found")
class TestLiveScan(unittest.TestCase):
    def setUp(self):
        handler = partial(SimpleHTTPRequestHandler, directory=EXAMPLES)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()

    def test_finds_runtime_bugs(self):
        url = "http://127.0.0.1:%d/live_demo.html" % self.port
        findings = scan_live.run_scan(url, wait_ms=1500)
        rules = {f.rule_id for f in findings}
        for expected in ("runtime-broken-image", "runtime-img-no-alt",
                         "runtime-button-no-name", "runtime-input-no-label",
                         "runtime-low-contrast", "runtime-duplicate-id",
                         "runtime-horizontal-overflow", "runtime-dialog-no-aria",
                         "runtime-network-error", "runtime-console-error"):
            self.assertIn(expected, rules, "expected %s in %s" % (expected, rules))


if __name__ == "__main__":
    unittest.main()
