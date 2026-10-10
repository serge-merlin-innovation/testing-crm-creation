// Monthly cost budget scoped to the resource group receiving this deployment.

targetScope = 'resourceGroup'

@minLength(1)
param name string

@minValue(1)
param amount int

@minValue(0)
@maxValue(1000)
param alertThreshold int

@minLength(3)
param alertEmail string

// Azure requires the first day of the current budget period. A parameter default
// keeps this valid when the manual Infra workflow is rerun in a later month.
param budgetStartMonth string = utcNow('yyyy-MM-01')

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: name
  properties: {
    amount: amount
    category: 'Cost'
    notifications: {
      Actual_GreaterThanOrEqualTo_80_Percent: {
        contactEmails: [
          alertEmail
        ]
        contactGroups: []
        contactRoles: []
        enabled: true
        locale: 'en-gb'
        operator: 'GreaterThanOrEqualTo'
        threshold: alertThreshold
        thresholdType: 'Actual'
      }
    }
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '${budgetStartMonth}T00:00:00Z'
    }
  }
}
