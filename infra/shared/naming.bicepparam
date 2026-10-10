using 'naming.bicep'

// The only copy of the resource-naming algorithm; every other parameters file reads the result
// through readEnvironmentVariable('AZURE_RESOURCE_NAME_STEM').
//
// Do not convert this into an exported function the other parameters files import. az.getSecret()
// cannot resolve imported symbols and would emit an unevaluated ARM expression where the deploy
// actions expect a literal Key Vault resource ID, breaking every cross-file check.
//
// Key Vault's 24-character name limit is what forces the truncation below.

var repository = toLower(readEnvironmentVariable('GITHUB_REPOSITORY'))
var repositoryName = last(split(repository, '/'))
var normalizedRepositoryName = replace(replace(repositoryName, '_', '-'), '.', '-')

param resourceNameStem = length(normalizedRepositoryName) <= 20
  ? normalizedRepositoryName
  : '${take(normalizedRepositoryName, 13)}-${take(uniqueString(repository), 6)}'
