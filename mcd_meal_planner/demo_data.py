"""内置演示数据(与真实麦当劳 MCP 无关,仅用于无 Token 时离线体验)。

注意:餐品名称参考了麦当劳中国常见菜单,价格/营养为近似示例值,
      不代表实时价格;优惠券为虚构示例。真实数据请申请 MCP Token 后
      在 open.mcd.cn/mcp 控制台获取。
"""
from __future__ import annotations

from .planner import Coupon, Meal

DEMO_STORE = {
    "storeId": "1950526",
    "name": "北京新东安二号餐厅(示例门店)",
}

# 分类说明:main=主食, snack=小食, drink=饮品, dessert=甜品
# 价格单位为"分"(与麦当劳 calculate-price 接口一致),kcal/蛋白为近似值
DEMO_MEALS = [
    Meal("m-1001", "巨无霸", "main", 2550, 520, 26.0),
    Meal("m-1002", "麦辣鸡腿堡", "main", 2150, 450, 22.0),
    Meal("m-1003", "板烧鸡腿堡", "main", 2250, 430, 24.0),
    Meal("m-1004", "麦香鱼", "main", 1950, 390, 17.0),
    Meal("m-1005", "双层吉士汉堡", "main", 2050, 480, 25.0),
    Meal("m-1006", "猪柳蛋麦满分", "main", 1750, 400, 17.0),
    Meal("m-1007", "皮蛋鸡肉粥", "main", 750, 180, 6.0),
    Meal("m-1008", "照烧鸡肉饭", "main", 2450, 560, 27.0),
    Meal("m-1009", "薯条(中)", "snack", 1300, 320, 4.0),
    Meal("m-1010", "薯条(大)", "snack", 1450, 450, 5.0),
    Meal("m-1011", "麦乐鸡(4块)", "snack", 1150, 220, 11.0),
    Meal("m-1012", "玉米杯(小)", "snack", 850, 90, 3.0),
    Meal("m-1013", "香芋派", "snack", 850, 250, 2.0),
    Meal("m-1014", "菠萝派", "snack", 850, 250, 2.0),
    Meal("m-1015", "麦辣鸡翅(2块)", "snack", 1150, 280, 14.0),
    Meal("m-1016", "可口可乐(中)", "drink", 1000, 180, 0.0),
    Meal("m-1017", "雪碧(中)", "drink", 1000, 190, 0.0),
    Meal("m-1018", "零度可乐(中)", "drink", 1000, 190, 0.0),
    Meal("m-1019", "阳光橙(中)", "drink", 1000, 210, 0.0),
    Meal("m-1020", "冰黑咖啡(中)", "drink", 1000, 15, 1.0),
    Meal("m-1021", "锡兰红茶(中)", "drink", 900, 120, 0.0),
    Meal("m-1022", "燕麦拿铁(中)", "drink", 1200, 220, 8.0),
    Meal("m-1023", "圆筒冰淇淋", "dessert", 600, 150, 4.0),
    Meal("m-1024", "草莓新地", "dessert", 1150, 260, 6.0),
]

# 示例优惠券(满 X 分减 Y 分)
DEMO_COUPONS = [
    Coupon("c-demo-1", "满25减4(示例券)", 2500, 400),
    Coupon("c-demo-2", "满40减7(示例券)", 4000, 700),
    Coupon("c-demo-3", "满60减12(示例券)", 6000, 1200),
]

# 官方 MCP 工具概览(来自 M-China/mcd-mcp-server 仓库,更新于 2026-10-01)
# 仅用于 `tools --demo` 离线展示;真实工具列表以 tools/list 实时获取为准
DEMO_TOOLS_OVERVIEW = [
    ("list-nutrition-foods", "餐品营养信息列表(能量、蛋白质、脂肪、碳水、钠、钙等)"),
    ("delivery-query-addresses", "获取用户可配送地址列表"),
    ("delivery-create-address", "新增配送地址"),
    ("delivery-query-stores", "查询可配送的门店列表"),
    ("query-meal-assistance", "查询助餐服务(企业团餐场景)"),
    ("query-nearby-stores", "查询附近可用门店"),
    ("query-store-coupons", "查询当前门店下可用的优惠券列表"),
    ("query-meals", "查询当前可售卖的餐品列表(分类、餐品编码、标签)"),
    ("query-meal-detail", "查询餐品详情与套餐组成、可替换选项"),
    ("calculate-price", "商品价格计算(金额、配送费、优惠、应付总价)"),
    ("create-order", "创建订单"),
    ("cancel-order", "取消订单"),
    ("query-order", "查询订单详情"),
    ("order-list", "查询历史订单"),
    ("campaign-calendar", "活动日历查询工具"),
    ("available-coupons", "麦麦省券列表查询"),
    ("auto-bind-coupons", "麦麦省一键领券"),
    ("query-my-coupons", "我的优惠券查询"),
    ("query-my-account", "我的积分查询"),
    ("mall-points-products", "查询麦麦商城商品列表"),
    ("mall-product-detail", "查询麦麦商城商品详情"),
    ("mall-create-order", "积分兑换商品下单"),
    ("now-time-info", "获取当前时间信息"),
    ("query-lottery-info", "查看积分抽奖活动信息"),
    ("draw-lottery", "积分抽奖"),
    ("query-my-prizes", "查看我的奖品"),
    ("mall-order-list", "麦麦商城订单查询"),
    ("mall-order-detail", "麦麦商城订单详情查询"),
    ("query-party-city", "主题活动城市列表查询"),
    ("query-party-store", "主题活动门店列表查询"),
    ("query-partystore-date", "主题活动可预约日期查询"),
    ("query-partystore-session", "主题活动可预约日期场次查询"),
    ("party-order-create", "主题活动订单创建"),
]
