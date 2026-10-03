"""analyze.py 판정 함수 테스트. 실행: py -m unittest discover -s .claude/skills/anal/scripts -p "test_*.py" """
import unittest

import analyze


def data(rev, op, ytd=((60, 50), (6, 5))):
    """rev, op: 3개 연도 값. ytd: ((누적 매출 당기, 전년동기), (누적 영업이익 당기, 전년동기)) 또는 None."""
    years = [{"연도": 2023 + i, "매출액": r, "영업이익": o} for i, (r, o) in enumerate(zip(rev, op))]
    cum = None
    if ytd is not None:
        (rc, rp), (oc, op_) = ytd
        cum = {"연도": 2026, "보고서": "반기보고서",
               "매출액": {"당기": rc, "전년동기": rp}, "영업이익": {"당기": oc, "전년동기": op_}}
    return {"연간": years, "올해누적": cum}


class Criterion1Test(unittest.TestCase):
    def test_c1_pass(self):
        self.assertEqual(analyze.criterion1(data([100, 110, 120], [10, 11, 12]))["판정"], "통과")

    def test_c1_equal_fails(self):
        r = analyze.criterion1(data([100, 100, 120], [10, 11, 12]))
        self.assertEqual(r["1-a"]["판정"], "탈락")
        self.assertEqual(r["판정"], "탈락")

    def test_c1_loss_shrinking(self):
        r = analyze.criterion1(data([100, 110, 120], [-100, -50, 30]))
        self.assertEqual(r["1-a"]["판정"], "통과")

    def test_c1_ytd_not_applicable(self):
        r = analyze.criterion1(data([100, 110, 120], [10, 11, 12], ytd=None))
        self.assertEqual(r["1-b"]["판정"], "해당 없음")
        self.assertEqual(r["판정"], "통과")

    def test_c1_ytd_fails(self):
        r = analyze.criterion1(data([100, 110, 120], [10, 11, 12], ytd=((50, 60), (6, 5))))
        self.assertEqual(r["1-b"]["판정"], "탈락")
        self.assertEqual(r["판정"], "탈락")

    def test_c1_missing_year(self):
        r = analyze.criterion1(data([None, 110, 120], [10, 11, 12]))
        self.assertEqual(r["1-a"]["판정"], "판정 불가")
        self.assertEqual(r["1-b"]["판정"], "통과")
        self.assertEqual(r["판정"], "판정 불가")

    def test_c1_fail_beats_unknown(self):
        r = analyze.criterion1(data([100, 90, 120], [10, 11, 12], ytd=((None, 50), (6, 5))))
        self.assertEqual(r["1-b"]["판정"], "판정 불가")
        self.assertEqual(r["판정"], "탈락")


class Criterion2Test(unittest.TestCase):
    def test_c2_pass_equal(self):
        r = analyze.criterion2(data([100, 200, 100], [10, 20, 12]))
        self.assertEqual([y["값"] for y in r["영업이익률"]], [10.0, 10.0, 12.0])
        self.assertEqual(r["판정"], "통과")

    def test_c2_equal_after_rounding(self):
        r = analyze.criterion2(data([100000, 300000, 100000], [10000, 30001, 12000]))
        self.assertEqual(r["판정"], "통과")

    def test_c2_drop_fails(self):
        r = analyze.criterion2(data([100, 10000, 10000], [10, 999, 2000]))
        self.assertEqual(r["판정"], "탈락")

    def test_c2_negative_margin(self):
        r = analyze.criterion2(data([69184238320, 95650538591, 82379163292],
                                    [-5608802365, 8017318466, 17391515095]))
        self.assertEqual([y["값"] for y in r["영업이익률"]], [-8.11, 8.38, 21.11])
        self.assertEqual(r["판정"], "통과")

    def test_c2_zero_revenue(self):
        self.assertEqual(analyze.criterion2(data([0, 100, 120], [1, 10, 12]))["판정"], "판정 불가")


class MarginTest(unittest.TestCase):
    def test_margin(self):
        self.assertEqual(analyze.margin(82379163292, 17391515095), 21.11)
        self.assertIsNone(analyze.margin(0, 5))
        self.assertIsNone(analyze.margin(None, 5))


if __name__ == "__main__":
    unittest.main()
