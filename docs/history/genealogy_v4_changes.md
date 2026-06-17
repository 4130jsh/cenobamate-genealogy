# Genealogy Tracer v4 — 버그 수정 (사용자 실데이터 검증 반영)

> v3 실행 검증 중 발견된 2건을 수정. 파일: `cenobamate_genealogy_tool_v4.py`

## 검증 결과 요약 (사용자 실데이터)
1~5번(tier 분류·CMO 분류·생산 링크·수량 정합·이상 엣지) **정상 확인**.
6번·7번에서 이슈 발견 → 수정.

## 수정 1 — 잔차 중복 기록 버그 (6번)

**증상**: 정상적으로 엣지에 매핑된 자재인데도 `unmatched_quantity_residual.csv`에
**원래 출고 수량과 거의 같은 값으로 잔차(neg_residual)** 가 중복 기록됨.

**원인**: `pair_negative_positive`의 분할매칭에서, **UoM 불일치/분할 off 경로**가
전량(`alloc=전량`)으로 엣지를 만들고 `break`하면서 **`need`를 차감하지 않음**.
→ 매칭이 끝났는데도 `need`가 원래 수량 그대로 남아 전량이 잔차로 오인됨.

**수정**: 전량/분할 경로 **모두** `need`·`pos_remaining`·`allocated`를 일관되게 차감.
잔차는 **실제 배분 후 남은 수량만** 기록.

| 케이스 | 수정 전 | 수정 후 |
| --- | --- | --- |
| UoM 불일치 전량매칭(KG→EA, 100) | 잔차 100 (오류) | **잔차 0** (엣지 전량 배분) |
| 정상 분할(100→60+40) | 잔차 0 | 잔차 0 (유지) |
| 진짜 부분매칭(100→70만 입고) | 잔차 30 | **잔차 30** (정상 — 진짜 추적 미완) |

> 핵심: 이제 잔차는 **진짜로 추적이 끊긴 수량만** 남습니다. 정상 매핑분은 빠집니다.

## 수정 2 — 일괄 추적 시 BOM_EXPECTED 미생성 (7번)

**증상**: `trace_bom_expected_missing.csv`가 단건(`--batch`)에서만 생성되고
빌드 전용/일괄(`--trace-scope`) 실행 시 안 만들어짐.

**원인**: `trace_many`(일괄)가 각 시드의 BOM_EXPECTED를 수집하지 않고 버림.

**수정**:
- `trace_many`가 시드별 BOM_EXPECTED를 통합 수집 → **`batch_trace_bom_expected.csv`** 신규 생성(각 행에 `trace_seed` 컬럼).
- 요약에 `total_bom_expected` 추가.

| 실행 방식 | BOM_EXPECTED 출력 파일 |
| --- | --- |
| 단건 `--batch` | `trace_bom_expected_missing.csv` (기존) |
| 일괄 `--trace-scope` / `--batch-list` | `batch_trace_bom_expected.csv` (신규) |

## 실행 팁 (검증 시)
- `--trace-scope all-fp`는 **FP 노드가 있을 때만** 시드가 잡힘. FP가 없으면 `all-leaf`(소비되지 않는 최종 노드) 사용.
- 잔차 점검: `unmatched_quantity_residual.csv`의 `residual_kind`가
  - `neg_unmatched` = 매칭 후보 자체가 없음(진짜 끊김)
  - `neg_residual` = 일부만 매칭되고 남은 실제 잔량
  - `pos_residual` = 입고 중 출고와 안 묶인 잔량

## 회귀검증 (v4)
- 잔차수정: UoM불일치 0 / 부분매칭 30 ✓
- A-3 다중output ✓ / A-2 분할(60+40) ✓ / C-2 날짜위반 ✓
- D-1 성능 ~1.4s / D-2 일괄 ✓ / D-3 HTML ✓
- → **전체 PASS**

## 하위호환
- 출력 컬럼·파일 **추가만**. 기존 단건 동작·스키마 불변.
