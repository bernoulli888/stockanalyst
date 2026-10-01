# stockanalyst

DART 정기보고서로 한국 상장사를 분석하고, 분석한 내용을 질의로 확인하는 프로젝트다. 앱이 아니라 Claude Code가 문서와 스크립트를 따라 작업한다.

## 반드시 지킬 것

- 기준과 근거 규칙은 [원칙.md](원칙.md)를 따른다. 기업 분석이나 보고서 질의 전에 읽는다.
- 작업 절차는 `dart-analyst` 스킬([SKILL.md](.claude/skills/dart-analyst/SKILL.md))을 따른다.
- 답의 근거는 DART 정기보고서, `data/` 아래 로컬 파일, 구글 드라이브 자료 폴더(`G:\내 드라이브\Chrome에서 저장됨`)뿐이다. 분석과 질의 때는 드라이브에서 해당 종목 자료를 항상 찾아본다. 외부 출처는 FnGuide(주가·컨센서스·업종 PER·PBR)만 예외로 허용한다. 찾을 수 없으면 "DART 정기보고서와 로컬 파일에서 찾을 수 없습니다"라고 답한다.
- 질의 답변에는 문장마다 출처를 붙인다.
- 숫자 계산과 판정은 스크립트가 한다. 직접 계산해서 스크립트 결과를 덮어쓰지 않는다.

## 환경

- Python: `py` 명령으로 실행한다(3.13). `python` 명령은 동작하지 않는다. 외부 패키지는 `drive_search.py`의 PDF 추출용 `pypdf` 하나뿐이다(`py -m pip install --user pypdf`). 나머지 스크립트는 표준 라이브러리만 쓴다.
- 구글 드라이브: Google Drive 데스크톱 앱이 `G:`로 연결한다. 앱이 로그아웃되면 폴더가 보이지 않는다. 긴 PDF는 Read 도구로 페이지 지정이 안 되므로(poppler 없음) `drive_search.py`로 찾은 뒤 캐시된 텍스트를 읽는다.
- OpenDART API 키: `.env`의 `DART_API_KEY`. 키 값을 문서, 보고서, 대화 출력에 적지 않는다.
- FnGuide: `wcomp.fnguide.com`(신버전)을 쓴다. 예전 주소 `comp.fnguide.com`은 닫혔다. FnGuide 자료는 저작권이 있으므로 요청받은 한 회사씩만 조회하고, 대량으로 수집하지 않는다.

## 폴더 구조

```
원칙.md                               분석 기준과 근거 규칙 (정본)
.env                                  DART_API_KEY (git 제외)
.claude/skills/dart-analyst/
  SKILL.md                            작업 절차
  scripts/
    common.py                         경로, .env, HTTP 공통
    dart_fetch.py                     DART 수집 → quarters.json
    fnguide_fetch.py                  FnGuide 조회
    analyze.py                        세 기준 판정 → 분석 보고서
    drive_search.py                   구글 드라이브 자료 검색 (파일명·PDF 본문)
data/
  _cache/corpcode.xml                 DART 회사 코드 목록 (7일마다 갱신)
  _cache/drive_text/                  드라이브 PDF 추출 텍스트 캐시
  국내/<종목코드>_<회사명>/
    dart/                             company.json, reports.json, 재무_*.json, quarters.json, 원문/*.txt
    fnguide/<날짜>.json               주가·컨센서스·업종 값
    분석/<날짜>.md, .json              판정 보고서
    메모/                             직접 넣는 자료 (질의 근거에 포함)
  해외/                               해외 기업 자료
```

## 기준을 바꿀 때

`원칙.md`를 고치면 `analyze.py`의 해당 기준 함수(`criterion1`~`criterion3`)도 함께 고친다. 둘이 어긋나면 판정이 원칙과 달라진다.
