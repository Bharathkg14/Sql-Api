-- =============================================================================
-- 02g_anomaly_dashboard_view.sql
-- Scenario 2: Unified Dashboard View — Rules vs Cortex
--
-- This is the payoff view. Side-by-side comparison of:
--   - What traditional rule-based DQ caught (and missed)
--   - What Cortex AI caught (including what rules couldn't see)
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;


-- ── VIEW: SIDE-BY-SIDE COMPARISON ────────────────────────────────────────────

CREATE OR REPLACE VIEW V_ANOMALY_COMPARISON AS
WITH cortex_findings AS (
    SELECT
        cas.REGION,
        cas.PRODUCT_CODE,
        cas.OUTLET_CODE,
        cas.TRANSACTION_DATE,
        cas.UNIT_PRICE,
        cas.SALES_VOLUME_CASES,
        cas.TRANSACTION_COUNT,
        cas.IS_ANOMALY           AS cortex_flagged,
        cas.ANOMALY_TYPE         AS cortex_anomaly_type,
        cas.CONFIDENCE           AS cortex_confidence,
        REPLACE(cas.CORTEX_REASONING, '"', '')  AS cortex_reasoning,
        cas.PRICE_MEAN,
        cas.PRICE_UPPER_FENCE,
        cas.VOLUME_MEAN
    FROM CORTEX_ANOMALY_SCORES cas
    WHERE cas.SCORED_DATE = CURRENT_DATE()
),
rule_findings AS (
    -- Aggregate rule results: did ANY rule fail for this fact_id?
    SELECT
        dqr.FACT_ID,
        dqr.REGION,
        dqr.PRODUCT_CODE,
        dqr.OUTLET_CODE,
        dqr.TRANSACTION_DATE,
        MAX(CASE WHEN dqr.RESULT = 'FAIL' THEN 1 ELSE 0 END)::BOOLEAN    AS rules_flagged,
        LISTAGG(CASE WHEN dqr.RESULT = 'FAIL' THEN dqr.CHECK_NAME END, ' | ')
            WITHIN GROUP (ORDER BY dqr.CHECK_NAME)                        AS failed_rule_names,
        LISTAGG(CASE WHEN dqr.RESULT = 'FAIL' THEN dqr.FAIL_REASON END, ' | ')
            WITHIN GROUP (ORDER BY dqr.CHECK_NAME)                        AS failed_rule_reasons
    FROM DQ_RULE_RESULTS dqr
    WHERE dqr.CHECK_DATE = CURRENT_DATE()
      AND dqr.FACT_ID IS NOT NULL
    GROUP BY 1, 2, 3, 4, 5
)
SELECT
    COALESCE(cf.REGION, rf.REGION)           AS region,
    COALESCE(cf.PRODUCT_CODE, rf.PRODUCT_CODE) AS product_code,
    COALESCE(cf.OUTLET_CODE, rf.OUTLET_CODE) AS outlet_code,
    COALESCE(cf.TRANSACTION_DATE, rf.TRANSACTION_DATE) AS transaction_date,
    cf.UNIT_PRICE,
    cf.SALES_VOLUME_CASES,
    cf.TRANSACTION_COUNT,
    cf.PRICE_MEAN,
    cf.PRICE_UPPER_FENCE,
    cf.VOLUME_MEAN,
    -- RULE-BASED FINDINGS
    COALESCE(rf.rules_flagged, FALSE)        AS rules_flagged,
    rf.failed_rule_names,
    rf.failed_rule_reasons,
    -- CORTEX AI FINDINGS
    COALESCE(cf.cortex_flagged, FALSE)       AS cortex_flagged,
    cf.cortex_anomaly_type,
    cf.cortex_confidence,
    cf.cortex_reasoning,
    -- DETECTION OUTCOME CLASSIFICATION
    CASE
        WHEN COALESCE(rf.rules_flagged, FALSE) = TRUE
         AND COALESCE(cf.cortex_flagged, FALSE) = TRUE
        THEN 'BOTH_DETECTED'
        WHEN COALESCE(rf.rules_flagged, FALSE) = FALSE
         AND COALESCE(cf.cortex_flagged, FALSE) = TRUE
        THEN 'CORTEX_ONLY'          -- ← These are the cases rules missed
        WHEN COALESCE(rf.rules_flagged, FALSE) = TRUE
         AND COALESCE(cf.cortex_flagged, FALSE) = FALSE
        THEN 'RULES_ONLY'           -- ← False positives from rules
        ELSE 'NO_ANOMALY'
    END AS detection_outcome
FROM cortex_findings cf
FULL OUTER JOIN rule_findings rf
    ON cf.OUTLET_CODE    = rf.OUTLET_CODE
   AND cf.PRODUCT_CODE   = rf.PRODUCT_CODE
   AND cf.TRANSACTION_DATE = rf.TRANSACTION_DATE;


-- ── VIEW: SILENT REGION SUMMARY ──────────────────────────────────────────────

CREATE OR REPLACE VIEW V_SILENT_REGION_ALERTS AS
SELECT
    cas.REGION,
    cas.TRANSACTION_DATE,
    cas.REGION_7D_AVG_ROWS          AS historical_avg_daily_records,
    0                               AS today_record_count,
    cas.ANOMALY_TYPE,
    cas.CONFIDENCE,
    REPLACE(cas.CORTEX_REASONING, '"', '') AS cortex_explanation,
    -- Check if rule-based check also caught this
    EXISTS (
        SELECT 1 FROM DQ_RULE_RESULTS dqr
        WHERE dqr.CHECK_DATE = CURRENT_DATE()
          AND dqr.CHECK_NAME = 'REGION_MINIMUM_RECORD_COUNT'
          AND dqr.REGION = cas.REGION
          AND dqr.RESULT = 'FAIL'
    ) AS also_caught_by_rules
FROM CORTEX_ANOMALY_SCORES cas
WHERE cas.SCORED_DATE   = CURRENT_DATE()
  AND cas.ANOMALY_TYPE  = 'SILENT_REGION';


-- =============================================================================
-- EXECUTE THE COMPARISON REPORTS
-- =============================================================================

-- ── REPORT 1: Full anomaly comparison ────────────────────────────────────────
SELECT
    DETECTION_OUTCOME,
    COUNT(*)          AS record_count,
    LISTAGG(DISTINCT REGION || ':' || COALESCE(PRODUCT_CODE, 'ALL'), ' | ')
        WITHIN GROUP (ORDER BY REGION) AS examples
FROM V_ANOMALY_COMPARISON
WHERE detection_outcome != 'NO_ANOMALY'
GROUP BY DETECTION_OUTCOME
ORDER BY CASE detection_outcome
    WHEN 'CORTEX_ONLY'   THEN 1   -- most important: what rules missed
    WHEN 'BOTH_DETECTED' THEN 2
    WHEN 'RULES_ONLY'    THEN 3
    ELSE 4 END;


-- ── REPORT 2: Detail for Cortex-only finds (the key insight) ─────────────────
SELECT
    region,
    product_code,
    outlet_code,
    unit_price,
    ROUND(price_mean, 2)         AS price_7d_mean,
    ROUND(price_upper_fence, 2)  AS price_upper_fence,
    sales_volume_cases,
    ROUND(volume_mean, 2)        AS volume_7d_mean,
    transaction_count,
    cortex_anomaly_type,
    cortex_confidence,
    cortex_reasoning
FROM V_ANOMALY_COMPARISON
WHERE detection_outcome = 'CORTEX_ONLY'
ORDER BY cortex_confidence, region;


-- ── REPORT 3: Silent region alerts with Cortex explanations ──────────────────
SELECT
    REGION,
    HISTORICAL_AVG_DAILY_RECORDS,
    TODAY_RECORD_COUNT,
    ALSO_CAUGHT_BY_RULES,
    CORTEX_EXPLANATION
FROM V_SILENT_REGION_ALERTS;


-- ── REPORT 4: Full scored record detail (for debugging / deep dive) ───────────
SELECT
    region,
    product_code,
    outlet_code,
    unit_price,
    sales_volume_cases,
    transaction_count,
    rules_flagged,
    failed_rule_names,
    cortex_flagged,
    cortex_anomaly_type,
    cortex_confidence,
    LEFT(cortex_reasoning, 200)  AS cortex_reasoning_preview,
    detection_outcome
FROM V_ANOMALY_COMPARISON
ORDER BY detection_outcome, region, product_code;
