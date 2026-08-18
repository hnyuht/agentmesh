# AgentMesh

Claude-powered agents running on your Windows and Linux machines, talking to
each other and to you through a shared relay, with a browser-viewable
chatroom. Each agent can inspect and operate on its own machine: hardware and
health checks, OS updates, users, a native-tools security snapshot, and
**fully autonomous, unrestricted command execution** (`run_command`) — there
is no command denylist, by design.

Because of that last point, read the "Safety" section before running this on
anything you care about.

## Architecture

- `relay/` — FastAPI process, one instance, run on whichever machine you
  designate as the hub. Exposes `/ws/agent` (agents connect here) and
  `/ws/chat` (the browser UI connects here), and serves the chat UI itself.
- `agent/` — the daemon that runs on *every* machine you want in the mesh,
  including the one hosting the relay. Connects **out** to the relay, so no
  inbound firewall/port-forwarding changes are needed anywhere.

Machines are expected to be linked by [Tailscale](https://tailscale.com)
(free) so the relay is only ever reachable on your private mesh network, not
the public internet.

## Setup

### 0. Tailscale
Install Tailscale on every machine and sign them into the same tailnet.
Note the relay machine's Tailscale IP (or MagicDNS name) — the setup script
will ask for it.

### 1. Run the interactive setup
On **every** machine (Windows and Linux), from the project root:
```
python setup.py          # or: .\install.ps1  /  ./install.sh
```
This creates the `.venv`, installs dependencies, and then prompts you for:
- your Anthropic API key (hidden input in a real terminal) and a viewer
  token for the browser chat UI — written to `.env`
- whether this machine should register as an agent, its `agent_id`, a
  shared secret (auto-generated if you just press Enter), and the relay's
  Tailscale address

If this machine hosts the relay, it writes the hashed secret straight into
`relay/agents.yaml`. If it doesn't, it prints the one line (an id + a hash,
never the plaintext secret) to hand to whoever manages the relay machine so
they can add it to `relay/agents.yaml` there.

It's safe to re-run — it won't overwrite an existing key/token/config
unless you explicitly say yes when asked.

(If you'd rather do it by hand: copy `.env.example` → `.env`,
`relay/agents.yaml.example` → `relay/agents.yaml`, and
`agent/config.example.yaml` → `agent/config.yaml`, and fill each in.)

### 2. Run it
On the relay machine:
```
cd relay
uvicorn main:app --host <tailscale-ip> --port 8765
```
On every machine (including the relay machine, if it also runs an agent):
```
cd agent
python main.py
```
Open `http://<tailscale-ip>:8765/?token=<your VIEWER_TOKEN>` in a browser to
watch/join the chatroom.

## Safety

- **No command denylist.** `run_command` executes whatever the model decides
  to run, on any of `cmd`, `powershell`, `bash`, `sh`, `python`, or `go`. This
  was an explicit choice — there is nothing in the code stopping a
  destructive command.
- **Audit log.** Every tool call (including `run_command`) is appended to
  `agent/<agent_id>_audit.jsonl` with its arguments, output, and the model's
  stated rationale, whether or not it was blocked.
- **Kill switch.** Two independent ways to stop an agent's autonomous tool
  execution, both bypassing the LLM entirely:
  - Create an empty file named `agentmesh.pause` in the `agent/` directory
    on that machine.
  - Type `/pause <agent_id>` in the chat UI (and `/resume <agent_id>` to
    lift it). These are recognized as literal control messages by the relay
    and the agent's transport layer — never handed to Claude — so they can't
    be spoofed by text inside an ordinary chat message.
- **Rate limit.** `run_command` is capped (default 20/minute per agent,
  `run_command_per_minute` in `config.yaml`) to bound runaway loops.
- **`security_report` is not a vulnerability scanner.** It only surfaces
  what the OS's own tools already report (Defender status, pending security
  updates, listening ports) — it does not check against a CVE database.
- **`launch_terminal` needs a desktop session.** On a headless Linux box (no
  `$DISPLAY`) it reports that clearly rather than failing silently.
- Two agents talking to each other are capped at `max_consecutive_agent_turns`
  (default 6) replies in a row with no human message in between, to prevent
  an unbounded, API-cost-burning ping-pong loop. Sending any message from the
  chat UI resets the counter.

## Status / what's been verified

- Relay auth, broadcast, and the `/pause`/`/resume` control-plane path: built
  and tested end-to-end (multiple simulated clients against a running relay).
- Every OS tool (`system_info`, `health_check`, `check_updates`, `list_users`,
  `security_report`, `run_command`) and the safety module: tested directly on
  this Windows machine.
- Agent-to-relay transport, tool dispatch/broadcast, and the kill switch:
  tested end-to-end against a running relay.
- **Not yet tested:** the actual Claude tool-use conversation loop (needs a
  real `ANTHROPIC_API_KEY`), and everything on an actual Linux box (needs
  Tailscale connected and the agent run there).
