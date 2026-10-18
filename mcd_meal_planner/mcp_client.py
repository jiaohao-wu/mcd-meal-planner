"""麦当劳 MCP Server 客户端(零第三方依赖)。

只使用 Python 标准库,通过 Streamable HTTP 协议调用麦当劳 MCP Server。

协议要点(来自官方文档 mcd-mcp-server 仓库与社区实测):
  1. POST https://mcp.mcd.cn,请求头携带 Authorization: Bearer <token>
  2. 响应可能是纯 JSON,也可能是 SSE 格式(以 "data: " 开头)
  3. 业务数据可能在 result.structuredContent 中,
     也可能混排在 result.content[0].text 里(说明文字 + 内嵌 JSON),
     需要把内嵌的 JSON 提取出来
  4. 部分请求(如 initialize)会返回 HTTP 202 空响应
  5. 限流:每个 Token 每分钟最多 600 次请求,超限返回 429

安全边界:本客户端只封装"查询类"工具的调用,
        绝不下单、不支付、不抽奖、不兑换积分。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_URL = "https://mcp.mcd.cn"
USER_AGENT = "mcd-meal-planner/1.0"


class MCPError(Exception):
    """MCP 调用通用错误。"""


class MCPAuthError(MCPError):
    """Token 无效或未提供(HTTP 401)。"""


class MCPRateLimitError(MCPError):
    """触发限流(HTTP 429)。"""


class MCPToolError(MCPError):
    """工具执行错误(isError=true 或 JSON-RPC error)。"""


def find_json_object(text: str) -> Optional[dict]:
    """从一段文本中提取第一个完整的 JSON 对象。

    能处理嵌套对象和字符串里的花括号,用于从
    "说明文字 {...业务 JSON...}" 这种混排文本中提取数据。
    找不到完整 JSON 时返回 None。
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class MCDClient:
    """麦当劳 MCP Server 客户端。"""

    def __init__(self, token: Optional[str] = None, url: str = DEFAULT_URL,
                 timeout: int = 25, debug: bool = False) -> None:
        self.token = token
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.debug = debug
        self._request_id = 0

    # ---------- 底层收发 ----------

    def _post(self, payload: dict) -> "tuple[int, str]":
        """发送一次 JSON-RPC POST,返回 (HTTP 状态码, 响应体文本)。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.url, data=body,
                                         headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
            if exc.code == 401:
                raise MCPAuthError("MCP Token 无效、已过期或未提供(HTTP 401)")
            if exc.code == 429:
                raise MCPRateLimitError("触发限流(HTTP 429,每 Token 每分钟 600 次)")
            raise MCPError("HTTP %d: %s" % (exc.code, raw[:200]))
        except urllib.error.URLError as exc:
            raise MCPError("网络错误: %s" % exc.reason)

    @staticmethod
    def parse_envelope(raw: str) -> Optional[dict]:
        """解析 JSON-RPC 响应信封,兼容 SSE 与纯 JSON;空响应返回 None。"""
        text = raw.strip()
        if not text:
            return None
        if text.startswith("data:"):
            # SSE 格式:去掉 data: 前缀,再提取 JSON
            text = text[len("data:"):].strip()
        return find_json_object(text)

    def _rpc(self, method: str, params: dict) -> dict:
        """发送一次 JSON-RPC 请求,返回 result 字段(可能是空 dict)。"""
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id,
                   "method": method, "params": params}
        if self.debug:
            print("[debug] >>> %s %s" % (method, json.dumps(params, ensure_ascii=False)[:300]))
        status, raw = self._post(payload)
        if self.debug:
            print("[debug] <<< HTTP %s %s" % (status, raw[:500]))
        envelope = self.parse_envelope(raw)
        if envelope is None:
            if status == 202:
                # 服务端已接收但无响应体(例如 initialize)
                return {}
            raise MCPError("无法解析响应(HTTP %s)" % status)
        if envelope.get("error"):
            err = envelope["error"]
            raise MCPToolError("MCP 错误 %s: %s" % (err.get("code"), err.get("message")))
        return envelope.get("result") or {}

    # ---------- 工具调用 ----------

    def call_tool(self, name: str, arguments: Optional[dict] = None,
                  retries: int = 2) -> dict:
        """调用一个 MCP 工具,返回业务数据(dict)。

        自动处理限流重试;业务数据按以下优先级提取:
        structuredContent > content[].text 中的内嵌 JSON > 纯文本。
        """
        result: Optional[Dict[str, Any]] = None
        for attempt in range(retries + 1):
            try:
                result = self._rpc("tools/call",
                                   {"name": name, "arguments": arguments or {}})
                break
            except MCPRateLimitError:
                # 只有限流才重试;其他错误(401/业务错误)直接抛出,不静默
                if attempt == retries:
                    raise
                time.sleep(1.5 * (attempt + 1))  # 简单退避后重试
        if result is None:
            raise MCPError("工具 %s 调用失败" % name)

        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", [])
                     if isinstance(c, dict)]
            raise MCPToolError("工具 %s 执行失败: %s" % (name, " ".join(texts)[:200]))

        business = extract_business_data(result)
        if business is not None:
            return business
        # 没有结构化数据时,把纯文本内容包一层返回,调用方自行处理
        texts = [c.get("text", "") for c in result.get("content", [])
                 if isinstance(c, dict)]
        if texts:
            return {"_text": "\n".join(texts)}
        return {}

    def list_tools(self) -> List[dict]:
        """列出 MCP Server 支持的全部工具(用于能力发现)。"""
        result = self._rpc("tools/list", {})
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def describe_tools(self) -> "dict[str, dict]":
        """返回 {工具名: 工具描述(含 inputSchema)} 的字典,失败时返回空字典。"""
        try:
            return {t.get("name"): t for t in self.list_tools() if isinstance(t, dict)}
        except MCPError:
            return {}


def extract_business_data(result: dict) -> Optional[dict]:
    """从 tools/call 的 result 中提取业务 JSON(dict)。找不到返回 None。"""
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and structured:
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                obj = find_json_object(item["text"])
                if isinstance(obj, dict):
                    return obj
    return None
