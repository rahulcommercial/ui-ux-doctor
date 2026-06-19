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


class TestComponentRules(unittest.TestCase):
    def test_modal_no_a11y(self):
        self.assertIn("modal-no-a11y",
                      ids(scan_jsx('<div className="modal">x</div>')))

    def test_modal_with_role_ok(self):
        src = '<div className="modal" role="dialog" aria-label="Settings">x</div>'
        self.assertNotIn("modal-no-a11y", ids(scan_jsx(src)))

    def test_dialog_no_label(self):
        self.assertIn("dialog-no-label",
                      ids(scan_jsx('<div role="dialog">x</div>')))

    def test_modal_no_escape(self):
        self.assertIn("modal-no-escape",
                      ids(scan_jsx('<div className="modal">x</div>')))

    def test_modal_with_escape_ok(self):
        src = ('<div className="modal">x</div>\n'
               "onKeyDown={(e) => e.key === 'Escape' && close()}")
        self.assertNotIn("modal-no-escape", ids(scan_jsx(src)))

    def test_sidebar_no_landmark(self):
        self.assertIn("sidebar-no-landmark",
                      ids(scan_jsx('<div className="sidebar">x</div>')))

    def test_sidebar_aside_ok(self):
        self.assertNotIn("sidebar-no-landmark",
                         ids(scan_jsx('<aside className="sidebar">x</aside>')))

    def test_nested_interactive(self):
        self.assertIn("nested-interactive",
                      ids(scan_jsx('<a href="/x"><button>Go</button></a>')))


class TestFormRules(unittest.TestCase):
    def test_input_no_label(self):
        self.assertIn("input-no-label",
                      ids(scan_jsx('<input type="email" placeholder="Email" />')))

    def test_input_with_aria_label_ok(self):
        self.assertNotIn("input-no-label",
                         ids(scan_jsx('<input type="text" aria-label="Name" />')))

    def test_input_wrapped_in_label_ok(self):
        src = '<label>Email <input type="email" /></label>'
        self.assertNotIn("input-no-label", ids(scan_jsx(src)))

    def test_hidden_input_not_flagged(self):
        self.assertNotIn("input-no-label",
                         ids(scan_jsx('<input type="hidden" value="1" />')))

    def test_textarea_no_label(self):
        self.assertIn("textarea-no-label",
                      ids(scan_jsx('<textarea placeholder="Notes" />')))

    def test_password_no_autocomplete(self):
        self.assertIn("password-no-autocomplete",
                      ids(scan_jsx('<input type="password" aria-label="pw" />')))

    def test_form_no_onsubmit(self):
        self.assertIn("form-no-onsubmit", ids(scan_jsx('<form><input id="a"/></form>')))

    def test_form_with_onsubmit_ok(self):
        self.assertNotIn("form-no-onsubmit",
                         ids(scan_jsx('<form onSubmit={save}><input id="a"/></form>')))


class TestThemingRules(unittest.TestCase):
    def test_no_dark_variant(self):
        self.assertIn("no-dark-variant",
                      ids(scan_jsx('<div className="bg-white text-black">x</div>')))

    def test_dark_variant_present_ok(self):
        src = '<div className="bg-white dark:bg-slate-900">x</div>'
        self.assertNotIn("no-dark-variant", ids(scan_jsx(src)))

    def test_hardcoded_theme_color(self):
        self.assertIn("hardcoded-theme-color",
                      ids(scan_jsx('<div style={{ background: "#fff" }}>x</div>')))


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
