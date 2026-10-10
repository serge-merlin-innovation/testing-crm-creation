# Estimate template

The skeleton of `docs/research/<client>/estimate.md`. Sections marked (app) are dropped for a feature list.

<estimate-template>

# <Client>: estimate

*Source: <app path and commit | the feature list and its date>, analysed on <date>. The evidence for every line is in
`inventory/`.*

## Totals

| Category | Tickets | What it is |
|---|---|---|
| Working features (list: requested) | n | Works today, or was asked for; we build it |
| Day-one data | n | Existing data and users moved in |
| Recommended | n | Not in the <app / list>, not in the boilerplate, needed for production |
| Project work | n | Setup, environments, cutover |
| **Tickets we build** | **n** | Sets the schedule |
| Boilerplate the project uses, counted as if built from scratch | n | Already exists, so it is never built again |
| **Tickets of value delivered** | **n** | Sets the price |
| Dead features, if the client says yes | +n | They add to both numbers |
| Deep dives before sizing | n sessions | Not sized |

<One paragraph:
- build tickets ÷ tickets per day = days;
- the days with every dead feature added;
- what comes on top: grilling, deep dives, and waits on the client side.>

## How this was built
<Three or four bullets:
- the agents per area;
- the sizing rule;
- the boilerplate counted in the value line only;
- the (unused) marker.>

## Roadmap
Every line is `not grilled`. The order is a proposal; the ranking is decided with the client.

### Working features (n)
**<Module>**
- R1 — <outcome, in one sentence>
  - <ticket name> **(unused: <evidence>)**, where it applies

### Day-one data (n)
### Recommended (n)
### Project work (n, not roadmap lines)

## Dead features: ask the client
| Dead feature | Why it's dead | Question for the client | Tickets |
|---|---|---|---|

Folded into existing tickets at no extra count: <list>

## Deep dives before sizing
<Each one, with what little the input says about it.>

## What to tell the client now (app)
<Security and data problems in their current app, each with its file:line.>

## Usage: what the data says (app)
<Where the data came from, and what was created in the app itself.>

## Assumptions and risks
<Cover these:
- ticket size not yet calibrated;
- waits on the client or third parties;
- conditional tickets;
- boilerplate gaps absorbed into existing tickets.>

## Evidence
`inventory/` holds the reports, which are the input for grilling each line later.

</estimate-template>
