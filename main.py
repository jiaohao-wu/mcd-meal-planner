#!/usr/bin/env python3
"""麦麦一周配餐师 - 命令行入口。

用法示例:
    python main.py demo                      # 离线演示(无需 Token)
    python main.py plan --budget 200         # 一周配餐(无 Token 时自动用演示数据)
    python main.py plan --budget 200 --days 5 --no-drink
    python main.py today --budget 30         # 今天吃什么
    python main.py tools                     # 列出麦当劳 MCP 工具

真实数据模式:先到 open.mcd.cn/mcp 用手机号登录免费领取 MCP Token,
然后设置环境变量 MCD_TOKEN,或加 --token 参数。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcd_meal_planner.cli import main

if __name__ == "__main__":
    main()
