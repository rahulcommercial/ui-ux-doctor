"""
ui-ux-doctor rule engine.

Pure Python standard library only. No pip, no npm, no network.

A "rule" is a heuristic that flags a likely UI/UX bug in React (.jsx/.tsx/.js/.ts)
or FastAPI (.py) source. Rules are deliberately conservative and explainable: each
finding carries a fix and a "why". This is a static, regex/heuristic scanner -- it
is meant to surface candidates for a human (or Claude) to confirm, not to be a
sound type checker.
"""

import bisect
import re
from collections import namedtuple

# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #

SEVERITY_ORDER = {"critical": 3, "warning": 2, "info": 1}

Finding = namedtuple("Finding", "rule_id severity category line message snippet fix")

# --------------------------------------------------------------------------- #
# Rule catalogue (metadata used for --list and reports)
# --------------------------------------------------------------------------- #

RULES = {
    # React / JSX -------------------------------------------------------------
    "clickable-nonbutton": {
        "category": "interaction",
        "severity": "warning",
        "summary": "onClick on a non-interactive element (div/span/li/...).",
        "fix": "Use a <button> (or <a> for navigation). If you must keep the tag, "
               "add role=\"button\", tabIndex={0} and an onKeyDown handler.",
        "why": "Divs with onClick are not keyboard-focusable and announce nothing to "
               "screen readers. This is the #1 cause of 'button does nothing on keyboard'.",
    },
    "icon-button-no-label": {
        "category": "accessibility",
        "severity": "warning",
        "summary": "Icon-only <button> with no accessible name.",
        "fix": "Add aria-label=\"...\" (or visually-hidden text) to the button, and "
               "aria-hidden=\"true\" on the decorative icon.",
        "why": "Screen readers announce icon-only buttons as 'button' with no purpose.",
    },
    "missing-key": {
        "category": "rendering",
        "severity": "warning",
        "summary": ".map() renders an element without a key prop.",
        "fix": "Add a stable key={item.id} to the top-level element returned by .map().",
        "why": "Missing keys cause wrong DOM reuse: stale content, lost input focus, "
               "and flickering on re-render.",
    },
    "index-as-key": {
        "category": "rendering",
        "severity": "warning",
        "summary": "Array index used as React key.",
        "fix": "Use a stable unique id (item.id). Index keys break when the list "
               "reorders, inserts, or deletes.",
        "why": "Index keys make React reuse the wrong elements, corrupting inputs and "
               "animations when the list changes.",
    },
    "length-and-leak": {
        "category": "rendering",
        "severity": "warning",
        "summary": "`x.length && <JSX>` can render a literal 0.",
        "fix": "Use a boolean: {x.length > 0 && <JSX>} or {!!x.length && <JSX>}.",
        "why": "When length is 0, React renders the number 0 instead of nothing -- a "
               "stray '0' appears in the UI.",
    },
    "img-no-alt": {
        "category": "accessibility",
        "severity": "warning",
        "summary": "<img> without an alt attribute.",
        "fix": "Add alt=\"description\" for meaningful images, or alt=\"\" for decorative ones.",
        "why": "Images with no alt are unusable to screen readers and show nothing if "
               "the image fails to load.",
    },
    "dangerous-html": {
        "category": "rendering",
        "severity": "warning",
        "summary": "dangerouslySetInnerHTML used.",
        "fix": "Render text/JSX directly. If HTML is required, sanitize it server-side "
               "first and confirm the source is trusted.",
        "why": "Unsanitized HTML injects XSS and frequently breaks layout/rendering.",
    },
    "hardcoded-localhost": {
        "category": "integration",
        "severity": "warning",
        "summary": "Hardcoded http://localhost / 127.0.0.1 URL.",
        "fix": "Read the API base from an env var / config (e.g. import.meta.env.VITE_API_URL "
               "in React, os.environ in FastAPI).",
        "why": "Hardcoded localhost works on your machine but breaks in every other "
               "environment -- the classic 'works locally, blank in prod' bug.",
    },
    "button-no-type": {
        "category": "interaction",
        "severity": "info",
        "summary": "<button> without an explicit type.",
        "fix": "Add type=\"button\" (or type=\"submit\" if it really submits a form).",
        "why": "A button inside a <form> defaults to type=submit, so clicking it "
               "reloads the page / fires the form unexpectedly.",
    },
    "positive-tabindex": {
        "category": "accessibility",
        "severity": "info",
        "summary": "Positive tabIndex breaks natural tab order.",
        "fix": "Use tabIndex={0} (focusable, natural order) or tabIndex={-1} "
               "(programmatic only). Never > 0.",
        "why": "Positive tabIndex hijacks the tab sequence and confuses keyboard users.",
    },
    "autofocus": {
        "category": "accessibility",
        "severity": "info",
        "summary": "autoFocus can disorient users and screen readers.",
        "fix": "Confirm autofocus is intentional (e.g. a search-only page). Avoid it "
               "on routed pages and modals that already manage focus.",
        "why": "Unexpected autofocus moves the viewport and steals focus on load.",
    },
    "console-log": {
        "category": "cleanliness",
        "severity": "info",
        "summary": "Leftover console.log / console.debug.",
        "fix": "Remove debug logging before shipping, or gate it behind a debug flag.",
        "why": "Debug logs leak data and noise into the production console.",
    },
    "useeffect-no-deps": {
        "category": "rendering",
        "severity": "info",
        "summary": "useEffect without a dependency array.",
        "fix": "Add a dependency array: useEffect(() => {...}, [deps]). Use [] for "
               "mount-only effects.",
        "why": "An effect with no deps array runs after every render -- a common cause "
               "of infinite fetch loops and re-render storms.",
    },
    "inline-style-object": {
        "category": "performance",
        "severity": "info",
        "summary": "Inline style={{...}} object literal.",
        "fix": "Move static styles to a class (Tailwind/CSS). Memoize dynamic styles.",
        "why": "A new object every render breaks memoization and can cause extra "
               "re-renders of child components.",
    },
    # Components: modals, dialogs, sidebars -----------------------------------
    "modal-no-a11y": {
        "category": "component",
        "severity": "warning",
        "summary": "Modal/dialog element without role=\"dialog\" + aria-modal.",
        "fix": "Add role=\"dialog\" aria-modal=\"true\" and an aria-label/aria-labelledby. "
               "Trap focus inside while open and restore it on close.",
        "why": "Without dialog semantics, screen readers don't announce the modal and "
               "keyboard focus leaks to the page behind it.",
    },
    "dialog-no-label": {
        "category": "accessibility",
        "severity": "warning",
        "summary": "role=\"dialog\" without an accessible name.",
        "fix": "Add aria-labelledby pointing at the title, or aria-label=\"...\".",
        "why": "A dialog with no name is announced as just 'dialog' with no context.",
    },
    "modal-no-escape": {
        "category": "component",
        "severity": "info",
        "summary": "Modal/dialog in this file with no Escape-to-close handler.",
        "fix": "Add a keydown listener that closes on key === 'Escape' (and close on "
               "backdrop click).",
        "why": "Users expect Esc to dismiss an overlay; without it the modal can trap them.",
    },
    "sidebar-no-landmark": {
        "category": "component",
        "severity": "info",
        "summary": "Sidebar/drawer that isn't a <nav>/<aside> landmark.",
        "fix": "Use <nav> (navigation) or <aside> (complementary), or add an appropriate "
               "role, so assistive tech and skip-links can find it.",
        "why": "A sidebar built from plain <div>s is invisible as a landmark to screen readers.",
    },
    "nested-interactive": {
        "category": "accessibility",
        "severity": "warning",
        "summary": "Interactive element nested inside another (button in a/button).",
        "fix": "Don't nest button/anchor inside button/anchor. Use one interactive "
               "element, or restructure (e.g. an icon button beside a link).",
        "why": "Nested interactives produce invalid HTML and unpredictable click/focus "
               "behavior across browsers and screen readers.",
    },
    # Forms: inputs, textareas, selects ---------------------------------------
    "input-no-label": {
        "category": "forms",
        "severity": "warning",
        "summary": "Form control (input/select) with no associated label.",
        "fix": "Add a <label htmlFor> tied to the control's id, wrap it in a <label>, or "
               "add aria-label. A placeholder is NOT a label.",
        "why": "Unlabeled fields are unusable with screen readers and break click-to-focus.",
    },
    "textarea-no-label": {
        "category": "forms",
        "severity": "warning",
        "summary": "<textarea> with no associated label.",
        "fix": "Add a <label htmlFor> tied to its id, wrap it in a <label>, or add aria-label.",
        "why": "An unlabeled textarea gives screen-reader users no idea what to type.",
    },
    "password-no-autocomplete": {
        "category": "forms",
        "severity": "info",
        "summary": "Password input without an autocomplete hint.",
        "fix": "Add autocomplete=\"current-password\" (login) or \"new-password\" (signup) "
               "so password managers and browsers behave correctly.",
        "why": "Missing autocomplete breaks password managers and autofill UX.",
    },
    "form-no-onsubmit": {
        "category": "forms",
        "severity": "info",
        "summary": "<form> without an onSubmit handler.",
        "fix": "Handle onSubmit and call e.preventDefault() so Enter-to-submit works and "
               "the page doesn't full-reload.",
        "why": "A form with no onSubmit reloads the page on Enter/submit -- losing app state.",
    },
    # Theming: light / dark mode ----------------------------------------------
    "no-dark-variant": {
        "category": "theming",
        "severity": "info",
        "summary": "Light-mode color utility with no dark: variant.",
        "fix": "Pair light utilities with dark ones, e.g. bg-white dark:bg-slate-900, "
               "text-black dark:text-white.",
        "why": "Hardcoded light backgrounds/text stay light in dark mode -- white flashes "
               "and unreadable contrast.",
    },
    "hardcoded-theme-color": {
        "category": "theming",
        "severity": "info",
        "summary": "Hardcoded black/white color in an inline style.",
        "fix": "Use theme tokens / CSS variables (or Tailwind classes with dark: variants) "
               "instead of literal #fff / #000 / white / black.",
        "why": "Literal colors don't adapt to light/dark themes and drift from the design system.",
    },
    # FastAPI / Python --------------------------------------------------------
    "cors-wildcard-credentials": {
        "category": "integration",
        "severity": "critical",
        "summary": "CORS allow_origins=['*'] together with allow_credentials=True.",
        "fix": "List explicit origins (e.g. allow_origins=[\"https://app.example.com\"]). "
               "The browser rejects wildcard + credentials, so authed requests fail.",
        "why": "Browsers block '*' when credentials are sent -- the React app gets a CORS "
               "error and the UI silently fails to load data.",
    },
    "cors-wildcard": {
        "category": "integration",
        "severity": "info",
        "summary": "CORS allow_origins=['*'].",
        "fix": "Restrict to the actual frontend origin(s) for anything beyond local dev.",
        "why": "Wildcard CORS is fine for quick local dev but unsafe and brittle in shared "
               "or production environments.",
    },
    "print-debug": {
        "category": "cleanliness",
        "severity": "info",
        "summary": "print() left in server code.",
        "fix": "Use logging (logger.info/debug) instead of print in request handlers.",
        "why": "print() bypasses log levels/handlers and clutters server output.",
    },
}

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*$", re.MULTILINE)  # keep http:// intact
_PY_COMMENT = re.compile(r"(?<!:)#.*$", re.MULTILINE)


def strip_comments(text, python=False):
    """Blank out comments while preserving line count (newlines kept)."""
    if python:
        return _PY_COMMENT.sub("", text)
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", text)


def _line_starts(text):
    starts = [0]
    for m in re.finditer(r"\n", text):
        starts.append(m.end())
    return starts


def _lineno(starts, index):
    return bisect.bisect_right(starts, index)


def _snippet(lines, lineno):
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()[:160]
    return ""


# JSX opening-tag tokenizer. Attributes may contain {expr} with `>` inside (arrow
# functions) and one level of nested braces (style={{...}}); braces take priority
# over plain chars so `onClick={() => x}` is consumed as one unit, not cut at `=>`.
_ATTRS = r"(?:\{(?:[^{}]|\{[^{}]*\})*\}|[^<>{])*?"
_OPEN_TAG = re.compile(r"<([A-Za-z][\w.]*)(" + _ATTRS + r")(/?)>", re.DOTALL)
_NON_INTERACTIVE = {
    "div", "span", "li", "p", "td", "tr", "ul", "ol", "section", "article",
    "header", "footer", "aside", "main", "figure", "label", "img",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


def _within_label(clean, pos):
    """True if char offset `pos` sits inside an unclosed <label> ... </label>."""
    before = clean[:pos]
    return before.rfind("<label") > before.rfind("</label>")


def _has(attrs, *names):
    """True if any of the attribute names appears in the tag's attr string."""
    return any(re.search(r"\b" + re.escape(n) + r"\s*=", attrs) for n in names)


def _classname_literal(attrs):
    """Return the literal className string, or '' if it's an expression/absent."""
    m = re.search(r"""className\s*=\s*["']([^"']*)["']""", attrs)
    return m.group(1) if m else ""


_LIGHT_UTILS = ("bg-white", "bg-black", "text-white", "text-black",
                "bg-gray-50", "bg-gray-100", "bg-slate-50", "bg-slate-100")
_INPUT_SKIP_TYPES = {"hidden", "submit", "button", "reset", "image",
                     "checkbox", "radio"}


def _mk(rule_id, lineno, lines):
    meta = RULES[rule_id]
    return Finding(
        rule_id=rule_id,
        severity=meta["severity"],
        category=meta["category"],
        line=lineno,
        message=meta["summary"],
        snippet=_snippet(lines, lineno),
        fix=meta["fix"],
    )


# --------------------------------------------------------------------------- #
# React / JSX scanning
# --------------------------------------------------------------------------- #

def scan_jsx(text):
    findings = []
    clean = strip_comments(text)
    raw_lines = text.splitlines()
    starts = _line_starts(clean)

    # --- tag-based rules ---------------------------------------------------- #
    for m in _OPEN_TAG.finditer(clean):
        tag = m.group(1)
        attrs = m.group(2) or ""
        lineno = _lineno(starts, m.start())

        if tag in _NON_INTERACTIVE and re.search(r"\bonClick\s*=", attrs):
            keyboard_ok = re.search(r"\brole\s*=", attrs) and re.search(
                r"\bonKey(Down|Press|Up)\s*=", attrs)
            if not keyboard_ok:
                findings.append(_mk("clickable-nonbutton", lineno, raw_lines))

        if tag == "img" and not re.search(r"\balt\s*=", attrs):
            findings.append(_mk("img-no-alt", lineno, raw_lines))

        if tag == "button" and not re.search(r"\btype\s*=", attrs):
            findings.append(_mk("button-no-type", lineno, raw_lines))

        if "dangerouslySetInnerHTML" in attrs:
            findings.append(_mk("dangerous-html", lineno, raw_lines))

        if re.search(r"\bstyle\s*=\s*\{\{", attrs):
            findings.append(_mk("inline-style-object", lineno, raw_lines))

        if re.search(r"\bautoFocus\b", attrs):
            findings.append(_mk("autofocus", lineno, raw_lines))

        tab = re.search(r"\btabIndex\s*=\s*\{?\s*['\"]?(\d+)", attrs)
        if tab and int(tab.group(1)) > 0:
            findings.append(_mk("positive-tabindex", lineno, raw_lines))

    # --- icon-only buttons (need inner content) ----------------------------- #
    btn_re = re.compile(r"<button\b(" + _ATTRS + r")>(.*?)</button>", re.DOTALL)
    for m in btn_re.finditer(clean):
        attrs, inner = m.group(1), m.group(2)
        has_label = re.search(r"\b(aria-label|aria-labelledby|title)\s*=", attrs)
        text_only = re.sub(r"<[^>]*>", "", inner)
        text_only = re.sub(r"\{[^{}]*\}", "", text_only).strip()
        looks_icon = ("<svg" in inner or "Icon" in inner or re.search(r"<i\b", inner))
        if looks_icon and not has_label and not text_only:
            findings.append(_mk("icon-button-no-label",
                                _lineno(starts, m.start()), raw_lines))

    # --- .map() without key ------------------------------------------------- #
    map_re = re.compile(
        r"\.map\(\s*(?:async\s*)?\(?[^()=]*\)?\s*=>\s*\(?\s*<([A-Za-z][\w.]*)((?:[^<>]|\{[^{}]*\})*?)/?>",
        re.DOTALL)
    for m in map_re.finditer(clean):
        attrs = m.group(2) or ""
        if not re.search(r"\bkey\s*=", attrs):
            findings.append(_mk("missing-key", _lineno(starts, m.start()), raw_lines))

    # --- index as key ------------------------------------------------------- #
    for m in re.finditer(r"\bkey\s*=\s*\{\s*([A-Za-z_]\w*)\s*\}", clean):
        if m.group(1) in {"i", "idx", "index", "_i", "n", "ix"}:
            findings.append(_mk("index-as-key", _lineno(starts, m.start()), raw_lines))

    # --- length && leak ----------------------------------------------------- #
    for m in re.finditer(r"\{\s*[\w.$]*\.length\s*&&", clean):
        findings.append(_mk("length-and-leak", _lineno(starts, m.start()), raw_lines))

    # --- useEffect without deps array --------------------------------------- #
    for m in re.finditer(r"useEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*\{",
                         clean):
        # find the matching close of the effect callback, then check what follows
        depth, i, n = 0, m.end() - 1, len(clean)
        while i < n:
            c = clean[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        tail = clean[i + 1:i + 40]
        if not re.match(r"\s*,\s*\[", tail):  # no dependency array follows
            findings.append(_mk("useeffect-no-deps", _lineno(starts, m.start()),
                                raw_lines))

    # --- component / forms / theming (tag-based) ---------------------------- #
    for m in _OPEN_TAG.finditer(clean):
        tag = m.group(1)
        attrs = m.group(2) or ""
        lineno = _lineno(starts, m.start())
        cls_lit = _classname_literal(attrs)
        cls_modalish = re.search(r"\b(modal|dialog)\b", attrs, re.I)
        is_dialog_role = re.search(r"role\s*=\s*['\"]dialog['\"]", attrs)

        # Modal / dialog semantics
        if (cls_modalish or is_dialog_role) and tag not in ("img",):
            if not is_dialog_role and not _has(attrs, "role"):
                findings.append(_mk("modal-no-a11y", lineno, raw_lines))
            if is_dialog_role and not _has(attrs, "aria-label", "aria-labelledby"):
                findings.append(_mk("dialog-no-label", lineno, raw_lines))

        # Sidebar / drawer landmark
        if re.search(r"\b(sidebar|drawer)\b", attrs, re.I) and \
                tag not in ("nav", "aside") and not _has(attrs, "role"):
            findings.append(_mk("sidebar-no-landmark", lineno, raw_lines))

        # Inputs / selects / textareas
        if tag in ("input", "select", "textarea"):
            typ = re.search(r"type\s*=\s*['\"]?(\w+)", attrs)
            typ = typ.group(1).lower() if typ else "text"
            labelled = _has(attrs, "aria-label", "aria-labelledby", "id") \
                or _within_label(clean, m.start())
            if tag in ("input", "select"):
                if typ not in _INPUT_SKIP_TYPES and not labelled:
                    findings.append(_mk("input-no-label", lineno, raw_lines))
                if typ == "password" and not _has(attrs, "autocomplete"):
                    findings.append(_mk("password-no-autocomplete", lineno, raw_lines))
            elif tag == "textarea" and not labelled:
                findings.append(_mk("textarea-no-label", lineno, raw_lines))

        # Form submit handling
        if tag == "form" and not _has(attrs, "onSubmit"):
            findings.append(_mk("form-no-onsubmit", lineno, raw_lines))

        # Light/dark theming
        if cls_lit and any(u in cls_lit for u in _LIGHT_UTILS) and "dark:" not in cls_lit:
            findings.append(_mk("no-dark-variant", lineno, raw_lines))
        if re.search(r"(?:color|background|backgroundColor)\s*:\s*['\"]?#?"
                     r"(?:fff(?:fff)?|000(?:000)?|white|black)\b", attrs, re.I):
            findings.append(_mk("hardcoded-theme-color", lineno, raw_lines))

    # --- nested interactive elements ---------------------------------------- #
    for pat in (r"<a\b" + _ATTRS + r">(?:(?!</a>).)*?<(?:button|a)\b",
                r"<button\b" + _ATTRS + r">(?:(?!</button>).)*?<(?:button|a)\b"):
        for m in re.finditer(pat, clean, re.DOTALL):
            findings.append(_mk("nested-interactive", _lineno(starts, m.start()),
                                raw_lines))

    # --- modal in file but no Escape handler (file-level) ------------------- #
    if re.search(r"\b(modal|dialog)\b", clean, re.I) or "role=\"dialog\"" in clean:
        if not re.search(r"['\"]Esc(?:ape)?['\"]|keyCode\s*===?\s*27|which\s*===?\s*27",
                         clean):
            mm = re.search(r"\b(modal|dialog)\b", clean, re.I)
            if mm:
                findings.append(_mk("modal-no-escape", _lineno(starts, mm.start()),
                                    raw_lines))

    # --- line-based rules --------------------------------------------------- #
    for n, line in enumerate(clean.splitlines(), 1):
        if re.search(r"\bconsole\.(log|debug)\s*\(", line):
            findings.append(_mk("console-log", n, raw_lines))
        if re.search(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", line):
            findings.append(_mk("hardcoded-localhost", n, raw_lines))

    return findings


# --------------------------------------------------------------------------- #
# FastAPI / Python scanning
# --------------------------------------------------------------------------- #

def scan_python(text):
    findings = []
    clean = strip_comments(text, python=True)
    raw_lines = text.splitlines()

    wildcard = re.search(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]", clean)
    credentials = re.search(r"allow_credentials\s*=\s*True", clean)
    if wildcard:
        starts = _line_starts(clean)
        lineno = _lineno(starts, wildcard.start())
        if credentials:
            findings.append(_mk("cors-wildcard-credentials", lineno, raw_lines))
        else:
            findings.append(_mk("cors-wildcard", lineno, raw_lines))

    for n, line in enumerate(clean.splitlines(), 1):
        if re.search(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", line):
            findings.append(_mk("hardcoded-localhost", n, raw_lines))
        if re.match(r"\s*print\s*\(", line):
            findings.append(_mk("print-debug", n, raw_lines))

    return findings


# --------------------------------------------------------------------------- #
# Dispatch by extension
# --------------------------------------------------------------------------- #

JSX_EXT = {".jsx", ".tsx", ".js", ".ts", ".mjs"}
PY_EXT = {".py"}


def scan_text(text, ext):
    if ext in JSX_EXT:
        return scan_jsx(text)
    if ext in PY_EXT:
        return scan_python(text)
    return []
