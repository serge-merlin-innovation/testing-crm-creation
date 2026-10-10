using '../postgres-database.bicep'

var resourceNameStem = readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM')

param serverName = 'psql-${resourceNameStem}'
param name = 'db-${resourceNameStem}'
param charset = 'UTF8'
param collation = 'en_US.utf8'
