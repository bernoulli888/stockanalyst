"""원칙.md의 두 기준으로 회사를 판정하고 보고서를 저장한다.

사용: py analyze.py <회사명|종목코드>   (dart_fetch.py 실행 후)
결과: data/국내/<종목코드>_<회사명>/분석/<YYYY-MM-DD>.md (+ .json)
"""
import argparse
from datetime import date

from common import company_dir, die, fmt_eok, read_json, write_json

PASS, FAIL, NA, SKIP = "통과", "탈락", "판정 불가", "해당 없음"


def margin(revenue, op):
    """영업이익률(%). 매출이 없거나 0 이하이면 None."""
    if revenue is None or op is None or revenue <= 0:
        return None
    return round(op / revenue * 100, 2)


def _rising(vals, strict=True):
    """3개 값이 매년 증가(strict) 또는 같거나 증가하면 PASS. 값이 빠지면 NA."""
    if len(vals) < 3 or any(v is None for v in vals):
        return NA
    ok = all((b > a) if strict else (b >= a) for a, b in zip(vals, vals[1:]))
    return PASS if ok else FAIL


def _combine(*results):
    results = [r for r in results if r != SKIP]
    if FAIL in results:
        return FAIL
    if NA in results:
        return NA
    return PASS


def criterion1(data):
    """매출·영업이익 연속 성장: 1-a 3개 연도 매년 증가, 1-b 올해 누적 > 전년 동기."""
    years = data["연간"]
    rev = [y["매출액"] for y in years]
    op = [y["영업이익"] for y in years]
    a = {"판정": _combine(_rising(rev), _rising(op)), "매출액": rev, "영업이익": op}

    cum = data.get("올해누적")
    if cum is None:
        b = {"판정": SKIP}
    else:
        pairs = [cum["매출액"], cum["영업이익"]]
        if any(p["당기"] is None or p["전년동기"] is None for p in pairs):
            verdict = NA
        else:
            verdict = PASS if all(p["당기"] > p["전년동기"] for p in pairs) else FAIL
        b = {"판정": verdict, "연도": cum["연도"], "보고서": cum["보고서"],
             "매출액": cum["매출액"], "영업이익": cum["영업이익"]}
    return {"판정": _combine(a["판정"], b["판정"]), "1-a": a, "1-b": b}


def criterion2(data):
    """영업이익률 유지: 3개 연도 영업이익률이 매년 같거나 오른다."""
    rows = [{"연도": y["연도"], "값": margin(y["매출액"], y["영업이익"])} for y in data["연간"]]
    return {"판정": _rising([r["값"] for r in rows], strict=False), "영업이익률": rows}


def cite(src):
    if not src:
        return "근거 없음"
    acc = ", ".join(f"{k} '{v}'" for k, v in src["계정"].items())
    return (f"[{src['보고서']}, {src['재무제표']} 손익계산서 {acc}, {src['필드']}, "
            f"접수번호 {src['접수번호']}]({src['url']})")


def pct(v):
    return "-" if v is None else f"{v:.2f}%"


def render(company, code, data, r1, r2, today):
    n_pass = [r1["판정"], r2["판정"]].count(PASS)
    years = data["연간"]
    a, b = r1["1-a"], r1["1-b"]
    L = [f"# {company}({code}) 분석 — {today}", "",
         f"기준은 [원칙.md](../../../../원칙.md)를 따른다. 재무제표: {data.get('재무제표') or '-'}", "",
         "| # | 기준 | 판정 | 핵심 수치 |", "|---|---|---|---|"]
    span = f"{years[0]['연도']}→{years[-1]['연도']}" if years else "-"
    L.append(f"| 1 | 매출·영업이익 연속 성장 | {r1['판정']} | 1-a {a['판정']} ({span}), 1-b {b['판정']} |")
    m = " → ".join(pct(r["값"]) for r in r2["영업이익률"]) or "-"
    L.append(f"| 2 | 영업이익률 유지 | {r2['판정']} | {m} |")
    L += ["", f"**종합: 2개 기준 중 {n_pass}개 통과**", "",
          "## 기준 1. 매출·영업이익 연속 성장", "",
          f"### 1-a 연간 — {a['판정']}", "",
          "| 연도 | 매출액 | 영업이익 |", "|---|---|---|"]
    L += [f"| {y['연도']} | {fmt_eok(y['매출액'])} | {fmt_eok(y['영업이익'])} |" for y in years]
    L += ["", f"근거: {cite(data.get('연간_근거'))}", "", f"### 1-b 올해 누적 — {b['판정']}", ""]
    if b["판정"] == SKIP:
        L.append("올해 정기보고서가 아직 없어 기준 1은 1-a만으로 판정했다.")
    else:
        cum = data["올해누적"]
        L += [f"{cum['연도']} {cum['보고서']} 누적 기준", "",
              "| 항목 | 올해 누적 | 전년 동기 누적 |", "|---|---|---|"]
        for item in ("매출액", "영업이익"):
            L.append(f"| {item} | {fmt_eok(cum[item]['당기'])} | {fmt_eok(cum[item]['전년동기'])} |")
        L += ["", f"근거: {cite(cum.get('근거'))}"]
    L += ["", f"## 기준 2. 영업이익률 유지 — {r2['판정']}", "",
          "| 연도 | 영업이익률 |", "|---|---|"]
    L += [f"| {r['연도']} | {pct(r['값'])} |" for r in r2["영업이익률"]]
    L += ["", "영업이익률 = 영업이익 ÷ 매출액 × 100 (소수 둘째 자리 반올림). 숫자는 기준 1-a 표와 같다."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help="회사명 또는 종목코드")
    a = ap.parse_args()
    base = company_dir(a.company)
    code, name = base.name.split("_", 1)

    path = base / "dart" / "annual.json"
    if not path.exists():
        die("annual.json이 없습니다. dart_fetch.py를 먼저 실행하세요.")
    data = read_json(path)
    r1, r2 = criterion1(data), criterion2(data)
    today = date.today().isoformat()
    md = render(name, code, data, r1, r2, today)
    out = base / "분석" / f"{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    write_json(out.with_suffix(".json"), {"기준1": r1, "기준2": r2})
    print(md)
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
