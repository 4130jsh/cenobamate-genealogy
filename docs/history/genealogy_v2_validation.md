# Genealogy Tracer v2 — 개선 구현 & 검증 결과

> 설계문서(`genealogy_improvement_design_v1`)의 A·B·C 전 항목을 구현하고 합성 데이터로 단위검증 완료.
> 파일: `cenobamate_genealogy_tool_v2.py` (1,018줄, 단일 파일, 바로 실행 가능)

## 구현된 개선 (13항목)

| ID | 개선 | 검증 케이스 | 결과 |
| --- | --- | --- | --- |
| A-1 | REF 빈키 과도결합 방지(ref 단독→LOW, PO/item 없으면 REF엣지 억제) | 빈 ref 행(D6) | **OK** — DOC_TRANSFER만 생성, false REF엣지 0 |
| A-2 | 1 neg→N pos 분할매칭(alloc_qty) | API300 100→60+40 | **OK** — alloc [60,40] 정확 |
| A-3 | 생산 다중output 페어링(item+tier+수량 점수) | 1문서 2 Tablet+2 API | **OK** — API201→TAB201, API202→TAB202 |
| A-4 | UoM 동일성(분할금지·score 감점·usage uom 분리) | KG/TAB 혼재 | **OK** — UoM 불일치 시 분할 차단 |
| A-5 | movement 분류 테이블화(541/521/531/311 등) | 311 transfer | **OK** — 확장 movement 인식 |
| B-1 | normalize_sap 벡터화(유니크 plant·sloc만 계산) | 7,000행 | **OK** — 7.3초, tier/cmo 정상 |
| B-2 | node/edge dict 인덱싱 | node_index | **OK** |
| C-1 | 사이클 가드+meta.cycles 로깅 | CYC 왕복 | **OK** — cycle 1건 포착·차단 |
| C-2 | 날짜 인과성(date_violation, --strict-dates) | APIDV 역전 | **OK** — 감지 1건, strict 시 제거 |
| C-3 | batch 다중 material candidate 명시 | meta.candidates | **OK** |
| C-4 | 분할 후 미배분 수량 잔차 리포트 | unmatched_quantity | **OK** — 잔차 시트 생성 |
| C-5 | 단일 export 한계 자동 주석 | scope_note | **OK** |
| - | 실제 BOM DB v1 연동(legacy 3건·Bottle=Tablet+Britestock) | DB v1 | **OK** |

## 신규 출력 컬럼/파일 (하위호환 — 기존 스키마에 추가만)
- **엣지 컬럼 추가**: `alloc_qty`(배분수량), `uom_match`, `date_violation`, `cycle_flag`, `from_posting_date`/`to_posting_date`, `confidence`(HIGH/MEDIUM/LOW)
- **신규 리포트**: `unmatched_quantity_residual.csv`(C-4), XLSX에 `Unmatched_Qty` 시트
- **meta.json 추가**: `cycles[]`, `cycle_count`, `date_violations`, `scope_note`

## 신규 CLI 플래그
| 플래그 | 기본 | 효과 |
| --- | --- | --- |
| `--no-split-matching` | off(분할 on) | 1:1 매칭만(기존 동작) |
| `--strict-dates` | off | 날짜 역전 엣지 제외 |
| `--include-reversals` | off | 102/542 등 역분개 포함(기존 유지) |
| `--exclude-movements` | 921,925 | 제외 movement(기존 유지) |

## 실행 예시
```bash
python cenobamate_genealogy_tool_v2.py \
  --sap EXPORT_20260617_141501.xlsx \
  --bom-db Cenobamate_BOM_DB_v1.sqlite \
  --batch 2096696 --material 5CNB5ZAA1ZZZ \
  --direction upstream --out genealogy_out --export-xlsx
```

## 남은 권장사항 (후속, D영역)
- 엣지 빌드의 `iterrows` → itertuples/벡터화로 추가 성능(대량 export 시).
- 일괄 추적(배치 리스트·전 FP 자동) 모드, HTML genealogy 트리 시각화.
- UoM 환산 테이블(kg↔g 등) 도입 시 분할 매칭 정밀도 향상.
