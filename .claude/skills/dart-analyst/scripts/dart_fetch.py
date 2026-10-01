"""DART 정기보고서(분기·반기·사업) 재무 숫자와 원문을 받아 저장하고 분기 실적표를 만든다.

사용: py dart_fetch.py <회사명|종목코드> [--count 8]
결과: data/국내/<종목코드>_<회사명>/dart/
  company.json        회사 기본정보
  reports.json        받은 보고서 목록 (접수번호, DART 링크)
  재무_<연도>_<보고서>.json   OpenDART 전체 재무제표 원자료
  원문/<연도>_<보고서>.txt    보고서 원문 텍스트 (질의 근거용)
  quarters.json       분기별 매출액·영업이익 (분석 입력)
"""
import argparse
import html
import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

from common import (CACHE, DATA, DOMESTIC, REPRT, dart_key, die, http_get, read_json,
                    write_json)

API = "https://opendart.fss.or.kr/api"


def dart_json(path, **params):
    params["crtfc_key"] = dart_key()
    return json.loads(http_get(f"{API}/{path}", params).decode("utf-8"))


# ---------- 회사 찾기 ----------

def corp_list():
    xml_path = CACHE / "corpcode.xml"
    if not xml_path.exists() or time.time() - xml_path.stat().st_mtime > 7 * 86400:
        raw = http_get(f"{API}/corpCode.xml", {"crtfc_key": dart_key()})
        if not raw.startswith(b"PK"):
            die("회사 코드 목록을 받지 못했습니다: " + raw[:200].decode("utf-8", "replace"))
        CACHE.mkdir(parents=True, exist_ok=True)
        xml_path.write_bytes(zipfile.ZipFile(io.BytesIO(raw)).read("CORPCODE.xml"))
    rows = []
    for el in ET.parse(xml_path).getroot():
        stock = (el.findtext("stock_code") or "").strip()
        if stock:  # 상장사만
            rows.append({"corp_code": el.findtext("corp_code"),
                         "corp_name": el.findtext("corp_name").strip(),
                         "stock_code": stock})
    return rows


def resolve(query):
    rows = corp_list()
    hit = [r for r in rows if query in (r["stock_code"], r["corp_name"])]
    if len(hit) == 1:
        return hit[0]
    part = [r for r in rows if query in r["corp_name"]]
    if len(part) == 1:
        return part[0]
    if not part:
        die(f"'{query}'에 해당하는 상장사를 찾지 못했습니다.")
    cands = ", ".join(f"{r['corp_name']}({r['stock_code']})" for r in part[:15])
    die(f"여러 회사가 해당됩니다. 정확한 이름이나 종목코드로 다시 요청하세요: {cands}", 2)


# ---------- 보고서 목록 ----------

NAME_RE = re.compile(r"(사업보고서|반기보고서|분기보고서)\s*\((\d{4})\.(\d{2})\)")


def periodic_reports(corp_code, count):
    bgn = (date.today() - timedelta(days=365 * 3 + 120)).strftime("%Y%m%d")
    found, page = {}, 1
    while True:
        d = dart_json("list.json", corp_code=corp_code, bgn_de=bgn, pblntf_ty="A",
                      last_reprt_at="Y", page_no=page, page_count=100)
        if d["status"] == "013":
            break
        if d["status"] != "000":
            die(f"공시 목록 조회 실패: {d['status']} {d.get('message')}")
        for x in d["list"]:
            m = NAME_RE.search(x["report_nm"])
            if not m:
                continue
            kind, yyyy, mm = m.groups()
            code = {"사업보고서": "11011", "반기보고서": "11012"}.get(kind)
            if kind == "분기보고서":
                code = {"03": "11013", "09": "11014"}.get(mm)
            if not code:
                continue
            key = (int(yyyy), code)
            if key not in found or x["rcept_dt"] > found[key]["rcept_dt"]:
                found[key] = {"year": int(yyyy), "reprt_code": code,
                              "report": REPRT[code][0], "report_nm": x["report_nm"].strip(),
                              "rcept_no": x["rcept_no"], "rcept_dt": x["rcept_dt"],
                              "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x['rcept_no']}"}
        if page >= d["total_page"]:
            break
        page += 1
    order = sorted(found.values(), key=lambda r: (r["year"], REPRT[r["reprt_code"]][1]),
                   reverse=True)
    return order[:count]


# ---------- 재무제표 ----------

def fetch_fin(corp_code, rep, out):
    if out.exists() and read_json(out).get("rcept_no") == rep["rcept_no"]:
        return read_json(out)
    for fs_div in ("CFS", "OFS"):  # 연결 우선, 연결이 없으면 별도
        d = dart_json("fnlttSinglAcntAll.json", corp_code=corp_code,
                      bsns_year=rep["year"], reprt_code=rep["reprt_code"], fs_div=fs_div)
        if d["status"] == "000":
            obj = {**rep, "fs_div": fs_div, "list": d["list"]}
            write_json(out, obj)
            return obj
        if d["status"] != "013":
            die(f"재무제표 조회 실패({rep['report_nm']}): {d['status']} {d.get('message')}")
    print(f"  - {rep['report_nm']}: 재무제표 데이터 없음")
    return None


# ---------- 원문 ----------

def xml_to_text(s):
    s = re.sub(r"<IMAGE.*?</IMAGE>", "", s, flags=re.S)
    # 표의 한 행은 한 줄로: 행 안의 줄바꿈·문단 태그를 공백으로
    s = re.sub(r"<TR\b.*?</TR>",
               lambda m: re.sub(r"</P>|<BR\s*/?>|\s*\n\s*", " ", m.group(0), flags=re.I),
               s, flags=re.S)

    def section_title(m):
        return "\n\n" + "#" * int(m.group(1)) + " " + re.sub(r"<[^>]+>", "", m.group(2)).strip() + "\n"
    s = re.sub(r"<SECTION-(\d)[^>]*>\s*<TITLE[^>]*>(.*?)</TITLE>", section_title, s, flags=re.S)
    s = re.sub(r"<TITLE[^>]*>(.*?)</TITLE>", r"\n\n#### \1\n", s, flags=re.S)
    s = re.sub(r"</TR>", "\n", s)
    s = re.sub(r"<(TD|TH|TE|TU)\b[^>]*>", " | ", s)
    s = re.sub(r"</P>|<PGBRK[^>]*>|</TABLE>|<BR\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in s.splitlines()]
    out, blank = [], 0
    for ln in lines:
        if ln in ("", "|"):
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def fetch_doc(rep, out):
    head = f"<!-- {rep['report_nm']} | 접수번호 {rep['rcept_no']} | {rep['url']} -->\n"
    if out.exists() and out.read_text(encoding="utf-8").startswith(head):
        return
    raw = http_get(f"{API}/document.xml", {"crtfc_key": dart_key(), "rcept_no": rep["rcept_no"]},
                   timeout=180)
    if not raw.startswith(b"PK"):
        print(f"  - {rep['report_nm']}: 원문을 받지 못했습니다")
        return
    z = zipfile.ZipFile(io.BytesIO(raw))
    parts = []
    for name in sorted(z.namelist(), key=lambda n: (not n.startswith(rep["rcept_no"] + "."), n)):
        b = z.read(name)
        txt = None
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                txt = b.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        if txt:
            parts.append(f"\n\n<!-- 파일: {name} -->\n" + xml_to_text(txt))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(head + "".join(parts), encoding="utf-8")


# ---------- 분기 실적 도출 ----------

REV_IDS = {"ifrs-full_Revenue", "ifrs_Revenue"}
REV_NMS = {"매출액", "수익(매출액)", "매출", "영업수익", "매출액(영업수익)"}
OI_IDS = {"dart_OperatingIncomeLoss"}
OI_NMS = {"영업이익", "영업이익(손실)", "영업손익"}


def amount(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    if v in ("", "-"):
        return None
    return int(float(v))


def pick(fin, ids, names):
    """손익계산서(IS, 없으면 포괄손익계산서 CIS)에서 계정을 찾는다."""
    for sj in ("IS", "CIS"):
        rows = [x for x in fin["list"] if x["sj_div"] == sj]
        for x in rows:
            if x["account_id"] in ids:
                return x
        for x in rows:
            if x["account_nm"].replace(" ", "") in names:
                return x
    return None


def build_quarters(fins):
    by = {(f["year"], f["reprt_code"]): f for f in fins if f}
    years = sorted({y for y, _ in by})
    out = []
    for item, ids, names in (("매출액", REV_IDS, REV_NMS), ("영업이익", OI_IDS, OI_NMS)):
        for y in years:
            rows = {c: (by[(y, c)], pick(by[(y, c)], ids, names))
                    for c in REPRT if (y, c) in by}

            def cell(code, field):
                if code not in rows or rows[code][1] is None:
                    return None
                return amount(rows[code][1].get(field))

            def src(code, how):
                f, x = rows[code]
                return {"보고서": f"{y} {f['report']}", "접수번호": f["rcept_no"],
                        "재무제표": "연결" if f["fs_div"] == "CFS" else "별도",
                        "계정": x["account_nm"] if x else None, "산출": how}

            q = {}
            if cell("11013", "thstrm_amount") is not None:
                q[1] = (cell("11013", "thstrm_amount"), [src("11013", "1분기 3개월 금액")])
            if cell("11012", "thstrm_amount") is not None:
                q[2] = (cell("11012", "thstrm_amount"), [src("11012", "2분기 3개월 금액")])
            if cell("11014", "thstrm_amount") is not None:
                q[3] = (cell("11014", "thstrm_amount"), [src("11014", "3분기 3개월 금액")])
            annual, cum3 = cell("11011", "thstrm_amount"), cell("11014", "thstrm_add_amount")
            if annual is not None and cum3 is not None:
                q[4] = (annual - cum3, [src("11011", "연간 금액"),
                                        src("11014", "3분기 누적 금액을 빼서 4분기 산출")])
            for n, (v, s) in q.items():
                out.append({"분기": f"{y}Q{n}", "연도": y, "분기번호": n,
                            "항목": item, "금액_원": v, "근거": s})
    return sorted(out, key=lambda r: (r["항목"], r["연도"], r["분기번호"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help="회사명 또는 종목코드")
    ap.add_argument("--count", type=int, default=8, help="받을 최근 정기보고서 수 (기본 8)")
    a = ap.parse_args()

    corp = resolve(a.company)
    info = dart_json("company.json", corp_code=corp["corp_code"])
    if info.get("acc_mt") != "12":
        die(f"{corp['corp_name']}은(는) {info.get('acc_mt')}월 결산입니다. "
            "현재는 12월 결산 법인만 분기 계산을 지원합니다.")
    base = DOMESTIC / f"{corp['stock_code']}_{corp['corp_name']}"
    dart_dir = base / "dart"
    (base / "메모").mkdir(parents=True, exist_ok=True)
    write_json(dart_dir / "company.json", {k: info.get(k) for k in (
        "corp_code", "corp_name", "stock_code", "ceo_nm", "corp_cls", "induty_code",
        "est_dt", "acc_mt", "hm_url")})

    reps = periodic_reports(corp["corp_code"], a.count)
    if not reps:
        die("최근 정기보고서를 찾지 못했습니다.")
    write_json(dart_dir / "reports.json", reps)
    print(f"{corp['corp_name']}({corp['stock_code']}) 정기보고서 {len(reps)}건")

    fins = []
    for r in reps:
        stem = f"{r['year']}_{r['report']}"
        print(f"  · {r['report_nm']} ({r['rcept_no']})")
        fins.append(fetch_fin(corp["corp_code"], r, dart_dir / f"재무_{stem}.json"))
        fetch_doc(r, dart_dir / "원문" / f"{stem}.txt")

    quarters = build_quarters(fins)
    write_json(dart_dir / "quarters.json", quarters)
    print(f"분기 실적 {len(quarters)}건 → {dart_dir / 'quarters.json'}")
    print(f"저장 위치: {base}")


if __name__ == "__main__":
    main()
