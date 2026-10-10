// Generic, reusable resource group module.
// Deployed at subscription scope by the caller.

targetScope = 'subscription'

param name string
// NFR-01: client data and its backups stay in EU data centres. Same list in every template.
@allowed([
  'westeurope'
  'northeurope'
  'francecentral'
  'germanywestcentral'
  'swedencentral'
])
param location string
param tags object = {}

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: name
  location: location
  tags: tags
}
