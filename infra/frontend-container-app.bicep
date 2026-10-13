// Frontend Azure Container App backed by a private container registry.
// Runtime settings are supplied by frontend-container-app.bicepparam.

param name string
// NFR-01: client data and its backups stay in EU data centres. Same list in every template.
@allowed([
  'westeurope'
  'northeurope'
  'francecentral'
  'germanywestcentral'
  'swedencentral'
])
param location string = any(resourceGroup().location)
param tags object = {}

param environmentId string

param containerName string
param containerImage string
param environmentVariables array = []

// Keep the secure slots aligned with the backend contract so the shared deployment
// action can validate either application consistently. The frontend currently uses none.
@maxLength(2)
param secretEnvironmentVariables array = []

@secure()
param secretEnvironmentVariableValue1 string = ''

@secure()
param secretEnvironmentVariableValue2 string = ''

param registryServer string

param registryUsername string

@secure()
param registryPassword string

@minValue(1)
@maxValue(65535)
param targetPort int

param externalIngress bool = true
// NFR-01: HTTPS only. The managed ingress terminates TLS 1.2+.
@allowed([
  false
])
param allowInsecure bool = false

@allowed([
  'auto'
  'http'
  'http2'
  'tcp'
])
param transport string = 'auto'

param cpu string = '0.5'

param memory string = '1Gi'

@minValue(0)
param minReplicas int = 1

@minValue(1)
param maxReplicas int = 1

var registryPasswordSecretName = 'registry-password'
var secretEnvironmentVariableValues = [
  secretEnvironmentVariableValue1
  secretEnvironmentVariableValue2
]
var containerAppSecrets = [for (secretEnvironmentVariable, index) in secretEnvironmentVariables: {
  name: secretEnvironmentVariable.secretName
  value: secretEnvironmentVariableValues[index]
}]
var containerSecretEnvironmentVariables = [for secretEnvironmentVariable in secretEnvironmentVariables: {
  name: secretEnvironmentVariable.name
  secretRef: secretEnvironmentVariable.secretName
}]

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: targetPort
        transport: transport
        allowInsecure: allowInsecure
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: registryServer
          username: registryUsername
          passwordSecretRef: registryPasswordSecretName
        }
      ]
      secrets: concat(
        [
          {
            name: registryPasswordSecretName
            value: registryPassword
          }
        ],
        containerAppSecrets
      )
    }
    template: {
      containers: [
        {
          name: containerName
          image: containerImage
          env: concat(
            environmentVariables,
            containerSecretEnvironmentVariables
          )
          resources: {
            cpu: json(cpu)
            memory: memory
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}
