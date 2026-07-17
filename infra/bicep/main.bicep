// =============================================================================
// HITRUST r2 — Synapse Diagnostic Logging Baseline (Bicep)
// =============================================================================
// Stands up the "always-on" audit-logging control for an EXISTING Azure Synapse
// workspace:
//   1. A Log Analytics workspace (365-day retention) for live KQL querying.
//   2. An immutable (WORM) Storage account for the tamper-proof archive.
//   3. A Diagnostic Setting on the Synapse workspace that streams the three
//      HITRUST-required categories to BOTH destinations.
//
// Scope: resource group. Deploy this into the SAME resource group as the
// Synapse workspace.
//
// Deploy:
//   az deployment group create \
//     --resource-group <rg-with-synapse> \
//     --template-file main.bicep \
//     --parameters synapseWorkspaceName=<name> \
//                  logAnalyticsWorkspaceName=<la-name> \
//                  storageAccountName=<globally-unique-lowercase>
// =============================================================================

@description('Name of the EXISTING Synapse workspace to attach diagnostics to.')
param synapseWorkspaceName string

@description('Name of the Log Analytics workspace to create for live querying.')
param logAnalyticsWorkspaceName string

@description('Globally-unique, lowercase name for the immutable archive storage account (3-24 chars).')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Log Analytics retention in days. HITRUST r2 minimum is 365.')
@minValue(365)
param logAnalyticsRetentionDays int = 365

@description('Immutable (WORM) retention window in days for the archive.')
@minValue(365)
param immutabilityDays int = 365

@description('Name of the diagnostic setting created on the Synapse workspace.')
param diagnosticSettingName string = 'hitrust-r2-synapse-diagnostics'

// --- Existing Synapse workspace (referenced, not created) --------------------
resource synapse 'Microsoft.Synapse/workspaces@2021-06-01' existing = {
  name: synapseWorkspaceName
}

// --- Log Analytics workspace (live KQL, 365-day retention) -------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: logAnalyticsRetentionDays
    features: {
      // Prevent silent data purge; supports the r2 "logs can't be deleted" posture.
      immediatePurgeDataOn30Days: false
    }
  }
}

// --- Immutable (WORM) storage archive ----------------------------------------
// Account-level immutability + versioning applies WORM to ALL blobs, including
// the `insights-logs-*` containers that Diagnostic Settings auto-creates.
// state 'Unlocked' lets you extend/lock later; switch to 'Locked' to make the
// retention window permanent and irrevocable (recommended before an audit).
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS' // Consider Standard_GRS/RA-GRS for production durability.
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    immutableStorageWithVersioning: {
      enabled: true
      immutabilityPolicy: {
        immutabilityPeriodSinceCreationInDays: immutabilityDays
        allowProtectedAppendWrites: true
        state: 'Unlocked'
      }
    }
  }
}

// --- Diagnostic Setting: stream to BOTH Log Analytics and the WORM archive ---
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: diagnosticSettingName
  scope: synapse
  properties: {
    workspaceId: logAnalytics.id
    storageAccountId: storage.id
    logs: [
      {
        category: 'IntegrationPipelineRuns'
        enabled: true
      }
      {
        category: 'IntegrationActivityRuns'
        enabled: true
      }
      {
        category: 'SynapseRbacOperations'
        enabled: true
      }
    ]
  }
}

output logAnalyticsWorkspaceId string = logAnalytics.id
output immutableArchiveStorageId string = storage.id
output diagnosticSettingId string = diagnostics.id
