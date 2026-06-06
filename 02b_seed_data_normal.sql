-- =============================================================================
-- 02b_seed_data_normal.sql
-- Scenario 2: Seed 30 days of realistic EPOS baseline data
--
-- Generates ~1,500 rows across 5 regions, 6 products, 3 channels
-- with realistic distributions for unit price, volume and value.
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;

-- We use a date spine + product/region cross join + controlled randomness
-- UNIFORM() gives us random values in [a, b]
-- We seed realistic price bands per product

INSERT INTO EPOS_DAILY_FACTS
    (TRANSACTION_DATE, OUTLET_CODE, PRODUCT_CODE, CUSTOMER_CODE,
     REGION, CHANNEL, BRAND_CODE, PACK_SIZE,
     UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT)

WITH date_spine AS (
    -- Last 30 days (baseline period)
    SELECT DATEADD(day, -seq, CURRENT_DATE() - 1) AS dt
    FROM (
        SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS seq
        FROM TABLE(GENERATOR(ROWCOUNT => 30))
    )
),
products AS (
    SELECT * FROM VALUES
        ('BR-JW-BLACK-750ML',  'JOHNNIEWALKER', '750ML',  280.00, 320.00),  -- unit price range [min, max]
        ('BR-JW-RED-1L',       'JOHNNIEWALKER', '1L',     195.00, 230.00),
        ('BR-BAILEYS-700ML',   'BAILEYS',        '700ML',  120.00, 145.00),
        ('BR-SMIRNOFF-980ML',  'SMIRNOFF',       '980ML',   85.00, 105.00),
        ('BR-GUINNESS-440ML',  'GUINNESS',        '440ML',   18.00,  24.00),
        ('BR-TANQUERAY-750ML', 'TANQUERAY',       '750ML',  210.00, 255.00)
        AS t(product_code, brand_code, pack_size, price_min, price_max)
),
regions AS (
    SELECT * FROM VALUES
        ('NORTH',   '0012340001', 'ON_TRADE'),
        ('SOUTH',   '0012340002', 'OFF_TRADE'),
        ('EAST',    '0012340003', 'MODERN_TRADE'),
        ('WEST',    '0012340004', 'ON_TRADE'),
        ('CENTRAL', '0012340005', 'OFF_TRADE')
        AS t(region, customer_code, channel)
),
outlet_codes AS (
    -- 3 outlets per region
    SELECT region, LPAD(outlet_seq::VARCHAR, 14, '0') AS outlet_code
    FROM regions r
    CROSS JOIN (SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) AS outlet_seq
                FROM TABLE(GENERATOR(ROWCOUNT => 3))) o
),
base_data AS (
    SELECT
        d.dt                                                           AS transaction_date,
        oc.outlet_code,
        p.product_code,
        r.customer_code,
        r.region,
        r.channel,
        p.brand_code,
        p.pack_size,
        -- Unit price: random within band, rounded to 2dp
        ROUND(UNIFORM(p.price_min, p.price_max, RANDOM()), 2)          AS unit_price,
        -- Volume: realistic daily volume per outlet (1-15 cases, varies by product)
        ROUND(UNIFORM(1.0, 15.0, RANDOM()), 4)                        AS sales_volume_cases
    FROM date_spine d
    CROSS JOIN products p
    CROSS JOIN regions r
    JOIN outlet_codes oc ON oc.region = r.region
    -- Not every outlet sells every product every day (80% fill rate)
    WHERE UNIFORM(0.0, 1.0, RANDOM()) > 0.20
)
SELECT
    transaction_date,
    outlet_code,
    product_code,
    customer_code,
    region,
    channel,
    brand_code,
    pack_size,
    unit_price,
    sales_volume_cases,
    ROUND(unit_price * sales_volume_cases, 2)          AS sales_value_brl,
    CEIL(UNIFORM(1.0, 12.0, RANDOM()))::NUMBER         AS transaction_count
FROM base_data;


-- Verify baseline
SELECT
    MIN(TRANSACTION_DATE) AS earliest,
    MAX(TRANSACTION_DATE) AS latest,
    COUNT(*)              AS total_rows,
    COUNT(DISTINCT REGION) AS regions,
    COUNT(DISTINCT PRODUCT_CODE) AS products,
    ROUND(AVG(UNIT_PRICE), 2)  AS avg_unit_price,
    ROUND(AVG(SALES_VOLUME_CASES), 4) AS avg_volume
FROM EPOS_DAILY_FACTS;
