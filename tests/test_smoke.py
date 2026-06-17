"""genealogy_tool 스모크/회귀 테스트 (pytest 불필요, 단독 실행 가능).

합성 SAP fixture(tests/synth_sap.py)로 GenealogyTool 을 빌드해
엣지 3규칙·날짜위반·reversal/exclude·tier 분류·추적 체인을 검증한다.

실행:
    python tests/test_smoke.py
    (pytest 가 있으면) pytest tests/test_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import genealogy_tool as gt  # noqa: E402
from synth_sap import write_synthetic_sap  # noqa: E402

BOM_DB = os.path.join(ROOT, "data", "Cenobamate_BOM_DB_v1.sqlite")


def _build(strict_dates=False):
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    write_synthetic_sap(tmp.name)
    tool = gt.GenealogyTool(sap_files=[tmp.name], bom_db=BOM_DB, strict_dates=strict_dates)
    return tool, tmp.name


def _kinds(tool):
    return tool.edges["edge_kind"].value_counts().to_dict() if not tool.edges.empty else {}


def _has_edge(tool, kind, from_batch, to_batch):
    e = tool.edges
    if e.empty:
        return False
    m = (e["edge_kind"] == kind) & (e["from_batch"] == from_batch) & (e["to_batch"] == to_batch)
    return bool(m.any())


# ----------------------------------------------------------------------
# 개별 검증 (assert)
# ----------------------------------------------------------------------
def test_prod_edge():
    tool, _ = _build()
    assert _has_edge(tool, "PROD", "RSM-B1", "API-B1"), "PROD: RSM-B1→API-B1 누락"


def test_ref_po_item_edge():
    tool, _ = _build()
    assert _has_edge(tool, "REF_PO_ITEM", "API-B1", "DP-B1"), "REF_PO_ITEM: API-B1→DP-B1 누락"


def test_doc_transfer_edges():
    tool, _ = _build()
    assert _has_edge(tool, "DOC_TRANSFER", "DP-B1", "SP-B1"), "DOC_TRANSFER: DP-B1→SP-B1 누락"
    assert _has_edge(tool, "DOC_TRANSFER", "SP-B1", "FP-B1"), "DOC_TRANSFER: SP-B1→FP-B1 누락"


def test_all_three_kinds_present():
    tool, _ = _build()
    kinds = _kinds(tool)
    for k in ("PROD", "REF_PO_ITEM", "DOC_TRANSFER"):
        assert kinds.get(k, 0) >= 1, f"엣지 종류 {k} 미생성 (kinds={kinds})"


def test_date_violation_flagged():
    tool, _ = _build()
    e = tool.edges
    vio = e[(e["from_batch"] == "DPV") & (e["to_batch"] == "SPV")]
    assert not vio.empty, "날짜위반 케이스 엣지 자체가 없음"
    assert bool(vio["date_violation"].iloc[0]), "date_violation 플래그가 False"


def test_strict_dates_drops_violation():
    tool, _ = _build(strict_dates=True)
    assert not _has_edge(tool, "DOC_TRANSFER", "DPV", "SPV"), "strict-dates 인데 날짜위반 엣지가 남음"
    assert any("strict-dates" in w for w in tool.build_warnings), "strict-dates 경고 누락"


def test_reversal_and_exclude_ignored():
    tool, _ = _build()
    # 102(reversal)/921(exclude) 로만 이뤄진 문서는 엣지를 만들지 않아야 함
    e = tool.edges
    assert e[e["material_doc"] == "DOC_REV"].empty, "reversal(102) 문서에서 엣지 생성됨"
    assert e[e["material_doc"] == "DOC_EXC"].empty, "exclude(921) 문서에서 엣지 생성됨"


def test_legacy_tier_classified_as_api():
    tool, _ = _build()
    rows = tool.rows
    lapi = rows[rows["material"] == "1CNZ001ZZZZZ"]
    assert not lapi.empty, "legacy 자재 행이 정규화 결과에 없음"
    assert (lapi["tier"] == "API").all(), "legacy 1CNZ* 가 API tier 로 분류되지 않음"


def test_upstream_trace_chain():
    tool, _ = _build()
    # FP-B1 에서 상류로 추적하면 RSM-B1 까지 도달해야 함
    trace_edges, trace_nodes, _, bom_expected, meta = tool.trace(
        batch="FP-B1", material="5CNT014A1ZZZ", direction="upstream", max_depth=12)
    batches = set(trace_nodes["batch"]) if not trace_nodes.empty else set()
    for b in ("FP-B1", "SP-B1", "DP-B1", "API-B1", "RSM-B1"):
        assert b in batches, f"상류 추적 체인에 {b} 누락 (도달={batches})"


def test_bom_expected_separated_from_actual():
    tool, _ = _build()
    # API-B1 의 BOM 입력 중 실측 없는 상류(1CNY002 등)는 BOM_EXPECTED 로만 떠야 함
    _, _, _, bom_expected, _ = tool.trace(
        batch="API-B1", material="2CNY001ZZZZZ", direction="upstream", max_depth=12)
    assert not bom_expected.empty, "API-B1 의 실측 없는 BOM 상류가 BOM_EXPECTED 로 안 뜸"
    # BOM_EXPECTED 는 status 컬럼으로 식별되며, 실제 엣지(edge_kind)와 분리돼 있어야 함
    assert "status" in bom_expected.columns and "edge_kind" not in bom_expected.columns, \
        "BOM_EXPECTED 가 실제 엣지 스키마와 섞임"
    assert bom_expected["status"].str.startswith("BOM_EXPECTED").all(), "BOM_EXPECTED 외 status 혼입"
    # 실측이 존재하는 상류(1CNY001ZZZZZ)는 BOM_EXPECTED 에 들어오면 안 됨
    assert "1CNY001ZZZZZ" not in set(bom_expected["from_material_expected"]), \
        "실측 있는 상류가 BOM_EXPECTED 로 잘못 분류됨"


# ----------------------------------------------------------------------
# 단독 실행 러너 (pytest 없이)
# ----------------------------------------------------------------------
def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
