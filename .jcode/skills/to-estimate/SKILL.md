---
name: to-estimate
description: Turn a client's vibe-coded app or a feature list into a sized roadmap with ticket names, a build count for the schedule and a value count for the price.
disable-model-invocation: true
---

# To Estimate

Size a client project before any spec exists. The input is either a **vibe-coded app** (client code built with AI,
read as the business requirements) or a **feature list**. The output is a roadmap of outcome lines, with ticket names
under each, and two numbers:

- **Build tickets**: what Merlin implements. Build tickets ÷ the team's tickets per day gives the schedule.
- **Value tickets**: the build tickets plus the boilerplate capabilities the project uses, counted as if built from
  scratch. They set the price. They never set the schedule, because that code already exists.

Stop at ticket names. Specs and ticket bodies are written just in time, when each roadmap line is grilled.

[shared-rules.md](shared-rules.md) holds the categories, the used? flag and the sizing rule. Every agent and the merge
apply it, so read it before step 2. A finished run, for reference:
`docs/research/vdp-crm/`.

## Process

### 1. Intake

Name the branch: **app**, **list**, or both. For both (an app plus extra wishes), run the app branch and add the
wishes as list items.

- **App:** find:
  - how it runs (README, manifest, launch config);
  - every environment variable it reads;
  - every external service it calls;
  - its data store, with row counts per table;
  - its modules and screens.

  Run `git ls-files` looking for databases, uploads, session files and `.env`. Committed personal data or secrets go
  into your first message to the user, with their paths. Rewriting git history is the user's call.
- **List:** read it whole. Write each feature as one line, marked **clear** (you can name its tickets) or **unclear**
  (it needs a deep dive with the client).

Find the boilerplate. It is this repo, if the repo was created from the template (it has `apps/backend`,
`apps/frontend` and `infra/`). Otherwise, clone `merlin-ai-labs/merlin-delivery-boilerplate` read-only into the
scratchpad. Note its commit.

**Done when** you can name about five areas to split the work into, by module or screen group. For an app, you can
also name every env var, every external service, the row counts, and what personal data the repo carries.

### 2. Agree the frame

Send the user one message, then wait for the answer. It covers:
- **The areas:** one agent per area, one agent for recommended features, and one for the boilerplate value.
- **The rules:** the categories and the sizing rule, one line each.
- **For an app:** ask to run a disposable copy with the client's keys removed, and to sign in to it as a throwaway
  admin created inside the copy.

**Done when** the user has confirmed the areas. For an app, they have also agreed to the copy and the sign-in.

### 3. Start the disposable copy (app only)

- Copy the app into the scratchpad, leaving out `.env`, session files and installed dependencies. Install from the
  lockfile.
- Create the test admin inside the copy with the app's own setup or seed script, or with a direct insert. Keep its
  credentials in a mode-600 file in the scratchpad, out of the chat.
- Add a launch entry for the copy and start it with the preview tool. Sign in once in the built-in browser. Every
  agent tab shares that session.
- Compare the client's original `.env` with `.env.example` key by key, printing no values. A real key means that
  integration probably works for the client, even though it can't run in the copy.

**Done when** the copy answers on localhost signed in as the test admin, none of the client's keys are in it, and the
original folder is untouched.

### 4. Fan out

Launch every agent in one message, in the background:
- **One per area,** from [area-brief.md](area-brief.md). Fill in the area's screens, routes, code ranges and tables,
  and which areas the other agents own.
- **One for recommended features,** from [recommended-brief.md](recommended-brief.md).
- **One for the boilerplate value,** from [boilerplate-brief.md](boilerplate-brief.md). An existing
  `boilerplate-from-scratch.md` for the same boilerplate commit is a cache: pass its path, and the agent redoes only
  the "needed by" column. The VDP run counted commit `7e970dd`:
  `docs/research/vdp-crm/inventory/boilerplate-from-scratch.md`.

Each agent writes `<scratchpad>/inventory/<area>.md`. As each report lands, relay it to the user in two lines.

**Done when** every agent has returned and every file has all its sections.

### 5. Verify and merge

Read every report whole. Then check these claims yourself, with one direct command each:
- every claim that adds or removes tickets;
- every security claim;
- every claim that contradicts the user.

Then merge the reports into one roadmap:

- **One ticket per behaviour.** A behaviour that two reports both name becomes one ticket, kept in the area that owns
  its data. The usual duplicates:
  - notifications a portal shows for a module;
  - access control, which every module names;
  - reminder emails;
  - migration tickets, named both by the area agents and by the recommended agent;
  - user onboarding.
- **Recategorise on evidence.**
  - A visible control that fails only because the copy lacks the client's real key is **working**, marked "not
    exercised".
  - A recommended item that repeats a working ticket merges into it.
  - A "the boilerplate covers it" claim that the boilerplate report's gap list contradicts becomes work inside the
    ticket that needs it, or one more ticket.
- **Folded, never lost.** A small dead feature that fits an existing ticket is listed as folded, next to that
  ticket's name.

**Done when** every ticket in every report appears in the merge exactly once, or is listed as merged or folded with
where it went.

### 6. Write the estimate

Scan every report for personal data before it enters the repo: emails, phone numbers, and every real name in the
app's user table. Then write `docs/research/<client>/estimate.md` from
[estimate-template.md](estimate-template.md), and copy the reports into `docs/research/<client>/inventory/`.

Report in chat:
- both numbers, with their days;
- the three findings that change the client conversation: usage, security, and boilerplate gaps;
- one question: does the ticket size match the size your tickets-per-day figure was measured on?

**Done when** both are written, the scan is clean, and the summary is sent.

### 7. Clean up (app only)

Ask the user, then:
- stop the copy;
- delete it from the scratchpad, because it holds client data;
- remove its launch entry.

**Done when** all three are gone, or the user chose to keep them.
