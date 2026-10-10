// Uptime monitoring for NFR-03 (99.5% between 8:00 and 20:00 CET).
// A standard availability test probes the frontend's readiness URL every 5 minutes from EU
// locations; an alert mails the operators when availability drops. The monthly business-hours
// figure is computed from these results (see docs/operations/availability.md).

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

@description('Public URL the probe calls, for example https://crm.example.be/health/ready')
param probeUrl string

@minLength(3)
param alertEmail string

@allowed([
  300
  600
  900
])
param frequencySeconds int = 300

@minValue(30)
@maxValue(730)
param retentionInDays int = 90

// EU probe locations only, so monitoring traffic and results stay in the EU.
var probeLocations = [
  'emea-nl-ams-azr'
  'emea-fr-pra-edge'
  'emea-gb-db3-azr'
  'emea-se-sto-edge'
  'emea-ch-zrh-edge'
]

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${name}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${name}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource probe 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'webtest-${name}'
  location: location
  // Azure links a web test to its component through this hidden tag.
  tags: union(tags, {
    'hidden-link:${insights.id}': 'Resource'
  })
  kind: 'standard'
  properties: {
    SyntheticMonitorId: 'webtest-${name}'
    Name: 'CRM readiness'
    Enabled: true
    Frequency: frequencySeconds
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [for location in probeLocations: {
      Id: location
    }]
    Request: {
      RequestUrl: probeUrl
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 14
    }
  }
}

resource operators 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${name}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'crm-uptime'
    enabled: true
    emailReceivers: [
      {
        name: 'operators'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource downAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${name}-down'
  location: 'global'
  tags: tags
  properties: {
    description: 'The CRM failed its readiness probe from at least 2 EU locations.'
    severity: 1
    enabled: true
    scopes: [
      probe.id
      insights.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: probe.id
      componentId: insights.id
      failedLocationCount: 2
    }
    actions: [
      {
        actionGroupId: operators.id
      }
    ]
  }
}

resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${name}-availability'
  location: 'global'
  tags: tags
  properties: {
    description: 'Hourly availability fell below the 99.5% target.'
    severity: 2
    enabled: true
    scopes: [
      insights.id
    ]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'availability'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.Insights/components'
          metricName: 'availabilityResults/availabilityPercentage'
          operator: 'LessThan'
          threshold: json('99.5')
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [
      {
        actionGroupId: operators.id
      }
    ]
  }
}

output applicationInsightsId string = insights.id
