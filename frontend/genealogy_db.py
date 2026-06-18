"""warehouse(sqlite) 읽기 + 상류/하류 서브그래프 + Graphviz DOT 생성 (순수 함수).

Streamlit UI(app.py)가 호출하는 데이터 계층. UI 없이 단독 테스트 가능하도록
사이드이펙트 없는 함수로 구성한다. genealogy_tool 결과 DB(gen_*·v_latest_*)만 읽고
엔진을 재실행하지 않는다(읽기 전용 조회).
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

TIER_ORDER = {"RSM": 0, "API": 1, "DP": 2, "SP": 3, "FP": 4, "OTHER": 9}
TIER_COLOR = {
    "RSM": "#9e9e9e", "API": "#1f77b4", "DP": "#2ca02c",
    "SP": "#ff7f0e", "FP": "#d62728", "OTHER": "#bdbdbd",
}
EDGE_COLOR = {"PROD": "#333333", "REF_PO_ITEM": "#1f77b4", "DOC_TRANSFER": "#2ca02c"}


# ----------------------------------------------------------------------
# DB 로딩
# ----------------------------------------------------------------------
def _table_exists(con, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)
    ).fetchone() is not None


def load_edges(db_path: str, run_id: Optional[str] = None) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        if run_id:
            return pd.read_sql_query("SELECT * FROM gen_edges WHERE run_id=?", con, params=[run_id])
        return pd.read_sql_query("SELECT * FROM v_latest_edges", con)
    finally:
        con.close()


def load_nodes(db_path: str, run_id: Optional[str] = None) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        if run_id:
            return pd.read_sql_query("SELECT * FROM gen_nodes WHERE run_id=?", con, params=[run_id])
        return pd.read_sql_query("SELECT * FROM v_latest_nodes", con)
    finally:
        con.close()


def load_runs(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "build_runs"):
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM build_runs ORDER BY built_at DESC, run_id DESC", con)
    finally:
        con.close()


def load_ingest_log(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "ingest_log"):
            return pd.DataFrame()
        return pd.read_sql_query("SELECT * FROM ingest_log ORDER BY ingested_at DESC", con)
    finally:
        con.close()


def load_bom_expected(db_path: str, run_id: Optional[str] = None) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        view = "v_latest_bom_expected"
        if run_id:
            return pd.read_sql_query("SELECT * FROM gen_bom_expected WHERE run_id=?", con, params=[run_id])
        if _table_exists(con, view):
            return pd.read_sql_query(f"SELECT * FROM {view}", con)
        return pd.DataFrame()
    finally:
        con.close()


# ----------------------------------------------------------------------
# 노드 선택 헬퍼
# ----------------------------------------------------------------------
def nodes_by_tier(nodes_df: pd.DataFrame, tier: str) -> pd.DataFrame:
    if nodes_df.empty or "tier" not in nodes_df.columns:
        return nodes_df
    sub = nodes_df[nodes_df["tier"] == tier].copy()
    return sub.sort_values([c for c in ["material", "batch"] if c in sub.columns])


# ----------------------------------------------------------------------
# 서브그래프 추적 (DB 엣지 기반 BFS)
# ----------------------------------------------------------------------
def trace_subgraph(edges_df: pd.DataFrame, start_node: str, direction: str = "upstream",
                   max_depth: int = 20, max_nodes: int = 400) -> Tuple[pd.DataFrame, Set[str], bool]:
    """start_node 에서 상류(upstream)/하류(downstream)로 엣지를 따라 서브그래프 수집.

    상류: to_node==current 인 엣지의 from_node 로 거슬러 올라감.
    하류: from_node==current 인 엣지의 to_node 로 내려감.
    반환: (서브그래프 엣지 DataFrame, 방문 노드 집합, 잘림 여부(max_nodes 초과))
    """
    if edges_df.empty:
        return edges_df, {start_node}, False
    if direction == "upstream":
        key, nxt = "to_node", "from_node"
    else:
        key, nxt = "from_node", "to_node"

    adj: Dict[str, List[int]] = {}
    kv = edges_df[key].tolist()
    for i, k in enumerate(kv):
        adj.setdefault(k, []).append(i)

    visited: Set[str] = {start_node}
    edge_idx: Set[int] = set()
    frontier = [(start_node, 0)]
    truncated = False
    nxt_col = edges_df[nxt].tolist()
    while frontier:
        node, depth = frontier.pop()
        if depth >= max_depth:
            continue
        for i in adj.get(node, []):
            edge_idx.add(i)
            child = nxt_col[i]
            if child and child not in visited:
                if len(visited) >= max_nodes:
                    truncated = True
                    continue
                visited.add(child)
                frontier.append((child, depth + 1))
    sub = edges_df.iloc[sorted(edge_idx)].copy() if edge_idx else edges_df.iloc[0:0].copy()
    return sub, visited, truncated


# ----------------------------------------------------------------------
# Graphviz DOT 생성 (tier 별 컬럼 정렬)
# ----------------------------------------------------------------------
def _label(node: str) -> str:
    mat, _, batch = str(node).partition("||")
    return f"{mat}\\n{batch}" if batch else str(node)


def build_dot(sub_edges: pd.DataFrame, nodes_df: pd.DataFrame, start_node: str,
              direction: str = "upstream") -> str:
    """tier 를 좌→우 컬럼(RSM…FP)으로 정렬한 Graphviz DOT 문자열.

    노드 집합은 서브그래프 엣지(+시작 노드)로 엄격히 한정한다(전체 warehouse 아님).
    """
    node_lookup = dict(zip(nodes_df["node"], nodes_df.get("tier", ""))) if not nodes_df.empty else {}
    edge_tier: Dict[str, str] = {}
    universe: Set[str] = {start_node}
    for _, r in sub_edges.iterrows():
        universe.add(r["from_node"]); universe.add(r["to_node"])
        if r.get("from_tier"):
            edge_tier[r["from_node"]] = r["from_tier"]
        if r.get("to_tier"):
            edge_tier[r["to_node"]] = r["to_tier"]

    def tier_of(n: str) -> str:
        return edge_tier.get(n) or node_lookup.get(n) or "OTHER"

    nodes = sorted(universe, key=lambda n: (TIER_ORDER.get(tier_of(n), 9), n))
    nid = {n: f"n{i}" for i, n in enumerate(nodes)}

    lines = [
        "digraph genealogy {",
        "  rankdir=LR;",                      # RSM(좌) → FP(우): 자재 흐름 방향
        "  node [shape=box, style=\"rounded,filled\", fontsize=10, fontname=\"Arial\"];",
        "  edge [fontsize=8, fontname=\"Arial\"];",
    ]
    for n in nodes:
        t = tier_of(n)
        fill = TIER_COLOR.get(t, "#bdbdbd")
        pen = ' penwidth=3 color="#000000"' if n == start_node else ""
        lines.append(f'  {nid[n]} [label="{_label(n)}", fillcolor="{fill}", fontcolor="white"{pen}];')
    by_tier: Dict[str, List[str]] = {}
    for n in nodes:
        by_tier.setdefault(tier_of(n), []).append(nid[n])
    for t in sorted(by_tier, key=lambda x: TIER_ORDER.get(x, 9)):
        ids = " ".join(f"{i};" for i in by_tier[t])
        lines.append(f"  {{ rank=same; {ids} }}")
    for _, r in sub_edges.iterrows():
        a, b = nid.get(r["from_node"]), nid.get(r["to_node"])
        if not a or not b:
            continue
        color = EDGE_COLOR.get(r.get("edge_kind", ""), "#666666")
        style = "dashed" if r.get("date_violation") in (1, True, "1", "True") else "solid"
        lines.append(f'  {a} -> {b} [color="{color}", style={style}];')
    lines.append("}")
    return "\n".join(lines)


def tier_legend() -> List[Tuple[str, str]]:
    return [(t, TIER_COLOR[t]) for t in ["RSM", "API", "DP", "SP", "FP"]]
