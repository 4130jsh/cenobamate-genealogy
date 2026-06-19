"""노드 엣지 진단: 특정 (material, batch)의 실측 incoming/outgoing 엣지를 규칙별로 나열.

"이 API 배치에 실제로 어떤 RSM이 연결됐나"를 정확히 확인하는 용도.

사용:
    python tests/diag_node_edges.py out/store/genealogy_edges_actual.csv 2CNY001ZZZZZ --batch 241036002N
"""
from __future__ import annotations

import argparse
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("edges_csv")
    ap.add_argument("material")
    ap.add_argument("--batch", required=True)
    args = ap.parse_args()

    e = pd.read_csv(args.edges_csv, dtype=str)
    node = f"{args.material}||{args.batch}"
    cols = ["edge_kind", "from_material", "from_batch", "to_material", "to_batch", "source_rule"]
    cols = [c for c in cols if c in e.columns]

    inc = e[e["to_node"] == node] if "to_node" in e.columns else e[(e["to_material"] == args.material) & (e["to_batch"] == args.batch)]
    out = e[e["from_node"] == node] if "from_node" in e.columns else e[(e["from_material"] == args.material) & (e["from_batch"] == args.batch)]

    print(f"=== {node} ===")
    print(f"\n[INCOMING] 이 배치로 들어온 실측 엣지: {len(inc)}개")
    if not inc.empty:
        print(inc[cols].sort_values(cols).to_string(index=False))
        print("  종류별:", inc["edge_kind"].value_counts().to_dict())
    print(f"\n[OUTGOING] 이 배치에서 나간 실측 엣지: {len(out)}개")
    if not out.empty:
        print(out[cols].sort_values(cols).to_string(index=False))
        print("  종류별:", out["edge_kind"].value_counts().to_dict())
    # self-loop 점검
    sl = e[(e.get("from_node") == e.get("to_node"))] if "from_node" in e.columns else pd.DataFrame()
    if not sl.empty:
        print(f"\n[경고] 자기-루프(from==to) 엣지 {len(sl)}개 — 위치 이동 노이즈 가능")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
