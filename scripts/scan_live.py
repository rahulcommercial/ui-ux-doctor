#!/usr/bin/env python3
"""
ui-ux-doctor (live) -- runtime UI/UX scanner for a RUNNING app.

Drives an already-installed Chrome / Edge / Chromium (via the DevTools Protocol,
pure stdlib -- see cdp.py) to open your localhost URL, let React render, and scan
the REAL rendered DOM + computed styles + console + network.

It catches what the static scanner can't:
  * broken images, zero-size / collapsed buttons, content overflowing the viewport
  * real color-contrast failures (computed from rendered colors)
  * buttons/links with no accessible name, inputs with no real label association
  * modals/dialogs missing dialog semantics
  * React's own console warnings (e.g. missing key), uncaught exceptions
  * failed API calls (HTTP 4xx/5xx) during load

Usage:
    python3 scripts/scan_live.py http://localhost:5173
    python3 scripts/scan_live.py http://localhost:8000 --click "#open-settings"
    python3 scripts/scan_live.py http://localhost:5173 --headed --wait 2000
    python3 scripts/scan_live.py http://localhost:5173 --attach 9222   # you launched it

No pip, no npm, no network egress -- it only talks to the browser already on the box.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import RUNTIME_RULES, SEVERITY_ORDER, Finding  # noqa: E402
from cdp import Browser, CDP  # noqa: E402

SEV_TAG = {"critical": "CRIT", "warning": "WARN", "info": "INFO"}
SEV_COLOR = {"critical": "\033[31m", "warning": "\033[33m", "info": "\033[36m"}
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
CAP = 25  # max findings reported per rule, to avoid floods

# --------------------------------------------------------------------------- #
# In-page audit (runs in the browser, returns plain JSON)
# --------------------------------------------------------------------------- #

AUDIT_JS = r"""
(() => {
  const CAP = 25;
  const out = [];
  const push = (rule, message, el) => out.push({rule, message, selector: sel(el)});
  const seen = {};
  const add = (rule, message, el) => {
    seen[rule] = (seen[rule] || 0) + 1;
    if (seen[rule] <= CAP) push(rule, message, el);
  };

  function sel(el) {
    if (!el || el.nodeType !== 1) return "";
    let s = el.tagName.toLowerCase();
    if (el.id) return s + "#" + el.id;
    if (el.className && typeof el.className === "string") {
      const c = el.className.trim().split(/\s+/).slice(0, 2).join(".");
      if (c) s += "." + c;
    }
    const p = el.parentElement;
    if (p) {
      const same = [...p.children].filter(x => x.tagName === el.tagName);
      if (same.length > 1) s += ":nth-of-type(" + ([...p.children].indexOf(el) + 1) + ")";
    }
    return s.slice(0, 70);
  }
  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0)
      return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function rendered(el) {  // in layout (not display:none), may be 0-size
    const cs = getComputedStyle(el);
    return cs.display !== "none" && cs.visibility !== "hidden";
  }
  function accName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) {
      const t = lb.split(/\s+/).map(id => {
        const n = document.getElementById(id); return n ? n.textContent : "";
      }).join(" ").trim();
      if (t) return t;
    }
    if (el.getAttribute("title")) return el.getAttribute("title").trim();
    const txt = (el.textContent || "").trim();
    if (txt) return txt;
    const img = el.querySelector("img[alt]");
    if (img && img.getAttribute("alt").trim()) return img.getAttribute("alt").trim();
    if (el.value && typeof el.value === "string") return el.value.trim();
    return "";
  }
  function parseRGB(s) {
    const m = s && s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  }
  function effBg(el) {
    let n = el;
    while (n && n.nodeType === 1) {
      const c = parseRGB(getComputedStyle(n).backgroundColor);
      if (c && c.a >= 0.999) return c;
      n = n.parentElement;
    }
    return {r: 255, g: 255, b: 255, a: 1};
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function contrast(a, b) {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }
  function hasDirectText(el) {
    for (const n of el.childNodes)
      if (n.nodeType === 3 && n.textContent.trim()) return true;
    return false;
  }

  // images
  document.querySelectorAll("img").forEach(img => {
    if (!img.hasAttribute("alt")) add("runtime-img-no-alt", "<img> has no alt", img);
    if (img.complete && img.naturalWidth === 0 && (img.getAttribute("src") || "").trim())
      add("runtime-broken-image", "image failed to load: " +
          (img.currentSrc || img.getAttribute("src") || "").slice(0, 80), img);
  });

  // buttons / links with no accessible name
  document.querySelectorAll("button, a[href], [role=button]").forEach(el => {
    if (visible(el) && !accName(el))
      add("runtime-button-no-name", el.tagName.toLowerCase() + " has no accessible name", el);
    if (rendered(el) && (el.tagName === "BUTTON" || el.getAttribute("role") === "button")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0)
        add("runtime-zero-size", "interactive element is 0x0 (collapsed)", el);
    }
    if (visible(el)) {
      const r = el.getBoundingClientRect();
      const m = Math.min(r.width, r.height);
      if (m > 0 && m < 24)
        add("runtime-tiny-target", "hit area only " + Math.round(r.width) + "x" +
            Math.round(r.height) + "px", el);
    }
  });

  // form controls without a real label
  const SKIP = new Set(["hidden", "submit", "button", "reset", "image"]);
  document.querySelectorAll("input, select, textarea").forEach(el => {
    if (el.tagName === "INPUT" && SKIP.has((el.getAttribute("type") || "text").toLowerCase()))
      return;
    if (!visible(el)) return;
    const labelled =
      (el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]')) ||
      el.closest("label") ||
      (el.getAttribute("aria-label") || "").trim() ||
      el.getAttribute("aria-labelledby") ||
      (el.getAttribute("title") || "").trim();
    if (!labelled)
      add("runtime-input-no-label", el.tagName.toLowerCase() +
          " has no associated label", el);
  });

  // dialogs / modals
  document.querySelectorAll('[role=dialog], [class*="modal" i], [class*="dialog" i]')
    .forEach(el => {
      if (!visible(el)) return;
      const role = el.getAttribute("role");
      if (role !== "dialog" || el.getAttribute("aria-modal") !== "true" || !accName(el))
        add("runtime-dialog-no-aria",
            "visible modal missing role=dialog / aria-modal / name", el);
    });

  // contrast
  const textEls = document.querySelectorAll(
    "p,span,a,button,li,td,th,label,h1,h2,h3,h4,h5,h6,div,strong,em,small");
  textEls.forEach(el => {
    if (seen["runtime-low-contrast"] >= CAP) return;
    if (!hasDirectText(el) || !visible(el)) return;
    const cs = getComputedStyle(el);
    const fg = parseRGB(cs.color);
    if (!fg || fg.a === 0) return;
    const bg = effBg(el);
    const ratio = contrast(fg, bg);
    const size = parseFloat(cs.fontSize);
    const large = size >= 24 || (size >= 18.66 && +cs.fontWeight >= 700);
    const min = large ? 3 : 4.5;
    if (ratio < min)
      add("runtime-low-contrast",
          ratio.toFixed(2) + ":1 (need " + min + ":1) for \"" +
          el.textContent.trim().slice(0, 30) + "\"", el);
  });

  // duplicate ids
  const ids = {};
  document.querySelectorAll("[id]").forEach(el => {
    const id = el.id;
    ids[id] = (ids[id] || 0) + 1;
  });
  Object.keys(ids).forEach(id => {
    if (ids[id] > 1)
      out.push({rule: "runtime-duplicate-id",
                message: 'id "' + id + '" used ' + ids[id] + " times", selector: "#" + id});
  });

  // horizontal overflow
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 2) {
    const offenders = [];
    document.querySelectorAll("body *").forEach(el => {
      if (offenders.length >= 5) return;
      const r = el.getBoundingClientRect();
      if (r.right > window.innerWidth + 2 && r.width <= de.scrollWidth)
        offenders.push(sel(el));
    });
    out.push({rule: "runtime-horizontal-overflow",
              message: "page is " + de.scrollWidth + "px wide vs " + de.clientWidth +
                       "px viewport; offenders: " + (offenders.join(", ") || "n/a"),
              selector: "html"});
  }

  return out;
})()
"""

# --------------------------------------------------------------------------- #
# Console / network harvesting from CDP events
# --------------------------------------------------------------------------- #

_REACT_KEY = ("unique \"key\"", "unique key", "each child in a list")
_NOTABLE_WARN = ("validatedomnesting", "controlled", "uncontrolled",
                 "unique \"key\"", "each child in a list")


def _arg_text(args):
    parts = []
    for a in args or []:
        v = a.get("value", a.get("description", ""))
        parts.append(str(v))
    return " ".join(parts).strip()


def harvest(events):
    findings = []
    seen = set()

    def emit(rule, message, selector=""):
        key = (rule, message[:120])
        if key in seen:
            return
        seen.add(key)
        meta = RUNTIME_RULES[rule]
        findings.append(Finding(rule, meta["severity"], meta["category"], 0,
                                message, selector, meta["fix"]))

    for ev in events:
        m = ev.get("method")
        p = ev.get("params", {})
        if m == "Runtime.consoleAPICalled":
            typ = p.get("type")
            text = _arg_text(p.get("args"))
            low = text.lower()
            if typ in ("error", "assert"):
                emit("runtime-console-error", text[:200] or "console error")
            elif typ == "warning":
                if any(k in low for k in _REACT_KEY):
                    emit("runtime-react-key-warning", text[:200])
                elif any(k in low for k in _NOTABLE_WARN):
                    emit("runtime-console-error", text[:200])
        elif m == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            txt = d.get("text", "")
            ex = d.get("exception", {})
            txt = (ex.get("description") or txt or "uncaught exception")
            emit("runtime-console-error", str(txt)[:200])
        elif m == "Log.entryAdded":
            e = p.get("entry", {})
            if e.get("level") == "error":
                emit("runtime-console-error", str(e.get("text", ""))[:200],
                     e.get("url", ""))
        elif m == "Network.responseReceived":
            r = p.get("response", {})
            if r.get("status", 0) >= 400:
                emit("runtime-network-error",
                     "HTTP %s %s" % (r.get("status"), r.get("url", "")[:120]))
        elif m == "Network.loadingFailed":
            if not p.get("canceled"):
                emit("runtime-network-error",
                     "request failed: %s" % p.get("errorText", "")[:120])
    return findings


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def run_scan(url, attach=None, browser=None, headed=False, wait_ms=1200,
             click=None):
    br = Browser(browser_path=browser, headless=not headed, port=attach)
    cdp = None
    try:
        ws = br.new_page()
        cdp = CDP(ws)
        cdp.enable()
        cdp.navigate(url)
        cdp.drain(wait_ms / 1000.0)  # let the SPA hydrate / fire XHRs

        dom = cdp.eval(AUDIT_JS) or []
        if click:
            try:
                cdp.eval("(()=>{const e=document.querySelector(%r);"
                         "if(e)e.click();return !!e;})()" % click)
                cdp.drain(max(wait_ms, 800) / 1000.0)
                dom += cdp.eval(AUDIT_JS) or []
            except Exception as exc:
                print("note: --click failed: %s" % exc, file=sys.stderr)

        findings = harvest(cdp.events) + _dom_to_findings(dom)
        return findings
    finally:
        if cdp:
            cdp.close()
        br.close()


def _dom_to_findings(dom):
    out, seen = [], set()
    for d in dom:
        rule = d.get("rule")
        meta = RUNTIME_RULES.get(rule)
        if not meta:
            continue
        key = (rule, d.get("message", "")[:120], d.get("selector", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(Finding(rule, meta["severity"], meta["category"], 0,
                           d.get("message", meta["summary"]),
                           d.get("selector", ""), meta["fix"]))
    return out


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def _counts(findings):
    c = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        c[f.severity] += 1
    return c


def render_text(url, findings, color):
    def c(s, code):
        return code + s + RESET if color else s
    if not findings:
        return c("ui-ux-doctor (live): %s -- no runtime issues found ✓" % url, "\033[32m")
    findings = sorted(findings, key=lambda f: (-SEVERITY_ORDER[f.severity], f.rule_id))
    out = [c(url, BOLD)]
    for f in findings:
        tag = c(SEV_TAG[f.severity], SEV_COLOR[f.severity]) if color else SEV_TAG[f.severity]
        loc = ("  @ " + f.snippet) if f.snippet else ""
        out.append("  %s  [%s] %s%s" % (tag, f.rule_id, f.message, loc))
        out.append(c("        fix: " + f.fix, DIM))
    cnt = _counts(findings)
    out.append("")
    out.append(c("ui-ux-doctor (live): %d critical, %d warning, %d info" %
                 (cnt["critical"], cnt["warning"], cnt["info"]), BOLD))
    return "\n".join(out)


def render_json(url, findings):
    import json
    return json.dumps({
        "url": url,
        "summary": _counts(findings),
        "findings": [{"rule": f.rule_id, "severity": f.severity,
                      "category": f.category, "message": f.message,
                      "selector": f.snippet, "fix": f.fix} for f in findings],
    }, indent=2)


def render_markdown(url, findings):
    out = ["# ui-ux-doctor live report", "", "**URL:** `%s`" % url, ""]
    if not findings:
        out.append("No runtime issues found. ✓")
        return "\n".join(out)
    cnt = _counts(findings)
    out.append("**%d critical · %d warning · %d info**" %
               (cnt["critical"], cnt["warning"], cnt["info"]))
    out.append("")
    out.append("| Severity | Rule | Issue | Where | Fix |")
    out.append("|----------|------|-------|-------|-----|")
    for f in sorted(findings, key=lambda f: (-SEVERITY_ORDER[f.severity], f.rule_id)):
        msg = f.message.replace("|", "\\|")
        fix = f.fix.replace("|", "\\|")
        out.append("| %s | `%s` | %s | `%s` | %s |" %
                   (f.severity, f.rule_id, msg, f.snippet, fix))
    return "\n".join(out)


def list_rules():
    print("%-28s %-9s %-13s %s" % ("RULE", "SEVERITY", "CATEGORY", "SUMMARY"))
    print("-" * 100)
    for rid, meta in sorted(RUNTIME_RULES.items(),
                            key=lambda kv: (-SEVERITY_ORDER[kv[1]["severity"]], kv[0])):
        print("%-28s %-9s %-13s %s" % (rid, meta["severity"], meta["category"],
                                       meta["summary"]))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ui-ux-doctor (live)",
        description="Runtime UI/UX scanner: drives an installed browser to scan a "
                    "running app's rendered DOM. Zero dependencies.")
    p.add_argument("url", nargs="?", help="URL of the running app, e.g. http://localhost:5173")
    p.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
    p.add_argument("--fail-on", choices=["info", "warning", "critical", "never"],
                   default="warning", help="Exit 1 if a finding >= this exists (default: warning).")
    p.add_argument("--attach", type=int, metavar="PORT",
                   help="Attach to a browser you launched with --remote-debugging-port=PORT.")
    p.add_argument("--browser", help="Path to a Chrome/Edge/Chromium binary (or set UXD_BROWSER).")
    p.add_argument("--headed", action="store_true", help="Show the browser window (default: headless).")
    p.add_argument("--wait", type=int, default=1200, metavar="MS",
                   help="Settle time after load for SPA hydration/XHR (default: 1200).")
    p.add_argument("--click", metavar="SELECTOR",
                   help="After the first scan, click this CSS selector (e.g. to open a "
                        "modal) and scan again.")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args(argv)

    if args.list_rules:
        list_rules()
        return 0
    if not args.url:
        p.error("a URL is required (or use --list-rules)")

    try:
        findings = run_scan(args.url, attach=args.attach, browser=args.browser,
                            headed=args.headed, wait_ms=args.wait, click=args.click)
    except Exception as exc:
        print("ui-ux-doctor (live) error: %s" % exc, file=sys.stderr)
        return 2

    color = sys.stdout.isatty() and not args.no_color
    if args.format == "json":
        print(render_json(args.url, findings))
    elif args.format == "markdown":
        print(render_markdown(args.url, findings))
    else:
        print(render_text(args.url, findings, color))

    if args.fail_on == "never":
        return 0
    gate = SEVERITY_ORDER[args.fail_on]
    return 1 if any(SEVERITY_ORDER[f.severity] >= gate for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
