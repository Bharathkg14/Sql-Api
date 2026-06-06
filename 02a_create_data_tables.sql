-- =============================================================================
-- 02a_create_data_tables.sql
-- Scenario 2: EPOS Fact Tables + Anomaly Tracking Tables — DDL
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;


-- ── EPOS DAILY FACTS ─────────────────────────────────────────────────────────
-- Simulates gold-layer EPOS data aggregated to outlet+product+day granularity

CREATE OR REPLACE TABLE EPOS_DAILY_FACTS (
    FACT_ID             NUMBER AUTOINCREMENT PRIMARY KEY,
    TRANSACTION_DATE    DATE            NOT NULL,
    OUTLET_CODE         VARCHAR(14)     NOT NULL,
    PRODUCT_CODE        VARCHAR(50)     NOT NULL,
    CUSTOMER_CODE       VARCHAR(10)     NOT NULL,
    REGION              VARCHAR(50)     NOT NULL,   -- NORTH | SOUTH | EAST | WEST | CENTRAL
    CHANNEL             VARCHAR(50),                -- ON_TRADE | OFF_TRADE | MODERN_TRADE
    BRAND_CODE          VARCHAR(50),
    PACK_SIZE           VARCHAR(20),
    UNIT_PRICE          NUMBER(12,2),               -- Per 9L case price in BRL
    SALES_VOLUME_CASES  NUMBER(12,4),               -- 9L equivalent cases
    SALES_VALUE_BRL     NUMBER(18,2),               -- Sales value in BRL
    TRANSACTION_COUNT   NUMBER,                     -- Number of POS transactions
    BATCH_DATE          DATE            DEFAULT CURRENT_DATE(),
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE EPOS_DAILY_FACTS IS
    'Simulated gold EPOS daily fact table. 30 days baseline + injected anomalies for Cortex demo.';


-- ── STATISTICAL BASELINE ─────────────────────────────────────────────────────
-- Stores rolling 7-day stats per metric dimension — populated by 02d script

CREATE OR REPLACE TABLE EPOS_STAT_BASELINE (
    BASELINE_ID         NUMBER AUTOINCREMENT PRIMARY KEY,
    STAT_DATE           DATE            NOT NULL,
    PRODUCT_CODE        VARCHAR(50)     NOT NULL,
    REGION              VARCHAR(50)     NOT NULL,
    METRIC              VARCHAR(50)     NOT NULL,   -- UNIT_PRICE | VOLUME | VALUE | TX_COUNT
    ROLLING_MEAN        NUMBER(18,6),
    ROLLING_STDDEV      NUMBER(18,6),
    ROLLING_MIN         NUMBER(18,6),
    ROLLING_MAX         NUMBER(18,6),
    ROLLING_P25         NUMBER(18,6),               -- 25th percentile
    ROLLING_P75         NUMBER(18,6),               -- 75th percentile
    IQR                 NUMBER(18,6),               -- Interquartile range
    LOWER_FENCE         NUMBER(18,6),               -- P25 - 1.5*IQR (Tukey lower)
    UPPER_FENCE         NUMBER(18,6),               -- P75 + 1.5*IQR (Tukey upper)
    WINDOW_DAYS         NUMBER          DEFAULT 7,
    COMPUTED_AT         TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE EPOS_STAT_BASELINE IS
    'Rolling 7-day statistical baseline per product+region+metric. Used to score anomalies.';


-- ── RULE-BASED DQ RESULTS ────────────────────────────────────────────────────
-- Traditional threshold-based DQ check results (for comparison with Cortex)

CREATE OR REPLACE TABLE DQ_RULE_RESULTS (
    RESULT_ID           NUMBER AUTOINCREMENT PRIMARY KEY,
    CHECK_DATE          DATE            NOT NULL,
    CHECK_NAME          VARCHAR(200)    NOT NULL,
    FACT_ID             NUMBER,
    OUTLET_CODE         VARCHAR(14),
    PRODUCT_CODE        VARCHAR(50),
    REGION              VARCHAR(50),
    TRANSACTION_DATE    DATE,
    METRIC_VALUE        NUMBER(18,6),
    THRESHOLD_MIN       NUMBER(18,6),
    THRESHOLD_MAX       NUMBER(18,6),
    RESULT              VARCHAR(10)     NOT NULL,    -- PASS | FAIL
    FAIL_REASON         VARCHAR(1000),
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE DQ_RULE_RESULTS IS
    'Traditional rule-based DQ check results. Compare with CORTEX_ANOMALY_SCORES to see what rules miss.';


-- ── CORTEX ANOMALY SCORES ─────────────────────────────────────────────────────
-- AI scoring output from Cortex COMPLETE() — includes reasoning + confidence

CREATE OR REPLACE TABLE CORTEX_ANOMALY_SCORES (
    SCORE_ID            NUMBER AUTOINCREMENT PRIMARY KEY,
    SCORED_DATE         DATE            NOT NULL,
    FACT_ID             NUMBER          NOT NULL,
    OUTLET_CODE         VARCHAR(14),
    PRODUCT_CODE        VARCHAR(50),
    REGION              VARCHAR(50),
    TRANSACTION_DATE    DATE,
    -- Metrics sent to Cortex
    UNIT_PRICE          NUMBER(12,2),
    SALES_VOLUME_CASES  NUMBER(12,4),
    SALES_VALUE_BRL     NUMBER(18,2),
    TRANSACTION_COUNT   NUMBER,
    -- Statistical context sent to Cortex
    PRICE_MEAN          NUMBER(18,6),
    PRICE_STDDEV        NUMBER(18,6),
    PRICE_UPPER_FENCE   NUMBER(18,6),
    VOLUME_MEAN         NUMBER(18,6),
    VOLUME_STDDEV       NUMBER(18,6),
    REGION_7D_AVG_ROWS  NUMBER,
    -- Cortex output
    IS_ANOMALY          BOOLEAN,
    ANOMALY_TYPE        VARCHAR(200),   -- PRICE_SPIKE | VOLUME_DROP | SILENT_REGION | COMBO | NONE
    CONFIDENCE          VARCHAR(20),    -- HIGH | MEDIUM | LOW
    CORTEX_REASONING    VARCHAR(4000),  -- Free-text explanation from the LLM
    MODEL_USED          VARCHAR(100)    DEFAULT 'mistral-7b',
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

COMMENT ON TABLE CORTEX_ANOMALY_SCORES IS
    'Cortex AI anomaly detection output. Includes LLM reasoning for each flagged record.';
