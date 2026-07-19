---
description: Assess the Azure data estate and design a data solution (lakehouse / dimensional model / ingestion pipeline)
---

Use the `data-architect` sub-agent. First **discover and inspect** the current data estate
(read-only): data-platform resources, ADLS Gen2 readiness of storage accounts, and the SQL
footprint. Then design what the user asked for, choosing the right skill:

- Medallion lakehouse layout → `medallion-lakehouse-design`
- Kimball dimensional model + Synapse DDL → `dimensional-model-synapse`
- ETL/ELT ingestion pipeline blueprint → `ingestion-pipeline-design`

Present options with trade-offs (scalability, cost, complexity), then a clear recommendation, and
always fold in security (private endpoints, Data Exfiltration Protection, CMK, RBAC) and
observability (diagnostic logging). Save substantial designs to `reports/output/`.

$ARGUMENTS
