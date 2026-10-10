// Single-owner blob service configuration on an existing storage account.
// The account is referenced by name and must already exist in this resource group.
//
// blobServices/default is a singleton that always exists on an account, so this contract configures
// it rather than creating it. Every property it can set is set here: the resource provider deletes
// every CORS rule when a request body omits them, so a second deployment that declared only some of
// these would silently clear the rest. That is why this is not a generic, reusable template.

param accountName string

// [{ allowedOrigins: string[], allowedMethods: string[], allowedHeaders: string[],
//    exposedHeaders: string[], maxAgeInSeconds: int }]
// A browser that uploads straight to a blob is blocked until its exact origin is listed here.
// Deliberately without a default: an omitted value is the one input that erases every existing rule.
param corsRules array

param versioningEnabled bool = true

@minValue(1)
@maxValue(365)
param softDeleteRetentionDays int = 7

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: accountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2024-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: corsRules
    }
    isVersioningEnabled: versioningEnabled
    deleteRetentionPolicy: {
      enabled: true
      days: softDeleteRetentionDays
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: softDeleteRetentionDays
    }
  }
}
