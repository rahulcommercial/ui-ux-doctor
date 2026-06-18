# ui-ux-doctor — Rule catalogue

Every rule, why it matters, and how to fix it. Rules are heuristic: they flag strong
candidates for a human/Claude to confirm in context. Generated to mirror
`scripts/rules.py`.

Severity:
- **critical** — actively breaks the app for real users.
- **warning** — a real bug or accessibility failure most users will hit.
- **info** — smell / cleanup.

---

## React / JSX (`.jsx` `.tsx` `.js` `.ts`)

### `clickable-nonbutton` — warning · interaction
`onClick` on a non-interactive element (`div`, `span`, `li`, headings, …).
**Why:** such elements aren't keyboard-focusable and announce nothing to screen
readers — the classic "button does nothing on keyboard / for screen-reader users".
**Fix:** use a `<button>` (or `<a>` for navigation). If the tag must stay, add
`role="button"`, `tabIndex={0}` and an `onKeyDown` handler. *(Tags that already have
`role` + a key handler are not flagged.)*

### `icon-button-no-label` — warning · accessibility
An icon-only `<button>` (contains `<svg>`/`Icon`/`<i>` and no text) with no accessible
name. **Why:** screen readers announce it as just "button". **Fix:** add `aria-label`
(or visually-hidden text) to the button and `aria-hidden="true"` on the icon.

### `missing-key` — warning · rendering
`.map()` returns an element without a `key`. **Why:** React reuses the wrong DOM nodes
— stale content, lost input focus, flicker. **Fix:** `key={item.id}` on the top-level
returned element.

### `index-as-key` — warning · rendering
Array index used as `key` (`key={index}`). **Why:** breaks when the list reorders,
inserts, or deletes, corrupting inputs/animations. **Fix:** stable unique id.

### `length-and-leak` — warning · rendering
`x.length && <JSX>`. **Why:** when length is `0`, React renders the literal `0` — a
stray "0" appears in the UI. **Fix:** `{x.length > 0 && <JSX>}` or `{!!x.length && …}`.

### `img-no-alt` — warning · accessibility
`<img>` with no `alt`. **Why:** invisible to screen readers; shows nothing on load
failure. **Fix:** `alt="description"`, or `alt=""` for purely decorative images.

### `dangerous-html` — warning · rendering
`dangerouslySetInnerHTML`. **Why:** XSS and frequent layout breakage. **Fix:** render
text/JSX directly; if HTML is required, sanitize server-side and confirm the source is
trusted.

### `hardcoded-localhost` — warning · integration
A hardcoded `http://localhost` / `127.0.0.1` URL. **Why:** works on your machine,
breaks everywhere else — the "works locally, blank in prod" bug. **Fix:** read the API
base from env/config (`import.meta.env.VITE_API_URL`, etc.).

### `button-no-type` — info · interaction
`<button>` with no explicit `type`. **Why:** inside a `<form>` it defaults to
`type=submit`, so clicking reloads the page / submits unexpectedly. **Fix:**
`type="button"` (or `type="submit"` when it really submits).

### `positive-tabindex` — info · accessibility
`tabIndex` greater than 0. **Why:** hijacks the natural tab order. **Fix:** use
`tabIndex={0}` or `tabIndex={-1}`; never positive.

### `autofocus` — info · accessibility
`autoFocus`. **Why:** unexpectedly moves the viewport and steals focus on load. **Fix:**
confirm it's intentional; avoid on routed pages and modals that manage focus themselves.

### `useeffect-no-deps` — info · rendering
`useEffect(() => {…})` with no dependency array. **Why:** runs after every render — a
common cause of infinite fetch loops / re-render storms. **Fix:** add deps; `[]` for
mount-only.

### `inline-style-object` — info · performance
`style={{…}}` literal. **Why:** a new object each render breaks memoization and can
re-render children. **Fix:** move static styles to a class; memoize dynamic ones.

### `console-log` — info · cleanliness
Leftover `console.log` / `console.debug`. **Fix:** remove before shipping or gate behind
a debug flag.

---

## FastAPI / Python (`.py`)

### `cors-wildcard-credentials` — critical · integration
CORS `allow_origins=["*"]` together with `allow_credentials=True`. **Why:** browsers
reject `*` when credentials are sent — authed requests fail and the React UI silently
can't load its data. **Fix:** list explicit origins, e.g.
`allow_origins=["https://app.example.com"]`.

### `cors-wildcard` — info · integration
`allow_origins=["*"]` (without credentials). **Why:** fine for quick local dev, unsafe
and brittle in shared/production environments. **Fix:** restrict to the real frontend
origin(s).

### `hardcoded-localhost` — warning · integration
Hardcoded `http://localhost` / `127.0.0.1`. **Fix:** read from `os.environ`/config.

### `print-debug` — info · cleanliness
`print()` in server code. **Why:** bypasses log levels/handlers, clutters output.
**Fix:** use `logging`.
