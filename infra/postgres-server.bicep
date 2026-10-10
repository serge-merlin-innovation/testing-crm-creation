// Generic, reusable Azure Database for PostgreSQL flexible server module.
// All server-specific values are passed in as parameters by the caller.

param name string
param location string = resourceGroup().location
param tags object = {}

param version string = '18'

// ---------- Compute ----------

param skuName string = 'Standard_B1ms'

@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param skuTier string = 'Burstable'

// ---------- Storage ----------

@allowed([
  32
  64
  128
  256
  512
  1024
  2048
  4096
  8192
  16384
  32767
])
param storageSizeGB int = 32

@allowed([
  'Enabled'
  'Disabled'
])
param storageAutoGrow string = 'Enabled'

// ---------- Backup ----------

@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

@allowed([
  'Enabled'
  'Disabled'
])
param geoRedundantBackup string = 'Disabled'

// ---------- Availability ----------

@allowed([
  'Disabled'
  'SameZone'
  'ZoneRedundant'
])
param highAvailabilityMode string = 'Disabled'

// Empty string lets Azure pick the zone.
param availabilityZone string = ''
param standbyAvailabilityZone string = ''

// ---------- Authentication ----------

param passwordAuthEnabled bool = true
param administratorLogin string = ''

@secure()
param administratorLoginPassword string = ''

param entraAuthEnabled bool = false
param entraTenantId string = subscription().tenantId

// ---------- Network ----------

@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

// Setting a delegated subnet switches the server to VNet integration and
// makes publicNetworkAccess inapplicable.
param delegatedSubnetResourceId string = ''
param privateDnsZoneResourceId string = ''

// [{ name: string, startIpAddress: string, endIpAddress: string }]
param firewallRules array = []

// ---------- Maintenance window ----------

@allowed([
  'Enabled'
  'Disabled'
])
param customMaintenanceWindow string = 'Disabled'

@minValue(0)
@maxValue(6)
param maintenanceDayOfWeek int = 0

@minValue(0)
@maxValue(23)
param maintenanceStartHour int = 0

@minValue(0)
@maxValue(59)
param maintenanceStartMinute int = 0

// ---------- Server configuration ----------

// [{ name: string, value: string, source: string? }]
param serverConfigurations array = []

// ---------- Resource ----------

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    administratorLogin: empty(administratorLogin) ? null : administratorLogin
    administratorLoginPassword: empty(administratorLoginPassword) ? null : administratorLoginPassword
    authConfig: {
      passwordAuth: passwordAuthEnabled ? 'Enabled' : 'Disabled'
      activeDirectoryAuth: entraAuthEnabled ? 'Enabled' : 'Disabled'
      tenantId: entraAuthEnabled ? entraTenantId : null
    }
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: storageAutoGrow
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: geoRedundantBackup
    }
    highAvailability: {
      mode: highAvailabilityMode
      standbyAvailabilityZone: highAvailabilityMode == 'ZoneRedundant' ? standbyAvailabilityZone : null
    }
    availabilityZone: availabilityZone
    network: empty(delegatedSubnetResourceId)
      ? {
          publicNetworkAccess: publicNetworkAccess
        }
      : {
          delegatedSubnetResourceId: delegatedSubnetResourceId
          privateDnsZoneArmResourceId: privateDnsZoneResourceId
        }
    maintenanceWindow: {
      customWindow: customMaintenanceWindow
      dayOfWeek: maintenanceDayOfWeek
      startHour: maintenanceStartHour
      startMinute: maintenanceStartMinute
    }
  }
}

// Flexible server rejects concurrent control-plane changes, so children are
// deployed one at a time and configurations wait for the firewall rules.

@batchSize(1)
resource firewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = [
  for rule in firewallRules: {
    parent: postgres
    name: rule.name
    properties: {
      startIpAddress: rule.startIpAddress
      endIpAddress: rule.endIpAddress
    }
  }
]

@batchSize(1)
resource serverConfiguration 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = [
  for config in serverConfigurations: {
    parent: postgres
    name: config.name
    properties: {
      value: config.value
      source: config.?source ?? 'user-override'
    }
    dependsOn: [
      firewallRule
    ]
  }
]

output fullyQualifiedDomainName string = postgres.properties.fullyQualifiedDomainName
