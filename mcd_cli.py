#!/usr/bin/env python3
"""mcd-cli: command line client for the McDonald's China MCP Server (https://mcp.mcd.cn).

Turns every MCP tool into a shell subcommand so agents and scripts can call it
without an MCP host. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "1.1.0"
DEFAULT_URL = "https://mcp.mcd.cn"
DEFAULT_AUTH = Path(__file__).resolve().parent / "auth.json"
PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "mcd-cli"

# Tools that create orders, cancel orders, claim coupons or spend points.
WRITE_TOOLS = {"create-order", "cancel-order", "mall-create-order", "party-order-create",
               "auto-bind-coupons", "draw-lottery", "delivery-create-address"}


class CLIError(Exception):
    pass


def fail(message: str, code: int = 1) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return code


# ---------------------------------------------------------------- credentials

def load_auth(auth_path: Path | None) -> tuple[dict[str, Any], str]:
    """Return (auth, source). Order: --auth file, MCD_MCP_TOKEN env, auth file from env, default file."""
    if auth_path is None and os.environ.get("MCD_MCP_TOKEN"):
        return {"token": os.environ["MCD_MCP_TOKEN"], "url": os.environ.get("MCD_MCP_URL")}, "env:MCD_MCP_TOKEN"
    if auth_path is None:
        env = os.environ.get("MCD_CLI_AUTH") or os.environ.get("MCP_CLI_AUTH")
        auth_path = Path(env).expanduser() if env else DEFAULT_AUTH
    if not auth_path.exists():
        raise CLIError(f"未找到凭证：请设置环境变量 MCD_MCP_TOKEN，或创建 {auth_path}，"
                       '内容如 {"token": "你的 MCP Token"}。Token 在 https://open.mcd.cn/mcp 申请')
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CLIError(f"凭证文件无效: {auth_path}: {exc}") from exc
    if not isinstance(data, dict) or not (data.get("token") or data.get("key")):
        raise CLIError(f"凭证文件必须包含非空 token 字段: {auth_path}")
    if stat.S_IMODE(auth_path.stat().st_mode) & 0o077:
        print(f"警告：凭证文件权限过宽，建议 chmod 600 {auth_path}", file=sys.stderr)
    return data, str(auth_path)


# ---------------------------------------------------------------- MCP client

class MCPClient:
    """Streamable HTTP MCP client: initialize -> notifications/initialized -> tools/*."""

    def __init__(self, auth: dict[str, Any], timeout: float):
        self.timeout = timeout
        base = str(auth.get("url") or DEFAULT_URL)
        parts = urllib.parse.urlsplit(base)
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        if auth.get("key"):
            query["key"] = [str(auth["key"])]
        self.url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path,
                                            urllib.parse.urlencode(query, doseq=True), parts.fragment))
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if auth.get("token"):
            self.headers["Authorization"] = f"Bearer {auth['token']}"
        self._id = 0
        self._ready = False

    def rpc(self, method: str, params: dict[str, Any] | None = None, notification: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            self._id += 1
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params
        req = urllib.request.Request(self.url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                session = resp.headers.get("Mcp-Session-Id")
                if session:
                    self.headers["Mcp-Session-Id"] = session
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise CLIError(f"MCP HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}") from exc
        except urllib.error.URLError as exc:
            raise CLIError(f"无法连接麦当劳 MCP: {exc.reason}") from exc
        if notification and not raw.strip():
            return {}
        msg = parse_body(raw)
        if msg.get("error"):
            err = msg["error"]
            raise CLIError(str(err.get("message", err)) if isinstance(err, dict) else str(err))
        return msg

    def initialize(self) -> None:
        if self._ready:
            return
        self.rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                "clientInfo": {"name": CLIENT_NAME, "version": VERSION}})
        self.rpc("notifications/initialized", notification=True)
        self._ready = True

    def tools(self) -> list[dict[str, Any]]:
        self.initialize()
        return (self.rpc("tools/list", {}).get("result") or {}).get("tools") or []

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        self.initialize()
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}).get("result") or {}
        if result.get("isError"):
            raise CLIError(str(extract_content(result)))
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        return extract_content(result)


def parse_body(raw: str) -> dict[str, Any]:
    """JSON body, or the first JSON `data:` frame of an SSE stream."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                    break
                except json.JSONDecodeError:
                    continue
        else:
            raise CLIError(f"MCP 返回了无法解析的响应: {raw[:300]}")
    return msg if isinstance(msg, dict) else {"result": msg}


def extract_content(result: dict[str, Any]) -> Any:
    content = result.get("content")
    if not isinstance(content, list):
        return result
    texts = [c.get("text") for c in content if isinstance(c, dict) and c.get("text") is not None]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except (TypeError, json.JSONDecodeError):
            return texts[0]
    return content


# ---------------------------------------------------------------- arguments

def norm_key(key: str) -> str:
    return re.sub(r"[-_]", "", key).lower()


def parse_scalar(value: str, schema: dict[str, Any] | None = None) -> Any:
    kind = (schema or {}).get("type")
    if kind in {"object", "array"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise CLIError(f"参数需要 JSON {kind}: {value}") from exc
    if kind == "boolean":
        low = value.lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
        raise CLIError(f"布尔参数值无效: {value}")
    if kind == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise CLIError(f"整数参数值无效: {value}") from exc
    if kind == "number":
        try:
            return float(value) if any(c in value for c in ".eE") else int(value)
        except ValueError as exc:
            raise CLIError(f"数字参数值无效: {value}") from exc
    if kind is None:
        if value[:1] in "{[":
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
    return value


def parse_options(tokens: list[str], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """--be-type 1 / --be_type=1 / --beType 1 all map to the schema property `beType`."""
    props = (schema or {}).get("properties", {})
    lookup = {norm_key(k): k for k in props}
    args: dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("--"):
            raise CLIError(f"不支持位置参数 {tok!r}，请使用 --参数 值；复杂参数可用 call 传 JSON")
        body = tok[2:]
        if "=" in body:
            key, value = body.split("=", 1)
        elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
            key, value = body, tokens[i + 1]
            i += 1
        else:
            key, value = body, "true"
        name = lookup.get(norm_key(key))
        if props and name is None:
            raise CLIError(f"未知参数 --{key}，可用参数：{', '.join(props) or '无'}")
        name = name or key
        args[name] = parse_scalar(value, props.get(name))
        i += 1
    missing = [r for r in (schema or {}).get("required", []) if r not in args]
    if missing:
        raise CLIError("缺少必填参数：" + ", ".join("--" + m for m in missing))
    return args


def find_tool(tools: list[dict[str, Any]], requested: str) -> dict[str, Any] | None:
    for tool in tools:
        if norm_key(str(tool.get("name", ""))) == norm_key(requested):
            return tool
    return None


def describe(tool: dict[str, Any]) -> str:
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required") or [])
    lines = [f"{tool['name']}" + ("  [会改动账户，需用户确认]" if tool["name"] in WRITE_TOOLS else ""), ""]
    lines.append((tool.get("description") or "").strip())
    lines.append("")
    lines.append("参数：")
    props = schema.get("properties") or {}
    if not props:
        lines.append("  （无）")
    for name, p in props.items():
        flag = "必填" if name in required else "可选"
        enum = f" 可选值 {p['enum']}" if p.get("enum") else ""
        desc = (p.get("description") or "").replace("\n", " ")[:80]
        lines.append(f"  --{name} <{p.get('type', 'any')}> {flag}{enum}  {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------- main

USAGE = """用法: mcd-cli [选项] <命令> [参数]

  mcd-cli tools [--names]                列出 MCP 工具（--names 只列名称）
  mcd-cli help <工具名>                   查看工具说明与参数
  mcd-cli <工具名> --参数 值              按工具名直接调用（--be-type / --beType 均可）
  mcd-cli call <工具名> '<JSON>'          用 JSON 对象调用，也可 @文件路径
  mcd-cli config show|path                查看当前凭证来源（Token 已打码）

选项:
  --auth PATH       指定凭证文件（JSON：{"token": "..."}）
  --timeout SEC     请求超时，默认 60
  --json/--compact  单行 JSON 输出；默认缩进 JSON（--pretty）

凭证优先级：--auth > 环境变量 MCD_MCP_TOKEN > 环境变量 MCD_CLI_AUTH 指向的文件 > 程序目录 auth.json
Token 申请：https://open.mcd.cn/mcp"""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    if argv[0] in {"-V", "--version"}:
        print(f"mcd-cli {VERSION}")
        return 0
    auth_path: Path | None = None
    timeout, compact, rest = 60.0, False, []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in {"--json", "--compact"}:
            compact = True
        elif tok == "--pretty":
            compact = False
        elif tok in {"--auth", "--timeout"}:
            if i + 1 >= len(argv):
                return fail(f"{tok} 缺少值")
            i += 1
            if tok == "--auth":
                auth_path = Path(argv[i]).expanduser()
            else:
                try:
                    timeout = float(argv[i])
                except ValueError:
                    return fail("--timeout 必须是数字")
        else:
            rest.append(tok)
        i += 1
    if not rest:
        print(USAGE)
        return 0

    def emit(obj: Any) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=None if compact else 2, default=str))

    try:
        auth, source = load_auth(auth_path)
        cmd = rest[0]
        if cmd == "config":
            action = rest[1] if len(rest) > 1 else "show"
            if action == "path":
                print(source)
            elif action == "show":
                emit({"source": source, "url": auth.get("url") or DEFAULT_URL,
                      "token": "***" + str(auth.get("token") or auth.get("key"))[-4:]})
            else:
                raise CLIError("config 仅支持 show 或 path")
            return 0
        client = MCPClient(auth, timeout)
        if cmd == "tools":
            tools = client.tools()
            if "--names" in rest[1:]:
                for t in tools:
                    print(t["name"] + ("  *" if t["name"] in WRITE_TOOLS else ""))
            else:
                emit(tools)
        elif cmd == "help":
            if len(rest) < 2:
                raise CLIError("用法：mcd-cli help <工具名>")
            tool = find_tool(client.tools(), rest[1])
            if tool is None:
                raise CLIError(f"未知工具: {rest[1]}，运行 mcd-cli tools --names 查看")
            print(describe(tool))
        elif cmd == "call":
            if len(rest) < 2:
                raise CLIError("call 需要工具名")
            tail = rest[2:]
            if tail and not tail[0].startswith("--"):
                raw = tail[0]
                if raw.startswith("@"):
                    raw = Path(raw[1:]).expanduser().read_text(encoding="utf-8")
                try:
                    arguments = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise CLIError(f"call 的参数必须是 JSON: {exc}") from exc
                if not isinstance(arguments, dict) or len(tail) > 1:
                    raise CLIError("call 只接受一个 JSON 对象参数")
                emit(client.call(rest[1], arguments))
            else:
                tool = find_tool(client.tools(), rest[1])
                emit(client.call(tool["name"] if tool else rest[1],
                                 parse_options(tail, tool.get("inputSchema") if tool else None)))
        else:
            tool = find_tool(client.tools(), cmd)
            if tool is None:
                raise CLIError(f"未知工具: {cmd}，运行 mcd-cli tools --names 查看")
            emit(client.call(str(tool["name"]), parse_options(rest[1:], tool.get("inputSchema"))))
        return 0
    except CLIError as exc:
        return fail(str(exc))
    except Exception as exc:  # keep errors JSON-shaped for automation
        return fail(f"内部错误: {exc}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
