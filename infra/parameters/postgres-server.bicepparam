using '../postgres-server.bicep'

var subscriptionId = readEnvironmentVariable('AZURE_SUBSCRIPTION_ID')
var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')
var resourceGroupName = 'rg-${resourceNameStem}'
var keyVaultName = 'kv-${resourceNameStem}'
var administratorPasswordSecretName = 'postgres-administrator-password'
var postgresAdministratorLogin = '${replace(resourceNameStem, '-', '')}admin'

param name = 'psql-${resourceNameStem}'
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
param version = '18'
param skuName = 'Standard_B1ms'
param skuTier = 'Burstable'
param storageSizeGB = 32
param storageAutoGrow = 'Enabled'
param backupRetentionDays = 35
param geoRedundantBackup = 'Disabled'
param highAvailabilityMode = 'Disabled'
param availabilityZone = ''
param standbyAvailabilityZone = ''
param passwordAuthEnabled = true
param administratorLogin = postgresAdministratorLogin
param administratorLoginPassword = az.getSecret(
  subscriptionId,
  resourceGroupName,
  keyVaultName,
  administratorPasswordSecretName
)
param entraAuthEnabled = false
param entraTenantId = readEnvironmentVariable('AZURE_TENANT_ID')
param publicNetworkAccess = 'Enabled'
param delegatedSubnetResourceId = ''
param privateDnsZoneResourceId = ''
param firewallRules = []
param customMaintenanceWindow = 'Disabled'
param maintenanceDayOfWeek = 0
param maintenanceStartHour = 0
param maintenanceStartMinute = 0
// The conflict check (AUTHZ-05) runs fuzzy name matching; the backend migration creates both extensions.
param serverConfigurations = [
  { name: 'azure.extensions', value: 'PG_TRGM,UNACCENT' }
]
