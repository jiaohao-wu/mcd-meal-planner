# mcd-meal-planner · 麦麦一周配餐师

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![零依赖](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](requirements.txt)
[![tests](https://img.shields.io/badge/tests-42%20passed-brightgreen.svg)](tests/)

> 基于麦当劳 MCP 的一周配餐规划工具:输入一周预算,输出每天不重样、营养达标、
> 用券最优的麦当劳餐单。**只查询,不下单。**

学生党 ¥280 吃一周麦当劳,怎么吃得丰盛、吃得营养、还不重样?
这个工具把"查菜单、找优惠券、算价格"三个孤立动作,变成"这一周怎么吃"的一次决策,
而且每一步的价格都由麦当劳官方 `calculate-price` 真实裁决,不是拍脑袋估算。

## 演示(无需 Token,零依赖直接跑)

```bash
python main.py demo
```

```
============================================================
麦麦一周配餐计划(共 7 顿)
门店: 北京新东安二号餐厅(示例门店)
总预算 ¥280.00 | 7 顿 | 日均 ¥39.20 | 每顿热量目标 500-850 kcal
============================================================
第 1 顿
  双层吉士汉堡     主食    480 kcal  蛋白 25.0 g
  圆筒冰淇淋       甜品    150 kcal  蛋白  4.0 g
  燕麦拿铁(中)     饮品    220 kcal  蛋白  8.0 g
  原价小计 ¥38.50    | 用券[满25减4(示例券)]    | 实付 ¥34.50

第 2 顿
  照烧鸡肉饭       主食    560 kcal  蛋白 27.0 g
  麦辣鸡翅(2块)    小食    280 kcal  蛋白 14.0 g
  原价小计 ¥36.00    | 用券[满25减4(示例券)]    | 实付 ¥32.00

第 3 顿
  板烧鸡腿堡       主食    430 kcal  蛋白 24.0 g
  麦乐鸡(4块)      小食    220 kcal  蛋白 11.0 g
  可口可乐(中)     饮品    180 kcal  蛋白  0.0 g
  原价小计 ¥44.00    | 用券[满40减7(示例券)]    | 实付 ¥37.00

第 4 顿
  麦辣鸡腿堡       主食    450 kcal  蛋白 22.0 g
  草莓新地         甜品    260 kcal  蛋白  6.0 g
  锡兰红茶(中)     饮品    120 kcal  蛋白  0.0 g
  原价小计 ¥42.00    | 用券[满40减7(示例券)]    | 实付 ¥35.00

第 5 顿
  巨无霸           主食    520 kcal  蛋白 26.0 g
  玉米杯(小)       小食     90 kcal  蛋白  3.0 g
  雪碧(中)         饮品    190 kcal  蛋白  0.0 g
  原价小计 ¥44.00    | 用券[满40减7(示例券)]    | 实付 ¥37.00

第 6 顿
  猪柳蛋麦满分     主食    400 kcal  蛋白 17.0 g
  草莓新地         甜品    260 kcal  蛋白  6.0 g
  零度可乐(中)     饮品    190 kcal  蛋白  0.0 g
  原价小计 ¥39.00    | 用券[满25减4(示例券)]    | 实付 ¥35.00

第 7 顿
  麦香鱼           主食    390 kcal  蛋白 17.0 g
  薯条(大)         小食    450 kcal  蛋白  5.0 g
  原价小计 ¥34.00    | 用券[满25减4(示例券)]    | 实付 ¥30.00

------------------------------------------------------------
一周汇总: 原价 ¥277.50 -> 券后 ¥240.50,共节省 ¥37.00(13.3%)
预算执行: ¥240.50 / ¥280.00
营养达成: 7/7 顿热量在目标区间
============================================================
```

以上为演示数据(价格/优惠券为近似示例)。连接真实数据后,菜单、优惠券、
算价全部来自麦当劳官方 MCP 实时返回。

## 功能特性

- **预算硬约束**:券后实付严格不超过每日预算,超支会明确警告;
- **一周不重样**:主食/小食/饮品/甜品分类轮换,小食用完自动重置一轮,
  宁可重复一个高性价比小食也不干吃主食;
- **热量感知选配**:附加品候选按"能否把一餐热量补进目标区间"排序,
  主食+小食+饮品的最优组合优先;
- **凑单优化**:允许 15% 超额凑单触发满减门槛,用券后必须回落到预算内;
- **真实算价校验**:每一顿都调用官方 `calculate-price` 复核,
  本地估算与真实价格的差异逐顿列出,请以官方实时价格为准;
- **营养视角**:每顿热量控制在目标区间(默认 500–850 kcal),汇总蛋白质摄入;
  刚上线暂无营养数据的新品会标注"暂无",不参与热量统计;
- **自动选门店**:不传门店编码时,按城市搜索附近门店,优先选营业中的;
- **零第三方依赖**:只用 Python 标准库,克隆即可跑,不需要 pip install;
- **防御式解析**:兼容 SSE / 纯 JSON / 混排文本内嵌 JSON / 文本表格 / 202 空响应
  等响应形态,单个工具不可用自动降级并给出中文提示。

## 快速开始

```bash
# 1. 克隆后直接跑演示(无需 Token、无需安装任何依赖)
python main.py demo

# 2. 一周配餐(无 Token 时自动使用演示数据)
python main.py plan --budget 200

# 3. 今天吃什么(单顿推荐)
python main.py today --budget 40
```

## 连接真实数据(麦当劳 MCP)

1. 打开 [open.mcd.cn/mcp](https://open.mcd.cn/mcp),手机号登录;
2. 右上角"控制台" -> 点击"激活",一键复制 MCP Token(免费);
3. 设置环境变量后重跑:

```bash
# Windows PowerShell
$env:MCD_TOKEN = "你的Token"
python main.py plan --budget 280 --days 7

# 或者用参数传递
python main.py plan --budget 280 --token 你的Token
```

不传 `--store-id` 时会按 `--city`(默认 上海市)自动搜索附近门店并优先选营业中的;
也可以显式指定门店编码:`--store-id 1450713`。

可调参数:`--days`(规划几顿)、`--no-drink`(不要饮品)、
`--kcal-min/--kcal-max`(热量区间)、`--store-id`(门店编码)、
`--city`(自动搜门店的城市)、`--debug`(查看原始响应)。

> Token 每分钟限 600 次请求,本项目一次规划约十几个调用,绰绰有余。
> Token 只保存在你自己的环境变量里,不要提交进仓库。

## 命令一览

| 命令 | 说明 |
|---|---|
| `python main.py demo` | 离线演示(内置示例数据) |
| `python main.py plan --budget 280` | 一周配餐计划 |
| `python main.py today --budget 40` | 今天吃什么 |
| `python main.py tools` | 列出麦当劳 MCP 在线工具清单 |
| `python -m unittest discover -s tests` | 运行全部 42 个测试 |

## 工作原理

```
麦当劳 MCP Server (https://mcp.mcd.cn)
   |  tools/list 能力发现(读取各工具 inputSchema)
   |  query-nearby-stores  按城市搜门店,优先营业中的(不传 --store-id 时)
   |  query-meals          拿餐品编码列表(真实菜单只返回 code)
   |  calculate-price      批量算价(每批 20 个),名称+价格一次拿全
   |  query-store-coupons / query-my-coupons / available-coupons  合并去重
   |  list-nutrition-foods 营养表(特殊的"表头+CSV"文本,专用解析器)
   v
mcp_client.py   JSON-RPC over Streamable HTTP(标准库实现)
   |  剥 SSE 壳 / 提取内嵌 JSON / 解析文本表格 / 202 空响应 / 429 退避重试
   v
planner.py      数据清洗 + 配餐算法
   |  每日预算 = 总预算 / 顿数
   |  每天:1 主食 + 至多 1 小食/甜品 + 至多 1 饮品
   |  组合策略:候选按"热量能否补进目标区间"排序,取第一个合规组合
   |  券策略:门槛可达的券里减得最多的一张
   v
cli.py           输出一周计划 + 真实算价校验报告
```

配餐算法是确定性纯函数(零随机),同样输入永远得到同样输出,可完整单测。

## 安全边界

- 只调用查询类工具,**绝不下单、不支付、不抽奖、不兑换积分**;
- 不调用 `create-order` / `cancel-order` / `mall-create-order` /
  `party-order-create` / `draw-lottery`;
- 领券(`auto-bind-coupons`)属于状态变更操作,本项目默认不调用;
- 仓库不含任何真实 Token,配置仅用环境变量占位符(见 `mcp-config.example.json`);
- 输出仅供参考,不构成医疗或营养建议;餐品供应与价格以麦当劳官方渠道为准。

## 项目结构

```
mcd-meal-planner/
├── main.py                     # 命令行入口(python main.py ...)
├── mcd_meal_planner/
│   ├── cli.py                  # 子命令、输出格式化、真实模式数据拉取与降级
│   ├── mcp_client.py           # MCP 客户端(JSON-RPC / SSE 解析 / 错误映射)
│   ├── planner.py              # 配餐算法 + MCP 响应数据清洗
│   └── demo_data.py            # 内置演示菜单/优惠券(无需 Token 可跑)
├── tests/
│   ├── mock_server.py          # 本地 Mock MCP Server(复现官方响应怪癖)
│   ├── test_client.py          # 客户端解析测试(SSE/JSON/202/401/429...)
│   ├── test_planner.py         # 算法与数据清洗测试
│   ├── test_cli.py             # CLI 冒烟测试
│   └── test_integration.py     # 端到端:CLI 真实模式 + mock server
├── CONTEST_DECLARATION.md      # 参赛声明(官方原文,不可改动)
├── MCP_INTEGRATION.md          # MCP 集成说明
├── mcp-config.example.json     # 脱敏配置示例(仅环境变量占位符)
├── workbuddy.md                # WorkBuddy 开发上下文存档
└── README.md
```

## 二次开发(写给想改着玩的你)

代码刻意写成了"大二 Python 基础也能改"的结构,所有注释都是中文:

- 想加餐品/改演示价格:改 `mcd_meal_planner/demo_data.py` 里的 `DEMO_MEALS` 列表
  (价格单位是**分**,比如 2550 = ¥25.50);
- 改热量目标:命令行加 `--kcal-min 500 --kcal-max 900`;
- 改凑单宽容度:`planner.py` 里 `build_day` 的 `slack` 参数(默认 1.15);
- 换配餐策略:`planner.py` 里 `_sort_by_value`(默认按"每元蛋白质"排序,
  你可以改成按价格或随机);
- 加新的 MCP 工具:在 `cli.py` 里仿照 `fetch_meals` 写一个 `fetch_xxx`,
  记得 try/except 降级。

## 测试

```bash
python -m unittest discover -s tests -v
# Ran 42 tests ... OK
```

测试包含一个本地 Mock MCP Server,复现了麦当劳 MCP 的已知响应行为:
SSE 包装、混排文本内嵌 JSON、文本表格营养数据、批量算价、
HTTP 202 空响应、isError、401/429——所以没有 Token 也能验证整条链路。

## 参赛信息

本项目参加**麦当劳程序员创意开发大赛**(麦当劳中国 GitHub 官方账号 M-China 主办):

- 活动仓库:[M-China/mcd-developer-innovation-challenge](https://github.com/M-China/mcd-developer-innovation-challenge)
- MCP 文档:[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)
- 参赛声明:[CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)(官方原文,不可改动)
- MCP 接入说明:[MCP_INTEGRATION.md](MCP_INTEGRATION.md)
- 使用腾讯 WorkBuddy 开发,开发过程存档见 [workbuddy.md](workbuddy.md)

如果这个项目对你有帮助,欢迎点个 Star。

## License

[MIT](LICENSE)
