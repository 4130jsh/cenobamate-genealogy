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
TRANSFER_COLOR = "#888888"  # 공장이전/재배치(같은 자재 다른 배치) 링크


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


def load_plant_map(db_path: str) -> Dict[str, str]:
    """plant_code → plant_name 매핑 (없으면 빈 dict)."""
    con = sqlite3.connect(db_path)
    try:
        if not _table_exists(con, "gen_plant_map"):
            return {}
        df = pd.read_sql_query("SELECT DISTINCT plant_code, plant_name FROM gen_plant_map", con)
        return {str(k): v for k, v in zip(df["plant_code"], df["plant_name"]) if v}
    finally:
        con.close()


def _norm(material: str, legacy_map: Dict[str, str]) -> str:
    return legacy_map.get(material, material)


def _map_plant(plant_str: str, plant_map: Dict[str, str]) -> str:
    """'1100,1210' → '본사, Patheon' 처럼 공장코드를 공장명으로 매핑."""
    if not plant_str:
        return ""
    parts = [p.strip() for p in str(plant_str).split(",") if p.strip()]
    return ", ".join((plant_map or {}).get(p, p) for p in parts)


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


def location_options(nodes_df: pd.DataFrame) -> List[str]:
    """노드 location(저장위치) 값을 콤마 분해해 유니크 옵션 목록으로(흐름검색 UI 용)."""
    if nodes_df.empty or "location" not in nodes_df.columns:
        return []
    toks: Set[str] = set()
    for v in nodes_df["location"].fillna(""):
        for t in str(v).split(","):
            t = t.strip()
            if t:
                toks.add(t)
    return sorted(toks)


def flow_search(edges_df: pd.DataFrame, nodes_df: pd.DataFrame,
                tiers: Optional[List[str]] = None, locations: Optional[List[str]] = None,
                kinds: Optional[List[str]] = None, date_from=None, date_to=None,
                query: str = "") -> pd.DataFrame:
    """멀티 조건(기간·tier·저장위치·전환유형·텍스트)으로 자재 흐름(엣지) 필터.

    - tiers: from_tier 또는 to_tier 가 선택 tier 에 속하는 엣지(흐름의 한쪽이라도 걸치면 포함)
    - locations: 엣지 양끝 노드의 location(저장위치)에 선택 토큰이 포함되면 포함
    - kinds: edge_kind(PROD/REF_PO_ITEM/DOC_TRANSFER)
    - date_from/date_to: posting_date(전기일) 범위 [from, to] (둘 중 하나만도 가능)
    - query: material/batch 부분일치(from/to 양쪽 대상)
    조건은 AND 로 결합(각 조건 내부는 OR). 빈 조건은 무시.
    """
    if edges_df.empty:
        return edges_df
    df = edges_df
    if tiers:
        ts = set(tiers)
        df = df[df["from_tier"].isin(ts) | df["to_tier"].isin(ts)]
    if kinds:
        df = df[df["edge_kind"].isin(kinds)]
    if (date_from or date_to) and "posting_date" in df.columns:
        d = pd.to_datetime(df["posting_date"], errors="coerce").dt.date
        keep = d.notna()
        if date_from:
            keep &= d >= date_from
        if date_to:
            keep &= d <= date_to
        df = df[keep]
    if locations and not df.empty:
        node_loc = dict(zip(nodes_df["node"], nodes_df["location"])) \
            if (not nodes_df.empty and "location" in nodes_df.columns) else {}
        fl = df["from_node"].map(node_loc).fillna("")
        tl = df["to_node"].map(node_loc).fillna("")
        mask = pd.Series(False, index=df.index)
        for loc in locations:
            mask |= fl.str.contains(loc, regex=False) | tl.str.contains(loc, regex=False)
        df = df[mask]
    q = (query or "").strip().upper()
    if q and not df.empty:
        cols = [c for c in ["from_material", "from_batch", "to_material", "to_batch"] if c in df.columns]
        m = pd.Series(False, index=df.index)
        for c in cols:
            m |= df[c].fillna("").str.upper().str.contains(q, regex=False)
        df = df[m]
    return df


def expected_missing(visited_nodes: Set[str], actual_edges: pd.DataFrame, bom_expected: pd.DataFrame,
                     nodes_df: pd.DataFrame, legacy_map: Optional[Dict[str, str]] = None) -> List[dict]:
    """서브그래프 각 노드에서 BOM 상 기대되지만 실측 상류 엣지가 없는 입력 목록.

    OR 경로(route) 인식: 한 경로의 input 이 실측되면 다른 경로는 끊긴 상류로 표시하지
    않는다(예: Bottle 이 Britestock 으로 제조됐으면 Tablet 은 직접 input 이 아님).
    어느 경로도 미실측이면 ROUTE_DIRECT(없으면 첫 경로)만 표시해 중복을 막는다.
    경로 없는(단일) input 은 기존대로 빠진 것만 표시.
    """
    legacy_map = legacy_map or {}
    if bom_expected.empty or nodes_df.empty:
        return []
    node_mat = dict(zip(nodes_df["node"], nodes_df["material"]))
    incoming: Dict[str, Set[str]] = {}
    if not actual_edges.empty:
        for to_node, from_mat in zip(actual_edges["to_node"], actual_edges["from_material"]):
            incoming.setdefault(to_node, set()).add(_norm(from_mat, legacy_map))

    has_route = "route" in bom_expected.columns
    has_group = "input_group" in bom_expected.columns
    exp_routed: Dict[str, Dict[str, Set[str]]] = {}    # to_material → route → {from} (공정 경로 OR)
    exp_grouped: Dict[str, Dict[str, Set[str]]] = {}   # to_material → group → {from} (호환 원료 OR)
    exp_unrouted: Dict[str, Set[str]] = {}             # to_material → {from}
    for i in range(len(bom_expected)):
        row = bom_expected.iloc[i]
        M = _norm(row["to_material"], legacy_map)
        F = _norm(row["from_material"], legacy_map)
        rt = (row["route"] if has_route else "") or ""
        ig = (row["input_group"] if has_group else "") or ""
        if rt:
            exp_routed.setdefault(M, {}).setdefault(rt, set()).add(F)
        elif ig:
            exp_grouped.setdefault(M, {}).setdefault(ig, set()).add(F)
        else:
            exp_unrouted.setdefault(M, set()).add(F)

    out: List[dict] = []
    seen: Set[Tuple[str, str]] = set()

    def emit(F: str, n: str):
        if F and F not in incoming.get(n, set()) and (F, n) not in seen:
            seen.add((F, n))
            out.append({"from_material": F, "from_tier": tier_from_code(F),
                        "to_node": n, "to_material": node_mat.get(n, "")})

    for n in visited_nodes:
        raw_mat = node_mat.get(n, "")
        # legacy API 코드(1CNZ*)는 RSM 미관리 시기 코드 → 투입 RSM 없음. BOM 기대 표시 안 함.
        if raw_mat in legacy_map:
            continue
        M = _norm(raw_mat, legacy_map)
        have = incoming.get(n, set())
        # 같은 자재 전입(공장이전/재배치) — 생산은 원천 배치에서 일어남 → 이 노드엔 BOM 기대 표시 안 함
        if M in have:
            continue
        for F in sorted(exp_unrouted.get(M, set())):
            emit(F, n)
        routes = exp_routed.get(M)
        if routes:
            all_routed = {f for s in routes.values() for f in s}
            real_incoming = {m for m in have if m and m != M}
            # 정의된 경로 실측 OR BOM 누락 경로라도 실제 상류 엣지가 있으면 확정 → 표시 안 함
            if (have & all_routed) or real_incoming:
                continue
            shown = routes.get("ROUTE_DIRECT") or next(iter(routes.values()))
            for F in sorted(shown):
                emit(F, n)
        # 호환 원료 그룹(ANY_OR_COMBO): 멤버 중 하나라도 실측이면 그룹 전체 표시 안 함; 없으면 대표 1개
        for members in (exp_grouped.get(M) or {}).values():
            if have & members:
                continue
            emit(sorted(members)[0], n)
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


def _san(text: str, maxlen: int = 34) -> str:
    """DOT 라벨용 정리: 따옴표/역슬래시 제거, 공백 정리, 길이 제한."""
    t = str(text or "").replace('"', "").replace("\\", "").replace("\n", " ").strip()
    t = " ".join(t.split())
    return (t[:maxlen] + "…") if len(t) > maxlen else t


def _label_full(node: str, desc: str = "", location: str = "") -> str:
    """자재코드 + (설명) + [배치] + (저장위치) 라벨."""
    mat, _, batch = str(node).partition("||")
    parts = [mat]
    d = _san(desc)
    if d:
        parts.append(d)
    if batch:
        parts.append(f"[{batch}]")
    loc = _san(location, 40)
    if loc:
        parts.append(f"위치: {loc}")
    return "\\n".join(parts)


def build_dot(sub_edges: pd.DataFrame, nodes_df: pd.DataFrame, start_node: str,
              direction: str = "upstream", expected: Optional[List[dict]] = None,
              show_dates: bool = False, plant_map: Optional[Dict[str, str]] = None) -> str:
    """tier 를 좌→우 컬럼(RSM…FP)으로 정렬한 Graphviz DOT 문자열.

    노드 집합은 서브그래프 엣지(+시작 노드)로 엄격히 한정한다(전체 warehouse 아님).
    expected 가 주어지면 '끊긴 상류(BOM_EXPECTED)'를 점선 노드/엣지로 덧그린다.
    """
    node_lookup = dict(zip(nodes_df["node"], nodes_df.get("tier", ""))) if not nodes_df.empty else {}
    node_desc = dict(zip(nodes_df["node"], nodes_df.get("description", ""))) if not nodes_df.empty else {}
    # 저장위치(storage location) 표시 — location 컬럼 우선, 없으면 공장코드→공장명 fallback
    has_loc = (not nodes_df.empty) and ("location" in nodes_df.columns)
    node_loc = dict(zip(nodes_df["node"], nodes_df["location"])) if has_loc else {}
    node_plant = dict(zip(nodes_df["node"], nodes_df.get("plant", ""))) if not nodes_df.empty else {}
    mat_desc: Dict[str, str] = {}
    if not nodes_df.empty and "material" in nodes_df.columns:
        for m, d in zip(nodes_df["material"], nodes_df.get("description", "")):
            if m and m not in mat_desc and d:
                mat_desc[m] = d
    edge_tier: Dict[str, str] = {}
    universe: Set[str] = {start_node} if start_node else set()
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
        "  ranksep=2.0;",                     # tier 간 간격 ↑ → 엣지 길어져 날짜 라벨 겹침 완화
        "  nodesep=0.7;",                     # 같은 tier 노드 간격 ↑ → fan-in 엣지/라벨 분산
        "  esep=\"+12\";",                    # 엣지/라벨 최소 간격 ↑ → 라벨 겹침 완화
        "  forcelabels=true;",
        "  overlap=false;",
        "  node [shape=box, style=\"rounded,filled\", fontsize=10, fontname=\"Arial\"];",
        "  edge [fontsize=8, fontname=\"Arial\"];",
    ]
    by_tier: Dict[str, List[str]] = {}
    for n in nodes:
        t = tier_of(n)
        fill = TIER_COLOR.get(t, "#bdbdbd")
        pen = ' penwidth=3 color="#000000"' if n == start_node else ""
        loclabel = node_loc.get(n, "") if has_loc else _map_plant(node_plant.get(n, ""), plant_map)
        lines.append(f'  {nid[n]} [label="{_label_full(n, node_desc.get(n, ""), loclabel)}", fillcolor="{fill}", fontcolor="white"{pen}];')
        by_tier.setdefault(t, []).append(nid[n])

    # BOM_EXPECTED: 실측 없는 기대 상류를 점선 노드+점선 엣지로
    for k, ex in enumerate(expected or []):
        if ex["to_node"] not in nid:
            continue
        eid = f"e{k}"
        et = ex.get("from_tier") or "OTHER"
        exd = _san(mat_desc.get(ex["from_material"], ""))
        exlabel = f'{ex["from_material"]}\\n{exd}\\n(BOM 기대)' if exd else f'{ex["from_material"]}\\n(BOM 기대)'
        lines.append(f'  {eid} [label="{exlabel}", '
                     f'fillcolor="{EXPECTED_COLOR}", fontcolor="#333333", style="rounded,filled,dashed"];')
        by_tier.setdefault(et, []).append(eid)
        lines.append(f'  {eid} -> {nid[ex["to_node"]]} [color="#9575b5", style=dashed];')

    for t in sorted(by_tier, key=lambda x: TIER_ORDER.get(x, 9)):
        ids = " ".join(f"{i};" for i in by_tier[t])
        lines.append(f"  {{ rank=same; {ids} }}")
    # 같은 노드쌍(from→to) 사이 평행 엣지는 1개로 합침(중복 이동 표시 제거).
    #   상세 표·타임라인엔 전부 남고, 그래프만 노드쌍당 1엣지로 정리.
    agg: Dict[Tuple[str, str], dict] = {}
    order: List[Tuple[str, str]] = []
    for _, r in sub_edges.iterrows():
        a, b = nid.get(r["from_node"]), nid.get(r["to_node"])
        if not a or not b:
            continue
        key = (a, b)
        if key not in agg:
            agg[key] = {"same_mat": str(r.get("from_material", "")).strip() == str(r.get("to_material", "")).strip()
                        and bool(str(r.get("from_material", "")).strip()),
                        "kind": r.get("edge_kind", ""), "dates": set(), "dv": False, "n": 0}
            order.append(key)
        info = agg[key]
        info["n"] += 1
        info["dv"] = info["dv"] or r.get("date_violation") in (1, True, "1", "True")
        dd = _edge_date(r.get("posting_date"))
        if dd:
            info["dates"].add(dd)

    for (a, b) in order:
        info = agg[(a, b)]
        dlabel = ""
        if show_dates and info["dates"]:
            ds = sorted(info["dates"])
            dlabel = ds[0] if len(ds) == 1 else f"{ds[0]}~{ds[-1]}"
        cnt = f" ×{info['n']}" if info["n"] > 1 else ""
        if info["same_mat"]:
            # 같은 자재 공장이전: 같은 tier(=같은 rank) 간 수평 엣지 → constraint=false 로
            # 레이아웃 왜곡/라벨 겹침 방지. 라벨은 줄바꿈으로 엣지선에서 띄움.
            lbl = "이전" + cnt + (f"\\n{dlabel}" if dlabel else "")
            lines.append(f'  {a} -> {b} [color="{TRANSFER_COLOR}", style=dashed, constraint=false, '
                         f'label="{lbl}", fontcolor="{TRANSFER_COLOR}", fontsize=8];')
        else:
            color = EDGE_COLOR.get(info["kind"], "#666666")
            style = "dashed" if info["dv"] else "solid"
            txt = (dlabel + cnt).strip()
            # 날짜 라벨을 엣지선 위로 살짝 띄워(앞에 개행) 인접 라벨/엣지와 겹침 완화
            lbl = f', label="\\n{txt}", fontcolor="#555555", fontsize=8' if txt else ""
            lines.append(f'  {a} -> {b} [color="{color}", style={style}{lbl}];')
    lines.append("}")
    return "\n".join(lines)


def _edge_date(s) -> str:
    """posting_date 문자열에서 날짜 부분(YYYY-MM-DD)만."""
    return str(s or "").split(" ")[0][:10]


def edge_date_bounds(sub_edges: pd.DataFrame):
    """서브그래프 엣지의 (최소, 최대) 전기일(date). 없으면 (None, None)."""
    if sub_edges.empty or "posting_date" not in sub_edges.columns:
        return None, None
    s = pd.to_datetime(sub_edges["posting_date"], errors="coerce").dropna()
    if s.empty:
        return None, None
    return s.min().date(), s.max().date()


def filter_edges_by_date(sub_edges: pd.DataFrame, start, end) -> pd.DataFrame:
    """전기일이 [start, end] 범위인 엣지만(날짜 없는 엣지는 보존)."""
    if sub_edges.empty or "posting_date" not in sub_edges.columns:
        return sub_edges
    d = pd.to_datetime(sub_edges["posting_date"], errors="coerce").dt.date
    keep = d.isna() | ((d >= start) & (d <= end))
    return sub_edges[keep]


def timeline_table(sub_edges: pd.DataFrame) -> pd.DataFrame:
    """전환/이동을 전기일 순으로 정렬한 타임라인 표."""
    if sub_edges.empty:
        return sub_edges
    df = sub_edges.copy()
    df["일자"] = df["posting_date"].map(_edge_date)
    df["_d"] = pd.to_datetime(df["posting_date"], errors="coerce")
    df["전환"] = df.apply(lambda r: f'{r.get("from_tier","")}→{r.get("to_tier","")}', axis=1)
    cols = {"일자": "일자", "edge_kind": "규칙", "from_material": "from_자재", "from_batch": "from_배치",
            "to_material": "to_자재", "to_batch": "to_배치", "전환": "전환",
            "alloc_qty": "수량", "source_rule": "근거"}
    have = [c for c in cols if c in df.columns]
    out = df.sort_values(["_d"], na_position="last")[have].rename(columns=cols)
    return out.reset_index(drop=True)


def tier_legend() -> List[Tuple[str, str]]:
    return [(t, TIER_COLOR[t]) for t in ["RSM", "API", "DP", "SP", "FP"]]


def edge_kind_legend() -> List[Tuple[str, str]]:
    """전환/이동 유형(edge_kind) 설명 — 흐름검색/범례 UI 용."""
    return [
        ("PROD",
         "생산: 같은 생산문서에서 원료 소비(543/541)와 제품 산출(101)이 함께 일어난 실제 제조 전환."),
        ("REF_PO_ITEM",
         "외주/구매 연계: 같은 Reference+PO+Item 으로 묶인 출고↔입고. 문서가 달라도 동일 거래(외주가공 등)로 연결."),
        ("DOC_TRANSFER",
         "문서 내 이동: 같은 자재문서 안의 음수→양수 이동(공정·공장·저장위치 이전 등)."),
        ("이전(회색 점선)",
         "공장이전/재배치: 같은 자재의 다른 배치 간 이동 표시(제조 전환이 아님). 그래프에서만 점선으로 구분."),
    ]


def expand_flow_upstream(edges_df: pd.DataFrame, seed_edges: pd.DataFrame,
                         max_depth: int = 30) -> pd.DataFrame:
    """seed_edges(검색 매칭 엣지)에 등장하는 모든 노드의 상류 흐름을 합쳐 반환.

    매칭된 자재 흐름뿐 아니라 그 자재들이 '어디서 왔는지' 전체 상류 경로를 포함한다.
    중복 엣지는 원본 인덱스 기준으로 제거하고 (매칭분 + 상류분) 합집합을 돌려준다.
    """
    if seed_edges.empty or edges_df.empty:
        return seed_edges
    collected: Set = set(seed_edges.index)
    seeds = set(seed_edges["from_node"]) | set(seed_edges["to_node"])
    for s in seeds:
        sub, _, _ = trace_subgraph(edges_df, s, "upstream", max_depth=max_depth)
        collected |= set(sub.index)
    return edges_df.loc[sorted(collected)].copy()


def dot_to_html(dot: str, title: str = "Genealogy") -> str:
    """DOT 를 브라우저에서 전체 화면에 맞춰(fit) 렌더하는 독립 HTML.

    Streamlit 스크롤 컨테이너와 달리 그래프 전체가 한 화면에 들어와 캡처/크롭이 쉽다.
    (렌더는 CDN d3-graphviz 사용 — 로컬 브라우저 인터넷 필요)
    """
    safe = dot.replace("\\", "\\\\").replace("`", "\\`")
    t = _san(title, 120)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{t}</title>
<style>
  html,body{{margin:0;height:100%;font-family:Arial,sans-serif}}
  #bar{{padding:6px 10px;background:#222;color:#eee;font-size:13px}}
  #bar b{{color:#fff}} #graph{{width:100%;height:calc(100% - 32px)}}
  #graph svg{{width:100%;height:100%}}
</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@hpcc-js/wasm@2/dist/graphviz.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-graphviz@5/build/d3-graphviz.min.js"></script>
</head><body>
<div id="bar"><b>{t}</b> — 휠=위아래 스크롤, <b>Ctrl+휠=확대/축소</b>, 드래그=이동.</div>
<div id="graph"></div>
<script>
  const dot = `{safe}`;
  const gv = d3.select("#graph").graphviz({{useWorker:false}}).fit(true).zoom(true);
  gv.renderDot(dot, function() {{
    try {{
      const zb = gv.zoomBehavior();
      if (zb) {{
        // 휠 단독=확대 금지(페이지 스크롤로 통과), Ctrl+휠일 때만 확대/축소. 드래그 패닝 허용.
        zb.filter(function(e) {{ return e.type === 'wheel' ? e.ctrlKey : !e.button; }});
        // 휠 한 틱당 확대 폭을 촘촘하게(기본의 약 1/4)
        zb.wheelDelta(function(e) {{
          return -e.deltaY * (e.deltaMode === 1 ? 0.0125 : e.deltaMode ? 0.25 : 0.0005);
        }});
      }}
    }} catch (err) {{}}
  }});
</script>
</body></html>"""
