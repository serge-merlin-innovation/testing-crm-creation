using '../resource-group-budget.bicep'

param name = 'monthly-cost-budget'
param amount = 5
param alertThreshold = 80
param alertEmail = readEnvironmentVariable('AZURE_BUDGET_ALERT_EMAIL')
