"""판정에 쓸 DART 정기보고서(최근 사업보고서 + 올해 최신 보고서)를 받아 저장하고 annual.json을 만든다.

사용: py dart_fetch.py <회사명|종목코드>
결과: data/국내/<종목코드>_<회사명>/dart/
  company.json        회사 기본정보
  reports.json        받은 보고서 목록 (접수번호, DART 링크)
  재무_<연도>_<보고서>.json   OpenDART 전체 재무제표 원자료
  원문/<연도>_<보고서>.txt    보고서 원문 텍스트 (질의 근거용)
  annual.json         3개 연도 매출액·영업이익과 올해 누적 실적 (분석 입력)
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


def select_reports(reports):
    """최신순 보고서 목록에서 (최근 사업보고서, 그 이후 연도의 최신 보고서)를 고른다."""
    annual = next((r for r in reports if r["reprt_code"] == "11011"), None)
    ytd = next((r for r in reports if r["reprt_code"] != "11011"
                and (annual is None or r["year"] > annual["year"])), None)
    return annual, ytd


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


def _src(f, picked, fields):
    return {"보고서": f"{f['year']} {f['report']}", "접수번호": f["rcept_no"], "url": f["url"],
            "재무제표": fs_name(f),
            "계정": {k: (x["account_nm"] if x else None) for k, x in picked.items()},
            "필드": fields}


def fs_name(f):
    return "연결" if f["fs_div"] == "CFS" else "별도"


def _pick_both(f):
    return {"매출액": pick(f, REV_IDS, REV_NMS), "영업이익": pick(f, OI_IDS, OI_NMS)}


def build_annual(annual_fin, ytd_fin, ytd_report=None):
    """사업보고서의 3개 연도 실적과 올해 보고서의 누적 실적을 annual.json 형식으로 만든다.

    ytd_report: 올해 보고서 목록 항목. 보고서는 있는데 ytd_fin이 없으면 값 없음으로 기록한다.
    """
    out = {"재무제표": None, "연간": [], "연간_근거": None, "올해누적": None}
    if annual_fin:
        picked = _pick_both(annual_fin)

        def val(item, field):
            x = picked[item]
            return amount(x.get(field)) if x else None

        y = annual_fin["year"]
        for offset, field in ((2, "bfefrmtrm_amount"), (1, "frmtrm_amount"), (0, "thstrm_amount")):
            out["연간"].append({"연도": y - offset, "매출액": val("매출액", field),
                               "영업이익": val("영업이익", field)})
        out["연간_근거"] = _src(annual_fin, picked,
                              "전전기 bfefrmtrm_amount, 전기 frmtrm_amount, 당기 thstrm_amount")
        out["재무제표"] = fs_name(annual_fin)
    if ytd_fin:
        picked = _pick_both(ytd_fin)
        pairs = [("thstrm_add_amount", "frmtrm_add_amount")]
        if ytd_fin.get("reprt_code") == "11013":  # 1분기는 3개월 = 누적
            pairs.append(("thstrm_amount", "frmtrm_q_amount"))
        used = []
        ytd = {"연도": ytd_fin["year"], "보고서": ytd_fin["report"]}
        for item, x in picked.items():
            ytd[item] = {"당기": None, "전년동기": None}
            for cur, prev in pairs:  # 당기와 전년동기는 같은 기간 쌍으로만 고른다
                c, pv = (amount(x.get(cur)), amount(x.get(prev))) if x else (None, None)
                if c is not None and pv is not None:
                    ytd[item] = {"당기": c, "전년동기": pv}
                    if (cur, prev) not in used:
                        used.append((cur, prev))
                    break
        ytd["근거"] = _src(ytd_fin, picked, "; ".join(f"당기 {c}, 전년동기 {pv}" for c, pv in used)
                         or "누적 금액 없음")
        out["올해누적"] = ytd
        out["재무제표"] = out["재무제표"] or fs_name(ytd_fin)
    elif ytd_report:  # 보고서는 있으나 재무 데이터를 받지 못함 → 1-b 판정 불가가 되도록 값 없음으로 둔다
        empty = {"당기": None, "전년동기": None}
        out["올해누적"] = {
            "연도": ytd_report["year"], "보고서": ytd_report["report"],
            "매출액": dict(empty), "영업이익": dict(empty),
            "근거": {"보고서": f"{ytd_report['year']} {ytd_report['report']}",
                   "접수번호": ytd_report["rcept_no"], "url": ytd_report["url"],
                   "재무제표": None, "계정": {}, "필드": "재무 데이터 없음"}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help="회사명 또는 종목코드")
    a = ap.parse_args()

    corp = resolve(a.company)
    info = dart_json("company.json", corp_code=corp["corp_code"])
    if info.get("acc_mt") != "12":
        die(f"{corp['corp_name']}은(는) {info.get('acc_mt')}월 결산입니다. "
            "현재는 12월 결산 법인만 지원합니다.")
    base = DOMESTIC / f"{corp['stock_code']}_{corp['corp_name']}"
    dart_dir = base / "dart"
    (base / "메모").mkdir(parents=True, exist_ok=True)
    write_json(dart_dir / "company.json", {k: info.get(k) for k in (
        "corp_code", "corp_name", "stock_code", "ceo_nm", "corp_cls", "induty_code",
        "est_dt", "acc_mt", "hm_url")})

    annual, ytd = select_reports(periodic_reports(corp["corp_code"], 8))
    reps = [r for r in (annual, ytd) if r]
    if not reps:
        die("최근 정기보고서를 찾지 못했습니다.")
    write_json(dart_dir / "reports.json", reps)
    print(f"{corp['corp_name']}({corp['stock_code']}) 판정용 정기보고서 {len(reps)}건")

    fins = {}
    for r in reps:
        stem = f"{r['year']}_{r['report']}"
        print(f"  · {r['report_nm']} ({r['rcept_no']})")
        fins[r["rcept_no"]] = fetch_fin(corp["corp_code"], r, dart_dir / f"재무_{stem}.json")
        fetch_doc(r, dart_dir / "원문" / f"{stem}.txt")

    data = build_annual(fins.get(annual["rcept_no"]) if annual else None,
                        fins.get(ytd["rcept_no"]) if ytd else None, ytd)
    write_json(dart_dir / "annual.json", data)
    print(f"연간·올해 누적 실적 → {dart_dir / 'annual.json'}")
    print(f"저장 위치: {base}")


if __name__ == "__main__":
    main()
