from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import spencer_quote_server


def _request(port: int, path: str, *, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _server(brain_dir, monkeypatch):
    monkeypatch.setattr(spencer_quote_server, "BRAIN_DIR", brain_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), spencer_quote_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def test_brain_status_search_context_and_note_endpoints(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Doctrine.md").write_text(
        "# Doctrine\n\nSpencer is paper-only and studies [[RELIANCE]].\n",
        encoding="utf-8",
    )
    (brain / "RELIANCE.md").write_text("# RELIANCE\n\nOne-stock research.\n", encoding="utf-8")
    httpd, thread = _server(brain, monkeypatch)
    try:
        port = httpd.server_address[1]
        _, status = _request(port, "/api/brain/status")
        _, search = _request(port, "/api/brain/search?q=paper-only")
        _, context = _request(port, "/api/brain/context?q=paper-only")
        _, note = _request(port, "/api/brain/note?path=Doctrine")
        _, graph = _request(port, "/api/brain/graph")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert status["primary"] is True
    assert search["results"][0]["title"] == "Doctrine"
    assert context["citations"]
    assert note["note"]["wikilink"] == "[[Doctrine]]"
    assert graph["edges"] == [{"source": "Doctrine", "target": "RELIANCE"}]


def test_brain_capture_requires_confirmation_and_persists(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    httpd, thread = _server(brain, monkeypatch)
    try:
        port = httpd.server_address[1]
        try:
            _request(port, "/api/brain/capture", payload={"title": "No", "content": "No"})
        except HTTPError as exc:
            rejected = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
        _, created = _request(
            port,
            "/api/brain/capture",
            payload={
                "confirmed": True,
                "title": "Operator decision",
                "content": "Keep Spencer paper-only.",
                "kind": "decision",
                "confidence": "verified",
            },
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert "confirmed=true" in rejected["error"]
    assert created["ok"] is True
    assert (brain / created["created"]).exists()


def test_chat_falls_back_to_local_obsidian_recall_without_key(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Doctrine.md").write_text(
        "# Doctrine\n\nSpencer is permanently paper-only.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(spencer_quote_server, "BRAIN_DIR", brain)
    monkeypatch.setattr(spencer_quote_server, "_env_value", lambda name: "")

    result = spencer_quote_server._brain_chat("Is Spencer paper-only?")

    assert result["ok"] is True
    assert result["mode"] == "local-recall"
    assert result["citations"][0]["wikilink"] == "[[Doctrine]]"
    assert result["llmError"]
