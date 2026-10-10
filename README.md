# mcd-cli · 麦当劳 MCP 命令行客户端

> 让只能执行 shell 命令的 Agent 和脚本，也能用上麦当劳 MCP。

麦当劳 MCP Server 需要支持 MCP 的宿主（WorkBuddy、Claude Desktop 等）才能调用。很多场景其实只有一个 shell：Codex/Claude Code 的子 Agent、CI、cron 定时任务、自己写的小脚本。`mcd-cli` 把 MCP 的 35 个 Tool 都变成命令行子命令：

- **一个文件，零依赖**：只用 Python 3.9+ 标准库，复制就能用；
- **参数按 schema 校验**：`--be-type`、`--beType` 都能识别，类型自动转换，缺少必填参数或写错参数名在请求前就报错，不会浪费一次调用；
- **对 Agent 友好**：`help <工具>` 直接给出参数表，`tools --names` 用 `*` 标出会改动账户的工具，错误统一用 JSON 输出到 stderr；
- **协议完整**：`initialize` → `notifications/initialized` → `tools/call`，兼容 JSON 和 SSE 两种响应，并保持 `Mcp-Session-Id`。

## 安装

```bash
git clone https://github.com/xm6661885/mcd-cli.git
ln -s "$PWD/mcd-cli/mcd-cli" ~/.local/bin/mcd-cli
export MCD_MCP_TOKEN=你的Token          # https://open.mcd.cn/mcp 申请
```

也可以把 Token 放进 `auth.json`（`{"token": "..."}`，记得 `chmod 600`），或用 `--auth` 指定其他凭证文件。

凭证优先级：`--auth` > `MCD_MCP_TOKEN` > `MCD_CLI_AUTH` 指向的文件 > 程序目录下的 `auth.json`。

## 使用示例

```bash
$ mcd-cli tools --names | head -4
cancel-order  *
delivery-create-address  *
query-store-coupons
query-meal-assistance

$ mcd-cli help query-store-coupons | tail -5
参数：
  --beCode <string> 可选  业务编码，与storeCode 配对使用……
  --beType <integer> 必填 可选值 [1, 2, 5, 6]  1-到店取餐，2-麦乐送到家，5-得来速(DT)，6-企业团餐
  --orderType <integer> 必填 可选值 [1, 2]  订单类型……
  --storeCode <string> 必填  门店编码必须全部由数字组成

$ mcd-cli query-store-coupons --be-type 1
{"error": "缺少必填参数：--orderType, --storeCode"}

$ mcd-cli --json query-nearby-stores --be-type 1 --search-type 2 --city 广州市 --keyword 广州南站
{"success": true, "code": 200, "data": [{"storeCode": "1400877", "storeName": "麦当劳广州南站三楼A23检票口上方餐厅", ...}]}

$ mcd-cli call calculate-price '{"storeCode":"1400464","orderType":1,"beType":1,"items":[{"productCode":"9900016073","quantity":1}]}'
```

配合 `jq` 在脚本里使用：

```bash
mcd-cli --json query-my-account | jq '.data'
mcd-cli --json campaign-calendar | jq '.data.dailyList[].events[].articleDto.title'
```

作为 Agent Skill 使用：把本仓库导入为 Skill，入口是 `SKILL.md`，里面写了常见调用流程和安全规则。

## 命令一览

| 命令 | 说明 |
|---|---|
| `mcd-cli tools [--names]` | 列出工具（完整 schema，或只列名称） |
| `mcd-cli help <工具>` | 工具说明和参数表 |
| `mcd-cli <工具> --参数 值` | 按工具名直接调用 |
| `mcd-cli call <工具> '<JSON>'` / `@file.json` | 用 JSON 调用 |
| `mcd-cli config show\|path` | 查看凭证来源（Token 打码） |
| `--json` / `--pretty` / `--timeout` / `--auth` | 输出格式、超时、凭证 |

## 目标用户

- 用 Codex、Claude Code、Gemini CLI 等终端 Agent 的开发者
- 想把麦当劳 MCP 接进 cron、CI、Shell 脚本的人
- 其他麦当劳 MCP Skill 的作者：可以用它做调试和联调工具

## 测试

```bash
python3 -m unittest discover -s tests
```

测试会在本地起一个模拟的 MCP HTTP 服务，覆盖握手、Bearer 鉴权、SSE 响应、参数映射与校验、Token 打码，不需要真实 Token。

## 声明

本项目为麦当劳程序员节创意开发大赛参赛作品，非麦当劳官方产品。接口能力与返回结果以麦当劳 MCP Server 为准。
