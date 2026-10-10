// Generic, reusable blob container on an existing storage account.
// The account is referenced by name and must already exist in this resource group.

param accountName string
param name string

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: accountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2024-01-01' existing = {
  parent: storageAccount
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: name
  properties: {
    // The account sets allowBlobPublicAccess: false, so anything but 'None' fails to deploy.
    publicAccess: 'None'
  }
}
