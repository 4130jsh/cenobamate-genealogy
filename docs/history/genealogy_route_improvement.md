# Bottle FP 대체경로(route) 개선 — 변경 내역

## 문제
Bottle SKU(`5CNB*`)의 input에 Tablet과 Britestock이 함께 매핑되어,
**두 자재가 모두 FP에 투입(AND)**되는 것처럼 인식됨.
실제로는 **두 대체경로(OR)**:
- ROUTE_DIRECT: Tablet(DP) → Bottle
- ROUTE_VIA_BRITESTOCK: Tablet → Britestock(SP) → Bottle

## 해결

### 1) BOM DB에 route 메타 추가
`bom_tree`에 2개 컬럼 추가:
- `input_routes`: `코드:ROUTE_DIRECT|코드:ROUTE_VIA_BRITESTOCK` 형식으로 각 input의 경로 구분
- `route_note`: 경로 설명

2경로 Bottle 6종 + 단일경로 3종에 route 채움. sqlite/xlsx/schema/BOM tree.md 모두 반영.

### 2) 추적 코드 route 인식
- `BomMaster.material_to_routes`: 자재 → {route: [input codes]} 로딩
- `bom_edges`에 `route` 컬럼 추가
- `bom_expected_for_nodes`를 **OR 해석**으로 수정:
  - 다중 route 자재에서, 한 route의 input이 실측되면 그 route 확정
  - 미사용 route는 BOM_EXPECTED로 표시 안 함
  - 어느 route도 미실측이면 ROUTE_DIRECT 기준 1개만 표시(중복 방지)

## 검증 (합성 3시나리오)

| 시나리오 | 결과 |
| --- | --- |
| Britestock 실측 | ROUTE_VIA_BRITESTOCK 확정. Bottle 직접경로 Tablet은 missing 안 뜸. Tablet은 Britestock 상류로만 표시 ✓ |
| Tablet 직접 실측 | ROUTE_DIRECT 확정. Britestock missing 안 뜸 ✓ |
| 둘 다 미실측 | ROUTE_DIRECT(Tablet) 1개만 표시, 둘 다 동시 표시 안 함 ✓ |

회귀: A-3/A-2/C-2 등 기존 기능 보존 PASS.

## 동작 핵심
- Britestock이 실측되면 → "Tablet→Britestock→Bottle" 경로로 해석.
  이때 Tablet은 Bottle의 직접 input이 아니라 **Britestock의 상류**로 추적됨(정확한 계보).
- 두 경로가 동시에 "FP에 투입"으로 잡히던 문제 해소.

## 하위호환
- 컬럼 추가만(`input_routes`, `route_note`, bom_edges의 `route`). 기존 스키마/출력 유지.
- route 정보가 없는 자재는 ROUTE_DEFAULT로 기존과 동일 동작.
