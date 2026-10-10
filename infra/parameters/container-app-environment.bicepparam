using '../container-app-environment.bicep'

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

param name = 'cae-${resourceNameStem}'
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
