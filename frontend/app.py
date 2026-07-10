"""Cenobamate Genealogy 조회 frontend (Streamlit).

warehouse(sqlite)의 최신 빌드 결과(v_latest_*)를 읽어 배치 계보를 조회한다.
- FP→RSM 상류 그래프 (+ 끊긴 상류 BOM_EXPECTED 점선 표시)
- RSM→FP 하류 그래프
- 배치 검색/필터, 노드·엣지 테이블, 빌드·적재 이력

실행:
    pip install -r requirements-frontend.txt
    streamlit run frontend/app.py
    # warehouse 경로는 사이드바에서 지정 (기본 data/warehouse.sqlite)
"""
from __future__ import annotations

import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genealogy_db as gdb  # noqa: E402

st.set_page_config(page_title="Cenobamate Genealogy", layout="wide")


@st.cache_data(show_spinner=False)
def _load(db_path: str, mtime: float, safe_copy: bool = True):
    # 공유폴더(OneDrive/SharePoint) 안전모드: 원본을 직접 열지 않고 로컬 복사본을 읽는다.
    path = gdb.snapshot_warehouse(db_path) if safe_copy else db_path
    return {
        "edges": gdb.load_edges(path),
        "nodes": gdb.load_nodes(path),
        "runs": gdb.load_runs(path),
        "ingest": gdb.load_ingest_log(path),
        "bom_expected": gdb.load_bom_expected(path),
        "legacy": gdb.load_legacy_map(path),
        "plant_map": gdb.load_plant_map(path),
    }


def _default_warehouse() -> str:
    """warehouse 기본 경로 해석: 환경변수 → warehouse_path.txt(리포 루트) → data/warehouse.sqlite.

    공유폴더(SharePoint/Teams) 배포 시 각 PC 마다 경로가 다르므로, 환경변수
    GENEALOGY_WAREHOUSE 나 리포 루트의 warehouse_path.txt 한 줄로 지정해두면 매번 안 쳐도 된다.
    """
    env = os.environ.get("GENEALOGY_WAREHOUSE", "").strip()
    if env:
        return env
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "warehouse_path.txt")
    try:
        if os.path.exists(cfg):
            line = open(cfg, encoding="utf-8").read().strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return "data/warehouse.sqlite"


def _legend_md() -> str:
    return "**Tier:** " + " ".join(
        f'<span style="background:{c};color:white;padding:2px 8px;border-radius:4px;margin-right:4px">{t}</span>'
        for t, c in gdb.tier_legend())


def _node_picker(nodes, key: str, default_tiers):
    """검색어 + tier 필터로 노드 선택 위젯. 선택된 node id 반환(없으면 None)."""
    c1, c2 = st.columns([2, 2])
    query = c1.text_input("검색(material/batch)", key=f"q_{key}")
    tiers = c2.multiselect("Tier", ["RSM", "API", "DP", "SP", "FP", "OTHER"],
                           default=default_tiers, key=f"t_{key}")
    found = gdb.search_nodes(nodes, query, tiers)
    if found.empty:
        st.info("조건에 맞는 배치가 없습니다.")
        return None
    labels = {n: f"[{t}] {m} / {b}" for n, t, m, b
              in zip(found["node"], found["tier"], found["material"], found["batch"])}
    options = found["node"].tolist()
    return st.selectbox(f"배치 선택 ({len(options)}개)", options,
                        format_func=lambda n: labels.get(n, n), key=f"s_{key}")


def main() -> None:
    st.title("🧬 Cenobamate Batch Genealogy")

    st.sidebar.header("데이터")
    db_path = st.sidebar.text_input(
        "warehouse 경로", value=_default_warehouse(),
        help="SharePoint/Teams 공유 warehouse.sqlite 의 로컬(OneDrive 동기화) 경로. "
             "환경변수 GENEALOGY_WAREHOUSE 또는 리포 루트 warehouse_path.txt 로 기본값 지정 가능.")
    safe_copy = st.sidebar.checkbox(
        "공유폴더 안전모드(로컬 복사 후 열기)", value=True,
        help="OneDrive/SharePoint 동기화 폴더의 파일을 직접 열면 잠금·동기화 충돌이 날 수 있어 "
             "로컬 임시본을 복사해 읽습니다. 원본이 갱신되면 자동으로 다시 복사합니다.")
    if st.sidebar.button("🔄 최신 데이터 다시 읽기", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if not os.path.exists(db_path):
        st.warning(f"warehouse 파일을 찾을 수 없습니다: `{db_path}`\n\n"
                   "공유폴더(SharePoint/Teams) 경로가 로컬에 동기화됐는지 확인하거나, "
                   "빌더 PC 에서 `--ingest --from-store --write-db` 로 결과 DB를 생성하세요.")
        st.stop()

    data = _load(db_path, os.path.getmtime(db_path), safe_copy)
    edges, nodes, runs = data["edges"], data["nodes"], data["runs"]
    ingest, bom_expected, legacy = data["ingest"], data["bom_expected"], data["legacy"]
    plant_map = data["plant_map"]

    if not runs.empty:
        r = runs.iloc[0]
        cols = st.columns(5)
        cols[0].metric("최신 빌드", str(r.get("run_id", ""))[:19])
        cols[1].metric("SAP rows", f"{int(r.get('sap_rows', 0)):,}")
        cols[2].metric("Edges", f"{int(r.get('edge_count', 0)):,}")
        cols[3].metric("Nodes", f"{int(r.get('node_count', 0)):,}")
        cols[4].metric("Date violations", f"{int(r.get('date_violations', 0)):,}")

    if edges.empty or nodes.empty:
        st.info("결과가 비어 있습니다. 빌드를 먼저 수행하세요.")
        st.stop()

    tabs = st.tabs(["⬆️ 상류 (FP→RSM)", "⬇️ 하류 (RSM→FP)", "🔎 흐름 검색",
                    "📅 기간 추적", "📋 노드/엣지", "🗂 빌드·적재 이력"])

    # ── Tab 1: 상류 그래프 + BOM_EXPECTED ─────────────────────
    with tabs[0]:
        sel = _node_picker(nodes, "up", ["FP"])
        if sel:
            c1, c2 = st.columns([1, 2])
            max_depth = c1.slider("최대 깊이", 1, 30, 20, key="d_up")
            show_exp = c2.checkbox("끊긴 상류(BOM 기대) 점선 표시", value=True)
            sub, visited, truncated = gdb.trace_subgraph(edges, sel, "upstream", max_depth=max_depth)
            if truncated:
                st.warning("그래프가 커서 일부만 표시했습니다(max_nodes 초과).")
            st.markdown(_legend_md(), unsafe_allow_html=True)
            if sub.empty and not show_exp:
                st.info("이 배치의 실측 상류 엣지가 없습니다(단일 export 범위 한계일 수 있음).")
            else:
                exp = gdb.expected_missing(visited, edges, bom_expected, nodes, legacy) if show_exp else None
                _render_trace(nodes, sub, visited, sel, "upstream", exp, "up", plant_map)

    # ── Tab 2: 하류 그래프 ───────────────────────────────────
    with tabs[1]:
        st.caption("RSM/API 등 상류 배치를 골라 어떤 완제품으로 흘렀는지 본다.")
        sel = _node_picker(nodes, "down", ["RSM", "API"])
        if sel:
            max_depth = st.slider("최대 깊이", 1, 30, 20, key="d_down")
            sub, visited, truncated = gdb.trace_subgraph(edges, sel, "downstream", max_depth=max_depth)
            if truncated:
                st.warning("그래프가 커서 일부만 표시했습니다(max_nodes 초과).")
            st.markdown(_legend_md(), unsafe_allow_html=True)
            if sub.empty:
                st.info("이 배치의 실측 하류 엣지가 없습니다.")
            else:
                _render_trace(nodes, sub, visited, sel, "downstream", None, "down", plant_map)

    # ── Tab 3: 흐름 검색 (멀티 조건 필터) ────────────────────
    with tabs[2]:
        _render_flow_search(edges, nodes)

    # ── Tab 4: 기간 추적 (제조→상류 / 소비→하류) ─────────────
    with tabs[3]:
        _render_period_trace(edges, nodes, bom_expected, legacy, plant_map)

    # ── Tab 5: 노드/엣지 테이블 ──────────────────────────────
    with tabs[4]:
        st.subheader("노드")
        c1, c2 = st.columns([2, 2])
        nq = c1.text_input("노드 검색(material/batch)")
        nt = c2.multiselect("Tier 필터", ["RSM", "API", "DP", "SP", "FP", "OTHER"], default=[])
        st.dataframe(gdb.search_nodes(nodes, nq, nt), use_container_width=True, hide_index=True)
        st.subheader("엣지")
        kind_filter = st.multiselect("Edge 종류", ["PROD", "REF_PO_ITEM", "DOC_TRANSFER"], default=[])
        ev = edges if not kind_filter else edges[edges["edge_kind"].isin(kind_filter)]
        st.dataframe(ev, use_container_width=True, hide_index=True)

    # ── Tab 6: 이력 ─────────────────────────────────────────
    with tabs[5]:
        st.subheader("빌드 이력 (build_runs)")
        st.dataframe(runs, use_container_width=True, hide_index=True)
        st.subheader("적재 이력 (ingest_log)")
        if ingest.empty:
            st.caption("적재 이력이 없습니다(--ingest 미사용).")
        else:
            st.dataframe(ingest, use_container_width=True, hide_index=True)


def _edge_table(sub):
    cols = [c for c in ["posting_date", "edge_kind", "from_material", "from_desc", "from_batch", "from_tier",
                        "from_posting_date", "to_material", "to_desc", "to_batch", "to_tier",
                        "to_posting_date", "confidence", "date_violation", "source_rule"] if c in sub.columns]
    st.dataframe(sub[cols], use_container_width=True, hide_index=True)


def _render_trace(nodes, sub, visited, sel, direction, exp, keyp, plant_map=None):
    """날짜 범위 필터 + 날짜 라벨 + 그래프 + 타임라인 + 엣지 테이블."""
    c1, c2 = st.columns([1, 2])
    show_dates = c1.checkbox("엣지에 날짜 표시", value=True, key=f"sd_{keyp}")
    sub_f = sub
    dmin, dmax = gdb.edge_date_bounds(sub)
    if dmin and dmax and dmin < dmax:
        rng = c2.slider("날짜 범위", dmin, dmax, (dmin, dmax), key=f"dr_{keyp}")
        sub_f = gdb.filter_edges_by_date(sub, rng[0], rng[1])
    elif dmin:
        c2.caption(f"전기일: {dmin}")

    dot = gdb.build_dot(sub_f, nodes, sel, direction, expected=exp, show_dates=show_dates, plant_map=plant_map)
    _graph_with_downloads(dot, f"{'상류' if direction=='upstream' else '하류'} {sel}", f"{keyp}_{sel}")

    cap = f"노드 {len(visited)}개 · 표시 엣지 {len(sub_f)}/{len(sub)}개"
    if exp:
        cap += f" · BOM 기대 {len(exp)}개"
    st.caption(cap + "  (실선=실측 제조, 회색점선'이전'=공장이전/재배치, 점선보라=BOM 기대, 엣지 숫자=전기일)")

    st.subheader("🕒 타임라인 (전기일 순)")
    tl = gdb.timeline_table(sub_f)
    if tl.empty:
        st.caption("표시할 전환/이동이 없습니다.")
    else:
        st.dataframe(tl, use_container_width=True, hide_index=True)
    if exp:
        with st.expander(f"끊긴 상류(BOM_EXPECTED) {len(exp)}개"):
            st.dataframe(exp, use_container_width=True, hide_index=True)
    with st.expander("이 경로의 실측 엣지 테이블(상세)"):
        _edge_table(sub_f)


def _render_flow_search(edges, nodes) -> None:
    """멀티 조건(기간·tier·저장위치·전환유형·텍스트)으로 자재 흐름을 검색하는 탭."""
    st.caption("기간·자재 tier·저장위치·전환/이동 유형을 멀티 선택해 해당 자재 흐름(엣지)을 검색한다. "
               "조건은 AND, 각 항목 내부는 OR.")
    with st.expander("ℹ️ 전환/이동 유형 설명"):
        for kind, desc in gdb.edge_kind_legend():
            st.markdown(f"- **{kind}** — {desc}")
    c1, c2 = st.columns(2)
    tiers = c1.multiselect("자재 Tier (흐름의 한쪽이라도 걸치면 포함)",
                           ["RSM", "API", "DP", "SP", "FP", "OTHER"], default=[], key="fs_tier")
    kinds = c2.multiselect("전환/이동 유형", ["PROD", "REF_PO_ITEM", "DOC_TRANSFER"],
                           default=[], key="fs_kind")
    locations = st.multiselect("저장위치(storage location)", gdb.location_options(nodes),
                               default=[], key="fs_loc")
    query = st.text_input("자재/배치 텍스트 검색(선택)", key="fs_q")

    dmin, dmax = gdb.edge_date_bounds(edges)
    date_from = date_to = None
    if dmin and dmax and dmin < dmax:
        date_from, date_to = st.slider("전기일 기간", dmin, dmax, (dmin, dmax), key="fs_date")
    elif dmin:
        st.caption(f"전기일: {dmin}")

    incl_up = st.checkbox("검색된 자재의 상류 전체 흐름 함께 표시", value=True, key="fs_up",
                          help="매칭된 흐름뿐 아니라 그 자재들이 어디서 왔는지(RSM 방향) 전체 상류 경로를 합쳐서 보여준다.")

    date_filtered = bool(date_from) and (date_from, date_to) != (dmin, dmax)
    if not (tiers or kinds or locations or query or date_filtered):
        st.info("위 조건을 하나 이상 선택하면 해당 흐름을 검색합니다.")
        return

    matched = gdb.flow_search(edges, nodes, tiers=tiers, locations=locations, kinds=kinds,
                              date_from=date_from, date_to=date_to, query=query)
    res = gdb.expand_flow_upstream(edges, matched) if incl_up else matched
    st.markdown(_legend_md(), unsafe_allow_html=True)
    if incl_up and len(res) > len(matched):
        st.caption(f"검색 매칭 {len(matched):,}건 + 상류 {len(res) - len(matched):,}건 = 표시 {len(res):,} / 전체 {len(edges):,}")
    else:
        st.caption(f"검색된 흐름(엣지): {len(res):,} / 전체 {len(edges):,}")
    if res.empty:
        st.info("조건에 맞는 흐름이 없습니다.")
        return

    GRAPH_CAP = 200
    if len(res) <= GRAPH_CAP:
        dot = gdb.build_dot(res, nodes, "", "upstream", show_dates=True)
        _graph_with_downloads(dot, "흐름 검색 결과", "flow")
    else:
        st.warning(f"엣지가 많아({len(res):,} > {GRAPH_CAP}) 그래프는 생략했습니다. "
                   "조건을 좁히거나 아래 타임라인/표를 이용하세요.")

    st.subheader("🕒 타임라인 (전기일 순)")
    st.dataframe(gdb.timeline_table(res), use_container_width=True, hide_index=True)
    with st.expander(f"엣지 테이블(상세) — {len(res):,}건"):
        _edge_table(res)
    st.download_button("⬇️ 검색결과 CSV", res.to_csv(index=False).encode("utf-8-sig"),
                       file_name="flow_search.csv", mime="text/csv",
                       key="fs_dl", use_container_width=True)


def _show_reached_fp(sub, nodes) -> None:
    """하류 흐름에서 도달한 FP(완제품) 배치 요약."""
    fp = gdb.reached_nodes(sub, nodes, tier="FP", side="to")
    if fp.empty:
        st.caption("이 흐름에서 도달한 FP(완제품) 배치가 없습니다(범위 내 완제품 미연결).")
    else:
        st.markdown(f"**🎯 도달한 FP(완제품) 배치: {len(fp):,}개**")
        st.dataframe(fp, use_container_width=True, hide_index=True)


def _render_period_trace(edges, nodes, bom_expected, legacy, plant_map) -> None:
    """특정 기간에 제조(→상류)/소비(→하류)된 배치를 찾아 전체 흐름을 보는 탭."""
    dlabel = st.radio("추적 방향",
                      ["상류 (이 배치가 어디서 왔나: RSM 방향)", "하류 (이 배치가 어디로 갔나: FP 방향)"],
                      horizontal=True, key="pp_dir")
    upstream = dlabel.startswith("상류")
    direction = "upstream" if upstream else "downstream"
    flow_word = "상류" if upstream else "하류"

    if upstream:
        st.caption("특정 기간에 제조/입고된 배치를 찾아, 각 배치의 전체 상류 흐름(RSM→해당 배치)을 본다.")
        basis = st.radio("제조일 기준", ["생산(101) 엣지 날짜 — 엄밀", "최초 전기일 — 입고 포함"],
                         horizontal=True, key="pp_basis",
                         help="엄밀: 실제 생산(101)된 배치만, 그 생산 전기일 기준. "
                              "입고 포함: 최초 전기일 기준(생산 엣지 없는 배치도 포함).")
        strict = basis.startswith("생산")
        date_map = gdb.production_dates(edges) if strict else None
        default_tiers, date_name, period_label = ["FP"], "생산일", "제조/입고 기간"
    else:
        st.caption("특정 기간에 소비/투입된 배치(RSM·API 등)를 찾아, 각 배치가 어느 완제품(FP)으로 흘렀는지 본다.")
        basis = st.radio("소비일 기준", ["소비 엣지 날짜 — 엄밀", "최초 전기일"],
                         horizontal=True, key="pp_basis",
                         help="엄밀: 그 배치가 입력으로 쓰인(out-edge) 가장 이른 전기일(실제 투입분만). "
                              "최초 전기일: 노드 최초 전기일 기준.")
        strict = basis.startswith("소비")
        date_map = gdb.consumption_dates(edges) if strict else None
        default_tiers, date_name, period_label = ["RSM", "API"], "소비일", "소비/투입 기간"

    if strict:
        pmin, pmax = gdb.date_map_bounds(date_map)
        if not pmin:
            st.info("엄밀 모드로 잡히는 배치가 없습니다. '최초 전기일' 기준을 쓰거나 결과 DB를 재빌드하세요.")
            return
    else:
        pmin, pmax = gdb.node_date_bounds(nodes)
        if not pmin:
            st.info("노드에 전기일 정보가 없습니다. 결과 DB를 최신 엔진으로 재빌드하세요.")
            return

    c1, c2 = st.columns([2, 2])
    tiers = c1.multiselect("배치 tier", ["FP", "SP", "DP", "API", "RSM", "OTHER"],
                           default=default_tiers, key="pp_tier")
    query = c2.text_input("자재/배치 텍스트(선택)", key="pp_q")
    if pmin < pmax:
        date_from, date_to = st.slider(period_label, pmin, pmax, (pmin, pmax), key="pp_date")
    else:
        date_from, date_to = pmin, pmax
        st.caption(f"{period_label}: {pmin}")

    anchors = gdb.nodes_in_period(nodes, date_from, date_to, tiers, query=query, date_map=date_map).copy()
    if strict:
        anchors[date_name] = anchors["node"].map(date_map)
        date_field = date_name
    else:
        date_field = "first_posting_date"
    st.caption(f"기간 내 대상 배치: {len(anchors):,}개")
    if anchors.empty:
        st.info("조건에 맞는 배치가 없습니다.")
        return
    show_cols = [c for c in ["tier", "material", "description", "batch",
                             date_field, "location", "cmo"] if c in anchors.columns]
    st.dataframe(anchors[show_cols], use_container_width=True, hide_index=True)

    mode = st.radio("보기 방식", ["배치 1건 선택", "전체 합쳐 보기"], horizontal=True, key="pp_mode")
    if mode == "배치 1건 선택":
        dcol = anchors[date_field] if date_field in anchors.columns else anchors["batch"]
        labels = {n: f"[{t}] {m} / {b}  ({str(d)[:10]})" for n, t, m, b, d in
                  zip(anchors["node"], anchors["tier"], anchors["material"], anchors["batch"], dcol)}
        sel = st.selectbox(f"배치 선택 ({len(anchors):,}개) → {flow_word} 전체", anchors["node"].tolist(),
                           format_func=lambda n: labels.get(n, n), key="pp_sel")
        if sel:
            sub, visited, _ = gdb.trace_subgraph(edges, sel, direction, max_depth=40)
            st.markdown(_legend_md(), unsafe_allow_html=True)
            if not upstream:
                _show_reached_fp(sub, nodes)
            exp = gdb.expected_missing(visited, edges, bom_expected, nodes, legacy) if upstream else None
            _render_trace(nodes, sub, visited, sel, direction, exp, "pp", plant_map)
    else:
        seeds = anchors["node"].tolist()
        res = gdb.flow_edges_of_nodes(edges, seeds, direction, max_depth=40)
        st.markdown(_legend_md(), unsafe_allow_html=True)
        st.caption(f"합산 {flow_word} 엣지: {len(res):,}개 (앵커 배치 {len(seeds):,}개)")
        if res.empty:
            st.info(f"이 배치들의 실측 {flow_word} 엣지가 없습니다(단일 export 범위 한계일 수 있음).")
            return
        if not upstream:
            _show_reached_fp(res, nodes)
        GRAPH_CAP = 250
        if len(res) <= GRAPH_CAP:
            dot = gdb.build_dot(res, nodes, "", direction, show_dates=True)
            _graph_with_downloads(dot, f"기간 {flow_word}(합본)", "ppall")
        else:
            st.warning(f"엣지가 많아({len(res):,} > {GRAPH_CAP}) 그래프는 생략했습니다. "
                       "'배치 1건 선택'으로 보거나 기간/tier 를 좁히세요.")
        st.subheader("🕒 타임라인 (전기일 순)")
        st.dataframe(gdb.timeline_table(res), use_container_width=True, hide_index=True)
        with st.expander(f"엣지 테이블(상세) — {len(res):,}건"):
            _edge_table(res)
        st.download_button(f"⬇️ {flow_word} 합본 CSV", res.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"period_{direction}.csv", mime="text/csv",
                           key="pp_dl", use_container_width=True)


def _graph_with_downloads(dot: str, title: str, key: str) -> None:
    """인터랙티브 그래프(휠 확대/축소·드래그 이동) + 전체 캡처용 다운로드(HTML/DOT)·복사."""
    c1, c2 = st.columns([3, 1])
    height = c1.slider("그래프 높이(px)", 400, 1400, 640, 20, key=f"gh_{key}")
    interactive = c2.checkbox("확대/축소", value=True, key=f"gi_{key}",
                              help="휠=확대/축소, 드래그=이동 (인터넷 필요). 끄면 정적 이미지")
    if interactive:
        components.html(gdb.dot_to_html(dot, title), height=height + 8, scrolling=False)
    else:
        st.graphviz_chart(dot, use_container_width=True)
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ 전체 그래프 HTML (한 화면 캡처용)", gdb.dot_to_html(dot, title),
                       file_name=f"{key}.html", mime="text/html", key=f"dlh_{key}",
                       use_container_width=True)
    d2.download_button("⬇️ DOT 소스", dot, file_name=f"{key}.dot",
                       mime="text/vnd.graphviz", key=f"dld_{key}", use_container_width=True)
    with st.expander("DOT 소스 복사(붙여넣어 외부 렌더 가능)"):
        st.code(dot, language="dot")


if __name__ == "__main__":
    main()
