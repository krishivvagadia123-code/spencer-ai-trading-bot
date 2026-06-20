from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import spencer_quote_server


def _server(monkeypatch):
    monkeypatch.setattr(
        spencer_quote_server,
        "_env_value",
        lambda name: "test-write-token" if name == "SPENCER_WRITE_TOKEN" else "",
    )
    monkeypatch.setattr(
        spencer_quote_server,
        "_set_budget",
        lambda budget: {"ok": True, "budget": budget},
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), spencer_quote_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _post_config(port: int, *, token: str | None = None, origin: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Spencer-Confirm"] = token
    if origin is not None:
        headers["Origin"] = origin
    request = Request(
        f"http://127.0.0.1:{port}/api/bot/config",
        data=json.dumps({"budget": 5000}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    return urlopen(request, timeout=5)


def test_bot_config_requires_write_token_and_echoes_allowed_origin(monkeypatch):
    httpd, thread = _server(monkeypatch)
    try:
        port = httpd.server_address[1]
        try:
            _post_config(
                port,
                origin="https://spencer-ai-trading-bot.vercel.app",
            )
        except HTTPError as exc:
            rejected = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 403
            assert "X-Spencer-Confirm" in rejected["error"]
            assert (
                exc.headers["Access-Control-Allow-Origin"]
                == "https://spencer-ai-trading-bot.vercel.app"
            )
        else:
            raise AssertionError("POST /api/bot/config without token should fail")

        with _post_config(
            port,
            token="test-write-token",
            origin="https://spencer-ai-trading-bot.vercel.app",
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload == {"ok": True, "budget": 5000}
            assert (
                response.headers["Access-Control-Allow-Origin"]
                == "https://spencer-ai-trading-bot.vercel.app"
            )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_cors_does_not_echo_unlisted_origin(monkeypatch):
    httpd, thread = _server(monkeypatch)
    try:
        port = httpd.server_address[1]
        with _post_config(
            port,
            token="test-write-token",
            origin="https://evil.example",
        ) as response:
            assert response.status == 200
            assert response.headers.get("Access-Control-Allow-Origin") is None
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
