-- =============================================================================
-- 01a_create_metadata_tables.sql
-- Scenario 1: Metadata Layer — DDL
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.METADATA;


-- ── TABLE CATALOGUE ──────────────────────────────────────────────────────────
-- Tracks every table in the data platform with ownership + refresh metadata

CREATE OR REPLACE TABLE META_TABLES (
    TABLE_ID            NUMBER AUTOINCREMENT PRIMARY KEY,
    TABLE_NAME          VARCHAR(200)    NOT NULL,
    SCHEMA_NAME         VARCHAR(100)    NOT NULL,
    DATABASE_NAME       VARCHAR(100)    NOT NULL,
    LAYER               VARCHAR(20)     NOT NULL,   -- LANDING | SILVER | GOLD
    DOMAIN              VARCHAR(50),                -- EPOS | DEPLETION | PRODUCT | CUSTOMER
    OWNER_TEAM          VARCHAR(100),
    OWNER_EMAIL         VARCHAR(200),
    DESCRIPTION         VARCHAR(2000),
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,
    REFRESH_FREQUENCY   VARCHAR(50),                -- DAILY | WEEKLY | REAL_TIME
    LAST_REFRESHED_AT   TIMESTAMP_NTZ,
    ROW_COUNT_LAST_RUN  NUMBER,
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE META_TABLES IS
    'Central catalogue of all platform tables across Landing, Silver and Gold layers.';


-- ── COLUMN CATALOGUE ─────────────────────────────────────────────────────────
-- Tracks every column with semantic descriptions — this is what Cortex reasons over

CREATE OR REPLACE TABLE META_COLUMNS (
    COLUMN_ID           NUMBER AUTOINCREMENT PRIMARY KEY,
    TABLE_ID            NUMBER          NOT NULL REFERENCES META_TABLES(TABLE_ID),
    TABLE_NAME          VARCHAR(200)    NOT NULL,
    COLUMN_NAME         VARCHAR(200)    NOT NULL,
    DATA_TYPE           VARCHAR(100),
    IS_NULLABLE         BOOLEAN,
    IS_PRIMARY_KEY      BOOLEAN         DEFAULT FALSE,
    IS_FOREIGN_KEY      BOOLEAN         DEFAULT FALSE,
    REFERENCES_TABLE    VARCHAR(200),
    REFERENCES_COLUMN   VARCHAR(200),
    DESCRIPTION         VARCHAR(2000),              -- Human-written semantic description
    SAMPLE_VALUES       VARCHAR(1000),              -- Comma-separated examples
    DQ_RULES_APPLIED    VARCHAR(1000),              -- e.g. NOT NULL, RANGE(0,100)
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE META_COLUMNS IS
    'Column-level catalogue with semantic descriptions used by Cortex for natural language Q&A.';


-- ── LINEAGE ──────────────────────────────────────────────────────────────────
-- Tracks source → target table relationships across pipeline hops

CREATE OR REPLACE TABLE META_LINEAGE (
    LINEAGE_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
    SOURCE_TABLE        VARCHAR(200)    NOT NULL,
    SOURCE_SCHEMA       VARCHAR(100),
    SOURCE_LAYER        VARCHAR(20),
    TARGET_TABLE        VARCHAR(200)    NOT NULL,
    TARGET_SCHEMA       VARCHAR(100),
    TARGET_LAYER        VARCHAR(20),
    TRANSFORM_TYPE      VARCHAR(100),   -- MERGE | JOIN | AGGREGATION | FILTER | LOOKUP
    TRANSFORM_NOTES     VARCHAR(1000),
    PIPELINE_NAME       VARCHAR(200),
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE META_LINEAGE IS
    'Source-to-target lineage graph. Used by Cortex to answer multi-hop upstream/downstream questions.';


-- ── DASHBOARD DEPENDENCIES ───────────────────────────────────────────────────
-- Maps which dashboards consume which gold tables

CREATE OR REPLACE TABLE META_DASHBOARD_DEPS (
    DEP_ID              NUMBER AUTOINCREMENT PRIMARY KEY,
    DASHBOARD_NAME      VARCHAR(200)    NOT NULL,
    DASHBOARD_TOOL      VARCHAR(100),               -- POWER_BI | TABLEAU | HEX | SIGMA
    TABLE_NAME          VARCHAR(200)    NOT NULL,
    SCHEMA_NAME         VARCHAR(100),
    FIELD_USED          VARCHAR(200),
    IS_CRITICAL         BOOLEAN         DEFAULT FALSE,
    BUSINESS_OWNER      VARCHAR(200),
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE META_DASHBOARD_DEPS IS
    'Maps BI dashboards to their underlying gold tables. Enables Cortex to answer: which dashboards are at risk if this table is stale?';


-- ── CORTEX Q&A LOG ───────────────────────────────────────────────────────────
-- Audit trail of every natural language question asked through Cortex

CREATE OR REPLACE TABLE META_CORTEX_QA_LOG (
    LOG_ID              NUMBER AUTOINCREMENT PRIMARY KEY,
    QUESTION            VARCHAR(4000),
    CONTEXT_TABLES_USED VARCHAR(500),
    MODEL_USED          VARCHAR(100),
    RESPONSE            VARCHAR(16000),
    TOKENS_APPROX       NUMBER,
    ASKED_BY            VARCHAR(200)    DEFAULT CURRENT_USER(),
    ASKED_AT            TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE META_CORTEX_QA_LOG IS
    'Audit log of all Cortex AI metadata Q&A queries — useful for tracking adoption and common questions.';
