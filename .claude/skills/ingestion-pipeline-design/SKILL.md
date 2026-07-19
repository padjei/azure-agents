---
name: ingestion-pipeline-design
description: Blueprint an Azure ETL/ELT ingestion pipeline — recommended service by latency pattern (batch/micro-batch/streaming), staged flow, incremental-load strategy, reliability, security, and observability. Use when designing data ingestion, ETL/ELT, or a Data Factory / Synapse pipeline.
---

# Ingestion Pipeline Blueprint

Ask for **source type**, **target**, and **latency pattern** if not given.

## Service by pattern
| Pattern | Recommended service |
|---------|---------------------|
| batch | Azure Data Factory or Synapse Pipelines (Copy + Mapping Data Flows) |
| micro-batch | Synapse Spark / Databricks Auto Loader (incremental file ingestion) |
| streaming | Event Hubs + Azure Stream Analytics (or Spark Structured Streaming on Databricks/Synapse) |

## Staged flow (medallion-aligned)
1. **Extract** — connect to the source via a **managed-identity** linked service (no secrets).
2. **Land (Bronze)** — write raw, immutable copy to ADLS Gen2 partitioned by ingest date.
3. **Transform (Silver)** — cleanse, dedupe, type, conform to the canonical model (Delta).
4. **Serve (Gold/SQL)** — curate and publish to the target for BI/ML.

## Incremental strategy
- Batch/micro-batch: high-watermark column (`LastModified`) or native **CDC**; store the watermark in a control table.
- Streaming: event-time watermarking + checkpointing; exactly-once sink where supported.

## Reliability
- Retry with exponential backoff on activities.
- Idempotent loads (MERGE / partition overwrite) so re-runs are safe.
- Dead-letter path for records that fail validation.

## Security
- Self-hosted or Managed Integration Runtime with **Managed Private Endpoints** for sources.
- Enable Synapse **Data Exfiltration Protection** (approved egress targets only).
- Managed Identity for all linked services; any unavoidable secrets in Key Vault.

## Observability
Stream `IntegrationPipelineRuns` / `IntegrationActivityRuns` to Log Analytics + an immutable archive
— see `infra/` for the HITRUST r2 diagnostic-logging setup. The `kql/` queries flag egress-volume
anomalies and unauthorized pipeline modifications.
