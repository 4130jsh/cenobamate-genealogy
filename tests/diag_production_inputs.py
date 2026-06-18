"""생산 투입 진단: 특정 산출물(DP/SP/FP) 배치를 만든 문서들이 어떤 입력을 소비했는지.

genealogy 엣지가 '같은 문서 내 101 산출 + 543/541 소비'로 만들어지므로, 어떤 API
배치가 어느 DP 배치에 실제로 짝지어졌는지(그리고 그 소비가 반품/취소됐는지)를 본다.

사용:
    python tests/diag_production_inputs.py out/store/normalized_sap_rows.csv 3CNY2Z001ZZZ --batch CDBWD
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

PROD_OUT = {101, 521, 531}
PROD_CONSUME = {543, 541}
REVERSAL_TO_ORIGINAL = {102: 101, 542: 541, 544: 543, 532: 531, 922: 921, 926: 925}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("material", help="산출물 material (예: DP 3CNY2Z001ZZZ)")
    ap.add_argument("--batch", help="산출물 배치 (예: CDBWD)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str)
    df["movement_type"] = pd.to_numeric(df["movement_type"], errors="coerce").fillna(0).astype(int)
    df["qty_f"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)

    # 대상 산출물을 101 로 생산한 문서들
    out = df[(df["material"] == args.material) & (df["movement_type"].isin(PROD_OUT))]
    if args.batch:
        out = out[out["batch"] == args.batch]
    docs = sorted(set(out["material_doc"]))
    if not docs:
        print("해당 산출물의 생산(101) 문서가 없습니다.")
        return 0

    # reversal 매칭 (소비 우선)
    def qk(q): return round(abs(float(q)), 3)
    def key(mvt, r): return (mvt, r["material"], r["batch"], r["plant"], r["sloc"],
                             str(r["purchase_order"]), qk(r["qty_f"]))
    recs = df.to_dict("records")
    orig_index = defaultdict(list)
    for i, r in enumerate(recs):
        if r["movement_type"] not in REVERSAL_TO_ORIGINAL:
            orig_index[key(r["movement_type"], r)].append(i)
    matched = set(); doc_cnt = defaultdict(int)
    revs = [(i, r) for i, r in enumerate(recs) if r["movement_type"] in REVERSAL_TO_ORIGINAL]
    revs.sort(key=lambda ir: 0 if REVERSAL_TO_ORIGINAL[ir[1]["movement_type"]] in PROD_CONSUME else 1)
    for _, r in revs:
        om = REVERSAL_TO_ORIGINAL[r["movement_type"]]
        cands = [j for j in orig_index.get(key(om, r), []) if j not in matched]
        if not cands:
            continue
        pref = [j for j in cands if doc_cnt[str(recs[j]["material_doc"])] > 0]
        j = pref[0] if pref else cands[0]
        matched.add(j); doc_cnt[str(recs[j]["material_doc"])] += 1
    idx_by_pos = {id(r): i for i, r in enumerate(recs)}

    print(f"=== {args.material}{' / '+args.batch if args.batch else ''} 를 생산한 문서별 소비 입력 ===")
    consumed_batches = defaultdict(float)  # 순소비(취소 반영)
    for d in docs:
        doc_rows = df[df["material_doc"] == d]
        outs = doc_rows[doc_rows["movement_type"].isin(PROD_OUT)]
        cons = doc_rows[doc_rows["movement_type"].isin(PROD_CONSUME)]
        print(f"\n문서 {d}:")
        for _, r in outs.iterrows():
            print(f"  [산출] {int(r.movement_type)} {r.material}/{r.batch} qty={r.qty}")
        for _, r in cons.iterrows():
            # 이 소비행이 reversal 로 취소됐는지
            pos = df.index[(df["material_doc"] == d) & (df["material_doc_item"] == r["material_doc_item"])]
            print(f"  [소비] {int(r.movement_type)} {r.material}/{r.batch} qty={r.qty}  PO={r.purchase_order}")

    # 입력 배치별 순소비량(전 문서 합산, 취소 반영): Σ소비 − Σ반품
    print("\n=== 입력 API 배치별 순소비량 (취소/반품 반영, PO 무관 합산) ===")
    net = defaultdict(float)
    for r in recs:
        mt = r["movement_type"]
        if mt in PROD_CONSUME:
            net[(r["material"], r["batch"])] += abs(float(r["qty_f"]))
        elif mt in (544, 542):
            net[(r["material"], r["batch"])] -= abs(float(r["qty_f"]))
    # 대상 산출물 문서가 소비한 배치만 표시
    consumed = set()
    for d in docs:
        for _, r in df[(df["material_doc"] == d) & (df["movement_type"].isin(PROD_CONSUME))].iterrows():
            consumed.add((r["material"], r["batch"]))
    for mb in sorted(consumed):
        print(f"  {mb[0]}/{mb[1]}: 순소비 = {net.get(mb, 0):,.3f}  ({'≈0 → 전량 반품(투입 아님 가능성)' if abs(net.get(mb,0))<1e-6 else '양(+) → 실제 투입'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
