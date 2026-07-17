#!/usr/bin/env bash
# =============================================================================
# HITRUST r2 — Synapse Diagnostic Logging Baseline (Azure CLI)
# =============================================================================
# Mirror of infra/bicep/main.bicep for teams who prefer imperative CLI.
# Creates a Log Analytics workspace (365d), an immutable WORM storage archive,
# and a Synapse diagnostic setting streaming the 3 HITRUST-required categories
# to BOTH destinations.
#
# Usage:
#   az login
#   ./setup_diagnostics.sh \
#       -g <resource-group> \
#       -s <synapse-workspace-name> \
#       -l <log-analytics-name> \
#       -a <storage-account-name>   # globally unique, lowercase, 3-24 chars
#
# Requires: Azure CLI. The signed-in identity needs Contributor on the RG.
# =============================================================================
set -euo pipefail

RETENTION_DAYS=365
IMMUTABILITY_DAYS=365
DIAG_NAME="hitrust-r2-synapse-diagnostics"
LOCATION=""

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while getopts "g:s:l:a:d:r:i:h" opt; do
  case "$opt" in
    g) RESOURCE_GROUP="$OPTARG" ;;
    s) SYNAPSE_WS="$OPTARG" ;;
    l) LA_NAME="$OPTARG" ;;
    a) STORAGE_NAME="$OPTARG" ;;
    d) DIAG_NAME="$OPTARG" ;;
    r) RETENTION_DAYS="$OPTARG" ;;
    i) IMMUTABILITY_DAYS="$OPTARG" ;;
    h|*) usage ;;
  esac
done

: "${RESOURCE_GROUP:?-g resource group is required}"
: "${SYNAPSE_WS:?-s synapse workspace name is required}"
: "${LA_NAME:?-l log analytics workspace name is required}"
: "${STORAGE_NAME:?-a storage account name is required}"

[ -z "$LOCATION" ] && LOCATION="$(az group show -n "$RESOURCE_GROUP" --query location -o tsv)"

echo "[*] Resolving Synapse workspace resource ID..."
SYNAPSE_ID="$(az synapse workspace show \
  --name "$SYNAPSE_WS" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)"

echo "[*] Creating Log Analytics workspace ($LA_NAME, ${RETENTION_DAYS}d retention)..."
az monitor log-analytics workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LA_NAME" \
  --location "$LOCATION" \
  --retention-time "$RETENTION_DAYS" \
  --output none
LA_ID="$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LA_NAME" --query id -o tsv)"

echo "[*] Creating immutable (WORM) storage archive ($STORAGE_NAME, ${IMMUTABILITY_DAYS}d)..."
# --enable-alw turns on account-level WORM; state Unlocked can be extended/locked later.
az storage account create \
  --name "$STORAGE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --https-only true \
  --enable-alw true \
  --immutability-period-since-creation-in-days "$IMMUTABILITY_DAYS" \
  --immutability-state Unlocked \
  --output none
STORAGE_ID="$(az storage account show \
  --name "$STORAGE_NAME" \
  --resource-group "$RESOURCE_GROUP" --query id -o tsv)"

echo "[*] Creating diagnostic setting on Synapse ($DIAG_NAME) -> Log Analytics + WORM archive..."
az monitor diagnostic-settings create \
  --name "$DIAG_NAME" \
  --resource "$SYNAPSE_ID" \
  --workspace "$LA_ID" \
  --storage-account "$STORAGE_ID" \
  --logs '[
    {"category":"IntegrationPipelineRuns","enabled":true},
    {"category":"IntegrationActivityRuns","enabled":true},
    {"category":"SynapseRbacOperations","enabled":true}
  ]' \
  --output none

echo "[+] Done. Synapse '$SYNAPSE_WS' now streams audit logs to:"
echo "    Log Analytics : $LA_ID"
echo "    WORM archive  : $STORAGE_ID"
echo "[i] To make the archive retention permanent before an audit, lock it:"
echo "    az storage account update -n $STORAGE_NAME -g $RESOURCE_GROUP --immutability-state Locked"
