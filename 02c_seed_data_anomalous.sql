-- =============================================================================
-- 02c_seed_data_anomalous.sql
-- Scenario 2: Inject three types of anomalies into today's data
--
-- ANOMALY 1 — PRICE SPIKE:
--   JW-BLACK-750ML in NORTH region has unit price ~10x normal (3,100 BRL vs ~300 normal)
--
-- ANOMALY 2 — SILENT REGION:
--   EAST region has ZERO records for today — a complete data silence
--   Normal pattern: 10-15 records per day for EAST
--
-- ANOMALY 3 — COMBO (Multi-column):
--   BAILEYS-700ML in WEST has a plausible unit price (130 BRL, within range)
--   but sales volume is 400 cases (normal: 1-15) AND transaction count = 1
--   Individually these might pass checks — together they're impossible
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.EPOS_DATA;


-- ── ANOMALY 1: PRICE SPIKE ────────────────────────────────────────────────────
-- JW Black 750ML, NORTH region, today
-- Normal price: 280-320 BRL. Anomalous price: 3,100 BRL (data entry error / wrong unit)

INSERT INTO EPOS_DAILY_FACTS
    (TRANSACTION_DATE, OUTLET_CODE, PRODUCT_CODE, CUSTOMER_CODE,
     REGION, CHANNEL, BRAND_CODE, PACK_SIZE,
     UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT)
VALUES
    (CURRENT_DATE(), '00000000000001', 'BR-JW-BLACK-750ML', '0012340001',
     'NORTH', 'ON_TRADE', 'JOHNNIEWALKER', '750ML',
     3100.00,   -- ← 10x normal (anomalous)
     8.0000,
     24800.00,  -- value = price × volume (consistent with the bad price)
     6),

    (CURRENT_DATE(), '00000000000002', 'BR-JW-BLACK-750ML', '0012340001',
     'NORTH', 'ON_TRADE', 'JOHNNIEWALKER', '750ML',
     2950.00,   -- ← also anomalous (same issue, different outlet)
     3.0000,
     8850.00,
     2);

-- Note: SOUTH, WEST, CENTRAL get normal JW Black records for today
INSERT INTO EPOS_DAILY_FACTS
    (TRANSACTION_DATE, OUTLET_CODE, PRODUCT_CODE, CUSTOMER_CODE,
     REGION, CHANNEL, BRAND_CODE, PACK_SIZE,
     UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT)
VALUES
    (CURRENT_DATE(), '00000000000004', 'BR-JW-BLACK-750ML', '0012340002',
     'SOUTH', 'OFF_TRADE', 'JOHNNIEWALKER', '750ML', 305.00, 7.0000, 2135.00, 5),
    (CURRENT_DATE(), '00000000000007', 'BR-JW-BLACK-750ML', '0012340004',
     'WEST', 'ON_TRADE', 'JOHNNIEWALKER', '750ML', 295.00, 12.0000, 3540.00, 9),
    (CURRENT_DATE(), '00000000000010', 'BR-JW-BLACK-750ML', '0012340005',
     'CENTRAL', 'OFF_TRADE', 'JOHNNIEWALKER', '750ML', 312.00, 5.0000, 1560.00, 4);


-- ── ANOMALY 2: SILENT REGION (EAST) ──────────────────────────────────────────
-- Insert ZERO records for EAST region today.
-- The anomaly is the ABSENCE of data — no row to flag in traditional DQ.
-- We detect this by comparing today's EAST row count to the 7-day average.
-- (No INSERT needed — the silence is the anomaly. Detection happens in 02f.)


-- ── ANOMALY 3: COMBO ANOMALY ──────────────────────────────────────────────────
-- BAILEYS 700ML, WEST region
-- Unit price: 132.00 (WITHIN normal 120-145 range — passes a range check)
-- Sales volume: 450 cases (normal: 1-15 — extreme outlier)
-- Transaction count: 1 (ONE transaction for 450 cases — impossible for a bar)
-- EACH metric alone might look arguable. TOGETHER they scream error.

INSERT INTO EPOS_DAILY_FACTS
    (TRANSACTION_DATE, OUTLET_CODE, PRODUCT_CODE, CUSTOMER_CODE,
     REGION, CHANNEL, BRAND_CODE, PACK_SIZE,
     UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT)
VALUES
    (CURRENT_DATE(), '00000000000008', 'BR-BAILEYS-700ML', '0012340004',
     'WEST', 'ON_TRADE', 'BAILEYS', '700ML',
     132.00,    -- ← plausible price (won't trigger range check)
     450.0000,  -- ← 30x normal volume (might trigger volume check if threshold is high)
     59400.00,  -- ← value is consistent with price × volume
     1);        -- ← single transaction for 450 cases (physically implausible)

-- Add normal BAILEYS records for other regions so we have comparison data
INSERT INTO EPOS_DAILY_FACTS
    (TRANSACTION_DATE, OUTLET_CODE, PRODUCT_CODE, CUSTOMER_CODE,
     REGION, CHANNEL, BRAND_CODE, PACK_SIZE,
     UNIT_PRICE, SALES_VOLUME_CASES, SALES_VALUE_BRL, TRANSACTION_COUNT)
VALUES
    (CURRENT_DATE(), '00000000000004', 'BR-BAILEYS-700ML', '0012340002',
     'SOUTH', 'OFF_TRADE', 'BAILEYS', '700ML', 128.00, 6.0000, 768.00, 4),
    (CURRENT_DATE(), '00000000000010', 'BR-BAILEYS-700ML', '0012340005',
     'CENTRAL', 'OFF_TRADE', 'BAILEYS', '700ML', 135.00, 9.0000, 1215.00, 7),
    (CURRENT_DATE(), '00000000000001', 'BR-BAILEYS-700ML', '0012340001',
     'NORTH', 'ON_TRADE', 'BAILEYS', '700ML', 122.00, 4.0000, 488.00, 3);


-- ── VERIFY ANOMALY INJECTION ──────────────────────────────────────────────────

SELECT
    TRANSACTION_DATE,
    REGION,
    PRODUCT_CODE,
    COUNT(*)                            AS record_count,
    ROUND(AVG(UNIT_PRICE), 2)           AS avg_price,
    ROUND(MAX(UNIT_PRICE), 2)           AS max_price,
    ROUND(AVG(SALES_VOLUME_CASES), 2)   AS avg_volume,
    ROUND(MAX(SALES_VOLUME_CASES), 2)   AS max_volume
FROM EPOS_DAILY_FACTS
WHERE TRANSACTION_DATE = CURRENT_DATE()
GROUP BY 1, 2, 3
ORDER BY 2, 3;

-- Expected observations:
-- NORTH | JW-BLACK → max_price ~3100 (anomaly 1)
-- EAST  → NO ROWS at all today (anomaly 2: silent region)
-- WEST  | BAILEYS  → max_volume ~450 (anomaly 3: combo)
