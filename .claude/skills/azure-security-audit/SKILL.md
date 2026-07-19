---
name: azure-security-audit
description: Read-only Azure security posture checks via the az CLI — Network Security Groups, Key Vault exposure, Microsoft Defender for Cloud alerts, Resource Group tags, and Azure Policy compliance. Use when auditing or scanning an Azure subscription's security/compliance.
---

# Azure Security Audit (read-only, via `az`)

All commands are read-only. Confirm scope first: `az account show -o json`.

## Network Security Groups — open ingress
```bash
az network nsg list -o json
```
Flag any rule where `direction == "Inbound"`, `access == "Allow"`, and
`sourceAddressPrefix in ("*", "0.0.0.0/0")`. Check both `securityRules` and `defaultSecurityRules`.
Report NSG name, resource group (`id` segment 4), destination port, protocol. Dangerous ports:
22 (SSH), 3389 (RDP), 80/443, 1433 (SQL), 3306 (MySQL), 5432 (Postgres).

Filter helper:
```bash
az network nsg list --query "[].{nsg:name,rg:resourceGroup,rules:securityRules[?direction=='Inbound'&&access=='Allow'&&(sourceAddressPrefix=='*'||sourceAddressPrefix=='0.0.0.0/0')].{name:name,port:destinationPortRange,proto:protocol}}" -o json
```

## Key Vault — public exposure
```bash
az keyvault list -o json
az keyvault show --name <vault> -o json
```
Report `properties.enableRbacAuthorization`, count of `properties.accessPolicies`,
`properties.publicNetworkAccess`, `properties.networkAcls.defaultAction`.
**FAIL** when `publicNetworkAccess != "Disabled"` AND `networkAcls.defaultAction != "Deny"`.

## Microsoft Defender for Cloud — active alerts
```bash
az security alert list -o json 2>/dev/null || echo "Defender for Cloud not enabled / needs Security Reader"
```
Summarize: `alertDisplayName`, `severity`, `compromisedEntity`, `remediation`.

## Resource Group compliance tags
```bash
az group list -o json
```
Flag groups missing `Environment`, `Owner`, or `HITRUST_Scope` tags.

## Azure Policy compliance
```bash
az policy state summarize -o json
az policy state list --filter "complianceState eq 'NonCompliant'" --top 50 -o json
```
List: resourceId, resourceType, policyAssignmentName, policyDefinitionName.

## Reporting
Correlate cross-service risk (public Key Vault + wide-open NSG = critical PHI path). Map to HITRUST
r2 Domain 09 (Access Control) and Domain 10 (Security Assessment). For fixes, emit exact `az`
commands or hand off to the `azure-policy-remediation` skill. Never delete/modify — recommend only.
