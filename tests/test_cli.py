"""CLI 冒烟测试:在进程内跑通 demo / plan / tools 命令,验证输出关键内容。"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_meal_planner.cli import main


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        main(argv)
    return buf.getvalue()


class TestCliDemo(unittest.TestCase):
    def test_demo_full_pipeline(self):
        out = run_cli(["demo"])
        self.assertIn("麦麦一周配餐计划", out)
        self.assertIn("一周汇总", out)
        self.assertIn("演示数据", out)
        self.assertIn("演示数据", out)
        self.assertIn("营养达成", out)

    def test_plan_without_token_falls_back_to_demo(self):
        out = run_cli(["plan", "--budget", "200"])
        self.assertIn("自动切换为演示数据", out)

    def test_today_command(self):
        out = run_cli(["today", "--budget", "40"])
        self.assertIn("今天吃麦当劳", out)

    def test_tools_demo_lists_official_tools(self):
        out = run_cli(["tools", "--demo"])
        self.assertIn("query-meals", out)
        self.assertIn("create-order", out)
        self.assertIn("共 33 个", out)

    def test_invalid_budget_exits_with_code_2(self):
        with self.assertRaises(SystemExit) as ctx:
            run_cli(["plan", "--budget", "abc"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
