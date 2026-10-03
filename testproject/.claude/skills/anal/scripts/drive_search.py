"""구글 드라이브 자료 폴더에서 키워드가 들어간 파일을 찾는다.

PDF는 텍스트를 한 번 추출해 data/_cache/drive_text/ 에 저장하고(파일이 바뀌면 다시 추출),
파일 이름과 본문을 함께 검색한다. PDF 추출에는 pypdf가 필요하다 (py -m pip install --user pypdf).

사용: py drive_search.py <키워드> [<키워드> ...] [--root 경로] [--context 80]
  키워드는 OR로 찾는다. 예: py drive_search.py ISC 아이에스시
결과: 일치한 파일, 페이지 번호, 앞뒤 문맥
"""
import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

from common import CACHE, die

logging.getLogger("pypdf").setLevel(logging.ERROR)  # 손상 객체 경고가 수백 줄 찍히는 것을 막는다

DEFAULT_ROOT = Path(r"G:\내 드라이브\Chrome에서 저장됨")
TEXT_CACHE = CACHE / "drive_text"


def pdf_pages(path):
    """페이지별 텍스트 목록. 캐시가 있으면 재사용한다."""
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()
    cached = TEXT_CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    try:
        from pypdf import PdfReader
    except ImportError:
        die("pypdf가 없습니다: py -m pip install --user pypdf")
    pages = []
    try:
        for p in PdfReader(str(path)).pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
    except Exception as e:
        print(f"  - 읽기 실패: {path.name} ({e.__class__.__name__})", file=sys.stderr)
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--context", type=int, default=80, help="일치 위치 앞뒤로 보여 줄 글자 수")
    ap.add_argument("--max-hits", type=int, default=3, help="파일당 보여 줄 최대 일치 수")
    ap.add_argument("--name-filter", help="파일명이 이 정규식에 맞는 파일만 본문 검색 (예: '반도체|소켓')")
    a = ap.parse_args()

    root = Path(a.root)
    if not root.exists():
        die(f"드라이브 폴더가 없습니다: {root} (Google Drive 앱 로그인 상태를 확인하세요)")
    # 영문·숫자 키워드는 단어 경계로 찾는다 (ISC가 DISCLAIMER에 걸리지 않도록)
    parts = [rf"(?<![A-Za-z0-9]){re.escape(k)}(?![A-Za-z0-9])" if re.fullmatch(r"[A-Za-z0-9]+", k)
             else re.escape(k) for k in a.keywords]
    pat = re.compile("|".join(parts), re.I)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if a.name_filter:
        nf = re.compile(a.name_filter, re.I)
        files = [p for p in files if nf.search(p.name) or pat.search(p.name)]
    hits = 0
    for i, f in enumerate(files, 1):
        rel = f.relative_to(root)
        name_hit = bool(pat.search(f.name))
        body = []
        if f.suffix.lower() == ".pdf":
            for n, text in enumerate(pdf_pages(f), 1):
                flat = re.sub(r"\s+", " ", text)
                for m in pat.finditer(flat):
                    s, e = max(0, m.start() - a.context), m.end() + a.context
                    body.append((n, flat[s:e]))
                    if len(body) >= a.max_hits:
                        break
                if len(body) >= a.max_hits:
                    break
        if name_hit or body:
            hits += 1
            print(f"\n## {rel}" + ("  (파일명 일치)" if name_hit else ""))
            for n, snip in body:
                print(f"  p.{n}: …{snip}…")
        if i % 50 == 0:
            print(f"[진행 {i}/{len(files)}]", file=sys.stderr)
    print(f"\n일치 파일 {hits}개 / 전체 {len(files)}개 (폴더: {root})")


if __name__ == "__main__":
    main()
