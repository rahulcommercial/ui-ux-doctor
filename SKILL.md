---
name: ui-ux-doctor
description: "Zero-dependency UI/UX bug doctor for React + FastAPI apps. Finds and fixes button issues, rendering bugs, accessibility gaps, and React<->FastAPI integration mistakes, then verifies the fix. Pure Python stdlib — no pip, no npm, no network — safe for locked-down / offline / office machines. Actions: find, detect, scan, audit, review, debug, diagnose, fix, repair, test, verify UI/UX bugs. Symptoms: button does nothing, button not clickable, button not keyboard accessible, list re-renders wrong, stray 0 on screen, missing key warning, input loses focus, infinite re-render, fetch loop, blank page, CORS error, data not loading, layout broken, image no alt, screen reader. Stack: React, JSX, TSX, FastAPI, Vite, fetch, CORS. Use after writing or before shipping UI code, or when a UI element misbehaves."
---

# UI/UX Doctor — Find, Fix & Verify UI Bugs (React + FastAPI)

A zero-dependency diagnostic skill. The scanner is **pure Python standard library**
— no pip, no npm, no internet — so it runs on locked-down office machines where
`eslint-plugin-jsx-a11y` / `axe-core` can't be installed.

It does NOT replace design taste — for *generating* a design system (palettes,
typography, styles) use a design skill. This skill is the **QA / debugging** half:
catch the bugs that make a working-looking UI actually broken, then fix and verify.

## When to use

- After writing or editing React components or FastAPI endpoints.
- Before shipping / opening a PR ("check this for UI bugs").
- When a symptom is reported: *"the button does nothing"*, *"a stray 0 shows up"*,
  *"the list jumps around"*, *"data won't load / CORS error"*, *"input loses focus"*.

## What it catches

| Category | Examples |
|----------|----------|
| **Interaction / buttons** | `onClick` on a `<div>` (not keyboard-accessible), `<button>` with no `type` (submits a form by accident) |
| **Rendering** | missing/`index` keys in `.map()`, `x.length && <JSX>` leaking a literal `0`, `useEffect` with no deps array (re-render/fetch loops), `dangerouslySetInnerHTML`, inline `style={{}}` |
| **Accessibility** | icon-only button with no `aria-label`, `<img>` without `alt`, positive `tabIndex`, `autoFocus` |
| **React ↔ FastAPI integration** | hardcoded `http://localhost` API URLs, FastAPI CORS `allow_origins=["*"]` + `allow_credentials=True` (browser blocks it → UI silently fails to load) |
| **Cleanliness** | leftover `console.log`, `print()` in handlers |

Run `python3 scripts/scan.py --list-rules` for the full catalogue. Full rationale per
rule is in [`data/rules.md`](data/rules.md).

## Prerequisites

Python 3.8+ only. Check:

```bash
python3 --version
```

Nothing to install.

## Workflow

### Step 1 — Scan (find)

Point it at the app (or a single file you just changed):

```bash
python3 scripts/scan.py path/to/app            # whole tree
python3 scripts/scan.py src/components/Cart.tsx # one file
```

It auto-skips `node_modules`, `dist`, `.venv`, etc., and scans
`.jsx .tsx .js .ts` (React) and `.py` (FastAPI).

Useful flags:

```bash
--format markdown        # paste into a PR / report
--format json            # machine-readable, for piping
--severity warning       # hide info-level noise
--fail-on critical       # CI gate: exit 1 only on critical
--list-rules             # show every rule + fix
```

### Step 2 — Triage

Read findings worst-first. Severity meaning:

- **CRIT** — actively breaks the app for real users (e.g. CORS wildcard+credentials
  → the React app can't load data). Fix before anything else.
- **WARN** — a real bug or accessibility failure most users will hit.
- **INFO** — smells / cleanups; fix opportunistically.

The scanner is **heuristic** — it surfaces strong candidates, not proofs. Open each
flagged `file:line`, confirm it's a genuine bug in context, and skip false positives
(e.g. a `<div onClick>` that already has `role` + `onKeyDown` is fine).

### Step 3 — Fix

Each finding ships with a concrete `fix:` line. Apply the minimal change that matches
the surrounding code style. Common ones:

- `clickable-nonbutton` → swap to `<button>`, or add `role="button" tabIndex={0}` + an
  `onKeyDown` handler.
- `missing-key` / `index-as-key` → use a stable `key={item.id}`.
- `length-and-leak` → `{items.length > 0 && <JSX>}`.
- `icon-button-no-label` → `aria-label="…"` on the button + `aria-hidden` on the icon.
- `useeffect-no-deps` → add the dependency array (`[]` for mount-only).
- `cors-wildcard-credentials` → replace `["*"]` with the explicit frontend origin(s).
- `hardcoded-localhost` → read the base URL from env/config.

### Step 4 — Verify (test)

1. **Re-scan** the file/tree and confirm the finding is gone and nothing new appeared:
   ```bash
   python3 scripts/scan.py path/to/app --severity warning
   ```
2. **Run the scanner's own tests** if you changed a rule:
   ```bash
   python3 -m unittest discover -s tests
   ```
3. **Exercise the actual UI** to confirm the bug is really fixed. Use whatever this
   environment provides, in order of preference:
   - a browser/preview tool if available (load the page, click the button, check the
     console for errors, resize for responsive);
   - otherwise a **manual keyboard+screen-reader pass**: Tab to the control, press
     Enter/Space, confirm it fires and is announced.
   Never report "fixed" from a green scan alone — confirm the behavior.

## CI / pre-commit use

```bash
# fail the build on warnings and above
python3 scripts/scan.py src --fail-on warning
```

## Try it

```bash
python3 scripts/scan.py examples/        # 1 critical, several warnings/infos
python3 -m unittest discover -s tests    # 22 passing tests
```
