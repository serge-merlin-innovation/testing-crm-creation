// Generic, reusable Azure Key Vault module.
// All vault-specific values are passed in as parameters by the caller.

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
param tenantId string = subscription().tenantId
param skuFamily string = 'A'

@allowed([
  'standard'
  'premium'
])
param skuName string = 'standard'

// ---------- Network ACLs ----------

@allowed([
  'AzureServices'
  'None'
])
param networkAclsBypass string = 'None'

@allowed([
  'Allow'
  'Deny'
])
param networkAclsDefaultAction string = 'Allow'
param ipRules array = []
param virtualNetworkRules array = []

@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

// ---------- Access ----------

param enableRbacAuthorization bool = true
param accessPolicies array = []
param enabledForDeployment bool = false
param enabledForDiskEncryption bool = false
param enabledForTemplateDeployment bool = false

// Optional deployment identity that can seed and rotate vault secrets. The
// caller needs permission to create role assignments when this is supplied.
param deploymentPrincipalId string = ''

// ---------- Soft delete / purge protection ----------

param enableSoftDelete bool = true

@minValue(7)
@maxValue(90)
param softDeleteRetentionInDays int = 90

// ---------- Resource ----------

resource keyVault 'Microsoft.KeyVault/vaults@2026-03-01-preview' = {
  name: name
  location: location
  properties: {
    sku: {
      family: skuFamily
      name: skuName
    }
    tenantId: tenantId
    networkAcls: {
      bypass: networkAclsBypass
      defaultAction: networkAclsDefaultAction
      ipRules: ipRules
      virtualNetworkRules: virtualNetworkRules
    }
    accessPolicies: enableRbacAuthorization ? [] : accessPolicies
    enabledForDeployment: enabledForDeployment
    enabledForDiskEncryption: enabledForDiskEncryption
    enabledForTemplateDeployment: enabledForTemplateDeployment
    enableSoftDelete: enableSoftDelete
    softDeleteRetentionInDays: softDeleteRetentionInDays
    enableRbacAuthorization: enableRbacAuthorization
    publicNetworkAccess: publicNetworkAccess
  }
}

var keyVaultSecretsOfficerRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
)

resource deploymentSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableRbacAuthorization && !empty(deploymentPrincipalId)) {
  name: guid(keyVault.id, deploymentPrincipalId, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    principalId: deploymentPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: keyVaultSecretsOfficerRoleId
  }
}
