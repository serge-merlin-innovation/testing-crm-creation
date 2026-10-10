---
name: setup
description: Set up a project cloned from this boilerplate — branch rules, local stack, placeholders, labels, Azure connection, design system — ending in a pull request. Run inside the clone; re-run to finish what was pending.
disable-model-invocation: true
---

# Set up the project

Runs inside a clone of a repository made from this template. Creating that repository and cloning
it are the user's steps, before this one (README, "Start a new project"). Every step is idempotent:
it checks its own state first and skips what is done, so a re-run resumes, and every run ends with
what is still pending and who owes it. The run stops at the open pull request; deploying (Infra,
CD) is a later decision.

Read `CONSTITUTION.md` before step 1.

## 0. Check where you are

```bash
gh repo view --json templateRepository --jq '.templateRepository | "\(.owner.login)/\(.name)"'
```

It prints `merlin-ai-labs/merlin-delivery-boilerplate` in a project's clone: continue. Anything else
— `null/null` in the template itself — means this is not a project: stop and say so.

## 1. Check the repository name

`infra/shared/naming.bicepparam` builds every Azure resource name from the repository name, so once
Infra has run, a rename builds a second set of resources. The name holds when it is lowercase
letters, digits and hyphens, starts and ends with a letter or digit, and is at most 20 characters;
past 20 the names get a hash suffix. A name that breaks the rule is cheap to fix now:
`gh repo rename <new-name>` inside the clone renames it and updates `origin`.

**Done when** the name holds, or the user chose to keep it.

## 2. Lock `main`

A repository made from a template gets the files and none of the rulesets, so `main` accepts direct
pushes until this step. Copy each of the template's rulesets this repository lacks:

```bash
gh api repos/merlin-ai-labs/merlin-delivery-boilerplate/rulesets/<id> \
  --jq '{name, target, enforcement, conditions, rules, bypass_actors}' |
  gh api --method POST repos/<owner>/<repository>/rulesets --input -
```

**Done when** this repository's rulesets read back rule for rule like the template's.

## 3. Collect the inputs

Ask in one batch for whatever the repository doesn't already answer — on a re-run the variables,
`layout.tsx` and the open issue answer most of it:

- **Display name**: the product's name for people, for the page title and `APP_NAME`.
- **Azure region** for `AZURE_LOCATION`. Existing projects use `westeurope`.
- **Budget alert email** for `AZURE_BUDGET_ALERT_EMAIL`.
- **The Azure admin's GitHub handle**: a Merlin person, usually not the user, who grants the roles in
  step 7.

**Done when** every input has a value.

## 4. Build the local stack

Follow the README's Quick start, with two edits before its `cp` of the env files:

- `apps/backend/.env.example`: `APP_NAME` becomes the display name.
- `apps/backend/docker-compose.yml`: add `name: <repository name>` as its first line. Docker
  otherwise names the project after the folder, `backend`, in every clone, and all projects on the
  machine share one Postgres volume.

The local secrets keep the example's values: they stay on this machine.

**Done when** `pnpm db:up` reports healthy, the migrations and the seed have run, and
`git config core.hooksPath` prints `.husky/_`. Step 9 pushes through those hooks, with Docker
running.

## 5. Replace the placeholders

- The root `package.json` `"name"` becomes the repository name.
- `apps/frontend/src/app/layout.tsx` `title` becomes the display name.

The `@merlin/*` package names stay: the README, the hooks and `ci.yml` filter on them.

**Done when** `grep -n "merlin-delivery-boilerplate\|application name" package.json
apps/frontend/src/app/layout.tsx` prints nothing.

## 6. Create the labels

Every label `docs/agents/triage-labels.md` maps, and every `wayfinder:*` label
`docs/agents/issue-tracker.md` names, with `gh label create <name> --force`.

**Done when** `gh label list` shows all of them.

## 7. Connect GitHub to Azure

Follow [azure.md](azure.md). It ends by handing the roles to the admin and the secrets to the user.

## 8. Install the design system

Run `install-design-system`. It reads the Claude Design export committed in `docs/design-system/`;
with that folder empty, the step is pending.

## 9. Open the pull request and report

Commit the file changes of steps 4, 5 and 8 on a branch named `setup`, push, and open the pull
request; the hooks run the gates on commit and push. Stop at the open pull request: a human merges
it.

Then report every step as done or pending, and who owes each pending one — the admin (the roles),
the user (the secrets, the design-system export in `docs/design-system/`), the pull request's review.
