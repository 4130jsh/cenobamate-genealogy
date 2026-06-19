"""합성 SAP MB51 export 생성기 (검증 전용).

실제 SAP는 민감 데이터라 리포에 없으므로, BOM DB(data/*.sqlite)의 실제 자재 코드
체계(1CNY*→2CNY*→3CNY*→4CN*→5CN*)를 그대로 따르는 합성 export를 만들어
genealogy_tool 의 엣지/추적 로직을 자체 검증한다.

세 가지 엣지 규칙을 모두 의도적으로 한 번씩 발화시키고, 추가로 날짜위반·legacy
코드·reversal/exclude movement 케이스를 섞어 회귀검증 기반으로 쓴다.
"""
from __future__ import annotations

import pandas as pd

# BOM DB에 실재하는 코드 (data/Cenobamate_BOM_DB_v1.sqlite 기준)
RSM = "1CNY001ZZZZZ"      # Raw Material (tier RSM)
RSM2 = "1CNY002ZZZZZ"     # 2CNY001 의 또 다른 BOM 입력 (실측 없음 → BOM_EXPECTED 용)
API = "2CNY001ZZZZZ"      # API
DP = "3CNY0Z001ZZZ"       # Drug Product
SP = "4CNS0Z2001ZZ"       # Semi-FP (Blister Strip)
FP = "5CNT014A1ZZZ"       # FP (Blister Card)
LEGACY_API = "1CNZ001ZZZZZ"  # legacy → 2CNY001ZZZZZ 매핑 대상

# SAP export 컬럼 (genealogy_tool.REQUIRED_SAP_COLS + 자주 쓰는 OPTIONAL)
COLUMNS = [
    "Material Document", "Material Doc.Item", "Material", "Material Description",
    "Batch", "Plant", "Storage Location", "Movement Type", "Movement Type Text",
    "Qty in unit of entry", "Unit of Entry", "Posting Date", "Document Date",
    "Entry Date", "Purchase order", "Item", "Reference", "Supplier", "User Name",
]


def _row(doc, item, mat, batch, sloc, mvt, qty, date,
         po="", po_item="", ref="", uom="KG", desc=""):
    return {
        "Material Document": doc, "Material Doc.Item": item, "Material": mat,
        "Material Description": desc, "Batch": batch, "Plant": "1100",
        "Storage Location": sloc, "Movement Type": mvt, "Movement Type Text": "",
        "Qty in unit of entry": qty, "Unit of Entry": uom, "Posting Date": date,
        "Document Date": date, "Entry Date": date, "Purchase order": po,
        "Item": po_item, "Reference": ref, "Supplier": "", "User Name": "tester",
    }


def build_rows() -> list[dict]:
    r = []

    # --- 케이스 1: PROD (같은 문서 내 543 소비 + 101 산출) → RSM → API ---
    r += [
        _row("DOC_PROD1", 1, RSM, "RSM-B1", "1100", 543, -100.0, "2026-01-05"),
        _row("DOC_PROD1", 2, API, "API-B1", "1104", 101, +50.0, "2026-01-05"),
    ]

    # --- 케이스 2: REF_PO_ITEM (Reference+PO+Item 동일, 다른 문서, 음수→양수) → API → DP ---
    # 문서를 다르게 두어 DOC_TRANSFER 와 겹치지 않게 격리
    r += [
        _row("DOC_REFA", 1, API, "API-B1", "1104", 311, -50.0, "2026-02-01",
             po="PO1", po_item="10", ref="REF1"),
        _row("DOC_REFB", 1, DP, "DP-B1", "3100", 311, +40.0, "2026-02-02",
             po="PO1", po_item="10", ref="REF1"),
    ]

    # --- 케이스 3: DOC_TRANSFER (같은 문서, 음수→양수, reference 비움) → DP → SP ---
    r += [
        _row("DOC_XFER1", 1, DP, "DP-B1", "3100", 301, -40.0, "2026-03-01"),
        _row("DOC_XFER1", 2, SP, "SP-B1", "4100", 301, +30.0, "2026-03-02"),
    ]
    # --- 케이스 3b: DOC_TRANSFER → SP → FP (체인 완성) ---
    r += [
        _row("DOC_XFER2", 1, SP, "SP-B1", "4100", 301, -30.0, "2026-04-01"),
        _row("DOC_XFER2", 2, FP, "FP-B1", "5100", 301, +20.0, "2026-04-02"),
    ]

    # --- 케이스 4: 날짜 역전 (from 날짜 > to 날짜) → date_violation=True ---
    r += [
        _row("DOC_DATEVIO", 1, DP, "DPV", "3100", 301, -10.0, "2026-05-10"),
        _row("DOC_DATEVIO", 2, SP, "SPV", "4100", 301, +10.0, "2026-05-01"),
    ]

    # --- 케이스 5: reversal(102)·exclude(921) movement → 엣지 생성 안 됨 ---
    r += [
        _row("DOC_REV", 1, DP, "DP-B1", "3100", 102, -5.0, "2026-06-01"),
        _row("DOC_REV", 2, SP, "SP-B1", "4100", 102, +5.0, "2026-06-01"),
        _row("DOC_EXC", 1, FP, "FP-B1", "5100", 921, -2.0, "2026-06-02"),
    ]

    # --- 케이스 6: legacy API 코드 (1CNZ*) tier 분류 확인용 ---
    r += [
        _row("DOC_LEGACY", 1, RSM2, "RSM2-B1", "1100", 543, -10.0, "2026-01-10"),
        _row("DOC_LEGACY", 2, LEGACY_API, "LAPI-B1", "1104", 101, +5.0, "2026-01-10"),
    ]

    # --- 케이스 7: 다중 output 생산 페어링 (choose_output_for_input 점수식 검증) ---
    # 한 문서에 RSM 2종 소비 + API 2종 산출. tier/UoM 동일하므로 BOM 토폴로지만이
    # 유일한 식별자다. item 순서상 naive(legacy)는 RSM-M1→API-M2 로 오결합하지만,
    # BOM(1CNY001→2CNY001, 1CNY002→2CNY002)을 보면 정답은 교차가 아닌 직결이다.
    #   BOM: 2CNY001ZZZZZ.in = 1CNY001ZZZZZ / 1CNY002ZZZZZ ...
    #        2CNY005ZZZZZ.in = 2CNY002ZZZZZ  (서로 다른 입력)
    r += [
        _row("DOC_MULTI", 1, RSM, "RSM-M1", "1100", 543, -100.0, "2026-07-01"),   # →2CNY001
        _row("DOC_MULTI", 2, "2CNY002ZZZZZ", "API2-M2", "1104", 101, +40.0, "2026-07-01"),
        _row("DOC_MULTI", 3, "1CNY002ZZZZZ", "RSM-M2", "1100", 543, -80.0, "2026-07-01"),  # 2CNY002.in
        _row("DOC_MULTI", 4, API, "API1-M1", "1104", 101, +50.0, "2026-07-01"),    # 2CNY001
    ]

    # --- 케이스 8: 같은 tier·다른 strength 간 가짜 전환 (transfer 페어링 차단 검증) ---
    # 4CNS0Z2001ZZ 와 4CNS1Z2001ZZ 는 둘 다 SP 지만 strength(0 vs 1)가 달라 서로 전환 불가.
    # BOM 상 입력관계도 없음(각각 3CNY0/3CNY1 에서 옴) → DOC_TRANSFER 로 페어링되면 안 됨.
    r += [
        _row("DOC_BADSTRENGTH", 1, "4CNS0Z2001ZZ", "SPX0", "4100", 301, -10.0, "2026-08-01"),
        _row("DOC_BADSTRENGTH", 2, "4CNS1Z2001ZZ", "SPX1", "4100", 301, +10.0, "2026-08-01"),
    ]

    # --- 케이스 9: 잘못 작성됐다가 취소(reversal)된 생산 문서 (reversal 넷팅 검증) ---
    # 같은 DP 배치(DPR)를 만든 두 생산 문서: 정상(APIOK 투입)과 오작성(APIBAD 투입).
    # 오작성 문서가 102/544 로 취소됨. 넷팅은 취소된 원본 문서를 무효화해
    # APIBAD→DPR 가짜 엣지를 제거하고 APIOK→DPR 만 남겨야 한다.
    r += [
        _row("DOC_RGOOD", 1, API, "APIOK", "1104", 543, -50.0, "2026-09-01", po="PO9", po_item="9"),
        _row("DOC_RGOOD", 2, DP, "DPR", "3100", 101, +50.0, "2026-09-01", po="PO9", po_item="9"),
        _row("DOC_RWRONG", 1, API, "APIBAD", "1104", 543, -50.0, "2026-09-02", po="PO9", po_item="9"),
        _row("DOC_RWRONG", 2, DP, "DPR", "3100", 101, +50.0, "2026-09-02", po="PO9", po_item="9"),
        # 취소 문서: 오작성분의 소비(544)·생산(102)을 역분개
        _row("DOC_RREV", 1, API, "APIBAD", "1104", 544, +50.0, "2026-09-03", po="PO9", po_item="9"),
        _row("DOC_RREV", 2, DP, "DPR", "3100", 102, -50.0, "2026-09-03", po="PO9", po_item="9"),
    ]

    # --- 케이스 10: 같은 DP를 만든 GR 3건 중 앞의 2건이 취소(연대순 넷팅) ---
    # 동일 DP 배치 DPC 를 3번 입고(101)했고 앞 2건이 reversal 됨. 연대순 매칭이면
    # 가장 이른 두 문서가 무효화되고 '마지막' 문서(DOC_C3, APIC3 투입)만 살아남아야 한다.
    r += [
        _row("DOC_C1", 1, API, "APIC1", "1104", 543, -50.0, "2026-10-01", po="POC", po_item="1"),
        _row("DOC_C1", 2, "3CNY1Z001ZZZ", "DPC", "3100", 101, +50.0, "2026-10-01", po="POC", po_item="1"),
        _row("DOC_C2", 1, API, "APIC2", "1104", 543, -50.0, "2026-10-02", po="POC", po_item="1"),
        _row("DOC_C2", 2, "3CNY1Z001ZZZ", "DPC", "3100", 101, +50.0, "2026-10-02", po="POC", po_item="1"),
        _row("DOC_C3", 1, API, "APIC3", "1104", 543, -50.0, "2026-10-03", po="POC", po_item="1"),
        _row("DOC_C3", 2, "3CNY1Z001ZZZ", "DPC", "3100", 101, +50.0, "2026-10-03", po="POC", po_item="1"),
        # 앞 2건 취소(소비 544 + 생산 102)
        _row("DOC_CR1", 1, API, "APIC1", "1104", 544, +50.0, "2026-10-04", po="POC", po_item="1"),
        _row("DOC_CR1", 2, "3CNY1Z001ZZZ", "DPC", "3100", 102, -50.0, "2026-10-04", po="POC", po_item="1"),
        _row("DOC_CR2", 1, API, "APIC2", "1104", 544, +50.0, "2026-10-05", po="POC", po_item="1"),
        _row("DOC_CR2", 2, "3CNY1Z001ZZZ", "DPC", "3100", 102, -50.0, "2026-10-05", po="POC", po_item="1"),
    ]

    # --- 케이스 11: 외주 다출력 문서 — PO-item 으로 라인↔부품 매칭 ---
    # 한 문서에서 같은 DP material 의 두 배치(DPp/DPq)를 생산하고 API 두 로트를 소비.
    # tier/BOM/UoM 동일하므로 PO-item 만이 어느 API가 어느 DP로 갔는지 가른다.
    #   APIp(po_item P1)→DPp(po_item P1), APIq(po_item P2)→DPq(po_item P2)
    # item 거리만 보면 APIp 는 DPq(가까움)로 오결합되지만 PO-item 이 바로잡아야 한다.
    r += [
        _row("DOC_POI", 1, API, "API-P", "1104", 543, -50.0, "2026-11-01", po="POX", po_item="P1"),
        _row("DOC_POI", 2, "3CNY0Z001ZZZ", "DP-Q", "3100", 101, +50.0, "2026-11-01", po="POX", po_item="P2"),
        _row("DOC_POI", 3, "3CNY0Z001ZZZ", "DP-P", "3100", 101, +50.0, "2026-11-01", po="POX", po_item="P1"),
        _row("DOC_POI", 4, API, "API-Q", "1104", 543, -50.0, "2026-11-01", po="POX", po_item="P2"),
    ]

    # --- 케이스 12: Bottle OR 경로 — Britestock 경유 (Tablet 은 직접 input 아님) ---
    # 5CNB2ZAA1ZZZ(Bottle) BOM input = 3CNY2Z001ZZZ(Tablet, ROUTE_DIRECT) | 4CNR2ZA001ZZ(Britestock, VIA).
    # 여기선 Tablet→Britestock→Bottle 로 제조(VIA 경로 실측) → Tablet 은 Bottle 의 BOM_EXPECTED 로
    # 뜨면 안 되고 Britestock 의 상류로 추적돼야 한다.
    r += [
        _row("DOC_BRIT", 1, "3CNY2Z001ZZZ", "DPB", "3100", 543, -50.0, "2026-12-01"),
        _row("DOC_BRIT", 2, "4CNR2ZA001ZZ", "BRIT", "4100", 101, +50.0, "2026-12-01"),
        _row("DOC_BOT", 1, "4CNR2ZA001ZZ", "BRIT", "4100", 543, -50.0, "2026-12-02"),
        _row("DOC_BOT", 2, "5CNB2ZAA1ZZZ", "BOT", "5100", 101, +50.0, "2026-12-02"),
    ]
    return r


def write_synthetic_sap(path: str) -> str:
    """합성 SAP export 를 xlsx(sheet 'Data')로 저장하고 경로를 반환."""
    df = pd.DataFrame(build_rows(), columns=COLUMNS)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Data", index=False)
    return path


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "out/synthetic_sap.xlsx"
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    print("wrote", write_synthetic_sap(out))
