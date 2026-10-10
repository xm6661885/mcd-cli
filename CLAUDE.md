# CLAUDE.md

`mcd-cli` 是麦当劳中国 MCP（`https://mcp.mcd.cn`）的命令行客户端，单文件 `mcd_cli.py`，只依赖 Python 标准库，不依赖其他仓库。

- `./mcd-cli --help`、`--version` 不需要凭证。
- 凭证优先级：`--auth` > `MCD_MCP_TOKEN` > `MCD_CLI_AUTH`/`MCP_CLI_AUTH` 指向的文件 > 仓库根目录 `auth.json`（已被 gitignore，权限 600）。
- 直接调用时，参数名会和 inputSchema 做忽略大小写、`-`/`_` 的匹配；未知参数和缺少必填参数在本地报错。
- `WRITE_TOOLS` 列出会改动账户的工具，`tools --names`/`help` 会标出。
- 测试：`python3 -m unittest discover -s tests`（本地模拟 MCP 服务，不需要 Token）。
- 本仓库公开在 github.com/xm6661885/mcd-cli（参赛作品），不要提交 auth.json。
