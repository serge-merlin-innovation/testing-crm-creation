---
name: install-design-system
description: Install the project's design system from docs/design-system/ (a Claude Design export committed to the repo) into apps/frontend, its fonts and tokens. Use for a project's first install and every time docs/design-system/ is replaced with a newer export.
---

# Install a design system

The design system is designed in Claude Design (claude.ai/design), downloaded from there, and
committed to `docs/design-system/`. That folder is the source of truth: this skill reads it and
never fetches anything. The output is `apps/frontend/public/fonts/` and the `@theme` token block in
`apps/frontend/src/app/globals.css`, the only CSS file in the app (`docs/agents/CONSTITUTION.md`).
Tailwind v4 turns each `@theme` token into utility classes (`--color-accent` → `bg-accent`), and
those classes are the only way screens and `src/components/ui/` style anything. It installs the
foundation only; components and screens come later and read from it.

## Settled — apply as given

| Decision | Settled as |
| --- | --- |
| Source | `docs/design-system/`, the export downloaded from Claude Design and committed. No link, no fetch, no copy in `~/Downloads`: an update is a new export replacing that folder in its own commit, so the diff shows what changed |
| Token names | The design system's own name behind the Tailwind namespace for its kind (table in step 3), so a re-install still diffs line by line |
| Tailwind defaults | Stay switched off: every namespace the baseline resets with `initial` (`--color-*`, `--radius-*`, `--font-*`, `--text-*`, `--shadow-*`) keeps its reset, so only design-system tokens produce classes |

## 1. Read the design system from `docs/design-system/`

The user downloads the design-system project from Claude Design (**Export → Download as .zip**),
unzips it into `docs/design-system/` and commits it. When that folder is empty or missing, stop and
ask for it: it is the one input only the user can produce. Leave the folder as it is: it is the
export, not a working copy, so the skill reads from it and never edits it.

Find the design-system files. Two export layouts carry the same files:

| Export | Where the design-system files are |
| --- | --- |
| A design-system project | at the folder root |
| A mockup: `<Name>.dc.html` beside `_ds/` | in `_ds/<system>-<id>/` |

```bash
find docs/design-system -name _ds_manifest.json
```

From there you use `colors_and_type.css` (tokens and `@font-face` blocks), `fonts/`, and
`_ds_manifest.json` (`namespace`, `themes`, `fonts`). The rest stays in `docs/design-system/`
for reference and is not installed: `_ds_bundle.js`, `preview/`, `slides/`, `assets/`, and the
export's own `SKILL.md` and `_adherence.oxlintrc.json`.

**Done when** `_ds_manifest.json` is found and the user has confirmed its `namespace` as this
project's design system.

## 2. Copy the fonts

Self-hosting publishes the font files at a public URL, so check the licence covers web use first:
Merlin's design system ships Microsoft's Aptos. When the licence is unclear, ask before copying.

A design system ships the whole family (Merlin's is 28 files, 5.6 MB). Copy from
`docs/design-system/` into
`apps/frontend/public/fonts/` only the faces the type tokens use: each `--font-*` family at each
`--fw-*` weight, normal style, plus the italic of the body weight for `<em>`. Point each
`@font-face` `src` at `/fonts/<file>`: Next.js serves `public/` from the site root.

**Done when** every `@font-face` you keep points at a file in `public/fonts/`, and every file there
has its `@font-face`.

## 3. Replace the token block

`globals.css` holds, in order: `@import "tailwindcss"`, the `@font-face` blocks, one `@theme`
block of tokens, and `@layer base` with the element defaults (`body`, headings, borders, focus
outline). Nothing else: no classes, no theme override block, no second stylesheet.

- **Replace the `@theme` tokens wholesale** with the design system's. On a fresh boilerplate they
  are a neutral shadcn placeholder palette; merging the two leaves ghosts of both. Keep each
  namespace's `--…-*: initial` reset line at the top of its group.
- **Rename each token into its Tailwind namespace**, keeping the design system's own name after
  the prefix:

  | Design-system token | `@theme` token | Class it produces |
  | --- | --- | --- |
  | colour `--accent`, `--fg-muted` | `--color-accent`, `--color-fg-muted` | `bg-accent`, `text-fg-muted` |
  | spacing scale `--space-1: 4px` … | `--spacing: 0.25rem` (the scale's step) | `p-1`, `gap-4` |
  | off-scale spacing `--space-gutter` | `--spacing-gutter` | `p-gutter` |
  | radius `--radius-md` | `--radius-md` | `rounded-md` |
  | font family `--font-sans` | `--font-sans` | `font-sans` |
  | font size `--fs-md` + `--lh-md` | `--text-md` + `--text-md--line-height` | `text-md` |
  | font weight `--fw-medium` | `--font-weight-medium` | `font-medium` |
  | shadow `--shadow-lg` | `--shadow-lg` | `shadow-lg` |
  | easing, duration `--ease`, `--duration-fast` | `--ease-standard`, `--duration-fast` | `ease-standard`, `duration-fast` |

  A token that fits no namespace stays a plain custom property inside `@theme` and is read with
  `var(--…)` from `@layer base` only.
- **Keep every token but the slide-only ones**: display sizes meant for 1920×1080 decks. With no
  screen built yet, the app-facing set is the whole design system.
- **Re-point the element defaults in `@layer base`** at the new tokens with `@apply` (`@apply
  bg-background text-foreground`). From the export take its element rules (`body`, `h1`–`h6`);
  its classes (`.eyebrow`, `.merlin-lockup`) do not come across: they become components in
  `src/components/ui/` when a screen needs them.
- **Leave `src/components/ui/` alone.** A component that reads a token the design system lacks
  is adapted to the new tokens, never the other way round (`CONSTITUTION.md`).

On a re-install the block already holds a design system: diff the old tokens against the new export
(`git diff` on `docs/design-system/` shows what changed) and list every renamed or removed token
that something still reads.

**Done when** both commands print nothing. The first checks every `var(--…)`, the second every
colour class under `src/` (Tailwind drops a class it can't resolve without an error, so the build
alone won't catch it):

```bash
cd apps/frontend
tokens=$(grep -oE '^ *--[a-z0-9-]+' src/app/globals.css | tr -d ' ' | sort -u)
comm -23 <(grep -rhoE 'var\(--[a-z0-9-]+' src | sed 's/var(//' | sort -u) <(echo "$tokens")
comm -23 \
  <(grep -rhoE '\b(bg|text|border|ring|outline|fill|stroke|divide|placeholder|from|via|to)-[a-z][a-z0-9-]*' src --include='*.tsx' \
      | sed -E 's/^[a-z]+-//; s/-[0-9]+$//' | sort -u) \
  <(echo "$tokens" | sed -n 's/^--color-//p'; printf '%s\n' transparent current inherit) \
  | grep -vxE 'xs|sm|base|md|lg|xl|[0-9]?xl|left|right|center|top|bottom|t|b|l|r|x|y|none|offset|inset|solid|dashed|dotted|double|hidden|wrap|nowrap|ellipsis|clip|balance|pretty|start|end|justify'
```

The second list may still show non-colour words (`text-ellipsis`): read it, and fix only the
names that were colour tokens.

## 4. Reconcile the type scale

Point every heading and body default at a `--text-*` step. Extend the scale only for a size the
design system's own type specimen uses.

**Done when** no `font-size` or `line-height` appears in `globals.css` outside `@theme`, and every
`text-[…]` arbitrary value is absent from `src/` (`grep -rn 'text-\[' src` prints nothing).

## 5. Verify

Run the frontend gates: `pnpm --filter @merlin/frontend lint`, `typecheck`, `test` and `build`.
Then in the browser: `document.fonts.check('400 16px <Family>')` is true for each family, and
`body`'s computed colours match `--color-background` and `--color-foreground`. A dev server may
already own port 3000: attach to it with `preview_start` and its URL rather than starting a second
one.

**Done when** the gates pass and your report names the design system's `namespace`, the fonts
copied (files and total size), and each dropped token with its reason.
