# Switching Hermes to an LM Studio model: worked case (2026-08-21)

## Goal
User (Ruslan) asked to switch Hermes's active model from cloud (routerai / deepseek-v4-flash) to a local LM Studio model.

## Steps that worked
1. **Probe LM Studio**:
   - `curl -s http://localhost:1234/api/v0/models` → JSON list; pick `state: "loaded"` entry. That session: `esatapedico/qwen3.8-27b-nvfp4-mtp-gguf/qwen3.8-27b-nvfp4-mtp-very-low.gguf`, `max_context_length: 262144`, **`loaded_context_length: 130048`**, `capabilities: ["tool_use"]`, type `vlm`.
   - `curl -s http://localhost:1234/v1/models` → OpenAI-compatible ids (same list).
2. **Discovered the built-in `lmstudio` provider** (hermes_cli/auth.py:285):
   - `ProviderConfig(id="lmstudio", inference_base_url="http://127.0.0.1:1234/v1", api_key_env_vars=("LM_API_KEY",), base_url_env_var="LM_BASE_URL")`.
   - Also referenced as a first-class provider in `hermes_cli/models.py:1162` and given special `reasoning_effort` (top-level param, not extra_body) handling in the compression/summary path — `_is_lmstudio_summary` check in `agent/chat_completion_helpers.py:2979` matches `agent.provider == "lmstudio"`.
   - **Conclusion: use `provider: lmstudio`, NOT `custom:lmstudio`.** A `custom:lmstudio` entry requires a `providers:`/`custom_providers:` config block and skips the lmstudio-specific reasoning handling.
3. **Config changes via CLI** (agent patch/write_file tools REFUSE to touch ~/.hermes/config.yaml — "security-sensitive configuration"; use `hermes config set`):
   ```bash
   cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d-%H%M%S)
   hermes config set model.base_url http://127.0.0.1:1234/v1
   hermes config set model.default "esatapedico/qwen3.8-27b-nvfp4-mtp-gguf/qwen3.8-27b-nvfp4-mtp-very-low.gguf"
   hermes config set model.provider lmstudio
   hermes config set model.context_length 130048     # = loaded_context_length, prevents probe-down
   # cleanup if a custom entry was created by mistake:
   hermes config unset providers.lmstudio
   ```
   Note: `hermes config set providers.lmstudio.base_url ...` DOES work but is the wrong path — creates a custom-provider entry that shadows nothing useful; the built-in provider is the right one.
4. **Verified resolution from the repo venv**:
   ```bash
   cd ~/.hermes/hermes-agent && ./venv/Scripts/python.exe -c "
   import sys; sys.path.insert(0, '.')
   from hermes_cli.runtime_provider import resolve_runtime_provider
   r = resolve_runtime_provider(requested='lmstudio')
   print(r['provider'], r['api_mode'], r['base_url'], bool(r['api_key']))"
   # → lmstudio chat_completions http://127.0.0.1:1234/v1 True
   ```
5. **End-to-end proof**: `hermes chat -q "..." -m "<model id>" --provider lmstudio` → answered in ~42s (1 user, 2 tool calls). Expected latency for a 27B local model.
6. **Told the user**: current Feishu session keeps running on the old model (model is fixed at session start); they must `/new` or `/reset` to pick up the LM Studio model. Warned: qwen3.8-27b is a thinking model (`reasoning_content` in responses) → `/reasoning low|medium` if loops/resets appear. Backup path: `~/.hermes/config.yaml.bak-20260821-154458`.

## Pitfalls hit
- `hermes config set model.default` with a very long GGUF id worked fine (id contains slashes and dots — quote it in bash).
- The venv python for the repo is `./venv/Scripts/python.exe` (Windows), not `.venv`.
- `get_model_metadata` import name was wrong (`agent.model_metadata.get_model_metadata` doesn't exist); the real API is `resolve_runtime_provider` / `get_model_capabilities` in `agent/models_dev.py` — but for a plain switch, `resolve_runtime_provider(requested='lmstudio')` is enough.
- First patch attempt at `custom:lmstudio` required adding a `providers:` entry AND had no reasoning handling — reverted before finalizing. Always check for a built-in provider id before inventing a custom one (`hermes_cli/models.py` ProviderEntry list / `hermes_cli/auth.py` ProviderConfig registry).

## LM Studio API cheatsheet (repeat of main reference)
- `GET /v1/models` — ids only
- `GET /api/v0/models` — `state`, `max_context_length`, `loaded_context_length`, `capabilities`, `quantization`, `arch`, `type` (llm/vlm/embeddings)
- Chat: `POST /v1/chat/completions` with `{"model": "<id>", "messages": [...], "max_tokens": N}` — response includes `reasoning_content` for thinking models (content may be empty when reasoning consumed the budget).
