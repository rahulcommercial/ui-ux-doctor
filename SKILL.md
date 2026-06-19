---
name: ui-ux-doctor
description: "Zero-dependency UI/UX bug doctor for React + FastAPI apps. Finds and fixes button issues, rendering bugs, accessibility gaps, component problems (modals, dialogs, sidebars/drawers), form/input/textarea issues, light/dark mode (theming) gaps, and React<->FastAPI integration mistakes, then suggests enhancements and verifies the fix. Pure Python stdlib — no pip, no npm, no network — safe for locked-down / offline / office machines. Actions: find, detect, scan, audit, review, debug, diagnose, fix, repair, improve, enhance, test, verify UI/UX. Elements: button, modal, dialog, sidebar, drawer, form, input, textarea, select, navbar. Symptoms: button does nothing, button not clickable / not keyboard accessible, modal has no escape, no focus trap, input has no label, textarea unlabeled, form reloads page on enter, no dark mode, white flash in dark mode, list re-renders wrong, stray 0 on screen, missing key warning, input loses focus, infinite re-render, fetch loop, blank page, CORS error, data not loading, image no alt, screen reader. Topics: accessibility, dark mode, theming, focus management, forms. Stack: React, JSX, TSX, Tailwind, FastAPI, Vite, fetch, CORS. Use after writing or before shipping UI code, or when a UI element misbehaves."
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
| **Interaction / buttons** | `onClick` on a `<div>` (not keyboard-accessible), `<button>` with no `type` (submits a form by accident), interactive nested inside interactive (button-in-anchor) |
| **Components (modals/sidebars)** | modal/dialog with no `role="dialog"` + `aria-modal`, dialog with no accessible name, modal with no Escape-to-close, sidebar/drawer that isn't a `<nav>`/`<aside>` landmark |
| **Forms (inputs/textareas)** | `<input>`/`<select>`/`<textarea>` with no label, password field with no `autocomplete`, `<form>` with no `onSubmit` (Enter reloads the page) |
| **Theming (light/dark mode)** | light-only Tailwind class with no `dark:` variant (white flash in dark mode), hardcoded `#fff`/`#000` inline colors that don't adapt |
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

## Two modes

| Mode | Command | Scans | Needs |
|------|---------|-------|-------|
| **Static** | `scripts/scan.py PATH` | source files (`.jsx/.tsx/.py`) | Python only |
| **Runtime (live)** | `scripts/scan_live.py URL` | the **rendered DOM** of a running app — real buttons/modals/contrast/console/network | Python + a Chrome/Edge/Chromium already installed |

Use **static** while writing code; use **runtime** to confirm the running app
actually renders and behaves. They catch different bugs — run both.

## Runtime (live) scanning

Drives the browser already on the machine over the DevTools Protocol (pure stdlib,
no pip/npm/network) to open a running localhost URL, let React render, and scan the
real DOM. It catches what static analysis can't: broken images, zero-size/collapsed
buttons, content overflowing the viewport, **real computed color-contrast** failures,
buttons/inputs with no real accessible name/label, modals missing dialog semantics,
React's own console warnings (e.g. missing key), uncaught exceptions, and failed API
calls (HTTP 4xx/5xx) during load.

```bash
# 1. start the app (its own dev server), e.g.:  npm run dev   /   uvicorn main:app
# 2. scan the running URL:
python3 scripts/scan_live.py http://localhost:5173
python3 scripts/scan_live.py http://localhost:8000 --click "#open-settings"  # open a modal, re-scan
python3 scripts/scan_live.py http://localhost:5173 --headed --wait 2000      # watch it, longer settle
python3 scripts/scan_live.py http://localhost:5173 --attach 9222             # attach to a browser you launched
python3 scripts/scan_live.py --list-rules
```

Browser discovery: it auto-finds Chrome/Edge/Chromium in the usual OS locations. If it
can't, set `UXD_BROWSER=/path/to/browser`, or launch the browser yourself with
`--remote-debugging-port=9222` and pass `--attach 9222`. Edge ships with Windows, so an
office machine almost always has one.

For a React **SPA**, point it at the running dev-server URL (not a built file) so JS has
actually rendered. `--wait` controls the settle time for hydration/XHR.

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
- `modal-no-a11y` → add `role="dialog" aria-modal="true"`, an `aria-labelledby`, focus
  trap + Esc-to-close.
- `input-no-label` / `textarea-no-label` → add a `<label htmlFor>` or `aria-label`
  (placeholder is not a label).
- `no-dark-variant` → pair light utilities with dark ones (`bg-white dark:bg-slate-900`).
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
3. **Exercise the actual running UI** to confirm the bug is really fixed:
   ```bash
   python3 scripts/scan_live.py http://localhost:<port>
   ```
   This loads the real page in a browser and reports rendered-DOM / console / network
   issues. For bugs behind an interaction (a modal, a dropdown), drive it with
   `--click "<selector>"` and re-scan. If no browser is available, fall back to a
   **manual keyboard+screen-reader pass**: Tab to the control, press Enter/Space,
   confirm it fires and is announced.
   Never report "fixed" from a green static scan alone — confirm the behavior at runtime.

## CI / pre-commit use

```bash
# fail the build on warnings and above
python3 scripts/scan.py src --fail-on warning
```

## Try it

```bash
python3 scripts/scan.py examples/        # 1 critical, plus component/form/theming warnings
python3 -m unittest discover -s tests    # 41 passing tests
```
