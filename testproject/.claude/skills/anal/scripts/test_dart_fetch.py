"""dart_fetch.py의 순수 함수 테스트. 실행: py -m unittest discover -s .claude/skills/anal/scripts -p "test_*.py" """
import unittest

import dart_fetch


def rep(year, code):
    return {"year": year, "reprt_code": code}


class SelectReportsTest(unittest.TestCase):
    def test_select_reports_half_year(self):
        reps = [rep(2026, "11012"), rep(2026, "11013"), rep(2025, "11011"), rep(2025, "11014")]
        annual, ytd = dart_fetch.select_reports(reps)
        self.assertEqual(annual, rep(2025, "11011"))
        self.assertEqual(ytd, rep(2026, "11012"))

    def test_select_reports_annual_latest(self):
        annual, ytd = dart_fetch.select_reports([rep(2025, "11011"), rep(2025, "11014")])
        self.assertEqual(annual, rep(2025, "11011"))
        self.assertIsNone(ytd)

    def test_select_reports_no_annual(self):
        annual, ytd = dart_fetch.select_reports([rep(2026, "11013")])
        self.assertIsNone(annual)
        self.assertEqual(ytd, rep(2026, "11013"))


def fin(year, report, rows):
    return {"year": year, "report": report, "rcept_no": f"R{year}", "url": f"U{year}",
            "fs_div": "CFS", "list": rows}


def row(account_id, name, **amounts):
    return {"sj_div": "CIS", "account_id": account_id, "account_nm": name, **amounts}


ANNUAL_2025 = fin(2025, "사업보고서", [
    row("ifrs-full_Revenue", "수익(매출액)", bfefrmtrm_amount="95650538591",
        frmtrm_amount="69184238320", thstrm_amount="82379163292"),
    row("dart_OperatingIncomeLoss", "영업이익(손실)", bfefrmtrm_amount="8017318466",
        frmtrm_amount="-5608802365", thstrm_amount="17391515095"),
])
HALF_2026 = fin(2026, "반기보고서", [
    row("ifrs-full_Revenue", "수익", thstrm_amount="18555106001",
        thstrm_add_amount="31184245863", frmtrm_q_amount="17073864677",
        frmtrm_add_amount="35893769749"),
    row("dart_OperatingIncomeLoss", "영업이익(손실)", thstrm_amount="5730276924",
        thstrm_add_amount="7188199287", frmtrm_q_amount="6858158688",
        frmtrm_add_amount="10805584145"),
])


class BuildAnnualTest(unittest.TestCase):
    def test_build_annual_full(self):
        d = dart_fetch.build_annual(ANNUAL_2025, HALF_2026)
        self.assertEqual(d["재무제표"], "연결")
        self.assertEqual(d["연간"], [
            {"연도": 2023, "매출액": 95650538591, "영업이익": 8017318466},
            {"연도": 2024, "매출액": 69184238320, "영업이익": -5608802365},
            {"연도": 2025, "매출액": 82379163292, "영업이익": 17391515095},
        ])
        self.assertEqual(d["연간_근거"]["접수번호"], "R2025")
        self.assertEqual(d["올해누적"]["연도"], 2026)
        self.assertEqual(d["올해누적"]["매출액"], {"당기": 31184245863, "전년동기": 35893769749})
        self.assertEqual(d["올해누적"]["영업이익"], {"당기": 7188199287, "전년동기": 10805584145})

    def test_build_annual_q1_fallback(self):
        q1 = fin(2026, "1분기보고서", [
            row("ifrs-full_Revenue", "수익(매출액)", thstrm_amount="12629139862",
                thstrm_add_amount="", frmtrm_q_amount="18819905072", frmtrm_add_amount=""),
            row("dart_OperatingIncomeLoss", "영업이익(손실)", thstrm_amount="1457922363",
                thstrm_add_amount="", frmtrm_q_amount="3947425457", frmtrm_add_amount=""),
        ])
        q1["reprt_code"] = "11013"
        d = dart_fetch.build_annual(ANNUAL_2025, q1)
        self.assertEqual(d["올해누적"]["매출액"], {"당기": 12629139862, "전년동기": 18819905072})
        self.assertIn("thstrm_amount", d["올해누적"]["근거"]["필드"])

    def test_build_annual_missing_year(self):
        f = fin(2025, "사업보고서", [
            row("ifrs-full_Revenue", "수익(매출액)", frmtrm_amount="10", thstrm_amount="20"),
            row("dart_OperatingIncomeLoss", "영업이익(손실)", frmtrm_amount="1", thstrm_amount="2"),
        ])
        d = dart_fetch.build_annual(f, None)
        self.assertIsNone(d["연간"][0]["매출액"])
        self.assertEqual(d["연간"][2]["매출액"], 20)
        self.assertIsNone(d["올해누적"])

    def test_build_annual_account_not_found(self):
        f = fin(2025, "사업보고서", [row("x", "이자수익", thstrm_amount="5")])
        d = dart_fetch.build_annual(f, None)
        self.assertEqual([y["매출액"] for y in d["연간"]], [None, None, None])
        self.assertEqual([y["영업이익"] for y in d["연간"]], [None, None, None])

    def test_build_annual_ytd_fin_missing(self):
        """올해 보고서는 있으나 재무 데이터를 받지 못하면 1-b가 '해당 없음'이 아니라 값 없음이어야 한다."""
        rep = {"year": 2026, "report": "반기보고서", "rcept_no": "R2026", "url": "U2026"}
        d = dart_fetch.build_annual(ANNUAL_2025, None, rep)
        self.assertIsNotNone(d["올해누적"])
        self.assertEqual(d["올해누적"]["연도"], 2026)
        self.assertEqual(d["올해누적"]["매출액"], {"당기": None, "전년동기": None})
        self.assertEqual(d["올해누적"]["근거"]["접수번호"], "R2026")

    def test_build_annual_mixed_fields_none(self):
        """반기 누적 당기와 전년 3개월을 섞어 비교하지 않는다."""
        half = fin(2026, "반기보고서", [
            row("ifrs-full_Revenue", "수익", thstrm_amount="10", thstrm_add_amount="30",
                frmtrm_q_amount="9", frmtrm_add_amount=""),
            row("dart_OperatingIncomeLoss", "영업이익(손실)", thstrm_amount="1",
                thstrm_add_amount="3", frmtrm_q_amount="1", frmtrm_add_amount="2"),
        ])
        half["reprt_code"] = "11012"
        d = dart_fetch.build_annual(ANNUAL_2025, half)
        self.assertEqual(d["올해누적"]["매출액"], {"당기": None, "전년동기": None})
        self.assertEqual(d["올해누적"]["영업이익"], {"당기": 3, "전년동기": 2})

    def test_build_annual_no_reports(self):
        self.assertEqual(dart_fetch.build_annual(None, None),
                         {"재무제표": None, "연간": [], "연간_근거": None, "올해누적": None})


if __name__ == "__main__":
    unittest.main()
