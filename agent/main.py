"""AgentMesh agent daemon: connects to the relay and runs a Claude tool-use
loop against this machine's OS tools.

Safety notes (see safety.py):
  - every tool call is audit-logged locally, regardless of outcome
  - /pause and /resume control messages and a local pause file are checked
    before every tool execution and BEFORE the LLM ever sees a turn -- they
    are never routed through Claude, so they can't be spoofed by prompt
    injection in ordinary chat text
  - run_command has no denylist, per project decision -- rate-limited only
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets
import yaml
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from safety import AuditLog, KillSwitch, RateLimiter
from tools import health_check, launch_terminal, run_command, security_report, system_info, updates, users

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR.parent / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"

TOOL_DEFS = [
    {"name": "system_info", "description": "Get OS, CPU, memory, and disk info for this machine.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "health_check", "description": "Check current CPU/memory/disk usage and top processes on this machine.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_updates", "description": "Check for available OS/package updates on this machine.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_users", "description": "List user accounts and who is currently logged in on this machine.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "security_report",
     "description": "Report AV/protection status, pending security updates, and listening network ports "
                     "using native OS tools only. Not a CVE-database vulnerability scanner.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_command",
     "description": "Execute a command on this machine through a chosen interpreter. Fully autonomous, no denylist.",
     "input_schema": {
         "type": "object",
         "properties": {
             "interpreter": {"type": "string", "enum": ["cmd", "powershell", "bash", "sh", "python", "go"]},
             "command": {"type": "string", "description": "Command text, or full source for python/go."},
         },
         "required": ["interpreter", "command"],
     }},
    {"name": "launch_terminal",
     "description": "Open a real, visible interactive terminal window on this machine's desktop session. "
                     "Reports an error instead of failing silently if there is no desktop session.",
     "input_schema": {"type": "object", "properties": {"shell": {"type": "string", "enum": ["default", "powershell"]}}}},
]

DISPATCH = {
    "system_info": lambda args: system_info.run(),
    "health_check": lambda args: health_check.run(),
    "check_updates": lambda args: updates.run(),
    "list_users": lambda args: users.run(),
    "security_report": lambda args: security_report.run(),
    "run_command": lambda args: run_command.run(args["interpreter"], args["command"], args.get("timeout", 120)),
    "launch_terminal": lambda args: launch_terminal.run(args.get("shell", "default")),
}

SYSTEM_PROMPT_TEMPLATE = (
    "You are {agent_id}, an autonomous system-operations agent running on a real {os_name} machine. "
    "You are in a shared chatroom with your human operator and possibly another agent on a different machine. "
    "You can inspect and operate on THIS machine using your tools: system_info, health_check, check_updates, "
    "list_users, security_report, run_command, and launch_terminal. run_command has no restrictions -- you decide "
    "what to run, and you are responsible for the consequences, so be deliberate and explain your reasoning before "
    "acting. Keep chat replies concise. When you run a tool, briefly state why first."
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"missing {CONFIG_PATH} -- copy config.example.yaml to config.yaml and fill it in")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


class Agent:
    def __init__(self, config: dict):
        self.config = config
        self.agent_id = config["agent_id"]
        self.client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = config.get("model", "claude-sonnet-5")
        self.audit = AuditLog(BASE_DIR / f"{self.agent_id}_audit.jsonl")
        self.kill_switch = KillSwitch(BASE_DIR / "agentmesh.pause")
        self.rate_limiter = RateLimiter(config.get("run_command_per_minute", 20))
        self.max_consecutive_agent_turns = config.get("max_consecutive_agent_turns", 6)
        self._consecutive_non_human = 0
        self.history: list[dict] = []
        self.ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self.ws = await websockets.connect(self.config["relay_url"])
        await self.ws.send(json.dumps({"agent_id": self.agent_id, "token": self.config["token"]}))

    async def send(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload))

    async def run(self) -> None:
        await self.connect()
        print(f"[{self.agent_id}] connected to relay")
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await self.handle_message(msg)

    async def handle_message(self, msg: dict) -> None:
        mtype = msg.get("type", "chat")
        sender = msg.get("sender", "?")

        if sender == self.agent_id:
            return  # our own broadcast

        if mtype == "control":
            if msg.get("target") == self.agent_id:
                paused = msg.get("command") == "pause"
                self.kill_switch.set_remote_paused(paused)
                print(f"[{self.agent_id}] {'paused' if paused else 'resumed'} by {sender}")
            return

        if mtype != "chat":
            return  # presence / tool-log messages from others aren't conversation turns

        if sender == "you":
            self._consecutive_non_human = 0
        else:
            self._consecutive_non_human += 1
            if self._consecutive_non_human > self.max_consecutive_agent_turns:
                return  # avoid endless agent<->agent ping-pong burning API calls

        if self.kill_switch.is_paused():
            return

        self.history.append({"role": "user", "content": f"[{sender}] {msg.get('text', '')}"})
        await self.think_and_act()

    async def think_and_act(self) -> None:
        os_name = system_info.run()["os"]
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(agent_id=self.agent_id, os_name=os_name)

        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOL_DEFS,
                messages=self.history,
            )
            self.history.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b.text for b in response.content if b.type == "text"]

            if text_blocks:
                await self.send({"type": "chat", "text": " ".join(text_blocks)})

            if not tool_uses:
                break

            tool_results = []
            for tu in tool_uses:
                result = await self.execute_tool(tu.name, tu.input, rationale=" ".join(text_blocks))
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result)})
            self.history.append({"role": "user", "content": tool_results})

            if response.stop_reason != "tool_use":
                break

    async def execute_tool(self, name: str, args: dict, rationale: str) -> dict:
        if self.kill_switch.is_paused():
            return {"error": "agent is paused, tool execution skipped"}
        if name == "run_command" and not self.rate_limiter.allow():
            return {"error": "rate limit exceeded for run_command, try again shortly"}

        fn = DISPATCH.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}

        try:
            result = await asyncio.to_thread(fn, args)
        except Exception as e:  # tool crashed -- report, don't kill the agent
            result = {"error": str(e)}

        self.audit.record(name, args, result, rationale)
        await self.send({"type": "tool", "tool": name, "output": json.dumps(result)[:2000]})
        return result


async def main() -> None:
    config = load_config()
    agent = Agent(config)
    while True:
        try:
            await agent.run()
        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            print(f"[{agent.agent_id}] connection lost ({e}), retrying in 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
