"""reversal 구조 진단: 특정 material 의 movement 와 취소(reversal) 매칭을 보여줌.

"왜 정상 배치가 제거됐나 / 오작성 배치의 소비가 취소됐나"를 데이터로 확인하는 용도.
normalized_sap_rows.csv(빌드 산출물)를 읽어 해당 material 의 행을 문서별로 나열하고,
reversal(102/544/…)이 어떤 원본과 매칭되는지, 어떤 문서가 '완전 취소'인지 보고한다.

사용:
    python tests/diag_reversals.py out/store/normalized_sap_rows.csv 3CNY2Z001ZZZ
    python tests/diag_reversals.py out/store/normalized_sap_rows.csv 1CNZ001ZZZZZ --batch 1082078
"""
from __future__ import annotations

import argparse
import pandas as pd

REVERSAL_TO_ORIGINAL = {102: 101, 542: 541, 544: 543, 532: 531, 922: 921, 926: 925}
PROD_MVTS = {101, 521, 531, 543, 541}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="normalized_sap_rows.csv 경로")
    ap.add_argument("material", help="조회할 material 코드")
    ap.add_argument("--batch", help="배치 필터(선택)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, dtype=str)
    for c in ("movement_type", "material_doc_item"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["qty_f"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)

    sub = df[df["material"] == args.material].copy()
    if args.batch:
        sub = sub[sub["batch"] == args.batch]
    if sub.empty:
        print("해당 material/batch 행이 없습니다.")
        return 0

    sub = sub.sort_values(["batch", "posting_date", "material_doc", "material_doc_item"])
    print(f"=== {args.material}{' / '+args.batch if args.batch else ''} movement 목록 ===")
    cols = ["material_doc", "material_doc_item", "movement_type", "batch", "qty",
            "posting_date", "plant", "sloc", "purchase_order"]
    print(sub[cols].to_string(index=False))

    # reversal 매칭 (속성 기준) + 완전 취소 문서 판정
    def qk(q): return round(abs(float(q)), 3)
    def key(mvt, r): return (mvt, r["material"], r["batch"], r["plant"], r["sloc"],
                             str(r["purchase_order"]), qk(r["qty_f"]))
    recs = df.to_dict("records")  # 매칭은 전체 행 대상(문서 전체 고려)
    from collections import defaultdict
    orig_index = defaultdict(list)
    for i, r in enumerate(recs):
        if r["movement_type"] not in REVERSAL_TO_ORIGINAL:
            orig_index[key(r["movement_type"], r)].append(i)
    matched = set(); doc_cnt = defaultdict(int)
    revs = [(i, r) for i, r in enumerate(recs) if r["movement_type"] in REVERSAL_TO_ORIGINAL]
    revs.sort(key=lambda ir: 0 if REVERSAL_TO_ORIGINAL[ir[1]["movement_type"]] in {543, 541} else 1)
    for _, r in revs:
        om = REVERSAL_TO_ORIGINAL[r["movement_type"]]
        cands = [j for j in orig_index.get(key(om, r), []) if j not in matched]
        if not cands:
            continue
        pref = [j for j in cands if doc_cnt[str(recs[j]["material_doc"])] > 0]
        j = pref[0] if pref else cands[0]
        matched.add(j); doc_cnt[str(recs[j]["material_doc"])] += 1

    doc_prod = defaultdict(list)
    for i, r in enumerate(recs):
        if r["movement_type"] in PROD_MVTS:
            doc_prod[str(r["material_doc"])].append(i)
    docs_here = set(sub["material_doc"])
    print("\n=== 이 material 이 등장하는 문서의 reversal 상태 ===")
    for d in sorted(docs_here):
        idxs = doc_prod.get(d, [])
        if not idxs:
            print(f"  {d}: 생산 movement 없음")
            continue
        full = all(i in matched for i in idxs)
        nmatched = sum(1 for i in idxs if i in matched)
        print(f"  {d}: 생산행 {len(idxs)}개 중 {nmatched}개 취소매칭 → {'완전취소(무효화 대상)' if full else '부분/미취소(보존)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
