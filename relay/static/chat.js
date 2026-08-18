const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const form = document.getElementById("composer");
const input = document.getElementById("input");

const proto = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${proto}://${location.host}/ws/chat?token=${encodeURIComponent(token)}`);

ws.onopen = () => { statusEl.textContent = "connected"; };
ws.onclose = (ev) => { statusEl.textContent = `disconnected (${ev.code})`; };
ws.onerror = () => { statusEl.textContent = "error"; };

ws.onmessage = (ev) => {
  let msg;
  try { msg = JSON.parse(ev.data); } catch { return; }
  appendMessage(msg);
};

function appendMessage(msg) {
  const div = document.createElement("div");
  const type = msg.type || "chat";
  div.className = `msg ${type}`;

  const time = msg.ts ? new Date(msg.ts).toLocaleTimeString() : "";

  if (type === "presence") {
    div.textContent = `${msg.sender} is ${msg.state} ${time}`;
  } else if (type === "control") {
    div.textContent = `${msg.sender} sent ${msg.command} -> ${msg.target} ${time}`;
  } else if (type === "tool") {
    div.innerHTML = `<span class="sender">${escapeHtml(msg.sender)}</span> ran <b>${escapeHtml(msg.tool || "")}</b><span class="ts">${time}</span>\n${escapeHtml(msg.output || "")}`;
  } else {
    div.innerHTML = `<span class="sender">${escapeHtml(msg.sender || "?")}</span>${escapeHtml(msg.text || "")}<span class="ts">${time}</span>`;
  }
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  ws.send(text);
  input.value = "";
});
