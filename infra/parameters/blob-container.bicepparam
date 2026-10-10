using '../blob-container.bicep'

var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

// Must match infra/parameters/storage-account.bicepparam; deploy-blob-container compares them.
param accountName = 'st${replace(resourceNameStem, '-', '')}'
param name = 'documents'
