# The constitution: the standing rules

*Merlin's standards, near-identical in every project forked from this boilerplate. Every change obeys them without restating them.*

---

- No comment, branch or file describes what the code used to do. Git holds the history.

- Default to none. Add one only where a future edit would otherwise silently break a constraint that is not visible from the code itself.

- Research, analysis and investigation results live in `docs/research/<topic>.md`.

- Dependencies point one way: `interfaces` → `modules` → `infrastructure`. Each feature is one vertical slice under `modules`.

- **The UI is shadcn/ui and nothing else.** Every file in `apps/frontend/src/components/ui/` comes from the official shadcn registry through the CLI (`pnpm dlx shadcn@latest add <name>` in `apps/frontend`) and is never edited by hand. No third-party registry, no hand-written primitive. Feature components only compose those primitives, choosing their look through each primitive's `variant` and `size` props, never by rendering raw styled HTML where a primitive exists. `src/app/globals.css` is the shadcn theme and the only CSS file in the app: change the look by changing its CSS variables, never by changing a component. Outside `components/ui/`, Tailwind classes only lay out and space the primitives, using theme tokens: no other `.css` or `.module.css` file, no `style` attribute, no arbitrary values like `p-[13px]` or `bg-[#111]`. The only UI and styling dependencies are what the shadcn CLI installs (`radix-ui`, `class-variance-authority`, `cn`, `lucide-react`, `tw-animate-css`, `shadcn`) and Tailwind. Logos and other images are static files in `public/`, rendered with `next/image`, never components.

- **Every change goes through a pull request, and merging is a human act.** No direct pushes to `main`; the ruleset has no bypass actors. Squash is the only merge method.

- **Nothing goes live without the user's say-so.** An agent never deploys, pushes an image, publishes documentation, rotates a secret or writes cloud state unless the user authorized that action. A real deployment is never the first syntax test.

- **Every Azure resource is created by changing `infra/` and letting the Infra workflow apply it.**

- **Every session that touches code ends with a postmortem.** When you implemented, tested, verified or otherwise changed code, run the `retro-auto` skill before your final response. Workers do it too, before their completion report.
