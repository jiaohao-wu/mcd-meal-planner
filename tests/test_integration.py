"""端到端集成测试:CLI 真实模式 + 本地 mock MCP server。

验证完整链路:工具发现 -> 拉菜单 -> 拉券(部分来源不存在时降级)
-> 拉营养(不存在时降级)-> 本地配餐 -> calculate-price 真实算价校验。
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_meal_planner.cli import main
from tests.mock_server import start_mock_server


class TestRealModeAgainstMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base_url = start_mock_server()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(argv)
        return buf.getvalue()

    def test_plan_real_mode_full_chain(self):
        out = self.run_cli(["plan", "--budget", "200", "--days", "3",
                            "--token", "good-token", "--url", self.base_url,
                            "--store-id", "1950526"])
        self.assertIn("正在连接麦当劳 MCP Server", out)
        self.assertIn("工具发现", out)
        self.assertIn("使用指定门店", out)
        self.assertIn("菜单获取成功", out)
        self.assertIn("巨无霸", out)
        self.assertIn("已跳过该来源", out)        # mock 里缺 2 个券工具,应降级
        self.assertIn("营养数据:补充", out)        # mock 的文本表格营养数据应被解析
        self.assertIn("真实算价校验", out)
        self.assertIn("真实算价 ¥33.50", out)     # 巨无霸25.5+薯条13,用满30减5
        self.assertIn("安全提示", out)

    def test_auto_store_search(self):
        # 不传 --store-id 时应自动搜索门店并优先选营业中的
        out = self.run_cli(["plan", "--budget", "200", "--days", "1",
                            "--token", "good-token", "--url", self.base_url,
                            "--city", "测试市"])
        self.assertIn("正在搜索 测试市 附近的门店", out)
        self.assertIn("已选门店: 麦当劳测试餐厅", out)
        self.assertIn("菜单获取成功", out)


if __name__ == "__main__":
    unittest.main()
