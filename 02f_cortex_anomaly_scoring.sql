-- =============================================================================
-- 02f_cortex_anomaly_scoring.sql
-- Scenario 2: Cortex AI Anomaly Detection + Explanation
--
-- For each record in today's EPOS data, we:
--   1. Join to the statistical baseline to get expected ranges
--   2. Build a structured prompt with both the data AND the historical context
--   3. Ask Cortex to determine: is this anomalous? why? what type?
--   4. Parse the JSON response and store results
--
-- For the SILENT REGION anomaly, we run a separate detection query
-- since there are no rows to score — the absence IS the anomaly.
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_LLM_WH;   -- Use larger warehouse for LLM batch calls
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;

-- Clear today's Cortex scores
DELETE FROM CORTEX_ANOMALY_SCORES WHERE SCORED_DATE = CURRENT_DATE();


-- =============================================================================
-- PART A: Score today's rows against historical baseline
-- =============================================================================

INSERT INTO CORTEX_ANOMALY_SCORES (
    SCORED_DATE, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT,
    PRICE_MEAN, PRICE_STDDEV, PRICE_UPPER_FENCE,
    VOLUME_MEAN, VOLUME_STDDEV,
    REGION_7D_AVG_ROWS,
    IS_ANOMALY, ANOMALY_TYPE, CONFIDENCE, CORTEX_REASONING, MODEL_USED
)
WITH today_facts AS (
    SELECT *
    FROM EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE()
),
price_baseline AS (
    SELECT PRODUCT_CODE, REGION,
           ROLLING_MEAN      AS price_mean,
           ROLLING_STDDEV    AS price_stddev,
           UPPER_FENCE       AS price_upper_fence,
           LOWER_FENCE       AS price_lower_fence
    FROM EPOS_STAT_BASELINE
    WHERE STAT_DATE = CURRENT_DATE()
      AND METRIC = 'UNIT_PRICE'
),
volume_baseline AS (
    SELECT PRODUCT_CODE, REGION,
           ROLLING_MEAN      AS volume_mean,
           ROLLING_STDDEV    AS volume_stddev,
           UPPER_FENCE       AS volume_upper_fence
    FROM EPOS_STAT_BASELINE
    WHERE STAT_DATE = CURRENT_DATE()
      AND METRIC = 'SALES_VOLUME'
),
rowcount_baseline AS (
    SELECT PRODUCT_CODE, REGION,
           ROLLING_MEAN      AS rowcount_mean,
           LOWER_FENCE       AS rowcount_lower_fence
    FROM EPOS_STAT_BASELINE
    WHERE STAT_DATE = CURRENT_DATE()
      AND METRIC = 'ROW_COUNT'
),
enriched AS (
    SELECT
        f.*,
        COALESCE(pb.price_mean, 0)           AS price_mean,
        COALESCE(pb.price_stddev, 0)         AS price_stddev,
        COALESCE(pb.price_upper_fence, 99999) AS price_upper_fence,
        COALESCE(pb.price_lower_fence, 0)    AS price_lower_fence,
        COALESCE(vb.volume_mean, 0)          AS volume_mean,
        COALESCE(vb.volume_stddev, 0)        AS volume_stddev,
        COALESCE(vb.volume_upper_fence, 99999) AS volume_upper_fence,
        COALESCE(rb.rowcount_mean, 10)       AS rowcount_mean,
        -- Price Z-score (how many stddevs from mean)
        CASE WHEN COALESCE(pb.price_stddev, 0) > 0
             THEN ABS(f.UNIT_PRICE - pb.price_mean) / pb.price_stddev
             ELSE 0 END                      AS price_z_score,
        -- Volume Z-score
        CASE WHEN COALESCE(vb.volume_stddev, 0) > 0
             THEN ABS(f.SALES_VOLUME_CASES - vb.volume_mean) / vb.volume_stddev
             ELSE 0 END                      AS volume_z_score
    FROM today_facts f
    LEFT JOIN price_baseline  pb ON f.PRODUCT_CODE = pb.PRODUCT_CODE AND f.REGION = pb.REGION
    LEFT JOIN volume_baseline vb ON f.PRODUCT_CODE = vb.PRODUCT_CODE AND f.REGION = vb.REGION
    LEFT JOIN rowcount_baseline rb ON f.PRODUCT_CODE = rb.PRODUCT_CODE AND f.REGION = rb.REGION
),
-- Build Cortex prompt per record
scored AS (
    SELECT
        e.*,
        -- Construct a structured prompt for Cortex
        'You are a data quality analyst for an EPOS (point-of-sale) data platform at a beverages company. '
        || 'Your job is to detect anomalies in daily sales data by comparing today''s values against the historical baseline. '
        || 'Respond ONLY in valid JSON with this exact structure: '
        || '{"is_anomaly": true/false, "anomaly_type": "PRICE_SPIKE|VOLUME_ANOMALY|COMBO_ANOMALY|NONE", "confidence": "HIGH|MEDIUM|LOW", "reasoning": "explanation in 2-3 sentences"} '
        || '\n\nDATA RECORD TO ANALYSE:'
        || '\n  Product: '          || e.PRODUCT_CODE
        || '\n  Region: '           || e.REGION
        || '\n  Channel: '          || COALESCE(e.CHANNEL, 'UNKNOWN')
        || '\n  Unit Price (BRL): ' || e.UNIT_PRICE::VARCHAR
        || '\n  Volume (cases): '   || e.SALES_VOLUME_CASES::VARCHAR
        || '\n  Sales Value (BRL): '|| e.SALES_VALUE_BRL::VARCHAR
        || '\n  Transaction Count: '|| e.TRANSACTION_COUNT::VARCHAR
        || '\n\n7-DAY HISTORICAL BASELINE FOR THIS PRODUCT+REGION:'
        || '\n  Price — Mean: '     || ROUND(e.price_mean, 2)::VARCHAR
        || '  StdDev: '             || ROUND(e.price_stddev, 2)::VARCHAR
        || '  Upper Fence (Tukey): '|| ROUND(e.price_upper_fence, 2)::VARCHAR
        || '\n  Volume — Mean: '    || ROUND(e.volume_mean, 2)::VARCHAR
        || '  StdDev: '             || ROUND(e.volume_stddev, 2)::VARCHAR
        || '  Upper Fence: '        || ROUND(e.volume_upper_fence, 2)::VARCHAR
        || '\n  Price Z-score: '    || ROUND(e.price_z_score, 2)::VARCHAR
        || '  Volume Z-score: '     || ROUND(e.volume_z_score, 2)::VARCHAR
        || '\n\nANALYSIS INSTRUCTIONS: '
        || 'Check if unit_price is far above the historical upper fence. '
        || 'Check if volume is far above the historical upper fence. '
        || 'Check if the combination of high volume with very low transaction count (e.g. 1 transaction for hundreds of cases) is physically plausible for a trade outlet. '
        || 'A single transaction exceeding 50 cases at an on-trade outlet is implausible. '
        || 'Classify as COMBO_ANOMALY if multiple metrics are collectively suspicious even if individually within range.'
        AS cortex_prompt
    FROM enriched e
)
SELECT
    CURRENT_DATE(),
    s.FACT_ID,
    s.OUTLET_CODE,
    s.PRODUCT_CODE,
    s.REGION,
    s.TRANSACTION_DATE,
    s.UNIT_PRICE,
    s.SALES_VOLUME_CASES,
    s.SALES_VALUE_BRL,
    s.TRANSACTION_COUNT,
    s.price_mean,
    s.price_stddev,
    s.price_upper_fence,
    s.volume_mean,
    s.volume_stddev,
    s.rowcount_mean,
    -- Parse Cortex JSON response
    TRY_PARSE_JSON(
        SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', s.cortex_prompt)
    ):is_anomaly::BOOLEAN                               AS is_anomaly,
    TRY_PARSE_JSON(
        SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', s.cortex_prompt)
    ):anomaly_type::VARCHAR                             AS anomaly_type,
    TRY_PARSE_JSON(
        SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', s.cortex_prompt)
    ):confidence::VARCHAR                               AS confidence,
    TRY_PARSE_JSON(
        SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', s.cortex_prompt)
    ):reasoning::VARCHAR                                AS cortex_reasoning,
    'mistral-7b'
FROM scored s;

-- NOTE: The 4x COMPLETE() calls above can be reduced to 1 by materialising
-- the response first. Production pattern shown below in Part B comment.

-- =============================================================================
-- PART B: Silent Region Detection (no rows = no records to score)
-- This is a purely structural check Cortex reasons over differently
-- =============================================================================

WITH expected_regions AS (
    SELECT * FROM VALUES
        ('NORTH'), ('SOUTH'), ('EAST'), ('WEST'), ('CENTRAL')
        AS t(region)
),
today_region_counts AS (
    SELECT REGION, COUNT(*) AS today_count
    FROM EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE()
    GROUP BY REGION
),
rowcount_baselines AS (
    SELECT REGION,
           AVG(ROLLING_MEAN) AS historical_avg_rows
    FROM EPOS_STAT_BASELINE
    WHERE STAT_DATE = CURRENT_DATE()
      AND METRIC = 'ROW_COUNT'
    GROUP BY REGION
),
silent_regions AS (
    SELECT
        er.region,
        COALESCE(trc.today_count, 0)     AS today_row_count,
        COALESCE(rb.historical_avg_rows, 10) AS historical_avg_rows
    FROM expected_regions er
    LEFT JOIN today_region_counts trc ON er.region = trc.region
    LEFT JOIN rowcount_baselines  rb  ON er.region = rb.region
    WHERE COALESCE(trc.today_count, 0) < COALESCE(rb.historical_avg_rows, 10) * 0.3
    -- Flag if today's count is less than 30% of historical average
)
INSERT INTO CORTEX_ANOMALY_SCORES (
    SCORED_DATE, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
    UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT,
    REGION_7D_AVG_ROWS,
    IS_ANOMALY, ANOMALY_TYPE, CONFIDENCE, CORTEX_REASONING, MODEL_USED
)
SELECT
    CURRENT_DATE(),
    -1,           -- No FACT_ID for absence anomalies
    NULL, NULL,
    sr.region,
    CURRENT_DATE(),
    NULL, NULL, NULL, NULL,
    sr.historical_avg_rows,
    TRUE,
    'SILENT_REGION',
    'HIGH',
    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-7b',
        'You are a data quality analyst. A regional data silence has been detected. '
        || 'Provide a 2-3 sentence explanation of why this is anomalous and what business impact it could have. '
        || '\nSituation: Region ' || sr.region || ' has ' || sr.today_row_count::VARCHAR
        || ' records today. '
        || 'The 7-day historical average is ' || ROUND(sr.historical_avg_rows, 1)::VARCHAR
        || ' records per day. '
        || 'This represents a ' || ROUND((1 - sr.today_row_count / NULLIF(sr.historical_avg_rows, 0)) * 100, 0)::VARCHAR
        || '% drop from normal. '
        || 'Common root causes include: pipeline failure, blob trigger not firing, source data not landing, '
        || 'or an upstream ETL job failing silently. '
        || 'Respond in 2-3 sentences, business-friendly language.'
    ),
    'mistral-7b'
FROM silent_regions sr;


-- =============================================================================
-- QUICK SUMMARY
-- =============================================================================

SELECT
    IS_ANOMALY,
    ANOMALY_TYPE,
    CONFIDENCE,
    COUNT(*) AS record_count
FROM CORTEX_ANOMALY_SCORES
WHERE SCORED_DATE = CURRENT_DATE()
GROUP BY 1, 2, 3
ORDER BY IS_ANOMALY DESC, COUNT(*) DESC;
