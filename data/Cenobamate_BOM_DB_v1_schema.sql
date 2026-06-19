CREATE VIEW v_api_tco AS
SELECT a.cmo_id, a.cmo_name, a.country, a.price_usd_kg, a.status,
       i.overall_total AS introcost, i.lead_time_mo, a.rsm_tariff_in, a.api_tariff_out
FROM fact_api_price a
LEFT JOIN fact_introcost i ON a.cmo_id=i.cmo_id;

CREATE VIEW v_dp_wide AS
SELECT strength_mg,
  MAX(CASE WHEN cmo_id='DP-AVARA' THEN price_per_1000tab END) AS avara_us,
  MAX(CASE WHEN cmo_id='DP-PATHEON' THEN price_per_1000tab END) AS patheon_ca
FROM fact_dp_price GROUP BY strength_mg ORDER BY strength_mg;

CREATE VIEW v_tariff_by_group AS
SELECT scenario_group, origin, dest, stage, rate_pct, rate_display, legal_basis, note
FROM fact_tariff ORDER BY scenario_group, rate_pct DESC;

CREATE TABLE bom_tree (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "level" TEXT, "material_type" TEXT, "material_code" TEXT, "material_description" TEXT, "batch_size_cmo_a" TEXT, "batch_size_cmo_b" TEXT, "unit" TEXT, "cmo_a" TEXT, "cmo_b" TEXT, "input_material_code" TEXT, "input_material_description" TEXT, "conversion_ratio" TEXT, "conversion_unit" TEXT, "note" TEXT, "sap_plant_cmo_a" TEXT, "sloc_cmo_a" TEXT, "sap_plant_cmo_b" TEXT, "sloc_cmo_b" TEXT, input_routes TEXT, route_note TEXT, input_group TEXT, input_group_mode TEXT);

CREATE TABLE cmo_summary (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "cmo" TEXT, "country" TEXT, "role" TEXT, "material_type_stage" TEXT, "target_market" TEXT, "key_products" TEXT, "batch_size_range" TEXT, "note" TEXT, "sap_plant" TEXT, "key_storage_locations" TEXT);

CREATE TABLE common_blend (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "blend_type" TEXT, "target_market" TEXT, "api_input_kg" TEXT, "strength" TEXT, "api_portion_kg" TEXT, "batch_count" TEXT, "material_code" TEXT, "material_description" TEXT, "batch_size_patheon" TEXT, "note" TEXT);

CREATE TABLE dim_cmo(
  cmo_id      TEXT PRIMARY KEY,
  cmo_name    TEXT NOT NULL,
  country     TEXT,
  stage       TEXT,
  status      TEXT CHECK(status IN ('active','candidate','no-go','benchmark')),
  lead_time_mo INTEGER,
  pv_scale_kg REAL,
  note        TEXT
);

CREATE TABLE fact_api_price(
  cmo_id TEXT REFERENCES dim_cmo(cmo_id),
  cmo_name TEXT, country TEXT,
  price_usd_kg REAL, basis TEXT, rsm_source TEXT,
  rsm_tariff_in TEXT, api_tariff_out TEXT,
  status TEXT, effective TEXT, source TEXT, note TEXT,
  PRIMARY KEY(cmo_id)
);

CREATE TABLE fact_dp_price(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cmo_id TEXT REFERENCES dim_cmo(cmo_id),
  cmo_name TEXT, country TEXT,
  strength_mg REAL, price_per_1000tab REAL, tier TEXT, unit TEXT, note TEXT
);

CREATE TABLE fact_fp_price(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cmo_id TEXT REFERENCES dim_cmo(cmo_id),
  cmo_name TEXT, country TEXT,
  fp_type TEXT, strength_or_pack TEXT, price_per_unit REAL,
  includes_dp TEXT CHECK(includes_dp IN ('Y','N')), unit TEXT, note TEXT
);

CREATE TABLE fact_introcost(
  cmo_id TEXT REFERENCES dim_cmo(cmo_id),
  cmo_name TEXT, country TEXT,
  rd_total REAL, prod_total REAL, overall_total REAL, capex REAL,
  lead_time_mo INTEGER, pv_scale_kg REAL,
  status TEXT, source TEXT, note TEXT,
  PRIMARY KEY(cmo_id)
);

CREATE TABLE fact_rsm_price(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  axis TEXT CHECK(axis IN ('US','EU')),
  volume_mt REAL,
  wisdom_old REAL, wisdom_new REAL, lianhe_old REAL, lianhe_applied_eu REAL,
  model_applied REAL,            -- US: avg(wisdom_new,lianhe_old) / EU: lianhe_applied_eu
  unit TEXT, effective TEXT, source TEXT
);

CREATE TABLE fact_sp_price(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cmo_id TEXT REFERENCES dim_cmo(cmo_id),
  cmo_name TEXT, country TEXT,
  pack_type TEXT, strength_or_count TEXT, price_per_unit REAL, unit TEXT, note TEXT
);

CREATE TABLE fact_tariff(
  tariff_id TEXT PRIMARY KEY,
  scenario_group TEXT, stage TEXT,
  origin TEXT, dest TEXT,
  rate_pct REAL, rate_display TEXT,
  basis TEXT, legal_basis TEXT, effective TEXT, note TEXT
);

CREATE TABLE legacy_api_codes(
  legacy_code          TEXT PRIMARY KEY,
  material_description  TEXT,
  supply_use            TEXT,
  conversion_flow       TEXT,
  current_code_map      TEXT,   -- 현행 2CNY* 코드 매핑
  status                TEXT DEFAULT 'discontinued',
  note                  TEXT
);

CREATE TABLE partner_mapping (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "partner" TEXT, "country_region" TEXT, "supply_level" TEXT, "product_material_code" TEXT, "product_description" TEXT, "partner_dp_pkg_capability" TEXT, "note" TEXT);

CREATE TABLE plant_master(row_id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_code TEXT, plant_name TEXT, search_term_1 TEXT, search_term_2 TEXT, mapped_cmo_role TEXT);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE storage_location(row_id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant TEXT, location TEXT, description TEXT, material_stage TEXT);

CREATE TABLE supply_flow (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "market" TEXT, "partner" TEXT, "supply_level" TEXT, "rsm_vendor" TEXT, "api_cmo" TEXT, "dp_cmo" TEXT, "semi_fp_cmo" TEXT, "fp_cmo_packaging" TEXT, "note" TEXT, "sap_plant_flow" TEXT);

CREATE INDEX ix_dp_cmo ON fact_dp_price(cmo_id);

CREATE INDEX ix_fp_cmo ON fact_fp_price(cmo_id);

CREATE INDEX ix_sp_cmo ON fact_sp_price(cmo_id);

CREATE INDEX ix_tar_grp ON fact_tariff(scenario_group);

CREATE INDEX ix_tar_od ON fact_tariff(origin,dest,stage);

