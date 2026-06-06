-- =============================================================================
-- 01c_cortex_metadata_qa.sql
-- Scenario 1: Natural Language Metadata Q&A using Cortex COMPLETE()
--
-- HOW IT WORKS:
--   We build a context string from our metadata tables, then inject it into
--   a Cortex prompt. Cortex reasons over the context — not a vector index —
--   to answer multi-hop questions that keyword search cannot handle.
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_LLM_WH;
USE SCHEMA    CORTEX_AI_LAB.METADATA;


-- ─────────────────────────────────────────────────────────────────────────────
-- HELPER MACRO: Build a rich metadata context block
-- We materialise this once as a CTE and reuse it in each question below.
-- ─────────────────────────────────────────────────────────────────────────────

-- Quick preview of context we'll pass to Cortex
WITH metadata_context AS (
    SELECT
        '=== TABLE CATALOGUE ===\n' ||
        LISTAGG(
            'TABLE: '          || t.TABLE_NAME         || ' | '
            'LAYER: '          || t.LAYER               || ' | '
            'DOMAIN: '         || COALESCE(t.DOMAIN, 'N/A') || ' | '
            'ACTIVE: '         || t.IS_ACTIVE::VARCHAR  || ' | '
            'LAST_REFRESH: '   || COALESCE(t.LAST_REFRESHED_AT::VARCHAR, 'UNKNOWN') || ' | '
            'REFRESH_FREQ: '   || COALESCE(t.REFRESH_FREQUENCY, 'N/A') || ' | '
            'DESCRIPTION: '    || COALESCE(t.DESCRIPTION, '')
        , '\n') WITHIN GROUP (ORDER BY t.LAYER, t.TABLE_NAME)
        AS table_context
    FROM META_TABLES t
),
lineage_context AS (
    SELECT
        '\n=== LINEAGE (SOURCE → TARGET) ===\n' ||
        LISTAGG(
            l.SOURCE_TABLE || ' [' || l.SOURCE_LAYER || '] → '
            || l.TARGET_TABLE || ' [' || l.TARGET_LAYER || '] | '
            'TRANSFORM: ' || l.TRANSFORM_TYPE || ' | '
            'PIPELINE: ' || COALESCE(l.PIPELINE_NAME, 'N/A')
        , '\n') WITHIN GROUP (ORDER BY l.SOURCE_LAYER, l.SOURCE_TABLE)
        AS lineage_context
    FROM META_LINEAGE l
),
dashboard_context AS (
    SELECT
        '\n=== DASHBOARD DEPENDENCIES ===\n' ||
        LISTAGG(
            d.DASHBOARD_NAME || ' (' || d.DASHBOARD_TOOL || ') uses '
            || d.TABLE_NAME || '.' || d.FIELD_USED
            || ' | CRITICAL: ' || d.IS_CRITICAL::VARCHAR
        , '\n') WITHIN GROUP (ORDER BY d.DASHBOARD_NAME)
        AS dashboard_context
    FROM META_DASHBOARD_DEPS d
)
SELECT
    LENGTH(m.table_context) + LENGTH(l.lineage_context) + LENGTH(d.dashboard_context)
    AS approx_context_chars
FROM metadata_context m, lineage_context l, dashboard_context d;


-- =============================================================================
-- QUESTION 1: Which tables haven't been refreshed in 7 days and are used
--             in active dashboards?
-- =============================================================================

WITH metadata_ctx AS (
    SELECT
        LISTAGG('TABLE: ' || t.TABLE_NAME
            || ' | ACTIVE: '       || t.IS_ACTIVE::VARCHAR
            || ' | LAST_REFRESH: ' || COALESCE(t.LAST_REFRESHED_AT::VARCHAR, 'NEVER')
            || ' | DESCRIPTION: '  || COALESCE(t.DESCRIPTION, '')
        , '\n') WITHIN GROUP (ORDER BY t.TABLE_NAME) AS tbl_ctx
    FROM META_TABLES t
),
dashboard_ctx AS (
    SELECT
        LISTAGG('DASHBOARD: ' || d.DASHBOARD_NAME
            || ' | TABLE: '    || d.TABLE_NAME
            || ' | CRITICAL: ' || d.IS_CRITICAL::VARCHAR
        , '\n') WITHIN GROUP (ORDER BY d.DASHBOARD_NAME) AS dash_ctx
    FROM META_DASHBOARD_DEPS d
),
full_context AS (
    SELECT
        '=== TABLE REFRESH STATUS ===\n' || m.tbl_ctx
        || '\n\n=== DASHBOARD DEPENDENCIES ===\n' || d.dash_ctx
        AS context
    FROM metadata_ctx m, dashboard_ctx d
),
question AS (
    SELECT
        'You are a data platform assistant. Answer based ONLY on the metadata context provided.\n\n'
        || 'METADATA CONTEXT:\n' || c.context
        || '\n\nQUESTION: Which tables have not been refreshed in the last 7 days AND are used by at least one active dashboard? '
        || 'For each table found, list: table name, days since last refresh, which dashboards depend on it, and whether those dashboards are marked as critical. '
        || 'If a table is not active (IS_ACTIVE=FALSE), note that too. Be specific and structured.'
        AS prompt
    FROM full_context c
)
SELECT
    'Q1: Stale tables used in active dashboards' AS question_label,
    SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', q.prompt) AS cortex_answer
FROM question q;


-- =============================================================================
-- QUESTION 2: Summarise what the OUTLET_CODE field represents across all pipelines
-- =============================================================================

WITH column_ctx AS (
    SELECT
        LISTAGG('TABLE: ' || c.TABLE_NAME
            || ' | COLUMN: '       || c.COLUMN_NAME
            || ' | TYPE: '         || COALESCE(c.DATA_TYPE, '')
            || ' | FK_TO: '        || COALESCE(c.REFERENCES_TABLE || '.' || c.REFERENCES_COLUMN, 'N/A')
            || ' | DESCRIPTION: '  || COALESCE(c.DESCRIPTION, '')
            || ' | DQ_RULES: '     || COALESCE(c.DQ_RULES_APPLIED, '')
            || ' | SAMPLES: '      || COALESCE(c.SAMPLE_VALUES, '')
        , '\n') WITHIN GROUP (ORDER BY c.TABLE_NAME)
        AS col_ctx
    FROM META_COLUMNS c
    WHERE UPPER(c.COLUMN_NAME) LIKE '%OUTLET%'
       OR UPPER(c.DESCRIPTION) LIKE '%OUTLET%'
),
lineage_ctx AS (
    SELECT
        LISTAGG(l.SOURCE_TABLE || ' → ' || l.TARGET_TABLE
            || ' | ' || l.TRANSFORM_NOTES
        , '\n') WITHIN GROUP (ORDER BY l.SOURCE_TABLE)
        AS lin_ctx
    FROM META_LINEAGE l
),
question AS (
    SELECT
        'You are a data platform assistant. Using only the metadata context below, provide a comprehensive summary.\n\n'
        || '=== OUTLET_CODE COLUMN APPEARANCES ===\n' || cc.col_ctx
        || '\n\n=== PIPELINE LINEAGE NOTES ===\n' || lc.lin_ctx
        || '\n\nQUESTION: Summarise what the OUTLET_CODE field represents across all pipelines. Cover: '
        || '(1) how it is structured (format, padding), '
        || '(2) which tables it appears in and what role it plays in each, '
        || '(3) any DQ rules applied to it, '
        || '(4) how it flows from landing through silver to gold, '
        || '(5) any known data quality gaps or caveats. '
        || 'Write in plain English suitable for a business analyst.'
        AS prompt
    FROM column_ctx cc, lineage_ctx lc
)
SELECT
    'Q2: OUTLET_CODE field summary across all pipelines' AS question_label,
    SNOWFLAKE.CORTEX.COMPLETE('mixtral-8x7b', q.prompt) AS cortex_answer
FROM question q;


-- =============================================================================
-- QUESTION 3: Which upstream sources feed into tb_fact_epos?
--             (Multi-hop lineage question)
-- =============================================================================

WITH lineage_ctx AS (
    SELECT
        LISTAGG('SOURCE: ' || l.SOURCE_TABLE
            || ' [' || l.SOURCE_LAYER || ']'
            || ' → TARGET: ' || l.TARGET_TABLE
            || ' [' || l.TARGET_LAYER || ']'
            || ' | TRANSFORM: ' || l.TRANSFORM_TYPE
            || ' | PIPELINE: '  || COALESCE(l.PIPELINE_NAME, 'N/A')
            || ' | NOTES: '     || COALESCE(l.TRANSFORM_NOTES, '')
        , '\n') WITHIN GROUP (ORDER BY l.TARGET_LAYER, l.SOURCE_TABLE)
        AS lin_ctx
    FROM META_LINEAGE l
),
table_ctx AS (
    SELECT
        LISTAGG('TABLE: ' || t.TABLE_NAME
            || ' | LAYER: ' || t.LAYER
            || ' | DESCRIPTION: ' || COALESCE(t.DESCRIPTION, '')
        , '\n') WITHIN GROUP (ORDER BY t.LAYER)
        AS tbl_ctx
    FROM META_TABLES t
),
question AS (
    SELECT
        'You are a data platform assistant with expertise in data lineage.\n\n'
        || '=== TABLE DESCRIPTIONS ===\n' || tc.tbl_ctx
        || '\n\n=== LINEAGE RELATIONSHIPS ===\n' || lc.lin_ctx
        || '\n\nQUESTION: Trace the complete upstream lineage for tb_fact_epos. '
        || 'Starting from tb_fact_epos, identify every upstream source — going all the way back to the landing zone if possible. '
        || 'For each hop, describe: what transformation happens, which pipeline handles it, and what the source table contains. '
        || 'Present this as a numbered lineage chain from landing to gold.'
        AS prompt
    FROM lineage_ctx lc, table_ctx tc
)
SELECT
    'Q3: Full upstream lineage for tb_fact_epos' AS question_label,
    SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', q.prompt) AS cortex_answer
FROM question q;


-- =============================================================================
-- QUESTION 4: What is the business impact if tb_fact_depletion goes stale?
--             (Risk + dependency analysis)
-- =============================================================================

WITH table_ctx AS (
    SELECT
        LISTAGG('TABLE: ' || t.TABLE_NAME
            || ' | ACTIVE: ' || t.IS_ACTIVE::VARCHAR
            || ' | LAST_REFRESH: ' || COALESCE(t.LAST_REFRESHED_AT::VARCHAR, 'NEVER')
            || ' | DESCRIPTION: ' || COALESCE(t.DESCRIPTION, '')
        , '\n') WITHIN GROUP (ORDER BY t.TABLE_NAME)
        AS tbl_ctx
    FROM META_TABLES t
),
dash_ctx AS (
    SELECT
        LISTAGG('DASHBOARD: ' || d.DASHBOARD_NAME
            || ' | TOOL: '    || d.DASHBOARD_TOOL
            || ' | TABLE: '   || d.TABLE_NAME
            || ' | FIELD: '   || d.FIELD_USED
            || ' | CRITICAL: '|| d.IS_CRITICAL::VARCHAR
            || ' | OWNER: '   || COALESCE(d.BUSINESS_OWNER, 'Unknown')
        , '\n') WITHIN GROUP (ORDER BY d.IS_CRITICAL DESC, d.DASHBOARD_NAME)
        AS dash_ctx
    FROM META_DASHBOARD_DEPS d
),
question AS (
    SELECT
        'You are a data platform risk analyst.\n\n'
        || '=== TABLE METADATA ===\n' || tc.tbl_ctx
        || '\n\n=== DASHBOARD DEPENDENCIES ===\n' || dc.dash_ctx
        || '\n\nQUESTION: Analyse the business impact if tb_fact_depletion remains stale or inactive. '
        || 'Cover: (1) which dashboards and business owners are directly affected, '
        || '(2) what business decisions would be impaired (based on the table description and field usage), '
        || '(3) whether any critical dashboards are at risk, '
        || '(4) a recommended escalation path. '
        || 'Note: IS_ACTIVE=FALSE means the pipeline is currently not running.'
        AS prompt
    FROM table_ctx tc, dash_ctx dc
)
SELECT
    'Q4: Business impact of tb_fact_depletion being stale' AS question_label,
    SNOWFLAKE.CORTEX.COMPLETE('mixtral-8x7b', q.prompt) AS cortex_answer
FROM question q;


-- =============================================================================
-- LOG ALL Q&A TO AUDIT TABLE
-- Run this after you're satisfied with answers — captures them for future reference
-- =============================================================================

INSERT INTO META_CORTEX_QA_LOG (QUESTION, CONTEXT_TABLES_USED, MODEL_USED, RESPONSE)
VALUES
    ('Which tables haven't been refreshed in 7 days and are used in active dashboards?',
     'META_TABLES, META_DASHBOARD_DEPS', 'mistral-7b',
     'See 01c_cortex_metadata_qa.sql Q1 output'),

    ('Summarise what the OUTLET_CODE field represents across all pipelines',
     'META_COLUMNS, META_LINEAGE', 'mixtral-8x7b',
     'See 01c_cortex_metadata_qa.sql Q2 output'),

    ('Which upstream sources feed into tb_fact_epos?',
     'META_LINEAGE, META_TABLES', 'mistral-7b',
     'See 01c_cortex_metadata_qa.sql Q3 output'),

    ('What is the business impact if tb_fact_depletion goes stale?',
     'META_TABLES, META_DASHBOARD_DEPS', 'mixtral-8x7b',
     'See 01c_cortex_metadata_qa.sql Q4 output');
