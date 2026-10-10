using '../uptime-monitor.bicep'

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

param name = resourceNameStem
param location = readEnvironmentVariable('AZURE_LOCATION')
param tags = {
  application: repository
  environment: 'production'
  managedBy: 'bicep'
}
// The frontend origin is only known once the Container Apps environment exists; CD resolves it.
param probeUrl = '${readEnvironmentVariable('UPTIME_PROBE_ORIGIN', 'https://example.invalid')}/health/ready'
param alertEmail = readEnvironmentVariable('AZURE_BUDGET_ALERT_EMAIL')
param frequencySeconds = 300
param retentionInDays = 90
