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
├── requirements.txt           # Python 의존성
├── src/
│   └── genealogy_tool.py      # 메인 추적 도구 (구 v4, 단일 파일)
├── data/
│   ├── Cenobamate_BOM_DB_v1.sqlite   # BOM/단가/관세 DB (단일 출처)
│   ├── Cenobamate_BOM_DB_v1.xlsx     # 동일 내용 Excel (사람 편집용)
│   ├── Cenobamate_BOM_DB_v1_schema.sql
│   └── Cenobamate_BOM_Tree_v1.md     # BOM 트리 문서
├── docs/
│   ├── DB_README.md           # DB 구조 상세
│   ├── BOM_CHANGELOG.md       # BOM 데이터 변경 이력
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

### Bottle FP 대체경로 (route) — 중요
Bottle SKU(`5CNB*`)는 **OR 대체경로**를 가집니다(AND 아님):
- **ROUTE_DIRECT**: Tablet(DP `3CNY*`) → Bottle
- **ROUTE_VIA_BRITESTOCK**: Tablet → Britestock(SP `4CNR*`) → Bottle

DB `bom_tree.input_routes` 컬럼(`코드:ROUTE_DIRECT|코드:ROUTE_VIA_BRITESTOCK`)이 경로를 구분합니다.
`material_to_routes`(자재→{route:[inputs]})로 로딩되며, `bom_expected_for_nodes`가 이를 OR로 해석합니다:
한 route의 input이 실측되면 그 route 확정 → 다른 route는 BOM_EXPECTED로 띄우지 않음.
**이 OR 로직을 AND로 되돌리지 말 것** (두 자재가 동시에 FP에 들어가는 것처럼 처리하면 안 됨).

### API RSM 호환그룹 (interchangeable input group) — 중요
API `2CNY001ZZZZZ`(US)의 RSM input 3종(`1CNY001ZZZZZ`/`1CNY001NZZZZ`/`1CNY002ZZZZZ`)은
**상호 대체 가능한 동일 등급**이며 **택1 또는 복수 조합**으로 투입됩니다(ANY_OR_COMBO).

DB `bom_tree.input_group`(`코드,코드,코드:그룹명`) / `input_group_mode` 컬럼이 정의합니다.
`material_to_input_groups`(자재→{group:[codes]})로 로딩되며, `bom_expected_for_nodes`가 처리:
그룹 자재 중 하나라도 실측되면 그룹 충족 → 미사용 RSM을 BOM_EXPECTED로 띄우지 않음.
하나도 없으면 그룹 대표 1개만 표시.

**route와 구분**: route는 거치는 공정 경로가 다름(Tablet 직접 vs Britestock 경유). group은 같은 역할의 호환 원료(어느 것이 와도 동일 공정). 둘은 독립적으로 공존.

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
```

주요 플래그: `--direction upstream|downstream|both`, `--max-depth N`, `--strict-dates`,
`--include-reversals`, `--no-split-matching`, `--batch-list FILE`, `--trace-scope all-fp|all-leaf|all`, `--html`, `--export-xlsx`

## 검증 방법 (코드 수정 후 반드시)

실제 SAP export는 리포에 없습니다(민감 데이터). 코드 수정 시:
1. 구문 점검: `python -c "import ast; ast.parse(open('src/genealogy_tool.py').read())"`
2. BOM DB 로딩 검증: DB로 `load_bom_master`가 정상 동작하는지
3. 합성 데이터로 단위검증 (과거 `docs/history/`의 검증 케이스 참고)
4. 회귀: tier 분류·생산 페어링·분할매칭·잔차·날짜위반이 유지되는지

## 알려진 제약

- 단일 기간 export에서는 상류 이력이 끊겨 `BOM_EXPECTED`가 많이 뜨는 게 **정상**(데이터 범위 한계).
- UoM(kg/EA 등) 환산 테이블은 없음. 현재는 동일 UoM만 분할 매칭.
- 엣지 빌드는 v4에서 dict 기반으로 최적화됨(7000행 ~1.5초).

## 문서

- `CLAUDE.md` — 이 파일
- `HANDOFF.md` — 현재 상태·다음 작업
- `docs/BOM_CHANGELOG.md` — **BOM 데이터 변경 이력** (레거시 코드·Britestock 수정·route 메타). BOM 수정 시 반드시 갱신.
- `docs/DB_README.md` — DB 구조 상세
- `docs/history/` — 코드 개선·검증 이력

## 코드 스타일

- 단일 파일 유지(배포 편의). 외부 의존성은 pandas/numpy/openpyxl만.
- 함수/변수명은 영문, 주석·문서는 한국어 허용.
- 응답·커밋 메시지·PR 설명은 한국어로.
