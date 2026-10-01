"""FnGuide에서 주가, 다음 연도(FY1) 컨센서스, 업종 PER·PBR을 받아 저장한다.

원칙.md의 유일한 외부 출처 예외다. 받은 값에는 출처 URL과 조회 시각을 함께 남긴다.

사용: py fnguide_fetch.py <회사명|종목코드>   (dart_fetch.py로 먼저 수집한 회사)
결과: data/<종목코드>_<회사명>/fnguide/<YYYY-MM-DD>.json
"""
import argparse
import json
import re
from datetime import datetime

from common import company_dir, die, http_get, read_json, write_json

BASE = "https://wcomp.fnguide.com"


def num(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def page_lines(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t).replace("&nbsp;", " ").replace("&#124;", "|")
    return [ln.strip() for ln in t.splitlines() if ln.strip()]


def snapshot(code):
    url = f"{BASE}/CompanyInfo/Snapshot?cmp_cd={code}"
    html = http_get(url).decode("utf-8", "replace")
    if f"({code})" not in html:
        die(f"FnGuide에서 종목 {code} 페이지를 찾지 못했습니다: {url}")
    lines = page_lines(html)
    price = price_date = None
    for i, ln in enumerate(lines):
        if ln == "시세현황" and i + 1 < len(lines) and re.match(r"\[\d{4}/\d{2}/\d{2}\]", lines[i + 1]):
            price_date = lines[i + 1].strip("[]")
        if ln.startswith("종가/") and price is None:
            price = num(lines[i + 1].rstrip("/"))
    if price is None:
        die(f"FnGuide 종가를 읽지 못했습니다(페이지 구조 변경 가능): {url}")
    return {"url": url, "종가_원": price, "종가_기준일": price_date}


def consensus_fy1(code, consol_typ):
    """Financial Highlight(연간)에서 첫 추정(E) 연도의 EPS·BPS·PER·PBR. consol_typ: C=연결, P=별도."""
    url = f"{BASE}/CompanyInfo/getSnpFinancial?cmp_cd={code}&consol_typ={consol_typ}&freq_typ=A"
    d = json.loads(http_get(url).decode("utf-8"))["dataset"]
    annual, prev = [], ""
    for h in d["header"]:  # 앞쪽 연간 열만 (연도가 되돌아가면 분기 열 시작)
        if h["YYMM"] < prev:
            break
        annual.append(h)
        prev = h["YYMM"]
    est = next((h for h in annual if (h.get("EP_CHK") or "").strip() == "E"), None)
    if not est:
        return {"url": url, "연도": None, "사유": "FnGuide에 추정(E) 연도 컨센서스가 없습니다."}
    rows = {r["NAME"].strip(): r for r in d["data"]}

    def val(name):
        r = rows.get(name)
        return num(r.get(est["CD"])) if r else None
    return {"url": url, "연도": est["YYMM"], "재무제표": est.get("CONSOL_TYPE"),
            "EPS_원": val("EPS"), "BPS_원": val("BPS"),
            "FnGuide_PER": val("PER"), "FnGuide_PBR": val("PBR"),
            "매출액_억원": val("매출액"), "영업이익_억원": val("영업이익(발표기준)")}


def sector(code):
    """업종분석 페이지에 들어 있는 업종(WI26) PER·PBR 중 가장 최근 결산 연도 값."""
    url = f"{BASE}/CompanyInfo/SectorAnalysis?cmp_cd={code}"
    html = http_get(url).decode("utf-8", "replace")
    out = {"url": url}
    for key, label in (("secAnal1", "PER"), ("secAnal2", "PBR")):
        i = html.find(key + ":")
        if i < 0:
            out[label] = None
            continue
        d, _ = json.JSONDecoder().raw_decode(html[i + len(key) + 1:].lstrip())
        head = {h["ID"]: re.sub(r"<[^>]+>", " ", h["NM"]).split()[0] for h in d["header"]}
        row = next((r for r in d["data"] if r["GUBN"] == "2" and r["LVL"] == "1"), None)
        if not row:
            out[label] = None
            continue
        out["업종명"] = row["NM"].strip()
        out[label] = num(row.get("FY_0"))
        out[f"{label}_기준연도"] = head.get("FY_0")
    out["산출"] = "업종 구성종목 시가총액(기말) / 순이익(지배) 또는 순자산 — 최근 결산 연도 실적 기준"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help="회사명 또는 종목코드")
    a = ap.parse_args()
    base = company_dir(a.company)
    code = base.name.split("_", 1)[0]

    snap = snapshot(code)
    # DART에서 쓴 재무제표(연결/별도)와 같은 기준의 컨센서스를 먼저 찾는다
    quarters = base / "dart" / "quarters.json"
    separate = quarters.exists() and any(
        s["재무제표"] == "별도" for r in read_json(quarters) for s in r["근거"])
    for typ in (("P", "C") if separate else ("C", "P")):
        fy1 = consensus_fy1(code, typ)
        if fy1.get("EPS_원") is not None or fy1.get("BPS_원") is not None:
            break
    sec = sector(code)
    price = snap["종가_원"]
    fwd = {
        "연도": fy1.get("연도"),
        "PER": round(price / fy1["EPS_원"], 2) if fy1.get("EPS_원") and fy1["EPS_원"] > 0 else None,
        "PBR": round(price / fy1["BPS_원"], 2) if fy1.get("BPS_원") and fy1["BPS_원"] > 0 else None,
        "산출": "FnGuide 종가 / FY1 컨센서스 EPS(또는 BPS)",
    }
    now = datetime.now()
    obj = {"조회시각": now.strftime("%Y-%m-%d %H:%M"), "종목코드": code,
           "주가": snap, "컨센서스_FY1": fy1, "다음연도_밸류에이션": fwd, "업종": sec}
    out = base / "fnguide" / f"{now:%Y-%m-%d}.json"
    write_json(out, obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
