// Generic, reusable Microsoft Foundry module: the account, one project, and its model deployments.
// All Foundry-specific values are passed in as parameters by the caller.
//
// The three Microsoft.CognitiveServices types share one API version deliberately, the way the
// Postgres server shares 2024-08-01 with its own children. Microsoft.Authorization stays on the
// version keyvault.bicep already uses, so the repository holds one version per provider.
//
// The project and the model deployments live here rather than in their own templates because
// neither can exist without an account created in the same run, and a model deployment has no
// consumer that addresses it independently. That changes if the account ever moves out of this
// resource group or is shared across repositories: the deployments would then need the
// `existing`-plus-preflight shape that postgres-database.bicep uses.

param name string
// NFR-01: client data and its backups stay in EU data centres. Same list in every template.
@allowed([
  'westeurope'
  'northeurope'
  'francecentral'
  'germanywestcentral'
  'swedencentral'
])
param location string = any(resourceGroup().location)
param tags object = {}

@allowed([
  'S0'
])
param skuName string = 'S0'

// Becomes the global DNS label behind the Foundry data-plane endpoint. Defaulted to the account
// name rather than left empty: an account created without a custom subdomain can never have one
// added afterwards, and the PUT that tries is rejected with no in-place fix.
param customSubDomainName string = name

// Required for child projects. An account without it cannot host a project.
param allowProjectManagement bool = true

// ---------- Access ----------

param disableLocalAuth bool = true
param dynamicThrottlingEnabled bool = false
param restrictOutboundNetworkAccess bool = false

@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

// Optional deployment identity that can deploy models and publish agent versions. The caller
// needs permission to create role assignments when this is supplied.
param deploymentPrincipalId string = ''
param deploymentRoleDefinitionIds array = []

// ---------- Project ----------

@minLength(2)
@maxLength(64)
param projectName string
param projectDisplayName string
param projectDescription string = ''

// ---------- Models ----------

// Ordered descriptors shaped as
// { name: <deployment name>, model: { format, name, version }, sku: { name, capacity },
//   versionUpgradeOption: <upgrade policy> }.
// Plain objects work here because nothing in this array is a Key Vault reference.
param modelDeployments array = []

// ---------- Resource ----------

resource account 'Microsoft.CognitiveServices/accounts@2026-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: skuName
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: allowProjectManagement
    customSubDomainName: customSubDomainName
    disableLocalAuth: disableLocalAuth
    dynamicThrottlingEnabled: dynamicThrottlingEnabled
    publicNetworkAccess: publicNetworkAccess
    restrictOutboundNetworkAccess: restrictOutboundNetworkAccess
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2026-05-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  // A project carries its own managed identity, separate from the account's: the account
  // rejects project creation without one.
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectDisplayName
    description: projectDescription
  }
}

// An account rejects concurrent control-plane changes, so the loop is serialized against itself
// and against the sibling project ARM would otherwise create in parallel with it.
@batchSize(1)
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = [
  for deployment in modelDeployments: {
    parent: account
    name: deployment.name
    sku: deployment.sku
    properties: {
      model: deployment.model
      versionUpgradeOption: deployment.versionUpgradeOption
    }
    dependsOn: [
      project
    ]
  }
]

// Bicep cannot put a condition on an individual loop iteration, so an absent principal empties
// the list instead.
var principalRoleDefinitionIds = empty(deploymentPrincipalId) ? [] : deploymentRoleDefinitionIds

resource deploymentPrincipalRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleDefinitionId in principalRoleDefinitionIds: {
    name: guid(account.id, deploymentPrincipalId, roleDefinitionId)
    scope: account
    properties: {
      principalId: deploymentPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    }
  }
]
