# Genealogy Tracer v3 — D영역 개선 & 검증 결과

> v2(A·B·C) 위에 D영역 3개를 **엔진 → 추적 → 표현 순서**로 구현. 전 항목 검증 + A·B·C 회귀 PASS.
> 파일: `cenobamate_genealogy_tool_v3.py` (1,266줄, 단일 파일)

## 진행 순서 판단 (reasoning-based)
하위 계층부터 쌓는 의존 순서로 진행:
1. **D-1 엣지 빌드 벡터화(성능)** — 일괄 추적이 다수 배치를 반복 처리하므로 엔진 속도가 선행되어야 함.
2. **D-2 일괄 추적** — 시각화가 "무엇을 그릴지" 결정하려면 추적 결과가 먼저 있어야 함.
3. **D-3 HTML 시각화** — 1·2의 산출물을 입력받는 최종 표현 계층.

## 구현 & 검증

| ID | 개선 | 결과 |
| --- | --- | --- |
| **D-1** | 엣지 빌드 dict 기반 고속화(groupby 내 boolean-indexing 제거, itertools.groupby) | **OK** — 7000행 **7.2s → 1.5s (약 5배)**, 정확도 완전 보존 |
| **D-2** | 일괄 추적: `--batch-list`(파일) / `--trace-scope all-fp\|all-leaf\|all`. `trace_many`가 통합 엣지·인덱스·요약 산출 | **OK** — seeds 일괄 처리, `batch_trace_*` 3파일 |
| **D-3** | HTML genealogy 시각화(외부 의존성 0, SVG 트리). tier 레이어·실제엣지·BOM_EXPECTED(점선)·사이클/날짜역전(빨강)·CMO 라벨 | **OK** — 렌더 확인 |

## 프로파일링 근거 (D-1)
- 병목은 `iterrows`가 아니라 **`build_production_edges`의 groupby 내 `g[(g["mt"]...)]` boolean indexing**(17,284회)였음.
- 해결: `eligible.sort_values(...).to_dict("records")` 후 `itertools.groupby` + 순수 파이썬 필터 → pandas 호출 제거.

## 신규 CLI (D영역)
| 플래그 | 효과 |
| --- | --- |
| `--batch-list FILE` | 줄당 `batch` 또는 `batch,material` 일괄 추적 |
| `--trace-scope all-fp` | 전 FP 자동 시드 추적 |
| `--trace-scope all-leaf` | 소비되지 않는 최종 노드 자동 추적 |
| `--html` | genealogy HTML 시각화 생성 |

## 신규 출력
- `batch_trace_edges_combined.csv` — 일괄 추적 통합 엣지(seed별 trace_seed 컬럼)
- `batch_trace_index.csv` — 시드별 엣지/노드/누락/사이클 요약
- `batch_trace_summary.json` — 전체 요약
- `genealogy_trace.html` / `genealogy_batch.html` — 시각화

## 실행 예시
```bash
# 단건 + HTML
python cenobamate_genealogy_tool_v3.py --sap EXPORT.xlsx --bom-db Cenobamate_BOM_DB_v1.sqlite \
  --batch 2096696 --material 5CNB5ZAA1ZZZ --direction upstream --html --out out

# 전 FP 일괄 추적 + HTML
python cenobamate_genealogy_tool_v3.py --sap EXPORT.xlsx --bom-db Cenobamate_BOM_DB_v1.sqlite \
  --trace-scope all-fp --direction upstream --html --export-xlsx --out out

# 배치 리스트 파일
python cenobamate_genealogy_tool_v3.py --sap EXPORT.xlsx --bom-db Cenobamate_BOM_DB_v1.sqlite \
  --batch-list my_batches.txt --html --out out
```

## 회귀검증 (D 후 A·B·C 보존)
- D-1 성능 1.5~1.7s / A-3 다중output ✓ / A-2 분할 ✓ / C-2 날짜위반 감지 ✓ / D-2 일괄 ✓ / BOM v1 연동(legacy 3·Bottle=Tablet+Britestock) ✓ → **전체 PASS**

## 하위호환
- v2 대비 출력 컬럼·플래그 **추가만**. 기존 단건 추적·CSV/XLSX 스키마 불변.
- `--html`/`--batch-list`/`--trace-scope` 미지정 시 v2와 동일 동작.

*샘플 시각화: `sample_genealogy_trace.html` 동봉.*
