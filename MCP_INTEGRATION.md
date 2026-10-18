# MCP 集成说明

本项目为麦当劳程序员创意开发大赛参赛作品,本文说明实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## MCP Server

| 项目 | 说明 |
|---|---|
| Server 地址 | `https://mcp.mcd.cn`(麦当劳中国官方 MCP Server) |
| 传输协议 | Streamable HTTP |
| 认证方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录,控制台点击"激活",免费领取 |
| 官方使用指南 | [github.com/M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server) |
| 限流 | 每个 Token 每分钟 600 次请求(429),客户端内置退避重试 |

## 使用的工具

| 工具 | 用途 | 调用时机 |
|---|---|---|
| `tools/list` | 能力发现:读取全部工具及 `inputSchema` | 真实模式启动时 |
| `query-nearby-stores` | 按城市+关键词搜索附近门店,取营业中的门店编码 | 未传 `--store-id` 时 |
| `query-meals` | 查询门店可售餐品**编码**列表(真实菜单只返回 code,不含价格) | 配餐前拉菜单(第 1 步) |
| `calculate-price` | 批量商品算价,一次最多 20 个,返回餐品名称+原价+实付 | 配餐前批量拉名称和价格;计划生成后逐顿复核 |
| `query-store-coupons` | 查询当前门店可用优惠券 | 配餐前拉券(来源 1/3) |
| `available-coupons` | 麦麦省可领取优惠券列表 | 配餐前拉券(来源 2/3) |
| `query-my-coupons` | 我的卡包优惠券 | 配餐前拉券(来源 3/3) |
| `list-nutrition-foods` | 餐品营养数据(能量、蛋白质等) | 拉菜单后按名称匹配合并 |

> 实际可用工具以运行时 `tools/list` 动态发现为准;某个工具不可用时自动降级(打印中文提示),不影响主流程。

## 调用流程

```
1. describe_tools()             tools/list 获取工具清单与参数结构
2. query-nearby-stores          -> resolve_store() 选出门店(城市+关键词,优先营业中)
3. query-meals                  -> _extract_meal_codes() 提取去重后的餐品编码
4. calculate-price(批量20个/批) -> meals_from_mcp_payload() 清洗成"名称+价格"餐品列表
5. query-store-coupons          -> coupons_from_mcp_payload()
   available-coupons                三源合并、按 couponId 去重
   query-my-coupons
6. list-nutrition-foods         -> 文本表格专用解析器,按餐品名模糊匹配补全 kcal/蛋白质
7. build_week_plan()            本地配餐:预算约束 + 满减凑单 + 热量区间 + 一周不重样
8. calculate-price              逐顿真实算价校验(带 couponId),差异逐顿列出
```

## 响应解析(协议实测要点)

麦当劳 MCP 是标准 JSON-RPC over Streamable HTTP,但响应有若干"怪癖",客户端均作了兼容:

1. 响应可能是纯 JSON,也可能是 SSE 格式(以 `data: ` 开头)——先剥壳再解析;
2. 业务数据优先取 `result.structuredContent`;若没有,则从 `result.content[0].text`
   的"说明文字 + 内嵌 JSON"混排文本中,用括号配对扫描提取 JSON 对象;
3. `list-nutrition-foods` 的 `data` 不是 JSON 数组,而是
   `[160]{表头}:` + CSV 行的**文本表格**——用表头列数对齐逐行解析;
4. `query-meals` 必须传 `storeCode + orderType + beType` 三个参数,且只返回餐品编码,
   名称和价格要靠 `calculate-price` 批量查询(本项目每批 20 个,实测每批全部返回);
5. `query-nearby-stores` 的 `city` 和 `keyword` 必须**同时传**,只传一个会报
   "城市名或者关键词不能为空";
6. 门店不在营业时间时 `query-meals` 报"门店可能已关闭"——客户端会优先选营业中的门店;
7. `calculate-price` 的金额单位是分(整数)——项目内部统一用分;
8. HTTP 401 -> Token 无效;HTTP 429 -> 限流,客户端自动退避重试。

## 安全边界

- 只调用查询类工具;
- **不调用** `create-order` / `cancel-order` / `mall-create-order` / `party-order-create` /
  `draw-lottery` 等任何下单、支付、抽奖、兑换类工具;
- 不包含真实 Token,配置仅使用环境变量占位符(见 `mcp-config.example.json`);
- 领券类工具(`auto-bind-coupons`)为状态变更操作,本项目默认不调用。

## 业务价值

把"查菜单、找券、算价格"三个孤立动作,变成"这一周的麦当劳怎么吃"的一次决策:

- **对学生党/预算敏感人群**:输入一周预算,输出每天的具体套餐,券后实付严格不超预算;
- **对营养关注人群**:每顿热量控制在目标区间,并给出蛋白质汇总;
- **对选择困难症**:一周不重样 + 凑单建议,不用每天重新纠结;
- **决策可信**:每一步的价格优化都由麦当劳官方 `calculate-price` 真实裁决,
  不是拍脑袋估算——本地估算与真实算价的差异会明确列出。
