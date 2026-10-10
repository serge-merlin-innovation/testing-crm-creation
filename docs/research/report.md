# Login page A/B test: latest boilerplate vs. ea6c63a

Two agents got the same prompt, "create a login page for apps/frontend". They ran at the same time in separate git worktrees.

| | NEW | OLD |
|---|---|---|
| Version | `main` @ `5c5dfa4` (Tailwind v4 + shadcn baseline, full `@theme` tokens) | `ea6c63a` "removed globals.css placeholder" (empty `globals.css`, "No Tailwind, no PostCSS") |
| Worktree / branch | `../merlin-wt-new` / `test/login-new` | `../merlin-wt-old` / `test/login-old` |
| Result commit | `0988511` (9 files, +420 / -42) | `c171f99` (16 files, +549 / -73) |
| Model | claude-opus-5-5 | claude-opus-5-5 |

Neither agent invoked `improve-codebase-architecture-afk`. The only mentions in either session journal are repo-wide `grep` hits and the agent's own statement. Neither session made a `Skill` call for it.

`main` gained `8f7c017` (to-tickets/implement skill docs) during the run. That commit doesn't touch the frontend, so it doesn't affect this comparison.

After the agents finished, I re-ran lint, typecheck and unit tests in both worktrees independently. Both pass: NEW 171/171, OLD 170/170.

## Time and tokens

These numbers come from the session journals in `~/.jcode/sessions`.

| | NEW | OLD |
|---|---|---|
| Wall clock | 11:52:19 to 11:56:50 UTC, **4 min 31 s** | 11:52:19 to 11:56:58 UTC, **4 min 39 s** |
| Model turns / tool calls | 31 / 30 | 32 / 31 |
| Uncached input tokens | 46,993 | 36,475 |
| Cache-write input tokens | 60,963 | 53,216 |
| Cache-read input tokens | 1,943,462 | 1,897,521 |
| Output tokens | 21,463 | 24,190 |
| **Total** | **2,072,881** | **2,011,402** |

Both runs cost almost the same. NEW used about 3% more tokens in total (more uncached input) but about 11% fewer output tokens, and finished 8 s faster. Cost and time are not where the two versions differ. The difference is in the quality of the result and in how much the agent had to work around the rules.

## Outcome

| | NEW | OLD |
|---|---|---|
| Styling | Tailwind utilities on existing `@theme` tokens. `globals.css` is unchanged. | CSS Modules on `var(--token)`. The agent rebuilt about 136 lines of tokens in `globals.css` from an older commit (`e018b5d`) and added new ones. |
| UI components | 5 shadcn components (button, input, label, card, alert) hand-adapted to the tokens. Adds Radix label/slot and `class-variance-authority`. | 5 "shadcn-shaped" components written from scratch, each with its own `.module.css`. |
| Extra CSS files | 0 | 6 `.module.css` files |
| Unit tests | 171/171 (+4: render of the login form HTML) | 170/170 (+6: extracted `login-state.ts`) |
| lint / typecheck / build | pass | pass |
| `/login` smoke test | 200 | 200 |
| E2E | not run (needs Docker + DB) | not run (needs Docker + DB) |

## Issues found

### Specific to OLD (ea6c63a). The newer commits fix these.

1. **The constitution contradicts the expected stack.** It says "No Tailwind, no PostCSS", but the prompt (and the current direction) is Tailwind + shadcn. The agent followed the constitution, so it had to fake shadcn without Tailwind.
2. **No design system to build on.** `globals.css` was empty, so the agent invented the visual language by copying tokens from git history. That broke "no file describes what the code used to do" in spirit, and its output is effectively a new design system.
3. **The leftover token-file comment was inconsistent with the file.** It said "no selectors beyond `:root`", but the previous file had base element selectors.
4. **A CSS file per component** (6 `.module.css`). Current rules forbid this ("No CSS anywhere else").

### Present in both versions. Still open on `main`.

1. **The shadcn CLI output breaks house rules (seen in NEW).** It imported `cn` from a non-existent package, pulled a meta-package that changed about 2,300 lockfile lines, and generated `dark:` classes and arbitrary values. The agent had to hand-write all components. `install-design-system` / the constitution should say how to add shadcn components (CLI flags, or "copy and adapt by hand").
2. **Lint message is misleading for shadcn's `import * as React` style (NEW).** The rule's error text doesn't explain what to do instead.
3. **Dangling references.**
   - `eslint.config.mjs` cites `CONSTITUTION.md § 2` and the e2e tests cite `§ 6`, but the constitution has no numbered sections.
   - `docs/agents/methodology.md` and `domain.md` point to `CLAUDE.md`, `PRODUCT.md`, `ROADMAP.md`, `CONTEXT.md` and `docs/adr/`, and none of them exist.
4. **The vertical-slice rule doesn't fit the frontend.** "`interfaces` → `modules` → `infrastructure`, one slice under `modules`" describes the backend. The frontend uses `app/ lib/ services/ components/`, so each agent picked its own placement.
5. **The pre-commit hook needs undocumented setup.** It runs the whole monorepo (backend included). The first commit fails with `Failed to spawn: ruff` because ruff/mypy/pytest are in the backend's optional `dev` extra. You need `uv sync --extra dev` in `apps/backend`, and nothing documents it.
6. **gitleaks is not installed**, so the hook silently skips the secret scan (it only warns).
7. **Unit tests can't render components.** Vitest runs in `node` with no jsdom or Testing Library. OLD extracted pure logic to have something to test. NEW asserted on rendered HTML strings.
8. **No formatter** (no Prettier). JSX was re-indented by hand.
9. **`next start` warns that it doesn't work with `output: standalone`.** It works for smoke tests, but the warning is noise.
10. The login route already existed with all of its logic and no styling, so "create a login page" really meant "style it". This is fine, but worth knowing when reading the results.

## Conclusion

The latest version is clearly better. With tokens and Tailwind/shadcn in place, the agent reused what existed: no new CSS files, no new tokens, and a smaller diff. OLD finished in the same time and for the same tokens, but it had to resolve a rule contradiction and rebuild a design system, and it produced code that current rules forbid.

Remaining work, in order of payoff:

1. Document how to add shadcn components without the CLI's `dark:`/arbitrary output.
2. Document `uv sync --extra dev` (or make the hook install it).
3. Fix the `§ n` references and the missing-doc pointers.
4. State the frontend's slice layout.
5. Add jsdom + Testing Library and a formatter.
