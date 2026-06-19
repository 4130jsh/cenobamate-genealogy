# BOM 변경 내역 (BOM_CHANGELOG)

> Claude Code 전달용. `data/Cenobamate_BOM_DB_v1.*`(sqlite/xlsx/schema/BOM tree.md)에 적용된 변경 이력입니다.
> 모든 변경은 **3개 산출물(sqlite, xlsx, BOM tree.md)에 일관 반영**되어야 하며, schema.sql은 sqlite에서 재생성합니다.
> 단일 출처는 sqlite입니다. 변경 시 이 문서를 함께 갱신하세요.

---

## 적용된 변경 요약

| # | 변경 | 대상 | 상태 |
| --- | --- | --- | --- |
| 1 | 레거시 API 코드 추가 (`1CNZ*`) | `legacy_api_codes` 테이블 / `LEGACY_Codes` 탭 / md §5B | 적용됨 |
| 2 | Bottle SKU input 오매핑 수정 (Blister Strip → Britestock) | `bom_tree` 3행 | 적용됨 |
| 3 | Bottle FP 대체경로(route) 메타 추가 | `bom_tree` 컬럼 2개 + 9행 | 적용됨 |
| 4 | 1~6번 BOM 탭 전체를 SQLite 테이블로 적재 | sqlite 7개 테이블 | 적용됨 |
| 5 | BOM tree.md 표에 Input Routes 컬럼 추가 | md §1 표 | 적용됨 |
| 6 | Physician Sample(5CNB2ZAA1SZZ) 대체경로 추가 | bom_tree 1행 | 적용됨 |
| 7 | API RSM 호환그룹(interchangeable) 반영 | bom_tree 컬럼 2개 + 1행 | 적용됨 |

---

## 변경 1 — 레거시 API 코드 추가

**배경**: 과거 RSM 미관리 시기, API부터 구매·관리하던 코드 체계(`1CNZ*`). 현재 재고 없음, 이력 보존 목적.

**테이블**: `legacy_api_codes` (별도 테이블, bom_tree와 분리)

| legacy_code | description | current_code_map (현행 매핑) |
| --- | --- | --- |
| `1CNZ001ZZZZZ` | Cenobamate API_US | `2CNY001ZZZZZ` (API_US) |
| `1CNZ004ZZZZZ` | Cenobamate API_ROW1 | `2CNY004ZZZZZ` (API_ROW1) |
| `1CNZ002ZZZZZ` | Cenobamate API_ROW | `2CNY002ZZZZZ` (API_EU) |

**컬럼**: `legacy_code`(PK), `material_description`, `supply_use`, `conversion_flow`, `current_code_map`, `status`(=discontinued), `note`

**도구 처리**: `legacy_to_current` 매핑으로 로딩. 추적 시 현행 `2CNY*`로 **표시만** 하고 **없는 RSM 배치를 지어내지 않음**. BOM_EXPECTED에서 `LEGACY_API_NO_RSM_ACTUAL` 상태로 표기.

**반영 위치**: sqlite `legacy_api_codes` / xlsx `LEGACY_Codes` 탭 / `Cenobamate_BOM_Tree_v1.md` §5B

---

## 변경 2 — Bottle SKU input 오매핑 수정

**문제**: Bottle SKU 100/150/200mg의 input에 **Blister Strip**(`4CNS*`, 카드 조립용)이 잘못 매핑됨. Bottle은 병 충전용 **Britestock**(`4CNR*`)을 받아야 함.

**수정** (`bom_tree`, input_material_code/description):

| material_code | SKU | 수정 전 (오류) | 수정 후 |
| --- | --- | --- | --- |
| `5CNB3ZAA1ZZZ` | B2 100mg Bottle | `4CNS3Z1001ZZ` Blister Strip | `4CNR3ZA001ZZ` Britestock |
| `5CNB4ZAA1ZZZ` | B3 150mg Bottle | `4CNS4Z1001ZZ` Blister Strip | `4CNR4ZA001ZZ` Britestock |
| `5CNB5ZAA1ZZZ` | B4 200mg Bottle | `4CNS5Z1001ZZ` Blister Strip | `4CNR5ZA001ZZ` Britestock |

> 25/50mg Bottle은 이미 Britestock으로 올바름(수정 불필요). Card/Pack SKU의 Blister Strip input은 정상이므로 유지.

**Britestock 코드 체계 (참조)**:
`4CNR2ZA001ZZ`=50mg, `4CNR3ZA001ZZ`=100mg, `4CNR4ZA001ZZ`=150mg, `4CNR5ZA001ZZ`=200mg

---

## 변경 3 — Bottle FP 대체경로(route) 메타 추가  ★핵심

**배경**: Bottle SKU(`5CNB*`)는 두 제조경로를 가지며 **OR(택1) 관계**(AND 아님):
- **ROUTE_DIRECT**: Tablet(DP `3CNY*`) → Bottle
- **ROUTE_VIA_BRITESTOCK**: Tablet → Britestock(SP `4CNR*`) → Bottle

input에 Tablet+Britestock이 함께 있으면 둘 다 투입이 아니라 **한 경로로 제조**됨.

**신규 컬럼** (`bom_tree`):
- `input_routes` TEXT — 형식: `코드:ROUTE_DIRECT|코드:ROUTE_VIA_BRITESTOCK`
- `route_note` TEXT — 경로 설명

**채워진 행**: 2경로 Bottle 6행 + 단일경로 Bottle 3행

예시:
```
5CNB3ZAA1ZZZ:  3CNY3Z001ZZZ:ROUTE_DIRECT|4CNR3ZA001ZZ:ROUTE_VIA_BRITESTOCK
5CNB2ZAE3ZZZ:  3CNY2Z007ZZZ:ROUTE_DIRECT   (단일경로)
```

**도구 처리** (`bom_expected_for_nodes`, OR 해석):
- `material_to_routes`(자재→{route:[inputs]})로 로딩
- 한 route의 input이 실측되면 그 route 확정 → 다른 route는 BOM_EXPECTED로 표시 안 함
- 어느 route도 미실측이면 ROUTE_DIRECT 기준 1개만 표시(중복 방지)

> **변경 금지 원칙**: 이 OR 로직을 AND로 되돌리지 말 것. Britestock 실측 시 Tablet은 Bottle 직접 input이 아니라 **Britestock의 상류**로 추적되어야 정확함.

---

## 변경 4 — BOM 탭 전체 SQLite 적재

**배경**: 초기엔 DB 정규화 탭(DIM/FACT)만 sqlite에 있었고, 1~6번 BOM 탭은 xlsx에만 존재.

**적재된 테이블** (xlsx 탭 → sqlite 테이블, 1:1):

| sqlite 테이블 | 출처 탭 | 행수 |
| --- | --- | --- |
| `bom_tree` | 1. BOM Tree | 64 |
| `common_blend` | 2. Common Blend | 9 |
| `partner_mapping` | 3. Partner Mapping | 10 |
| `cmo_summary` | 4. CMO Summary | 7 |
| `supply_flow` | 5. Supply Flow | 11 |
| `plant_master` | 6. Plant & Storage (Section A) | 7 |
| `storage_location` | 6. Plant & Storage (Section B) | 47 |

> 6번 탭은 Section A(플랜트)/B(저장위치)를 **별도 테이블**로 분리. 개행·빈값(`-`) 정리, 영문 컬럼명 정규화.

---


## 변경 5 — BOM tree.md 표에 Input Routes 컬럼 추가

**배경**: 변경 3(route 메타)이 sqlite/xlsx엔 컬럼으로 들어갔으나, BOM tree.md는 상단 노트로만 설명되어 표만 보면 OR 경로를 알기 어려웠음.

**수정**: `Cenobamate_BOM_Tree_v1.md`의 BOM Tree 표(§1)에 맨 끝 **`Input Routes`** 컬럼 추가.
- 2경로 Bottle: `직접=<Tablet코드> 또는 Britestock경유=<Britestock코드>`
- 단일경로 Bottle: `직접=<Tablet코드>`
- 그 외 행: 빈 셀

> schema.sql은 route 작업 시 이미 재생성되어 최신(별도 수정 불필요).


## 변경 6 — Physician Sample(5CNB2ZAA1SZZ) 대체경로 추가

**배경**: `5CNB2ZAA1SZZ`(Cenobamate USA B1 Physician Samples)도 Bottle과 동일하게 2경로를 가짐. 기존엔 단일경로(Tablet 직접)로만 등록됨.

**경로**:
- ROUTE_DIRECT: `3CNY2Z001ZZZ`(US 50mg Tablet) → Sample
- ROUTE_VIA_BRITESTOCK: Tablet → `4CNR2ZA001ZZ`(US 50mg Britestock) → Sample

**수정** (`bom_tree` row, 3산출물):
- `input_material_code`: `3CNY2Z001ZZZ` → `3CNY2Z001ZZZ 4CNR2ZA001ZZ`
- `input_routes`: `3CNY2Z001ZZZ:ROUTE_DIRECT|4CNR2ZA001ZZ:ROUTE_VIA_BRITESTOCK`
- `route_note`: 2경로 안내

→ 2경로 자재 총 6종 → **7종**. 도구의 `material_to_routes`가 OR로 자동 인식.


## 변경 7 — API RSM 호환그룹(interchangeable input group) 반영

**배경**: API `2CNY001ZZZZZ`(US)의 RSM input 3종(`1CNY001ZZZZZ` US / `1CNY001NZZZZ` US_New / `1CNY002ZZZZZ` EU)은 **상호 대체 가능한 동일 등급**. 기존 note는 "택1"로만 표기됐으나, 실제로는 **택1 또는 복수 조합** 투입.

**route와의 차이**: route(Bottle)는 거치는 공정 경로가 다름. group(RSM)은 같은 역할의 호환 원료(어느 것/몇 개가 와도 동일 공정).

**신규 컬럼** (`bom_tree`):
- `input_group` TEXT — 형식: `코드,코드,코드:그룹명` (예: `1CNY001ZZZZZ,1CNY001NZZZZ,1CNY002ZZZZZ:RSM_US_INTERCHANGEABLE`)
- `input_group_mode` TEXT — `ANY_OR_COMBO`(택1 또는 조합)

**적용**: `2CNY001ZZZZZ` 1행. note도 "택1 또는 복수 조합 투입(interchangeable)"으로 정정.

**도구 처리** (`bom_expected_for_nodes`):
- `material_to_input_groups`로 로딩
- 그룹 자재 중 하나라도 실측되면 그룹 충족 → 미사용 RSM을 BOM_EXPECTED로 표시 안 함
- 하나도 미실측이면 대표 1개만 표시(호환자재 중복 방지)

**검증** (합성 3시나리오): US 1종 실측→나머지 missing 없음 / US+EU 조합→나머지 missing 없음 / 미실측→대표 1종만. 전부 PASS. route(Bottle 6종)와 공존 확인.

## bom_tree 최종 컬럼 (참조)

```
row_id, level, material_type, material_code, material_description,
batch_size_cmo_a, batch_size_cmo_b, unit, cmo_a, cmo_b,
input_material_code, input_material_description, conversion_ratio, conversion_unit,
note, sap_plant_cmo_a, sloc_cmo_a, sap_plant_cmo_b, sloc_cmo_b,
input_routes, route_note,         ← 변경 3에서 추가
input_group, input_group_mode     ← 변경 7에서 추가
```

## 향후 BOM 변경 시 체크리스트

1. **sqlite를 먼저 수정** (단일 출처)
2. xlsx 동일 반영 (해당 탭)
3. `Cenobamate_BOM_Tree_v1.md` 문서 반영
4. `schema.sql` 재생성: `SELECT sql FROM sqlite_master WHERE sql IS NOT NULL`
5. 3개 산출물 일치 검증 (행수·내용)
6. **이 문서(BOM_CHANGELOG)에 변경 추가**
7. route/legacy 등 도구 로직에 영향 시 → 합성 데이터로 회귀 검증

## 코드 자재 접두 체계 (참조)

| 접두 | tier | 예 |
| --- | --- | --- |
| `1CNY*` | RSM (현행) | YKP1941 |
| `1CNZ*` | API (레거시, RSM 미관리 시기) | Cenobamate API_US |
| `2CNY*` | API (현행) | Cenobamate API |
| `3CNY*` | DP (Tablet) | US 100mg Tablet |
| `4CNR*` | SP (Britestock) | 100mg Britestock |
| `4CNS*` | SP (Blister Strip) | 100mg Blister Strip |
| `5CNB*` | FP (Bottle) | 100mg Bottle |
| `5CNT*` | FP (Blister Card) | Blister Card |
