"""두 pairing-mode 출력의 PROD 엣지 페어링 차이 비교 (로컬 검증용).

다중 output 생산 페어링은 입력당 출력 1개라 엣지 '개수'는 모드와 무관하게 같다.
달라지는 것은 각 입력이 '어느 출력(to_node)에 붙었는가' 뿐이므로, 같은 입력 행을
키로 두 출력의 to_node 를 비교해 바뀐 페어링만 추려낸다.

사용:
    python tests/compare_pairing.py out/legacy/genealogy_edges_actual.csv \
                                    out/bomaware/genealogy_edges_actual.csv
"""
from __future__ import annotations

import sys
import pandas as pd

# 입력(소비) 행을 유일하게 식별하는 키 — from 측은 모드와 무관하게 동일하다
KEY = ["source_file", "material_doc", "material_doc_item_from", "from_node"]
SHOW = ["material_doc", "from_material", "from_batch",
        "to_material_a", "to_batch_a", "to_material_b", "to_batch_b"]


def load_prod(path: str) -> pd.DataFrame:
    e = pd.read_csv(path, dtype=str)
    e = e[e["edge_kind"] == "PROD"].copy()
    return e


def main(a_path: str, b_path: str) -> int:
    a = load_prod(a_path)
    b = load_prod(b_path)
    print(f"A(legacy?)   PROD 엣지: {len(a):,}  ({a_path})")
    print(f"B(bom-aware?) PROD 엣지: {len(b):,}  ({b_path})")

    m = a.merge(b, on=KEY, how="outer", suffixes=("_a", "_b"), indicator=True)

    only_a = m[m["_merge"] == "left_only"]
    only_b = m[m["_merge"] == "right_only"]
    both = m[m["_merge"] == "both"].copy()

    changed = both[both["to_node_a"] != both["to_node_b"]]

    print(f"\n공통 입력 행: {len(both):,}")
    print(f"페어링 바뀐 입력: {len(changed):,}")
    print(f"A에만 있는 입력 행: {len(only_a):,}   B에만 있는 입력 행: {len(only_b):,}")

    if not changed.empty:
        print("\n=== 페어링이 바뀐 PROD 엣지 (A → B) ===")
        cols = [c for c in SHOW if c in changed.columns]
        with pd.option_context("display.max_rows", None, "display.width", 200):
            print(changed[KEY[1:] + cols].to_string(index=False))
    else:
        print("\n변경된 페어링 없음 (두 모드가 동일한 출력에 붙임).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python tests/compare_pairing.py <A_edges.csv> <B_edges.csv>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
