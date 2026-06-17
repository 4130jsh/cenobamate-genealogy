# Cenobamate Batch Genealogy Tool

SKBP Cenobamate(XCOPRI) API CMO 공급망의 **batch genealogy & traceability** 도구입니다.
SAP MB51 자재이동 export와 BOM 데이터베이스를 결합해, 배치 단위로 RSM→API→DP→SP→FP 계보를 추적합니다.

## 빠른 시작

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 빌드만 (데이터 로딩·엣지 생성 확인)
python src/genealogy_tool.py \
  --sap EXPORT_20260617_141501.xlsx \
  --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --out out

# 3) 특정 배치 추적 + HTML 시각화
python src/genealogy_tool.py \
  --sap EXPORT_20260617_141501.xlsx \
  --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --batch <배치값> --direction upstream --html --out out
```

`<배치값>`은 `out/normalized_sap_rows.csv`의 `batch` 컬럼에서 실제 값을 고릅니다.
**SAP export 파일은 민감 데이터라 리포에 포함되지 않습니다** — 본인 파일을 사용하세요.

## 무엇을 하나

genealogy 그래프의 노드는 `(material, batch)` 쌍이고, 엣지(실제 계보 링크)는 3규칙으로 생성됩니다:
- **PROD**: 같은 material document 내 산출(101) + 소비(543/541)
- **REF_PO_ITEM**: Reference+PO+Item이 같은 음수→양수 이동
- **DOC_TRANSFER**: 같은 material document 내 음수→양수 이동

실측이 없는 BOM상 기대 상류는 `BOM_EXPECTED`로 **분리 표기**하며, 가짜 배치를 만들지 않습니다.

## 주요 출력

| 파일 | 내용 |
| --- | --- |
| `genealogy_edges_actual.csv` | 실제 계보 엣지 |
| `normalized_sap_rows.csv` | 정규화 SAP 행(tier/cmo 분류 포함) |
| `unmatched_quantity_residual.csv` | 추적 미완(미배분) 수량 잔차 |
| `trace_bom_expected_missing.csv` | BOM상 기대되나 실측 없는 상류(단건) |
| `batch_trace_bom_expected.csv` | 동일(일괄) |
| `genealogy_trace.html` / `genealogy_batch.html` | 시각화 |
| `genealogy_output.xlsx` | 통합 워크북(`--export-xlsx`) |

## CLI 옵션

```
--sap FILE...            SAP MB51 export (여러 개·glob 가능)
--bom-db FILE            BOM SQLite DB
--batch BATCH            추적할 배치 (단건)
--material CODE          배치 중복 시 자재 한정
--direction             upstream|downstream|both (기본 upstream)
--max-depth N            추적 깊이 (기본 12)
--trace-scope           all-fp|all-leaf|all (일괄 추적 시드 자동 선택)
--batch-list FILE        배치 목록 파일(줄당 'batch' 또는 'batch,material')
--strict-dates           날짜 역전 엣지 제외
--include-reversals      102/542 등 취소 movement 포함
--no-split-matching      1:1 매칭만 (분할 끄기)
--html                   HTML 시각화 생성
--export-xlsx            통합 XLSX 출력
```

더 많은 예시는 `examples/run_examples.sh` 참고.

## 디렉토리

```
src/genealogy_tool.py    # 메인 도구 (단일 파일)
data/                    # BOM DB(sqlite/xlsx/schema) + BOM 트리 문서
docs/                    # DB 구조·설계·검증 이력
examples/                # 실행 예시
CLAUDE.md                # Claude Code 컨텍스트
HANDOFF.md               # 인수인계 문서
```

## 문서

- `CLAUDE.md` — Claude Code로 작업 시 자동 로드되는 프로젝트 컨텍스트·설계 원칙
- `HANDOFF.md` — 현재 상태·완료 작업·다음 작업 후보
- `docs/DB_README.md` — BOM/단가/관세 DB 구조 상세
- `docs/history/` — 개선 설계·검증 이력 (v1~v4)

## 라이선스 / 보안

내부 사용. SAP export 등 민감 데이터는 `.gitignore`로 커밋에서 제외됩니다.
