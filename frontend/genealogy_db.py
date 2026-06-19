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
EXPECTED_COLOR = "#c9b8d8"  # BOM 기대(실측 없음) 점선 노드


def tier_from_code(material: str) -> str:
    """자재 코드 접두로 tier 추정(BOM_EXPECTED 노드 색상용)."""
    m = (material or "").upper()
    if m.startswith("1CNY"):
        return "RSM"
    if m.startswith("1CNZ") or m.startswith("2CN"):
        return "API"
    if m.startswith("3"):
        return "DP"
    if m.startswith("4"):
        return "SP"
    if m.startswith("5"):
        return "FP"
    return "OTHER"


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


def load_legacy_map(db_path: str, run_id: Optional[str] = None) -> Dict[str, str]:
    """legacy_code → current_code 매핑 (없으면 빈 dict)."""
    con = sqlite3.connect(db_path)
    try:
        if run_id and _table_exists(con, "gen_legacy_map"):
            df = pd.read_sql_query("SELECT legacy_code, current_code FROM gen_legacy_map WHERE run_id=?",
                                   con, params=[run_id])
        elif _table_exists(con, "v_latest_legacy_map"):
            df = pd.read_sql_query("SELECT legacy_code, current_code FROM v_latest_legacy_map", con)
        else:
            return {}
        return dict(zip(df["legacy_code"], df["current_code"]))
    finally:
        con.close()


def _norm(material: str, legacy_map: Dict[str, str]) -> str:
    return legacy_map.get(material, material)


# ----------------------------------------------------------------------
# 노드 선택 헬퍼
# ----------------------------------------------------------------------
def nodes_by_tier(nodes_df: pd.DataFrame, tier: str) -> pd.DataFrame:
    if nodes_df.empty or "tier" not in nodes_df.columns:
        return nodes_df
    sub = nodes_df[nodes_df["tier"] == tier].copy()
    return sub.sort_values([c for c in ["material", "batch"] if c in sub.columns])


def search_nodes(nodes_df: pd.DataFrame, query: str = "", tiers: Optional[List[str]] = None) -> pd.DataFrame:
    """material/batch 부분일치 + tier 필터로 노드 검색(선택 UI 용)."""
    if nodes_df.empty:
        return nodes_df
    sub = nodes_df
    if tiers:
        sub = sub[sub["tier"].isin(tiers)]
    q = (query or "").strip().upper()
    if q:
        mat = sub["material"].fillna("").str.upper()
        bat = sub["batch"].fillna("").str.upper()
        sub = sub[mat.str.contains(q, regex=False) | bat.str.contains(q, regex=False)]
    cols = [c for c in ["tier", "material", "batch"] if c in sub.columns]
    return sub.sort_values(cols) if cols else sub


def expected_missing(visited_nodes: Set[str], actual_edges: pd.DataFrame, bom_expected: pd.DataFrame,
                     nodes_df: pd.DataFrame, legacy_map: Optional[Dict[str, str]] = None) -> List[dict]:
    """서브그래프 각 노드에서 BOM 상 기대되지만 실측 상류 엣지가 없는 입력 목록.

    실측(actual) 들어오는 자재집합과 BOM 기대 입력집합을 legacy 정규화해 비교,
    빠진 것만 '끊긴 상류(BOM_EXPECTED)'로 반환. (material 단위 비교)
    """
    legacy_map = legacy_map or {}
    if bom_expected.empty or nodes_df.empty:
        return []
    node_mat = dict(zip(nodes_df["node"], nodes_df["material"]))
    # 노드별 실측 incoming 자재(정규화)
    incoming: Dict[str, Set[str]] = {}
    if not actual_edges.empty:
        for to_node, from_mat in zip(actual_edges["to_node"], actual_edges["from_material"]):
            incoming.setdefault(to_node, set()).add(_norm(from_mat, legacy_map))
    # to_material(정규화) → 기대 from_material 목록
    exp: Dict[str, Set[str]] = {}
    for to_m, from_m in zip(bom_expected["to_material"], bom_expected["from_material"]):
        exp.setdefault(_norm(to_m, legacy_map), set()).add(_norm(from_m, legacy_map))

    out: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    for n in visited_nodes:
        M = _norm(node_mat.get(n, ""), legacy_map)
        have = incoming.get(n, set())
        for F in sorted(exp.get(M, set())):
            if F and F not in have and (F, n) not in seen:
                seen.add((F, n))
                out.append({"from_material": F, "from_tier": tier_from_code(F),
                            "to_node": n, "to_material": node_mat.get(n, "")})
    return out


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
              direction: str = "upstream", expected: Optional[List[dict]] = None) -> str:
    """tier 를 좌→우 컬럼(RSM…FP)으로 정렬한 Graphviz DOT 문자열.

    노드 집합은 서브그래프 엣지(+시작 노드)로 엄격히 한정한다(전체 warehouse 아님).
    expected 가 주어지면 '끊긴 상류(BOM_EXPECTED)'를 점선 노드/엣지로 덧그린다.
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
    by_tier: Dict[str, List[str]] = {}
    for n in nodes:
        t = tier_of(n)
        fill = TIER_COLOR.get(t, "#bdbdbd")
        pen = ' penwidth=3 color="#000000"' if n == start_node else ""
        lines.append(f'  {nid[n]} [label="{_label(n)}", fillcolor="{fill}", fontcolor="white"{pen}];')
        by_tier.setdefault(t, []).append(nid[n])

    # BOM_EXPECTED: 실측 없는 기대 상류를 점선 노드+점선 엣지로
    for k, ex in enumerate(expected or []):
        if ex["to_node"] not in nid:
            continue
        eid = f"e{k}"
        et = ex.get("from_tier") or "OTHER"
        lines.append(f'  {eid} [label="{ex["from_material"]}\\n(BOM 기대)", '
                     f'fillcolor="{EXPECTED_COLOR}", fontcolor="#333333", style="rounded,filled,dashed"];')
        by_tier.setdefault(et, []).append(eid)
        lines.append(f'  {eid} -> {nid[ex["to_node"]]} [color="#9575b5", style=dashed];')

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
