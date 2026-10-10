using '../ressource-group.bicep'

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

param name = 'rg-${resourceNameStem}'
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
