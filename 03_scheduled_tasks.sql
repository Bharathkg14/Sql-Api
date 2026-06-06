-- =============================================================================
-- 03_scheduled_tasks.sql
-- Orchestration: Snowflake Tasks to run both pipelines daily
--
-- Task DAG:
--
--   [ROOT TASK: daily_anomaly_pipeline]    9:00 AM UTC daily
--         │
--         ├─→ [task_compute_baselines]     Recompute rolling stats
--         │         │
--         │         └─→ [task_rule_dq]    Run rule-based DQ checks
--         │                   │
--         │                   └─→ [task_cortex_scoring]  Cortex AI scoring
--         │                               │
--         │                               └─→ [task_refresh_views]  Refresh dashboard
--         │
--         └─→ [task_metadata_qa_log]      Optionally log nightly Q&A audit
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;


-- ── TASK 1: ROOT — Triggers daily pipeline at 9 AM UTC ───────────────────────

CREATE OR REPLACE TASK TASK_DAILY_ANOMALY_ROOT
    WAREHOUSE   = CORTEX_WH
    SCHEDULE    = 'USING CRON 0 9 * * * UTC'
    COMMENT     = 'Root task — triggers daily Cortex anomaly detection pipeline'
AS
    -- Lightweight: just a flag to trigger the DAG
    SELECT CURRENT_TIMESTAMP() AS pipeline_started;


-- ── TASK 2: Compute statistical baselines ────────────────────────────────────

CREATE OR REPLACE TASK TASK_COMPUTE_BASELINES
    WAREHOUSE   = CORTEX_WH
    AFTER       TASK_DAILY_ANOMALY_ROOT
    COMMENT     = 'Recompute rolling 7-day stats for all product+region combinations'
AS
EXECUTE IMMEDIATE $$
    -- Truncate and rebuild
    TRUNCATE TABLE CORTEX_AI_LAB.EPOS_DATA.EPOS_STAT_BASELINE;

    INSERT INTO CORTEX_AI_LAB.EPOS_DATA.EPOS_STAT_BASELINE
        (STAT_DATE, PRODUCT_CODE, REGION, METRIC,
         ROLLING_MEAN, ROLLING_STDDEV, ROLLING_MIN, ROLLING_MAX,
         ROLLING_P25, ROLLING_P75, IQR, LOWER_FENCE, UPPER_FENCE, WINDOW_DAYS)
    WITH daily_agg AS (
        SELECT
            TRANSACTION_DATE, PRODUCT_CODE, REGION,
            AVG(UNIT_PRICE)         AS daily_avg_price,
            SUM(SALES_VOLUME_CASES) AS daily_total_volume,
            COUNT(*)                AS daily_row_count
        FROM CORTEX_AI_LAB.EPOS_DATA.EPOS_DAILY_FACTS
        WHERE TRANSACTION_DATE < CURRENT_DATE()
        GROUP BY 1, 2, 3
    ),
    windowed AS (
        SELECT
            TRANSACTION_DATE, PRODUCT_CODE, REGION,
            AVG(daily_avg_price)     OVER w7 AS price_mean,
            STDDEV(daily_avg_price)  OVER w7 AS price_stddev,
            MIN(daily_avg_price)     OVER w7 AS price_min,
            MAX(daily_avg_price)     OVER w7 AS price_max,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY daily_avg_price) OVER w7 AS price_p25,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY daily_avg_price) OVER w7 AS price_p75,
            AVG(daily_total_volume)  OVER w7 AS volume_mean,
            STDDEV(daily_total_volume) OVER w7 AS volume_stddev,
            MIN(daily_total_volume)  OVER w7 AS volume_min,
            MAX(daily_total_volume)  OVER w7 AS volume_max,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY daily_total_volume) OVER w7 AS volume_p25,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY daily_total_volume) OVER w7 AS volume_p75,
            AVG(daily_row_count)     OVER w7 AS rowcount_mean,
            STDDEV(daily_row_count)  OVER w7 AS rowcount_stddev
        FROM daily_agg
        WINDOW w7 AS (
            PARTITION BY PRODUCT_CODE, REGION
            ORDER BY TRANSACTION_DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )
    ),
    latest AS (
        SELECT * FROM windowed
        WHERE TRANSACTION_DATE = (SELECT MAX(TRANSACTION_DATE) FROM daily_agg)
    )
    SELECT CURRENT_DATE(), PRODUCT_CODE, REGION, 'UNIT_PRICE',
           price_mean, price_stddev, price_min, price_max, price_p25, price_p75,
           price_p75 - price_p25,
           price_p25 - 1.5*(price_p75 - price_p25),
           price_p75 + 1.5*(price_p75 - price_p25), 7
    FROM latest
    UNION ALL
    SELECT CURRENT_DATE(), PRODUCT_CODE, REGION, 'SALES_VOLUME',
           volume_mean, volume_stddev, volume_min, volume_max, volume_p25, volume_p75,
           volume_p75 - volume_p25,
           volume_p25 - 1.5*(volume_p75 - volume_p25),
           volume_p75 + 1.5*(volume_p75 - volume_p25), 7
    FROM latest
    UNION ALL
    SELECT CURRENT_DATE(), PRODUCT_CODE, REGION, 'ROW_COUNT',
           rowcount_mean, rowcount_stddev, NULL, NULL, NULL, NULL, NULL,
           rowcount_mean - 2*rowcount_stddev,
           rowcount_mean + 2*rowcount_stddev, 7
    FROM latest;
$$;


-- ── TASK 3: Rule-based DQ ────────────────────────────────────────────────────

CREATE OR REPLACE TASK TASK_RULE_DQ_CHECKS
    WAREHOUSE   = CORTEX_WH
    AFTER       TASK_COMPUTE_BASELINES
    COMMENT     = 'Run traditional threshold-based DQ checks for today'
AS
EXECUTE IMMEDIATE $$
    DELETE FROM CORTEX_AI_LAB.EPOS_DATA.DQ_RULE_RESULTS WHERE CHECK_DATE = CURRENT_DATE();

    -- NOT NULL check
    INSERT INTO CORTEX_AI_LAB.EPOS_DATA.DQ_RULE_RESULTS
        (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
         TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
    SELECT
        CURRENT_DATE(), 'UNIT_PRICE_NOT_NULL',
        FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
        UNIT_PRICE, NULL, NULL,
        CASE WHEN UNIT_PRICE IS NULL THEN 'FAIL' ELSE 'PASS' END,
        CASE WHEN UNIT_PRICE IS NULL THEN 'Unit price is null' ELSE NULL END
    FROM CORTEX_AI_LAB.EPOS_DATA.EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE();

    -- Price range check
    INSERT INTO CORTEX_AI_LAB.EPOS_DATA.DQ_RULE_RESULTS
        (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
         TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
    SELECT
        CURRENT_DATE(), 'UNIT_PRICE_GLOBAL_RANGE_CHECK',
        FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
        UNIT_PRICE, 0, 1000,
        CASE WHEN UNIT_PRICE > 1000 THEN 'FAIL' ELSE 'PASS' END,
        CASE WHEN UNIT_PRICE > 1000 THEN 'Price exceeds 1000 BRL global max' ELSE NULL END
    FROM CORTEX_AI_LAB.EPOS_DATA.EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE();

    -- Volume range check
    INSERT INTO CORTEX_AI_LAB.EPOS_DATA.DQ_RULE_RESULTS
        (CHECK_DATE, CHECK_NAME, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION,
         TRANSACTION_DATE, METRIC_VALUE, THRESHOLD_MIN, THRESHOLD_MAX, RESULT, FAIL_REASON)
    SELECT
        CURRENT_DATE(), 'VOLUME_CASES_RANGE_CHECK',
        FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
        SALES_VOLUME_CASES, 0, 100,
        CASE WHEN SALES_VOLUME_CASES > 100 THEN 'FAIL' ELSE 'PASS' END,
        CASE WHEN SALES_VOLUME_CASES > 100 THEN 'Volume exceeds 100 case threshold' ELSE NULL END
    FROM CORTEX_AI_LAB.EPOS_DATA.EPOS_DAILY_FACTS
    WHERE TRANSACTION_DATE = CURRENT_DATE();
$$;


-- ── TASK 4: Cortex AI Scoring ─────────────────────────────────────────────────

CREATE OR REPLACE TASK TASK_CORTEX_ANOMALY_SCORE
    WAREHOUSE   = CORTEX_LLM_WH   -- larger warehouse for LLM calls
    AFTER       TASK_RULE_DQ_CHECKS
    COMMENT     = 'Cortex AI anomaly scoring for today — row-level and silent region'
AS
    -- In production: call a stored procedure that encapsulates 02f logic
    -- Stored procedure pattern shown below
    CALL CORTEX_AI_LAB.EPOS_DATA.SP_CORTEX_ANOMALY_SCORING();


-- ── TASK 5: Refresh Dashboard Views ──────────────────────────────────────────

CREATE OR REPLACE TASK TASK_REFRESH_DASHBOARD
    WAREHOUSE   = CORTEX_WH
    AFTER       TASK_CORTEX_ANOMALY_SCORE
    COMMENT     = 'Refresh any dynamic tables or alert on new CORTEX_ONLY findings'
AS
EXECUTE IMMEDIATE $$
    -- Alert: Insert into alert log if there are Cortex-only findings today
    INSERT INTO CORTEX_AI_LAB.DQ_RESULTS.ALERT_LOG
        (ALERT_DATE, ALERT_TYPE, DETAIL_COUNT, SUMMARY)
    SELECT
        CURRENT_DATE(),
        'CORTEX_ONLY_ANOMALY',
        COUNT(*),
        'Cortex detected ' || COUNT(*)::VARCHAR
        || ' anomalies that rule-based checks missed today. Review V_ANOMALY_COMPARISON.'
    FROM CORTEX_AI_LAB.EPOS_DATA.V_ANOMALY_COMPARISON
    WHERE detection_outcome = 'CORTEX_ONLY'
    HAVING COUNT(*) > 0;
$$;


-- ── ALERT LOG TABLE (needed by Task 5) ───────────────────────────────────────

USE SCHEMA CORTEX_AI_LAB.DQ_RESULTS;

CREATE TABLE IF NOT EXISTS ALERT_LOG (
    ALERT_ID    NUMBER AUTOINCREMENT PRIMARY KEY,
    ALERT_DATE  DATE,
    ALERT_TYPE  VARCHAR(200),
    DETAIL_COUNT NUMBER,
    SUMMARY     VARCHAR(2000),
    CREATED_AT  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);


-- ── STORED PROCEDURE for Cortex Scoring (called by Task 4) ───────────────────

USE SCHEMA CORTEX_AI_LAB.EPOS_DATA;

CREATE OR REPLACE PROCEDURE SP_CORTEX_ANOMALY_SCORING()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    -- Clear today
    DELETE FROM CORTEX_AI_LAB.EPOS_DATA.CORTEX_ANOMALY_SCORES
    WHERE SCORED_DATE = CURRENT_DATE();

    -- Row-level scoring (references 02f logic)
    INSERT INTO CORTEX_AI_LAB.EPOS_DATA.CORTEX_ANOMALY_SCORES (
        SCORED_DATE, FACT_ID, OUTLET_CODE, PRODUCT_CODE, REGION, TRANSACTION_DATE,
        UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT,
        PRICE_MEAN, PRICE_STDDEV, PRICE_UPPER_FENCE,
        VOLUME_MEAN, VOLUME_STDDEV, REGION_7D_AVG_ROWS,
        IS_ANOMALY, ANOMALY_TYPE, CONFIDENCE, CORTEX_REASONING, MODEL_USED
    )
    WITH today_facts AS (
        SELECT * FROM EPOS_DAILY_FACTS WHERE TRANSACTION_DATE = CURRENT_DATE()
    ),
    price_b AS (
        SELECT PRODUCT_CODE, REGION, ROLLING_MEAN AS pm, ROLLING_STDDEV AS psd, UPPER_FENCE AS puf
        FROM EPOS_STAT_BASELINE WHERE STAT_DATE = CURRENT_DATE() AND METRIC = 'UNIT_PRICE'
    ),
    vol_b AS (
        SELECT PRODUCT_CODE, REGION, ROLLING_MEAN AS vm, ROLLING_STDDEV AS vsd, UPPER_FENCE AS vuf
        FROM EPOS_STAT_BASELINE WHERE STAT_DATE = CURRENT_DATE() AND METRIC = 'SALES_VOLUME'
    ),
    rc_b AS (
        SELECT PRODUCT_CODE, REGION, ROLLING_MEAN AS rcm
        FROM EPOS_STAT_BASELINE WHERE STAT_DATE = CURRENT_DATE() AND METRIC = 'ROW_COUNT'
    ),
    enriched AS (
        SELECT f.*,
            COALESCE(pb.pm, 0) AS price_mean, COALESCE(pb.psd, 0) AS price_stddev,
            COALESCE(pb.puf, 99999) AS price_upper_fence,
            COALESCE(vb.vm, 0) AS volume_mean, COALESCE(vb.vsd, 0) AS volume_stddev,
            COALESCE(rb.rcm, 10) AS rowcount_mean
        FROM today_facts f
        LEFT JOIN price_b pb ON f.PRODUCT_CODE = pb.PRODUCT_CODE AND f.REGION = pb.REGION
        LEFT JOIN vol_b   vb ON f.PRODUCT_CODE = vb.PRODUCT_CODE AND f.REGION = vb.REGION
        LEFT JOIN rc_b    rb ON f.PRODUCT_CODE = rb.PRODUCT_CODE AND f.REGION = rb.REGION
    ),
    with_prompt AS (
        SELECT e.*,
            'You are a data quality analyst. Respond ONLY in valid JSON: '
            || '{"is_anomaly": true/false, "anomaly_type": "PRICE_SPIKE|VOLUME_ANOMALY|COMBO_ANOMALY|NONE", "confidence": "HIGH|MEDIUM|LOW", "reasoning": "2 sentences"} '
            || 'Product: ' || e.PRODUCT_CODE || ' Region: ' || e.REGION
            || ' Price: ' || e.UNIT_PRICE::VARCHAR || ' (7d mean: ' || ROUND(e.price_mean,2)::VARCHAR || ', upper fence: ' || ROUND(e.price_upper_fence,2)::VARCHAR || ')'
            || ' Volume: ' || e.SALES_VOLUME_CASES::VARCHAR || ' (7d mean: ' || ROUND(e.volume_mean,2)::VARCHAR || ')'
            || ' Tx count: ' || e.TRANSACTION_COUNT::VARCHAR
            || ' Flag COMBO_ANOMALY if volume>50 AND tx_count=1 for on-trade outlet.' AS prompt
        FROM enriched e
    ),
    scored AS (
        SELECT e.*,
            TRY_PARSE_JSON(SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', wp.prompt)) AS resp
        FROM with_prompt wp
        JOIN enriched e ON wp.FACT_ID = e.FACT_ID
    )
    SELECT CURRENT_DATE(), s.FACT_ID, s.OUTLET_CODE, s.PRODUCT_CODE, s.REGION, s.TRANSACTION_DATE,
           s.UNIT_PRICE, s.SALES_VOLUME_CASES, s.SALES_VALUE_BRL, s.TRANSACTION_COUNT,
           s.price_mean, s.price_stddev, s.price_upper_fence,
           s.volume_mean, s.volume_stddev, s.rowcount_mean,
           s.resp:is_anomaly::BOOLEAN, s.resp:anomaly_type::VARCHAR,
           s.resp:confidence::VARCHAR, s.resp:reasoning::VARCHAR, 'mistral-7b'
    FROM scored s;

    RETURN 'Cortex anomaly scoring complete for ' || CURRENT_DATE()::VARCHAR;
END;
$$;


-- ── START / RESUME TASKS ─────────────────────────────────────────────────────
-- Tasks are created SUSPENDED by default. Resume when ready to go live.

-- ALTER TASK TASK_REFRESH_DASHBOARD      RESUME;
-- ALTER TASK TASK_CORTEX_ANOMALY_SCORE   RESUME;
-- ALTER TASK TASK_RULE_DQ_CHECKS         RESUME;
-- ALTER TASK TASK_COMPUTE_BASELINES      RESUME;
-- ALTER TASK TASK_DAILY_ANOMALY_ROOT     RESUME;   -- Resume root LAST

-- To manually trigger the full DAG:
-- EXECUTE TASK TASK_DAILY_ANOMALY_ROOT;

-- To check task run history:
-- SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
--     SCHEDULED_TIME_RANGE_START => DATEADD(day, -1, CURRENT_TIMESTAMP()),
--     RESULT_LIMIT => 20
-- ));
