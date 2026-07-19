---
name: medallion-lakehouse-design
description: Design a Bronze/Silver/Gold (medallion) lakehouse on Azure Data Lake Storage Gen2 + Delta Lake — zone layout, path conventions, formats, governance, and security. Use when designing a data lake, lakehouse, or medallion architecture for a data domain.
---

# Medallion Lakehouse Design (ADLS Gen2 + Delta)

Ask for the **domain** and **source systems** if not given, then produce the design.

## Storage foundation
- **Service**: ADLS Gen2 (hierarchical namespace enabled — verify with `az storage account show --query isHnsEnabled`).
- **Redundancy**: ZRS minimum; GRS/RA-GRS for production DR.
- **Table format**: Delta Lake (ACID, time travel) for Silver & Gold; source-native retained immutably in Bronze.
- **Partitioning**: Bronze by ingest date (`yyyy/MM/dd`); Gold by business keys.

## Zones
| Zone | Container | Path convention | Purpose | Format |
|------|-----------|-----------------|---------|--------|
| Bronze (Raw) | `bronze` | `bronze/{domain}/{source}/{yyyy}/{MM}/{dd}/` | Immutable landing, as-received | Source-native |
| Silver (Cleansed/Conformed) | `silver` | `silver/{domain}/{entity}/` | Deduped, typed, validated, conformed | Delta |
| Gold (Curated/Serving) | `gold` | `gold/{domain}/{mart}/` | Business aggregates / dimensional models for BI & ML | Delta (optionally served to Synapse dedicated SQL pool) |

## Governance
- Register the lake in **Microsoft Purview** (catalog, classification, lineage).
- Data-quality gates Bronze→Silver (schema + expectation checks).
- PII tagging / column-level classification at Silver.

## Security (by design)
- Private endpoints on the storage account; disable public blob access.
- Customer-managed keys (CMK) via Key Vault for encryption at rest.
- POSIX ACLs on paths + Azure RBAC for coarse-grained access.
- Synapse Data Exfiltration Protection when reading/writing from Synapse.

## Observability
Stream pipeline runs to Log Analytics + immutable archive — see `infra/` (HITRUST r2 diagnostic logging).
