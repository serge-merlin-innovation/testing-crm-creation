using '../frontend-container-app.bicep'

var subscriptionId = readEnvironmentVariable('AZURE_SUBSCRIPTION_ID')
var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')
var resourceGroupName = 'rg-${resourceNameStem}'
var environmentName = 'cae-${resourceNameStem}'
var keyVaultName = 'kv-${resourceNameStem}'
var containerRegistryPasswordSecretName = 'ghcr-token'

param name = 'ca-${resourceNameStem}-frontend'
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
param environmentId = '/subscriptions/${subscriptionId}/resourceGroups/${resourceGroupName}/providers/Microsoft.App/managedEnvironments/${environmentName}'
param containerName = 'frontend'
// Compile-time default for the frontend resource contract. CD always overrides this parameter
// with the immutable release version produced by CI.
param containerImage = 'ghcr.io/${repository}/frontend:main'
param environmentVariables = [
  {
    name: 'BACKEND_URL'
    // CD resolves Azure's internal backend origin after Infra creates the environment.
    value: readEnvironmentVariable('FRONTEND_BACKEND_URL', '')
  }
  {
    name: 'BFF_TRUSTED_PROXY_HOPS'
    value: '1'
  }
  {
    name: 'BACKEND_TIMEOUT_MS'
    value: '30000'
  }
]
param secretEnvironmentVariables = []
param registryServer = 'ghcr.io'
param registryUsername = toLower(readEnvironmentVariable('GITHUB_REPOSITORY_OWNER'))
param registryPassword = az.getSecret(
  subscriptionId,
  resourceGroupName,
  keyVaultName,
  containerRegistryPasswordSecretName
)
param targetPort = 3000
param externalIngress = true
param allowInsecure = false
param transport = 'auto'
param cpu = '0.25'
param memory = '0.5Gi'
param minReplicas = 0
param maxReplicas = 1
