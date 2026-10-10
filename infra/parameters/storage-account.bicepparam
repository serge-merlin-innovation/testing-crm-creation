using '../storage-account.bicep'

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

// A storage account name accepts only lowercase letters and digits. blob-container.bicepparam and
// blob-service.bicepparam repeat this expression and must change with it; deploy-blob-container and
// deploy-blob-service compare against this file at deploy time. The stem is at most 20 characters,
// keeping this inside the 24-character limit.
var storageAccountName = 'st${replace(resourceNameStem, '-', '')}'

param name = storageAccountName
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
param skuName = 'Standard_LRS'
param accessTier = 'Hot'
param minimumTlsVersion = 'TLS1_2'
param publicNetworkAccess = 'Enabled'
param networkAclsBypass = 'AzureServices'
param networkAclsDefaultAction = 'Allow'
param ipRules = []
param virtualNetworkRules = []
