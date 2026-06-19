"""frontend 데이터 계층(genealogy_db) 검증 — Streamlit 없이 단독 실행.

합성 SAP 로 warehouse(결과 DB)를 만든 뒤, FP→RSM 상류 서브그래프 추적과
Graphviz DOT 생성이 올바른지 확인한다.

실행: python tests/test_frontend.py
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "frontend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import genealogy_tool as gt        # noqa: E402
import genealogy_db as gdb          # noqa: E402
from synth_sap import write_synthetic_sap  # noqa: E402

BOM_DB = os.path.join(ROOT, "data", "Cenobamate_BOM_DB_v1.sqlite")


def _warehouse():
    sap = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False); sap.close()
    write_synthetic_sap(sap.name)
    db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False); db.close()
    tool = gt.GenealogyTool(sap_files=[sap.name], bom_db=BOM_DB)
    tool.write_results_db(db.name, run_id="run_fe", replace=True)
    return db.name


def test_load_latest_views():
    db = _warehouse()
    edges = gdb.load_edges(db)
    nodes = gdb.load_nodes(db)
    runs = gdb.load_runs(db)
    assert not edges.empty and not nodes.empty, "v_latest_* 로딩 실패"
    assert runs.iloc[0]["run_id"] == "run_fe", "build_runs 최신 정렬 오류"


def test_fp_nodes_present():
    db = _warehouse()
    nodes = gdb.load_nodes(db)
    fp = gdb.nodes_by_tier(nodes, "FP")
    assert "5CNT014A1ZZZ||FP-B1" in set(fp["node"]), "FP 노드 선택 목록에 FP-B1 누락"


def test_upstream_fp_reaches_rsm():
    db = _warehouse()
    edges = gdb.load_edges(db)
    sub, visited, truncated = gdb.trace_subgraph(edges, "5CNT014A1ZZZ||FP-B1", "upstream")
    assert not truncated
    # FP-B1 상류로 SP/DP/API/RSM 배치까지 도달해야 함
    batches = {n.split("||")[1] for n in visited if "||" in n}
    for b in ("FP-B1", "SP-B1", "DP-B1", "API-B1", "RSM-B1"):
        assert b in batches, f"상류 서브그래프에 {b} 누락 (도달={batches})"


def test_build_dot_valid():
    db = _warehouse()
    edges = gdb.load_edges(db)
    nodes = gdb.load_nodes(db)
    start = "5CNT014A1ZZZ||FP-B1"
    sub, _, _ = gdb.trace_subgraph(edges, start, "upstream")
    dot = gdb.build_dot(sub, nodes, start, "upstream")
    assert dot.startswith("digraph genealogy {") and dot.rstrip().endswith("}")
    assert "rankdir=LR" in dot
    assert "rank=same" in dot                 # tier 컬럼 정렬
    assert dot.count("->") == len(sub)        # 엣지 수 일치
    assert "penwidth=3" in dot                # 시작 노드 강조
    # 노드 집합은 서브그래프로 한정 (전체 warehouse 노드가 새어들지 않아야 함)
    _, visited, _ = gdb.trace_subgraph(edges, start, "upstream")
    n_defs = dot.count("fillcolor=")
    assert n_defs == len(visited), f"DOT 노드 수({n_defs}) != 상류 노드 수({len(visited)})"
    # FP-B1 상류엔 무관 노드(DPV/RSM-M1 등)가 없어야 함
    for stray in ("DPV", "RSM-M1", "API2-M2"):
        assert stray not in dot, f"무관 노드 {stray} 가 그래프에 새어듦"


def test_downstream_rsm_reaches_fp():
    db = _warehouse()
    edges = gdb.load_edges(db)
    # RSM-B1 에서 하류로 FP-B1 까지 도달해야 함
    sub, visited, _ = gdb.trace_subgraph(edges, "1CNY001ZZZZZ||RSM-B1", "downstream")
    batches = {n.split("||")[1] for n in visited if "||" in n}
    for b in ("RSM-B1", "API-B1", "DP-B1", "SP-B1", "FP-B1"):
        assert b in batches, f"하류 서브그래프에 {b} 누락 (도달={batches})"


def test_search_nodes_filter():
    db = _warehouse()
    nodes = gdb.load_nodes(db)
    # batch 부분일치
    hit = gdb.search_nodes(nodes, "FP-B1")
    assert "5CNT014A1ZZZ||FP-B1" in set(hit["node"])
    # tier 필터
    only_fp = gdb.search_nodes(nodes, "", ["FP"])
    assert not only_fp.empty and set(only_fp["tier"]) == {"FP"}


def test_expected_missing_and_dot():
    db = _warehouse()
    edges = gdb.load_edges(db)
    nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db)
    legacy = gdb.load_legacy_map(db)
    start = "5CNT014A1ZZZ||FP-B1"
    sub, visited, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(visited, edges, bexp, nodes, legacy)
    # API-B1 의 BOM 입력 중 실측 없는 RSM(1CNY001N/1CNY002)이 끊긴 상류로 떠야 함
    expmats = {m["from_material"] for m in miss}
    assert any(x in expmats for x in ("1CNY001NZZZZ", "1CNY002ZZZZZ")), f"BOM 기대 누락 미검출: {expmats}"
    # 실측이 있는 1CNY001ZZZZZ 는 끊긴 상류로 뜨면 안 됨
    api_node = "2CNY001ZZZZZ||API-B1"
    api_miss = {m["from_material"] for m in miss if m["to_node"] == api_node}
    assert "1CNY001ZZZZZ" not in api_miss, "실측 있는 상류가 BOM 기대로 잘못 분류됨"
    # DOT 에 점선 기대 노드가 들어가야 함
    dot = gdb.build_dot(sub, nodes, start, "upstream", expected=miss)
    assert "BOM 기대" in dot and "dashed" in dot


def test_legacy_map_loaded():
    db = _warehouse()
    lm = gdb.load_legacy_map(db)
    # legacy_api_codes 가 DB에 있으므로 매핑이 비어있지 않아야 함
    assert lm.get("1CNZ001ZZZZZ") == "2CNY001ZZZZZ", f"legacy 매핑 누락: {lm}"


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
