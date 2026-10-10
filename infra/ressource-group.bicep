// Generic, reusable resource group module.
// Deployed at subscription scope by the caller.

targetScope = 'subscription'

param name string
param location string
param tags object = {}

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: name
  location: location
  tags: tags
}
