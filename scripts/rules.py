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
