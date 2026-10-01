"""공통 기능: 경로, .env 로드, HTTP, 회사 폴더 찾기."""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# 콘솔(cp949)에서 한글·특수문자 출력이 깨지거나 죽지 않도록 한다
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# .claude/skills/dart-analyst/scripts/ → 프로젝트 루트
ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
CACHE = DATA / "_cache"
DOMESTIC = DATA / "국내"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# 보고서 코드 → (이름, 분기 번호). 사업보고서는 4분기 도출에 쓴다.
REPRT = {
    "11013": ("1분기보고서", 1),
    "11012": ("반기보고서", 2),
    "11014": ("3분기보고서", 3),
    "11011": ("사업보고서", 4),
}


def die(msg, code=1):
    print(f"[오류] {msg}", file=sys.stderr)
    sys.exit(code)


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def dart_key():
    load_env()
    key = os.environ.get("DART_API_KEY")
    if not key:
        die(f"DART_API_KEY가 없습니다. {ROOT / '.env'} 에 DART_API_KEY=... 를 넣어 주세요.")
    return key


def http_get(url, params=None, headers=None, timeout=60):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def company_dir(query):
    """이미 수집한 회사 폴더를 회사명 또는 종목코드로 찾는다."""
    if not DATA.exists():
        die("data 폴더가 없습니다. 먼저 dart_fetch.py 로 수집하세요.")
    dirs = [d for d in DATA.rglob("*")
            if d.is_dir() and not d.name.startswith("_")
            and (d / "dart").is_dir()]
    exact = [d for d in dirs if d.name.split("_", 1)[0] == query
             or d.name.split("_", 1)[-1] == query]
    if len(exact) == 1:
        return exact[0]
    part = [d for d in dirs if query in d.name]
    if len(part) == 1:
        return part[0]
    if not part:
        die(f"'{query}' 수집 폴더가 없습니다. 먼저 dart_fetch.py 로 수집하세요.")
    die("여러 회사가 해당됩니다: " + ", ".join(d.name for d in part))


def fmt_eok(won):
    """원 → 억원 문자열."""
    if won is None:
        return "-"
    return f"{won / 1e8:,.0f}억원"
