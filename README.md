# ui-ux-doctor

**Zero-dependency UI/UX bug doctor for React + FastAPI apps.**

Finds, explains, and helps you fix the bugs that make a working-*looking* UI actually
broken — dead buttons, rendering glitches, accessibility gaps, and React↔FastAPI
integration mistakes — then helps you verify the fix.

It's **pure Python standard library**: no `pip`, no `npm`, no network. That's the whole
point — it runs on locked-down / offline / corporate machines where you *can't* install
`eslint-plugin-jsx-a11y` or `axe-core`. Clone it, run it, done.

```bash
python3 scripts/scan.py path/to/your/app
```

```
src/components/Cart.tsx
  WARN  src/components/Cart.tsx:23  [clickable-nonbutton] onClick on a non-interactive element (div/span/li/...).
        > <div onClick={() => removeItem(id)}>Remove</div>
        fix: Use a <button> (or <a> for navigation). If you must keep the tag, add role="button", tabIndex={0} and an onKeyDown handler.
  WARN  src/components/Cart.tsx:31  [missing-key] .map() renders an element without a key prop.
        fix: Add a stable key={item.id} to the top-level element returned by .map().

api/main.py
  CRIT  api/main.py:14  [cors-wildcard-credentials] CORS allow_origins=['*'] together with allow_credentials=True.
        fix: List explicit origins. The browser rejects wildcard + credentials, so authed requests fail.

ui-ux-doctor: 1 critical, 2 warning, 0 info
```

## Why this exists

`eslint-plugin-jsx-a11y`, `axe-core`, and friends are great — but they need a Node
toolchain and a package install. On a restricted work machine you often can't do that.
`ui-ux-doctor` is a single, dependency-free Python tool you can drop into any repo (and
into Claude Code as a skill) to catch the most common, highest-impact UI bugs across
**both** the React frontend and the FastAPI backend that serves it.

It's a **QA / debugging** tool, not a design generator — it complements design-system
skills rather than replacing them.

## Two modes: static + runtime

| Mode | Command | Scans | Needs |
|------|---------|-------|-------|
| **Static** | `python3 scripts/scan.py PATH` | source files (`.jsx/.tsx/.js/.ts/.py`) | Python only |
| **Runtime (live)** | `python3 scripts/scan_live.py URL` | the **rendered DOM** of a *running* app | Python + a Chrome/Edge/Chromium already installed |

The **runtime** scanner drives the browser already on the machine over the Chrome
DevTools Protocol — still **pure stdlib, no pip/npm, no install, no network egress** (it
hand-rolls a tiny WebSocket + CDP client). It opens your running localhost app, lets
React render, and scans the *real* DOM, so it catches things static analysis can't:

- broken images, zero-size / collapsed buttons, content overflowing the viewport
- **real** color-contrast failures (computed from rendered colors)
- buttons/links with no accessible name; inputs with no real label association
- modals/dialogs missing dialog semantics
- React's own console warnings (e.g. missing `key`), uncaught exceptions
- failed API calls (HTTP 4xx/5xx) during load

```bash
# start your app first (npm run dev / uvicorn ...), then:
python3 scripts/scan_live.py http://localhost:5173
python3 scripts/scan_live.py http://localhost:8000 --click "#open-settings"  # open a modal & re-scan
python3 scripts/scan_live.py http://localhost:5173 --headed --wait 2000      # show the window
python3 scripts/scan_live.py http://localhost:5173 --attach 9222             # attach to your own browser
```

Browser discovery is automatic (Chrome/Edge/Chromium in the usual OS paths). Override
with `UXD_BROWSER=/path/to/browser`, or launch the browser yourself with
`--remote-debugging-port=9222` and use `--attach 9222`. Edge ships with Windows, so an
office machine almost always has a usable browser.

## Install

There's nothing to install. You need Python 3.8+ (and, for live mode, any Chromium-family browser).

```bash
git clone https://github.com/rahulcommercial/ui-ux-doctor.git
python3 ui-ux-doctor/scripts/scan.py /path/to/your/app
```

Use it as a **Claude Code skill** by placing the repo at
`.claude/skills/ui-ux-doctor/` in your project (the `SKILL.md` at the root is the
manifest). Claude will then run the find → fix → verify workflow automatically when you
ask it to check or debug UI.

## Usage

```bash
python3 scripts/scan.py [path] [options]

  path                 File or directory to scan (default: current dir)
  -f, --format         text (default) | markdown | json
  -s, --severity       Minimum severity to report: info | warning | critical
      --fail-on        Exit 1 if a finding >= this exists: info | warning | critical | never
                       (default: warning) — use as a CI gate
      --list-rules     Print the full rule catalogue and exit
      --no-color       Disable ANSI colors
```

Examples:

```bash
python3 scripts/scan.py src --severity warning      # hide info noise
python3 scripts/scan.py . -f markdown > report.md   # paste into a PR
python3 scripts/scan.py api -f json | jq '.summary' # machine-readable
python3 scripts/scan.py src --fail-on critical      # CI: block only on critical
```

## What it catches

28 rules across the frontend **and** the backend:

- **Buttons & interaction** — `onClick` on a `<div>`, missing button `type`, interactive
  nested inside interactive.
- **Components** — modals/dialogs with no `role`/`aria-modal`/Escape handler, dialogs with
  no accessible name, sidebars/drawers that aren't landmarks.
- **Forms** — inputs/textareas/selects with no label, password fields with no
  `autocomplete`, forms with no `onSubmit`.
- **Light/dark mode (theming)** — light-only Tailwind classes with no `dark:` variant,
  hardcoded `#fff`/`#000` inline colors.
- **Rendering** — missing/`index` keys, `x.length && <JSX>` `0`-leaks, `useEffect` with no
  deps (re-render/fetch loops), `dangerouslySetInnerHTML`, inline `style={{}}`.
- **Accessibility** — icon-only buttons with no label, `<img>` with no `alt`, positive
  `tabIndex`, `autoFocus`.
- **React ↔ FastAPI integration** — hardcoded hosts, CORS wildcard + credentials.
- **Cleanliness** — stray `console.log` / `print()`.

Full list with rationale and fixes: [`data/rules.md`](data/rules.md), or
`python3 scripts/scan.py --list-rules`.

The scanner is **heuristic** — it flags strong candidates fast and explains each one. It
won't catch everything a full AST/runtime tool would, and it can occasionally
false-positive; always confirm a finding in context before "fixing" it.

## Try it

```bash
# static
python3 scripts/scan.py examples/        # buggy sample app: 1 critical + many warnings
python3 -m unittest discover -s tests    # passing test suite (live test auto-skips w/o a browser)

# runtime
python3 -m http.server 8911 --directory examples &
python3 scripts/scan_live.py http://localhost:8911/live_demo.html
```

## License

MIT — see [LICENSE](LICENSE).
