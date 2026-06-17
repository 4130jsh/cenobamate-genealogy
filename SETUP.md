# SETUP — GitHub 업로드 & Claude Code 연결 가이드

이 리포를 GitHub에 올리고 Claude Code로 작업하는 방법입니다.

---

## A. GitHub에 올리기

### 방법 1: 명령줄 (git 설치되어 있는 경우) — 권장

```bash
# 1) 압축 해제한 폴더로 이동
cd cenobamate-genealogy

# 2) git 초기화
git init
git add .
git commit -m "Initial commit: Cenobamate genealogy tool v4 + BOM DB"

# 3) GitHub에서 빈 리포 생성 후 (아래 B 참고), 원격 연결
git remote add origin https://github.com/<your-username>/cenobamate-genealogy.git
git branch -M main
git push -u origin main
```

### 방법 2: GitHub 웹 업로드 (git 없이)

1. github.com 로그인 → 우측 상단 `+` → **New repository**
2. 이름 `cenobamate-genealogy`, **Private** 선택(내부 데이터), **Create**
3. 생성된 페이지에서 **uploading an existing file** 클릭
4. 압축 푼 폴더의 **모든 파일·폴더를 드래그**해서 업로드 → **Commit changes**

> ⚠️ `data/`의 sqlite/xlsx는 BOM 마스터라 올려도 되지만, **실제 SAP export(EXPORT_*.xlsx)는 절대 올리지 마세요.** `.gitignore`가 막아두었지만 웹 업로드 시 수동으로도 제외하세요.

### GitHub 빈 리포 만들기 (방법 1용)
1. github.com → `+` → New repository
2. 이름 입력, Private, **README/gitignore 추가하지 않음**(이미 있음), Create
3. 표시되는 `https://github.com/.../....git` 주소를 위 `git remote add`에 사용

---

## B. Claude Code 설치 & 연결

### 1) Claude Code 설치

```bash
npm install -g @anthropic-ai/claude-code
```

(Node.js 18+ 필요. 없으면 nodejs.org에서 설치)

### 2) 리포 클론 후 Claude Code 실행

```bash
# 리포 클론
git clone https://github.com/<your-username>/cenobamate-genealogy.git
cd cenobamate-genealogy

# Claude Code 시작 (이 폴더 안에서)
claude
```

처음 실행 시 브라우저로 Anthropic 계정 인증이 진행됩니다.

### 3) 동작 확인

Claude Code가 시작되면 **`CLAUDE.md`를 자동으로 읽어** 프로젝트 맥락을 파악합니다. 첫 메시지로 이렇게 확인해 보세요:

```
이 프로젝트 구조와 genealogy_tool.py가 하는 일을 요약해줘
```

제대로 맥락을 잡으면 설정 완료입니다.

---

## C. Claude Code로 작업하는 법

`HANDOFF.md`의 "다음 작업 후보"를 참고해 자연어로 요청하면 됩니다. 예시:

```
# 테스트 추가
docs/history의 합성 검증 케이스를 tests/ 폴더에 pytest로 정식화해줘

# 기능 개선
UoM 환산 테이블(kg↔g, EA↔box)을 추가해서 분할 매칭을 정밀화해줘.
CLAUDE.md의 변경 금지 원칙은 지켜줘.

# 디버깅
실제 SAP를 돌렸더니 <증상>이 나와. genealogy_tool.py에서 원인 찾아줘
```

### 작업 팁
- **SAP export는 로컬에만** 두고 Claude Code에게 경로를 알려주면, 그 자리에서 실행·디버깅합니다(리포엔 안 올라감).
- 변경 후에는 Claude Code에게 "합성 데이터로 회귀 검증해줘"라고 하면 `CLAUDE.md`의 검증 절차를 따릅니다.
- 커밋도 맡길 수 있습니다: "변경사항 커밋하고 푸시해줘" (한국어 커밋 메시지로).

### 권장 워크플로
1. `claude` 실행 → 작업 요청
2. Claude Code가 코드 수정 + 합성 검증
3. 로컬 SAP로 실제 동작 확인 (직접 또는 Claude Code 위임)
4. 만족하면 커밋·푸시
5. 다음 작업은 `HANDOFF.md` 갱신부터 (Claude Code에게 "HANDOFF 현재 상태 업데이트해줘")

---

## D. 자주 묻는 것

**Q. data/의 BOM DB도 Claude Code가 수정하나요?**
네. 단가/관세/BOM 변경을 요청하면 sqlite·xlsx·schema를 함께 갱신합니다. 단 BOM DB는 단일 출처이므로 변경 시 신중히.

**Q. 실제 SAP를 리포에 올려도 되나요?**
권장하지 않습니다. `.gitignore`가 `EXPORT_*.xlsx`, `*MB51*`을 제외합니다. 민감 데이터는 로컬 보관.

**Q. 여러 명이 협업하나요?**
Private 리포에 collaborator를 추가하면 됩니다. 각자 클론 후 `claude` 실행. `CLAUDE.md`가 공통 맥락을 보장합니다.
