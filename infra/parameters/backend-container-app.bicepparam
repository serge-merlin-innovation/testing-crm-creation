using '../backend-container-app.bicep'

var subscriptionId = readEnvironmentVariable('AZURE_SUBSCRIPTION_ID')
var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')
var resourceGroupName = 'rg-${resourceNameStem}'
var environmentName = 'cae-${resourceNameStem}'
var keyVaultName = 'kv-${resourceNameStem}'
var postgresAdministratorLogin = '${replace(resourceNameStem, '-', '')}admin'
var postgresDatabaseName = 'db-${resourceNameStem}'
var postgresAdministratorPasswordSecretName = 'postgres-administrator-password'
var backendSecretKeySecretName = 'backend-secret-key'
var containerRegistryPasswordSecretName = 'ghcr-token'

param name = 'ca-${resourceNameStem}-backend'
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
param environmentId = '/subscriptions/${subscriptionId}/resourceGroups/${resourceGroupName}/providers/Microsoft.App/managedEnvironments/${environmentName}'
param containerName = 'backend'
// Compile-time default for the backend resource contract. CD always overrides this with the
// immutable backend release version emitted by CI.
param containerImage = 'ghcr.io/${repository}/backend:main'
param environmentVariables = [
  {
    name: 'ENVIRONMENT'
    value: 'production'
  }
  {
    name: 'POSTGRES_USER'
    value: postgresAdministratorLogin
  }
  {
    name: 'POSTGRES_SERVER'
    value: 'psql-${resourceNameStem}.postgres.database.azure.com'
  }
  {
    name: 'POSTGRES_PORT'
    value: '5432'
  }
  {
    name: 'POSTGRES_DB'
    value: postgresDatabaseName
  }
  {
    name: 'POSTGRES_SYNC_PREFIX'
    value: 'postgresql://'
  }
  {
    name: 'POSTGRES_ASYNC_PREFIX'
    value: 'postgresql+asyncpg://'
  }
  {
    name: 'CREATE_TABLES_ON_STARTUP'
    value: 'false'
  }
  {
    name: 'SESSION_SECURE_COOKIES'
    value: 'true'
  }
  {
    name: 'CSRF_ENABLED'
    value: 'true'
  }
  {
    name: 'TRUSTED_PROXY_HOPS'
    value: '2'
  }
  {
    name: 'CORS_ENABLED'
    value: 'false'
  }
  {
    name: 'FRONTEND_BASE_URL'
    // CD resolves Azure's public frontend origin after Infra creates the environment.
    value: readEnvironmentVariable('BACKEND_FRONTEND_BASE_URL', '')
  }
  {
    name: 'OAUTH_REDIRECT_BASE_URL'
    value: readEnvironmentVariable('BACKEND_FRONTEND_BASE_URL', '')
  }
]
param secretEnvironmentVariables = [
  {
    name: 'POSTGRES_PASSWORD'
    secretName: 'postgres-password'
  }
  {
    name: 'SECRET_KEY'
    secretName: 'secret-key'
  }
]
param secretEnvironmentVariableValue1 = az.getSecret(
  subscriptionId,
  resourceGroupName,
  keyVaultName,
  postgresAdministratorPasswordSecretName
)
param secretEnvironmentVariableValue2 = az.getSecret(
  subscriptionId,
  resourceGroupName,
  keyVaultName,
  backendSecretKeySecretName
)
param registryServer = 'ghcr.io'
param registryUsername = toLower(readEnvironmentVariable('GITHUB_REPOSITORY_OWNER'))
param registryPassword = az.getSecret(
  subscriptionId,
  resourceGroupName,
  keyVaultName,
  containerRegistryPasswordSecretName
)
param targetPort = 8000
// The browser reaches FastAPI through the frontend relay; only apps inside the
// Container Apps environment should resolve this ingress.
param externalIngress = false
param allowInsecure = false
param transport = 'auto'
param cpu = '0.25'
param memory = '0.5Gi'
param minReplicas = 0
param maxReplicas = 1
