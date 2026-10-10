using '../ai-foundry.bicep'

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

// The account name is also the global DNS label behind the data-plane endpoint the Agents
// workflow calls, which is why both parameters are set to the same value here.
param name = 'aif-${resourceNameStem}'
param customSubDomainName = 'aif-${resourceNameStem}'

// GlobalStandard capacity for a given model is not offered in every region, so this location may
// legitimately differ from the other resources' once a client region lacks the model.
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
param skuName = 'S0'
param allowProjectManagement = true
param disableLocalAuth = true
param dynamicThrottlingEnabled = false
param restrictOutboundNetworkAccess = false
param publicNetworkAccess = 'Enabled'
param deploymentPrincipalId = readEnvironmentVariable('AZURE_PRINCIPAL_OBJECT_ID')
param deploymentRoleDefinitionIds = [
  'eadc314b-1a2d-4efa-be10-5d325db5065e' // Foundry Project Manager: deploy models, publish agent versions
  '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Foundry User: call the published agent's endpoint
]
param projectName = 'proj-${resourceNameStem}'
param projectDisplayName = 'proj-${resourceNameStem}'
param projectDescription = 'Hosts the prompt agents published by this repository.'

// capacity is thousands of tokens per minute and is the quota-consuming knob. capacity and
// model.version are mutable in place; model.name and sku.name are not, so switching model means a
// new descriptor with a new name.
param modelDeployments = [
  {
    name: 'gpt-5-nano'
    model: {
      format: 'OpenAI'
      name: 'gpt-5-nano'
      version: '2025-08-07'
    }
    sku: {
      name: 'GlobalStandard'
      capacity: 50
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
]
