# anal 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `testproject`에 DART 정기보고서로 두 기준(연속 성장, 영업이익률 유지)을 판정하고 근거 제한 질의를 하는 `anal` 스킬을 만든다.

**Architecture:** 상위 `dart-analyst/scripts`의 `common.py`, `drive_search.py`를 복사하고, `dart_fetch.py`는 복사 후 "사업보고서 1건 + 올해 최신 보고서 1건"을 받아 `annual.json`을 만들도록 고친다. `analyze.py`는 `annual.json`만 읽어 두 기준을 판정한다. 판정·추출 로직은 순수 함수로 두고 unittest로 검증한다.

**Tech Stack:** Python 3.13 (`py` 명령), 표준 라이브러리(unittest 포함), `pypdf`(drive_search 전용), OpenDART API.

**Spec:** `docs/superpowers/specs/2026-10-03-anal-skill-design.md`

모든 경로는 `testproject/` 기준이다. 스크립트 폴더 `S = .claude/skills/anal/scripts`. 상위 원본 폴더 `P = ../.claude/skills/dart-analyst/scripts`.

## Global Constraints

- 실행은 `py`(3.13). `python` 명령은 동작하지 않는다.
- 외부 패키지는 `drive_search.py`의 `pypdf` 하나뿐. 나머지는 표준 라이브러리만.
- `DART_API_KEY` 값은 파일·출력·문서에 적지 않는다. `.env`는 git에서 제외한다.
- 연결재무제표 우선, 없을 때만 별도. 12월 결산만 지원.
- 판정 값은 `통과`, `탈락`, `판정 불가` (1-b만 `해당 없음` 추가). 종합은 "2개 기준 중 N개 통과".
- 영업이익률 = 영업이익 ÷ 매출 × 100, `round(x, 2)`로 비교.
- 찾지 못한 질의의 답은 정확히 "DART 정기보고서와 로컬 파일에서 찾을 수 없습니다."
- FnGuide는 쓰지 않는다.

## Review Focus

1. 가장 최근 정기보고서가 사업보고서인 시기(3~5월): 올해 보고서가 없으므로 1-b `해당 없음`, 기준 1은 1-a만으로 판정. (Task 3 `test_select_reports_annual_latest`, Task 4 `test_c1_ytd_not_applicable`)
2. 상장 3년 미만이라 사업보고서의 `bfefrmtrm_amount`가 비어 있음: 크래시 없이 1-a·기준 2 `판정 불가`. (Task 3 `test_build_annual_missing_year`, Task 4 `test_c1_missing_year`)
3. 금융업처럼 매출·영업이익 계정을 못 찾음: `None` → `판정 불가`. (Task 3 `test_build_annual_account_not_found`)
4. 반올림 후 영업이익률이 같은 해: 통과. (Task 4 `test_c2_equal_after_rounding`)
5. 적자→적자 축소→흑자 전환: 증가로 인정, 그 해 영업이익률도 숫자로 비교. (Task 4 `test_c1_loss_shrinking`, `test_c2_negative_margin`)

---

### Task 1: 작업 브랜치와 기반 파일

**Files:**
- Create: `.gitignore`, `.env`(상위 `../.env` 복사), `S/common.py`(P에서 복사), `S/drive_search.py`(P에서 복사)

**Interfaces:**
- Produces: `common.ROOT`가 `testproject`를 가리킨다. `common.{DATA, CACHE, DOMESTIC, REPRT, dart_key, die, http_get, read_json, write_json, company_dir, fmt_eok}`는 원본과 동일.

- [ ] **Step 1: 브랜치 생성** — `git switch -c anal-skill` (현재 `main`)
- [ ] **Step 2: 복사** — `cp ../.env .env`, `mkdir -p S && cp P/common.py P/drive_search.py S/`
- [ ] **Step 3: `.gitignore` 작성** — 내용 3줄: `.env`, `data/_cache/`, `__pycache__/`
- [ ] **Step 4: 확인**
  Run: `py -c "import sys; sys.path.insert(0, '.claude/skills/anal/scripts'); import common; print(common.ROOT.name)"`
  Expected: `testproject`
  Run: `git status --short` → `.env`가 목록에 없어야 한다.
- [ ] **Step 5: 커밋** — `git add .gitignore .claude/skills/anal/scripts && git commit -m "feat(anal): 공통 스크립트 복사"`

---

### Task 2: 보고서 선택 (`select_reports`)

**Files:**
- Create: `S/dart_fetch.py` (P에서 복사 후 수정), `S/test_dart_fetch.py`

**Interfaces:**
- Consumes: `periodic_reports(corp_code, count) -> list[dict]` (원본 그대로; 최신순, 각 dict에 `year:int`, `reprt_code:str`, `report`, `report_nm`, `rcept_no`, `rcept_dt`, `url`)
- Produces: `select_reports(reports: list[dict]) -> tuple[dict | None, dict | None]` → `(사업보고서, 올해 최신 보고서)`

- [ ] **Step 1: 복사** — `cp P/dart_fetch.py S/`
- [ ] **Step 2: 실패하는 테스트 작성** (`S/test_dart_fetch.py`, `unittest`, 보고서 dict는 `{"year": y, "reprt_code": c}`만 있어도 된다)
  - `test_select_reports_half_year`: 입력 최신순 `[(2026,"11012"), (2026,"11013"), (2025,"11011"), (2025,"11014")]` → `(2025,"11011")`, `(2026,"11012")`
  - `test_select_reports_annual_latest`: `[(2025,"11011"), (2025,"11014")]` → `(2025,"11011")`, `None`
  - `test_select_reports_no_annual`: `[(2026,"11013")]` → `None`, `(2026,"11013")`
- [ ] **Step 3: 실패 확인** — Run: `py -m unittest discover -s .claude/skills/anal/scripts -p "test_*.py"` → `AttributeError`/`ImportError` (select_reports 없음)
- [ ] **Step 4: 구현** — 사업보고서 = 첫 번째 `reprt_code == "11011"`. 올해 보고서 = 사업보고서 연도보다 `year`가 큰 첫 번째 비사업보고서(사업보고서가 없으면 첫 번째 비사업보고서).
- [ ] **Step 5: 통과 확인** — 같은 명령, 3 tests OK
- [ ] **Step 6: 커밋** — `git commit -m "feat(anal): 판정용 보고서 선택"`

---

### Task 3: `annual.json` 생성 (`build_annual`)과 수집 흐름 수정

**Files:**
- Modify: `S/dart_fetch.py` (`build_quarters` 삭제, `build_annual` 추가, `main` 수정, 모듈 docstring의 결과 목록 수정)
- Test: `S/test_dart_fetch.py`

**Interfaces:**
- Consumes: `select_reports`, 원본의 `pick(fin, ids, names)`, `amount(v)`, `REV_IDS/REV_NMS/OI_IDS/OI_NMS`, `fetch_fin`, `fetch_doc`
- Produces: `build_annual(annual_fin: dict | None, ytd_fin: dict | None) -> dict` — `annual.json`의 형식이자 Task 4의 입력:

```json
{
  "재무제표": "연결",
  "연간": [{"연도": 2023, "매출액": 0, "영업이익": 0}, {"연도": 2024, ...}, {"연도": 2025, ...}],
  "연간_근거": {"보고서": "2025 사업보고서", "접수번호": "...", "url": "...", "재무제표": "연결",
               "계정": {"매출액": "수익(매출액)", "영업이익": "영업이익(손실)"},
               "필드": "전전기 bfefrmtrm_amount, 전기 frmtrm_amount, 당기 thstrm_amount"},
  "올해누적": {"연도": 2026, "보고서": "반기보고서",
              "매출액": {"당기": 0, "전년동기": 0}, "영업이익": {"당기": 0, "전년동기": 0},
              "근거": {"보고서": "2026 반기보고서", "접수번호": "...", "url": "...", "재무제표": "연결",
                      "계정": {...}, "필드": "당기 thstrm_add_amount, 전년동기 frmtrm_add_amount"}}
}
```
  - `연간`은 오름차순 3개. 사업보고서가 없으면 `[]`, `연간_근거`는 `null`. 값을 못 구하면 해당 칸 `null`.
  - `올해누적`은 올해 보고서가 없으면 `null`. 누적 필드가 비면 `thstrm_amount` / `frmtrm_q_amount`로 대체하고 `필드`에 실제 쓴 필드를 적는다.
  - 최상위 `재무제표`는 연간 쪽(없으면 올해 쪽) 값.

- [ ] **Step 1: 실패하는 테스트 작성** — 가짜 fin: `{"year", "report", "rcept_no", "url", "fs_div": "CFS", "list": [{"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "수익(매출액)", ...amount 필드}, {... "dart_OperatingIncomeLoss" ...}]}`
  - `test_build_annual_full`: 2025 사업보고서(매출 bfefrmtrm 95650538591 / frmtrm 69184238320 / thstrm 82379163292, 영업이익 8017318466 / -5608802365 / 17391515095) + 2026 반기(매출 add 31184245863 / frmtrm_add 35893769749) → `연간 == [{"연도":2023,"매출액":95650538591,"영업이익":8017318466}, {2024,...}, {2025,...}]`, `올해누적["매출액"] == {"당기":31184245863,"전년동기":35893769749}`, `재무제표 == "연결"`
  - `test_build_annual_q1_fallback`: 1분기 fin의 `thstrm_add_amount == ""` → `thstrm_amount`, `frmtrm_q_amount` 사용, `근거["필드"]`에 `thstrm_amount` 포함
  - `test_build_annual_missing_year`: `bfefrmtrm_amount` 없음 → `연간[0]["매출액"] is None`
  - `test_build_annual_account_not_found`: list에 매출·영업이익 계정 없음 → 연간 값 모두 `None`, 예외 없음
  - `test_build_annual_no_reports`: `build_annual(None, None)` → `{"재무제표": None, "연간": [], "연간_근거": None, "올해누적": None}`
- [ ] **Step 2: 실패 확인** — discover 명령 → `build_annual` 없음
- [ ] **Step 3: 구현** — `build_annual`을 추가하고 `build_quarters`를 지운다.
- [ ] **Step 4: `main` 수정**
  - `periodic_reports(corp_code, 8)` → `select_reports`로 두 건만 고른다. `--count` 인자는 지운다.
  - `reports.json`에는 고른 보고서(없는 쪽 제외)만 쓴다.
  - 고른 각 보고서에 `fetch_fin`, `fetch_doc`을 그대로 실행한다.
  - `write_json(dart_dir / "annual.json", build_annual(...))`
  - 출력: 사용 보고서 목록과 `annual.json` 경로.
  - 사업보고서와 올해 보고서가 모두 없으면 `die("최근 정기보고서를 찾지 못했습니다.")`.
- [ ] **Step 5: 통과 확인** — discover 명령, 8 tests OK
- [ ] **Step 6: 실제 실행 확인** — Run: `py .claude/skills/anal/scripts/dart_fetch.py 코세스`
  Expected: `2025 사업보고서`와 `2026 반기보고서` 2건, `data/국내/089890_코세스/dart/annual.json` 생성, `연간` 매출 `[95650538591, 69184238320, 82379163292]`
- [ ] **Step 7: 커밋** — `git commit -m "feat(anal): 연간·올해 누적 실적 annual.json 생성"`

---

### Task 4: 판정 (`analyze.py`)

**Files:**
- Create: `S/analyze.py`, `S/test_analyze.py`

**Interfaces:**
- Consumes: Task 3의 `annual.json` 형식, `common.company_dir`, `common.fmt_eok`, `common.read_json`, `common.write_json`
- Produces:
  - `margin(revenue: int | None, op: int | None) -> float | None` — `revenue`가 `None`이거나 0 이하이면 `None`, 아니면 `round(op / revenue * 100, 2)`
  - `criterion1(data: dict) -> dict` — `{"판정": str, "1-a": {"판정": str, "매출액": [..], "영업이익": [..]}, "1-b": {"판정": str, ...올해누적 숫자}}`
  - `criterion2(data: dict) -> dict` — `{"판정": str, "영업이익률": [{"연도": int, "값": float | None}]}`
  - `render(company: str, code: str, data: dict, r1: dict, r2: dict, today: str) -> str` (마크다운)
  - CLI: `py S/analyze.py <회사명|종목코드>` → `분석/<YYYY-MM-DD>.md`·`.json` 저장, md를 출력

규칙(스펙 그대로):
- 1-a: 3개 연도 매출과 영업이익이 각각 엄격히 증가해야 `통과`. 값이 하나라도 `None`이거나 연도가 3개 미만이면 `판정 불가`.
- 1-b: `올해누적`이 `null`이면 `해당 없음`. 네 값 중 하나라도 `None`이면 `판정 불가`. 매출·영업이익 모두 `당기 > 전년동기`이면 `통과`.
- 기준 1 종합: 하나라도 `탈락`이면 `탈락`, 아니면서 하나라도 `판정 불가`이면 `판정 불가`, 아니면 `통과` (`해당 없음`은 무시).
- 기준 2: 3개 연도 영업이익률이 모두 계산되고 각 해가 전해보다 `>=`이면 `통과`. 하나라도 `None`이거나 연도가 3개 미만이면 `판정 불가`.

- [ ] **Step 1: 실패하는 테스트 작성** (`S/test_analyze.py`; `data`는 `{"연간": [...], "올해누적": {...}}`만 채운다)
  - `test_c1_pass`: 매출 100→110→120, 영업이익 10→11→12, 누적 매출 60>50, 누적 영업이익 6>5 → `통과`
  - `test_c1_equal_fails`: 매출 100→100→120 → 1-a `탈락`, 기준 1 `탈락`
  - `test_c1_loss_shrinking`: 영업이익 -100→-50→30(매출 증가) → 1-a `통과`
  - `test_c1_ytd_not_applicable`: `올해누적 = None`, 1-a 통과 → 1-b `해당 없음`, 기준 1 `통과`
  - `test_c1_ytd_fails`: 누적 매출 50<60 → 1-b `탈락`, 기준 1 `탈락`
  - `test_c1_missing_year`: `연간[0]["매출액"] = None` → 1-a `판정 불가`, 기준 1 `판정 불가`(1-b 통과일 때)
  - `test_c1_fail_beats_unknown`: 1-a `탈락` + 1-b 값 `None` → 기준 1 `탈락`
  - `test_c2_pass_equal`: 영업이익률 10.0, 10.0, 12.0 → `통과`
  - `test_c2_equal_after_rounding`: 매출 300,000 영업이익 30,001 (10.0) vs 매출 100,000 영업이익 10,000 (10.0) → 같음으로 `통과`
  - `test_c2_drop_fails`: 10.0 → 9.99 → `탈락`
  - `test_c2_negative_margin`: 영업이익률 -8.11, 8.38, 21.11 → `통과`
  - `test_c2_zero_revenue`: 한 해 매출 0 → `판정 불가`
  - `test_margin`: `margin(82379163292, 17391515095) == 21.11`, `margin(0, 5) is None`
- [ ] **Step 2: 실패 확인** — discover 명령 → `analyze` 모듈 없음
- [ ] **Step 3: 구현** — 위 시그니처대로. `render` 형식:
  1. 제목 `# <회사>(<코드>) 분석 — <날짜>`와 재무제표 구분, 사용 보고서(접수번호, DART 링크)
  2. 요약 표 `| # | 기준 | 판정 | 핵심 수치 |` 2행과 `**종합: 2개 기준 중 N개 통과**`
  3. 기준 1 표: 연도별 매출·영업이익(`fmt_eok`), 1-a/1-b 판정, 올해 누적 대 전년 동기. 1-b가 `해당 없음`이면 "올해 정기보고서가 아직 없어 1-a만으로 판정" 문장
  4. 기준 2 표: 연도별 영업이익률(소수 둘째 자리 %)
  5. 각 표 아래에 `연간_근거`·`올해누적.근거`를 `[보고서, 재무제표 손익계산서 '계정', 필드, 접수번호](url)` 형식으로
- [ ] **Step 4: 통과 확인** — discover 명령, 전체(21 tests) OK
- [ ] **Step 5: 실제 실행 확인** — Run: `py .claude/skills/anal/scripts/analyze.py 코세스`
  Expected: 기준 1 `탈락`(매출 2023 957억 → 2024 692억 감소), 기준 2 `탈락`(2023 8.38% → 2024 -8.11%), `종합: 2개 기준 중 0개 통과`, `data/국내/089890_코세스/분석/2026-10-03.md` 생성
- [ ] **Step 6: 커밋** — `git commit -m "feat(anal): 두 기준 판정과 분석 보고서"`

---

### Task 5: 문서 (`원칙.md`, `SKILL.md`, `CLAUDE.md`)와 끝까지 확인

**Files:**
- Create: `원칙.md`, `.claude/skills/anal/SKILL.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: Task 3·4의 CLI와 파일 형식

- [ ] **Step 1: `원칙.md`** — 상위 `../원칙.md`의 구조(1. 근거의 범위 / 2. 분석 기준 / 3. 출처 표시)를 따른다.
  - 1절: FnGuide 예외 문단을 삭제한다. 드라이브 폴더 문단은 유지한다.
  - 2절: 스펙 "판정 규칙" 전체(기준 1·2, 공통, 판정 불가 표, 기준 1 종합 규칙).
  - 3절: 상위 표에서 FnGuide 행을 삭제한다.
  - 첫 문단에 "판정 로직은 `.claude/skills/anal/scripts/analyze.py`의 `criterion1`, `criterion2`에 구현"을 적는다.
- [ ] **Step 2: `SKILL.md`** — frontmatter
  - `name: anal`
  - `description`: "DART 정기보고서를 가져와 원칙.md의 두 기준(매출·영업이익 연속 성장, 영업이익률 유지)으로 한국 상장사를 분석하고, DART 보고서·로컬 파일·구글 드라이브 자료만 근거로 질문에 답한다. '○○ anal로 분석해 줘', '○○ 보고서에서 △△ 확인해 줘'처럼 특정 회사의 분석이나 질의를 요청할 때 사용한다."
  - 본문: 상위 SKILL.md 구조를 따르되 FnGuide 단계를 삭제하고, 단계를 1 수집, 2 판정, 3 드라이브, 4 결과 전달로 한다. 경로는 `.claude/skills/anal/scripts/`. 질의 모드 파일 표의 `quarters.json`을 `annual.json`으로 바꾸고 `fnguide` 행을 삭제한다.
- [ ] **Step 3: `CLAUDE.md`** — 상위 `../CLAUDE.md` 구조를 따르고 스펙 "CLAUDE.md 내용"을 반영한다. FnGuide 줄을 삭제하고, 스킬명·경로·`criterion1`/`criterion2`를 반영한다.
- [ ] **Step 4: 상위 스킬과 이름 충돌 확인** — `testproject`에서 새 세션을 열면 상위 `dart-analyst`도 보일 수 있다. `SKILL.md` description에 "anal"이 들어갔는지 확인한다.
- [ ] **Step 5: 끝까지 확인 (분석 모드)** — 새 세션 또는 현재 세션에서 SKILL.md 절차대로 코세스를 분석한다. Expected: Task 4 Step 5와 같은 판정, 드라이브 자료 7건 검색, 보고서 링크 제시.
- [ ] **Step 6: 끝까지 확인 (질의 모드)**
  - "코세스 2025년 영업이익은?" → 174억원(17,391,515,095원), 문장마다 `[2025 사업보고서 ...]` 출처
  - "코세스 2026년 배당 계획은?" → 근거에 없으면 정확히 "DART 정기보고서와 로컬 파일에서 찾을 수 없습니다."
- [ ] **Step 7: 커밋** — `git add 원칙.md CLAUDE.md .claude/skills/anal/SKILL.md docs && git commit -m "docs(anal): 원칙, 스킬 절차, CLAUDE.md"`
