#!/usr/bin/env bash
# =============================================================================
# Assign the "Deploy Synapse diagnostic settings" DeployIfNotExists policy
# =============================================================================
# Creates the custom policy definition, assigns it at a subscription (or RG)
# scope with a system-assigned managed identity, grants that identity the roles
# needed to deploy diagnostic settings, and kicks off a remediation task so
# EXISTING non-compliant Synapse workspaces are fixed immediately.
#
# Usage:
#   az login
#   ./assign_policy.sh \
#       -w "<log-analytics-workspace-resource-id>" \
#       [-s "<subscription-id>"] \        # default: current subscription
#       [-g "<resource-group>"]           # optional: scope to one RG instead of the whole sub
#
# Requires: Azure CLI + permission to create role assignments (Owner or
# User Access Administrator) at the target scope.
# =============================================================================
set -euo pipefail

DEF_NAME="deploy-synapse-diagnostics-hitrust-r2"
ASSIGN_NAME="synapse-diag-hitrust-r2"
LOCATION="eastus"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_FILE="$SCRIPT_DIR/synapse-diagnostics-deployIfNotExists.json"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while getopts "w:s:g:l:h" opt; do
  case "$opt" in
    w) LA_WORKSPACE_ID="$OPTARG" ;;
    s) SUBSCRIPTION_ID="$OPTARG" ;;
    g) RESOURCE_GROUP="$OPTARG" ;;
    l) LOCATION="$OPTARG" ;;
    h|*) usage ;;
  esac
done

: "${LA_WORKSPACE_ID:?-w Log Analytics workspace resource ID is required}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"

if [ -n "${RESOURCE_GROUP:-}" ]; then
  SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
else
  SCOPE="/subscriptions/$SUBSCRIPTION_ID"
fi

echo "[*] Creating/updating policy definition '$DEF_NAME'..."
az policy definition create \
  --name "$DEF_NAME" \
  --display-name "Deploy Synapse diagnostic settings to Log Analytics (HITRUST r2)" \
  --mode Indexed \
  --rules "@$RULES_FILE" \
  --subscription "$SUBSCRIPTION_ID" \
  --output none
# The --rules file above is the full policy object; if your CLI version expects
# only the policyRule, extract it with:  jq '.properties.policyRule' <file>

echo "[*] Assigning policy at scope: $SCOPE"
az policy assignment create \
  --name "$ASSIGN_NAME" \
  --display-name "Synapse diagnostics (HITRUST r2)" \
  --policy "$DEF_NAME" \
  --scope "$SCOPE" \
  --mi-system-assigned \
  --location "$LOCATION" \
  --params "{\"logAnalyticsWorkspaceId\":{\"value\":\"$LA_WORKSPACE_ID\"}}" \
  --output none

echo "[*] Waiting for the assignment's managed identity to propagate..."
PRINCIPAL_ID="$(az policy assignment show --name "$ASSIGN_NAME" --scope "$SCOPE" --query identity.principalId -o tsv)"
for _ in $(seq 1 12); do
  [ -n "$PRINCIPAL_ID" ] && break
  sleep 5
  PRINCIPAL_ID="$(az policy assignment show --name "$ASSIGN_NAME" --scope "$SCOPE" --query identity.principalId -o tsv)"
done

echo "[*] Granting the identity the roles DeployIfNotExists needs..."
# Monitoring Contributor + Log Analytics Contributor (match roleDefinitionIds in the policy).
for ROLE in "Monitoring Contributor" "Log Analytics Contributor"; do
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "$ROLE" \
    --scope "$SCOPE" \
    --output none
done

echo "[*] Triggering remediation for existing non-compliant Synapse workspaces..."
az policy remediation create \
  --name "remediate-$ASSIGN_NAME" \
  --policy-assignment "$ASSIGN_NAME" \
  --resource-group "${RESOURCE_GROUP:-}" 2>/dev/null \
  || az policy remediation create \
       --name "remediate-$ASSIGN_NAME" \
       --policy-assignment "$ASSIGN_NAME"

echo "[+] Policy assigned and remediation started."
echo "[i] New or drifted Synapse workspaces will now auto-receive the diagnostic setting."
