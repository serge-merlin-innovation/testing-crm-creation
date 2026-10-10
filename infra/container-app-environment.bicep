// Generic Azure Container Apps managed environment.
// Container apps are deployed separately so one environment can host multiple apps.

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

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {}
}

output id string = environment.id
