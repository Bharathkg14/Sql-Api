-- =============================================================================
-- 00_setup_environment.sql
-- Snowflake Cortex AI Project — Environment Setup
-- Run as: ACCOUNTADMIN or SYSADMIN
-- =============================================================================

-- ── 1. DATABASE & SCHEMAS ────────────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS CORTEX_AI_LAB
    COMMENT = 'Snowflake Cortex AI demo — metadata insights + anomaly detection';

CREATE SCHEMA IF NOT EXISTS CORTEX_AI_LAB.METADATA
    COMMENT = 'Metadata catalogue layer for Scenario 1';

CREATE SCHEMA IF NOT EXISTS CORTEX_AI_LAB.EPOS_DATA
    COMMENT = 'EPOS fact data for Scenario 2 anomaly detection';

CREATE SCHEMA IF NOT EXISTS CORTEX_AI_LAB.DQ_RESULTS
    COMMENT = 'DQ check results — rule-based and Cortex AI findings';


-- ── 2. VIRTUAL WAREHOUSES ────────────────────────────────────────────────────

-- Standard warehouse for DDL + data loading
CREATE WAREHOUSE IF NOT EXISTS CORTEX_WH
    WAREHOUSE_SIZE = 'SMALL'
    AUTO_SUSPEND   = 120
    AUTO_RESUME    = TRUE
    COMMENT        = 'General compute for Cortex AI project';

-- Larger warehouse for Cortex LLM inference (can be CPU-heavy for batch scoring)
CREATE WAREHOUSE IF NOT EXISTS CORTEX_LLM_WH
    WAREHOUSE_SIZE = 'MEDIUM'
    AUTO_SUSPEND   = 60
    AUTO_RESUME    = TRUE
    COMMENT        = 'Dedicated warehouse for Cortex COMPLETE() batch calls';


-- ── 3. ROLE & PRIVILEGES ─────────────────────────────────────────────────────

CREATE ROLE IF NOT EXISTS CORTEX_DEV
    COMMENT = 'Developer role for Cortex AI project';

GRANT USAGE ON DATABASE CORTEX_AI_LAB          TO ROLE CORTEX_DEV;
GRANT USAGE ON ALL SCHEMAS IN DATABASE CORTEX_AI_LAB TO ROLE CORTEX_DEV;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE CORTEX_AI_LAB TO ROLE CORTEX_DEV;
GRANT CREATE TABLE  ON SCHEMA CORTEX_AI_LAB.METADATA  TO ROLE CORTEX_DEV;
GRANT CREATE TABLE  ON SCHEMA CORTEX_AI_LAB.EPOS_DATA  TO ROLE CORTEX_DEV;
GRANT CREATE TABLE  ON SCHEMA CORTEX_AI_LAB.DQ_RESULTS TO ROLE CORTEX_DEV;
GRANT CREATE VIEW   ON SCHEMA CORTEX_AI_LAB.DQ_RESULTS TO ROLE CORTEX_DEV;
GRANT USAGE, OPERATE ON WAREHOUSE CORTEX_WH    TO ROLE CORTEX_DEV;
GRANT USAGE, OPERATE ON WAREHOUSE CORTEX_LLM_WH TO ROLE CORTEX_DEV;

-- Cortex functions live in the SNOWFLAKE database — grant access
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE CORTEX_DEV;

-- Assign role to your user (replace YOUR_USERNAME)
-- GRANT ROLE CORTEX_DEV TO USER YOUR_USERNAME;


-- ── 4. CONTEXT ───────────────────────────────────────────────────────────────

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE DATABASE  CORTEX_AI_LAB;

-- ── 5. VERIFY CORTEX IS AVAILABLE ────────────────────────────────────────────

SELECT SNOWFLAKE.CORTEX.COMPLETE(
    'mistral-7b',
    'Respond in one sentence: What is Snowflake Cortex AI?'
) AS cortex_test;

-- Expected: A short text description. If you get an error, check your region
-- and run: SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;
