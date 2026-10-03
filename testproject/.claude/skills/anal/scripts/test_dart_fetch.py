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


if __name__ == "__main__":
    unittest.main()
