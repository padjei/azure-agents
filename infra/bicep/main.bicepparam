// Example parameter file for main.bicep.
// Deploy with:
//   az deployment group create -g <rg> -f main.bicep -p main.bicepparam
using './main.bicep'

param synapseWorkspaceName = 'my-synapse-workspace'
param logAnalyticsWorkspaceName = 'la-hitrust-r2'
param storageAccountName = 'hitrustr2archive001' // must be globally unique + lowercase
// Optional overrides:
// param logAnalyticsRetentionDays = 365
// param immutabilityDays = 365
