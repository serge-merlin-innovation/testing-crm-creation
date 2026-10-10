using '../keyvault.bicep'

var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

param name = 'kv-${resourceNameStem}'
param location = readEnvironmentVariable('AZURE_LOCATION')
param tenantId = readEnvironmentVariable('AZURE_TENANT_ID')
param skuFamily = 'A'
param skuName = 'standard'
param networkAclsBypass = 'AzureServices'
param networkAclsDefaultAction = 'Allow'
param ipRules = []
param virtualNetworkRules = []
param publicNetworkAccess = 'Enabled'
param enableRbacAuthorization = true
param accessPolicies = []
param enabledForDeployment = false
param enabledForDiskEncryption = false
param enabledForTemplateDeployment = true
param deploymentPrincipalId = readEnvironmentVariable('AZURE_PRINCIPAL_OBJECT_ID')
param enableSoftDelete = true
param softDeleteRetentionInDays = 90
