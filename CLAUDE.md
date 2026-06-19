# CLAUDE.md

이 파일은 Claude Code가 이 리포지토리에서 작업할 때 자동으로 읽는 프로젝트 컨텍스트입니다.

## 프로젝트 개요

SKBP의 **Cenobamate(XCOPRI) API CMO 공급망** batch genealogy & traceability 도구입니다.
SAP MB51 자재이동 export와 BOM 데이터베이스를 결합해 배치 단위 계보(어느 RSM→API→DP→SP→FP로 흘렀는지)를 추적합니다.

- 응답 언어: **한국어**
- 통화 단위: USD
- 핵심 산출물: `src/genealogy_tool.py` (단일 파일, 외부 의존성 최소)

## 디렉토리 구조

```
.
├── CLAUDE.md                  # 이 파일 (프로젝트 컨텍스트)
├── README.md                  # 사용자용 개요·실행법
├── HANDOFF.md                 # 작업 인수인계 문서 (현재 상태·다음 작업)
├── requirements.txt           # 엔진 의존성 (pandas/numpy/openpyxl)
├── requirements-frontend.txt  # frontend 전용 의존성 (streamlit)
├── src/
│   └── genealogy_tool.py      # 메인 추적 도구 (구 v4, 단일 파일)
├── frontend/                  # [Phase 3] Streamlit 조회 앱 (warehouse 읽기 전용)
│   ├── app.py                 #   UI (상류 FP→RSM·BOM_EXPECTED 점선, 하류 RSM→FP, 검색/필터)
│   └── genealogy_db.py        #   DB 로딩·서브그래프·끊긴상류·Graphviz DOT (순수 함수, 테스트됨)
├── data/
│   ├── Cenobamate_BOM_DB_v1.sqlite   # BOM/단가/관세 DB (단일 출처)
│   ├── Cenobamate_BOM_DB_v1.xlsx     # 동일 내용 Excel (사람 편집용)
│   ├── Cenobamate_BOM_DB_v1_schema.sql
│   └── Cenobamate_BOM_Tree_v1.md     # BOM 트리 문서
├── docs/
│   ├── DB_README.md           # DB 구조 상세
│   └── history/               # 설계·검증 이력 (v1~v4)
└── examples/
    └── run_examples.sh        # 실행 예시 모음
```

## 핵심 설계 (수정 시 반드시 유지)

genealogy 그래프의 **노드 = (material, batch)** 쌍입니다. 같은 batch 텍스트가 여러 material에 나타나도 false join이 안 되게 하는 핵심 불변식입니다.

엣지(실제 계보 링크)는 3가지 규칙으로만 생성됩니다:
- **PROD**: 같은 material document 내 `101`(산출) + `543/541`(소비)
- **REF_PO_ITEM**: `Reference + Purchase order + Item`이 같은 음수→양수 이동
- **DOC_TRANSFER**: 같은 material document 내 음수→양수 이동

규칙·movement 분류는 `MOVEMENT_CLASS` 딕셔너리(파일 상단)에 테이블화돼 있습니다.

다음은 **변경 금지** 원칙입니다:
- 노드 정의((material,batch))를 바꾸지 말 것
- `BOM_EXPECTED`(실측 없는 BOM상 기대 상류)는 실제 엣지와 **분리**해서 표기. 가짜 배치를 만들지 말 것
- legacy `1CNZ*` API 코드는 현행 `2CNY*`로 **표시 매핑**만 하고, 없는 RSM 배치를 지어내지 말 것
- 출력 스키마는 **컬럼 추가만** (기존 CSV/XLSX 소비처가 깨지지 않도록)
- 신규 동작은 CLI 플래그로 토글, 기본값은 안전 우선

## 데이터 흐름

```
SAP MB51 export(.xlsx) ─┐
                        ├─> genealogy_tool.py ─> 엣지/노드/추적/BOM_EXPECTED/시각화
BOM DB(.sqlite) ────────┘
```

DB(`data/*.sqlite`)는 **데이터 단일 출처**입니다. BOM/단가/관세를 바꾸려면 sqlite(또는 xlsx)를 수정합니다. 스키마는 `data/*_schema.sql` 참고.

## 자주 쓰는 명령

```bash
# 빌드만 (데이터 로딩·엣지 생성 확인)
python src/genealogy_tool.py --sap <SAP.xlsx> --bom-db data/Cenobamate_BOM_DB_v1.sqlite --out out

# 단건 추적 + HTML
python src/genealogy_tool.py --sap <SAP.xlsx> --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --batch <배치> --direction upstream --html --out out

# 전 완제품 일괄 추적
python src/genealogy_tool.py --sap <SAP.xlsx> --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --trace-scope all-fp --direction upstream --html --export-xlsx --out out

# [Phase 2] 수시 적재: 새 MB51 export 를 누적 store 에 idempotent 누적 (자연키 dedup)
python src/genealogy_tool.py --sap <NEW_MB51.xlsx> --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --store warehouse.sqlite --ingest

# [Phase 2] 누적분 전체로 빌드 + 결과 DB화 (frontend 가 읽을 warehouse)
python src/genealogy_tool.py --from-store --store warehouse.sqlite \
  --bom-db data/Cenobamate_BOM_DB_v1.sqlite --out out --write-db warehouse.sqlite --db-replace

# [Phase 2] 적재+재빌드+결과DB화 한 명령 (새 파일 폴더에 넣고 실행; 중복 자동 무시)
#   주의: data/ 에 파일만 넣는다고 적재되지 않음 — 반드시 --ingest 필요
python src/genealogy_tool.py --ingest --from-store --sap "data/sap/EXPORT_*.xlsx" \
  --store data/warehouse.sqlite --bom-db data/Cenobamate_BOM_DB_v1.sqlite \
  --out out/store --write-db data/warehouse.sqlite --db-replace
# (Windows 헬퍼: scripts/refresh.ps1)
```

데이터 제품 로드맵: ①수시 적재(`--ingest`, raw_sap_rows 누적) → ②엔진 빌드(`--from-store`) →
③결과 DB화(`--write-db`, gen_*·build_runs·v_latest_*) → ④Streamlit frontend(`frontend/app.py`).
warehouse sqlite 하나가 raw 누적·결과·빌드이력을 모두 보유(향후 Postgres 이전 가능 스키마).

```bash
# [Phase 3] frontend 실행 (warehouse 의 v_latest_* 를 읽어 FP→RSM 상류 그래프 조회)
pip install -r requirements-frontend.txt
streamlit run frontend/app.py   # 사이드바에서 warehouse 경로 지정 (기본 data/warehouse.sqlite)
```

주요 플래그: `--direction upstream|downstream|both`, `--max-depth N`, `--strict-dates`,
`--include-reversals`, `--no-split-matching`, `--batch-list FILE`, `--trace-scope all-fp|all-leaf|all`, `--html`, `--export-xlsx`,
`--pairing-mode bom-aware|legacy`(다중 output 생산 페어링 점수식; 기본 bom-aware=BOM 토폴로지 우선, legacy=구 item-순서 하위호환),
`--store PATH`·`--ingest`·`--from-store`(Phase 2 누적 store), `--write-db PATH`·`--db-replace`(결과 DB화),
`--legacy-transfer-pairing`(구 transfer 페어링 복원; 기본은 같은 tier 다른 strength 가짜 전환 차단),
`--no-net-reversals`(reversal 넷팅 끄기; 기본은 취소된 원본 문서를 엣지에서 무효화)

## 검증 방법 (코드 수정 후 반드시)

실제 SAP export는 리포에 없습니다(민감 데이터). 코드 수정 시:
1. 구문 점검: `python -c "import ast; ast.parse(open('src/genealogy_tool.py').read())"`
2. BOM DB 로딩 검증: DB로 `load_bom_master`가 정상 동작하는지
3. 스모크/회귀 테스트: `python tests/test_smoke.py` (합성 SAP fixture `tests/synth_sap.py`로
   엣지 3규칙·날짜위반·strict-dates·tier분류·상류추적·BOM_EXPECTED분리·다중output페어링·
   결과DB화·store적재idempotency 검증)
4. frontend 데이터계층: `python tests/test_frontend.py` (warehouse 로딩·FP→RSM 상류 서브그래프·DOT 생성)
5. 회귀: tier 분류·생산 페어링·분할매칭·잔차·날짜위반이 유지되는지

## 알려진 제약

- 단일 기간 export에서는 상류 이력이 끊겨 `BOM_EXPECTED`가 많이 뜨는 게 **정상**(데이터 범위 한계).
- UoM(kg/EA 등) 환산 테이블은 없음. 현재는 동일 UoM만 분할 매칭.
- 엣지 빌드는 v4에서 dict 기반으로 최적화됨(7000행 ~1.5초).

## 코드 스타일

- 단일 파일 유지(배포 편의). 외부 의존성은 pandas/numpy/openpyxl만.
- 함수/변수명은 영문, 주석·문서는 한국어 허용.
- 응답·커밋 메시지·PR 설명은 한국어로.
