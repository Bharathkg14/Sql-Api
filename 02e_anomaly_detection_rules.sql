-- =============================================================================
-- 02e_anomaly_detection_rules.sql
-- Scenario 2: Traditional Rule-Based DQ Checks
--
-- These are the checks a typical DQ framework would run.
-- We then compare their findings to Cortex AI output in the dashboard view.
-- Note what these MISS — that's the point.
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;

-- Clear today's rule results
DELETE FROM DQ_RULE_RESULTS WHERE CHECK_DATE = CURRENT_DATE();


-- ── CHECK 1: UNIT_PRICE NOT NULL ─────────────────────────────────────────────
INSERT INTO DQ_RULE_RESULTS
    (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
     TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
SELECT
    CURRENT_DATE(),
    'UNIT_PRICE_NOT_NULL',
    FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    UNIT_PRICE, NULL, NULL,
    CASE WHEN UNIT_PRICE IS NULL THEN 'FAIL' ELSE 'PASS' END,
    CASE WHEN UNIT_PRICE IS NULL THEN 'Unit price is null' ELSE NULL END
FROM EPOS_DAILY_FACTS
WHERE TRANSACTION_DATE = CURRENT_DATE();

-- Result: ALL PASS (anomaly 1 has a price — just a wrong one. Rules can't catch this.)


-- ── CHECK 2: UNIT_PRICE HARDCODED RANGE (Global threshold — too blunt) ────────
-- A naive DQ engineer might set a global upper limit of, say, 1000 BRL per case.
-- Anomaly 1 (3100 BRL) WOULD be caught here.
-- But what if the threshold was set at 5000? Or if the spike was only 600 BRL for a cheap product?

INSERT INTO DQ_RULE_RESULTS
    (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
     TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
SELECT
    CURRENT_DATE(),
    'UNIT_PRICE_GLOBAL_RANGE_CHECK',
    FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    UNIT_PRICE, 0, 1000,
    CASE WHEN UNIT_PRICE < 0 OR UNIT_PRICE > 1000 THEN 'FAIL' ELSE 'PASS' END,
    CASE WHEN UNIT_PRICE > 1000 THEN 'Price exceeds global max of 1000 BRL' ELSE NULL END
FROM EPOS_DAILY_FACTS
WHERE TRANSACTION_DATE = CURRENT_DATE();

-- Result: Catches anomaly 1 (3100 BRL) BUT would miss a spike to 600 BRL for a 280 BRL product
-- Also: this check is hardcoded. Any global threshold will have false positives or false negatives.


-- ── CHECK 3: SALES_VOLUME_CASES RANGE ────────────────────────────────────────
-- Hard upper limit of 100 cases per outlet per day (engineer's assumption)
-- Anomaly 3 (450 cases) WOULD be caught. But what if the combo was 80 cases + 1 transaction?

INSERT INTO DQ_RULE_RESULTS
    (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
     TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
SELECT
    CURRENT_DATE(),
    'VOLUME_CASES_RANGE_CHECK',
    FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    SALES_VOLUME_CASES, 0, 100,
    CASE WHEN SALES_VOLUME_CASES < 0 OR SALES_VOLUME_CASES > 100 THEN 'FAIL' ELSE 'PASS' END,
    CASE WHEN SALES_VOLUME_CASES > 100 THEN 'Volume exceeds 100 case threshold' ELSE NULL END
FROM EPOS_DAILY_FACTS
WHERE TRANSACTION_DATE = CURRENT_DATE();

-- Result: Catches anomaly 3 (450 cases) BUT misses the real signal:
-- 450 cases in 1 transaction. Volume alone is suspicious; volume+tx_count combo is impossible.


-- ── CHECK 4: TRANSACTION_COUNT NOT NULL AND POSITIVE ─────────────────────────
INSERT INTO DQ_RULE_RESULTS
    (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
     TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
SELECT
    CURRENT_DATE(),
    'TRANSACTION_COUNT_POSITIVE',
    FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    TRANSACTION_COUNT, 1, 9999,
    CASE WHEN TRANSACTION_COUNT IS NULL OR TRANSACTION_COUNT < 1 THEN 'FAIL' ELSE 'PASS' END,
    CASE WHEN TRANSACTION_COUNT < 1 THEN 'Transaction count is zero or negative' ELSE NULL END
FROM EPOS_DAILY_FACTS
WHERE TRANSACTION_DATE = CURRENT_DATE();

-- Result: ALL PASS — anomaly 3 has tx_count = 1 which is technically valid.
-- Rules don't look at 450 cases + 1 tx TOGETHER.


-- ── CHECK 5: REGION RECORD COUNT (the silent region check attempt) ────────────
-- A data engineer who knows EAST should have data might add this check.
-- But they have to hardcode the minimum count — a brittle assumption.

INSERT INTO DQ_RULE_RESULTS
    (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
     TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
WITH today_region_counts AS (
    SELECT REGION, COUNT(*) AS today_count
    FROM EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE()
    GROUP BY REGION
),
all_regions AS (
    SELECT * FROM VALUES
        ('NORTH'), ('SOUTH'), ('EAST'), ('WEST'), ('CENTRAL')
        AS t(region)
)
SELECT
    CURRENT_DATE(),
    'REGION_MINIMUM_RECORD_COUNT',
    NULL, NULL, NULL,
    ar.region,
    CURRENT_DATE(),
    COALESCE(trc.today_count, 0),
    5,     -- hardcoded minimum: "EAST should have at least 5 records" (arbitrary)
    NULL,
    CASE WHEN COALESCE(trc.today_count, 0) < 5 THEN 'FAIL' ELSE 'PASS' END,
    CASE WHEN COALESCE(trc.today_count, 0) < 5
         THEN 'Region has fewer than 5 records today (possible silent region)'
         ELSE NULL END
FROM all_regions ar
LEFT JOIN today_region_counts trc ON ar.region = trc.region;

-- Result: Catches EAST with 0 records. BUT:
-- (a) threshold of 5 is arbitrary — what if a real slow day has 3 records?
-- (b) doesn't tell you WHY it's silent or what the historical pattern was
-- (c) Cortex will explain: "EAST averages 12 records/day, today has 0, this is a pattern break"


-- ── SUMMARY: WHAT RULES CAUGHT TODAY ─────────────────────────────────────────

SELECT
    CHECK_NAME,
    RESULT,
    COUNT(*)            AS count,
    LISTAGG(DISTINCT REGION, ', ') WITHIN GROUP (ORDER BY REGION) AS regions_affected
FROM DQ_RULE_RESULTS
WHERE CHECK_DATE = CURRENT_DATE()
GROUP BY CHECK_NAME, RESULT
ORDER BY CHECK_NAME, RESULT;

-- KEY INSIGHT TO HIGHLIGHT:
-- Rules caught: price > 1000 (anomaly 1), volume > 100 (anomaly 3), EAST count < 5 (anomaly 2)
-- Rules MISSED: combo anomaly (450 cases + 1 tx) via individual column checks
-- Rules cannot explain WHY something is anomalous — just that it crossed a threshold
-- Cortex will provide reasoning AND catch what rules miss
