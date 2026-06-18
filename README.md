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

## Install

There's nothing to install. You need Python 3.8+.

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

Buttons & interaction · rendering (keys, `0`-leaks, effect loops, dangerous HTML) ·
accessibility (labels, alt text, tab order) · React↔FastAPI integration (hardcoded
hosts, CORS wildcard+credentials) · cleanliness (stray logs).

Full list with rationale and fixes: [`data/rules.md`](data/rules.md), or
`python3 scripts/scan.py --list-rules`.

The scanner is **heuristic** — it flags strong candidates fast and explains each one. It
won't catch everything a full AST/runtime tool would, and it can occasionally
false-positive; always confirm a finding in context before "fixing" it.

## Try it

```bash
python3 scripts/scan.py examples/        # buggy sample app: 1 critical + several warnings
python3 -m unittest discover -s tests    # run the test suite
```

## License

MIT — see [LICENSE](LICENSE).
