"""配餐算法与 MCP 数据清洗。

核心思路(整个项目最重要的文件,但逻辑很短):
  1. 把一周预算拆成"每日预算"(留 2% 缓冲);
  2. 每一天从菜单里挑 1 个主食,预算还够就加小食/饮品;
  3. 对当天的购物篮挑一张最划算的优惠券;
  4. 允许最多 15% 的"凑单超额",用券后必须回落到当日预算内;
  5. 主食/小食/饮品轮换使用,保证一周内尽量不重样。

另外提供 meals_from_mcp_payload / coupons_from_mcp_payload:
  把麦当劳 MCP 返回的(结构不固定的)JSON 清洗成 Meal / Coupon 对象。
  字段名映射是"防御式"的,因为官方文档没有给出响应结构样例。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# 餐品分类(与 demo_data 保持一致)
CATEGORY_MAIN = "main"       # 主食
CATEGORY_SNACK = "snack"     # 小食
CATEGORY_DRINK = "drink"     # 饮品
CATEGORY_DESSERT = "dessert"  # 甜品
CATEGORY_LABELS = {
    CATEGORY_MAIN: "主食",
    CATEGORY_SNACK: "小食",
    CATEGORY_DRINK: "饮品",
    CATEGORY_DESSERT: "甜品",
}

DEFAULT_KCAL_RANGE = (500, 850)  # 每顿热量目标区间(近似值;新品暂无营养数据)


# -----------------------------------------------------------
# 数据模型
# -----------------------------------------------------------

@dataclass
class Meal:
    """一个餐品。price_cents 单位为分(与麦当劳 calculate-price 一致)。"""
    code: str
    name: str
    category: str
    price_cents: int
    kcal: int = 0
    protein_g: float = 0.0


@dataclass
class Coupon:
    """一张满减券:满 threshold_cents 减 off_cents。"""
    coupon_id: str
    name: str
    threshold_cents: int
    off_cents: int


@dataclass
class DayPlan:
    """一天的配餐结果。"""
    day_index: int
    items: List[Meal]
    original_cents: int          # 原价小计(分)
    coupon: Optional[Coupon]     # 使用的优惠券(可能为 None)
    paid_cents: int              # 券后实付(分)
    note: str = ""               # 备注(如"预算紧张")

    @property
    def kcal(self) -> int:
        return sum(m.kcal for m in self.items)

    @property
    def protein_g(self) -> float:
        return sum(m.protein_g for m in self.items)

    @property
    def names(self) -> List[str]:
        return [m.name for m in self.items]


@dataclass
class WeekPlan:
    """一周(或 N 顿)的配餐结果。"""
    budget_cents: int
    daily_budget_cents: int
    days: List[DayPlan] = field(default_factory=list)
    kcal_range: Tuple[int, int] = DEFAULT_KCAL_RANGE

    @property
    def total_original_cents(self) -> int:
        return sum(d.original_cents for d in self.days)

    @property
    def total_paid_cents(self) -> int:
        return sum(d.paid_cents for d in self.days)

    @property
    def total_saved_cents(self) -> int:
        return self.total_original_cents - self.total_paid_cents

    @property
    def in_range_days(self) -> int:
        low, high = self.kcal_range
        return sum(1 for d in self.days if low <= d.kcal <= high)

    def check_balance(self) -> bool:
        """对平自检:每日实付之和必须等于总实付。"""
        return sum(d.paid_cents for d in self.days) == self.total_paid_cents


# -----------------------------------------------------------
# 配餐算法
# -----------------------------------------------------------

def pick_best_coupon(original_cents: int, coupons: Iterable[Coupon]) -> Optional[Coupon]:
    """从可用券中挑"减得最多"的一张;没有可用券返回 None。"""
    usable = [c for c in coupons
              if c.off_cents > 0 and original_cents >= c.threshold_cents]
    if not usable:
        return None
    return max(usable, key=lambda c: c.off_cents)


def _protein_per_yuan(meal: Meal) -> float:
    """每元蛋白质含量,用于给主食排序(先按性价比,同性价比按价格)。

    没有营养数据的餐品(kcal 为 0,通常是刚上线还没进营养表的新品)
    按性价比 0 处理,排在后面,避免它们挤占配餐名额。
    """
    if meal.price_cents <= 0 or meal.kcal <= 0:
        return 0.0
    return meal.protein_g / (meal.price_cents / 100.0)


def _sort_by_value(meals: List[Meal]) -> List[Meal]:
    return sorted(meals, key=lambda m: (-_protein_per_yuan(m), m.price_cents))


def _rotating(candidates: List[Meal], used_names: set) -> List[Meal]:
    """轮换排序:没用过的排前面,全用过了就重置一轮(用于主食,保证每天有主食)。"""
    fresh = [m for m in candidates if m.name not in used_names]
    return fresh if fresh else list(candidates)


def _rotating_extras(candidates: List[Meal], used_names: set) -> List[Meal]:
    """附加品轮换:优先没用过的;都用过了就重置一轮。

    与 _fresh_only 的区别:池子小的时候宁可重复一个高性价比的小食,
    也要保证每天"主食+小食"的搭配完整,而不是干吃主食。
    """
    fresh = [m for m in candidates if m.name not in used_names]
    return fresh if fresh else list(candidates)


def _fresh_only(candidates: List[Meal], used_names: set) -> List[Meal]:
    """只返回没用过的;用完了就返回空列表。

    用于小食/饮品/甜品:宁可这天不加,也不重复,
    保证"一周不重样"是硬约束。
    """
    return [m for m in candidates if m.name not in used_names]


def _is_sauce_or_condiment(meal: Meal) -> bool:
    """酱料/配料类:没有营养数据且单价很低,不适合当配餐小食。

    麦当劳菜单里套餐子项(各种酱、小配料)也会被算价接口返回,
    它们kcal 为 0 且价格极低,直接放进配餐会让一整天没有热量。
    """
    return meal.kcal <= 0 and 0 < meal.price_cents < 800


def _day_combinations(main: Meal, extras: List[Meal]) -> Iterable[List[Meal]]:
    """生成"主食 + 附加品"的组合,从最丰盛到最朴素。"""
    for count in range(len(extras), -1, -1):
        for combo in itertools.combinations(extras, count):
            yield [main, *combo]


def build_day(day_index: int, daily_budget_cents: int, pools: Dict[str, List[Meal]],
              coupons: List[Coupon], used_names: set,
              want_drink: bool = True,
              kcal_range: Tuple[int, int] = DEFAULT_KCAL_RANGE,
              slack: float = 1.15) -> DayPlan:
    """生成一天的配餐。

    slack: 允许的凑单超额系数(先按 1.15 倍日预算凑单触发满减门槛,
            用券后必须回落到 daily_budget_cents 以内)。

    附加品(小食/甜品/饮品)各取性价比最高的前 3 名做候选,
    按"主食+附加品"的总热量能否达到下限优先排序,尽量让营养达标。
    """
    mains = _sort_by_value(_rotating(pools.get(CATEGORY_MAIN, []), used_names))
    snacks = [m for m in _rotating_extras(pools.get(CATEGORY_SNACK, []), used_names)
              if not _is_sauce_or_condiment(m)]
    drinks = _sort_by_value(_rotating_extras(pools.get(CATEGORY_DRINK, []), used_names))
    desserts = [m for m in _rotating_extras(pools.get(CATEGORY_DESSERT, []), used_names)
                if not _is_sauce_or_condiment(m)]
    extras_pool = _sort_by_value(snacks + desserts)
    kcal_low = kcal_range[0] if kcal_range else 0
    kcal_high = kcal_range[1] if kcal_range else 0

    fallback: Optional[DayPlan] = None   # 暂存第一个"从简"方案,继续找带搭配的
    for main in mains:
        # 附加品候选组合:小食前 3 × 饮品前 3 的完整组合,
        # 再加各自单独出场,最后是"只吃主食"的从简组合
        snack_cands = extras_pool[:3]
        drink_cands = drinks[:3] if want_drink else []
        combos: List[List[Meal]] = []
        for snack in snack_cands:
            for drink in drink_cands:
                combos.append([snack, drink])
        for snack in snack_cands:
            combos.append([snack])
        for drink in drink_cands:
            combos.append([drink])
        combos.append([])

        def _combo_key(combo: List[Meal]) -> Tuple[int, int]:
            total_kcal = main.kcal + sum(m.kcal for m in combo)
            reaches = 1 if (not kcal_low or total_kcal >= kcal_low) else 0
            return (-reaches, -total_kcal)

        for items in sorted(combos, key=_combo_key):
            full = [main] + items
            original = sum(m.price_cents for m in full)
            if original > daily_budget_cents * slack:
                continue                     # 凑单上限,跳过
            if kcal_high and sum(m.kcal for m in full) > kcal_high:
                continue                     # 超过热量上限,跳过
            coupon = pick_best_coupon(original, coupons)
            paid = max(0, original - (coupon.off_cents if coupon else 0))
            if paid > daily_budget_cents:
                continue
            if items:                        # 带搭配的方案,立即采用
                for m in full:
                    used_names.add(m.name)
                return DayPlan(day_index, full, original, coupon, paid)
            if fallback is None:             # 从简方案先记下,继续找带搭配的
                fallback = DayPlan(day_index, full, original, coupon, paid,
                                   note="预算较紧,今日从简")
        # 这个主食凑不出合规组合,换下一个主食

    if fallback is not None:
        for m in fallback.items:
            used_names.add(m.name)
        return fallback

    # 所有主食都超预算:退回最便宜的主食,并在备注里说明
    all_mains = pools.get(CATEGORY_MAIN, [])
    if all_mains:
        cheapest = min(all_mains, key=lambda m: m.price_cents)
        original = cheapest.price_cents
        coupon = pick_best_coupon(original, coupons)
        paid = max(0, original - (coupon.off_cents if coupon else 0))
        if paid <= daily_budget_cents:
            note = "预算较紧,今日从简"
        else:
            note = "警告:最便宜的主食也超出当日预算,请上调预算"
        return DayPlan(day_index, [cheapest], original, coupon, paid, note=note)
    raise ValueError("菜单里没有任何主食,无法配餐")


def build_week_plan(meals: List[Meal], coupons: List[Coupon], budget_cents: int,
                    days: int = 7, want_drink: bool = True,
                    kcal_range: Tuple[int, int] = DEFAULT_KCAL_RANGE) -> WeekPlan:
    """生成一周(默认 7 顿)配餐计划。预算单位为分。"""
    if days < 1:
        raise ValueError("天数至少为 1")
    if budget_cents <= 0:
        raise ValueError("预算必须为正数")
    pools: Dict[str, List[Meal]] = {}
    for meal in meals:
        pools.setdefault(meal.category, []).append(meal)
    if not pools.get(CATEGORY_MAIN):
        raise ValueError("菜单里没有任何主食,无法配餐")

    # 每日预算 = 总预算 * 0.98 / 天数(留 2% 缓冲)
    daily_budget = max(1, int(budget_cents * 0.98 / days))
    used_names: set = set()
    plan = WeekPlan(budget_cents=budget_cents, daily_budget_cents=daily_budget,
                    kcal_range=kcal_range)
    for i in range(days):
        plan.days.append(build_day(i + 1, daily_budget, pools, coupons,
                                   used_names, want_drink, kcal_range))
    if not plan.check_balance():
        raise AssertionError("内部错误:每日实付之和与总实付不一致")
    return plan


# -----------------------------------------------------------
# MCP 响应数据清洗(防御式字段映射)
# -----------------------------------------------------------

_NAME_KEYS = ("mealName", "productName", "mealTitle", "title", "name")
_PRICE_KEYS = ("currentPrice", "salePrice", "priceYuan", "originalPrice",
               "originalSubtotal", "subtotal", "price", "amount", "money")
_CODE_KEYS = ("mealCode", "productCode", "skuId", "productId", "code", "id")
_KCAL_KEYS = ("kcal", "energyKcal", "energy", "calorie", "calories")
_PROTEIN_KEYS = ("proteinG", "protein", "proteinContent")
_CATEGORY_KEYS = ("category", "mealType", "type", "tag")

_MAIN_HINTS = ("堡", "卷", "饭", "粥", "全鸡", "肉卷", "巨无霸", "吉士", "麦香鱼",
               "板烧", "猪柳", "安格斯", "厚牛", "瘦肉", "烧饼", "满分", "鸡排",
               "烤堡", "珍堡", "皇堡", "鸡肉卷", "牛肉卷")
_SNACK_HINTS = ("薯", "鸡块", "鸡翅", "翅", "派", "玉米", "盒", "球", "条")
_DRINK_HINTS = ("可乐", "雪碧", "咖啡", "茶", "汁", "水", "奶", "怡泉", "气泡",
                "奇诺", "拿铁", "摩卡", "美式", "冷萃", "黑巧", "雪冰", "咖")
# 容器词:麦当劳餐品名里出现"杯/瓶/罐"基本只有饮品
_CONTAINER_HINTS = ("杯", "瓶", "罐")
_DESSERT_HINTS = ("冰淇淋", "甜筒", "圣代", "新地", "甜品")


def _first_key(item: dict, keys: Tuple[str, ...]):
    """返回 item 中第一个存在且非空的键值。"""
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _key_of(item: dict, keys: Tuple[str, ...]) -> str:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return key
    return ""


def _to_cents(value, key_name: str) -> int:
    """把价格转成"分"。

    单位启发式(官方未文档化响应单位):
      - 键名含 cent/分  -> 视为分
      - 键名含 yuan/元  -> 视为元,乘 100
      - 其他            -> 大于等于 200 的整数视为分,否则视为元
    """
    if value is None:
        return 0
    try:
        num = float(str(value).strip())
    except (TypeError, ValueError):
        return 0
    lower = key_name.lower()
    if "cent" in lower or "分" in key_name:
        return int(round(num))
    if "yuan" in lower or "元" in key_name:
        return int(round(num * 100))
    if num >= 200 and num == int(num):
        return int(num)          # 很可能已经是"分"
    return int(round(num * 100))  # 默认按"元"处理


def _guess_category(name: str, item: dict) -> str:
    """根据显式分类字段或餐品名猜测分类,猜不出归为小食(不影响配餐主流程)。"""
    explicit = _first_key(item, _CATEGORY_KEYS)
    if isinstance(explicit, str):
        text = explicit.lower()
        if any(h in text for h in ("main", " staple", "主食", "汉堡", "主餐")):
            return CATEGORY_MAIN
        if any(h in text for h in ("drink", "饮品", "饮料")):
            return CATEGORY_DRINK
        if any(h in text for h in ("dessert", "甜品", "冰淇淋")):
            return CATEGORY_DESSERT
        if any(h in text for h in ("snack", "小食", "配餐")):
            return CATEGORY_SNACK
    if any(h in name for h in _MAIN_HINTS):
        return CATEGORY_MAIN
    if any(h in name for h in _DRINK_HINTS):
        return CATEGORY_DRINK
    if any(h in name for h in _DESSERT_HINTS):
        return CATEGORY_DESSERT
    if any(h in name for h in _SNACK_HINTS):
        return CATEGORY_SNACK
    if any(h in name for h in _CONTAINER_HINTS):
        return CATEGORY_DRINK   # "中杯/大杯"在麦当劳菜单里只出现在饮品名上
    return CATEGORY_SNACK


def _find_dict_lists(obj, out: List[list]) -> None:
    """递归找出所有"字典组成的列表",用于在未知结构的响应里找餐品/券数组。

    注意:找到一个列表后还会继续递归它的元素,
    因为官方响应可能是 {"categories": [{"productList": [...]}]} 这种两层嵌套。
    """
    if isinstance(obj, dict):
        for value in obj.values():
            if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
                out.append(value)
                for item in value:
                    _find_dict_lists(item, out)
            else:
                _find_dict_lists(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _find_dict_lists(value, out)


def meals_from_mcp_payload(payload) -> List[Meal]:
    """把 query-meals 之类的响应清洗成 Meal 列表。"""
    lists: List[list] = []
    _find_dict_lists(payload, lists)
    meals: List[Meal] = []
    seen = set()
    for group in lists:
        for item in group:
            name = _first_key(item, _NAME_KEYS)
            price_key = _key_of(item, _PRICE_KEYS)
            price_raw = _first_key(item, _PRICE_KEYS)
            if not name or price_raw is None:
                continue
            cents = _to_cents(price_raw, price_key)
            if cents <= 0:
                continue
            code = str(_first_key(item, _CODE_KEYS) or name)
            kcal_raw = _first_key(item, _KCAL_KEYS)
            protein_raw = _first_key(item, _PROTEIN_KEYS)
            try:
                kcal = int(float(kcal_raw)) if kcal_raw is not None else 0
            except (TypeError, ValueError):
                kcal = 0
            try:
                protein = float(protein_raw) if protein_raw is not None else 0.0
            except (TypeError, ValueError):
                protein = 0.0
            key = (str(name), cents)
            if key in seen:
                continue
            seen.add(key)
            category = _guess_category(str(name), item)
            # 兜底规则:名称里没有任何小食/饮品/甜品线索、但单价达到 15 元以上的,
            # 按主食处理(麦当劳菜单里纯小食/饮品/甜品都在 15 元以下)
            if (category == CATEGORY_SNACK and cents >= 1500
                    and not any(h in str(name)
                                for h in _SNACK_HINTS + _DRINK_HINTS + _DESSERT_HINTS)):
                category = CATEGORY_MAIN
            meals.append(Meal(code, str(name), category, cents, kcal, protein))
    return meals


_COUPON_ID_KEYS = ("couponId", "couponCode", "id", "code")
_COUPON_NAME_KEYS = ("couponName", "title", "name", "description", "desc")
_THRESHOLD_KEYS = ("thresholdAmount", "minAmount", "limitAmount", "useThreshold",
                   "fullAmount", "conditionAmount", "threshold", "满")
_OFF_KEYS = ("discountAmount", "offAmount", "reduceAmount", "couponAmount",
             "discount", "off", "优惠")


def coupons_from_mcp_payload(payload) -> List[Coupon]:
    """把 query-store-coupons / available-coupons 之类的响应清洗成 Coupon 列表。

    优惠券的字段名各家叫法差异很大,这里是尽力而为的映射;
    真实数据建议配合 --debug 查看原始响应人工核对。
    """
    lists: List[list] = []
    _find_dict_lists(payload, lists)
    coupons: List[Coupon] = []
    seen = set()
    for group in lists:
        for item in group:
            coupon_id = _first_key(item, _COUPON_ID_KEYS)
            threshold_key = _key_of(item, _THRESHOLD_KEYS)
            off_key = _key_of(item, _OFF_KEYS)
            threshold_raw = _first_key(item, _THRESHOLD_KEYS)
            off_raw = _first_key(item, _OFF_KEYS)
            if coupon_id is None or threshold_raw is None or off_raw is None:
                continue
            threshold = _to_cents(threshold_raw, threshold_key)
            off = _to_cents(off_raw, off_key)
            if threshold <= 0 or off <= 0:
                continue
            name = _first_key(item, _COUPON_NAME_KEYS) or str(coupon_id)
            key = str(coupon_id)
            if key in seen:
                continue
            seen.add(key)
            coupons.append(Coupon(str(coupon_id), str(name), threshold, off))
    return coupons
