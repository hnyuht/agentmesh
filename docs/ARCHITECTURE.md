# AgentMesh architecture

## Message types on the relay

Every message broadcast through the relay is JSON with a `type` field:

| type       | sender fields                          | meaning                                                          |
|------------|-----------------------------------------|-------------------------------------------------------------------|
| `chat`     | `sender`, `text`                        | conversational turn from a human viewer or an agent               |
| `tool`     | `sender`, `tool`, `output`              | record of a tool call an agent just made                          |
| `presence` | `sender`, `state` (`online`/`offline`)  | connect/disconnect notice                                         |
| `control`  | `sender`, `command`, `target`           | `/pause` or `/resume` issued by the viewer at a specific agent_id  |

`sender` is always set/overwritten by the relay (agents can't spoof another
agent's identity; only the literal string `"you"` is used for the human
viewer).

## Agent conversation loop

Each agent keeps its own Anthropic message history (`Agent.history`). Every
incoming `chat` message not from itself becomes a `user` turn
(`"[sender] text"`). The agent then calls Claude with the full tool
definition set; if Claude requests a tool, the agent runs it locally,
appends a `tool_result` turn, and loops until Claude stops requesting tools,
posting any text output as a `chat` message along the way.

`control` messages are intercepted in `Agent.handle_message` *before* they
would ever become part of that history — they update `KillSwitch` state
directly and return, so a pause/resume can never be influenced by what the
model itself generates or by injected text in someone else's chat message.

## Why outbound-only connections

Both the relay and every agent only ever make/accept WebSocket connections
that agents initiate outward to the relay. Combined with the relay binding
to the Tailscale interface only, this means no machine in the mesh needs an
inbound firewall rule or port forward, and nothing is reachable from the
public internet at all.
