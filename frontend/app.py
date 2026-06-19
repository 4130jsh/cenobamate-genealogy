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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genealogy_db as gdb  # noqa: E402

st.set_page_config(page_title="Cenobamate Genealogy", layout="wide")


@st.cache_data(show_spinner=False)
def _load(db_path: str, mtime: float):
    return {
        "edges": gdb.load_edges(db_path),
        "nodes": gdb.load_nodes(db_path),
        "runs": gdb.load_runs(db_path),
        "ingest": gdb.load_ingest_log(db_path),
        "bom_expected": gdb.load_bom_expected(db_path),
        "legacy": gdb.load_legacy_map(db_path),
    }


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
    db_path = st.sidebar.text_input("warehouse 경로", value="data/warehouse.sqlite")
    if not os.path.exists(db_path):
        st.warning(f"warehouse 파일을 찾을 수 없습니다: `{db_path}`\n\n"
                   "먼저 `--ingest` 로 적재하고 `--from-store --write-db` 로 결과 DB를 생성하세요.")
        st.stop()

    data = _load(db_path, os.path.getmtime(db_path))
    edges, nodes, runs = data["edges"], data["nodes"], data["runs"]
    ingest, bom_expected, legacy = data["ingest"], data["bom_expected"], data["legacy"]

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

    tabs = st.tabs(["⬆️ 상류 (FP→RSM)", "⬇️ 하류 (RSM→FP)", "📋 노드/엣지", "🗂 빌드·적재 이력"])

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
                st.graphviz_chart(gdb.build_dot(sub, nodes, sel, "upstream", expected=exp),
                                  use_container_width=True)
                cap = f"상류 노드 {len(visited)}개 · 실측 엣지 {len(sub)}개"
                if exp:
                    cap += f" · BOM 기대(끊김) {len(exp)}개"
                st.caption(cap + "  (실선=실측, 점선보라=BOM 기대 상류, 점선=날짜 역전)")
                if exp:
                    with st.expander(f"끊긴 상류(BOM_EXPECTED) {len(exp)}개"):
                        st.dataframe(exp, use_container_width=True, hide_index=True)
                with st.expander("이 경로의 실측 엣지 테이블"):
                    _edge_table(sub)

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
                st.graphviz_chart(gdb.build_dot(sub, nodes, sel, "downstream"), use_container_width=True)
                st.caption(f"하류 노드 {len(visited)}개 · 실측 엣지 {len(sub)}개")
                with st.expander("이 경로의 실측 엣지 테이블"):
                    _edge_table(sub)

    # ── Tab 3: 노드/엣지 테이블 ──────────────────────────────
    with tabs[2]:
        st.subheader("노드")
        c1, c2 = st.columns([2, 2])
        nq = c1.text_input("노드 검색(material/batch)")
        nt = c2.multiselect("Tier 필터", ["RSM", "API", "DP", "SP", "FP", "OTHER"], default=[])
        st.dataframe(gdb.search_nodes(nodes, nq, nt), use_container_width=True, hide_index=True)
        st.subheader("엣지")
        kind_filter = st.multiselect("Edge 종류", ["PROD", "REF_PO_ITEM", "DOC_TRANSFER"], default=[])
        ev = edges if not kind_filter else edges[edges["edge_kind"].isin(kind_filter)]
        st.dataframe(ev, use_container_width=True, hide_index=True)

    # ── Tab 4: 이력 ─────────────────────────────────────────
    with tabs[3]:
        st.subheader("빌드 이력 (build_runs)")
        st.dataframe(runs, use_container_width=True, hide_index=True)
        st.subheader("적재 이력 (ingest_log)")
        if ingest.empty:
            st.caption("적재 이력이 없습니다(--ingest 미사용).")
        else:
            st.dataframe(ingest, use_container_width=True, hide_index=True)


def _edge_table(sub):
    cols = [c for c in ["edge_kind", "from_material", "from_batch", "from_tier",
                        "to_material", "to_batch", "to_tier", "confidence",
                        "date_violation", "source_rule"] if c in sub.columns]
    st.dataframe(sub[cols], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
