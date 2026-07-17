# Azure Technical Security Retention Framework — HITRUST CSF r2 (Synapse)

For a **HITRUST CSF r2 Validated Assessment**, the stakes are significantly higher than r1.
The r2 track tests not just implementation, but also your formal **Policies and Procedures**
(the PRISMA maturity model).

Because Azure Synapse Analytics is used here as a multi-directional data hub (ingesting
external data and executing ETL/ELT to egress data to third-party environments), the primary
HITRUST risks are:

- **Data Ingestion Integrity**
- **Data Exfiltration / Leakage**
- **Cross-Border / Cross-System Boundary Auditing**

You must configure a specific technical framework, retention plan, and KQL audit cadence to
satisfy an r2 auditor.

---

## 1. Hardening & Logging Synapse Ingestion & ETL Pipelines

To satisfy HITRUST **Domain 09 (Access Control)** and **Domain 10 (Security Assessment)**, you
must explicitly log pipeline executions, connections, and external data mutations.

- **Enable Managed Private Endpoints** — Ensure the Synapse Workspace uses Managed Virtual
  Networks. Connect to external Azure data sources or file storage safely using Managed Private
  Endpoints.
- **Enforce Data Exfiltration Protection (DEP)** — Enable DEP on the workspace. This locks down
  outbound communication, forcing Synapse to communicate only with validated, approved external
  targets via designated Linked Services.
- **Activate Synapse Diagnostic Logs** — In Diagnostic Settings, stream the following telemetry
  to a centralized Log Analytics Workspace:
  - `IntegrationPipelineRuns` — tracks entire ETL execution states
  - `IntegrationActivityRuns` — tracks individual copy/transform steps
  - `SynapseRbacOperations` — logs role-based access modifications

---

## 2. Required KQL Queries for r2 ETL Audit Review

Your r2 auditor expects evidence that you regularly monitor the integrity and security of these
ingestion/egress pipelines. Incorporate these into your dashboard reviews. See:

- [`kql/etl_egress_volume_anomalies.kql`](../kql/etl_egress_volume_anomalies.kql) — flag bulk
  exfiltration spikes (baseline example: > 5 GB).
- [`kql/unauthorized_pipeline_modifications.kql`](../kql/unauthorized_pipeline_modifications.kql)
  — detect unauthorized pipeline / linked service writes.

---

## 3. Fulfilling the r2 PRISMA Maturity Requirement

Under HITRUST r2, technical implementation is only **1 of 3** core scores needed for
certification — Policy, Procedure, and Implementation must all be documented.

| Maturity Level  | What you must do for Synapse / ETL logging |
| --------------- | ------------------------------------------ |
| **1. Policy**   | Draft a corporate policy stating that all systems handling PHI must log data movement across system boundaries, and that logs are retained for the compliance duration. |
| **2. Procedure**| Create a step-by-step SOP: how the Azure Portal is configured, the explicit KQL queries used, and who is assigned to review pipeline anomalies. |
| **3. Implemented** | Run the systems as defined. Provide the auditor with 90+ days of historical KQL search history logs and signed-off weekly review logs showing you followed the SOP. |

---

## 4. r2 Log Retention & "Point-In-Time" Archiving

HITRUST r2 mandates a strict **1-year minimum** retention for operational security logging (some
organizational risk factors extend this). Because Synapse processes active pipelines, configure a
**dual-destination strategy** via Diagnostic Settings:

1. **Log Analytics Workspace** — retain data for **365 days** for immediate KQL query availability.
2. **Immutable Blob Storage** — stream the exact same `IntegrationPipelineRuns` to an Azure Storage
   account configured with a **Time-Based Retention Policy**. This forms a **WORM** (Write Once,
   Read Many) archive, protecting pipeline records from internal administrative deletion — a
   critical proof point during a validated r2 audit.

---

## Open configuration questions (from the source doc)

- Are you using **Self-hosted Integration Runtimes (SHIR)** to pull data from on-premises file
  shares or databases? (If so, SHIR appliances need explicit Log Analytics configuration.)
- Do the external systems you transmit data to require **REST API / Webhook egress**, or are they
  standard Cloud Storage/Databases? (REST egress should be routed through an approved API
  Management proxy.)
