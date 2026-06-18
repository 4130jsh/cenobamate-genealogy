"""PROD 엣지 페어링 품질 진단 (로컬 검증용, 모드 무관).

genealogy_edges_actual.csv 의 PROD 엣지 각각에 대해, BOM 마스터가 정의한
입력→산출 부품관계와 일치하는지 점검한다. 두 pairing-mode 가 같은 결과를 낼 때
(diff 0건) "그래서 그 페어링이 실제로 맞느냐"를 독립적으로 확인하는 용도.

또한 다중 output 생산 문서(점수식이 실제로 작동하는 케이스)가 데이터에 몇 건
있는지도 함께 보고한다.

사용:
    python tests/diag_pairing.py out/legacy/genealogy_edges_actual.csv \
                                 data/Cenobamate_BOM_DB_v1.sqlite
"""
from __future__ import annotations

import os
import sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import genealogy_tool as gt  # noqa: E402


def bom_consistent(bom, frm: str, to: str):
    """True/False = BOM 일치 여부, None = 해당 산출의 BOM 입력 정보 없음(판정 불가)."""
    to_cur = bom.legacy_to_current.get(to, to)
    inputs = bom.material_to_inputs.get(to_cur, []) or bom.material_to_inputs.get(to, [])
    if not inputs:
        return None
    frm_cur = bom.legacy_to_current.get(frm, frm)
    inputs_cur = {bom.legacy_to_current.get(i, i) for i in inputs}
    return (frm in inputs) or (frm_cur in inputs_cur)


def main(edges_csv: str, db: str) -> int:
    bom = gt.GenealogyTool.load_bom_master(db)
    e = pd.read_csv(edges_csv, dtype=str)
    p = e[e["edge_kind"] == "PROD"].copy()
    print(f"PROD 엣지: {len(p):,}  ({edges_csv})")

    # 다중 output 생산 문서 = 한 문서에서 PROD 산출 노드가 2개 이상 (점수식이 실제 작동)
    out_per_doc = p.groupby("material_doc")["to_node"].nunique()
    multi_docs = set(out_per_doc[out_per_doc > 1].index)
    in_multi = int(p["material_doc"].isin(multi_docs).sum())
    print(f"다중 output 생산 문서: {len(multi_docs):,}건  (해당 문서 내 PROD 엣지: {in_multi:,})")
    print("  → 0이면 이 export 엔 모호한 다중 output 페어링이 없어 점수식 개선 효과가 나타날 여지가 없음")

    consistent = inconsistent = unknown = 0
    bad = []
    for _, r in p.iterrows():
        c = bom_consistent(bom, r["from_material"], r["to_material"])
        if c is None:
            unknown += 1
        elif c:
            consistent += 1
        else:
            inconsistent += 1
            bad.append((r["material_doc"], r["from_material"], r["from_batch"],
                        r["to_material"], r["to_batch"], r["material_doc"] in multi_docs))

    print(f"\nBOM 일치     : {consistent:,}")
    print(f"BOM 불일치   : {inconsistent:,}   ← 점검 대상 (소비→산출이 BOM 부품관계가 아님)")
    print(f"판정 불가    : {unknown:,}   (해당 산출의 BOM 입력 미정의)")

    if bad:
        print("\n=== BOM 불일치 PROD 엣지 (multi=다중output문서 여부) ===")
        bdf = pd.DataFrame(bad, columns=["material_doc", "from_material", "from_batch",
                                         "to_material", "to_batch", "multi_output_doc"])
        with pd.option_context("display.max_rows", None, "display.width", 200):
            print(bdf.to_string(index=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python tests/diag_pairing.py <edges.csv> <bom_db.sqlite>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
