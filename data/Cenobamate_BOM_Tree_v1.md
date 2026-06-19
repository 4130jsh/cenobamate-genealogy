# Cenobamate BOM Tree (v1)

> Eurofarma 반영 완료 / Plant & Storage Location 통합

---

## 1. BOM Tree

> **[Bottle FP 대체경로(route) 안내]** Bottle SKU(`5CNB*`)는 두 가지 제조 경로를 가질 수 있으며, 이는 **AND(둘 다 투입)가 아니라 OR(택1)** 관계입니다.
> - **ROUTE_DIRECT**: Tablet(DP, `3CNY*`) → Bottle(FP) 직접
> - **ROUTE_VIA_BRITESTOCK**: Tablet(DP) → Britestock(SP, `4CNR*`) → Bottle(FP)
>
> 따라서 Bottle의 input에 Tablet과 Britestock이 함께 매핑된 경우, 두 자재가 동시에 FP에 들어가는 것이 아니라 **둘 중 한 경로로 제조**됩니다. DB의 `input_routes` 컬럼이 각 input의 경로를 구분하며(`코드:ROUTE_DIRECT|코드:ROUTE_VIA_BRITESTOCK`), genealogy 추적 시 실측에 따라 사용된 경로가 확정됩니다.

> **[API RSM 호환그룹(interchangeable) 안내]** API `2CNY001ZZZZZ`(US)의 RSM input 3종(`1CNY001ZZZZZ` US / `1CNY001NZZZZ` US_New / `1CNY002ZZZZZ` EU)은 **상호 대체 가능한 동일 등급**입니다. **택1 또는 복수 조합**으로 투입되며(예: US만, 또는 US+EU, 또는 3종 모두), 어느 조합이 와도 정상입니다. DB의 `input_group`/`input_group_mode`(ANY_OR_COMBO) 컬럼이 이를 정의하며, genealogy 추적 시 그룹 중 하나라도 실측되면 충족으로 처리하고 미사용 RSM을 누락으로 표시하지 않습니다. (route와 달리, 거치는 공정 경로가 다른 것이 아니라 같은 역할의 호환 원료입니다.)

| Level | Material Type | Material Code | Material Description | Batch Size / (CMO A) | Batch Size / (CMO B) | Unit | CMO A | CMO B | Input Material / Code | Input Material / Description | Conversion / Ratio | Conversion / Unit | Note | SAP Plant (CMO A) | SLoc (CMO A) | SAP Plant (CMO B) | SLoc (CMO B) | Input Routes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---  ---  --- | --- |
| 0 | Raw Material | 1CNY001ZZZZZ | YKP1941_US | 200 | 180 | KG | Lianhe | Wisdom | - | - | - | - | US API Input Option A / 3종 RSM 상호 대체 가능 (Interchangeable) | 1100 | 1101 | 1100 | 1102   |  |
| 0 | Raw Material | 1CNY001NZZZZ | YKP1941_US_New | 200 | 180 | KG | Lianhe | Wisdom | - | - | - | - | US API Input Option B / 신규 공정 적용 자재 / 3종 RSM 상호 대체 가능 | 1100 | 1101 | 1100 | 1102   |  |
| 0 | Raw Material | 1CNY002ZZZZZ | YKP1941_EU | 200 | 180 | KG | Lianhe | Wisdom | - | - | - | - | EU API 전용 Input / US API Input Option C로도 사용 가능 / 3종 RSM 상호 대체 가능 | 1100 | 1101 | 1100 | 1102   |  |
| 1 | API | 2CNY001ZZZZZ | Cenobamate API_US_Subcontract | 482 | - | KG | SK biotek | - | 1CNY001ZZZZZ / / 1CNY001NZZZZ / / 1CNY002ZZZZZ | YKP1941_US / / YKP1941_US_New / / YKP1941_EU | 0.861 | KG/KG | 실제 합성 공정 / RSM 3종(US·US_New·EU) 상호 대체 가능(interchangeable) / 택1 또는 복수 조합 투입 | 1100 | V202 | - | -   |  |
| 1 | API | 2CNY002ZZZZZ | Cenobamate API_EU_Subcontract | 482 | - | KG | SK biotek | - | 1CNY002ZZZZZ | YKP1941_EU | 0.861 | KG/KG | 실제 합성 공정 / EU RSM만 사용 | 1100 | V202 | - | -   |  |
| 1 | API | 2CNY004ZZZZZ | Cenobamate API_ROW1_Subcontract | 482 | - | KG | SK biotek | - | 2CNY001ZZZZZ | Cenobamate API_US | 1 | KG/KG | ⚠ 코드 변환만 (물리적 공정 없음) / US API → ROW1 API 코드 변환 | 1100 | V202 | - | -   |  |
| 1 | API | 2CNY005ZZZZZ | Cenobamate API_CA_Subcontract | 482 | - | KG | SK biotek | - | 2CNY002ZZZZZ | Cenobamate API_EU | 1 | KG/KG | ⚠ 코드 변환만 (물리적 공정 없음) / EU API → CA API 코드 변환 | 1100 | V202 | - | -   |  |
| 2 | Drug Product | 3CNY0Z001ZZZ | Cenobamate(US) 12.5mg_Tablet | 400000 | 200000 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 80000 | TAB/KG | Common Blend: API 40kg 중 5kg 분량 → 1배치 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY1Z001ZZZ | Cenobamate(US) 25mg_Tablet | 400000 | 200000 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 40000 | TAB/KG | Common Blend: API 40kg 중 10kg 분량 → 1배치 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z001ZZZ | Cenobamate(US) 50mg_Tablet | 500000 | 800000 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 20000 | TAB/KG | Common Blend: API 40kg 중 25kg 분량 → 1배치 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z001ZZZ | Cenobamate(US) 50mg_Tablet [Scale-up] | 800000 | - | - | Patheon | Avara | - | - | 20000 | TAB/KG | 50mg 단독 Scale-up 생산 / SAP 코드 동일, Desc.으로 구분 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY3Z001ZZZ | Cenobamate(US) 100mg_Tablet | 800000 | 800000 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 10000 | TAB/KG | 단독 제조 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY4Z001ZZZ | Cenobamate(US) 150mg_Tablet | 533333 | 533333 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 6666.66 | TAB/KG | 단독 제조 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY5Z001ZZZ | Cenobamate(US) 200mg_Tablet | 400000 | 1200000 | TAB | Patheon | Avara | 2CNY001ZZZZZ | API_US | 5000 | TAB/KG | 단독 제조 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY0Z004ZZZ | Cenobamate(CA) 12.5mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 80000 | TAB/KG | Avara: US 전용 (CA 미승인) | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY1Z004ZZZ | Cenobamate(CA) 25mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 40000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z004ZZZ | Cenobamate(CA) 50mg_Tablet | 500000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 20000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY3Z004ZZZ | Cenobamate(CA) 100mg_Tablet | 800000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 10000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY4Z004ZZZ | Cenobamate(CA) 150mg_Tablet | 533333 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 6666.66 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY5Z004ZZZ | Cenobamate(CA) 200mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_CA | 5000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY0Z005ZZZ | Cenobamate(IL) 12.5mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 80000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY1Z005ZZZ | Cenobamate(IL) 25mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY005ZZZZZ | API_ROW1 | 40000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z005ZZZ | Cenobamate(IL) 50mg_Tablet | 500000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 20000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY3Z005ZZZ | Cenobamate(IL) 100mg_Tablet | 800000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 10000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY4Z005ZZZ | Cenobamate(IL) 150mg_Tablet | 533333 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 6666.66 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY5Z005ZZZ | Cenobamate(IL) 200mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 5000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY0Z006ZZZ | Cenobamate(HK) 12.5mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 80000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY1Z006ZZZ | Cenobamate(HK) 25mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 40000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z006ZZZ | Cenobamate(HK) 50mg_Tablet | 500000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 20000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY3Z006ZZZ | Cenobamate(HK) 100mg_Tablet | 800000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 10000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY4Z006ZZZ | Cenobamate(HK) 150mg_Tablet | 533333 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 6666.66 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY5Z006ZZZ | Cenobamate(HK) 200mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 5000 | TAB/KG | - | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY0Z007ZZZ | Cenobamate(CN) 12.5mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 80000 | TAB/KG | CN Common Blend: API 40kg 중 5kg×3배치=15kg | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY1Z007ZZZ | Cenobamate(CN) 25mg_Tablet | 400000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 40000 | TAB/KG | CN Common Blend에 미포함 / 별도 단독 생산 시 해당 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z007ZZZ | Cenobamate(CN) 50mg_Tablet | 500000 | - | TAB | Patheon | Avara | 2CNY004ZZZZZ | API_ROW1 | 20000 | TAB/KG | CN Common Blend: API 40kg 중 25kg → 1배치 | 1210 | V301 | 1310 | V301   |  |
| 2 | Drug Product | 3CNY2Z007ZZZ | Cenobamate(CN) 50mg_Tablet [Scale-up] | 800000 | - | - | Patheon | Avara | - | - | 20000 | TAB/KG | 50mg 단독 Scale-up 생산 / SAP 코드 동일 | 1210 | V301 | 1310 | V301   |  |
| 3 | Semi-FP_Britestock | 4CNR1ZA001ZZ | Cenobamate(US) 25mg_Britestock_30ct | 13333 | - | BTL | Patheon | Avara | 3CNY1Z001ZZZ | US 25mg Tablet | 1/30 | BTL/TAB | Bottle Packaging 전 단계 | 1210 | V401 | 1310 | V401   |  |
| 3 | Semi-FP_Britestock | 4CNR2ZA001ZZ | Cenobamate(US) 50mg_Britestock_30ct | 16666 | - | BTL | Patheon | Avara | 3CNY2Z001ZZZ | US 50mg Tablet | 1/30 | BTL/TAB | - | 1210 | V401 | 1310 | V401   |  |
| 3 | Semi-FP_Britestock | 4CNR3ZA001ZZ | Cenobamate(US) 100mg_Britestock_30ct | 26666 | - | BTL | Patheon | Avara | 3CNY3Z001ZZZ | US 100mg Tablet | 1/30 | BTL/TAB | - | 1210 | V401 | 1310 | V401   |  |
| 3 | Semi-FP_Britestock | 4CNR4ZA001ZZ | Cenobamate(US) 150mg_Britestock_30ct | 17777 | - | BTL | Patheon | Avara | 3CNY4Z001ZZZ | US 150mg Tablet | 1/30 | BTL/TAB | - | 1210 | V401 | 1310 | V401   |  |
| 3 | Semi-FP_Britestock | 4CNR5ZA001ZZ | Cenobamate(US) 200mg_Britestock_30ct | 13333 | - | BTL | Patheon | Avara | 3CNY5Z001ZZZ | US 200mg Tablet | 1/30 | BTL/TAB | - | 1210 | V401 | 1310 | V401   |  |
| 3 | Semi-FP_Blister Strip | 4CNS0Z2001ZZ | Cenobamate(US) 12.5mg_Blister_Strip A | 14285 | - | BLS | PCI CA | - | 3CNY0Z001ZZZ | US 12.5mg Tablet | 1/14 | BLS/TAB | Blister Card 조립용 | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS0Z2007ZZ | Cenobamate(CN) 12.5mg_Blister_Strip | 14285 | - | BLS | PCI CA | - | 3CNY0Z007ZZZ | CN 12.5mg Tablet | 1/14 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS1Z2001ZZ | Cenobamate(US) 25mg_Blister_Strip B | 14285 | - | BLS | PCI CA | - | 3CNY1Z001ZZZ | US 25mg Tablet | 1/14 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS2Z1001ZZ | Cenobamate(US) 50mg_Blister_Strip C | 71428 | - | BLS | PCI CA | - | 3CNY2Z001ZZZ | US 50mg Tablet | 1/7 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS3Z1001ZZ | Cenobamate(US) 100mg_Blister_Strip D | 114285 | - | BLS | PCI CA | - | 3CNY3Z001ZZZ | US 100mg Tablet | 1/7 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS4Z1001ZZ | Cenobamate(US) 150mg_Blister_Strip E | 76190 | - | BLS | PCI CA | - | 3CNY4Z001ZZZ | US 150mg Tablet | 1/7 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 3 | Semi-FP_Blister Strip | 4CNS5Z1001ZZ | Cenobamate(US) 200mg_Blister_Strip F | 57142 | - | BLS | PCI CA | - | 3CNY5Z001ZZZ | US 200mg Tablet | 1/7 | BLS/TAB | - | 1220 | V401 | - | -   |  |
| 4 | FP_Bottle | 5CNB1ZAA1ZZZ | Cenobamate(US) 25mg_Bottle_30ct | 13333 | - | BTL | Patheon | - | 3CNY1Z001ZZZ / 4CNR1ZA001ZZ | US 25mg Tablet / US 25mg Britestock | 1/30 | BTL/TAB | Patheon만 제조 (PCI US 미제조) | 1210 | V501 | - | - | 직접=3CNY1Z001ZZZ 또는 Britestock경유=4CNR1ZA001ZZ |
| 4 | FP_Bottle | 5CNB2ZAA1SZZ | Cenobamate(USA) B1 Physician Samples(30) | 16666 | - | BTL | Patheon | - | 3CNY2Z001ZZZ / 4CNR2ZA001ZZ | US 50mg Tablet / US 50mg Britestock | 1/30 | BTL/TAB | Physician Sample / 2경로(직접 또는 Britestock 경유) | 1210 | V501 | - | - | 직접=3CNY2Z001ZZZ 또는 Britestock경유=4CNR2ZA001ZZ |
| 4 | FP_Bottle | 5CNB2ZAA1ZZZ | Cenobamate(US) B1_50mg_Bottle_30ct | 16666 | - | BTL | Patheon | PCI US | 3CNY2Z001ZZZ / 4CNR2ZA001ZZ | US 50mg Tablet / US 50mg Britestock | 1/30 | BTL/TAB | PCI US: Avara 제조 Tablet만 포장 | 1210 | V501 | 1230 | V501 | 직접=3CNY2Z001ZZZ 또는 Britestock경유=4CNR2ZA001ZZ |
| 4 | FP_Bottle | 5CNB2ZAA1ZZZ | Cenobamate(US) B1_50mg_Bottle_30ct [Scale-up] | 26666 | - | - | Patheon | - | 3CNY2Z001ZZZ / 4CNR2ZA001ZZ | US 50mg Tablet / US 50mg Britestock | 1/30 | BTL/TAB | Scale-up, SAP 코드 동일 | 1210 | V501 | - | - | 직접=3CNY2Z001ZZZ 또는 Britestock경유=4CNR2ZA001ZZ |
| 4 | FP_Bottle | 5CNB2ZAE3ZZZ | Cenobamate(CN) 50mg_Bottle_30ct | 16666 | - | BTL | Patheon | - | 3CNY2Z007ZZZ | CN 50mg Tablet | 1/30 | BTL/TAB | - | 1210 | V501 | - | - | 직접=3CNY2Z007ZZZ |
| 4 | FP_Bottle | 5CNB2ZAE3ZZZ | Cenobamate(CN) 50mg_Bottle_30ct [Scale-up] | 26666 | - | - | Patheon | - | 3CNY2Z007ZZZ | CN 50mg Tablet | 1/30 | BTL/TAB | Scale-up, SAP 코드 동일 | 1210 | V501 | - | - | 직접=3CNY2Z007ZZZ |
| 4 | FP_Bottle | 5CNB3ZAA1ZZZ | Cenobamate(US) B2_100mg_Bottle_30ct | 26666 | - | BTL | Patheon | PCI US | 3CNY3Z001ZZZ / 4CNR3ZA001ZZ | US 100mg Tablet / US 100mg Britestock | 1/30 | BTL/TAB | PCI US: Avara 제조 Tablet만 포장 | 1210 | V501 | 1230 | V501 | 직접=3CNY3Z001ZZZ 또는 Britestock경유=4CNR3ZA001ZZ |
| 4 | FP_Bottle | 5CNB4ZAA1ZZZ | Cenobamate(US) B3_150mg_Bottle_30ct | 17777 | - | BTL | Patheon | PCI US | 3CNY4Z001ZZZ / 4CNR4ZA001ZZ | US 150mg Tablet / US 150mg Britestock | 1/30 | BTL/TAB | PCI US: Avara 제조 Tablet만 포장 | 1210 | V501 | 1230 | V501 | 직접=3CNY4Z001ZZZ 또는 Britestock경유=4CNR4ZA001ZZ |
| 4 | FP_Bottle | 5CNB5ZAA1ZZZ | Cenobamate(US) B4_200mg_Bottle_30ct | 13333 | - | BTL | Patheon | PCI US | 3CNY5Z001ZZZ / 4CNR5ZA001ZZ | US 200mg Tablet / US 200mg Britestock | 1/30 | BTL/TAB | PCI US: Avara 제조 Tablet만 포장 | 1210 | V501 | 1230 | V501 | 직접=3CNY5Z001ZZZ 또는 Britestock경유=4CNR5ZA001ZZ |
| 4 | FP_Blister Card | 5CNT014A1SZZ | Cenobamate TP1_Physician Sample(12.5X25) | 3000 | - | PAK | PCI CA | - | 4CNS0Z2001ZZ / 4CNS1Z2001ZZ | 12.5mg Strip A / 25mg Strip B | 1+1 | Strip/PAK | Physician Sample | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT014A1ZZZ | Cenobamate(US) T1_Pack (12.5mg X 25mg) | 3000 | - | PAK | PCI CA | - | 4CNS0Z2001ZZ / 4CNS1Z2001ZZ | 12.5mg Strip A / 25mg Strip B | 1+1 | Strip/PAK | Titration Pack | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT0Z2E3ZZZ | Cenobamate(CN) 12.5mg_Pack | 28571 | - | PAK | PCI CA | - | 4CNS0Z2007ZZ / 4CNS0Z2007ZZ | CN 12.5mg Strip / CN 12.5mg Strip | 1+1 | Strip/PAK | - | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT234A1ZZZ | Cenobamate(US) T2_Pack (50mg X 100mg) | 3000 | - | PAK | PCI CA | - | 4CNS2Z1001ZZ / 4CNS3Z1001ZZ | 50mg Strip C / 100mg Strip D | 2+2 | Strip/PAK | Titration Pack | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT348A1ZZZ | Cenobamate(USA)2021 MP3_PK 100mg X 150mg | 3000 | - | PAK | PCI CA | - | 4CNS3Z1001ZZ / 4CNS4Z1001ZZ | 100mg Strip D / 150mg Strip E | 4+4 | Strip/PAK | Maintenance Pack | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT454A1ZZZ | Cenobamate(US) T3_Pack(150mg X 200mg) | 3000 | - | PAK | PCI CA | - | 4CNS4Z1001ZZ / 4CNS5Z1001ZZ | 150mg Strip E / 200mg Strip F | 2+2 | Strip/PAK | Titration Pack | 1220 | V501 | - | -   |  |
| 4 | FP_Blister Card | 5CNT458A1ZZZ | Cenobamate(US) MP4_Pack(150mg X 200mg) | 1000 | - | PAK | PCI CA | - | 4CNS4Z1001ZZ / 4CNS5Z1001ZZ | 150mg Strip E / 200mg Strip F | 4+4 | Strip/PAK | Maintenance Pack | 1220 | V501 | - | -   |  |

---

## 2. Common Blend

| Blend Type | 대상 시장 | API 투입량 / (KG) | 함량 | API 분량 / (KG) | 배치 수 | Material Code | Material Description | Batch Size / (Patheon) | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Standard / Common Blend | US / CA / IL / HK | 40 | 12.5mg | 5 | 1 | 3CNY0Z001ZZZ / (시장별 상이) | Cenobamate 12.5mg_Tablet | 400000 | - |
| Standard / Common Blend | US / CA / IL / HK | 40 | 25mg | 10 | 1 | 3CNY1Z001ZZZ / (시장별 상이) | Cenobamate 25mg_Tablet | 400000 | - |
| Standard / Common Blend | US / CA / IL / HK | 40 | 50mg | 25 | 1 | 3CNY2Z001ZZZ / (시장별 상이) | Cenobamate 50mg_Tablet | 500000 | 소계: 5+10+25 = 40 KG |
| CN / Common Blend | China | 40 | 12.5mg | 5 | 3 | 3CNY0Z007ZZZ | Cenobamate(CN) 12.5mg_Tablet | 400000 | 5kg × 3배치 = 총 15kg |
| CN / Common Blend | China | 40 | 50mg | 25 | 1 | 3CNY2Z007ZZZ | Cenobamate(CN) 50mg_Tablet | 500000 | 소계: 15+25 = 40 KG / 25mg 미생산 |
| 단독 제조 | 전 시장 공통 | - | 100mg | - | 1 | 3CNY3Z___ZZZ | Cenobamate 100mg_Tablet | 800000 | Common Blend 미적용 |
| 단독 제조 | 전 시장 공통 | - | 150mg | - | 1 | 3CNY4Z___ZZZ | Cenobamate 150mg_Tablet | 533333 | - |
| 단독 제조 | 전 시장 공통 | - | 200mg | - | 1 | 3CNY5Z___ZZZ | Cenobamate 200mg_Tablet | 400000 | - |
| 50mg Scale-up / (단독) | US / CN | - | 50mg | - | 1 | 3CNY2Z001ZZZ / 3CNY2Z007ZZZ | Cenobamate 50mg_Tablet [Scale-up] | 800000 | Common Blend 미적용 / 50mg 단독 생산 / SAP 코드 동일, Desc. 구분 |

---

## 3. Partner Mapping

| Partner | Country/ / Region | Supply / Level | 공급 제품 / (Material Code) | 공급 제품 / (Description) | 파트너 자체 / DP/Pkg 역량 | Note |
| --- | --- | --- | --- | --- | --- | --- |
| SK Life Sciences | US | FP | 5CNB1ZAA1ZZZ, 5CNB2ZAA1SZZ, / 5CNB2ZAA1ZZZ, 5CNB3ZAA1ZZZ, / 5CNB4ZAA1ZZZ, 5CNB5ZAA1ZZZ, / 5CNT014A1SZZ, 5CNT014A1ZZZ, / 5CNT234A1ZZZ, 5CNT348A1ZZZ, / 5CNT454A1ZZZ, 5CNT458A1ZZZ | Bottle 6종 + Blister Card 6종 / (Physician Sample 포함) | N/A (자사) | 최종 완제품(FP) 공급 / Bottle + Blister Card 전 품목 |
| Angelini | EU | API | 2CNY002ZZZZZ | Cenobamate API_EU_Subcontract | 보유 (자체 DP/Pkg) | EU RSM으로만 합성된 API 공급 |
| Ignis | China | FP | 5CNB2ZAE3ZZZ, 5CNT0Z2E3ZZZ | CN 50mg Bottle + CN 12.5mg Pack | - | CN Common Blend 적용 |
| Ignis | Hong Kong | DP | 3CNY0Z006ZZZ, 3CNY1Z006ZZZ, / 3CNY2Z006ZZZ, 3CNY3Z006ZZZ, / 3CNY4Z006ZZZ, 3CNY5Z006ZZZ | HK 12.5mg~200mg Tablet 6종 | 보유 (자체 Pkg) | Tablet 형태로 공급 → 자체 포장 |
| Ono | Japan | API | 2CNY001ZZZZZ | Cenobamate API_US_Subcontract | 보유 (자체 DP/Pkg) | US API 공급 |
| Knight | Canada | DP | 3CNY0Z004ZZZ, 3CNY1Z004ZZZ, / 3CNY2Z004ZZZ, 3CNY3Z004ZZZ, / 3CNY4Z004ZZZ, 3CNY5Z004ZZZ | CA 12.5mg~200mg Tablet 6종 | 보유 (자체 Pkg) | CA API(=EU API 코드 변환) 기반 DP 공급 |
| Eurofarma | LATAM | API | 2CNY001ZZZZZ | Cenobamate API_US_Subcontract | 보유 (자체 DP/Pkg) | US API 공급 |
| Hikma | MENA | API | 2CNY001ZZZZZ | Cenobamate API_US_Subcontract | 보유 (자체 DP/Pkg) | US API 공급 |
| Dong-A ST | Korea | API | 2CNY001ZZZZZ | Cenobamate API_US_Subcontract | 보유 (자체 DP/Pkg) | US API 공급 |
| Dexcel | Israel | DP | 3CNY0Z005ZZZ, 3CNY1Z005ZZZ, / 3CNY2Z005ZZZ, 3CNY3Z005ZZZ, / 3CNY4Z005ZZZ, 3CNY5Z005ZZZ | IL 12.5mg~200mg Tablet 6종 | 보유 (자체 Pkg) | ROW1 API(=US API 코드 변환) 기반 DP 공급 |

---

## 4. CMO Summary

| CMO | Country | 역할 (Role) | 담당 단계 / (Material Type) | 대상 시장 / (Market) | 주요 제품 | Batch Size 범위 | Note | SAP Plant | Key Storage Locations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lianhe | China | RSM 제조 / (CMO A) | Raw Material | 전 시장 | YKP1941_US / EU / US_New | 200 KG/batch | 기존 + 신규 공정 모두 적용 | 1100 | 1101 (RMat1941-Lianhe) |
| Wisdom | China | RSM 제조 / (CMO B) | Raw Material | 전 시장 | YKP1941_US / EU / US_New | 180 KG/batch | 기존 + 신규 공정 모두 적용 | 1100 | 1102 (RMat1941-Wisdom) |
| SK biotek | Korea | API 합성 | API | 전 시장 | US/EU API 실제 합성 / ROW1/CA API 코드 변환 | 482 KG/batch | 전 시장 API 단독 CMO / ROW1/CA는 물리적 공정 없음 | 1100 | V202 (Sub3089-BT) |
| Patheon | Canada | DP 제조 (CMO A) / + Britestock / + Bottle Packaging | DP → Semi-FP / → FP | 전 시장 | 전 함량 Tablet 제조 / Britestock 충전 / Bottle 라벨링/포장 | 다양 (함량별 상이) | 전 시장 DP CMO (Primary) / Patheon Tablet → Patheon Bottle | 1210 | V101(RM) / V301(DP) / V401(SP) / V501(FP) |
| Avara | USA | DP 제조 (CMO B) | Drug Product | US 전용 | US 시장 전 함량 Tablet | 다양 (함량별 상이) | US 시장 전용 승인 및 사용 / Avara Tablet → PCI US Bottle | 1310 | V101(RM) / V301(DP) / V401(SP) / V501(FP) |
| PCI CA | Canada | Blister Strip 제조 / + Blister Card 조립 | Semi-FP / → FP | US / CN | Blister Strip A~F (US) / Blister Strip (CN) / Blister Card (Titration/Maintenance) | 다양 (함량별 상이) | US: 전 함량 Blister Strip + Card / CN: 12.5mg Strip + Card | 1220 | V101-V102(RM) / V301-V302(DP) / V401-V402(SP) / V501-V502(FP) |
| PCI US | USA | Bottle Packaging / (Avara Tablet 전용) | Finished Product | US 전용 | US 50~200mg Bottle / (Avara 제조 Tablet만) | 다양 (함량별 상이) | 25mg Bottle은 미제조 / Avara Tablet 전용 포장 파트너 | 1230 | V101(RM) / V301(DP) / V401(SP) / V501(FP) |

---

## 5. Supply Flow

| 시장 / (Market) | Partner | Supply / Level | ① RSM Vendor | ② API CMO | ③ DP CMO | ④ Semi-FP CMO | ⑤ FP CMO / Packaging | 비고 (Note) | SAP Plant Flow |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US | SK Life Science | FP | Lianhe / Wisdom | SK biotek / (US API 합성) | Patheon / (CMO A) | Patheon (Britestock) / PCI CA (Blister Strip) | Patheon (Bottle) / PCI CA (Blister Card) | Patheon 라인: / RSM→API→DP→Britestock→Bottle /  / Blister 라인: / DP→Strip(PCI CA)→Card(PCI CA) | 1100 → 1210 → 1220 → 2100 |
| US / (Avara 라인) | SK Life Science | FP | Lianhe / Wisdom | SK biotek / (US API 합성) | Avara / (CMO B, US 전용) | Avara (Britestock) | PCI US (Bottle) / ※ 50~200mg만 | Avara Tablet → PCI US Bottle / 25mg Bottle은 Patheon만 제조 | 1100 → 1310 → 1230 → 2100 |
| EU | Angelini | API | Lianhe / Wisdom | SK biotek / (EU API 합성) | 파트너 자체 | 파트너 자체 | 파트너 자체 | RSM→API까지만 공급 / Angelini 자체 DP/Pkg | 1100 → Partner |
| China | Ignis | FP | Lianhe / Wisdom | SK biotek / (US API→ROW1 코드변환) | Patheon | PCI CA / (Blister Strip) | Patheon (Bottle) / PCI CA (Blister Card) | CN Common Blend 적용 / 12.5mg×3 + 50mg×1 | 1100 → 1210 → 1220 → Partner |
| Hong Kong | Ignis | DP | Lianhe / Wisdom | SK biotek / (US API→ROW1 코드변환) | Patheon | 파트너 자체 | 파트너 자체 | Tablet 형태로 공급 / Ignis 자체 포장 | 1100 → 1210 → Partner |
| Japan | Ono | API | Lianhe / Wisdom | SK biotek / (US API 합성) | 파트너 자체 | 파트너 자체 | 파트너 자체 | US API 공급 / Ono 자체 DP/Pkg | 1100 → Partner |
| Canada | Knight | DP | Lianhe / Wisdom | SK biotek / (EU API→CA 코드변환) | Patheon | 파트너 자체 | 파트너 자체 | CA API = EU API 코드 변환 / Tablel 공급, Knight 자체 포장 | 1100 → 1210 → Partner |
| LATAM | Eurofarma | API | Lianhe / Wisdom | SK biotek / (US API 합성) | 파트너 자체 | 파트너 자체 | 파트너 자체 | US API 공급 | 1100 → Partner |
| MENA | Hikma | API | Lianhe / Wisdom | SK biotek / (US API 합성) | 파트너 자체 | 파트너 자체 | 파트너 자체 | US API 공급 | 1100 → Partner |
| Korea | Dong-A ST | API | Lianhe / Wisdom | SK biotek / (US API 합성) | 파트너 자체 | 파트너 자체 | 파트너 자체 | US API 공급 | 1100 → Partner |
| Israel | Dexcel | DP | Lianhe / Wisdom | SK biotek / (US API→ROW1 코드변환) | Patheon | 파트너 자체 | 파트너 자체 | ROW1 API 기반 DP 공급 / Dexcel 자체 포장 | 1100 → 1210 → Partner |

---

## 5B. Legacy API Codes (과거 코드 — RSM 미관리, API부터 구매·관리)

> 과거에는 RSM(Raw Material)을 관리하지 않고 **API 단계부터 구매·관리**하던 시기가 있었음. 당시 사용된 코드 체계(`1CNZ*`)로, 현재는 재고가 남아있지 않으나 이력 추적·과거 데이터 정합성을 위해 보존. 현행 코드(`2CNY*`)와 매핑.

| 과거 코드 (Legacy) | Material Description | 공급 국가/용도 | 변환/투입 흐름 | 현행 코드 매핑 | 비고 |
| --- | --- | --- | --- | --- | --- |
| 1CNZ001ZZZZZ | Cenobamate API_US | US FP에 투입되어 사용 | → 1CNZ004ZZZZZ(API_ROW1)로 코드 변환되어 China·HongKong·Israel용 DP에 투입 | 2CNY001ZZZZZ (API_US) | RSM 미관리 시기 — API가 구매 시작점(Level 0 취급) |
| 1CNZ004ZZZZZ | Cenobamate API_ROW1 | China·HongKong·Israel용 DP에 투입 | 1CNZ001ZZZZZ(API_US)에서 코드 변환 (물리 공정 없음) | 2CNY004ZZZZZ (API_ROW1) | US API → ROW1 코드 변환 |
| 1CNZ002ZZZZZ | Cenobamate API_ROW | EU DP에 투입되어 사용 (현재는 EU에 API를 공급) | EU DP 직접 투입 | 2CNY002ZZZZZ (API_EU) | 과거 EU는 DP 투입용 API_ROW 사용, 현행은 EU에 API 공급으로 전환 |

> **체계 변화 요약**: 과거(`1CNZ*`) = RSM 미관리, API부터 관리(API가 최상위 구매 자재) → 현행(`1CNY*` RSM + `2CNY*` API) = RSM 단계부터 관리. 레거시 코드는 현재 재고 없음(이력 보존 목적).

---


## 6. Plant & Storage Location

### Section A: Plant Master

| Plant Code | Plant Name | Search Term 1 | Search Term 2 | Mapped CMO / 역할 |
| --- | --- | --- | --- | --- |
| 1100 | SK BP 본사 | SKBP-HQ | SKBP-HQ | RSM·API 수령 및 관리 (본사) |
| 1210 | SKBP-Patheon | SKBP-PATHEON | SKBP-PATHEON | Patheon (DP·SP·FP 제조) |
| 1220 | SKBP-PCI | SKBP-PCI | SKBP-PCI | PCI CA (Blister Strip·Card) |
| 1230 | SKBP-PCI US | SKBP-PCI US | SKBP-PCI US | PCI US (Bottle Packaging) |
| 1310 | SKBP-AVARA | SKBP-AVARA | SKBP-AVARA | Avara (DP 제조 - US 전용) |
| 2020 | SK Life Science Lab Inc. | SKLSL | SKLSL | SKLSL (Lab) |
| 2100 | SK Life Science Inc. | SKLSI | SKLSI | SKLSI (US Distribution·3PL) |

### Section B: Storage Location

| Plant | Location | Description | Material Stage |
| --- | --- | --- | --- |
| 1100 | 1100 | RMat.S/L | RSM/RM |
| 1100 | 1101 | RMat1941(Lianhe) | RSM/RM |
| 1100 | 1102 | RMat1941(Wisdom) | RSM/RM |
| 1100 | 1103 | RM1941DSVYJ | - |
| 1100 | 1104 | Sub3089DSVYJ | API (Intermediate) |
| 1100 | 1105 | RM1941DSVIC | - |
| 1100 | 1106 | Sub3089DSVIC | API (Intermediate) |
| 1100 | 3100 | DP (Semi-P) S/L | DP |
| 1100 | 4100 | SP (Semi-P) S/L | Semi-FP |
| 1100 | 5100 | FP (Final-P) S/L | FP |
| 1100 | 9100 | Sales Return-S/L | Return |
| 1100 | R101 | Sub-Caris(Micro) | API (Intermediate) |
| 1100 | R102 | SubCaris_Cambrex | API (Intermediate) |
| 1100 | V101 | RMat1941(Porton) | RSM/RM |
| 1100 | V201 | Sub3089(Porton) | API (Intermediate) |
| 1100 | V202 | Sub3089(BT) | API (Intermediate) |
| 1210 | V101 | RM-Patheon | RSM/RM |
| 1210 | V301 | DP-Patheon | DP |
| 1210 | V401 | SP-Patheon | Semi-FP |
| 1210 | V501 | FP-Patheon | FP |
| 1210 | V901 | Sales Return | Return |
| 1220 | V101 | RM-PCI Mis | RSM/RM |
| 1220 | V102 | RM-PCI BRT | RSM/RM |
| 1220 | V301 | DP-PCI Mis | DP |
| 1220 | V302 | DP-PCI BRT | DP |
| 1220 | V401 | SP-PCI Mis | Semi-FP |
| 1220 | V402 | SP-PCI BRT | Semi-FP |
| 1220 | V501 | FP-PCI Mis | FP |
| 1220 | V502 | FP-PCI BRT | FP |
| 1220 | V901 | Sales Return | Return |
| 1230 | V101 | RM-PCI US | RSM/RM |
| 1230 | V301 | DP-PCI US | DP |
| 1230 | V401 | SP-PCI US | Semi-FP |
| 1230 | V501 | FP-PCI US | FP |
| 1230 | V901 | Sales Return | Return |
| 1310 | V101 | RM-AVARA | RSM/RM |
| 1310 | V301 | DP-AVARA | DP |
| 1310 | V401 | SP-AVARA | Semi-FP |
| 1310 | V501 | FP-AVARA | FP |
| 1310 | V901 | Sales Return | Return |
| 2020 | 5100 | Gen. Store | General |
| 2100 | 5100 | In-Transit-CAD | In-Transit |
| 2100 | 5105 | In-Transit-KNP | In-Transit |
| 2100 | 5200 | Cardinal (3PL) | 3PL/Distribution |
| 2100 | 5300 | Return | Return |
| 2100 | 5400 | Walgreens HUB | 3PL/Distribution |
| 2100 | 5500 | Knipper (3PL) | 3PL/Distribution |

---

## 7. CMO Pricing Master (단가 종합 정리)

> 본 섹션은 전략 수립 모델(Cockpit v10)에 반영된 전 단계 CMO 단가를 종합 정리한 것입니다. 통화 USD. 관세는 2026.10 발효·강도 설정에 따라 변동.

### 7.1 RSM 단가 (YKP1941, China 제조 — 물량별)

**US API 축 (USD/kg)** — 모델 적용단가 = avg(Wisdom 신규, Lianhe 기존)

| 물량 (MT) | Wisdom 기존 | Wisdom 신규 | Lianhe 기존 | 모델 적용(avg) | 비고 |
| --- | --- | --- | --- | --- | --- |
| 1.0 | 625 | 600 | 776 | 688 | |
| 2.1 | 610 | 590 | 761 | 676 | |
| 5.3 | 605 | 520 | 493 | 507 | |
| 8.5 | 598 | 510 | 466 | 488 | |
| 10.0 | 565 | 505 | 453 | 479 | 10MT 이상 tier |

**EU API 축 (USD/kg)** — Lianhe Applied 단가(EU 버블 반영, 고가)

| 물량 (MT) | Lianhe Applied | (US 단가 대비) | EU 버블 |
| --- | --- | --- | --- |
| 1.0 | 1,067 | 776 | +42 |
| 2.1 | 1,047 | 761 | +40 |
| 5.3 | 863 | 493 | +159 |
| 8.5 | 767 | 466 | +101 |
| 10.0 | 717 | 453 | +70 |

- RSM→API 전환비율: API 1kg = RSM 1/0.861 kg
- RSM 통관가(invoice): $680/kg, API 통관가: $2,400/kg

### 7.2 API 단가 (제조비 기준, USD/kg)

| CMO | 제조국 | 제조비 ($/kg) | RSM 출처 | 도입비용 (one-time) | 리드타임 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| **SK biotek (SKBT)** | Korea | **1,177** (25배치/12t) | China (Lianhe/Wisdom) | **$0** (기존 CMO) | — | 20배치=$1,211 / 40배치=$1,108 / FTZ 재수출로 RSM 관세 0% |
| **Porton** | China | **760.79** (PV $895.05 × 85%) | China 자국 | ~$1,385,100 (2022·미확보) | — | China-origin / milling PV 필요 |
| **Cambrex** | USA | **2,076** (8MT) | China 수입 | **$9,122,000** | 16개월 | CAPEX $1,507,500 (spinning riffler+jet mill) |
| **SKPT** | USA | **2,099** (8MT) | China 수입 | **$11,321,800** | 8개월 | |
| **Piramal** | USA | **4,460** (8MT, v02) | India (Ennore, 포함) | **$7,014,875** | 11개월 | RSM 단가 포함(1-5MT $4,980/5-8MT $4,460/8-10MT $4,400) |
| **Curia** | USA | **1,095** (8MT) | China 수입 | **$3,367,600** | 14개월 | **No-go** (2026 FDA 483) |

**SKBT API All-in 분해 (US향, 20배치 $1,211/kg 기준)**

| 항목 | $/kg | 근거 |
| --- | --- | --- |
| 제조비 | 1,211 | Schedule C 20배치(9,640kg) |
| + RSM 원가 | ~556 | US RSM ÷ 0.861 |
| + RSM 수입관세 (CN→KR) | **0** | 한국 FTZ 반입→제조→2년내 재수출 면제 |
| + API 수출관세 (KR→US) | ~360 | KR→US 15% (수입국 부담) |
| **= All-in** | **~2,127** | (FTZ 적용 후, 기존 $2,163 대비 RSM 관세 $36 제거) |

### 7.3 DP 단가 (Tablet 제조, USD / 1,000 TAB)

| 함량 | Avara (US, Tier2) | Patheon (CA, Camp1) | 비고 |
| --- | --- | --- | --- |
| 12.5mg | 81.99 | 91.97 | |
| 25mg | 144.64 | 100.35 | |
| 50mg | 80.85 | 103.84 | |
| 100mg | 80.49 | 89.09 | |
| 150mg | 116.48 | 132.45 | |
| 200mg | 141.57 | 175.66 | |

- Avara Tier 기준: T1(<10M TAB), **T2(10~20M, 기본값)**, T3(>20M)
- Avara = US 전용 / Patheon = 전 시장 (Primary DP)

### 7.4 SP (Semi-FP) 단가

**Patheon Bottle (Britestock, USD/BTL, FS Pack)**

| 함량 | 25mg | 50mg | 100mg | 150mg | 200mg |
| --- | --- | --- | --- | --- | --- |
| FS Pack/BTL | 1.88 | 1.78 | 1.66 | 1.76 | 1.88 |

**PCI CA Blister Strip (USD/BLS)**

| 함량 | 12.5/25mg (14ct) | 50/100/150/200mg (7ct) |
| --- | --- | --- |
| Strip 단가 | 0.49 | 0.56 |

**PCI US Bottle Packaging (USD/BTL, Standard, 50-200mg만)**

| 함량 | 50mg | 100mg | 150mg | 200mg |
| --- | --- | --- | --- | --- |
| Pkg/BTL | 4.27 | 4.27 | 4.55 | 3.95 |

### 7.5 FP 단가 (완제품, USD/unit)

**Bottle FP Total (DP + Pkg 포함)**

| 함량 | Patheon CA | PCI US (Avara DP+PCI US Pkg) | 비고 |
| --- | --- | --- | --- |
| 25mg | 4.89 | — | 25mg는 Patheon만 |
| 50mg | 4.90 | 6.70 | |
| 100mg | 4.33 | 6.69 | |
| 150mg | 5.73 | 8.05 | |
| 200mg | 7.15 | 8.20 | |

**PCI CA Blister Card (USD/Card, Run 3K) — 포장·조립만 (DP 별도)**

| Pack | TP1 (12.5×25) | TP2 (50×100) | TP3 (150×200) | MP3B (100×150) | MP4 (150×200) |
| --- | --- | --- | --- | --- | --- |
| Card 단가 | 7.76 | 9.02 | 9.02 | 14.62 | 14.62 |

- 카드는 PCI CA 전용(US 포장 옵션 없음) → 카드 FP는 항상 CA→US 관세 노출
- FP 분해: 병 = DP(CMO)+포장(site) / 카드 = 포장 + DP(CMO 별도가산)

### 7.6 관세 구조 (對中 API 수입관세, 수령국별)

| 수령국 | Partner | 對中 관세 | 근거 |
| --- | --- | --- | --- |
| US | SK Life Science | **100%** | Section 232 (특허 100%, 최대 200%) |
| EU | Angelini | 0~6.5% | WTO 의약품협정 MFN (등재 시 0%) |
| Canada | Knight | 0~6.5% | 협정 서명국 (의약품 분쟁 제외) |
| Japan | Ono | 0% | 협정 서명국 |
| Korea (RSM·FTZ) | SKBT | **0%** | FTZ 반입→제조→2년내 재수출 면제 |
| Hong Kong | Ignis | 0% | 자유항 |
| LATAM (Brazil) | Eurofarma | 8~14% | 비서명국 Mercosur CET |
| MENA | Hikma | ~5% | 국가별 상이 |
| Israel | Dexcel | 0~low | 확인 필요 |

**기타 노드 간 관세**
- CN→US (Porton API): 100% (Section 232) / CA→US (FP route): 100% (FP TP 과세표준)
- KR→US (SKBT API 수출): 15% / KR→EU·CA·기타: 0% (협정)

### 7.7 도입비용 (one-time, US Onshoring CMO)

| CMO | R&D Total | Production Total | **Overall Total** | 리드타임 | PV Batch Scale |
| --- | --- | --- | --- | --- | --- |
| Cambrex | $1,546,600 | $1,821,000 | **$9,122,000** | 16개월 | 450kg |
| SKPT | $4,032,870 | $7,288,930 | **$11,321,800** | 8개월 | 500kg |
| Piramal | $2,295,125 | $4,719,750 | **$7,014,875** | 11개월 | 240kg |
| Curia | $1,546,600 | $1,821,000 | **$3,367,600** | 14개월 | 500kg |
| SKBT | — | — | **$0** (기존) | — | — |
| Porton | — | — | ~$1,385,100 (2022·미확보) | — | 300kg |

> **TCO = 5년 운영 COGS + 도입비용**. US onshoring은 도입비 발생하나 KR→US 수출관세(15%) 또는 CN→US(100%) 회피. SKBT는 도입비 $0 + FTZ로 RSM 관세 0%이나 KR→US 15% 수출관세 부담.

---