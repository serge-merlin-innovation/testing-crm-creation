# Connect GitHub to Azure

GitHub Actions signs in to Azure through OIDC: a federated credential on an Entra app, with no
stored secret.

## Discover before asking

Read: the repository (`gh repo view`), the active tenant and subscription (`az account show`), Entra
apps named after the repository and their federated credentials, the service principal's role
assignments, and the names of the repository's Actions variables and secrets.

## Ask, in one batch, what is still open

1. **The subscription**: confirm the one `az account show` reports.
2. **Custom HTTPS origins**, `FRONTEND_BACKEND_URL` and `BACKEND_FRONTEND_BASE_URL`, only as an
   intentional override. By default CD derives Azure's origins once Infra has created the Container
   Apps environment.
3. **Reuse or create the Entra app**, when discovery finds a near match.
4. **The role scope.** Infra names the resource group `rg-<repository name>`.
   - It exists: grant at that resource group, and the first Infra run sets `deploy_resource_group`
     to false.
   - Infra will create it: grant at the subscription. That is a wider blast radius, so say so and
     get an explicit yes.

## Create the trust

Three IDs, kept apart: the app's client ID, the app's object ID, and the service principal's object
ID, which is `AZURE_PRINCIPAL_OBJECT_ID`.

One federated credential on the app: issuer `https://token.actions.githubusercontent.com`, audience
`api://AzureADTokenExchange`, subject `repo:<owner>/<repository>:ref:refs/heads/main`. An existing
credential with the same three values is success; a conflicting one is reported and left as it is.
If the tenant won't let this user register the app, the app joins the admin's issue below.

## Set the variables

The workflows are the list. Set every name this prints, with `gh variable set`:

```bash
grep -ohE "vars\.[A-Z_]+" .github/workflows/*.yml | sed 's/vars\.//' | sort -u
```

The four IDs go to `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and
`AZURE_PRINCIPAL_OBJECT_ID`; the answers from `/setup` step 3 go to `AZURE_LOCATION` and
`AZURE_BUDGET_ALERT_EMAIL`. The two origin variables carry an HTTPS URL when an override was agreed,
and stay unset otherwise. A name none of this covers is new in the workflows: ask what it takes.

**Done when** every printed name is set, or is an origin override nobody asked for.

## Hand the roles to the admin

The workflows cannot grant their own first permissions. An admin who can write role assignments at
the chosen scope grants the service principal two roles, once:

- `Contributor`, to deploy the resources.
- `Role Based Access Control Administrator`, because the templates assign roles to that same
  principal: `Key Vault Secrets Officer` on the vault, `Foundry Project Manager` and `Foundry User`
  on the Foundry account. Without it Infra fails and the Agents workflow cannot publish.

Check with inherited roles included:
`az role assignment list --assignee <sp-object-id> --scope <scope> --include-inherited`. Both in
place: done. Otherwise open one issue, unless one is already open — title
`Grant Azure roles to <repository>'s deployment identity`, label `ready-for-human`, assigned to the
admin — whose body says why in one line, then gives the command to run from a clone:
`bash scripts/grant-azure-roles.sh <sp-object-id> <scope>`.

On a resume, check again, and close the issue with a comment once both roles are in place. The
admin's grant is the one source of these two roles.

## Hand the secrets to the user

The workflows' secrets seed Key Vault on the first Infra run. The user types them into
`bash scripts/set-github-secrets.sh` in their own terminal, so this conversation only ever sees
their names.

**Done when** the variables match the workflows, the admin's issue is open or closed as verified,
and every `secrets.*` name the workflows read, bar `GITHUB_TOKEN`, is in `gh secret list` or is
reported pending.
