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

## Components — modals, dialogs, sidebars (`.jsx` `.tsx` …)

### `modal-no-a11y` — warning · component
An element that looks like a modal/dialog (className contains `modal`/`dialog`) but has
no `role="dialog"`. **Why:** screen readers don't announce it and focus leaks to the page
behind. **Fix:** `role="dialog" aria-modal="true"` + `aria-labelledby`, trap focus while
open, restore focus on close.

### `dialog-no-label` — warning · accessibility
`role="dialog"` with no accessible name. **Why:** announced as just "dialog". **Fix:**
`aria-labelledby` pointing at the title, or `aria-label`.

### `modal-no-escape` — info · component
A modal/dialog appears in the file but nothing handles the Escape key. **Why:** users
expect Esc to dismiss overlays; without it they can feel trapped. **Fix:** a keydown
listener closing on `key === 'Escape'` (and close on backdrop click). *(Heuristic,
file-level — won't see an Esc handler that lives in a shared hook.)*

### `sidebar-no-landmark` — info · component
An element with `sidebar`/`drawer` in its className that isn't a `<nav>`/`<aside>` and has
no `role`. **Why:** a sidebar made of plain `<div>`s is invisible as a landmark. **Fix:**
use `<nav>`/`<aside>` or add the matching role.

### `nested-interactive` — warning · accessibility
An interactive element nested inside another (e.g. `<button>` inside `<a>`). **Why:**
invalid HTML with unpredictable click/focus behavior. **Fix:** use a single interactive
element or restructure.

---

## Forms — inputs, textareas, selects (`.jsx` `.tsx` …)

### `input-no-label` — warning · forms
An `<input>`/`<select>` with no `aria-label`, `aria-labelledby`, `id`, or wrapping
`<label>`. **Why:** unusable with screen readers; breaks click-to-focus. **Fix:** a
`<label htmlFor>` tied to the id, a wrapping `<label>`, or `aria-label`. A placeholder is
**not** a label. *(Inputs wrapped in a `<label>` and `type=hidden/submit/button/...` are
skipped.)*

### `textarea-no-label` — warning · forms
A `<textarea>` with no associated label. **Fix:** as above.

### `password-no-autocomplete` — info · forms
`<input type="password">` without `autocomplete`. **Why:** breaks password managers /
autofill. **Fix:** `autocomplete="current-password"` (login) or `"new-password"` (signup).

### `form-no-onsubmit` — info · forms
A `<form>` with no `onSubmit`. **Why:** pressing Enter triggers a full page reload, losing
app state. **Fix:** handle `onSubmit` and call `e.preventDefault()`.

---

## Theming — light / dark mode (`.jsx` `.tsx` …)

### `no-dark-variant` — info · theming
A light-mode Tailwind utility (`bg-white`, `text-black`, `bg-gray-50`, …) in a literal
className with no `dark:` variant. **Why:** stays light in dark mode → white flashes and
unreadable contrast. **Fix:** pair them, e.g. `bg-white dark:bg-slate-900`,
`text-black dark:text-white`. *(Only literal className strings are checked, to avoid noise
on dynamic class expressions.)*

### `hardcoded-theme-color` — info · theming
A literal black/white color (`#fff`, `#000`, `white`, `black`) in an inline style. **Why:**
doesn't adapt to themes and drifts from the design system. **Fix:** use theme tokens / CSS
variables or Tailwind classes with `dark:` variants.

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
