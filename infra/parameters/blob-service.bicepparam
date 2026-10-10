using '../blob-service.bicep'

var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

// Deliberately without a default: an unset origin would compile to a rule allowing nothing, and
// deploying that deletes every CORS rule on the blob service. CD resolves the real origin before it
// compiles this file, so an unset variable is a bug that must fail the compile rather than ship.
var blobCorsAllowedOrigin = readEnvironmentVariable('BLOB_CORS_ALLOWED_ORIGIN')

// Must match infra/parameters/storage-account.bicepparam; deploy-blob-service compares them.
param accountName = 'st${replace(resourceNameStem, '-', '')}'

// Exactly what the browser's direct PUT sends: the SAS carries the authorization, so no auth
// header is listed, and Azure answers the preflight itself once a rule matches.
param corsRules = [
  {
    allowedOrigins: [blobCorsAllowedOrigin]
    allowedMethods: ['PUT']
    allowedHeaders: ['content-type', 'x-ms-blob-type']
    exposedHeaders: []
    maxAgeInSeconds: 3600
  }
]
param versioningEnabled = true
param softDeleteRetentionDays = 7
