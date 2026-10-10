// Generic Azure Container Apps managed environment.
// Container apps are deployed separately so one environment can host multiple apps.

param name string
param location string = resourceGroup().location
param tags object = {}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {}
}

output id string = environment.id
