# HANDOFF — Cenobamate Genealogy Tool

작업 인수인계 문서. 현재 상태, 완료된 작업, 다음 작업 후보를 정리합니다.

## 현재 상태 (v4 기준)

`src/genealogy_tool.py`는 SAP MB51 export + BOM DB로 batch genealogy를 추적하는 단일 파일 도구입니다.
사용자 실데이터(6,966행 SAP export)로 검증 완료. tier 분류·CMO 분류·생산 링크·수량 정합 모두 정상 확인됨.

## 완료된 작업 (이력 요약)

전체 상세는 `docs/history/` 참고. 요약:

**A. 정확도** — REF/DOC 빈키 과도결합 방지, 1:N 분할매칭(alloc_qty), 생산 다중output 페어링 점수화, UoM 검증, movement 분류 테이블화

**B. 성능** — `normalize_sap` 벡터화(유니크 plant·sloc만 계산), 엣지 빌드 dict 기반 고속화(groupby 내 boolean indexing 제거). 7000행 기준 7.3초→1.5초

**C. 견고성** — 사이클 가드+로깅, 날짜 인과성 검증(`--strict-dates`), batch 다중 material candidate 명시, 분할 잔차 리포트, 단일 export 한계 자동 주석

**D. 운영** — 일괄 추적(`--batch-list`, `--trace-scope`), HTML genealogy 시각화(SVG, 의존성 0)

**v4 버그수정** (실데이터 검증 반영):
1. 잔차 중복 기록 — UoM 불일치/전량매칭 경로에서 `need` 미차감 → 정상 매핑분이 잔차로 오인되던 문제. 전량·분할 모두 일관 차감하도록 수정.
2. 일괄 추적 시 BOM_EXPECTED 미생성 — `trace_many`가 expected를 수집·출력하도록 보완(`batch_trace_bom_expected.csv`).

## 출력 파일 레퍼런스

| 파일 | 내용 |
| --- | --- |
| `normalized_sap_rows.csv` | 정규화된 SAP 행 (material/batch/tier/cmo 분류 포함) |
| `genealogy_edges_actual.csv` | 실제 계보 엣지 (PROD/REF_PO_ITEM/DOC_TRANSFER) |
| `genealogy_nodes.csv` | 노드 요약 |
| `unlinked_or_missing_history.csv` | 상류 이력 없는 생산 배치 |
| `unmatched_quantity_residual.csv` | 미배분 수량 잔차 (neg_unmatched/neg_residual/pos_residual) |
| `trace_*.csv` | 단건 추적 결과 (--batch 시) |
| `batch_trace_*.csv` | 일괄 추적 결과 (--trace-scope/--batch-list 시) |
| `genealogy_*.html` | 시각화 (--html 시) |
| `genealogy_output.xlsx` | 통합 워크북 (--export-xlsx 시) |

## 다음 작업 후보 (우선순위 미정)

아직 미구현. 필요 시 Claude Code에 요청:

1. **엣지 빌드 추가 최적화** — `pair_negative_positive`의 후보 정렬을 더 큰 export(수만 행)에서 프로파일링 후 개선.
2. **UoM 환산 테이블** — kg↔g, EA↔box 등 단위 환산을 도입해 분할 매칭 정밀화.
3. **다중 export 병합 워크플로** — 연속 기간 MB51을 자동 병합해 상류 끊김 최소화(`--sap` glob은 이미 지원, 검증·중복제거 강화 여지).
4. **테스트 스위트** — `docs/history`의 합성 검증을 `tests/`로 정식화(pytest).
5. **CI** — GitHub Actions로 구문·합성테스트 자동화.
6. **리포트 대시보드** — HTML 시각화에 필터·검색·KPI 추가.

## 주의사항

- 실제 SAP export는 **민감 데이터**라 리포에 없음. 로컬에서만 실행.
- `data/`의 BOM DB는 단일 출처. 단가/관세/BOM 변경은 여기서.
- 코드 수정 시 `CLAUDE.md`의 "변경 금지" 원칙 준수.
- `.gitignore`로 `out/`, SAP export(`EXPORT_*.xlsx`, `*MB51*`)는 커밋에서 제외.

## 연락/맥락

- 담당: Suho Jo (SKBP, 공급망/전략)
- 관련 산출물: BOM DB는 동일 리포 `data/`, 별도 전략 시뮬레이션(Strategy Cockpit HTML)은 이 리포 범위 밖.
