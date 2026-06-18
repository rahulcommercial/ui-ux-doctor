#!/usr/bin/env python3
"""
ui-ux-doctor -- zero-dependency UI/UX bug scanner for React + FastAPI.

Pure Python standard library. No pip, no npm, no network. Drop the repo anywhere
(including a locked-down office machine) and run:

    python3 scripts/scan.py path/to/your/app

Scans .jsx/.tsx/.js/.ts (React) and .py (FastAPI) for common UI/UX bugs:
button/interaction issues, rendering issues (keys, 0-leaks, effects), accessibility
gaps, and React<->FastAPI integration mistakes (CORS, hardcoded hosts).

Exit code is 0 when nothing at/above the threshold is found, else 1 -- so it works
as a CI gate.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import RULES, SEVERITY_ORDER, JSX_EXT, PY_EXT, scan_text  # noqa: E402

IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "out", "coverage",
    "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", "vendor", "site-packages",
}
SCAN_EXT = JSX_EXT | PY_EXT

SEV_TAG = {"critical": "CRIT", "warning": "WARN", "info": "INFO"}
SEV_COLOR = {"critical": "\033[31m", "warning": "\033[33m", "info": "\033[36m"}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def discover(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1] in SCAN_EXT:
                yield os.path.join(dirpath, name)


def scan_path(root, threshold):
    results = []  # (filepath, [Finding, ...])
    min_sev = SEVERITY_ORDER[threshold]
    for path in discover(root):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        ext = os.path.splitext(path)[1]
        findings = [f for f in scan_text(text, ext)
                    if SEVERITY_ORDER[f.severity] >= min_sev]
        if findings:
            findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.line))
            results.append((path, findings))
    results.sort(key=lambda r: r[0])
    return results


def _counts(results):
    c = {"critical": 0, "warning": 0, "info": 0}
    for _, fs in results:
        for f in fs:
            c[f.severity] += 1
    return c


def _rel(path, root):
    try:
        return os.path.relpath(path, root if os.path.isdir(root) else os.path.dirname(root) or ".")
    except ValueError:
        return path


def render_text(results, root, color):
    out = []
    def c(s, code):
        return f"{code}{s}{RESET}" if color else s
    if not results:
        out.append(c("ui-ux-doctor: no issues found ✓", "\033[32m"))
        return "\n".join(out)
    for path, findings in results:
        out.append(c(_rel(path, root), BOLD))
        for f in findings:
            tag = c(SEV_TAG[f.severity], SEV_COLOR[f.severity]) if color else SEV_TAG[f.severity]
            out.append(f"  {tag}  {_rel(path, root)}:{f.line}  [{f.rule_id}] {f.message}")
            if f.snippet:
                out.append(c(f"        > {f.snippet}", DIM))
            out.append(c(f"        fix: {f.fix}", DIM))
        out.append("")
    cnt = _counts(results)
    summary = f"{cnt['critical']} critical, {cnt['warning']} warning, {cnt['info']} info"
    out.append(c(f"ui-ux-doctor: {summary}", BOLD))
    return "\n".join(out)


def render_markdown(results, root):
    out = ["# ui-ux-doctor report", ""]
    if not results:
        out.append("No issues found. ✓")
        return "\n".join(out)
    cnt = _counts(results)
    out.append(f"**{cnt['critical']} critical · {cnt['warning']} warning · {cnt['info']} info**")
    out.append("")
    for path, findings in results:
        out.append(f"## `{_rel(path, root)}`")
        out.append("")
        out.append("| Line | Severity | Rule | Issue | Fix |")
        out.append("|------|----------|------|-------|-----|")
        for f in findings:
            msg = f.message.replace("|", "\\|")
            fix = f.fix.replace("|", "\\|")
            out.append(f"| {f.line} | {f.severity} | `{f.rule_id}` | {msg} | {fix} |")
        out.append("")
    return "\n".join(out)


def render_json(results, root):
    payload = {
        "summary": _counts(results),
        "files": [
            {
                "file": _rel(path, root),
                "findings": [
                    {
                        "rule": f.rule_id, "severity": f.severity,
                        "category": f.category, "line": f.line,
                        "message": f.message, "snippet": f.snippet, "fix": f.fix,
                    }
                    for f in findings
                ],
            }
            for path, findings in results
        ],
    }
    return json.dumps(payload, indent=2)


def list_rules():
    rows = sorted(RULES.items(),
                  key=lambda kv: (-SEVERITY_ORDER[kv[1]["severity"]], kv[1]["category"], kv[0]))
    print(f"{'RULE':<28} {'SEVERITY':<9} {'CATEGORY':<14} SUMMARY")
    print("-" * 100)
    for rid, meta in rows:
        print(f"{rid:<28} {meta['severity']:<9} {meta['category']:<14} {meta['summary']}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ui-ux-doctor",
        description="Zero-dependency UI/UX bug scanner for React + FastAPI.")
    p.add_argument("path", nargs="?", default=".",
                   help="File or directory to scan (default: current dir).")
    p.add_argument("-f", "--format", choices=["text", "markdown", "json"],
                   default="text", help="Output format (default: text).")
    p.add_argument("-s", "--severity", choices=["info", "warning", "critical"],
                   default="info", help="Minimum severity to report (default: info).")
    p.add_argument("--fail-on", choices=["info", "warning", "critical", "never"],
                   default="warning",
                   help="Exit 1 if a finding at/above this severity exists "
                        "(default: warning). Use 'never' to always exit 0.")
    p.add_argument("--list-rules", action="store_true",
                   help="Print the rule catalogue and exit.")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    args = p.parse_args(argv)

    if args.list_rules:
        list_rules()
        return 0

    if not os.path.exists(args.path):
        print(f"ui-ux-doctor: path not found: {args.path}", file=sys.stderr)
        return 2

    results = scan_path(args.path, args.severity)
    color = sys.stdout.isatty() and not args.no_color

    if args.format == "json":
        print(render_json(results, args.path))
    elif args.format == "markdown":
        print(render_markdown(results, args.path))
    else:
        print(render_text(results, args.path, color))

    if args.fail_on == "never":
        return 0
    gate = SEVERITY_ORDER[args.fail_on]
    has_blocking = any(SEVERITY_ORDER[f.severity] >= gate
                       for _, fs in results for f in fs)
    return 1 if has_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
