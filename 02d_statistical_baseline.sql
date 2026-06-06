-- =============================================================================
-- 02d_statistical_baseline.sql
-- Scenario 2: Compute rolling 7-day statistical baselines per product + region
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;


-- Truncate and rebuild baselines (idempotent)
TRUNCATE TABLE EPOS_STAT_BASELINE;

INSERT INTO EPOS_STAT_BASELINE
    (STAT_DATE, PRODUCT_CODE, REGION, METRIC,
     ROLLING_MEAN, ROLLING_STDDEV, ROLLING_MIN, ROLLING_MAX,
     ROLLING_P25, ROLLING_P75, IQR, LOWER_FENCE, UPPER_FENCE, WINDOW_DAYS)

WITH base AS (
    SELECT
        TRANSACTION_DATE,
        PRODUCT_CODE,
        REGION,
        UNIT_PRICE,
        SALES_VOLUME_CASES,
        SALES_VALUE_BRL,
        TRANSACTION_COUNT
    FROM EPOS_DAILY_FACTS
    -- Exclude today's data from baseline (we're scoring today against history)
    WHERE TRANSACTION_DATE < CURRENT_DATE()
),
daily_agg AS (
    -- Aggregate to daily level first to avoid outlet-level noise
    SELECT
        TRANSACTION_DATE,
        PRODUCT_CODE,
        REGION,
        AVG(UNIT_PRICE)         AS daily_avg_price,
        SUM(SALES_VOLUME_CASES) AS daily_total_volume,
        SUM(SALES_VALUE_BRL)    AS daily_total_value,
        SUM(TRANSACTION_COUNT)  AS daily_tx_count,
        COUNT(*)                AS daily_row_count
    FROM base
    GROUP BY 1, 2, 3
),
windowed AS (
    -- Compute rolling 7-day stats using window function
    SELECT
        TRANSACTION_DATE,
        PRODUCT_CODE,
        REGION,
        -- PRICE stats
        AVG(daily_avg_price)   OVER w7  AS price_mean,
        STDDEV(daily_avg_price) OVER w7  AS price_stddev,
        MIN(daily_avg_price)   OVER w7  AS price_min,
        MAX(daily_avg_price)   OVER w7  AS price_max,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY daily_avg_price)
            OVER w7                      AS price_p25,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY daily_avg_price)
            OVER w7                      AS price_p75,
        -- VOLUME stats
        AVG(daily_total_volume) OVER w7  AS volume_mean,
        STDDEV(daily_total_volume) OVER w7 AS volume_stddev,
        MIN(daily_total_volume) OVER w7  AS volume_min,
        MAX(daily_total_volume) OVER w7  AS volume_max,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY daily_total_volume)
            OVER w7                      AS volume_p25,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY daily_total_volume)
            OVER w7                      AS volume_p75,
        -- ROW COUNT (for silent region detection)
        AVG(daily_row_count)   OVER w7   AS rowcount_mean,
        STDDEV(daily_row_count) OVER w7   AS rowcount_stddev
    FROM daily_agg
    WINDOW w7 AS (
        PARTITION BY PRODUCT_CODE, REGION
        ORDER BY TRANSACTION_DATE
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW   -- 7-day window
    )
),
latest_stats AS (
    -- Take the most recent window (last complete day before today)
    SELECT *
    FROM windowed
    WHERE TRANSACTION_DATE = (SELECT MAX(TRANSACTION_DATE) FROM daily_agg)
)
-- Pivot into long format for EPOS_STAT_BASELINE
SELECT
    CURRENT_DATE()  AS stat_date,
    PRODUCT_CODE,
    REGION,
    'UNIT_PRICE'    AS metric,
    price_mean, price_stddev, price_min, price_max,
    price_p25, price_p75,
    price_p75 - price_p25                          AS iqr,
    price_p25 - 1.5 * (price_p75 - price_p25)     AS lower_fence,
    price_p75 + 1.5 * (price_p75 - price_p25)     AS upper_fence,
    7
FROM latest_stats

UNION ALL

SELECT
    CURRENT_DATE(),
    PRODUCT_CODE,
    REGION,
    'SALES_VOLUME',
    volume_mean, volume_stddev, volume_min, volume_max,
    volume_p25, volume_p75,
    volume_p75 - volume_p25,
    volume_p25 - 1.5 * (volume_p75 - volume_p25),
    volume_p75 + 1.5 * (volume_p75 - volume_p25),
    7
FROM latest_stats

UNION ALL

SELECT
    CURRENT_DATE(),
    PRODUCT_CODE,
    REGION,
    'ROW_COUNT',
    rowcount_mean, rowcount_stddev, NULL, NULL,
    NULL, NULL, NULL,
    rowcount_mean - 2 * rowcount_stddev,    -- lower fence: mean - 2σ
    rowcount_mean + 2 * rowcount_stddev,
    7
FROM latest_stats;


-- Verify
SELECT METRIC, COUNT(*) AS combos,
       ROUND(AVG(ROLLING_MEAN), 2)  AS avg_mean,
       ROUND(AVG(UPPER_FENCE), 2)   AS avg_upper_fence
FROM EPOS_STAT_BASELINE
GROUP BY METRIC;
