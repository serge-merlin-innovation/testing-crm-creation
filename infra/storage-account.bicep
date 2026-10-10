// Generic, reusable Azure Storage account module.
// All account-specific values are passed in as parameters by the caller.

param name string
param location string = resourceGroup().location
param tags object = {}

// ---------- Redundancy and tier ----------

@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
  'Standard_RAGRS'
  'Standard_GZRS'
  'Standard_RAGZRS'
  'Premium_LRS'
  'Premium_ZRS'
])
param skuName string = 'Standard_LRS'

@allowed([
  'Hot'
  'Cool'
  'Cold'
])
param accessTier string = 'Hot'

// ---------- Network ----------

@allowed([
  'TLS1_2'
  'TLS1_3'
])
param minimumTlsVersion string = 'TLS1_2'

@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

@allowed([
  'AzureServices'
  'Logging'
  'Metrics'
  'None'
])
param networkAclsBypass string = 'AzureServices'

@allowed([
  'Allow'
  'Deny'
])
param networkAclsDefaultAction string = 'Allow'

param ipRules array = []
param virtualNetworkRules array = []

// ---------- Resource ----------

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: 'StorageV2'
  properties: {
    accessTier: accessTier
    // Not parameters: a shared key bypasses Entra RBAC entirely, and public blob access
    // bypasses it too. Both off is what makes a user-delegation SAS the only way to hand
    // out blob access, which the direct browser upload flow depends on.
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: minimumTlsVersion
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      bypass: networkAclsBypass
      defaultAction: networkAclsDefaultAction
      ipRules: ipRules
      virtualNetworkRules: virtualNetworkRules
    }
  }
}

output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
