"""원칙.md의 세 기준으로 회사를 판정하고 보고서를 저장한다.

사용: py analyze.py <회사명|종목코드>   (dart_fetch.py, fnguide_fetch.py 실행 후)
결과: data/<종목코드>_<회사명>/분석/<YYYY-MM-DD>.md (+ .json)
"""
import argparse
import json
from datetime import date

from common import company_dir, die, fmt_eok, read_json, write_json

PASS, FAIL, NA = "통과", "탈락", "판정 불가"


def prev_q(y, q):
    return (y, q - 1) if q > 1 else (y - 1, 4)


def cite(src, urls):
    return (f"[{src['보고서']}, {src['재무제표']} 손익계산서 '{src['계정']}', "
            f"{src['산출']}, 접수번호 {src['접수번호']}]({urls.get(src['접수번호'], '')})")


def criterion1(oi, urls):
    """최근 4개 분기 영업이익 합계가 흑자."""
    if not oi:
        return {"판정": NA, "사유": "영업이익 분기 데이터가 없습니다."}
    y, q = max(oi)
    keys = [(y, q)]
    for _ in range(3):
        keys.append(prev_q(*keys[-1]))
    missing = [f"{k[0]}Q{k[1]}" for k in keys if k not in oi]
    if missing:
        return {"판정": NA, "사유": f"분기 데이터 없음: {', '.join(missing)}"}
    total = sum(oi[k]["금액_원"] for k in keys)
    return {"판정": PASS if total > 0 else FAIL, "합계_원": total,
            "분기": [{"분기": f"{k[0]}Q{k[1]}", "금액_원": oi[k]["금액_원"],
                     "근거": [cite(s, urls) for s in oi[k]["근거"]]} for k in reversed(keys)]}


def criterion2(rev, urls):
    """최근 분기 매출액이 전년 같은 분기보다 증가(0% 초과)."""
    if not rev:
        return {"판정": NA, "사유": "매출액 분기 데이터가 없습니다."}
    y, q = max(rev)
    if (y - 1, q) not in rev:
        return {"판정": NA, "사유": f"비교 대상 {y - 1}Q{q} 매출액이 없습니다."}
    cur, base = rev[(y, q)]["금액_원"], rev[(y - 1, q)]["금액_원"]
    if base <= 0:
        return {"판정": NA, "사유": f"{y - 1}Q{q} 매출액이 0 이하라 성장률을 계산할 수 없습니다."}
    g = (cur - base) / base * 100
    return {"판정": PASS if g > 0 else FAIL, "성장률_퍼센트": round(g, 2),
            "최근": {"분기": f"{y}Q{q}", "금액_원": cur,
                   "근거": [cite(s, urls) for s in rev[(y, q)]["근거"]]},
            "전년동기": {"분기": f"{y - 1}Q{q}", "금액_원": base,
                     "근거": [cite(s, urls) for s in rev[(y - 1, q)]["근거"]]}}


def criterion3(fg):
    """다음 연도(FY1) PER·PBR이 둘 다 업종 평균보다 낮음."""
    if not fg:
        return {"판정": NA, "사유": "FnGuide 조회 결과가 없습니다. fnguide_fetch.py를 먼저 실행하세요."}
    fwd, sec = fg["다음연도_밸류에이션"], fg["업종"]
    parts = {}
    for k in ("PER", "PBR"):
        c, s = fwd.get(k), sec.get(k)
        if c is None or s is None:
            parts[k] = {"판정": NA, "회사": c, "업종": s,
                        "사유": "추정 이익이 적자이거나 값이 없습니다." if c is None else "업종 값이 없습니다."}
        else:
            parts[k] = {"판정": PASS if c < s else FAIL, "회사": c, "업종": s}
    vs = [p["판정"] for p in parts.values()]
    verdict = FAIL if FAIL in vs else (NA if NA in vs else PASS)
    return {"판정": verdict, **parts, "FY1": fwd.get("연도"),
            "종가_원": fg["주가"]["종가_원"], "종가_기준일": fg["주가"]["종가_기준일"],
            "업종명": sec.get("업종명"), "업종_기준연도": sec.get("PER_기준연도"),
            "조회시각": fg["조회시각"],
            "출처": [fg["주가"]["url"], fg["컨센서스_FY1"]["url"], sec["url"]]}


def render(name, code, r1, r2, r3, today):
    L = [f"# {name}({code}) 분석 — {today}", "",
         "기준은 [원칙.md](../../../원칙.md)를 따른다. 세 기준 모두 끝까지 계산한다.", "",
         "| # | 기준 | 판정 | 핵심 수치 |", "|---|---|---|---|"]
    k1 = fmt_eok(r1.get("합계_원")) if "합계_원" in r1 else r1.get("사유")
    k2 = (f"{r2['최근']['분기']} {fmt_eok(r2['최근']['금액_원'])} vs "
          f"{r2['전년동기']['분기']} {fmt_eok(r2['전년동기']['금액_원'])} ({r2['성장률_퍼센트']:+.2f}%)"
          if "성장률_퍼센트" in r2 else r2.get("사유"))
    def v(x):
        return "-" if x is None else x
    k3 = (f"PER {v(r3['PER']['회사'])} vs 업종 {v(r3['PER']['업종'])}, "
          f"PBR {v(r3['PBR']['회사'])} vs 업종 {v(r3['PBR']['업종'])}" if "PER" in r3 else r3.get("사유"))
    L += [f"| 1 | 최근 4개 분기 영업이익 합계 흑자 | {r1['판정']} | {k1} |",
          f"| 2 | 최근 분기 매출액 전년 동기 대비 증가 | {r2['판정']} | {k2} |",
          f"| 3 | 다음 연도 PER·PBR 모두 업종보다 낮음 | {r3['판정']} | {k3} |", ""]
    passed = sum(r["판정"] == PASS for r in (r1, r2, r3))
    L += [f"**종합: 3개 기준 중 {passed}개 통과**", ""]

    L += ["## 기준 1. 최근 4개 분기 영업이익 합계", ""]
    if "분기" in r1:
        L += ["| 분기 | 영업이익 | 근거 |", "|---|---|---|"]
        L += [f"| {x['분기']} | {fmt_eok(x['금액_원'])} | {'<br>'.join(x['근거'])} |" for x in r1["분기"]]
        L += [f"| **합계** | **{fmt_eok(r1['합계_원'])}** | 위 4개 분기 합 |", ""]
    else:
        L += [r1["사유"], ""]

    L += ["## 기준 2. 매출액 전년 동기 대비", ""]
    if "성장률_퍼센트" in r2:
        L += ["| 분기 | 매출액 | 근거 |", "|---|---|---|"]
        for k in ("최근", "전년동기"):
            L.append(f"| {r2[k]['분기']} | {fmt_eok(r2[k]['금액_원'])} | {'<br>'.join(r2[k]['근거'])} |")
        L += ["", f"성장률 = (최근 − 전년 동기) / 전년 동기 = **{r2['성장률_퍼센트']:+.2f}%**", ""]
    else:
        L += [r2["사유"], ""]

    L += ["## 기준 3. 다음 연도 PER·PBR vs 업종", ""]
    if "PER" in r3:
        L += [f"- 다음 연도(FY1): {r3['FY1']} 추정, 종가 {r3['종가_원']:,.0f}원 ({r3['종가_기준일']} 기준)",
              f"- 업종: {r3['업종명']}, {r3['업종_기준연도']}년 결산 실적 기준", "",
              "| 지표 | 회사(FY1 추정) | 업종 | 판정 |", "|---|---|---|---|"]
        for k in ("PER", "PBR"):
            p = r3[k]
            L.append(f"| {k} | {p['회사'] if p['회사'] is not None else '-'} | "
                     f"{p['업종'] if p['업종'] is not None else '-'} | {p['판정']} |")
        L += ["", "> 주의: FnGuide 무료 화면의 업종 PER·PBR은 **과거 결산 실적 기준**이다. "
              "회사 값(추정 실적)과 기준 시점이 달라, 이익이 늘어나는 해에는 회사가 싸게 보이기 쉽다.", "",
              f"출처 (외부 예외, 조회 {r3['조회시각']}):"]
        L += [f"- {u}" for u in r3["출처"]]
    else:
        L += [r3["사유"]]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", help="회사명 또는 종목코드")
    a = ap.parse_args()
    base = company_dir(a.company)
    code, name = base.name.split("_", 1)

    qpath = base / "dart" / "quarters.json"
    if not qpath.exists():
        die("quarters.json이 없습니다. dart_fetch.py를 먼저 실행하세요.")
    rows = read_json(qpath)
    urls = {r["rcept_no"]: r["url"] for r in read_json(base / "dart" / "reports.json")}
    oi = {(r["연도"], r["분기번호"]): r for r in rows if r["항목"] == "영업이익"}
    rev = {(r["연도"], r["분기번호"]): r for r in rows if r["항목"] == "매출액"}

    fg_files = sorted((base / "fnguide").glob("*.json")) if (base / "fnguide").exists() else []
    fg = read_json(fg_files[-1]) if fg_files else None

    r1, r2, r3 = criterion1(oi, urls), criterion2(rev, urls), criterion3(fg)
    today = date.today().isoformat()
    md = render(name, code, r1, r2, r3, today)
    out = base / "분석" / f"{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    write_json(out.with_suffix(".json"), {"기준1": r1, "기준2": r2, "기준3": r3})
    print(md)
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
