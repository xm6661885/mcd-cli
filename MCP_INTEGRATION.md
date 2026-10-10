# MCP 集成说明

## MCP Server

- 麦当劳中国 MCP Server（`mcd-mcp`），`https://mcp.mcd.cn`，Streamable HTTP，JSON-RPC 2.0
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`
- 协议版本：`2024-11-05`

## 协议实现（`mcd_cli.py`）

| 步骤 | JSON-RPC | 说明 |
|---|---|---|
| 1 | `initialize` | 发送 `clientInfo: mcd-cli` |
| 2 | `notifications/initialized` | 通知，无 id |
| 3 | `tools/list` | 用于 `tools`、`help` 和直接调用时取 `inputSchema` |
| 4 | `tools/call` | 优先返回 `structuredContent`，否则解析 `content[].text` 中的 JSON |

响应是 `application/json` 或 `text/event-stream`（取第一个 JSON `data:` 帧）都能处理；服务端返回 `Mcp-Session-Id` 时，后续请求会带上。

## 使用的 Tool

覆盖 MCP Server 当前公开的全部 35 个 Tool，按 `tools/list` 动态发现，不写死。新增工具不用改代码就能用。

| 类别 | Tool |
|---|---|
| 门店 | `query-nearby-stores`, `delivery-query-addresses`, `delivery-create-address`*, `delivery-query-stores` |
| 菜单 | `query-meals`, `query-meal-detail`, `list-nutrition-foods` |
| 价格与下单 | `query-store-coupons`, `calculate-price`, `create-order`*, `query-order`, `order-list`, `cancel-order`*, `query-survey-coupon` |
| 团餐 | `query-promotions`, `query-meal-assistance` |
| 券与积分 | `available-coupons`, `auto-bind-coupons`*, `query-my-coupons`, `query-my-account` |
| 积分商城 | `mall-points-products`, `mall-product-detail`, `mall-create-order`*, `mall-order-list`, `mall-order-detail` |
| 活动 | `campaign-calendar`, `query-lottery-info`, `draw-lottery`*, `query-my-prizes`, `now-time-info` |
| 派对 | `query-party-city`, `query-party-store`, `query-party-store-date`, `query-party-store-session`, `party-order-create`* |

带 `*` 的工具会改动账户，CLI 在 `tools --names` 和 `help` 里会标出来，`SKILL.md` 要求调用前先得到用户确认。

## 调用流程（直接按工具名调用时）

```
mcd-cli query-meals --store-code 1 --order-type 1 --be-type 1
   ▼ initialize → notifications/initialized
   ▼ tools/list → 找到 query-meals 的 inputSchema
   ▼ 参数名归一（store-code → storeCode）、类型转换、必填校验
   ▼ tools/call
   ▼ 输出 JSON（stdout），错误输出 {"error": ...}（stderr，退出码 1）
```

## 业务价值

- 让没有 MCP 宿主的环境（终端 Agent、cron、CI、脚本）也能使用麦当劳 MCP 的全部能力。
- 参数在本地按 schema 校验，Agent 写错参数名或漏传必填项时立刻得到明确提示，减少无效调用。
- 对其他 Skill 开发者来说，也是一个调试和联调麦当劳 MCP 的工具。
