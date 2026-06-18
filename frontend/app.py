"""Cenobamate Genealogy 조회 frontend (Streamlit).

warehouse(sqlite)의 최신 빌드 결과(v_latest_*)를 읽어 배치 계보를 조회한다.
1순위 화면: 완제품(FP)에서 원료(RSM)까지 한눈에 보는 상류 그래프.

실행:
    pip install -r requirements-frontend.txt
    streamlit run frontend/app.py
    # warehouse 경로는 사이드바에서 지정 (기본 data/warehouse.sqlite)
"""
from __future__ import annotations

import os
import sys

import pandas as pd
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
    }


def main() -> None:
    st.title("🧬 Cenobamate Batch Genealogy")

    # ── 사이드바: warehouse 선택 ──────────────────────────────
    st.sidebar.header("데이터")
    db_path = st.sidebar.text_input("warehouse 경로", value="data/warehouse.sqlite")
    if not os.path.exists(db_path):
        st.warning(f"warehouse 파일을 찾을 수 없습니다: `{db_path}`\n\n"
                   "먼저 `--ingest` 로 적재하고 `--from-store --write-db` 로 결과 DB를 생성하세요.")
        st.stop()

    data = _load(db_path, os.path.getmtime(db_path))
    edges, nodes, runs, ingest = data["edges"], data["nodes"], data["runs"], data["ingest"]

    if not runs.empty:
        r = runs.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("최신 빌드", str(r.get("run_id", ""))[:19])
        c2.metric("SAP rows", f"{int(r.get('sap_rows', 0)):,}")
        c3.metric("Edges", f"{int(r.get('edge_count', 0)):,}")
        c4.metric("Nodes", f"{int(r.get('node_count', 0)):,}")
        c5.metric("Date violations", f"{int(r.get('date_violations', 0)):,}")

    if edges.empty or nodes.empty:
        st.info("결과가 비어 있습니다. 빌드를 먼저 수행하세요.")
        st.stop()

    tabs = st.tabs(["⬆️ FP→RSM 상류 그래프", "📋 노드/엣지", "🗂 빌드·적재 이력"])

    # ── Tab 1: 상류 그래프 ───────────────────────────────────
    with tabs[0]:
        fp = gdb.nodes_by_tier(nodes, "FP")
        if fp.empty:
            st.info("FP(완제품) 노드가 없습니다.")
        else:
            left, right = st.columns([2, 1])
            options = fp["node"].tolist()
            labels = {n: f"{m} / {b}" for n, m, b in zip(fp["node"], fp["material"], fp["batch"])}
            sel = left.selectbox("완제품(FP) 배치 선택", options, format_func=lambda n: labels.get(n, n))
            max_depth = right.slider("최대 깊이", 1, 30, 20)

            sub, visited, truncated = gdb.trace_subgraph(edges, sel, "upstream", max_depth=max_depth)
            if truncated:
                st.warning("그래프가 커서 일부만 표시했습니다(max_nodes 초과).")

            # tier 범례
            legend = " ".join(
                f'<span style="background:{c};color:white;padding:2px 8px;border-radius:4px;margin-right:4px">{t}</span>'
                for t, c in gdb.tier_legend())
            st.markdown("**Tier:** " + legend, unsafe_allow_html=True)

            if sub.empty:
                st.info("이 배치의 실측 상류 엣지가 없습니다(단일 export 범위 한계일 수 있음).")
            else:
                st.graphviz_chart(gdb.build_dot(sub, nodes, sel, "upstream"), use_container_width=True)
                st.caption(f"상류 노드 {len(visited)}개 · 엣지 {len(sub)}개  "
                           "(실선=실측 엣지, 점선=날짜 역전 / 색=엣지 규칙)")
                with st.expander("이 경로의 엣지 테이블"):
                    cols = [c for c in ["edge_kind", "from_material", "from_batch", "from_tier",
                                        "to_material", "to_batch", "to_tier", "confidence",
                                        "date_violation", "source_rule"] if c in sub.columns]
                    st.dataframe(sub[cols], use_container_width=True, hide_index=True)

    # ── Tab 2: 노드/엣지 테이블 ──────────────────────────────
    with tabs[1]:
        st.subheader("노드")
        tier_filter = st.multiselect("Tier 필터", ["RSM", "API", "DP", "SP", "FP", "OTHER"],
                                     default=[])
        nv = nodes if not tier_filter else nodes[nodes["tier"].isin(tier_filter)]
        st.dataframe(nv, use_container_width=True, hide_index=True)
        st.subheader("엣지")
        kind_filter = st.multiselect("Edge 종류", ["PROD", "REF_PO_ITEM", "DOC_TRANSFER"], default=[])
        ev = edges if not kind_filter else edges[edges["edge_kind"].isin(kind_filter)]
        st.dataframe(ev, use_container_width=True, hide_index=True)

    # ── Tab 3: 이력 ─────────────────────────────────────────
    with tabs[2]:
        st.subheader("빌드 이력 (build_runs)")
        st.dataframe(runs, use_container_width=True, hide_index=True)
        st.subheader("적재 이력 (ingest_log)")
        if ingest.empty:
            st.caption("적재 이력이 없습니다(--ingest 미사용).")
        else:
            st.dataframe(ingest, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
