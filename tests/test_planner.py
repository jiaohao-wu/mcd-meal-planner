"""配餐算法与数据清洗测试(纯逻辑,不需要网络和 Token)。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_meal_planner.demo_data import DEMO_COUPONS, DEMO_MEALS
from mcd_meal_planner.planner import (Coupon, Meal, build_week_plan,
                                      coupons_from_mcp_payload,
                                      meals_from_mcp_payload,
                                      pick_best_coupon, _to_cents)


class TestCouponSelection(unittest.TestCase):
    def setUp(self):
        self.coupons = [
            Coupon("c1", "满25减4", 2500, 400),
            Coupon("c2", "满40减7", 4000, 700),
            Coupon("c3", "满60减12", 6000, 1200),
        ]

    def test_below_all_thresholds(self):
        self.assertIsNone(pick_best_coupon(2000, self.coupons))

    def test_picks_max_discount(self):
        best = pick_best_coupon(4100, self.coupons)
        self.assertEqual(best.coupon_id, "c2")

    def test_picks_highest_when_multiple(self):
        best = pick_best_coupon(6500, self.coupons)
        self.assertEqual(best.coupon_id, "c3")


class TestWeekPlan(unittest.TestCase):
    def test_demo_plan_within_budget_and_balanced(self):
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=7)
        self.assertEqual(len(plan.days), 7)
        self.assertLessEqual(plan.total_paid_cents, plan.budget_cents)
        self.assertTrue(plan.check_balance())
        self.assertGreater(plan.total_saved_cents, 0)

    def test_mains_do_not_repeat_within_a_week(self):
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=7)
        mains = [m.name for d in plan.days for m in d.items if m.category == "main"]
        self.assertEqual(len(mains), len(set(mains)), "一周内主食不应重样")

    def test_kcal_in_range_for_demo_data(self):
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=7)
        self.assertEqual(plan.in_range_days, 7)

    def test_deterministic(self):
        plan1 = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=7)
        plan2 = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=7)
        self.assertEqual([d.names for d in plan1.days], [d.names for d in plan2.days])
        self.assertEqual(plan1.total_paid_cents, plan2.total_paid_cents)

    def test_tight_budget_falls_back_to_cheapest_main(self):
        # 每天只有 8 元,只够最便宜的主食(皮蛋鸡肉粥 7.5 元),且备注"从简"
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=800, days=1)
        self.assertEqual(plan.days[0].names, ["皮蛋鸡肉粥"])
        self.assertLessEqual(plan.days[0].paid_cents, plan.daily_budget_cents)
        self.assertIn("从简", plan.days[0].note)

    def test_impossible_budget_warns(self):
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=100, days=1)
        self.assertIn("警告", plan.days[0].note)

    def test_no_drink_option(self):
        plan = build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000,
                               days=7, want_drink=False)
        for day in plan.days:
            self.assertTrue(all(m.category != "drink" for m in day.items))

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            build_week_plan(DEMO_MEALS, DEMO_COUPONS, budget_cents=28000, days=0)
        with self.assertRaises(ValueError):
            build_week_plan([], [], budget_cents=28000, days=7)


class TestUnitConversion(unittest.TestCase):
    def test_yuan_string(self):
        self.assertEqual(_to_cents("25.5", "priceYuan"), 2550)

    def test_cents_integer(self):
        self.assertEqual(_to_cents(2550, "price"), 2550)

    def test_explicit_yuan_key(self):
        self.assertEqual(_to_cents("25.5", "price元"), 2550)

    def test_explicit_cent_key(self):
        self.assertEqual(_to_cents(2550, "priceCent"), 2550)

    def test_invalid_value(self):
        self.assertEqual(_to_cents("abc", "price"), 0)
        self.assertEqual(_to_cents(None, "price"), 0)


class TestMCPPayloadCleaning(unittest.TestCase):
    def test_meals_from_nested_payload(self):
        payload = {
            "success": True,
            "data": {
                "storeMenu": {
                    "categories": [
                        {"categoryName": "主食", "productList": [
                            {"productName": "麦辣鸡腿堡", "currentPrice": 21.5,
                             "productCode": "A01", "category": "main"},
                            {"productName": "可口可乐", "currentPrice": 10.0,
                             "productCode": "D01", "category": "drink"},
                        ]},
                    ]
                }
            }
        }
        meals = meals_from_mcp_payload(payload)
        names = {m.name for m in meals}
        self.assertIn("麦辣鸡腿堡", names)
        self.assertIn("可口可乐", names)
        burger = next(m for m in meals if m.name == "麦辣鸡腿堡")
        self.assertEqual(burger.price_cents, 2150)
        self.assertEqual(burger.category, "main")

    def test_meals_from_cents_payload(self):
        payload = {"meals": [{"name": "巨无霸", "price": 2550, "code": "m-1"}]}
        meals = meals_from_mcp_payload(payload)
        self.assertEqual(meals[0].price_cents, 2550)

    def test_meals_skip_items_without_price(self):
        payload = {"meals": [{"name": "白开水"}, {"name": "薯条", "price": 13.0}]}
        meals = meals_from_mcp_payload(payload)
        self.assertEqual(len(meals), 1)
        self.assertEqual(meals[0].name, "薯条")

    def test_coupons_from_payload(self):
        payload = {"coupons": [
            {"couponId": "c-1", "couponName": "满25减4", "thresholdAmount": 25.0,
             "discountAmount": 4.0},
            {"couponId": "c-2", "couponName": "无效券", "thresholdAmount": 0,
             "discountAmount": 0},
        ]}
        coupons = coupons_from_mcp_payload(payload)
        self.assertEqual(len(coupons), 1)
        self.assertEqual(coupons[0].threshold_cents, 2500)
        self.assertEqual(coupons[0].off_cents, 400)

    def test_empty_payload(self):
        self.assertEqual(meals_from_mcp_payload({}), [])
        self.assertEqual(coupons_from_mcp_payload({"foo": "bar"}), [])


if __name__ == "__main__":
    unittest.main()
