"""本地 Mock MCP Server。

复现麦当劳 MCP Server(mcp.mcd.cn)实测的行为,
让客户端逻辑可以在没有真实 Token 的情况下被完整测试:

  1. tools/list          -> 纯 JSON
  2. initialize          -> HTTP 202 空响应
  3. query-nearby-stores -> content 文本里嵌业务 JSON(含 businessStatus)
  4. query-meals         -> SSE 响应,业务 JSON 混排在说明文字里;
                            真实菜单只返回餐品编码(categories[].meals[].code)
  5. calculate-price     -> 纯 JSON content,批量返回 productList(名称+价格)
  6. query-store-coupons -> SSE,返回一张满 30 减 5 券
  7. list-nutrition-foods-> 特殊的"行数+表头+CSV"文本表格
  8. broken-tool         -> isError=true
  9. Token 错误          -> HTTP 401
 10. 路径 /limited       -> HTTP 429(限流)
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _text_result(req_id, text: str, sse: bool = False) -> str:
    """把一段文本包装成 MCP tools/call 的标准 result。"""
    payload = {"jsonrpc": "2.0", "id": req_id,
               "result": {"content": [{"type": "text", "text": text}]}}
    return _sse(payload) if sse else json.dumps(payload, ensure_ascii=False)


# mock 菜单:只有编码,名称和价格要靠 calculate-price 批量拿
_MOCK_MENU_CODES = ["m-1", "m-2", "m-3"]

# mock 算价表:按餐品编码返回名称和原价(分)
_MOCK_PRICES = {
    "m-1": ("巨无霸", 2550),
    "m-2": ("薯条(中)", 1300),
    "m-3": ("可乐(中)", 1000),
}


class MockMCPHandler(BaseHTTPRequestHandler):
    token = "good-token"

    def log_message(self, *args):  # 静音请求日志
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except ValueError:
            req = {}

        if self.path.startswith("/limited"):
            self._reply(429, json.dumps({"error": "rate limited"}))
            return

        auth = self.headers.get("Authorization", "")
        if self.token not in auth:
            self._reply(401, json.dumps({"error": "unauthorized"}))
            return

        method = req.get("method")
        if method == "tools/call":
            self._handle_tool_call(req)
        elif method == "tools/list":
            payload = {"jsonrpc": "2.0", "id": req.get("id"),
                       "result": {"tools": [
                           {"name": "query-nearby-stores", "description": "搜门店",
                            "inputSchema": {"type": "object", "properties": {},
                                            "required": ["beType", "searchType"]}},
                           {"name": "query-meals", "description": "查菜单",
                            "inputSchema": {"type": "object",
                                            "properties": {"storeCode": {"type": "string"}},
                                            "required": ["storeCode", "orderType", "beType"]}},
                           {"name": "calculate-price", "description": "算价",
                            "inputSchema": {"type": "object",
                                            "properties": {"storeCode": {"type": "string"},
                                                           "items": {"type": "array"}},
                                            "required": ["storeCode", "orderType", "beType"]}},
                           {"name": "query-store-coupons", "description": "门店券",
                            "inputSchema": {"type": "object",
                                            "properties": {"storeCode": {"type": "string"}},
                                            "required": ["storeCode", "orderType", "beType"]}},
                           {"name": "list-nutrition-foods", "description": "营养数据",
                            "inputSchema": {"type": "object", "properties": {}}}]}}
            self._reply(200, json.dumps(payload, ensure_ascii=False))
        elif method == "initialize":
            self._reply(202, "")  # 官方实测:202 空响应
        else:
            self._reply(200, json.dumps({"jsonrpc": "2.0", "id": req.get("id"),
                                         "result": {}}))

    def _handle_tool_call(self, req):
        name = req.get("params", {}).get("name")
        arguments = req.get("params", {}).get("arguments") or {}
        req_id = req.get("id")

        if name == "query-nearby-stores":
            # 真实响应:content 文本里嵌业务 JSON
            text = ('附近门店查询结果如下。\n{"success": true, "code": 200, '
                    '"data": [{"storeCode": "1950526", "storeName": "麦当劳测试餐厅", '
                    '"address": "测试地址 1 号", "businessStatus": true}, '
                    '{"storeCode": "1950999", "storeName": "麦当劳已打烊餐厅", '
                    '"address": "测试地址 2 号", "businessStatus": false}]}')
            self._reply(200, _text_result(req_id, text, sse=True),
                        content_type="text/event-stream")

        elif name == "query-meals":
            if not arguments.get("storeCode"):
                text = '{"success": false, "code": 400, "message": "缺少参数"}'
                self._reply(200, _text_result(req_id, text, sse=True),
                            content_type="text/event-stream")
                return
            # 真实菜单只返回餐品编码,名称/价格要另外批量算价
            text = ('# API Response Information\n菜单数据:{"success": true, "code": 200, '
                    '"data": {"categories": [{"name": "主食", "meals": ['
                    '{"code": "m-1"}, {"code": "m-2"}]}, '
                    '{"name": "饮品", "meals": [{"code": "m-3"}]}]}}')
            self._reply(200, _text_result(req_id, text, sse=True),
                        content_type="text/event-stream")

        elif name == "calculate-price":
            items = arguments.get("items") or []
            product_list = []
            original_total = 0
            for item in items:
                code = item.get("productCode")
                meal_name, cents = _MOCK_PRICES.get(code, (code, 0))
                original_total += cents * item.get("quantity", 1)
                product_list.append({"productCode": code, "productName": meal_name,
                                     "quantity": item.get("quantity", 1),
                                     "originalSubtotal": cents, "subtotal": cents})
            # mock 用券规则:任意商品带上 couponId 且原价满 3000 减 500
            # (与真实 calculate-price 的 couponId 语义一致)
            discount = 0
            coupon_id = next((i.get("couponId") for i in items if i.get("couponId")), None)
            if coupon_id and original_total >= 3000:
                discount = 500
            payload = {"jsonrpc": "2.0", "id": req_id,
                       "result": {"content": [{"type": "text", "text":
                                   json.dumps({"success": True, "code": 200,
                                               "originalPrice": original_total,
                                               "price": max(0, original_total - discount),
                                               "discount": discount,
                                               "productList": product_list},
                                              ensure_ascii=False)}]}}
            self._reply(200, json.dumps(payload, ensure_ascii=False))

        elif name == "query-store-coupons":
            text = ('{"success": true, "code": 200, "data": ['
                    '{"couponId": "c-1", "couponName": "满30减5", '
                    '"thresholdAmount": 3000, "discountAmount": 500}]}')
            self._reply(200, _text_result(req_id, text, sse=True),
                        content_type="text/event-stream")

        elif name == "list-nutrition-foods":
            # 真实形态:data 是"行数+表头+CSV 行"的文本,不是 JSON 数组
            # (表头列数与数据列数严格对齐,错位就会串列)
            text = ('{"success": true, "code": 200, "data": "[3]'
                    '{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\\n'
                    '  巨无霸,null,2217,531,27,29,43,930,180\\n'
                    '  薯条(中),null,1210,289,4,12,38,165,18\\n'
                    '  可乐(中),null,753,180,0,0,45,18,0"}')
            self._reply(200, _text_result(req_id, text))

        elif name == "broken-tool":
            payload = {"jsonrpc": "2.0", "id": req_id,
                       "result": {"isError": True,
                                  "content": [{"type": "text", "text": "门店不存在"}]}}
            self._reply(200, json.dumps(payload))

        else:
            payload = {"jsonrpc": "2.0", "id": req_id,
                       "error": {"code": -32601, "message": "unknown tool"}}
            self._reply(200, json.dumps(payload))

    def _reply(self, status: int, body: str, content_type: str = "application/json"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_mock_server(token: str = "good-token"):
    """启动 mock server,返回 (server 对象, base_url)。"""
    MockMCPHandler.token = token
    server = HTTPServer(("127.0.0.1", 0), MockMCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]
