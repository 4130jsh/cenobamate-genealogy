#!/usr/bin/env python3
"""
Cenobamate batch genealogy tracer  (v2 — accuracy / performance / robustness)

개선 요약 (설계문서 genealogy_improvement_design_v1 반영)
-----------------------------------------------------------
A. 정확도
  A-1 REF/DOC 그룹키 빈 값 과도결합 방지 (ref 단독 그룹 신뢰도 강등)
  A-2 1 neg -> N pos 분할 매칭 (alloc_qty 기록), --split-matching
  A-3 생산 엣지 다중 output 페어링 정확화 (item거리+tier+수량 점수)
  A-4 UoM 동일성 검증 (분할/transfer 후보, usage 집계를 uom 포함)
  A-5 movement type 분류 테이블화 (541/521/531/311 등 확장)
B. 성능
  B-1 행별 apply 제거 -> 유니크 (plant,sloc) 조합 계산 + 벡터 tier 규칙
  B-2 node/edge dict 인덱싱
C. 견고성
  C-1 사이클 가드 + meta.cycles 로깅
  C-2 날짜 인과성 검증 (date_violation flag, --strict-dates)
  C-3 batch 다중 material candidate 명시
  C-4 분할 후 미배분 수량 잔차 리포트 (unmatched_quantity)
  C-5 단일 export 한계 자동 주석

하위호환: 신규 동작은 플래그 토글. 출력은 컬럼 추가만(alloc_qty/cycle_flag/date_violation/confidence).

Example
-------
python cenobamate_genealogy_tool_v2.py \
  --sap EXPORT_20260617_141501.xlsx \
  --bom-db Cenobamate_BOM_DB_v1.sqlite \
  --batch 2096696 --material 5CNB5ZAA1ZZZ \
  --direction upstream --out genealogy_out --export-xlsx
"""
from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import os
import re
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd


# ============================================================
# 상수 / movement 분류 (A-5)
# ============================================================
TIER_ORDER = {"RSM": 0, "API": 1, "DP": 2, "SP": 3, "FP": 4, "OTHER": 99}
ORDER_TIER = {v: k for k, v in TIER_ORDER.items()}

# A-5: 하드코딩 isin([101,543]) 대신 분류 테이블
MOVEMENT_CLASS = {
    "production_out": {101, 521, 531},          # GR 생산/무지시생산/부산물
    "production_consume": {543, 541},           # 외주 component 소비/출고
    "transfer": {301, 303, 305, 311, 313, 315}, # 재고/위치 이동
    "reversal": {102, 542, 544, 532, 922, 926}, # 취소(역분개)
    "exclude": {921, 925},                      # 시장출고/판매성
}
DEFAULT_EXCLUDE_MOVEMENTS = set(MOVEMENT_CLASS["exclude"])
DEFAULT_REVERSAL_MOVEMENTS = set(MOVEMENT_CLASS["reversal"])
DEFAULT_MAX_DEPTH = 12
EPS = 1e-6

REQUIRED_SAP_COLS = [
    "Material Document", "Material Doc.Item", "Material", "Batch",
    "Plant", "Storage Location", "Movement Type", "Qty in unit of entry",
]
OPTIONAL_SAP_COLS = [
    "Material Description", "Unit of Entry", "Posting Date", "Entry Date",
    "Purchase order", "Reference", "Movement Type Text", "Document Date",
    "Item", "Supplier", "User Name",
]


# ============================================================
# 스칼라 정규화 헬퍼
# ============================================================
def clean_str(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = html.unescape(str(value)).strip()
    if s.lower() in {"nan", "none", "nat", "null"}:
        return ""
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s.strip()


def clean_code(value) -> str:
    return clean_str(value).upper()


def parse_float(value) -> float:
    s = clean_str(value).replace(",", "")
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_int(value) -> int:
    s = clean_str(value)
    if s == "":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def node_id(material: str, batch: str) -> str:
    return f"{material}||{batch}"


def split_node_id(nid: str) -> Tuple[str, str]:
    if "||" not in nid:
        return nid, ""
    return tuple(nid.split("||", 1))  # type: ignore[return-value]


def split_material_codes(value: str) -> List[str]:
    s = clean_str(value)
    if not s or s == "-":
        return []
    tokens = re.findall(r"\b[1-5][A-Z0-9]{6,}\b", s.upper())
    out: List[str] = []
    seen: Set[str] = set()
    for t in tokens:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def first_nonblank(values: Iterable) -> str:
    for v in values:
        s = clean_str(v)
        if s:
            return s
    return ""


def last_nonblank(values: Iterable) -> str:
    last = ""
    for v in values:
        s = clean_str(v)
        if s:
            last = s
    return last


def join_unique(values: Iterable) -> str:
    out: List[str] = []
    seen: Set[str] = set()
    for v in values:
        s = clean_str(v)
        if not s or s in seen:
            continue
        out.append(s)
        seen.add(s)
    return ", ".join(out)


# ============================================================
# BOM 마스터
# ============================================================
@dataclass
class BomMaster:
    material: pd.DataFrame
    bom_edges: pd.DataFrame
    plant: pd.DataFrame
    sloc: pd.DataFrame
    legacy: pd.DataFrame
    material_to_tier: Dict[str, str]
    material_to_desc: Dict[str, str]
    material_to_inputs: Dict[str, List[str]]
    legacy_to_current: Dict[str, str]
    plant_role: Dict[str, str]
    sloc_stage: Dict[Tuple[str, str], str]
    sloc_desc: Dict[Tuple[str, str], str]


# ============================================================
# GenealogyTool
# ============================================================
class GenealogyTool:
    def __init__(
        self,
        sap_files: Sequence[str],
        bom_db: str,
        include_reversals: bool = False,
        excluded_movements: Optional[Set[int]] = None,
        split_matching: bool = True,        # A-2
        strict_dates: bool = False,         # C-2
        pairing_mode: str = "bom-aware",    # A-3+: 다중 output 페어링 점수식 (bom-aware 기본, legacy 하위호환)
    ) -> None:
        self.sap_files = list(sap_files)
        self.bom_db = bom_db
        self.include_reversals = include_reversals
        self.split_matching = split_matching
        self.strict_dates = strict_dates
        self.pairing_mode = pairing_mode if pairing_mode in ("legacy", "bom-aware") else "bom-aware"
        self.excluded_movements = excluded_movements or set(DEFAULT_EXCLUDE_MOVEMENTS)
        self.ignored_movements = set(self.excluded_movements)
        if not include_reversals:
            self.ignored_movements |= set(DEFAULT_REVERSAL_MOVEMENTS)

        self.build_warnings: List[str] = []
        self.unmatched_rows: List[dict] = []   # C-4

        self.bom = self.load_bom_master(bom_db)
        self.rows = self.load_sap_files(self.sap_files)
        self.edges = self.build_edges(self.rows)
        self.nodes = self.build_nodes(self.rows, self.edges)
        self.node_index = {r["node"]: r for r in self.nodes.to_dict("records")} if not self.nodes.empty else {}  # B-2
        self.up_adj, self.down_adj = self.build_adjacency(self.edges)
        self.scope_note = self.derive_scope_note()  # C-5

    # ----------------------------------------------------------
    # Loaders
    # ----------------------------------------------------------
    @staticmethod
    def load_bom_master(db_path: str) -> BomMaster:
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"BOM SQLite DB not found: {db_path}")
        con = sqlite3.connect(db_path)
        try:
            bom_tree = pd.read_sql_query("SELECT * FROM bom_tree", con)
            plant = pd.read_sql_query("SELECT * FROM plant_master", con)
            sloc = pd.read_sql_query("SELECT * FROM storage_location", con)
            legacy = pd.read_sql_query("SELECT * FROM legacy_api_codes", con)
        finally:
            con.close()

        for df in [bom_tree, plant, sloc, legacy]:
            for c in df.columns:
                df[c] = df[c].map(clean_str)

        material_rows: List[dict] = []
        edge_rows: List[dict] = []
        for _, r in bom_tree.iterrows():
            mat = clean_code(r.get("material_code", ""))
            if not mat or mat == "-":
                continue
            tier = GenealogyTool.tier_from_bom_row(r)
            desc = clean_str(r.get("material_description", ""))
            material_rows.append({
                "material": mat, "tier": tier, "level": clean_str(r.get("level", "")),
                "material_type": clean_str(r.get("material_type", "")), "description": desc,
                "unit": clean_str(r.get("unit", "")), "cmo_a": clean_str(r.get("cmo_a", "")),
                "cmo_b": clean_str(r.get("cmo_b", "")),
                "sap_plant_cmo_a": clean_str(r.get("sap_plant_cmo_a", "")), "sloc_cmo_a": clean_str(r.get("sloc_cmo_a", "")),
                "sap_plant_cmo_b": clean_str(r.get("sap_plant_cmo_b", "")), "sloc_cmo_b": clean_str(r.get("sloc_cmo_b", "")),
                "note": clean_str(r.get("note", "")),
            })
            inputs = split_material_codes(r.get("input_material_code", ""))
            for inp in inputs:
                if inp == mat:
                    continue
                edge_rows.append({
                    "from_material": inp, "to_material": mat, "edge_kind": "BOM_EXPECTED", "to_tier": tier,
                    "conversion_ratio": clean_str(r.get("conversion_ratio", "")),
                    "conversion_unit": clean_str(r.get("conversion_unit", "")),
                    "note": clean_str(r.get("note", "")),
                })

        material = pd.DataFrame(material_rows).drop_duplicates(subset=["material"], keep="first")
        bom_edges = pd.DataFrame(edge_rows).drop_duplicates()

        material_to_tier = dict(zip(material["material"], material["tier"]))
        material_to_desc = dict(zip(material["material"], material["description"]))
        material_to_inputs: Dict[str, List[str]] = defaultdict(list)
        for _, er in bom_edges.iterrows():
            material_to_inputs[er["to_material"]].append(er["from_material"])

        legacy_to_current: Dict[str, str] = {}
        for _, r in legacy.iterrows():
            legacy_code = clean_code(r.get("legacy_code", ""))
            current_codes = split_material_codes(clean_str(r.get("current_code_map", "")))
            if legacy_code and current_codes:
                legacy_to_current[legacy_code] = current_codes[0]
                material_to_tier.setdefault(legacy_code, "API")
                material_to_desc.setdefault(legacy_code, clean_str(r.get("material_description", "")))

        plant_role = {clean_str(r.get("plant_code", "")): clean_str(r.get("mapped_cmo_role", "")) for _, r in plant.iterrows()}
        sloc_stage = {(clean_str(r.get("plant", "")), clean_code(r.get("location", ""))): clean_str(r.get("material_stage", "")) for _, r in sloc.iterrows()}
        sloc_desc = {(clean_str(r.get("plant", "")), clean_code(r.get("location", ""))): clean_str(r.get("description", "")) for _, r in sloc.iterrows()}

        return BomMaster(material, bom_edges, plant, sloc, legacy, material_to_tier, material_to_desc,
                         dict(material_to_inputs), legacy_to_current, plant_role, sloc_stage, sloc_desc)

    @staticmethod
    def tier_from_bom_row(r: pd.Series) -> str:
        mat_type = clean_str(r.get("material_type", "")).upper()
        level = clean_str(r.get("level", ""))
        if "RAW" in mat_type: return "RSM"
        if "API" in mat_type: return "API"
        if "DRUG PRODUCT" in mat_type: return "DP"
        if "SEMI" in mat_type: return "SP"
        if "FP" in mat_type or "FINISHED" in mat_type: return "FP"
        return {"0": "RSM", "1": "API", "2": "DP", "3": "SP", "4": "FP"}.get(level, "OTHER")

    def load_sap_files(self, files: Sequence[str]) -> pd.DataFrame:
        expanded: List[str] = []
        for f in files:
            matches = glob.glob(f)
            expanded.extend(matches if matches else [f])
        if not expanded:
            raise ValueError("No SAP Excel files supplied")
        dfs: List[pd.DataFrame] = []
        for file_path in expanded:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"SAP Excel file not found: {file_path}")
            xls = pd.ExcelFile(file_path)
            sheet = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]
            raw = pd.read_excel(file_path, sheet_name=sheet, dtype=str)
            missing = [c for c in REQUIRED_SAP_COLS if c not in raw.columns]
            if missing:
                raise ValueError(f"{file_path} missing required SAP columns: {missing}")
            for c in OPTIONAL_SAP_COLS:
                if c not in raw.columns:
                    raw[c] = ""
            raw["source_file"] = os.path.basename(file_path)
            raw["source_sheet"] = sheet
            dfs.append(raw)
        df = pd.concat(dfs, ignore_index=True)
        return self.normalize_sap(df)

    # ----------------------------------------------------------
    # B-1: 벡터화 normalize_sap
    # ----------------------------------------------------------
    def normalize_sap(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        out["source_file"] = df["source_file"].map(clean_str)
        out["source_sheet"] = df["source_sheet"].map(clean_str)
        out["material_doc"] = df["Material Document"].map(clean_str)
        out["material_doc_item"] = df["Material Doc.Item"].map(parse_int)
        out["material"] = df["Material"].map(clean_code)
        out["material_desc"] = df["Material Description"].map(clean_str)
        out["batch"] = df["Batch"].map(clean_code)
        out["plant"] = df["Plant"].map(clean_str)
        out["sloc"] = df["Storage Location"].map(clean_code)
        out["movement_type"] = df["Movement Type"].map(parse_int)
        out["movement_text"] = df["Movement Type Text"].map(clean_str)
        out["qty"] = df["Qty in unit of entry"].map(parse_float)
        out["uom"] = df["Unit of Entry"].map(clean_str)
        out["posting_date"] = df["Posting Date"].map(clean_str)
        out["document_date"] = df["Document Date"].map(clean_str)
        out["entry_date"] = df["Entry Date"].map(clean_str)
        out["purchase_order"] = df["Purchase order"].map(clean_str)
        out["po_item"] = df["Item"].map(clean_str)
        out["reference"] = df["Reference"].map(clean_str)
        out["supplier"] = df["Supplier"].map(clean_str)
        out["user_name"] = df["User Name"].map(clean_str)

        # B-1: (plant,sloc) 유니크 조합만 cmo/stage/desc 계산 후 merge (행수 -> 유니크수)
        uniq = out[["plant", "sloc"]].drop_duplicates().copy()
        uniq["cmo"] = uniq.apply(lambda r: self.classify_cmo(r["plant"], r["sloc"]), axis=1)
        uniq["sloc_stage"] = uniq.apply(lambda r: self.bom.sloc_stage.get((r["plant"], r["sloc"]), ""), axis=1)
        uniq["sloc_desc"] = uniq.apply(lambda r: self.bom.sloc_desc.get((r["plant"], r["sloc"]), ""), axis=1)
        out = out.merge(uniq, on=["plant", "sloc"], how="left")

        # B-1: tier 벡터 규칙 우선, 미해결 행만 sloc fallback
        out["tier"] = self.classify_tier_vectorized(out)

        out["node"] = np.where(
            (out["material"] != "") & (out["batch"] != ""),
            out["material"] + "||" + out["batch"], "",
        )
        dedup_cols = ["material_doc", "material_doc_item", "material", "batch", "plant", "sloc",
                      "movement_type", "qty", "purchase_order", "po_item", "reference"]
        out = out.drop_duplicates(subset=dedup_cols, keep="first").reset_index(drop=True)
        out["row_id"] = range(1, len(out) + 1)
        return out

    def classify_tier_vectorized(self, out: pd.DataFrame) -> pd.Series:
        mat = out["material"].fillna("").str.upper()
        desc_u = out["material_desc"].fillna("").str.upper()
        # BOM 마스터/legacy 직접 매핑
        tier = mat.map(self.bom.material_to_tier)
        # 접두/패턴 규칙 (np.select)
        cond = [
            tier.notna(),
            mat.isin(self.bom.legacy_to_current.keys()) | mat.str.startswith("1CNZ"),
            mat.str.startswith("1CNY") | desc_u.str.contains("YKP1941", na=False),
            mat.str.startswith("2CNY") | mat.str.startswith("2CNF"),
            mat.str.startswith("3"),
            mat.str.startswith("4"),
            mat.str.startswith("5"),
        ]
        choice = [tier.fillna("OTHER"), "API", "RSM", "API", "DP", "SP", "FP"]
        res = pd.Series(np.select(cond, choice, default=""), index=out.index)
        # sloc 기반 fallback (미해결 행만)
        unresolved = res.eq("") | res.isna()
        if unresolved.any():
            stage = out.loc[unresolved].apply(
                lambda r: self.bom.sloc_stage.get((clean_str(r["plant"]), clean_code(r["sloc"])), "").upper(), axis=1)
            def stage_to_tier(s):
                if "RSM" in s or s == "RM": return "RSM"
                if "API" in s: return "API"
                if "SEMI" in s or s == "SP": return "SP"
                if s == "DP": return "DP"
                if s == "FP": return "FP"
                return "OTHER"
            res.loc[unresolved] = stage.map(stage_to_tier)
        return res.replace("", "OTHER")

    def classify_tier(self, material: str, desc: str = "", plant: str = "", sloc: str = "") -> str:
        """단건용 (node_summary 등에서 사용)."""
        material = clean_code(material); desc_u = clean_str(desc).upper()
        if material in self.bom.material_to_tier:
            return self.bom.material_to_tier[material]
        if material in self.bom.legacy_to_current or material.startswith("1CNZ"):
            return "API"
        if material.startswith("1CNY") or "YKP1941" in desc_u: return "RSM"
        if material.startswith("2CNY") or material.startswith("2CNF"): return "API"
        if material.startswith("3"): return "DP"
        if material.startswith("4"): return "SP"
        if material.startswith("5"): return "FP"
        stage = self.bom.sloc_stage.get((clean_str(plant), clean_code(sloc)), "").upper()
        if "RSM" in stage or stage == "RM": return "RSM"
        if "API" in stage: return "API"
        if "SEMI" in stage or stage == "SP": return "SP"
        if stage == "DP": return "DP"
        if stage == "FP": return "FP"
        return "OTHER"

    def classify_cmo(self, plant: str, sloc: str) -> str:
        plant = clean_str(plant); sloc = clean_code(sloc)
        desc_u = self.bom.sloc_desc.get((plant, sloc), "").upper()
        if plant == "1100":
            if sloc == "1101" or "LIANHE" in desc_u: return "Lianhe"
            if sloc == "1102" or "WISDOM" in desc_u: return "Wisdom"
            if sloc in {"V202", "1104", "1106"} or "SUB3089" in desc_u or "BT" in desc_u: return "SK biotek"
            if sloc in {"V101", "V201"} or "PORTON" in desc_u: return "Porton"
            if sloc == "R101": return "Caris(Micro)"
            if sloc == "R102": return "Caris(Cambrex)"
            return "SKBP HQ"
        return {"1210": "Patheon", "1220": "PCI CA", "1230": "PCI US", "1310": "Avara",
                "2100": "SKLSI / 3PL", "2020": "SKLSL"}.get(plant, self.bom.plant_role.get(plant, plant))

    # ----------------------------------------------------------
    # Edge construction
    # ----------------------------------------------------------
    def build_edges(self, rows: pd.DataFrame) -> pd.DataFrame:
        frames = [
            self.build_production_edges(rows),
            self.build_reference_edges(rows),
            self.build_document_transfer_edges(rows),
        ]
        frames = [x for x in frames if not x.empty]
        edges = pd.concat(frames, ignore_index=True) if frames else self.empty_edges()
        if edges.empty:
            return self.empty_edges()
        key_cols = ["edge_kind", "from_node", "to_node", "material_doc", "reference",
                    "purchase_order", "po_item", "from_qty", "to_qty", "alloc_qty", "posting_date"]
        for c in key_cols:
            if c not in edges.columns:
                edges[c] = ""
        edges = edges.drop_duplicates(subset=key_cols, keep="first").reset_index(drop=True)
        # C-2: 날짜 인과성
        edges["date_violation"] = edges.apply(
            lambda e: bool(e["from_posting_date"] and e["to_posting_date"] and e["from_posting_date"] > e["to_posting_date"]), axis=1)
        if self.strict_dates:
            n0 = len(edges)
            edges = edges[~edges["date_violation"]].reset_index(drop=True)
            if len(edges) < n0:
                self.build_warnings.append(f"strict-dates: {n0-len(edges)} edge(s) dropped for date inversion")
        edges["edge_id"] = [f"E{i+1:07d}" for i in range(len(edges))]
        return edges

    @staticmethod
    def empty_edges() -> pd.DataFrame:
        cols = ["edge_id", "edge_kind", "confidence", "transition", "status",
                "from_node", "from_material", "from_batch", "from_desc", "from_tier", "from_plant", "from_sloc", "from_cmo",
                "from_qty", "from_uom", "from_posting_date",
                "to_node", "to_material", "to_batch", "to_desc", "to_tier", "to_plant", "to_sloc", "to_cmo",
                "to_qty", "to_uom", "to_posting_date",
                "alloc_qty", "uom_match", "date_violation", "cycle_flag",
                "material_doc", "material_doc_item_from", "material_doc_item_to",
                "reference", "purchase_order", "po_item", "posting_date", "source_file", "source_rule", "note"]
        return pd.DataFrame(columns=cols)

    def row_to_edge(self, kind, from_r, to_r, source_rule, confidence="HIGH", note="", alloc_qty=None) -> dict:
        uom_match = (clean_str(from_r["uom"]) == clean_str(to_r["uom"])) or not clean_str(from_r["uom"]) or not clean_str(to_r["uom"])
        if alloc_qty is None:
            alloc_qty = abs(float(from_r["qty"]))
        return {
            "edge_kind": kind, "confidence": confidence,
            "transition": f"{from_r['tier']} > {to_r['tier']}", "status": "VERIFIED_ACTUAL",
            "from_node": from_r["node"], "from_material": from_r["material"], "from_batch": from_r["batch"],
            "from_desc": from_r["material_desc"], "from_tier": from_r["tier"], "from_plant": from_r["plant"],
            "from_sloc": from_r["sloc"], "from_cmo": from_r["cmo"], "from_qty": from_r["qty"], "from_uom": from_r["uom"],
            "from_posting_date": from_r["posting_date"],
            "to_node": to_r["node"], "to_material": to_r["material"], "to_batch": to_r["batch"],
            "to_desc": to_r["material_desc"], "to_tier": to_r["tier"], "to_plant": to_r["plant"],
            "to_sloc": to_r["sloc"], "to_cmo": to_r["cmo"], "to_qty": to_r["qty"], "to_uom": to_r["uom"],
            "to_posting_date": to_r["posting_date"],
            "alloc_qty": alloc_qty, "uom_match": uom_match, "date_violation": False, "cycle_flag": False,
            "material_doc": to_r["material_doc"] or from_r["material_doc"],
            "material_doc_item_from": from_r["material_doc_item"], "material_doc_item_to": to_r["material_doc_item"],
            "reference": to_r["reference"] or from_r["reference"],
            "purchase_order": to_r["purchase_order"] or from_r["purchase_order"],
            "po_item": to_r["po_item"] or from_r["po_item"],
            "posting_date": to_r["posting_date"] or from_r["posting_date"],
            "source_file": to_r["source_file"] or from_r["source_file"],
            "source_rule": source_rule, "note": note,
        }

    def tier_ok_for_prod(self, from_tier, to_tier, from_material, to_material) -> bool:
        fi = TIER_ORDER.get(from_tier, 99); ti = TIER_ORDER.get(to_tier, 99)
        if fi == 99 or ti == 99: return False
        if fi < ti: return True
        if fi == ti and from_material != to_material: return True
        return False

    # A-3: 생산 엣지 — 다중 output 페어링 정확화 (D-1: dict 기반 고속화)
    def build_production_edges(self, rows: pd.DataFrame) -> pd.DataFrame:
        out_mv = MOVEMENT_CLASS["production_out"]
        in_mv = MOVEMENT_CLASS["production_consume"]
        eligible = rows[(rows["node"] != "") & (~rows["movement_type"].isin(self.ignored_movements))
                        & (rows["movement_type"].isin(out_mv | in_mv))].copy()
        if eligible.empty:
            return self.empty_edges()
        eligible = eligible.sort_values(["source_file", "material_doc", "material_doc_item", "row_id"])
        recs = eligible.to_dict("records")
        # 문서별 그룹핑 (순수 파이썬)
        from itertools import groupby as _gb
        edges: List[dict] = []
        keyf = lambda r: (r["source_file"], r["material_doc"])
        for (sf, doc), grp in _gb(recs, key=keyf):
            if not doc:
                continue
            g = list(grp)
            outputs = [r for r in g if r["movement_type"] in out_mv and r["qty"] > 0]
            inputs = [r for r in g if r["movement_type"] in in_mv and r["qty"] < 0]
            if not outputs or not inputs:
                continue
            single = len(outputs) == 1
            for input_r in inputs:
                chosen = self.choose_output_for_input(input_r, outputs, single)
                if chosen is None:
                    continue
                if single:
                    rule = "101/543 single-output"
                elif self.pairing_mode == "bom-aware":
                    rule = "101/543 BOM-aware scored pairing"
                else:
                    rule = "101/543 scored item-order pairing"
                edges.append(self.row_to_edge("PROD", input_r, chosen, rule))
        return pd.DataFrame(edges) if edges else self.empty_edges()

    def bom_consistent(self, from_material: str, to_material: str) -> bool:
        """BOM 마스터가 from_material 을 to_material 의 입력(부품)으로 명시하는지.

        legacy(1CNZ*) ↔ 현행(2CNY*) 코드 차이를 정규화해 비교한다.
        """
        to_cur = self.bom.legacy_to_current.get(to_material, to_material)
        inputs = self.bom.material_to_inputs.get(to_cur, []) or self.bom.material_to_inputs.get(to_material, [])
        if not inputs:
            return False
        from_cur = self.bom.legacy_to_current.get(from_material, from_material)
        inputs_cur = {self.bom.legacy_to_current.get(i, i) for i in inputs}
        return from_material in inputs or from_cur in inputs_cur

    def choose_output_for_input(self, input_r, output_items, single) -> Optional[dict]:
        cands = [o for o in output_items
                 if self.tier_ok_for_prod(input_r["tier"], o["tier"], input_r["material"], o["material"])]
        if not cands:
            return None
        if single:
            return cands[0]

        def _uom_pen(o):
            return 0 if (clean_str(o["uom"]) == clean_str(input_r["uom"]) or not o["uom"] or not input_r["uom"]) else 1

        if self.pairing_mode == "bom-aware":
            # A-3+ 점수: BOM 토폴로지 최우선 → tier 인접도 → UoM → 문서 라인 순서(약한 tiebreak)
            def score(o):
                bom_pen = 0 if self.bom_consistent(input_r["material"], o["material"]) else 1
                tier_gap = TIER_ORDER.get(o["tier"], 99) - TIER_ORDER.get(input_r["tier"], 99)
                tier_pen = 0 if tier_gap == 1 else (1 if tier_gap == 0 else 2)  # 인접 tier 최우선
                prior_bonus = 0 if o["material_doc_item"] < input_r["material_doc_item"] else 1
                item_dist = abs(int(o["material_doc_item"]) - int(input_r["material_doc_item"]))
                return (bom_pen, tier_pen, _uom_pen(o), prior_bonus, item_dist)
            return sorted(cands, key=score)[0]

        # legacy(기본) 점수: item 거리 + tier gap(상위일수록 선호) + UoM 불일치 패널티(A-4)
        def score(o):
            item_dist = abs(int(o["material_doc_item"]) - int(input_r["material_doc_item"]))
            prior_bonus = 0 if o["material_doc_item"] < input_r["material_doc_item"] else 1  # 직전 output 선호
            tier_gap = TIER_ORDER.get(o["tier"], 99) - TIER_ORDER.get(input_r["tier"], 99)
            tier_pen = 0 if tier_gap >= 1 else 3
            return (prior_bonus, item_dist, tier_pen, _uom_pen(o))
        return sorted(cands, key=score)[0]

    # A-1: REF 그룹키 빈 값 신뢰도 강등
    def build_reference_edges(self, rows: pd.DataFrame) -> pd.DataFrame:
        out_mv = MOVEMENT_CLASS["production_out"] | MOVEMENT_CLASS["production_consume"]
        eligible = rows[(rows["node"] != "") & (rows["reference"] != "")
                        & (~rows["movement_type"].isin(self.ignored_movements))
                        & (~rows["movement_type"].isin(out_mv))].copy()
        if eligible.empty:
            return self.empty_edges()
        return self.pair_negative_positive(
            eligible, ["source_file", "reference", "purchase_order", "po_item"],
            kind="REF_PO_ITEM", source_rule="neg->pos by Reference+PO+Item")

    def build_document_transfer_edges(self, rows: pd.DataFrame) -> pd.DataFrame:
        out_mv = MOVEMENT_CLASS["production_out"] | MOVEMENT_CLASS["production_consume"]
        eligible = rows[(rows["node"] != "") & (rows["material_doc"] != "")
                        & (~rows["movement_type"].isin(self.ignored_movements))
                        & (~rows["movement_type"].isin(out_mv))].copy()
        if eligible.empty:
            return self.empty_edges()
        return self.pair_negative_positive(
            eligible, ["source_file", "material_doc"],
            kind="DOC_TRANSFER", source_rule="neg->pos within material document")

    # A-2 분할매칭 + A-1 신뢰도 + A-4 UoM + C-4 잔차 (D-1: dict 기반 고속화)
    def pair_negative_positive(self, rows, group_cols, kind, source_rule) -> pd.DataFrame:
        from itertools import groupby as _gb
        edges: List[dict] = []
        seen_pairs: Set[Tuple] = set()
        sorted_rows = rows.sort_values(list(group_cols) + ["posting_date", "material_doc_item", "row_id"])
        recs = sorted_rows.to_dict("records")
        keyf = lambda r: tuple(r.get(c, "") for c in group_cols)
        for key, grp in _gb(recs, key=keyf):
            g = list(grp)
            if len(g) < 2:
                continue
            base_conf = "HIGH" if kind == "REF_PO_ITEM" else "MEDIUM"
            if kind == "REF_PO_ITEM":
                kd = dict(zip(group_cols, key))
                if not clean_str(kd.get("purchase_order", "")) and not clean_str(kd.get("po_item", "")):
                    base_conf = "LOW"
            neg = [r for r in g if r["qty"] < 0]
            pos = [r for r in g if r["qty"] > 0]
            if not neg or not pos:
                continue
            pos_remaining = {pi: abs(float(prow["qty"])) for pi, prow in enumerate(pos)}
            for nrow in neg:
                need = abs(float(nrow["qty"]))
                allocated = 0.0  # 이 neg에서 엣지로 배분된 누적 수량
                cands = [pi for pi in range(len(pos)) if self.is_valid_transfer_candidate(nrow, pos[pi])]
                cands.sort(key=lambda pi: self.transfer_score(nrow, pos[pi]))
                matched_any = False
                for pi in cands:
                    if pos_remaining.get(pi, 0) <= EPS or need <= EPS:
                        continue
                    prow = pos[pi]
                    same_uom = (clean_str(nrow["uom"]) == clean_str(prow["uom"])) or not nrow["uom"] or not prow["uom"]
                    # 분할(같은 UoM): 잔여 수량만큼, 그 외(분할 off/UoM 불일치): 1건 전량 배분
                    if self.split_matching and same_uom:
                        alloc = min(need, pos_remaining[pi])
                    else:
                        alloc = min(need, pos_remaining[pi]) if pos_remaining[pi] > 0 else need
                    pair_key = (kind, nrow["node"], prow["node"],
                                clean_str(nrow["reference"] or prow["reference"]),
                                clean_str(nrow["material_doc"] or prow["material_doc"]))
                    if pair_key in seen_pairs and not self.split_matching:
                        continue
                    seen_pairs.add(pair_key)
                    note = ("transfer/code/batch conversion"
                            if nrow["batch"] != prow["batch"] or nrow["material"] != prow["material"]
                            else "inventory location transfer")
                    if not same_uom:
                        note += " [UoM mismatch]"
                    edges.append(self.row_to_edge(kind, nrow, prow, source_rule,
                                                  confidence=base_conf, note=note, alloc_qty=alloc))
                    matched_any = True
                    # 버그수정: 전량/분할 경로 모두 need·pos_remaining·allocated를 일관 차감
                    pos_remaining[pi] = max(0.0, pos_remaining[pi] - alloc)
                    need -= alloc
                    allocated += alloc
                    if not (self.split_matching and same_uom):
                        # 비분할 경로는 1:1로 종료 (전량 배분 반영 후)
                        break
                    if need <= EPS:
                        break
                # C-4: neg 잔차 = 실제 배분 후 남은 수량만 (정상 매칭분은 제외)
                residual = need
                if residual > EPS:
                    rkind = "neg_residual" if matched_any else "neg_unmatched"
                    self.unmatched_rows.append(self._unmatched(nrow, rkind, residual, kind))
            # C-4: pos 잔차 (배분 후 남은 입고)
            if self.split_matching:
                for pi, rem in pos_remaining.items():
                    if rem > EPS:
                        self.unmatched_rows.append(self._unmatched(pos[pi], "pos_residual", rem, kind))
        return pd.DataFrame(edges) if edges else self.empty_edges()

    def _unmatched(self, r, kind_residual, qty, edge_kind) -> dict:
        return {"residual_kind": kind_residual, "edge_rule": edge_kind, "material": r["material"],
                "batch": r["batch"], "tier": r["tier"], "uom": r["uom"], "residual_qty": qty,
                "plant": r["plant"], "sloc": r["sloc"], "posting_date": r["posting_date"],
                "material_doc": r["material_doc"], "reference": r["reference"],
                "purchase_order": r["purchase_order"], "po_item": r["po_item"], "source_file": r["source_file"]}

    @staticmethod
    def is_valid_transfer_candidate(nrow, prow) -> bool:
        if nrow["node"] == prow["node"] and nrow["plant"] == prow["plant"] and nrow["sloc"] == prow["sloc"]:
            return False
        changed = (nrow["batch"] != prow["batch"] or nrow["material"] != prow["material"]
                   or nrow["plant"] != prow["plant"] or nrow["sloc"] != prow["sloc"])
        if not changed:
            return False
        nt = TIER_ORDER.get(nrow["tier"], 99); pt = TIER_ORDER.get(prow["tier"], 99)
        if nrow["material"] == prow["material"]:
            return True
        if abs(nt - pt) <= 1:
            return True
        return False

    @staticmethod
    def transfer_score(nrow, prow) -> Tuple:
        qty_diff = abs(abs(float(nrow["qty"])) - abs(float(prow["qty"])))
        mat_pen = 0 if nrow["material"] == prow["material"] else 5
        tier_pen = abs(TIER_ORDER.get(nrow["tier"], 99) - TIER_ORDER.get(prow["tier"], 99))
        batch_pen = 0 if nrow["batch"] != prow["batch"] else 1
        loc_pen = 0 if (nrow["plant"], nrow["sloc"]) != (prow["plant"], prow["sloc"]) else 1
        uom_pen = 0 if (clean_str(nrow["uom"]) == clean_str(prow["uom"]) or not nrow["uom"] or not prow["uom"]) else 4  # A-4
        return (uom_pen, qty_diff, mat_pen, tier_pen, batch_pen, loc_pen)

    # ----------------------------------------------------------
    # Graph / trace
    # ----------------------------------------------------------
    @staticmethod
    def build_adjacency(edges: pd.DataFrame):
        up: Dict[str, List[int]] = defaultdict(list)
        down: Dict[str, List[int]] = defaultdict(list)
        if edges.empty:
            return up, down
        for i, to_node, from_node in zip(edges.index, edges["to_node"].to_numpy(), edges["from_node"].to_numpy()):
            up[to_node].append(i)
            down[from_node].append(i)
        return up, down

    def build_nodes(self, rows, edges) -> pd.DataFrame:
        base = rows[rows["node"] != ""].copy()
        if base.empty:
            return pd.DataFrame(columns=["node", "material", "batch", "tier", "description", "cmo", "plant", "sloc"])
        agg = (base.groupby(["node", "material", "batch", "tier"], dropna=False)
               .agg(description=("material_desc", first_nonblank),
                    cmo=("cmo", join_unique), plant=("plant", join_unique), sloc=("sloc", join_unique),
                    first_posting_date=("posting_date", lambda x: first_nonblank(sorted([v for v in x if v]))),
                    last_posting_date=("posting_date", lambda x: last_nonblank(sorted([v for v in x if v]))),
                    row_count=("row_id", "count")).reset_index())
        return agg

    def resolve_batch(self, batch, material=None):
        b = clean_code(batch); m = clean_code(material) if material else ""
        cand = self.nodes[self.nodes["batch"] == b].copy()
        if m:
            cand = cand[cand["material"] == m]
        return cand["node"].tolist(), cand

    def trace(self, batch, material=None, direction="upstream", max_depth=DEFAULT_MAX_DEPTH):
        seeds, candidates = self.resolve_batch(batch, material)
        warnings: List[str] = []
        cycles: List[dict] = []
        if not seeds:
            warnings.append(f"No node found for batch={batch}, material={material or ''}")
            return self.empty_edges(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"warnings": warnings, "candidates": []}
        if len(seeds) > 1:
            warnings.append("Batch resolved to multiple material nodes; all candidates traced. Pass --material to force one.")

        trace_edge_indices: List[int] = []
        visited_edges: Set[int] = set()
        visited_nodes: Set[str] = set(seeds)

        # C-1: path 기반 사이클 가드
        def run_bfs(adj, get_next, seed_nodes):
            q = deque((n, 0, frozenset([n])) for n in seed_nodes)
            while q:
                node, depth, path = q.popleft()
                if depth >= max_depth:
                    continue
                for ei in adj.get(node, []):
                    nxt = get_next(self.edges.loc[ei])
                    if nxt and nxt in path:
                        cycles.append({"at_node": node, "next_node": nxt, "edge_id": self.edges.loc[ei, "edge_id"]})
                        self.edges.at[ei, "cycle_flag"] = True
                        continue
                    if ei not in visited_edges:
                        visited_edges.add(ei)
                        trace_edge_indices.append(ei)
                    if nxt and nxt not in visited_nodes:
                        visited_nodes.add(nxt)
                        q.append((nxt, depth + 1, path | {nxt}))

        d = direction.lower()
        if d in {"up", "upstream", "bwd", "backward", "both"}:
            run_bfs(self.up_adj, lambda e: e["from_node"], seeds)
        if d in {"down", "downstream", "fwd", "forward", "both"}:
            run_bfs(self.down_adj, lambda e: e["to_node"], seeds)

        trace_edges = self.edges.loc[trace_edge_indices].copy() if trace_edge_indices else self.empty_edges()
        if not trace_edges.empty:
            trace_edges = self.add_trace_depth(trace_edges, seeds, direction, max_depth)
        trace_nodes = self.node_summary(visited_nodes, seeds)
        expected = self.bom_expected_for_nodes(visited_nodes, trace_edges)
        usage = self.trace_node_usage(trace_edges)
        meta = {"warnings": warnings, "cycles": cycles, "cycle_count": len(cycles),
                "candidate_count": len(candidates), "candidates": candidates.to_dict("records"),
                "seed_nodes": seeds, "edge_count": int(len(trace_edges)), "node_count": int(len(trace_nodes)),
                "expected_count": int(len(expected)),
                "date_violations": int(trace_edges["date_violation"].sum()) if not trace_edges.empty else 0,
                "scope_note": self.scope_note}
        return trace_edges, trace_nodes, usage, expected, meta

    def add_trace_depth(self, trace_edges, seeds, direction, max_depth):
        depth_by_edge: Dict[str, int] = {}
        edge_id_set = set(trace_edges["edge_id"])
        visited_edges: Set[str] = set()
        def bfs(adj, next_col):
            q = deque((n, 0) for n in seeds)
            while q:
                n, depth = q.popleft()
                if depth >= max_depth:
                    continue
                for ei in adj.get(n, []):
                    eid = self.edges.loc[ei, "edge_id"]
                    if eid not in edge_id_set or eid in visited_edges:
                        continue
                    visited_edges.add(eid)
                    depth_by_edge[eid] = depth + 1
                    q.append((self.edges.loc[ei, next_col], depth + 1))
        d = direction.lower()
        if d in {"up", "upstream", "bwd", "backward", "both"}:
            bfs(self.up_adj, "from_node")
        if d in {"down", "downstream", "fwd", "forward", "both"}:
            bfs(self.down_adj, "to_node")
        te = trace_edges.copy()
        te["depth"] = te["edge_id"].map(depth_by_edge).fillna(0).astype(int)
        return te.sort_values(["depth", "edge_kind", "from_tier", "to_tier", "posting_date"])

    def node_summary(self, visited_nodes, seeds) -> pd.DataFrame:
        if not visited_nodes:
            return pd.DataFrame()
        ns = self.nodes[self.nodes["node"].isin(visited_nodes)].copy()
        missing = sorted(visited_nodes - set(ns["node"]))
        if missing:
            rows = []
            for nid in missing:
                mat, bat = split_node_id(nid)
                rows.append({"node": nid, "material": mat, "batch": bat, "tier": self.classify_tier(mat),
                             "description": self.bom.material_to_desc.get(mat, ""), "cmo": "", "plant": "", "sloc": "",
                             "first_posting_date": "", "last_posting_date": "", "row_count": 0})
            ns = pd.concat([ns, pd.DataFrame(rows)], ignore_index=True)
        ns["is_seed"] = ns["node"].isin(seeds)
        ns["legacy_current_code"] = ns["material"].map(self.bom.legacy_to_current).fillna("")
        ns["tier_rank"] = ns["tier"].map(lambda x: TIER_ORDER.get(x, 99))
        return ns.sort_values(["tier_rank", "material", "batch"]).drop(columns=["tier_rank"])

    # A-4: usage 집계를 (material,batch,uom) 단위로
    def trace_node_usage(self, trace_edges) -> pd.DataFrame:
        if trace_edges.empty:
            return pd.DataFrame()
        tmp = trace_edges.copy()
        tmp["alloc_abs"] = tmp["alloc_qty"].astype(float).abs()
        tmp["manuf_abs"] = tmp.apply(lambda r: float(abs(r["alloc_qty"])) if r["edge_kind"] == "PROD" else 0.0, axis=1)
        tmp["transfer_abs"] = tmp.apply(lambda r: float(abs(r["alloc_qty"])) if r["edge_kind"] != "PROD" else 0.0, axis=1)
        cols = ["from_material", "from_batch", "from_desc", "from_tier", "from_uom"]
        usage = (tmp.groupby(cols, dropna=False)
                 .agg(manufacturing_consumed_qty_abs=("manuf_abs", "sum"),
                      transfer_moved_qty_abs=("transfer_abs", "sum"),
                      all_edge_alloc_qty_abs=("alloc_abs", "sum"),
                      edge_count=("edge_id", "count"),
                      consumed_into_materials=("to_material", join_unique),
                      consumed_into_batches=("to_batch", join_unique),
                      source_edges=("edge_kind", join_unique)).reset_index()
                 .rename(columns={"from_material": "material", "from_batch": "batch", "from_desc": "description",
                                  "from_tier": "tier", "from_uom": "uom"}))
        usage["tier_rank"] = usage["tier"].map(lambda x: TIER_ORDER.get(x, 99))
        return usage.sort_values(["tier_rank", "material", "batch"]).drop(columns=["tier_rank"])

    def actual_upstream_materials_for_node(self, node, trace_edges) -> Set[str]:
        if trace_edges.empty:
            return set()
        return set(trace_edges.loc[trace_edges["to_node"] == node, "from_material"].dropna().astype(str))

    # ----------------------------------------------------------
    # D-2: 일괄 추적
    # ----------------------------------------------------------
    def seed_batches_for_scope(self, scope: str) -> List[Tuple[str, str]]:
        """scope='all-fp'|'all-leaf'|'all' → (material,batch) 시드 목록."""
        if self.nodes.empty:
            return []
        ns = self.nodes
        if scope == "all":
            sel = ns
        elif scope == "all-fp":
            sel = ns[ns["tier"] == "FP"]
        elif scope == "all-leaf":
            # 다른 노드의 input으로 소비되지 않는 최종 산출(엣지의 from_node에 없는 to-only)
            if self.edges.empty:
                sel = ns
            else:
                consumed = set(self.edges["from_node"])
                sel = ns[~ns["node"].isin(consumed)]
        else:
            sel = ns[ns["tier"] == "FP"]
        return list(zip(sel["material"], sel["batch"]))

    def trace_many(self, seeds: List[Tuple[str, str]], direction="upstream", max_depth=DEFAULT_MAX_DEPTH):
        """여러 (material,batch) 시드를 일괄 추적. 통합 트레이스 엣지/노드/BOM_EXPECTED/요약 반환."""
        all_edges = []
        all_expected = []
        index_rows = []
        seen_edge_ids: Set[str] = set()
        node_union: Set[str] = set()
        cycle_total = 0
        for mat, bat in seeds:
            te, tn, tu, be, meta = self.trace(batch=bat, material=mat, direction=direction, max_depth=max_depth)
            n_edges = 0 if te.empty else len(te)
            if not te.empty:
                te = te.copy()
                te["trace_seed"] = f"{mat}||{bat}"
                all_edges.append(te)
                seen_edge_ids |= set(te["edge_id"])
            if be is not None and not be.empty:
                be = be.copy()
                be["trace_seed"] = f"{mat}||{bat}"
                all_expected.append(be)
            node_union |= set(meta.get("seed_nodes", []))
            cycle_total += meta.get("cycle_count", 0)
            index_rows.append({
                "seed_material": mat, "seed_batch": bat, "seed_tier": self.classify_tier(mat),
                "seed_desc": self.bom.material_to_desc.get(mat, ""),
                "edge_count": n_edges, "node_count": meta.get("node_count", 0),
                "expected_missing": meta.get("expected_count", 0),
                "date_violations": meta.get("date_violations", 0),
                "cycles": meta.get("cycle_count", 0),
                "candidates": meta.get("candidate_count", 0),
            })
        combined = pd.concat(all_edges, ignore_index=True) if all_edges else self.empty_edges()
        expected_combined = pd.concat(all_expected, ignore_index=True).drop_duplicates() if all_expected else pd.DataFrame()
        index_df = pd.DataFrame(index_rows)
        summary = {
            "seed_count": len(seeds), "traced_with_edges": int((index_df["edge_count"] > 0).sum()) if not index_df.empty else 0,
            "total_unique_edges": len(seen_edge_ids), "total_cycles": cycle_total,
            "total_bom_expected": int(len(expected_combined)),
            "direction": direction, "scope_note": self.scope_note,
        }
        return combined, index_df, expected_combined, summary

    def bom_expected_for_nodes(self, visited_nodes, trace_edges) -> pd.DataFrame:
        rows: List[dict] = []
        processed: Set[Tuple[str, str]] = set()
        def add_expected_chain(to_material, to_batch, to_node, depth, reason):
            if depth > 6:
                return
            if to_material in self.bom.legacy_to_current:
                current = self.bom.legacy_to_current[to_material]
                rows.append({"status": "LEGACY_API_NO_RSM_ACTUAL", "depth": depth,
                             "from_material_expected": current,
                             "from_material_desc_expected": self.bom.material_to_desc.get(current, ""),
                             "from_batch_expected": "<NO_ACTUAL_RSM_BATCH>", "from_tier_expected": self.classify_tier(current),
                             "to_material": to_material, "to_batch": to_batch, "to_node": to_node,
                             "reason": "legacy 1CNZ* API: current 2CNY* shown, actual RSM batch not available"})
                return
            inputs = self.bom.material_to_inputs.get(to_material, [])
            if not inputs:
                return
            actual_inputs = self.actual_upstream_materials_for_node(to_node, trace_edges)
            if to_material.startswith("5CNB") and actual_inputs.intersection(set(inputs)):
                return
            for inp in inputs:
                key = (inp, to_node)
                if key in processed:
                    continue
                processed.add(key)
                if inp in actual_inputs:
                    continue
                rows.append({"status": "BOM_EXPECTED_MISSING_ACTUAL", "depth": depth,
                             "from_material_expected": inp,
                             "from_material_desc_expected": self.bom.material_to_desc.get(inp, ""),
                             "from_batch_expected": "<MISSING_IN_SAP_EXTRACT>", "from_tier_expected": self.classify_tier(inp),
                             "to_material": to_material, "to_batch": to_batch, "to_node": to_node, "reason": reason})
                add_expected_chain(inp, "<MISSING_IN_SAP_EXTRACT>", node_id(inp, "<MISSING_IN_SAP_EXTRACT>"),
                                   depth + 1, "recursive BOM expected upstream")
        for nid in sorted(visited_nodes):
            mat, bat = split_node_id(nid)
            add_expected_chain(mat, bat, nid, 1, "no verified actual upstream edge for this BOM input in supplied SAP extract")
        return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()

    def unlinked_batches(self) -> pd.DataFrame:
        out_mv = MOVEMENT_CLASS["production_out"]
        prod = self.rows[(self.rows["node"] != "") & (self.rows["movement_type"].isin(out_mv))
                         & (self.rows["qty"] > 0) & (~self.rows["movement_type"].isin(self.ignored_movements))].copy()
        if prod.empty:
            return pd.DataFrame()
        linked_to = set(self.edges["to_node"]) if not self.edges.empty else set()
        prod["has_actual_upstream"] = prod["node"].isin(linked_to)
        prod["has_bom_input"] = prod["material"].map(lambda m: bool(self.bom.material_to_inputs.get(m, [])))
        out = prod[(prod["has_bom_input"]) & (~prod["has_actual_upstream"])].copy()
        if out.empty:
            return pd.DataFrame()
        out["status"] = "MISSING_HISTORY_OR_SCOPE"
        out["expected_inputs"] = out["material"].map(lambda m: ", ".join(self.bom.material_to_inputs.get(m, [])))
        keep = ["status", "tier", "material", "material_desc", "batch", "plant", "sloc", "cmo", "qty", "uom",
                "posting_date", "material_doc", "purchase_order", "po_item", "source_file", "expected_inputs"]
        return out[keep].drop_duplicates()

    def unmatched_quantity(self) -> pd.DataFrame:  # C-4
        return pd.DataFrame(self.unmatched_rows) if self.unmatched_rows else pd.DataFrame()

    def derive_scope_note(self) -> str:  # C-5
        n_files = self.rows["source_file"].nunique() if not self.rows.empty else 0
        if n_files <= 1:
            return ("scope=single SAP export: 상류 이력 부재(BOM_EXPECTED)는 데이터 범위 한계이며 오류가 아님. "
                    "전체 genealogy는 연속 기간의 다중 MB51 export 병합 시 완성됨.")
        return f"scope={n_files} SAP exports merged."

    # ----------------------------------------------------------
    # Exports
    # ----------------------------------------------------------
    def export_all(self, out_dir, trace_edges=None, trace_nodes=None, trace_usage=None,
                   bom_expected=None, meta=None, export_xlsx=False) -> Dict[str, str]:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        outputs: Dict[str, str] = {}
        def save_csv(df, name):
            path = os.path.join(out_dir, name)
            (df if df is not None else pd.DataFrame()).to_csv(path, index=False, encoding="utf-8-sig")
            outputs[name] = path
        save_csv(self.rows, "normalized_sap_rows.csv")
        save_csv(self.edges, "genealogy_edges_actual.csv")
        save_csv(self.bom.bom_edges, "bom_expected_edges_master.csv")
        save_csv(self.nodes, "genealogy_nodes.csv")
        save_csv(self.unlinked_batches(), "unlinked_or_missing_history.csv")
        save_csv(self.unmatched_quantity(), "unmatched_quantity_residual.csv")  # C-4
        if trace_edges is not None: save_csv(trace_edges, "trace_edges_line_level.csv")
        if trace_nodes is not None: save_csv(trace_nodes, "trace_nodes.csv")
        if trace_usage is not None: save_csv(trace_usage, "trace_node_usage_aggregate.csv")
        if bom_expected is not None: save_csv(bom_expected, "trace_bom_expected_missing.csv")
        if meta is not None:
            path = os.path.join(out_dir, "trace_meta.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2, default=str)
            outputs["trace_meta.json"] = path
        if export_xlsx:
            xlsx_path = os.path.join(out_dir, "genealogy_output.xlsx")
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
                self.edges.to_excel(w, sheet_name="Actual_Edges", index=False)
                self.nodes.to_excel(w, sheet_name="Nodes", index=False)
                self.unlinked_batches().to_excel(w, sheet_name="Missing_History", index=False)
                self.unmatched_quantity().to_excel(w, sheet_name="Unmatched_Qty", index=False)
                self.bom.bom_edges.to_excel(w, sheet_name="BOM_Expected_Master", index=False)
                if trace_edges is not None: trace_edges.to_excel(w, sheet_name="Trace_Line_Level", index=False)
                if trace_nodes is not None: trace_nodes.to_excel(w, sheet_name="Trace_Nodes", index=False)
                if trace_usage is not None: trace_usage.to_excel(w, sheet_name="Trace_Aggregate", index=False)
                if bom_expected is not None: bom_expected.to_excel(w, sheet_name="Trace_BOM_Missing", index=False)
            outputs["genealogy_output.xlsx"] = xlsx_path
        return outputs

    # ----------------------------------------------------------
    # Phase 1: genealogy 결과 DB화 (frontend/누적 조회용)
    # 기존 CSV/XLSX 출력과 독립. sqlite 표준 스키마(향후 Postgres 이전 가능).
    # ----------------------------------------------------------
    def write_results_db(self, db_path: str, run_id: Optional[str] = None,
                         replace: bool = False) -> str:
        """nodes/edges/bom_expected_master 를 결과 sqlite 로 적재하고 run_id 반환.

        - replace=False(기본): run_id 를 붙여 append (빌드 이력 누적)
        - replace=True: 기존 결과를 비우고 이번 빌드만 남김
        build_runs 레지스트리와 최신 스냅샷 뷰(v_latest_*)도 함께 관리한다.
        """
        run_id = run_id or datetime.datetime.now().strftime("run_%Y%m%dT%H%M%S")
        built_at = datetime.datetime.now().isoformat(timespec="seconds")
        date_violations = int(self.edges["date_violation"].sum()) if not self.edges.empty else 0

        def _stamp(df: pd.DataFrame) -> pd.DataFrame:
            out = df.copy()
            out.insert(0, "run_id", run_id)
            return out

        Path(os.path.dirname(db_path) or ".").mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS build_runs (
                run_id TEXT PRIMARY KEY, built_at TEXT, sap_files TEXT, bom_db TEXT,
                pairing_mode TEXT, sap_rows INTEGER, edge_count INTEGER, node_count INTEGER,
                date_violations INTEGER, scope_note TEXT)""")
            mode = "replace" if replace else "append"
            if replace:
                cur.execute("DELETE FROM build_runs")
            _stamp(self.nodes).to_sql("gen_nodes", con, if_exists=mode, index=False)
            _stamp(self.edges).to_sql("gen_edges", con, if_exists=mode, index=False)
            _stamp(self.bom.bom_edges).to_sql("gen_bom_expected", con, if_exists=mode, index=False)
            cur.execute("INSERT OR REPLACE INTO build_runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
                run_id, built_at, json.dumps(self.sap_files, ensure_ascii=False), self.bom_db,
                self.pairing_mode, len(self.rows), len(self.edges), len(self.nodes),
                date_violations, self.scope_note))
            # 최신 빌드 스냅샷 뷰 (frontend 기본 조회 대상)
            cur.executescript("""
                DROP VIEW IF EXISTS v_latest_run;
                CREATE VIEW v_latest_run AS
                    SELECT run_id FROM build_runs ORDER BY built_at DESC, run_id DESC LIMIT 1;
                DROP VIEW IF EXISTS v_latest_edges;
                CREATE VIEW v_latest_edges AS
                    SELECT e.* FROM gen_edges e WHERE e.run_id IN (SELECT run_id FROM v_latest_run);
                DROP VIEW IF EXISTS v_latest_nodes;
                CREATE VIEW v_latest_nodes AS
                    SELECT n.* FROM gen_nodes n WHERE n.run_id IN (SELECT run_id FROM v_latest_run);
                DROP VIEW IF EXISTS v_latest_bom_expected;
                CREATE VIEW v_latest_bom_expected AS
                    SELECT b.* FROM gen_bom_expected b WHERE b.run_id IN (SELECT run_id FROM v_latest_run);
            """)
            con.commit()
        finally:
            con.close()
        return run_id


def render_html(trace_edges: pd.DataFrame, trace_nodes: pd.DataFrame, bom_expected: pd.DataFrame,
                meta: dict, title: str, out_path: str) -> str:
    """D-3: genealogy를 단일 HTML(SVG 트리)로 렌더. 외부 의존성 없음."""
    TIER_COL = {"RSM": "#64748b", "API": "#0ea5e9", "DP": "#8b5cf6", "SP": "#f59e0b", "FP": "#10b981", "OTHER": "#94a3b8"}
    KIND_COL = {"PROD": "#0ea5e9", "REF_PO_ITEM": "#8b5cf6", "DOC_TRANSFER": "#94a3b8", "BOM_EXPECTED": "#f59e0b"}
    nodes_meta: Dict[str, dict] = {}
    if trace_nodes is not None and not trace_nodes.empty:
        for r in trace_nodes.to_dict("records"):
            nodes_meta[r["node"]] = r
    # 엣지(실제) + BOM_EXPECTED(점선)를 그래프 엣지로 통합
    e_list = []
    if trace_edges is not None and not trace_edges.empty:
        for r in trace_edges.to_dict("records"):
            e_list.append({"frm": r["from_node"], "to": r["to_node"], "kind": r["edge_kind"],
                           "from_tier": r["from_tier"], "to_tier": r["to_tier"],
                           "from_label": f'{r["from_material"]} {r["from_batch"]}',
                           "to_label": f'{r["to_material"]} {r["to_batch"]}',
                           "alloc": r.get("alloc_qty", ""), "uom": r.get("from_uom", ""),
                           "conf": r.get("confidence", ""), "cycle": bool(r.get("cycle_flag", False)),
                           "dv": bool(r.get("date_violation", False)), "cmo": r.get("from_cmo", "")})
    exp_list = []
    if bom_expected is not None and not bom_expected.empty:
        for r in bom_expected.to_dict("records"):
            exp_list.append({"frm": node_id(r["from_material_expected"], r.get("from_batch_expected", "")),
                             "to": r["to_node"], "kind": "BOM_EXPECTED",
                             "from_tier": r.get("from_tier_expected", "OTHER"), "to_tier": "",
                             "from_label": f'{r["from_material_expected"]} (expected)',
                             "to_label": "", "status": r.get("status", "")})
    # 노드 집합 & tier 레이어 배치
    all_nodes: Dict[str, dict] = {}
    def reg(nid, tier, label, cmo="", is_expected=False):
        if nid not in all_nodes:
            all_nodes[nid] = {"id": nid, "tier": tier or "OTHER", "label": label, "cmo": cmo, "expected": is_expected}
    for e in e_list:
        reg(e["frm"], e["from_tier"], e["from_label"], e.get("cmo", ""))
        reg(e["to"], e["to_tier"], e["to_label"])
    for e in exp_list:
        reg(e["frm"], e["from_tier"], e["from_label"], is_expected=True)
    # 레이어 = tier 순서 (RSM 좌→FP 우)
    layers: Dict[int, List[str]] = defaultdict(list)
    for nid, nd in all_nodes.items():
        layers[TIER_ORDER.get(nd["tier"], 99)].append(nid)
    layer_keys = sorted(layers.keys())
    # 좌표
    NW, NH, HGAP, VGAP, PAD = 150, 46, 90, 20, 40
    pos: Dict[str, Tuple[float, float]] = {}
    max_rows = max((len(v) for v in layers.values()), default=1)
    for li, lk in enumerate(layer_keys):
        x = PAD + li * (NW + HGAP)
        col = layers[lk]
        for ri, nid in enumerate(col):
            y = PAD + ri * (NH + VGAP)
            pos[nid] = (x, y)
    W = PAD * 2 + (len(layer_keys)) * (NW + HGAP)
    H = PAD * 2 + max_rows * (NH + VGAP) + 40
    # SVG
    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;font-family:Arial,sans-serif">']
    def edge_path(a, b, color, dashed, w=2):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        sx, sy = x1 + NW, y1 + NH / 2
        ex, ey = x2, y2 + NH / 2
        mx = (sx + ex) / 2
        d = f"M {sx} {sy} C {mx} {sy}, {mx} {ey}, {ex} {ey}"
        dash = 'stroke-dasharray="5 4"' if dashed else ''
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" {dash}/>'
    # 실제 엣지
    for e in e_list:
        if e["frm"] in pos and e["to"] in pos:
            col = "#ef4444" if (e.get("cycle") or e.get("dv")) else KIND_COL.get(e["kind"], "#94a3b8")
            svg.append(edge_path(e["frm"], e["to"], col, dashed=False, w=2.4 if e["kind"] == "PROD" else 1.8))
    # 기대 엣지(점선)
    for e in exp_list:
        if e["frm"] in pos and e["to"] in pos:
            svg.append(edge_path(e["frm"], e["to"], KIND_COL["BOM_EXPECTED"], dashed=True, w=1.6))
    # 노드
    for nid, nd in all_nodes.items():
        if nid not in pos:
            continue
        x, y = pos[nid]
        col = TIER_COL.get(nd["tier"], "#94a3b8")
        fill = "#fff" if not nd["expected"] else "#fffbeb"
        dash = 'stroke-dasharray="4 3"' if nd["expected"] else ''
        mat, bat = split_node_id(nid)
        mat_e, bat_e = html.escape(mat), html.escape(bat)
        svg.append(f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="8" fill="{fill}" stroke="{col}" stroke-width="2" {dash}/>')
        svg.append(f'<rect x="{x}" y="{y}" width="6" height="{NH}" rx="3" fill="{col}"/>')
        svg.append(f'<text x="{x+14}" y="{y+18}" font-size="11" font-weight="700" fill="#0f172a">{mat_e}</text>')
        svg.append(f'<text x="{x+14}" y="{y+33}" font-size="10" fill="#475569">{bat_e or ("expected" if nd["expected"] else "")}</text>')
        if nd.get("cmo"):
            svg.append(f'<text x="{x+NW-6}" y="{y+12}" text-anchor="end" font-size="8" fill="{col}">{html.escape(str(nd["cmo"]))}</text>')
    # tier 헤더
    for li, lk in enumerate(layer_keys):
        x = PAD + li * (NW + HGAP)
        svg.append(f'<text x="{x+NW/2}" y="20" text-anchor="middle" font-size="12" font-weight="800" fill="{TIER_COL.get(ORDER_TIER.get(lk,"OTHER"),"#475569")}">{ORDER_TIER.get(lk,"OTHER")}</text>')
    svg.append("</svg>")
    svg_str = "\n".join(svg)
    # 메타 요약
    cyc = meta.get("cycle_count", meta.get("total_cycles", 0))
    dvv = meta.get("date_violations", 0)
    legend = """
    <div class="lg">
      <span><i style="background:#0ea5e9"></i>PROD(생산)</span>
      <span><i style="background:#8b5cf6"></i>REF/PO</span>
      <span><i style="background:#94a3b8"></i>DOC 이동</span>
      <span><i style="background:#f59e0b"></i>BOM_EXPECTED(점선)</span>
      <span><i style="background:#ef4444"></i>사이클/날짜역전</span>
    </div>"""
    html_doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body{{font-family:Arial,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
 header{{background:#1e3a5f;color:#fff;padding:14px 20px}}
 header h1{{margin:0;font-size:16px}} header .sub{{font-size:12px;opacity:.85;margin-top:4px}}
 .bar{{display:flex;gap:18px;padding:10px 20px;background:#fff;border-bottom:1px solid #e2e8f0;font-size:12px;flex-wrap:wrap}}
 .bar b{{font-size:15px}} .kpi{{color:#475569}}
 .wrap{{padding:16px 20px;overflow:auto}}
 .lg{{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;padding:8px 20px;color:#475569}}
 .lg i{{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:middle}}
 .warn{{color:#b91c1c;font-weight:700}}
</style></head><body>
<header><h1>🧬 {html.escape(title)}</h1><div class="sub">{html.escape(meta.get("scope_note",""))}</div></header>
<div class="bar">
 <span class="kpi">실제 엣지 <b>{len(e_list)}</b></span>
 <span class="kpi">노드 <b>{len([n for n in all_nodes.values() if not n['expected']])}</b></span>
 <span class="kpi">BOM_EXPECTED <b>{len(exp_list)}</b></span>
 <span class="kpi {'warn' if cyc else ''}">사이클 <b>{cyc}</b></span>
 <span class="kpi {'warn' if dvv else ''}">날짜역전 <b>{dvv}</b></span>
</div>
{legend}
<div class="wrap">{svg_str}</div>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return out_path


def print_summary(tool: GenealogyTool, meta=None) -> None:
    print("\n=== Genealogy Build Summary (v2) ===")
    print(f"SAP rows: {len(tool.rows):,}")
    print(f"Actual edges: {len(tool.edges):,}")
    if not tool.edges.empty:
        print(tool.edges["edge_kind"].value_counts().to_string())
        print(f"  date_violations: {int(tool.edges['date_violation'].sum())}")
    print(f"Nodes: {len(tool.nodes):,}")
    print(f"Unlinked/missing-history: {len(tool.unlinked_batches()):,}")
    print(f"Unmatched-qty residual rows: {len(tool.unmatched_quantity()):,}")
    print(f"Scope: {tool.scope_note}")
    if tool.build_warnings:
        print("Build warnings:", "; ".join(tool.build_warnings))
    if meta:
        print("\n=== Trace Summary ===")
        slim = {k: v for k, v in meta.items() if k != "candidates"}
        print(json.dumps(slim, ensure_ascii=False, indent=2, default=str)[:3500])


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Cenobamate batch genealogy tracer v2")
    p.add_argument("--sap", nargs="+", required=True)
    p.add_argument("--bom-db", required=True)
    p.add_argument("--batch")
    p.add_argument("--material")
    p.add_argument("--direction", default="upstream", choices=["upstream", "downstream", "both"])
    p.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    p.add_argument("--out", default="genealogy_out")
    p.add_argument("--export-xlsx", action="store_true")
    p.add_argument("--include-reversals", action="store_true")
    p.add_argument("--exclude-movements", default="921,925")
    p.add_argument("--no-split-matching", action="store_true", help="1:1 매칭만(하위호환)")
    p.add_argument("--strict-dates", action="store_true", help="날짜 역전 엣지 제외")
    p.add_argument("--pairing-mode", choices=["legacy", "bom-aware"], default="bom-aware",
                   help="다중 output 생산 페어링 점수식 (bom-aware=기본/BOM 토폴로지 우선, legacy=하위호환/구 item-순서)")
    p.add_argument("--write-db", metavar="PATH",
                   help="genealogy 결과(nodes/edges/bom_expected)를 결과 sqlite 로 적재 (frontend/누적 조회용)")
    p.add_argument("--db-run-id", help="결과 DB 적재 시 run_id 지정(미지정 시 타임스탬프)")
    p.add_argument("--db-replace", action="store_true",
                   help="결과 DB 의 기존 빌드를 비우고 이번 빌드만 남김(기본: append 누적)")
    p.add_argument("--batch-list", help="배치 목록 파일(줄당 'batch' 또는 'batch,material') 일괄 추적")
    p.add_argument("--trace-scope", choices=["all-fp", "all-leaf", "all"], help="시드 자동 선택 일괄 추적")
    p.add_argument("--html", action="store_true", help="genealogy HTML 시각화 생성")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    excluded = {parse_int(x) for x in args.exclude_movements.split(",") if clean_str(x)}
    tool = GenealogyTool(sap_files=args.sap, bom_db=args.bom_db, include_reversals=args.include_reversals,
                         excluded_movements=excluded, split_matching=not args.no_split_matching,
                         strict_dates=args.strict_dates, pairing_mode=args.pairing_mode)
    trace_edges = trace_nodes = trace_usage = bom_expected = meta = None
    Path(args.out).mkdir(parents=True, exist_ok=True)

    # D-2: 일괄 추적 (배치 리스트 또는 scope)
    batch_seeds: List[Tuple[str, str]] = []
    if args.batch_list and os.path.exists(args.batch_list):
        for line in open(args.batch_list, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in re.split(r"[,\t]", line)]
            bat = parts[0]
            mat = parts[1] if len(parts) > 1 else None
            for nid in tool.resolve_batch(bat, mat)[0]:
                m_, b_ = split_node_id(nid)
                batch_seeds.append((m_, b_))
            if not tool.resolve_batch(bat, mat)[0]:
                batch_seeds.append((mat or "", bat))
    if args.trace_scope:
        batch_seeds = tool.seed_batches_for_scope(args.trace_scope)

    if batch_seeds:
        combined, index_df, expected_combined, summary = tool.trace_many(batch_seeds, direction=args.direction, max_depth=args.max_depth)
        combined.to_csv(os.path.join(args.out, "batch_trace_edges_combined.csv"), index=False, encoding="utf-8-sig")
        index_df.to_csv(os.path.join(args.out, "batch_trace_index.csv"), index=False, encoding="utf-8-sig")
        expected_combined.to_csv(os.path.join(args.out, "batch_trace_bom_expected.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(args.out, "batch_trace_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n=== Batch Trace (seeds={summary['seed_count']}, with_edges={summary['traced_with_edges']}, "
              f"unique_edges={summary['total_unique_edges']}, bom_expected={summary['total_bom_expected']}, "
              f"cycles={summary['total_cycles']}) ===")
        if args.html and not combined.empty:
            meta_h = {"scope_note": tool.scope_note, "total_cycles": summary["total_cycles"],
                      "date_violations": int(combined["date_violation"].sum())}
            tnodes = tool.node_summary(set(combined["from_node"]) | set(combined["to_node"]), [])
            hp = render_html(combined, tnodes, pd.DataFrame(), meta_h,
                             f"Batch Genealogy ({args.trace_scope or args.batch_list})",
                             os.path.join(args.out, "genealogy_batch.html"))
            print(f"HTML: {hp}")

    # 단건 추적
    if args.batch:
        trace_edges, trace_nodes, trace_usage, bom_expected, meta = tool.trace(
            batch=args.batch, material=args.material, direction=args.direction, max_depth=args.max_depth)
        if args.html:
            hp = render_html(trace_edges, trace_nodes, bom_expected, meta,
                             f"Genealogy: {args.material or ''} / batch {args.batch} ({args.direction})",
                             os.path.join(args.out, "genealogy_trace.html"))
            print(f"HTML: {hp}")

    outputs = tool.export_all(args.out, trace_edges, trace_nodes, trace_usage, bom_expected, meta, args.export_xlsx)
    if args.write_db:
        run_id = tool.write_results_db(args.write_db, run_id=args.db_run_id, replace=args.db_replace)
        outputs[f"results_db ({run_id})"] = args.write_db
    print_summary(tool, meta)
    print("\n=== Output files ===")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
