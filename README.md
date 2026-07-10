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

### Windows 원클릭 (적재 + 조회화면 한 번에)

`data\sap\` 에 MB51 export(`EXPORT_*.xlsx`)를 넣고 **`start_genealogy.bat` 를 더블클릭**하면
데이터 적재 → 재빌드 → Streamlit 조회화면 실행이 한 번에 됩니다.
(신규 파일이 없으면 기존 warehouse 로 조회화면만 엽니다.)

- **Python 은 배치가 자동으로 찾습니다** — `py` 런처 / PATH / Anaconda·Miniconda / python.org 순.
  **conda 설치는 필수가 아닙니다.** 아무 Python 도 없으면 창이 꺼지지 않고 설치 안내를 띄웁니다.
  필요한 패키지(streamlit 등)도 없으면 자동 설치합니다.
- **첫 실행 팁**: Streamlit 을 처음 켜면 터미널이 `Email:` 에서 잠깐 멈춥니다 → 그냥 **Enter**.
  브라우저가 자동으로 안 열리면 **http://localhost:8501** 로 접속. 종료는 창에서 **Ctrl+C**.

### 팀 공유 배포 (SharePoint/Teams 에 warehouse 두고 각자 조회)

한 명(**빌더**)만 SAP 를 적재·재빌드하고, 결과 `warehouse.sqlite` 를 공유폴더에 두면
나머지(**뷰어**)는 각자 로컬에서 조회만 합니다. 프런트엔드는 `warehouse.sqlite` **하나만** 읽습니다
(SAP·BOM DB 불필요).

1. **빌더 PC**: `start_genealogy.bat` 로 재빌드 후, 생성된 `data\warehouse.sqlite` 를
   SharePoint/Teams 문서 라이브러리에 올림(또는 그 동기화 폴더를 `--write-db` 대상으로 지정).
2. **뷰어 PC** (conda 불필요, Python 만 있으면 됨):
   - 이 리포를 클론 (패키지는 `view_genealogy.bat` 이 없으면 자동 설치)
   - 공유 라이브러리를 OneDrive 로 **동기화**(또는 "바로가기 추가") → 로컬 경로 생김
   - 리포 루트에 `warehouse_path.txt` 파일을 만들고 그 **로컬 경로 한 줄**만 적음
     (예: `C:\Users\<사번>\OneDrive - skbpcorp\CPM team - Batch Genealogy\warehouse.sqlite`).
     또는 환경변수 `GENEALOGY_WAREHOUSE` 지정, 또는 실행 후 사이드바에 직접 입력해도 됨.
   - **`view_genealogy.bat` 더블클릭** → 조회 전용 실행 (적재/재빌드 안 함)
3. 빌더가 warehouse 를 갱신하면, 뷰어는 사이드바 **🔄 최신 데이터 다시 읽기** 로 반영.

> 공유폴더의 SQLite 를 직접 열면 잠금·동기화 충돌이 날 수 있어, 기본으로 **로컬 복사본을 읽는
> 안전모드**가 켜져 있습니다(읽기 전용, 원본에 `-wal`/lock 파일을 만들지 않음). 사이드바에서 끌 수 있습니다.

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
