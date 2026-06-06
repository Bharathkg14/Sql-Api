-- =============================================================================
-- 01d_metadata_search_service.sql
-- Scenario 1: Cortex Search Service — Semantic Search over Metadata
--
-- Cortex Search Service indexes text columns and enables fast semantic
-- similarity search via SQL — no embeddings code needed.
--
-- USE CASE: "Find all columns related to outlet location or geography"
--           Returns semantically similar results, not just keyword matches.
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.METADATA;


-- ── 1. CREATE A UNIFIED SEARCHABLE VIEW ──────────────────────────────────────
-- Cortex Search needs a flat source with a primary text column to index.
-- We combine table + column descriptions into one searchable corpus.

CREATE OR REPLACE VIEW V_METADATA_SEARCH_CORPUS AS
SELECT
    'COLUMN'                                            AS entity_type,
    c.TABLE_NAME || '.' || c.COLUMN_NAME               AS entity_name,
    c.TABLE_NAME                                        AS parent_table,
    c.COLUMN_NAME                                       AS column_name,
    c.DATA_TYPE                                         AS data_type,
    t.LAYER                                             AS layer,
    t.DOMAIN                                            AS domain,
    -- PRIMARY SEARCH TEXT — Cortex indexes this
    COALESCE(c.DESCRIPTION, '')
    || ' Table: ' || c.TABLE_NAME
    || ' Column: ' || c.COLUMN_NAME
    || ' Type: '   || COALESCE(c.DATA_TYPE, '')
    || ' DQ: '     || COALESCE(c.DQ_RULES_APPLIED, '')
    || ' Samples: '|| COALESCE(c.SAMPLE_VALUES, '')     AS search_text,
    c.DESCRIPTION                                        AS raw_description
FROM META_COLUMNS c
JOIN META_TABLES  t ON c.TABLE_ID = t.TABLE_ID

UNION ALL

SELECT
    'TABLE'                         AS entity_type,
    t.TABLE_NAME                    AS entity_name,
    t.TABLE_NAME                    AS parent_table,
    NULL                            AS column_name,
    NULL                            AS data_type,
    t.LAYER                         AS layer,
    t.DOMAIN                        AS domain,
    COALESCE(t.DESCRIPTION, '')
    || ' Table: ' || t.TABLE_NAME
    || ' Layer: ' || t.LAYER
    || ' Domain: '|| COALESCE(t.DOMAIN, '')
    || ' Refresh: '|| COALESCE(t.REFRESH_FREQUENCY, '')  AS search_text,
    t.DESCRIPTION                    AS raw_description
FROM META_TABLES t;


-- ── 2. CREATE CORTEX SEARCH SERVICE ─────────────────────────────────────────
-- This creates a managed search index over search_text.
-- Snowflake automatically embeds, indexes, and serves semantic queries.
-- Note: Takes 1-2 minutes to build the first time.

CREATE OR REPLACE CORTEX SEARCH SERVICE METADATA_SEMANTIC_SEARCH
    ON search_text                          -- column to embed + index
    ATTRIBUTES entity_type, entity_name,    -- filterable metadata columns
               parent_table, layer, domain,
               column_name, data_type,
               raw_description
    WAREHOUSE = CORTEX_WH
    TARGET_LAG = '1 hour'                   -- how fresh to keep the index
AS (
    SELECT * FROM V_METADATA_SEARCH_CORPUS
);


-- ── 3. QUERY THE SEARCH SERVICE ──────────────────────────────────────────────
-- Use the SEARCH_PREVIEW function to test semantic queries.
-- This returns the top-K most semantically similar metadata entries.

-- Query A: Find columns related to outlet location/geography
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'CORTEX_AI_LAB.METADATA.METADATA_SEMANTIC_SEARCH',
        '{
            "query": "outlet location geography address region",
            "columns": ["entity_type", "entity_name", "layer", "domain", "raw_description"],
            "limit": 5
        }'
    )
) AS semantic_search_results;


-- Query B: Find everything related to product harmonisation or matching
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'CORTEX_AI_LAB.METADATA.METADATA_SEMANTIC_SEARCH',
        '{
            "query": "product harmonisation symphony matching fuzzy lookup",
            "columns": ["entity_type", "entity_name", "layer", "raw_description"],
            "filter": {"@eq": {"layer": "GOLD"}},
            "limit": 5
        }'
    )
) AS semantic_search_results;


-- Query C: Find all DQ-related columns and tables
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'CORTEX_AI_LAB.METADATA.METADATA_SEMANTIC_SEARCH',
        '{
            "query": "data quality validation error quarantine check",
            "columns": ["entity_type", "entity_name", "parent_table", "raw_description"],
            "limit": 8
        }'
    )
) AS semantic_search_results;


-- Query D: Identify columns involved in surrogate key generation
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'CORTEX_AI_LAB.METADATA.METADATA_SEMANTIC_SEARCH',
        '{
            "query": "surrogate key hash SHA upsert merge unique identifier",
            "columns": ["entity_type", "entity_name", "parent_table", "raw_description"],
            "limit": 5
        }'
    )
) AS semantic_search_results;


-- ── 4. COMBINE SEARCH + COMPLETE (THE POWER MOVE) ────────────────────────────
-- Step 1: Search for relevant metadata chunks
-- Step 2: Pass those chunks as context to COMPLETE() for a structured answer
-- This is a lightweight RAG (Retrieval-Augmented Generation) pattern in pure SQL.

WITH search_results AS (
    SELECT
        r.value:entity_name::VARCHAR   AS entity_name,
        r.value:layer::VARCHAR         AS layer,
        r.value:raw_description::VARCHAR AS description
    FROM TABLE(
        FLATTEN(
            PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                    'CORTEX_AI_LAB.METADATA.METADATA_SEMANTIC_SEARCH',
                    '{
                        "query": "surrogate key hash generation pipeline",
                        "columns": ["entity_name", "layer", "raw_description"],
                        "limit": 4
                    }'
                )
            ):results
        )
    ) r
),
context_block AS (
    SELECT
        LISTAGG(s.entity_name || ': ' || COALESCE(s.description, ''), '\n')
        WITHIN GROUP (ORDER BY s.entity_name) AS ctx
    FROM search_results s
)
SELECT
    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-7b',
        'You are a data platform assistant. Using only the metadata below, explain in 2-3 sentences '
        || 'how surrogate keys are generated in this platform and which tables/columns are involved.\n\n'
        || 'RETRIEVED METADATA:\n' || c.ctx
        || '\n\nAnswer in plain English.'
    ) AS rag_answer
FROM context_block c;
