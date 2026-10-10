"""Offline tests: a tiny local HTTP server plays the MCP Server, no token or network needed."""

import contextlib
import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mcd_cli  # noqa: E402

TOOLS = [{
    "name": "query-store-coupons",
    "description": "查询门店可用券",
    "inputSchema": {"type": "object", "required": ["storeCode", "orderType", "beType"],
                    "properties": {"storeCode": {"type": "string"}, "orderType": {"type": "integer"},
                                   "beType": {"type": "integer"}, "beCode": {"type": "string"}}},
}, {"name": "create-order", "description": "下单", "inputSchema": {"type": "object", "properties": {}}}]


class FakeMCP(BaseHTTPRequestHandler):
    calls = []
    sse = False

    def log_message(self, *args):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMCP.calls.append((req, self.headers.get("Authorization")))
        if "id" not in req:
            self.send_response(202)
            self.end_headers()
            return
        method = req["method"]
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            body = {"success": True, "code": 200, "data": {"echo": req["params"]["arguments"]}}
            result = {"content": [{"type": "text", "text": json.dumps(body)}]}
        else:
            result = {}
        msg = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result})
        out = (f"event: message\ndata: {msg}\n\n" if FakeMCP.sse else msg).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if FakeMCP.sse else "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class CLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeMCP)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ["MCD_MCP_TOKEN"] = "test-token-1234"
        os.environ["MCD_MCP_URL"] = f"http://127.0.0.1:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeMCP.calls.clear()
        FakeMCP.sse = False

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mcd_cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_kebab_flags_map_to_schema(self):
        code, out, _ = self.run_cli("--json", "query-store-coupons", "--be-type", "1",
                                    "--order-type=1", "--store-code", "1400464")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["echo"], {"beType": 1, "orderType": 1, "storeCode": "1400464"})

    def test_handshake_and_bearer(self):
        self.run_cli("--json", "query-store-coupons", "--beType", "1", "--orderType", "1", "--storeCode", "1")
        methods = [c[0]["method"] for c in FakeMCP.calls]
        self.assertEqual(methods[:2], ["initialize", "notifications/initialized"])
        self.assertEqual(FakeMCP.calls[0][1], "Bearer test-token-1234")

    def test_missing_required(self):
        code, _, err = self.run_cli("query-store-coupons", "--beType", "1")
        self.assertEqual(code, 1)
        self.assertIn("--orderType", err)

    def test_unknown_flag_and_tool(self):
        self.assertIn("未知参数 --foo", self.run_cli("query-store-coupons", "--foo", "1")[2])
        self.assertIn("未知工具", self.run_cli("nope")[2])

    def test_call_json_and_sse(self):
        FakeMCP.sse = True
        code, out, _ = self.run_cli("--json", "call", "query-store-coupons", '{"storeCode":"9"}')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["echo"], {"storeCode": "9"})

    def test_help_marks_write_tools(self):
        self.assertIn("需用户确认", self.run_cli("help", "create-order")[1])
        self.assertIn("create-order  *", self.run_cli("tools", "--names")[1])

    def test_config_masks_token(self):
        out = self.run_cli("config", "show")[1]
        self.assertIn("***1234", out)
        self.assertNotIn("test-token", out)

    def test_parse_scalar(self):
        self.assertEqual(mcd_cli.parse_scalar("[1,2]", {"type": "array"}), [1, 2])
        self.assertIs(mcd_cli.parse_scalar("yes", {"type": "boolean"}), True)
        self.assertEqual(mcd_cli.parse_scalar("3", {"type": "number"}), 3)
        with self.assertRaises(mcd_cli.CLIError):
            mcd_cli.parse_scalar("x", {"type": "integer"})


if __name__ == "__main__":
    unittest.main()
