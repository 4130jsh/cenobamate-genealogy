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
    # FP-B1(Card)의 SP 2종(AND) 중 실측 없는 4CNS1Z2001ZZ 이 끊긴 상류로 떠야 함
    expmats = {m["from_material"] for m in miss}
    assert "4CNS1Z2001ZZ" in expmats, f"BOM 기대 누락 미검출: {expmats}"
    # 실측이 있는 4CNS0Z2001ZZ 는 끊긴 상류로 뜨면 안 됨
    assert "4CNS0Z2001ZZ" not in expmats, "실측 있는 상류가 BOM 기대로 잘못 분류됨"
    # DOT 에 점선 기대 노드가 들어가야 함
    dot = gdb.build_dot(sub, nodes, start, "upstream", expected=miss)
    assert "BOM 기대" in dot and "dashed" in dot


def test_bottle_or_route_frontend():
    # frontend 끊긴상류: Britestock 경유 Bottle 의 Tablet 은 점선(BOM기대)으로 뜨면 안 됨
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db); legacy = gdb.load_legacy_map(db)
    start = "5CNB2ZAA1ZZZ||BOT"
    sub, vis, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(vis, edges, bexp, nodes, legacy)
    bot_miss = {m["from_material"] for m in miss if m["to_node"] == start}
    assert "3CNY2Z001ZZZ" not in bot_miss, f"Bottle OR경로인데 Tablet 이 끊긴상류로 표시됨: {bot_miss}"


def test_single_route_bottle_actual_suppresses_frontend():
    # frontend: 단일경로 Bottle 이 Britestock(BOM 누락 경로)으로 제조됐어도 실제 상류 있으면
    # Tablet 끊긴상류 점선 안 뜸
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db); legacy = gdb.load_legacy_map(db)
    start = "5CNB2ZAA1SZZ||PSAMP"
    sub, vis, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(vis, edges, bexp, nodes, legacy)
    ps_miss = {m["from_material"] for m in miss if m["to_node"] == start}
    assert "3CNY2Z001ZZZ" not in ps_miss, f"실제 상류 있는데 Tablet 끊긴상류로 표시됨: {ps_miss}"


def test_legacy_map_loaded():
    db = _warehouse()
    lm = gdb.load_legacy_map(db)
    # legacy_api_codes 가 DB에 있으므로 매핑이 비어있지 않아야 함
    assert lm.get("1CNZ001ZZZZZ") == "2CNY001ZZZZZ", f"legacy 매핑 누락: {lm}"


def test_node_label_has_description():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    start = "5CNT014A1ZZZ||FP-B1"
    sub, _, _ = gdb.trace_subgraph(edges, start, "upstream")
    dot = gdb.build_dot(sub, nodes, start, "upstream")
    # API-B1 노드 라벨에 자재 설명이 포함돼야 함
    assert "Cenobamate API_US" in dot, "노드 라벨에 자재 설명이 안 들어감"
    assert "[API-B1]" in dot, "배치는 [..] 형태로 라벨에 있어야 함"
    # 저장위치(storage location) 표시: API-B1(sloc 1104 → 'Sub3089DSVYJ')
    assert "위치:" in dot and "Sub3089DSVYJ" in dot, "노드 라벨에 저장위치(storage location)가 표시돼야 함"
    # location 컬럼이 없는 (구) 결과 DB 는 plant_map 으로 공장명 fallback
    nodes_noloc = nodes.drop(columns=["location"])
    dot2 = gdb.build_dot(sub, nodes_noloc, start, "upstream", plant_map={"1100": "SK BP 본사"})
    assert "SK BP 본사" in dot2, "location 없을 때 plant_map 공장명 fallback 이 안 됨"


def test_interchangeable_group_frontend():
    # frontend: API RSM 호환그룹 중 하나(1CNY001) 실측되면 나머지(1CNY001N/1CNY002) 점선 안 뜸
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db); legacy = gdb.load_legacy_map(db)
    start = "2CNY001ZZZZZ||API-B1"
    sub, vis, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(vis, edges, bexp, nodes, legacy)
    api_miss = {m["from_material"] for m in miss if m["to_node"] == start}
    assert not ({"1CNY001NZZZZ", "1CNY002ZZZZZ"} & api_miss), \
        f"호환 RSM 그룹 중 하나 실측됐는데 나머지가 끊긴상류로 뜸: {api_miss}"


def test_transfer_in_node_no_bom_expected():
    # 같은 자재 전입(공장이전)된 노드는 BOM 기대(RSM 점선)를 표시하지 않음
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db); legacy = gdb.load_legacy_map(db)
    start = "2CNY001ZZZZZ||APIP"   # APIH(HQ)→APIP(Patheon) 전입 배치
    sub, vis, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(vis, edges, bexp, nodes, legacy)
    apip_miss = [m for m in miss if m["to_node"] == start]
    assert not apip_miss, f"전입 노드에 BOM 기대가 표시됨: {apip_miss}"


def test_legacy_api_no_bom_expected():
    # legacy API 코드(1CNZ*) 노드는 RSM 미관리 → BOM 기대(점선 RSM) 표시 안 함
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    bexp = gdb.load_bom_expected(db); legacy = gdb.load_legacy_map(db)
    start = "1CNZ001ZZZZZ||LAPI-B1"
    sub, vis, _ = gdb.trace_subgraph(edges, start, "upstream")
    miss = gdb.expected_missing(vis, edges, bexp, nodes, legacy)
    lapi_miss = [m for m in miss if m["to_node"] == start]
    assert not lapi_miss, f"legacy API 노드에 BOM 기대가 표시됨: {lapi_miss}"


def test_transfer_link_styled():
    import pandas as pd
    # 같은 자재 다른 배치(공장이전/재배치)는 회색점선+'이전' 라벨, 제조 전환은 일반 색
    sub = pd.DataFrame([
        {"from_node": "2CNY001ZZZZZ||APIH", "to_node": "2CNY001ZZZZZ||APIP",
         "from_material": "2CNY001ZZZZZ", "to_material": "2CNY001ZZZZZ",
         "from_tier": "API", "to_tier": "API", "edge_kind": "REF_PO_ITEM"},
        {"from_node": "1CNY001ZZZZZ||R1", "to_node": "2CNY001ZZZZZ||APIH",
         "from_material": "1CNY001ZZZZZ", "to_material": "2CNY001ZZZZZ",
         "from_tier": "RSM", "to_tier": "API", "edge_kind": "PROD"},
    ])
    dot = gdb.build_dot(sub, pd.DataFrame(), "2CNY001ZZZZZ||APIP", "upstream")
    assert 'label="이전"' in dot and gdb.TRANSFER_COLOR in dot, "공장이전 링크 스타일 누락"
    # 제조 전환(RSM→API)은 '이전' 라벨이 붙으면 안 됨 → 라벨 개수 1개
    assert dot.count('label="이전"') == 1, "제조 전환에 잘못 '이전' 라벨이 붙음"


def test_timeline_and_date_features():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    start = "5CNT014A1ZZZ||FP-B1"
    sub, _, _ = gdb.trace_subgraph(edges, start, "upstream")
    # 타임라인: 전기일 순 정렬 표
    tl = gdb.timeline_table(sub)
    assert "일자" in tl.columns and "전환" in tl.columns and len(tl) == len(sub)
    # 날짜 라벨이 DOT 에 들어감
    dot = gdb.build_dot(sub, nodes, start, "upstream", show_dates=True)
    assert "label=" in dot  # 엣지/노드 라벨 존재
    # 날짜 범위 필터
    lo, hi = gdb.edge_date_bounds(sub)
    assert lo is not None and hi is not None
    f = gdb.filter_edges_by_date(sub, lo, hi)
    assert len(f) == len(sub)  # 전체 범위면 전부 유지


def test_parallel_edges_collapsed():
    import pandas as pd
    # 같은 노드쌍 사이 평행 엣지 3개 → 그래프엔 1개로 합쳐지고 ×N·날짜범위 표시
    sub = pd.DataFrame([
        {"from_node": "3CNY2Z001ZZZ||A", "to_node": "3CNY2Z001ZZZ||B",
         "from_material": "3CNY2Z001ZZZ", "to_material": "3CNY2Z001ZZZ",
         "from_tier": "DP", "to_tier": "DP", "edge_kind": "DOC_TRANSFER", "posting_date": d}
        for d in ("2020-06-22", "2020-08-01", "2020-06-22")
    ])
    dot = gdb.build_dot(sub, pd.DataFrame(), "3CNY2Z001ZZZ||B", "upstream", show_dates=True)
    assert dot.count("->") == 1, "평행 엣지가 1개로 합쳐지지 않음"
    assert "×3" in dot and "2020-06-22~2020-08-01" in dot, "합친 엣지에 건수·날짜범위 표시 누락"


def test_dot_to_html_full_graph():
    dot = "digraph { a -> b; }"
    html = gdb.dot_to_html(dot, "테스트")
    assert "<html" in html and "renderDot" in html
    assert "a -> b" in html and ".fit(true)" in html  # 전체 맞춤 렌더
    # 휠 단독은 확대 금지, Ctrl+휠만 확대 (페이지 스크롤 통과)
    assert "e.ctrlKey" in html and "'wheel'" in html


def test_flow_search_filters():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)

    # 저장위치 옵션이 노드 location 에서 추출됨
    opts = gdb.location_options(nodes)
    assert any("S/L" in o or "Sub3089" in o for o in opts), f"저장위치 옵션 추출 실패: {opts[:5]}"

    # tier 필터: API 가 한쪽이라도 걸친 엣지만
    api = gdb.flow_search(edges, nodes, tiers=["API"])
    assert not api.empty and (api["from_tier"].eq("API") | api["to_tier"].eq("API")).all()

    # 전환유형 필터
    prod = gdb.flow_search(edges, nodes, kinds=["PROD"])
    assert not prod.empty and prod["edge_kind"].eq("PROD").all()

    # 조건 AND 결합: tier+kind 동시
    both = gdb.flow_search(edges, nodes, tiers=["API"], kinds=["PROD"])
    assert len(both) <= min(len(api), len(prod))

    # 텍스트 검색(from/to 양쪽 대상)
    q = gdb.flow_search(edges, nodes, query="API-B1")
    assert not q.empty
    assert q.apply(lambda r: "API-B1" in f'{r["from_batch"]}{r["to_batch"]}', axis=1).all()

    # 빈 조건이면 전체 반환(상위 UI 에서 게이팅)
    assert len(gdb.flow_search(edges, nodes)) == len(edges)


def test_flow_search_date_and_location():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    lo, hi = gdb.edge_date_bounds(edges)
    # 전 범위면 날짜 있는 엣지 전부 유지
    full = gdb.flow_search(edges, nodes, date_from=lo, date_to=hi)
    import pandas as pd
    dated = edges["posting_date"].map(lambda s: bool(str(s or "").strip())).sum()
    assert len(full) == dated

    # 저장위치 필터로 좁힌 결과는 전체 이하이고 양끝 중 하나가 해당 위치
    opts = gdb.location_options(nodes)
    if opts:
        loc = opts[0]
        node_loc = dict(zip(nodes["node"], nodes["location"]))
        r = gdb.flow_search(edges, nodes, locations=[loc])
        assert len(r) <= len(edges)
        ok = r.apply(lambda x: loc in str(node_loc.get(x["from_node"], "")) or
                     loc in str(node_loc.get(x["to_node"], "")), axis=1)
        assert ok.all() if not r.empty else True


def test_build_dot_no_start_node():
    # 흐름검색은 시작노드 없이 임의 엣지집합을 렌더 → 빈 노드 박스가 생기면 안 됨
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    res = gdb.flow_search(edges, nodes, kinds=["PROD"])
    dot = gdb.build_dot(res, nodes, "", "upstream", show_dates=True)
    assert "digraph" in dot and "->" in dot
    assert 'label=""' not in dot, "시작노드 없이 빈 라벨 노드가 생성됨"


def test_flow_search_includes_upstream():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    matched = gdb.flow_search(edges, nodes, query="FP-B1")
    assert not matched.empty, "FP-B1 매칭 흐름이 없음"
    expanded = gdb.expand_flow_upstream(edges, matched)
    assert len(expanded) > len(matched), "상류 흐름이 합쳐지지 않음"
    assert set(matched.index).issubset(set(expanded.index)), "매칭 엣지가 결과에 누락"
    # 상류에 RSM→API 제조(PROD) 엣지가 포함돼야 함
    assert ((expanded["from_tier"] == "RSM") & (expanded["to_tier"] == "API")).any(), \
        "상류 RSM→API 엣지가 포함되지 않음"


def test_edge_kind_legend():
    leg = gdb.edge_kind_legend()
    kinds = {k for k, _ in leg}
    assert {"PROD", "REF_PO_ITEM", "DOC_TRANSFER"}.issubset(kinds), f"유형 누락: {kinds}"
    assert all(d.strip() for _, d in leg), "설명이 비어 있는 항목이 있음"


def test_nodes_in_period_and_upstream():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    lo, hi = gdb.node_date_bounds(nodes)
    assert lo is not None and hi is not None, "노드 제조/입고일 경계 산출 실패"

    # FP 배치만, 전 기간 → FP 노드만 선택됨
    fp = gdb.nodes_in_period(nodes, lo, hi, tiers=["FP"])
    assert not fp.empty and fp["tier"].eq("FP").all()

    # 좁은 기간(케이스1 PROD: API-B1 제조일 2026-01-05) → API-B1 포함, 그 상류에 RSM→API 존재
    import datetime as dt
    d = dt.date(2026, 1, 5)
    api = gdb.nodes_in_period(nodes, d, d, tiers=["API"])
    assert (api["batch"] == "API-B1").any(), f"기간 내 제조 API 배치 누락: {api['batch'].tolist()}"

    # 앵커 배치(FP-B1)의 상류 합산 → RSM→API(PROD) 포함
    seeds = nodes[nodes["batch"] == "FP-B1"]["node"].tolist()
    up = gdb.upstream_edges_of_nodes(edges, seeds)
    assert not up.empty
    assert ((up["from_tier"] == "RSM") & (up["to_tier"] == "API")).any(), \
        "FP-B1 상류 합산에 RSM→API 가 없음"


def test_production_date_strict_anchor():
    db = _warehouse()
    edges = gdb.load_edges(db); nodes = gdb.load_nodes(db)
    prod = gdb.production_dates(edges)   # PROD(101) 엣지의 산출측 전기일
    assert prod, "생산일 맵이 비어 있음"
    # 케이스1: RSM-B1 소비 + API-B1 산출(101) 2026-01-05 → API-B1 생산일 잡힘
    api_node = nodes[nodes["batch"] == "API-B1"]["node"].iloc[0]
    assert prod.get(api_node) == "2026-01-05", f"API-B1 생산일 오류: {prod.get(api_node)}"
    # 구매 입고만 있는 RSM(원천)에는 PROD 엣지가 없어 생산일 맵에서 제외
    rsm_node = nodes[nodes["batch"] == "RSM-B1"]["node"].iloc[0]
    assert rsm_node not in prod, "생산 엣지 없는 RSM 이 생산일 맵에 잘못 포함됨"

    import datetime as dt
    d = dt.date(2026, 1, 5)
    strict = gdb.nodes_in_period(nodes, d, d, tiers=["API"], date_map=prod)
    assert (strict["batch"] == "API-B1").any(), "엄밀 모드로 API-B1 이 안 잡힘"
    # 같은 날 first_posting_date 로는 잡히지 않는 노드와 결과가 다를 수 있음(엄밀성 확인)
    bounds = gdb.date_map_bounds(prod)
    assert bounds[0] is not None and bounds[0] <= bounds[1]


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
