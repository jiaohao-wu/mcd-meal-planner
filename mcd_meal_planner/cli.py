"""命令行入口:plan(一周配餐) / today(今天吃什么) / tools(工具清单) / demo(离线演示)。

真实模式需要 MCP Token(open.mcd.cn/mcp 手机号登录免费领取),
可以通过 --token 传入,或设置环境变量 MCD_TOKEN。
任何查询失败都会自动降级并给出中文提示,不会静默出错。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

# 让 Windows 控制台也能正确输出中文
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from .demo_data import (DEMO_COUPONS, DEMO_MEALS, DEMO_STORE,
                        DEMO_TOOLS_OVERVIEW)
from .mcp_client import MCDClient, MCPError
from .planner import (CATEGORY_LABELS, DEFAULT_KCAL_RANGE, Coupon, DayPlan,
                      Meal, WeekPlan, build_day, build_week_plan,
                      coupons_from_mcp_payload, meals_from_mcp_payload)

# calculate-price 响应里"应付金额"可能的键名(按优先级)
_PAID_KEYS = ("actualPrice", "payAmount", "paidAmount", "finalPrice",
              "totalPrice", "totalFee", "price", "productPrice",
              "amount", "total")

# 按 inputSchema 组装参数时的别名表(键为小写字段名片段,值为内部值名)
_ARG_ALIASES = {
    "storeid": "store_id", "storecode": "store_id", "store": "store_id",
    "mealcode": "meal_codes", "productcode": "meal_codes", "code": "meal_codes",
    "meallist": "meal_codes", "productlist": "meal_codes", "products": "meal_codes",
    "couponid": "coupon_ids", "couponcode": "coupon_ids", "couponlist": "coupon_ids",
    "coupons": "coupon_ids", "quantity": "quantities",
}


# -----------------------------------------------------------
# 输出辅助(处理中英文混排对齐)
# -----------------------------------------------------------

def _disp_width(text: str) -> int:
    """字符串显示宽度:中文等宽字符按 2 计算。"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def _pad(text: str, width: int, align: str = "left") -> str:
    text = str(text)
    gap = max(0, width - _disp_width(text))
    return text + " " * gap if align == "left" else " " * gap + text


def money(cents: int) -> str:
    """分 -> '¥25.50'。"""
    return "¥%.2f" % (cents / 100.0)


def yuan_to_cents(yuan: float) -> int:
    return int(round(yuan * 100))


# -----------------------------------------------------------
# 真实模式:从 MCP 拉取数据(每步都可降级)
# -----------------------------------------------------------

def resolve_store(client: MCDClient, city: str,
                  keyword: str = "麦当劳") -> Tuple[str, str]:
    """按城市搜索门店,返回 (storeCode, 门店名)。

    优先返回营业中的门店;全部打烊时返回第一家并给出提示。
    官方 query-nearby-stores 要求 city 和 keyword 必须同时传。
    """
    payload = client.call_tool("query-nearby-stores",
                               {"beType": 1, "searchType": 2,
                                "city": city, "keyword": keyword})
    lists: List[list] = []
    from .planner import _find_dict_lists
    _find_dict_lists(payload, lists)
    stores = [item for group in lists for item in group
              if item.get("storeCode") or item.get("storecode")]
    if not stores:
        raise MCPError("城市「%s」没搜到门店,换个城市试试(--city 广州)" % city)
    open_stores = [s for s in stores if s.get("businessStatus")]
    chosen = open_stores[0] if open_stores else stores[0]
    name = chosen.get("storeName") or chosen.get("storeName".lower()) or chosen.get("name") or "未知门店"
    if not open_stores:
        print("  [提示] %s 的门店当前都不在营业时间,已选第一家:%s" % (city, name))
    return str(chosen.get("storeCode") or chosen.get("storecode")), str(name)


def _extract_meal_codes(payload) -> List[str]:
    """从 query-meals 响应里提取去重后的餐品编码(保持出现顺序)。"""
    codes: List[str] = []
    seen = set()

    def walk(obj):
        if isinstance(obj, dict):
            code = obj.get("code") or obj.get("mealCode") or obj.get("productCode")
            if code and isinstance(code, str) and code not in seen:
                seen.add(code)
                codes.append(code)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(payload)
    return codes


def fetch_meals(client: MCDClient, store_code: str,
                batch_size: int = 20) -> List[Meal]:
    """两步拿菜单:query-meals 取餐品编码,再批量 calculate-price 取名称和价格。

    官方菜单接口只返回餐品编码,价格要用算价接口逐批查询;
    批量传 20 个一批,兼顾限流与效率(实测每批都会全部返回)。
    """
    menu_payload = client.call_tool("query-meals",
                                    {"storeCode": store_code,
                                     "orderType": 1, "beType": 1})
    if isinstance(menu_payload, dict) and menu_payload.get("success") is False:
        raise MCPError("query-meals 被拒绝:%s" % menu_payload.get("message"))
    codes = _extract_meal_codes(menu_payload)
    if not codes:
        raise MCPError("query-meals 响应里没有解析出餐品编码。"
                       "请加 --debug 查看原始响应,或换一家门店。")

    meals: List[Meal] = []
    seen = set()
    for start in range(0, len(codes), batch_size):
        batch = codes[start:start + batch_size]
        price_payload = client.call_tool(
            "calculate-price",
            {"storeCode": store_code, "orderType": 1, "beType": 1,
             "items": [{"productCode": code, "quantity": 1} for code in batch]})
        if isinstance(price_payload, dict) and price_payload.get("success") is False:
            print("  [提示] 第 %d 批算价失败(%s),跳过"
                  % (start // batch_size + 1, price_payload.get("message")))
            continue
        for meal in meals_from_mcp_payload(price_payload):
            if (meal.name, meal.price_cents) in seen:
                continue
            seen.add((meal.name, meal.price_cents))
            meals.append(meal)
    if not meals:
        raise MCPError("算价接口没有返回任何餐品价格,请加 --debug 查看原始响应。")
    return meals


def fetch_coupons(client: MCDClient, store_code: str) -> List[Coupon]:
    """合并多个券来源,按 coupon_id 去重。单个来源失败不影响其他来源。"""
    merged = {}
    sources = [
        ("query-store-coupons",
         {"storeCode": store_code, "orderType": 1, "beType": 1}),
        ("query-my-coupons", {}),
        ("available-coupons", {}),
    ]
    for name, arguments in sources:
        try:
            payload = client.call_tool(name, arguments)
        except MCPError as exc:
            print("  [提示] %s 调用失败(%s),已跳过该来源" % (name, exc))
            continue
        for coupon in coupons_from_mcp_payload(payload):
            merged.setdefault(coupon.coupon_id, coupon)
    return list(merged.values())


def _parse_nutrition_text(payload) -> List[dict]:
    """解析 list-nutrition-foods 的特殊文本表格响应。

    官方返回形如:
      data: "[160]{productName,energyKcal,protein,...}:\\n  猪柳麦满分,null,308,16,..."
    即 data 不是 JSON 数组,而是一段"行数+表头+CSV 行"的文本。
    这里把表头后面的每一行解析成字典,表头没有的列按 colN 命名。
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, str):
        return []

    # 1. 找表头: [160]{productName,energyKcal,...}:
    match = re.search(r"\{\s*([^}]*?)\s*\}:", data)
    if not match:
        return []
    headers = [h.strip() for h in match.group(1).split(",") if h.strip()]

    # 2. 表头之后的每一行按逗号切分
    items: List[dict] = []
    for line in data[match.end():].splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        values = [v.strip() for v in line.split(",")]
        if len(values) < 2:
            continue
        item = {}
        for i, value in enumerate(values):
            key = headers[i] if i < len(headers) else "col%d" % i
            item[key] = None if value in ("null", "") else value
        if item.get("productName"):
            items.append(item)
    return items


def fetch_nutrition(client: MCDClient) -> List[dict]:
    """拉取营养数据(list-nutrition-foods),失败返回空列表(营养维度降级)。"""
    try:
        payload = client.call_tool("list-nutrition-foods", {})
    except MCPError as exc:
        print("  [提示] 营养数据获取失败(%s),营养维度将降级" % exc)
        return []
    items = _parse_nutrition_text(payload)
    if not items:
        # 兜底:万一官方改回标准 JSON 结构,仍按旧路径尝试
        lists = []
        from .planner import _find_dict_lists
        _find_dict_lists(payload, lists)
        items = [item for group in lists for item in group]
    return items


def merge_nutrition(meals: List[Meal], nutrition_items: List[dict]) -> int:
    """把营养数据按餐品名模糊匹配合并进 meals,返回补充了几条。"""
    def norm(text: str) -> str:
        return "".join(ch for ch in str(text) if ch.isalnum())

    filled = 0
    for meal in meals:
        if meal.kcal and meal.protein_g:
            continue
        meal_key = norm(meal.name)
        for item in nutrition_items:
            name = (item.get("productName") or item.get("foodName")
                    or item.get("name") or item.get("food") or "")
            if norm(name) and (norm(name) in meal_key or meal_key in norm(name)):
                kcal = item.get("energy") or item.get("kcal") or item.get("energyKcal")
                protein = item.get("protein") or item.get("proteinG")
                try:
                    if kcal and not meal.kcal:
                        meal.kcal = int(float(kcal))
                    if protein and not meal.protein_g:
                        meal.protein_g = float(protein)
                    filled += 1
                except (TypeError, ValueError):
                    pass
                break
    return filled


def _build_args_from_schema(schema: dict, values: dict) -> Tuple[dict, List[str]]:
    """按工具的 inputSchema 必填字段,用别名表组装调用参数。

    官方未文档化各工具的参数结构,这里做"schema 自适应"组装;
    有填不上的必填字段时返回 missing,调用方应降级处理。
    """
    if not isinstance(schema, dict):
        return {}, ["<无 schema>"]
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    arguments = {}
    missing = []
    for field_name in required:
        prop = properties.get(field_name) or {}
        lowered = field_name.lower()
        value_key = None
        for alias, key in _ARG_ALIASES.items():
            if alias in lowered:
                value_key = key
                break
        if value_key and values.get(value_key):
            arguments[field_name] = values[value_key]
        elif isinstance(prop.get("default"), (str, int, float)):
            arguments[field_name] = prop["default"]
        else:
            missing.append(field_name)
    return arguments, missing


def _extract_paid_cents(payload) -> Optional[int]:
    """从 calculate-price 响应里递归找"应付金额",单位用分(启发式)。"""
    from .planner import _to_cents
    best = None
    best_rank = 99

    def walk(obj):
        nonlocal best, best_rank
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (int, float, str)) and key in _PAID_KEYS:
                    rank = _PAID_KEYS.index(key)
                    cents = _to_cents(value, key)
                    if cents > 0 and rank < best_rank:
                        best, best_rank = cents, rank
                else:
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return best


def verify_prices_with_mcp(client: MCDClient, plan: WeekPlan,
                           tools_map: dict, store_code: Optional[str]) -> List[str]:
    """用 calculate-price 对每天的真实实付做校验(尽力而为)。

    返回报告行列表;调用失败时只返回提示,不影响主流程。
    """
    report: List[str] = []
    for day in plan.days:
        if not store_code:
            report.append("第%d顿: 未指定门店,跳过校验" % day.day_index)
            continue
        items = []
        for meal in day.items:
            item = {"productCode": meal.code, "quantity": 1}
            if day.coupon:
                item["couponId"] = day.coupon.coupon_id
            items.append(item)
        try:
            payload = client.call_tool(
                "calculate-price",
                {"storeCode": store_code, "orderType": 1, "beType": 1,
                 "items": items})
        except MCPError as exc:
            report.append("第%d顿: calculate-price 调用失败(%s),跳过校验"
                          % (day.day_index, exc))
            continue
        real_paid = _extract_paid_cents(payload)
        if real_paid is None:
            report.append("第%d顿: 响应中未找到应付金额字段,跳过校验" % day.day_index)
            continue
        diff = real_paid - day.paid_cents
        if abs(diff) <= 1:
            report.append("第%d顿: 真实算价 %s,与本地估算一致" % (day.day_index, money(real_paid)))
        else:
            report.append("第%d顿: 真实算价 %s,本地估算 %s(差 %s),请以官方实时价格为准"
                          % (day.day_index, money(real_paid), money(day.paid_cents),
                             money(abs(diff))))
    return report


# -----------------------------------------------------------
# 输出:配餐计划
# -----------------------------------------------------------

def print_day(day: DayPlan, kcal_range: Tuple[int, int]) -> None:
    print("第 %d 顿" % day.day_index)
    for meal in day.items:
        kcal_text = "%6s" % meal.kcal if meal.kcal else "  暂无"
        protein_text = "%4.1f g" % meal.protein_g if meal.kcal else " 暂无"
        print("  %s %s %s kcal  蛋白 %s" % (
            _pad(meal.name, 16), _pad(CATEGORY_LABELS.get(meal.category, meal.category), 4),
            kcal_text, protein_text))
    coupon_text = "用券[%s]" % day.coupon.name if day.coupon else "无可用券"
    print("  原价小计 %s | %s | 实付 %s" % (
        _pad(money(day.original_cents), 10),
        _pad(coupon_text, 24),
        money(day.paid_cents)))
    if day.note:
        print("  备注: %s" % day.note)
    print("")


def print_plan(plan: WeekPlan, title: str, store_name: Optional[str] = None,
               is_demo: bool = False, verify_report: Optional[List[str]] = None) -> None:
    bar = "=" * 60
    print(bar)
    print(title)
    if store_name:
        print("门店: %s" % store_name)
    print("总预算 %s | %d 顿 | 日均 %s | 每顿热量目标 %d-%d kcal"
          % (money(plan.budget_cents), len(plan.days),
             money(plan.daily_budget_cents),
             plan.kcal_range[0], plan.kcal_range[1]))
    print(bar)
    for day in plan.days:
        print_day(day, plan.kcal_range)
    print("-" * 60)
    saved_pct = (plan.total_saved_cents / plan.total_original_cents * 100
                 if plan.total_original_cents else 0.0)
    print("一周汇总: 原价 %s -> 券后 %s,共节省 %s(%.1f%%)"
          % (money(plan.total_original_cents), money(plan.total_paid_cents),
             money(plan.total_saved_cents), saved_pct))
    print("预算执行: %s / %s%s"
          % (money(plan.total_paid_cents), money(plan.budget_cents),
             "" if plan.total_paid_cents <= plan.budget_cents else " (已超支,请上调预算)"))
    print("营养达成: %d/%d 顿热量在目标区间" % (plan.in_range_days, len(plan.days)))
    unknown = sum(1 for d in plan.days for m in d.items if m.kcal <= 0)
    if unknown:
        print("         (其中 %d 个餐品是刚上线新品,官方营养表暂无数据,按 0 计)" % unknown)
    if verify_report:
        print("-" * 60)
        print("真实算价校验(calculate-price):")
        for line in verify_report:
            print("  %s" % line)
    print(bar)
    if is_demo:
        print("以上为【演示数据】,价格与优惠券均为近似示例,不代表麦当劳实时价格。")
        print("申请 MCP Token(open.mcd.cn/mcp,手机号免费登录)后即可使用真实菜单与真实算价。")
    else:
        print("安全提示:本项目仅调用查询类工具,不会下单、支付或抽奖;")
        print("        餐品供应、价格与优惠以麦当劳官方渠道实时结果为准。")


# -----------------------------------------------------------
# 子命令实现
# -----------------------------------------------------------

def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--token", default=os.environ.get("MCD_TOKEN"),
                        help="麦当劳 MCP Token(也可用环境变量 MCD_TOKEN)")
    parser.add_argument("--url", default="https://mcp.mcd.cn", help="MCP Server 地址")
    parser.add_argument("--store-id", default=None,
                        help="门店编码(storeCode);不传则按 --city 自动搜索")
    parser.add_argument("--city", default="上海市",
                        help="自动搜门店时使用的城市名(默认 上海市)")
    parser.add_argument("--debug", action="store_true", help="打印原始请求/响应")


def _load_data(args) -> dict:
    """加载菜单与优惠券数据。

    返回一个字典,包含:
      meals       菜单(Meal 列表)
      coupons     优惠券(Coupon 列表)
      store_name  门店展示名
      is_demo     是否为演示数据
      client      MCDClient 实例(演示模式下为 None)
      tools_map   MCP 工具清单(演示模式下为空字典)
      store_code  门店编码(演示模式下为 None)
    """
    if args.demo or not args.token:
        if not args.demo:
            print("未检测到 MCP Token,自动切换为演示数据。")
            print("真实数据:打开 open.mcd.cn/mcp,手机号登录后在控制台点\"激活\"免费领取。\n")
        return {"meals": list(DEMO_MEALS), "coupons": list(DEMO_COUPONS),
                "store_name": DEMO_STORE["name"], "is_demo": True,
                "client": None, "tools_map": {}, "store_code": None}

    client = MCDClient(token=args.token, url=args.url, debug=args.debug)
    print("正在连接麦当劳 MCP Server(%s)..." % args.url)
    tools_map = client.describe_tools()
    if tools_map:
        needed = ["query-meals", "query-store-coupons", "available-coupons",
                  "query-my-coupons", "list-nutrition-foods", "calculate-price",
                  "query-nearby-stores"]
        missing = [name for name in needed if name not in tools_map]
        if missing:
            print("工具发现:共 %d 个工具;缺少 %s(相关功能自动降级)"
                  % (len(tools_map), ", ".join(missing)))
        else:
            print("工具发现:共 %d 个工具,核心工具全部可用" % len(tools_map))
    else:
        print("[提示] 未能获取工具列表,将按文档假定工具名继续调用")
        tools_map = {}

    # 1. 确定门店:显式传入的优先,否则按城市自动搜(优先营业中的)
    if args.store_id:
        store_code, store_name = str(args.store_id), "门店 %s" % args.store_id
        print("使用指定门店: %s" % store_name)
    else:
        print("未指定门店,正在搜索 %s 附近的门店..." % args.city)
        store_code, store_name = resolve_store(client, args.city)
        print("已选门店: %s(%s)" % (store_name, store_code))

    # 2. 菜单:query-meals 拿编码 -> calculate-price 批量拿名称和价格
    meals = fetch_meals(client, store_code)
    print("菜单获取成功: %d 个餐品" % len(meals))

    # 3. 优惠券:门店券 + 我的卡包 + 可领券,合并去重
    coupons = fetch_coupons(client, store_code)
    print("优惠券获取成功: %d 张(已合并多个来源并去重)" % len(coupons))

    # 4. 营养数据(可选,失败自动降级)
    nutrition_items = fetch_nutrition(client)
    if nutrition_items:
        filled = merge_nutrition(meals, nutrition_items)
        print("营养数据:补充 %d 个餐品的营养信息" % filled)

    return {"meals": meals, "coupons": coupons, "store_name": store_name,
            "is_demo": False, "client": client, "tools_map": tools_map,
            "store_code": store_code}


def cmd_plan(args: argparse.Namespace) -> None:
    data = _load_data(args)
    plan = build_week_plan(data["meals"], data["coupons"],
                           yuan_to_cents(args.budget),
                           days=args.days, want_drink=not args.no_drink,
                           kcal_range=(args.kcal_min, args.kcal_max))
    verify_report: List[str] = []
    if not data["is_demo"]:
        verify_report = verify_prices_with_mcp(data["client"], plan,
                                               data["tools_map"],
                                               data["store_code"])
    print_plan(plan, "麦麦一周配餐计划(共 %d 顿)" % args.days,
               store_name=data["store_name"], is_demo=data["is_demo"],
               verify_report=verify_report)


def cmd_today(args: argparse.Namespace) -> None:
    data = _load_data(args)
    pools = {}
    for meal in data["meals"]:
        pools.setdefault(meal.category, []).append(meal)
    day = build_day(1, yuan_to_cents(args.budget), pools, data["coupons"], set(),
                    want_drink=not args.no_drink,
                    kcal_range=(args.kcal_min, args.kcal_max))
    plan = WeekPlan(budget_cents=yuan_to_cents(args.budget),
                    daily_budget_cents=yuan_to_cents(args.budget), days=[day],
                    kcal_range=(args.kcal_min, args.kcal_max))
    print_plan(plan, "今天吃麦当劳:一顿 %s 的搭配" % money(yuan_to_cents(args.budget)),
               store_name=data["store_name"], is_demo=data["is_demo"])


def cmd_tools(args: argparse.Namespace) -> None:
    if args.demo or not args.token:
        if not args.demo:
            print("未检测到 MCP Token,展示官方文档中的工具清单(离线)。\n")
        print("麦当劳 MCP 官方工具清单(来自 M-China/mcd-mcp-server,共 %d 个):"
              % len(DEMO_TOOLS_OVERVIEW))
        for name, desc in DEMO_TOOLS_OVERVIEW:
            print("  %-26s %s" % (name, desc))
        print("\n本项目的安全边界:只调用查询类工具,不碰下单/支付/抽奖/兑换。")
        return
    client = MCDClient(token=args.token, url=args.url, debug=args.debug)
    tools = client.list_tools()
    if not tools:
        print("未获取到工具列表。")
        return
    print("麦当劳 MCP 在线工具清单(共 %d 个):" % len(tools))
    for tool in tools:
        print("  %-26s %s" % (tool.get("name", "?"),
                              (tool.get("description") or "").split("\n")[0][:60]))


def cmd_demo(args: argparse.Namespace) -> None:
    """离线演示:用内置示例数据完整跑一遍配餐流程(无需 Token)。"""
    args.demo = True
    args.budget = 280.0
    args.days = 7
    args.no_drink = False
    args.kcal_min, args.kcal_max = DEFAULT_KCAL_RANGE
    args.store_id = None
    args.city = None
    args.token = None
    cmd_plan(args)


# -----------------------------------------------------------
# 参数解析
# -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcd-meal-planner",
        description="麦麦一周配餐师:基于麦当劳 MCP,在预算内规划一周不重样、"
                    "营养达标的麦当劳餐食(只查询,不下单)。")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="生成一周配餐计划")
    p_plan.add_argument("--budget", type=float, required=True, help="一周预算(元)")
    p_plan.add_argument("--days", type=int, default=7, help="规划几顿(默认 7)")
    p_plan.add_argument("--no-drink", action="store_true", help="不要饮品")
    p_plan.add_argument("--kcal-min", type=int, default=DEFAULT_KCAL_RANGE[0],
                        help="每顿热量下限(默认 %d)" % DEFAULT_KCAL_RANGE[0])
    p_plan.add_argument("--kcal-max", type=int, default=DEFAULT_KCAL_RANGE[1],
                        help="每顿热量上限(默认 %d)" % DEFAULT_KCAL_RANGE[1])
    p_plan.add_argument("--demo", action="store_true", help="强制使用演示数据")
    _add_common_args(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_today = sub.add_parser("today", help="今天吃什么(单顿推荐)")
    p_today.add_argument("--budget", type=float, required=True, help="本顿预算(元)")
    p_today.add_argument("--no-drink", action="store_true", help="不要饮品")
    p_today.add_argument("--kcal-min", type=int, default=DEFAULT_KCAL_RANGE[0])
    p_today.add_argument("--kcal-max", type=int, default=DEFAULT_KCAL_RANGE[1])
    p_today.add_argument("--demo", action="store_true", help="强制使用演示数据")
    _add_common_args(p_today)
    p_today.set_defaults(func=cmd_today)

    p_tools = sub.add_parser("tools", help="列出麦当劳 MCP 工具清单")
    p_tools.add_argument("--demo", action="store_true", help="展示离线文档版清单")
    _add_common_args(p_tools)
    p_tools.set_defaults(func=cmd_tools)

    p_demo = sub.add_parser("demo", help="离线演示(无需 Token,预算 ¥200/7 顿)")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except MCPError as exc:
        print("\n[MCP 错误] %s" % exc)
        print("可以先用 `python main.py demo` 体验离线演示;")
        print("Token 问题请到 open.mcd.cn/mcp 用手机号登录后在控制台点\"激活\"。")
        sys.exit(1)
    except ValueError as exc:
        print("\n[参数错误] %s" % exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
