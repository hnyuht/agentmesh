"""AgentMesh relay: WebSocket hub + browser chatroom.

Two endpoints:
  /ws/agent  - agents authenticate with {agent_id, token} as their first message
  /ws/chat   - the human viewer authenticates with ?token=... query param

Every message that passes through is broadcast to all connected sockets and
appended to chatlog.jsonl for durability/audit. /pause and /resume from the
viewer are relayed as a distinct "control" message type -- agents must treat
these as authoritative and never route them through their LLM loop.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from auth import hash_secret, load_agents, verify_agent, verify_viewer

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR.parent / ".env")

AGENTS_PATH = BASE_DIR / "agents.yaml"
CHATLOG_PATH = BASE_DIR / "chatlog.jsonl"
VIEWER_TOKEN_HASH = hash_secret(os.environ["VIEWER_TOKEN"]) if os.environ.get("VIEWER_TOKEN") else None

app = FastAPI()


class ConnectionManager:
    def __init__(self) -> None:
        self.sockets: dict[str, WebSocket] = {}  # identity -> socket

    async def connect(self, identity: str, ws: WebSocket) -> None:
        self.sockets[identity] = ws

    def disconnect(self, identity: str) -> None:
        self.sockets.pop(identity, None)

    async def broadcast(self, message: dict) -> None:
        message.setdefault("ts", datetime.now(timezone.utc).isoformat())
        line = json.dumps(message, ensure_ascii=False)
        with CHATLOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        dead = []
        for identity, sock in self.sockets.items():
            try:
                await sock.send_text(line)
            except Exception:
                dead.append(identity)
        for identity in dead:
            self.disconnect(identity)


manager = ConnectionManager()


@app.websocket("/ws/agent")
async def agent_socket(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
        hello = json.loads(raw)
        agent_id = hello.get("agent_id", "")
        token = hello.get("token", "")
    except Exception:
        await ws.close(code=4400)
        return

    agents = load_agents(AGENTS_PATH)
    if not verify_agent(agents, agent_id, token):
        await ws.close(code=4401)
        return

    await manager.connect(agent_id, ws)
    await manager.broadcast({"type": "presence", "sender": agent_id, "state": "online"})
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            payload["sender"] = agent_id
            payload.setdefault("type", "chat")
            await manager.broadcast(payload)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(agent_id)
        await manager.broadcast({"type": "presence", "sender": agent_id, "state": "offline"})


@app.websocket("/ws/chat")
async def chat_socket(ws: WebSocket) -> None:
    await ws.accept()
    token = ws.query_params.get("token", "")
    if not verify_viewer(VIEWER_TOKEN_HASH, token):
        await ws.close(code=4401)
        return

    identity = f"viewer-{id(ws)}"
    await manager.connect(identity, ws)
    await manager.broadcast({"type": "presence", "sender": "you", "state": "online"})
    try:
        while True:
            raw = await ws.receive_text()
            text = raw.strip()
            if text.startswith("/pause ") or text.startswith("/resume "):
                cmd, target = text.split(" ", 1)
                await manager.broadcast(
                    {"type": "control", "sender": "you", "command": cmd[1:], "target": target.strip()}
                )
                continue
            await manager.broadcast({"type": "chat", "sender": "you", "text": text})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(identity)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
