-- =============================================================================
-- 01b_seed_metadata.sql
-- Scenario 1: Seed realistic DDH-style metadata (tables, columns, lineage, dashboards)
-- =============================================================================

USE ROLE      CORTEX_DEV;
USE WAREHOUSE CORTEX_WH;
USE SCHEMA    CORTEX_AI_LAB.METADATA;


-- ── SEED: META_TABLES ────────────────────────────────────────────────────────

INSERT INTO META_TABLES
    (TABLE_NAME, SCHEMA_NAME, DATABASE_NAME, LAYER, DOMAIN, OWNER_TEAM,
     OWNER_EMAIL, DESCRIPTION, IS_ACTIVE, REFRESH_FREQUENCY, LAST_REFRESHED_AT, ROW_COUNT_LAST_RUN)
VALUES
-- LANDING
('tf_atl_br_tradeedge_epos_raw',   'landing', 'ddh2_dev', 'LANDING', 'EPOS',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Raw TradeEdge EPOS data landed from Brazil. Contains outlet sales transactions with product, customer and outlet codes before any cleansing. Files arrive daily via blob trigger.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 182400),

('tf_atl_depletion_raw',           'landing', 'ddh2_dev', 'LANDING', 'DEPLETION',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Raw distributor depletion data. Captures volume moved from Diageo to distributors, split by SKU and ship-to location. Source: SAP extracts loaded nightly.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 94300),

('tf_atl_nielsen_raw',             'landing', 'ddh2_dev', 'LANDING', 'EPOS',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Nielsen market share data landed weekly. Contains retail offtake volumes, market share percentages and competitor benchmarks by category and region.',
 TRUE, 'WEEKLY', DATEADD(day, -9, CURRENT_TIMESTAMP()), 12800),

-- SILVER
('tf_atl_bau_epos',                'silver',  'ddh2_dev', 'SILVER', 'EPOS',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Cleansed and validated EPOS silver table. Applies 11 DQ checks, LPAD normalisation on outlet codes, SHA1 surrogate key generation. Feeds all gold EPOS pipelines.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 178100),

('tf_atl_depletion_silver',        'silver',  'ddh2_dev', 'SILVER', 'DEPLETION',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Validated depletion silver table with enriched distributor keys and period normalisation to calendar week. Feeds volume movement gold tables.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 91200),

('tf_atl_bau_epos_errors',         'silver',  'ddh2_dev', 'SILVER', 'EPOS',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'DQ error quarantine table. Rows failing any of the 11 EPOS DQ checks land here with error_code and error_message. Does NOT retain source natural keys — known gap, bridge table recommended.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 3200),

-- GOLD
('tb_fact_epos',                   'gold',    'ddh2_dev', 'GOLD', 'EPOS',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Gold EPOS fact table. Contains resolved dimension surrogate keys (ProductKey, CustomerKey, OutletKey, DateKey), sales volume and value KPIs. Partitioned by SourceSystem, Country, EndDateKey.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 165400),

('tb_dimproductunharmonised',       'gold',    'ddh2_dev', 'GOLD', 'PRODUCT',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Unharmonised product dimension. Contains raw product attributes as received from source systems before harmonisation to Global Item master. Includes ProductHash (SHA-256) for change detection.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 48600),

('tb_dimproductharmonised',         'gold',    'ddh2_dev', 'GOLD', 'PRODUCT',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Harmonised product dimension linked to Symphony Global Item master. Only products successfully matched via fuzzy/exact lookup appear here. Orphaned records remain in unharmonised until manually resolved.',
 TRUE, 'DAILY', DATEADD(day, -2, CURRENT_TIMESTAMP()), 41200),

('tb_dimoutlet',                    'gold',    'ddh2_dev', 'GOLD', 'CUSTOMER',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Outlet dimension. Each row is a unique trade outlet (bar, supermarket, off-trade). OutletCode is LPAD to 14 characters. Includes geolocation and channel classification.',
 TRUE, 'DAILY', DATEADD(day, -1, CURRENT_TIMESTAMP()), 312000),

('tb_fact_depletion',               'gold',    'ddh2_dev', 'GOLD', 'DEPLETION',
 'Customer Foundation', 'ddh-foundation@diageo.com',
 'Gold depletion fact. Volume (cases) moved from Diageo warehouses to distributor locations by SKU and period. Used for sell-in vs sell-out gap analysis.',
 FALSE, 'DAILY', DATEADD(day, -15, CURRENT_TIMESTAMP()), 0);   -- ← INACTIVE, stale


-- ── SEED: META_COLUMNS ───────────────────────────────────────────────────────

INSERT INTO META_COLUMNS
    (TABLE_ID, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, IS_PRIMARY_KEY,
     IS_FOREIGN_KEY, REFERENCES_TABLE, REFERENCES_COLUMN,
     DESCRIPTION, SAMPLE_VALUES, DQ_RULES_APPLIED)
VALUES
-- tb_fact_epos columns
((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'EPOS_KEY', 'VARCHAR(64)', FALSE, TRUE, FALSE, NULL, NULL,
 'SHA1 surrogate key generated by IIQ framework. Concatenation of OutletCode|ProductCode|CustomerCode|DateKey|SourceSystem. Used as the unique row identifier for upsert/merge operations.',
 NULL, 'NOT NULL, LENGTH=40'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'OUTLET_CODE', 'VARCHAR(14)', FALSE, FALSE, TRUE, 'tb_dimoutlet', 'OUTLET_CODE',
 'Outlet identifier LPAD to 14 characters with leading zeros. Represents the physical trade point of sale where the EPOS transaction occurred. Brazilian outlet codes are typically 8-10 digits padded to 14.',
 '00000012345678, 00000098765432', 'NOT NULL, LPAD(14), FK→tb_dimoutlet'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'PRODUCT_CODE', 'VARCHAR(50)', FALSE, FALSE, TRUE, 'tb_dimproductharmonised', 'PRODUCT_CODE',
 'Product identifier as received from the source system (TradeEdge). Maps to the harmonised product dimension via Symphony lookup. UPPER() and TRIM() applied during silver processing.',
 'BR-JOHNIE-750ML, JW-BLACK-1L', 'NOT NULL, UPPER, TRIM, FK→tb_dimproductharmonised'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'CUSTOMER_CODE', 'VARCHAR(10)', FALSE, FALSE, TRUE, 'tb_dimoutlet', 'CUSTOMER_CODE',
 'Customer/distributor code LPAD to 10 characters. Identifies the Diageo customer account that owns the outlet. A single customer can own many outlets.',
 '0012345678, 0098765432', 'NOT NULL, LPAD(10)'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'SALES_VOLUME_CASES', 'NUMBER(18,4)', TRUE, FALSE, FALSE, NULL, NULL,
 'Volume of product sold in the EPOS transaction expressed in 9-litre equivalent cases. Null is allowed for value-only transactions where volume is not reported by the source.',
 '12.0000, 4.5000, 100.0000', 'RANGE(0, 50000), NO_NEGATIVE'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'SALES_VALUE_LOCAL_CCY', 'NUMBER(18,2)', TRUE, FALSE, FALSE, NULL, NULL,
 'Transaction sales value in local currency (BRL for Brazil). Exchange rates are NOT applied at this layer — currency conversion happens at the presented/reporting layer.',
 '250.00, 1200.50, 89.99', 'RANGE(0, 10000000)'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'DATE_KEY', 'NUMBER(8)', FALSE, FALSE, TRUE, 'tb_dimdatetime', 'DATE_KEY',
 'Integer date key in YYYYMMDD format. Joins to the datetime dimension. Represents the transaction date as reported by the outlet POS system.',
 '20240115, 20240301', 'NOT NULL, FORMAT=YYYYMMDD'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'SOURCE_SYSTEM', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, NULL,
 'Source system identifier. Always TRADEEDGE for EPOS data. Used as partition key alongside Country and EndDateKey. Helps distinguish multi-source pipelines at the gold layer.',
 'TRADEEDGE, NIELSEN', 'NOT NULL'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'COUNTRY', 'VARCHAR(3)', FALSE, FALSE, FALSE, NULL, NULL,
 'ISO 3166-1 alpha-3 country code. Partition key. BR for Brazil, ZAF for South Africa, GBR for Great Britain. Used to filter pipeline runs per market.',
 'BRA, ZAF, GBR', 'NOT NULL, LENGTH=3, ISO3166'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_fact_epos'),
 'tb_fact_epos', 'END_DATE_KEY', 'NUMBER(8)', FALSE, FALSE, FALSE, NULL, NULL,
 'Partition date key representing the processing batch date. Used with SourceSystem and Country as the three-column partition. Set by the IIQ pipeline run timestamp.',
 '20240115, 20240301', 'NOT NULL'),

-- tb_dimproductunharmonised columns
((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_dimproductunharmonised'),
 'tb_dimproductunharmonised', 'PRODUCT_HASH', 'VARCHAR(64)', FALSE, TRUE, FALSE, NULL, NULL,
 'SHA-256 hash generated from ProductCode|ProductName|BrandCode|PackSize|SourceSystem (each UPPER/TRIM/COALESCE applied before hashing). Used to detect attribute changes and trigger SCD updates. Framework default SHA1 was overridden with execute_spark_expression + sha2() to produce SHA-256.',
 NULL, 'NOT NULL, LENGTH=64, SHA256'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_dimproductunharmonised'),
 'tb_dimproductunharmonised', 'PRODUCT_CODE', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, NULL,
 'Raw product code from source system. Not yet matched to Symphony Global Item. May contain trailing spaces or mixed case from source — UPPER/TRIM applied.',
 'br-johnie-750ml, JW-BLACK-1L', 'NOT NULL, UPPER, TRIM'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_dimproductunharmonised'),
 'tb_dimproductunharmonised', 'BRAND_CODE', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, NULL,
 'Brand identifier as provided by the source system. Not yet validated against Diageo brand master. Null is permissible for distributor-reported products where brand is unknown.',
 'JOHNNIEWALKER, BAILEYS, GUINNESS', 'NULLABLE'),

((SELECT TABLE_ID FROM META_TABLES WHERE TABLE_NAME='tb_dimproductunharmonised'),
 'tb_dimproductunharmonised', 'PACK_SIZE', 'VARCHAR(20)', TRUE, FALSE, FALSE, NULL, NULL,
 'Pack/bottle size from the source (e.g. 750ML, 1L, 700ML). Not standardised at this layer. Harmonisation to standard Diageo pack size codes happens in tb_dimproductharmonised.',
 '750ML, 1L, 700ML, 1.75L', 'NULLABLE');


-- ── SEED: META_LINEAGE ───────────────────────────────────────────────────────

INSERT INTO META_LINEAGE
    (SOURCE_TABLE, SOURCE_SCHEMA, SOURCE_LAYER,
     TARGET_TABLE, TARGET_SCHEMA, TARGET_LAYER,
     TRANSFORM_TYPE, TRANSFORM_NOTES, PIPELINE_NAME)
VALUES
('tf_atl_br_tradeedge_epos_raw', 'landing', 'LANDING',
 'tf_atl_bau_epos',              'silver',  'SILVER',
 'FILTER+CLEANSE',
 'Applies 11 DQ checks, LPAD normalisation (outlet 14 chars, customer 10 chars), date format validation, NOT NULL checks on key fields.',
 'tf_atl_br_tradeedge_epos.yml'),

('tf_atl_bau_epos',              'silver',  'SILVER',
 'tb_fact_epos',                 'gold',    'GOLD',
 'MERGE+LOOKUP',
 'Dimension key resolution for ProductKey, CustomerKey, OutletKey via hash lookups. SHA1 surrogate key generation. UPSERT on EPOS_KEY. Partition by SourceSystem|Country|EndDateKey.',
 'tf_atl_bau_epos.yml'),

('tf_atl_bau_epos',              'silver',  'SILVER',
 'tb_dimproductunharmonised',    'gold',    'GOLD',
 'MERGE',
 'Extracts distinct product attributes from EPOS silver. SHA-256 ProductHash for change detection (overrides IIQ default SHA1 via execute_spark_expression). Partition by SourceSystem|Country|EndDateKey.',
 'tf_tradeedge_epos_dimproductunharmonised.yml'),

('tb_dimproductunharmonised',    'gold',    'GOLD',
 'tb_dimproductharmonised',      'gold',    'GOLD',
 'JOIN+LOOKUP',
 'Fuzzy + exact match against Symphony Global Item master. Records that fail matching remain in unharmonised as orphans. Manual intervention required for orphan resolution.',
 'symphony_harmonisation_pipeline'),

('tf_atl_depletion_raw',         'landing', 'LANDING',
 'tf_atl_depletion_silver',      'silver',  'SILVER',
 'FILTER+CLEANSE',
 'Period normalisation to calendar week, distributor code validation, volume range checks.',
 'tf_atl_depletion.yml'),

('tf_atl_depletion_silver',      'silver',  'SILVER',
 'tb_fact_depletion',            'gold',    'GOLD',
 'MERGE',
 'Distributor key lookup, aggregation to weekly level.',
 'tf_atl_depletion_gold.yml');


-- ── SEED: META_DASHBOARD_DEPS ────────────────────────────────────────────────

INSERT INTO META_DASHBOARD_DEPS
    (DASHBOARD_NAME, DASHBOARD_TOOL, TABLE_NAME, SCHEMA_NAME, FIELD_USED, IS_CRITICAL, BUSINESS_OWNER)
VALUES
('Brazil EPOS Weekly Review',     'POWER_BI',  'tb_fact_epos',              'gold', 'SALES_VOLUME_CASES',      TRUE,  'Country Revenue Manager — Brazil'),
('Brazil EPOS Weekly Review',     'POWER_BI',  'tb_fact_epos',              'gold', 'SALES_VALUE_LOCAL_CCY',   TRUE,  'Country Revenue Manager — Brazil'),
('Brazil EPOS Weekly Review',     'POWER_BI',  'tb_dimoutlet',              'gold', 'OUTLET_CODE',             TRUE,  'Country Revenue Manager — Brazil'),
('Global Brand Performance',      'TABLEAU',   'tb_fact_epos',              'gold', 'PRODUCT_CODE',            TRUE,  'Global Brand Director'),
('Global Brand Performance',      'TABLEAU',   'tb_dimproductharmonised',   'gold', 'BRAND_CODE',              TRUE,  'Global Brand Director'),
('DBT Model Performance Monitor', 'HEX',       'tb_fact_epos',              'gold', 'END_DATE_KEY',            FALSE, 'Data Engineering Team'),
('Distributor Sell-In Tracker',   'SIGMA',     'tb_fact_depletion',         'gold', 'SALES_VOLUME_CASES',      TRUE,  'Supply Chain Analytics'),
('RGM Pricing Intelligence',      'POWER_BI',  'tb_fact_epos',              'gold', 'SALES_VALUE_LOCAL_CCY',   TRUE,  'Revenue Growth Management'),
('Product Catalogue',             'TABLEAU',   'tb_dimproductunharmonised', 'gold', 'PRODUCT_HASH',            FALSE, 'Master Data Team');


-- ── VERIFY ───────────────────────────────────────────────────────────────────

SELECT 'META_TABLES'         AS tbl, COUNT(*) AS rows FROM META_TABLES         UNION ALL
SELECT 'META_COLUMNS'        AS tbl, COUNT(*) AS rows FROM META_COLUMNS        UNION ALL
SELECT 'META_LINEAGE'        AS tbl, COUNT(*) AS rows FROM META_LINEAGE        UNION ALL
SELECT 'META_DASHBOARD_DEPS' AS tbl, COUNT(*) AS rows FROM META_DASHBOARD_DEPS;
