# Cenobamate Batch Genealogy Tracer — 개선안 설계문서 (v1)

> 대상: `cenobamate_genealogy_tool.py` (첨부 코드)
> 범위: **A. 정확도 버그 · B. 성능 · C. 추적 견고성** (D. 운영편의는 후속)
> 원칙: 기존 설계(노드=material+batch, 3종 엣지, BOM_EXPECTED 분리, legacy 매핑)는 유지. 실데이터(BOM DB v1 + SAP MB51 스키마) 검증 결과 반영.

---

## 0. 검증으로 확인된 데이터 사실 (개선 근거)

| 사실 | 수치/내용 | 개선 함의 |
| --- | --- | --- |
| Batch null | 64.8% | genealogy 노드(material+batch)는 전체 ~35%만 형성. node='' 행은 엣지에서 자연 제외 — **정상이나 누락 리포팅 필요** |
| Material null | 62.5% | SAP Material 코드 결측 多 → `classify_tier`가 desc/sloc fallback에 크게 의존 |
| Reference null / PO null | 40.6% / 18.8% | REF_PO_ITEM 그룹키에 **빈 값이 섞이면 과도결합(false join)** 위험 |
| 수량 단위 | Unit of Entry(EA 등) 혼재 | 1 neg→N pos 분할 매칭·집계 시 **UoM 동일성 확인 필요** |
| tier 분류 | BOM 전 행 100% 정합(불일치 0) | 핵심 로직 신뢰 → 주변 견고성에 집중 |
| BOM input 파싱 | 불일치 0 | `split_material_codes` 정규식 신뢰 |

---

## A. 정확도 버그 수정

### A-1. REF/DOC 그룹키의 빈 값 과도결합 방지 (높음)
**문제**: `build_reference_edges`는 `[source_file, reference, purchase_order, po_item]`로 그룹핑.
Reference 40.6% / PO 18.8%가 null → **빈 키끼리 한 그룹으로 뭉쳐** 서로 무관한 neg/pos가 매칭될 수 있음.
`build_document_transfer_edges`도 material_doc 빈 값에서 동일 위험.

**해결**:
- 그룹 형성 전 **키 필수 구성요소가 모두 빈 그룹은 제외**.
- REF_PO_ITEM: `reference`가 빈 행은 이 규칙에서 제외(이미 reference!='' 필터 있음 ✓) — 추가로 `purchase_order`와 `po_item`이 **둘 다 빈 경우** reference 단독 그룹은 신뢰도 LOW로 강등.
- DOC_TRANSFER: `material_doc`은 PK라 항상 존재하나, **단일 문서 내 동일 자재 단순 이동(분할)** 과 **진짜 전환**을 구분(아래 A-3와 연계).

```text
function build_reference_edges(rows):
    eligible = rows[node!='' and reference!='' and mt not in ignored and mt not in (101,543)]
    for (file, ref, po, item), g in groupby:
        key_strength = count_nonblank(po, item)          # 0,1,2
        confidence = HIGH if key_strength>=1 else LOW     # ref 단독이면 LOW
        pair_negative_positive(g, kind=REF_PO_ITEM, base_confidence=confidence)
```

### A-2. 1 neg → N pos 분할 매칭 (높음)
**문제**: `pair_negative_positive`는 neg 1건당 best pos **1건만** 사용(used_pos.add). 부분 소비/분할 입고(한 출고가 여러 입고로 분할)에서 **엣지 누락**.

**해결**: 잔여 수량(remaining qty) 기반 **1:N 그리디 분할**.
- neg의 |qty|를 pos들에 수량 근접 순으로 소진하며 다중 엣지 생성.
- 각 분할 엣지에 `alloc_qty`(배분 수량) 기록 → 수량 추적 정확.
- UoM 다르면 분할 금지(A-4).

```text
function pair_negative_positive_split(g, group_cols, kind):
    neg = g[qty<0] sorted by (posting_date, item)
    pos = g[qty>0] sorted by (posting_date, item)
    pos_remaining = {idx: |qty|}
    for nrow in neg:
        need = |nrow.qty|
        for prow in candidates(nrow, pos) sorted by score:        # A-3 점수
            if pos_remaining[prow] <= 0: continue
            if not same_uom(nrow, prow): continue                  # A-4
            alloc = min(need, pos_remaining[prow])
            emit_edge(nrow, prow, alloc_qty=alloc, kind)
            need -= alloc; pos_remaining[prow] -= alloc
            if need <= eps: break
```
> 옵션 플래그 `--split-matching`(기본 on). off면 기존 1:1 동작(하위호환).

### A-3. 생산 엣지 다중 output 페어링 정확화 (높음)
**문제**: `build_production_edges`의 다중 output 처리 = "543 직전의 101에 귀속"(item 순서만).
SAP 문서에서 **item 순서가 공정 순서와 다를 수 있어** 잘못된 output에 component 연결 가능.

**해결**: item 순서 + **수량/tier 정합성 점수**로 보강.
- 후보 output 중 (a) tier가 input보다 상위이고 (b) item 거리 최소 (c) 수량 스케일 합리적인 것 선택.
- 단일 output 문서는 현행 유지(명확).

```text
function choose_output_for_input(input_r, outputs):
    cands = [o for o in outputs if tier_ok_for_prod(input_r.tier, o.tier, ...)]
    if empty(cands): return None
    return argmin(cands, key=lambda o: (abs(o.item-input_r.item), tier_gap, qty_implausibility))
```

### A-4. UoM 동일성 검증 (중간)
**문제**: 수량 매칭/집계(`transfer_score`, usage sum)가 **UoM 무시**. kg↔EA 혼재 시 분할·합산 오류.

**해결**:
- 분할 매칭(A-2)·transfer 후보에서 **from.uom == to.uom** 아니면 감점 또는 제외.
- `trace_node_usage` 집계는 **(material, batch, uom)** 단위로 — UoM 다르면 별 행.

### A-5. Movement type 커버리지 확대 (중간)
**문제**: 생산은 101/543만. 실제 MB51엔 **541**(subcontract component 출고), **521**(생산 without order), **531**(by-product 입고), **311/313/315**(transfer posting), **101 reversal 102** 등.

**해결**: 설정 가능한 movement 분류 테이블 도입.
```text
MOVEMENT_CLASS = {
  "production_out": {101, 521, 531},
  "production_in_consume": {543, 541},
  "transfer": {311,313,315,301,303,305},
  "reversal": {102,542,544,532,922,926},   # include-reversals 시에만 사용
  "exclude": {921,925},                      # 시장출고/판매
}
```
- 기존 하드코딩(`isin([101,543])`)을 위 테이블 참조로 교체 → 확장·튜닝 용이.

---

## B. 성능 최적화

### B-1. 행별 apply → 벡터화/사전 매핑 (높음)
**문제**: `normalize_sap`에서 `out.apply(classify_tier/classify_cmo/sloc_stage..., axis=1)` 4회.
6,967행 × Python 함수콜 = 수만 회. 다중 export 시 선형 증가.

**해결**:
- `sloc_stage`/`sloc_desc`: `(plant,sloc)` 키 → **map(merge)** 로 벡터화.
- `classify_cmo`: (plant, sloc) **유니크 조합만** 1회 계산 후 join → 행 수와 무관.
- `classify_tier`: material/desc 접두 규칙은 **np.select/str.startswith 벡터화**, sloc fallback만 잔여 행에 적용.

```text
uniq = rows[['plant','sloc']].drop_duplicates()
uniq['cmo'] = uniq.apply(classify_cmo)        # 유니크 조합만 (수십 건)
rows = rows.merge(uniq, on=['plant','sloc'])
# tier: 벡터 규칙 우선, 미해결 행만 apply
```
> 기대효과: tier/cmo 분류를 행수→유니크 조합수로 축소(수천→수십). 체감 수 배 단축.

### B-2. 엣지 빌드/트레이스 인덱싱 (중간)
**문제**: `node_summary`·`bom_expected_for_nodes`에서 반복 `df[df[col]==...]` 필터(O(N)×반복).
**해결**:
- nodes를 `node→record` **dict 인덱스**로 1회 구성.
- `trace_edges`의 to_node→edges, from_node→edges **adjacency dict** 재사용(이미 build_adjacency 있음 → trace 단계도 동일 패턴 적용).

### B-3. groupby 키 dtype 고정 (낮음)
- 그룹키 컬럼을 string으로 고정(혼합 dtype groupby 경고/속도). 이미 clean_str 처리되나 명시.

---

## C. 추적 견고성

### C-1. 사이클(cycle) 가드 & 로깅 (높음)
**문제**: code 변환(2CNY001→2CNY004)이 **동일 tier** 허용. 데이터 오류로 A→B→A 발생 시 BFS는 visited로 막지만, **엣지 단위 visited**라 노드 재방문 경로가 길게 늘어질 수 있고 사이클이 **조용히** 처리됨.

**해결**:
- BFS에 **경로(path) 기반 사이클 감지** 추가 → 사이클 엣지를 `cycle_flag=True`로 표시하고 `meta.cycles[]`에 기록(차단하되 가시화).
- `tier_ok_for_prod`/transfer에서 **A↔A material 왕복** 방지 규칙 보강.

```text
function run_bfs(adj, get_next):
    q = deque((seed, depth=0, path={seed}))
    while q:
        node, depth, path = q.popleft()
        for ei in adj[node]:
            nxt = get_next(edge[ei])
            if nxt in path:                      # 사이클
                meta.cycles.append((node, nxt, ei)); continue
            ... enqueue (nxt, depth+1, path|{nxt})
```

### C-2. 날짜 인과성 검증 (높음)
**문제**: 상류(from) posting_date가 하류(to)보다 **미래**인 비논리 엣지 미검출.
**해결**:
- 엣지 생성 시 `date_violation = from.posting_date > to.posting_date` 플래그.
- 기본은 **경고 표시(유지)**, `--strict-dates` 옵션 시 해당 엣지 **제외**.
- 동일 문서(PROD)는 같은 날짜라 영향 없음. REF/DOC 전환에서 주로 점검.

```text
edge.date_violation = (from.posting_date and to.posting_date
                       and from.posting_date > to.posting_date)
if strict_dates and edge.date_violation: drop(edge)
else: keep with flag
```

### C-3. batch→다중 material candidate 명시 강화 (중간)
**현황**: `resolve_batch`가 다중 노드 시 경고만. 이미 (material,batch) 노드로 false join은 방지됨 ✓.
**개선**:
- trace 결과에 **resolved candidates 표**(material/tier/cmo/기간)를 항상 출력.
- `--material` 미지정 다중 후보 시, 각 후보를 **별도 트레이스 ID**로 분리 표기(혼선 방지).

### C-4. 분할 매칭 수량 잔차 리포트 (중간)
**문제**: A-2 분할 후 **미배분 잔여 수량**(소진 안 된 neg, 또는 남은 pos)이 traceability 공백.
**해결**: `unmatched_quantity` 리포트 시트 추가 — neg/pos 잔차를 material/batch/uom별로 집계 → "추적 미완" 가시화.

### C-5. 단일 export 한계 명시 (낮음)
- 입력이 단일 MB51이면 **상류 이력 부재(BOM_EXPECTED 다수)는 정상** — 리포트 헤더에 "scope=single export, 상류 누락은 범위 한계" 자동 주석.

---

## 적용 우선순위 & 검증 계획

| 순위 | 항목 | 영향 | 검증 방법 |
| --- | --- | --- | --- |
| 1 | A-1 빈키 과도결합 | false edge 제거 | 빈 ref/po 그룹에서 엣지 미생성 단위테스트 |
| 2 | A-2 분할매칭 + C-4 잔차 | 엣지 누락↓·수량정합 | 합성 1neg-2pos 케이스 수량합 일치 확인 |
| 3 | A-3 생산페어링 | 잘못된 PROD 링크↓ | 다중 output 합성문서로 페어 정확도 |
| 4 | B-1 벡터화 | 속도 | 6,967행 처리시간 before/after |
| 5 | C-1/C-2 사이클·날짜 | 비논리 엣지 가시화 | 합성 사이클·역전날짜 케이스 |
| 6 | A-4/A-5 UoM·movement | 일반화 | UoM 혼재·541/521 포함 케이스 |

**하위호환**: 모든 신규 동작은 플래그로 토글(`--split-matching`, `--strict-dates`, `--include-reversals` 확장). 기본값은 **안전 우선**(과도결합 방지 on, 분할 on, strict-dates off=경고만).

**비변경 원칙**: 노드 정의, BOM_EXPECTED 분리, legacy 매핑, CSV/XLSX 출력 스키마는 **컬럼 추가만**(alloc_qty, cycle_flag, date_violation, confidence 등) — 기존 소비처 깨지지 않음.

---

*다음 단계: 본 설계 확정 후, 개선된 단일 파일 코드로 재작성 + 합성 데이터 단위검증 결과 동봉.*
