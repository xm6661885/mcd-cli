---
name: mcd-cli
description: 用命令行调用麦当劳中国 MCP Server 的全部工具：查菜单、门店、优惠券、积分、订单，到店或外送下单，积分商城与活动。适合没有 MCP 宿主、只能执行 shell 命令的 Agent，或需要在脚本、定时任务里调用麦当劳 MCP 的场景。当用户提到麦当劳、麦乐送、麦当劳优惠券/积分，或想点麦当劳时使用。
---

# mcd-cli：麦当劳 MCP 的命令行入口

`mcd-cli` 把麦当劳 MCP Server（`https://mcp.mcd.cn`）的每个 Tool 变成一个 shell 子命令，参数按 Tool 的 `inputSchema` 自动校验和转换类型。

## 准备

```bash
export MCD_MCP_TOKEN=你的Token     # 在 https://open.mcd.cn/mcp 申请
mcd-cli tools --names              # 列出工具，带 * 的会改动账户
mcd-cli help query-meals           # 查看某个工具的说明和参数
```

不要把 Token 写进命令行参数或输出给用户。

## 调用方式

```bash
mcd-cli query-nearby-stores --be-type 1 --search-type 2 --city 广州市 --keyword 天河城
mcd-cli query-meals --store-code 1400464 --order-type 1 --be-type 1 --json
mcd-cli call calculate-price '{"storeCode":"1400464","orderType":1,"beType":1,"items":[{"productCode":"9900016073","quantity":1}]}'
```

- 参数写成 `--beType`、`--be-type`、`--be_type` 都可以；未知参数和缺少必填参数会在请求前报错。
- 数组、对象参数用 JSON；结构复杂时用 `call <工具名> '<JSON>'` 或 `@文件`。
- 价格字段（`calculate-price`）单位是分。

## 常见流程

- **到店点餐**：`query-nearby-stores` → `query-meals` →（`query-meal-detail`）→ `query-store-coupons` → `calculate-price` → `create-order`（带 `takeWayCode`）
- **麦乐送**：`delivery-query-addresses` → `delivery-query-stores` → `query-meals` → `calculate-price` → `create-order`（带 `addressId`）
- **订单**：`order-list`、`query-order`、`cancel-order`
- **券和积分**：`available-coupons`、`auto-bind-coupons`、`query-my-coupons`、`query-my-account`、`mall-points-products` → `mall-product-detail` → `mall-create-order`
- **活动**：`campaign-calendar`、`query-lottery-info`、`draw-lottery`、派对系列 `query-party-*` → `party-order-create`

## 安全规则

`tools --names` 里带 `*` 的工具（`create-order`、`cancel-order`、`mall-create-order`、`party-order-create`、`auto-bind-coupons`、`draw-lottery`、`delivery-create-address`）会下单、扣积分或改动账户。必须先向用户确认门店、餐品、数量、方式和金额，得到明确同意后再调用。查询类工具可以直接用。
