# SolidCraft 0.15 agent chat — configuration findings

0.15 ships an in-app **Agent chat** panel (`ui.agent_chat`, answers render as
Markdown). It works on the open design through SolidCraft's own tools; its edits
show live and undo as one step per message.

## How it's configured
Preferences > AI. Relevant prefs (seen in
`~/Library/Application Support/SolidCraft/app.ron` under `solidcraft.prefs` →
`preferences`): `ai_features`, `ai_permissions` ("edits"), `agents` (list),
`agent_default`, `agent_models`, `agent_permissions`, `agent_always_allow`,
`agent_chat_turn_limit` (24), `agent_chat_side`.

"Add agent" offers three kinds (`ui.ai_add_*`):
1. **Installed agent** — a coding agent already on the machine (Claude Code / Codex-style).
2. **Custom command** — your own command/args.
3. **OpenAI-compatible API** (`ui.ai_add_api`) — fields: **Name**, **Base URL**
   (`ui.ai_base_url`), **Model** (`ui.ai_model`), **API key** (`ui.ai_key`).

## Pointing it at Crusoe Nemotron (OpenAI-compatible)
Yes, directly supported. In Preferences > AI → Add agent → OpenAI-compatible API:
- Name: `Crusoe Nemotron`
- Base URL: `https://api.inference.crusoecloud.com/v1`
- Model: the Nemotron model id served there
- API key: the Crusoe key (stored in the system keychain, never in settings;
  `ui.ai_key_note`; a key is only sent over HTTPS — Crusoe is HTTPS so fine).

Caveats from the strings:
- `ui.agent_chat_desktop_only`: the chat needs the desktop app.
- `ui.agent_chat_no_control` / `ui.ai_http_key` / `ui.ai_http_busy`: the chat
  uses the same local control endpoint; a bad key or rate limit surfaces there.
- Tool permissions for what the agent may do without asking are set in
  Preferences > AI (`ai_permissions`, `agent_always_allow`).

Not verified end-to-end (no live Nemotron key wired in a 10-min box); the config
surface and fields are confirmed from the binary strings + app.ron, so the path
is a plain OpenAI-compatible endpoint entry.
