"""Unit tests for ui-ux-doctor. Pure stdlib unittest.

Run:  python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from rules import scan_jsx, scan_python  # noqa: E402


def ids(findings):
    return {f.rule_id for f in findings}


class TestJSXRules(unittest.TestCase):
    def test_clickable_nonbutton(self):
        self.assertIn("clickable-nonbutton",
                      ids(scan_jsx('<div onClick={go}>x</div>')))

    def test_clickable_div_with_role_and_key_handler_ok(self):
        src = '<div role="button" tabIndex={0} onClick={go} onKeyDown={go}>x</div>'
        self.assertNotIn("clickable-nonbutton", ids(scan_jsx(src)))

    def test_real_button_not_flagged_as_clickable(self):
        self.assertNotIn("clickable-nonbutton",
                         ids(scan_jsx('<button onClick={go}>Save</button>')))

    def test_missing_key(self):
        src = "items.map(x => <li>{x.name}</li>)"
        self.assertIn("missing-key", ids(scan_jsx(src)))

    def test_key_present_ok(self):
        src = "items.map(x => <li key={x.id}>{x.name}</li>)"
        self.assertNotIn("missing-key", ids(scan_jsx(src)))

    def test_index_as_key(self):
        src = "items.map((x, index) => <li key={index}>{x}</li>)"
        found = ids(scan_jsx(src))
        self.assertIn("index-as-key", found)

    def test_length_and_leak(self):
        self.assertIn("length-and-leak",
                      ids(scan_jsx("<div>{items.length && <List/>}</div>")))

    def test_img_no_alt(self):
        self.assertIn("img-no-alt", ids(scan_jsx('<img src="a.png" />')))

    def test_img_with_alt_ok(self):
        self.assertNotIn("img-no-alt", ids(scan_jsx('<img src="a.png" alt="A" />')))

    def test_icon_button_no_label(self):
        src = '<button onClick={x}><svg viewBox="0 0 24 24"/></button>'
        self.assertIn("icon-button-no-label", ids(scan_jsx(src)))

    def test_icon_button_with_arrow_handler(self):
        # arrow fn `=>` in attrs must not truncate the tag parse
        src = '<button onClick={() => setX([])}><svg viewBox="0 0 24 24" /></button>'
        self.assertIn("icon-button-no-label", ids(scan_jsx(src)))

    def test_icon_button_with_label_ok(self):
        src = '<button aria-label="Close" onClick={x}><svg /></button>'
        self.assertNotIn("icon-button-no-label", ids(scan_jsx(src)))

    def test_dangerous_html(self):
        self.assertIn("dangerous-html",
                      ids(scan_jsx('<div dangerouslySetInnerHTML={{__html: h}} />')))

    def test_useeffect_no_deps(self):
        self.assertIn("useeffect-no-deps",
                      ids(scan_jsx("useEffect(() => { run(); })")))

    def test_useeffect_with_deps_ok(self):
        self.assertNotIn("useeffect-no-deps",
                         ids(scan_jsx("useEffect(() => { run(); }, [run])")))

    def test_hardcoded_localhost(self):
        self.assertIn("hardcoded-localhost",
                      ids(scan_jsx('const u = "http://localhost:8000/api";')))

    def test_console_log(self):
        self.assertIn("console-log", ids(scan_jsx('console.log("x")')))

    def test_comment_not_flagged(self):
        # localhost only inside a comment should be ignored
        self.assertNotIn("hardcoded-localhost",
                         ids(scan_jsx('// see http://localhost:8000\nconst x = 1;')))


class TestPythonRules(unittest.TestCase):
    def test_cors_wildcard_credentials(self):
        src = 'allow_origins=["*"]\nallow_credentials=True\n'
        self.assertIn("cors-wildcard-credentials", ids(scan_python(src)))

    def test_cors_wildcard_only(self):
        src = 'allow_origins=["*"]\n'
        found = ids(scan_python(src))
        self.assertIn("cors-wildcard", found)
        self.assertNotIn("cors-wildcard-credentials", found)

    def test_print_debug(self):
        self.assertIn("print-debug", ids(scan_python('    print("x")\n')))

    def test_python_hardcoded_localhost(self):
        self.assertIn("hardcoded-localhost",
                      ids(scan_python('API = "http://127.0.0.1:9000"\n')))


if __name__ == "__main__":
    unittest.main()
