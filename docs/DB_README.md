# Cenobamate (XCOPRI) Global API CMO Supply-Chain — 산출물 README

> SKBP 글로벌 API CMO 공급망 전략 프로젝트의 산출물 안내서.
> 크게 **① 데이터베이스(BOM·단가·관세)** 와 **② 전략 수립 모델(Cockpit)** 로 구성됩니다.
> 통화: USD. 버전: v1 (전 파일 통일).

---

## 1. 한눈에 보기

| 파일 | 형식 | 역할 | 누가 언제 사용 |
| --- | --- | --- | --- |
| `Cenobamate_BOM_DB_v1.xlsx` | Excel | **마스터 데이터 (사람이 편집)** — BOM + 단가 + 관세 + 도입비 + 레거시 코드 | 단가·CMO·관세 변경/추가 시 |
| `Cenobamate_BOM_DB_v1.sqlite` | SQLite DB | **마스터 데이터 (쿼리·시스템 연동)** — Excel과 동일 내용 | SQL 조회·자동화·앱 연동 시 |
| `Cenobamate_BOM_DB_v1_schema.sql` | SQL DDL | **DB 설계도** — 테이블·뷰 정의 (재생성·이관용) | DB 재구축·구조 검토 시 |
| `Cenobamate_BOM_Tree_v1.md` | Markdown | **BOM 트리 문서 (읽기용)** — 사람이 읽는 BOM 설명 | BOM 구조 빠른 참조 |
| `Cenobamate_API_CMO_Strategy_Cockpit_v10.html` | HTML | **전략 수립 모델 (시뮬레이션)** — TCO·관세·시나리오 빌더 | 소싱 의사결정·시나리오 비교 |

> **핵심 관계**: DB(xlsx/sqlite) = "데이터 단일 출처(Single Source of Truth)" → Cockpit(html) = "그 데이터로 전략을 시뮬레이션하는 도구".
> xlsx와 sqlite는 **내용이 100% 동일**합니다 (편집 편의 vs 쿼리/연동 용도 차이).

---

## 2. 데이터베이스 파일 상세

### 2-1. `Cenobamate_BOM_DB_v1.xlsx` — 마스터 데이터 (Excel)
사람이 직접 편집하는 메인 데이터 파일. **17개 탭**, 3개 영역으로 구성.

**A. BOM 영역 (탭 0~6)** — 기존 BOM 트리
- `0. Cover` — 탭 안내 표지
- `1. BOM Tree` — Level별 BOM 구조 (RSM→API→DP→SP→FP)
- `2. Common Blend` — 함량별 공통 블렌드·배치 구성
- `3. Partner Mapping` — 파트너별 공급 레벨·제품코드
- `4. CMO Summary` — CMO별 역할·담당 단계·플랜트
- `5. Supply Flow` — 시장별 공급 흐름
- `6. Plant & Storage Location` — SAP 플랜트·저장위치 마스터

**B. 레거시 영역 (탭)**
- `LEGACY_Codes` — 과거 API 코드(`1CNZ*`, RSM 미관리 시기) ↔ 현행 코드(`2CNY*`) 매핑. 현재 재고 없음(이력 보존).

**C. DB 영역 (정규화 탭 8개 + README)** — "데이터베이스화"된 단가·관세
- `DIM_CMO` — **CMO 마스터** (기본키 `cmo_id`, 모든 단가/관세가 이 id로 연결)
- `FACT_RSM_Price` — RSM 물량·축별 단가 (`model_applied`는 수식 자동계산)
- `FACT_API_Price` — API CMO별 제조비·관세 요약
- `FACT_DP_Price` / `FACT_SP_Price` / `FACT_FP_Price` — DP·Semi-FP·FP 단가
- `FACT_Tariff` — **공급망 전 구간 관세 시나리오** (A~E 26행)
- `FACT_IntroCost` — **US onshoring 도입비용** (one-time)
- `README_DB` — DB 스키마·편집법 안내(파일 내장)

> 편집 시: 셀을 직접 수정. `cmo_id`·`country`·`status` 등은 **드롭다운 검증** 적용(오타 방지). RSM 모델가는 입력만 바꾸면 자동 재계산.

### 2-2. `Cenobamate_BOM_DB_v1.sqlite` — 마스터 데이터 (SQLite)
Excel과 **동일 내용**의 관계형 DB (Excel 전 탭 1:1 반영). SQL 쿼리·시스템 연동·무결성 강제용.
- **BOM 테이블 7개** (1~6번 탭): `bom_tree` · `common_blend` · `partner_mapping` · `cmo_summary` · `supply_flow` · `plant_master` · `storage_location`
- **DB 정규화 테이블 8개** (단가·관세): `dim_cmo`(마스터) + `fact_api_price`/`fact_dp_price`/`fact_sp_price`/`fact_fp_price`/`fact_introcost`(cmo_id 외래키) + `fact_rsm_price` + `fact_tariff`
- **레거시 테이블 1개**: `legacy_api_codes`
- **뷰 3개**: `v_api_tco`(API 단가+도입비 결합) · `v_dp_wide`(함량별 Avara/Patheon pivot) · `v_tariff_by_group`(시나리오별 관세)
- **무결성**: FK 참조, `status`/`includes_dp`/`axis` CHECK 제약, 인덱스
- 편집 도구: [DB Browser for SQLite](https://sqlitebrowser.org/) (무료 GUI) 권장

### 2-3. `Cenobamate_BOM_DB_v1_schema.sql` — DB 설계도
SQLite의 전체 구조(CREATE TABLE/VIEW 문)를 담은 텍스트 파일.
- 용도: DB를 처음부터 재생성, 다른 DB(PostgreSQL 등)로 이관, 구조 리뷰/공유
- 데이터는 없고 **구조만** 포함

### 2-4. `Cenobamate_BOM_Tree_v1.md` — BOM 트리 문서 (읽기용)
사람이 읽기 위한 BOM 설명 문서(Markdown). DB와 같은 내용을 서술형으로 정리.
- BOM Tree, Common Blend, Partner Mapping, CMO Summary, Supply Flow, Legacy API Codes, Plant & Storage, CMO Pricing Master 포함
- 용도: 코드 없이 BOM 구조·흐름을 빠르게 파악

---

## 3. 전략 수립 모델 파일

### `Cenobamate_API_CMO_Strategy_Cockpit_v10.html` — 전략 시뮬레이션 (최신)
브라우저에서 바로 열리는 단일 HTML 인터랙티브 모델. DB의 단가·관세를 기반으로 전략을 시뮬레이션.
- **2축 전략구조** (US API / EU API) 시각화 — 파트너별 분기 흐름
- **CMO 비교·비용** — 제조비·관세·도입비 분해
- **관세 Map** — 공급망 전 구간 관세 + 한국 FTZ 구조
- **시나리오 빌더** — 노드별 CMO 선택 → E2E supply chain map(노드 제조비·노드간 관세·도입비·E2E 총비용)
- **TCO 비교** — 5년 운영 COGS + 도입비용
- ⚠ `v10`이 최신입니다. v2~v9는 과거 버전(참고용 보존).

---

## 4. 데이터 변경·추가 방법

| 상황 | 작업 |
| --- | --- |
| **CMO 추가** | ① `DIM_CMO`에 행 추가(`cmo_id` 부여) → ② 해당 `FACT_*` 탭에 그 `cmo_id`로 단가 행 추가 |
| **단가 변경** | 해당 `FACT_*` 셀 수정 + `effective`(분기)·`source` 갱신 |
| **관세 변경** | `FACT_Tariff`에서 `rate_pct` 수정 → `rate_display`·근거 함께 갱신 |
| **레거시 코드 추가** | `LEGACY_Codes` 탭 / `legacy_api_codes` 테이블에 행 추가 |

> Excel ↔ SQLite는 수동으로 양쪽을 맞추거나, 한쪽을 원본으로 정해 빌드 스크립트로 재생성하는 것을 권장합니다.

---

## 5. 권장 운영 흐름

```
[Excel/SQLite DB]  ── 단일 출처(데이터 입력·검증) ──►  [Cockpit HTML]  ── 전략 시뮬레이션·의사결정
   (단가/관세/CMO/BOM)                                  (TCO·관세·시나리오 비교)
```

1. **데이터는 DB에서만 관리** (xlsx 편집 → sqlite 동기화).
2. **분석·의사결정은 Cockpit에서** (DB 값을 모델에 반영해 시나리오 비교).
3. 변경 이력은 `effective`·`source` 컬럼으로 추적, 버전 업 시 파일명 `v2`로 상향.

### 확장 경로 (필요 시)
- **현재**: Excel + SQLite (추가 인프라 0, 소규모 팀 최적)
- **다음**: SQLite를 중심으로 Cockpit이 JSON으로 직접 읽도록 연결 → "DB 수정 → 모델 자동 반영"
- **이후**: 다중 사용자·웹폼·변경이력 필요 시 Airtable/PostgreSQL 등으로 이관(schema.sql 활용)

---

*Generated for SKBP Cenobamate API CMO Supply-Chain Strategy · v1*
