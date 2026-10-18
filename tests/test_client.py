"""MCP 客户端测试:用本地 mock server 验证各种响应形态的解析。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_meal_planner.mcp_client import (MCDClient, MCPAuthError, MCPError,
                                         MCPRateLimitError, MCPToolError,
                                         find_json_object)
from tests.mock_server import start_mock_server


class TestEnvelopeParsing(unittest.TestCase):
    def test_pure_json(self):
        raw = '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
        env = MCDClient.parse_envelope(raw)
        self.assertEqual(env["result"], {"ok": True})

    def test_sse_prefix(self):
        raw = 'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        env = MCDClient.parse_envelope(raw)
        self.assertEqual(env["result"], {"ok": True})

    def test_empty_response(self):
        self.assertIsNone(MCDClient.parse_envelope(""))
        self.assertIsNone(MCDClient.parse_envelope("   "))

    def test_embedded_json_in_prose(self):
        text = '查询成功。{"success": true, "meals": [{"name": "巨无霸"}]} 完毕'
        obj = find_json_object(text)
        self.assertEqual(obj["success"], True)
        self.assertEqual(obj["meals"][0]["name"], "巨无霸")

    def test_nested_braces_and_strings(self):
        text = '前置 {"a": {"b": "带}括号的字符串"}, "c": 1} 后置'
        obj = find_json_object(text)
        self.assertEqual(obj, {"a": {"b": "带}括号的字符串"}, "c": 1})

    def test_incomplete_json_returns_none(self):
        self.assertIsNone(find_json_object('{"a": 1'))


class TestClientAgainstMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base_url = start_mock_server(token="good-token")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def make_client(self, **kwargs):
        kwargs.setdefault("token", "good-token")
        kwargs.setdefault("url", self.base_url)
        return MCDClient(**kwargs)

    def test_call_tool_extracts_embedded_json(self):
        client = self.make_client()
        data = client.call_tool("query-meals", {"storeCode": "1950526"})
        self.assertTrue(data["success"])
        # 真实菜单只返回餐品编码,名称/价格靠 calculate-price 批量拿
        meals = data["data"]["categories"][0]["meals"]
        self.assertEqual([m["code"] for m in meals], ["m-1", "m-2"])

    def test_call_tool_parses_batch_price(self):
        client = self.make_client()
        data = client.call_tool("calculate-price", {"storeCode": "1950526",
                                                    "items": [
                                                        {"productCode": "m-1", "quantity": 1},
                                                        {"productCode": "m-2", "quantity": 1}]})
        self.assertEqual(len(data["productList"]), 2)
        self.assertEqual(data["productList"][0]["productName"], "巨无霸")
        self.assertEqual(data["productList"][0]["originalSubtotal"], 2550)
        self.assertEqual(data["price"], 3850)

    def test_list_tools(self):
        client = self.make_client()
        tools = client.list_tools()
        self.assertEqual(len(tools), 5)
        self.assertIn("query-nearby-stores", [t["name"] for t in tools])

    def test_initialize_returns_empty_dict(self):
        client = self.make_client()
        result = client._rpc("initialize", {})
        self.assertEqual(result, {})

    def test_is_error_raises_tool_error(self):
        client = self.make_client()
        with self.assertRaises(MCPToolError):
            client.call_tool("broken-tool", {})

    def test_unknown_tool_raises_tool_error(self):
        client = self.make_client()
        with self.assertRaises(MCPToolError):
            client.call_tool("no-such-tool", {})

    def test_bad_token_raises_auth_error(self):
        client = self.make_client(token="wrong-token")
        with self.assertRaises(MCPAuthError):
            client.call_tool("query-meals", {})

    def test_rate_limit_raises(self):
        client = self.make_client(url=self.base_url + "/limited")
        with self.assertRaises(MCPRateLimitError):
            client._rpc("tools/list", {})


if __name__ == "__main__":
    unittest.main()
