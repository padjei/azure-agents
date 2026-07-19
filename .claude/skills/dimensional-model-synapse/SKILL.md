---
name: dimensional-model-synapse
description: Design a Kimball star schema for a business process and emit Synapse-dedicated-SQL-pool-optimized T-SQL DDL (HASH/REPLICATE distribution, clustered columnstore, SCD types). Use when designing a data warehouse, star schema, fact/dimension model, or dimensional model.
---

# Dimensional Model (Kimball) for Synapse

Ask for the **business process**, **grain**, **measures**, and **dimensions** if not given.

## Method
1. Declare the **grain** first ("one row per ...") — everything follows from it.
2. **Fact** = `Fact<Process>`; measures are additive where possible; one FK per dimension.
3. **Dimensions** = `Dim<Name>`, surrogate key `<Name>Key`; date/time dims are Type 0 (static);
   most business dims are SCD **Type 2** (track history with RowIsCurrent/RowStart/RowEnd).
4. Consider transaction vs periodic-snapshot vs accumulating-snapshot fact types.

## Synapse dedicated SQL pool optimizations
- **Fact**: `DISTRIBUTION = HASH(<high-cardinality FK>)` + `CLUSTERED COLUMNSTORE INDEX`; partition by date key.
- **Small dimensions**: `DISTRIBUTION = REPLICATE`. **Very large dims**: `ROUND_ROBIN` or `HASH`.
- Load via CTAS / partition switching for performant batch loads.

## DDL template
```sql
-- Fact: HASH distribution + clustered columnstore
CREATE TABLE dbo.Fact<Process>
(
    DateKey INT NOT NULL,
    <Dim>Key INT NOT NULL,          -- one FK per dimension
    <measure> DECIMAL(18,2) NULL,   -- one column per measure
    LoadDate DATETIME2 NOT NULL
)
WITH (DISTRIBUTION = HASH(<Dim>Key), CLUSTERED COLUMNSTORE INDEX);

-- Dimension (SCD Type 2)
CREATE TABLE dbo.Dim<Name>
(
    <Name>Key INT NOT NULL,         -- surrogate key
    BusinessKey NVARCHAR(100) NOT NULL,
    -- descriptive attributes ...
    RowIsCurrent BIT NOT NULL,
    RowStartDate DATETIME2 NOT NULL,
    RowEndDate DATETIME2 NULL
)
WITH (DISTRIBUTION = REPLICATE, CLUSTERED COLUMNSTORE INDEX);
```
Emit the concrete DDL with real table/column names filled in, plus a short rationale for the
distribution choices.
