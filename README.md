# Snowflake Cortex AI — End-to-End Project
## Metadata-Driven Smart Insights + AI-Powered Anomaly Detection

---

## Project Structure

```
snowflake_cortex_ai_project/
│
├── README.md                          ← This file
│
├── 00_setup/
│   └── 00_setup_environment.sql       ← Roles, databases, warehouses, schemas
│
├── 01_metadata_insights/
│   ├── 01a_create_metadata_tables.sql ← Metadata layer (tables, columns, lineage, dashboards)
│   ├── 01b_seed_metadata.sql          ← Realistic sample metadata for DDH-style pipelines
│   ├── 01c_cortex_metadata_qa.sql     ← Cortex COMPLETE() for natural language Q&A
│   └── 01d_metadata_search_service.sql← Cortex Search Service for fast semantic retrieval
│
├── 02_anomaly_detection/
│   ├── 02a_create_data_tables.sql     ← Fact tables simulating EPOS/Depletion data
│   ├── 02b_seed_data_normal.sql       ← Seed normal baseline data (30 days)
│   ├── 02c_seed_data_anomalous.sql    ← Inject anomalies: price spike, silent region, combo
│   ├── 02d_statistical_baseline.sql   ← Compute rolling stats (mean, stddev, IQR)
│   ├── 02e_anomaly_detection_rules.sql← Rule-based DQ checks (traditional baseline)
│   ├── 02f_cortex_anomaly_scoring.sql ← Cortex ML anomaly scoring + explanation
│   └── 02g_anomaly_dashboard_view.sql ← Unified view: rule-based vs Cortex findings
│
└── 03_orchestration/
    └── 03_scheduled_tasks.sql         ← Snowflake Tasks to automate daily runs
```

---

## Execution Order

Run scripts **in the numbered order** above. Each script is self-contained and idempotent where possible.

### Prerequisites
- Snowflake account with **Enterprise tier or above** (required for Cortex AI functions)
- ACCOUNTADMIN or SYSADMIN role to create roles/databases
- Cortex AI enabled in your Snowflake region (available in AWS us-east-1, us-west-2, EU regions — check `SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION'`)

### Verify Cortex Availability
```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', 'Say hello') AS test;
```
If this returns a result, you're good to go.

---

## What Each Scenario Delivers

### Scenario 1 — Metadata Smart Insights
| Feature | Implementation |
|---|---|
| Metadata catalogue | Tables: `meta_tables`, `meta_columns`, `meta_lineage`, `meta_dashboard_deps` |
| Natural language Q&A | `CORTEX.COMPLETE()` with metadata context injection |
| Semantic search | Cortex Search Service over column/table descriptions |
| Example questions | 4 pre-built queries you can run and adapt |

### Scenario 2 — AI Anomaly Detection
| Feature | Implementation |
|---|---|
| Baseline data | 30 days of EPOS fact data with realistic distributions |
| Anomaly types | Price spike (10x), silent region (zero records), multi-column combo anomaly |
| Statistical baseline | Rolling 7-day mean, stddev, IQR per metric/dimension |
| Rule-based DQ | 5 traditional threshold checks (for comparison) |
| Cortex detection | `CORTEX.COMPLETE()` scoring each record with reasoning |
| Dashboard view | Side-by-side: what rules caught vs what Cortex caught |

---

## Key Snowflake Cortex Functions Used

| Function | Purpose |
|---|---|
| `SNOWFLAKE.CORTEX.COMPLETE(model, prompt)` | LLM inference — Q&A, anomaly reasoning, explanation |
| `SNOWFLAKE.CORTEX.SUMMARIZE(text)` | Summarise long metadata descriptions |
| `SNOWFLAKE.CORTEX.SENTIMENT(text)` | Not used here but available for feedback pipelines |
| Cortex Search Service | `CREATE CORTEX SEARCH SERVICE` for semantic metadata retrieval |

Models available: `mistral-7b`, `mixtral-8x7b`, `llama3-8b`, `llama3-70b`, `snowflake-arctic`
