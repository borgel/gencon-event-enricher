# GenCon Event Enricher

A static webpage that lets you browse and filter all GenCon events, enriched with BoardGameGeek (BGG) ratings and metadata. Pre-processed offline from periodic data dumps; no live API calls; hosted on GitHub Pages.

## Source data

- `gencon_events-*.xlsx` — from <https://www.gencon.com/downloads/events.xlsx> (committed snapshot).
- `boardgames_ranks-*.csv` — from BGG's data dump at <https://boardgamegeek.com/data_dumps/bg_ranks> (committed snapshot; download requires login).

The pipeline auto-globs the latest matching dump in the repo root, so refreshing data is just a matter of dropping in a newer file and re-running.

## Pipeline

```bash
# one-time
uv sync --all-groups
uv run playwright install chromium

# whenever new dumps land — single-command driver:
./run.sh                                # build only (deterministic, free, ~3 min)
./run.sh --with-agent                   # build → agent → rebuild
./run.sh --with-agent --verbose         # show per-batch progress
./run.sh --with-agent --backend claude  # use Claude API instead of local Ollama

# or run the steps directly:
uv run python -m pipeline.build
uv run python -m pipeline.match_with_agent --dry-run --limit 5  # preview prompts
uv run python -m pipeline.match_with_agent                      # default: ollama
uv run python -m pipeline.build                                 # re-run to integrate

# tests
uv run pytest -v
```

`build.py` produces:

- `docs/data/events.json` — consumed by the webpage.
- `pipeline/agent-input.json` — list of unmatched groups (with fuzzy candidates) for the optional agent runner.

## Webpage

`docs/` is the GitHub Pages source root — plain HTML/CSS/ES-modules, no build step.

To run locally:

```bash
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```

To deploy: GitHub repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main` → Folder: `/docs`. Pushing to `main` is the deploy.

## Architecture

Two subsystems, separated by `docs/data/events.json`:

1. **Python pipeline** (`pipeline/build.py`) — joins GenCon + BGG with a four-stage matching cascade:
   1. Manual overrides (`pipeline/mappings.yaml`)
   2. Agent overrides (`pipeline/mappings.agent.yaml`)
   3. Exact match after normalization
   4. Fuzzy match (rapidfuzz `token_set_ratio`, threshold 90)

   Anything still unmatched is dumped to `pipeline/agent-input.json`.

2. **Static webpage** (`docs/`) — vanilla JS, hand-rolled virtualized table (50-line module), `MiniSearch` for free-text indexing, filter state synced to URL hash, saved-events in `localStorage`.

## Agent runner

`pipeline/match_with_agent.py` resolves unmatched events by sending each batch to a model. The model is told the GenCon event title/system/description plus the top-5 BGG fuzzy candidates, and returns either a BGG id or `null` ("not a tabletop game"). Validated responses (against `pipeline/agent_response_schema.json`) land in `pipeline/mappings.agent.yaml`.

The runner is resumable — keys already present in `mappings.yaml` or `mappings.agent.yaml` are skipped on subsequent runs.

Useful flags:

- `--backend openai|ollama|claude` — which matcher to use (default: `openai`).
- `--model NAME` — override the per-backend default model.
- `--base-url URL` — for `--backend openai`, where to find the server.
- `--max-tokens N` — output budget per request (default 16384). Raise on reasoning models.
- `--no-strict-schema` — for `--backend openai`, fall back to `json_object` if the server rejects `json_schema`.
- `--dry-run` — print the prompt(s) without invoking the model.
- `--limit N` — cap groups processed in this run.
- `--batch-size N` — events per request (default 200 for openai/ollama, 50 for claude).
- `--popular-bgg-size N` — how many of the most-rated BGG entries to include in the prompt as a general catalog. Defaults: 500 (openai/ollama), 5000 (claude). Set to 0 to omit entirely. Per-batch fuzzy candidates are always included regardless.
- `-v` / `--verbose` — per-batch progress with token + cost stats.

### Backend: OpenAI-compatible server (default — local MLX, LM Studio, etc.)

`--backend openai` POSTs to `<base_url>/chat/completions` with a JSON-schema-constrained request. Works against any server implementing the OpenAI Chat Completions API. On Apple Silicon, **MLX-accelerated serving is 1.5–2.5× faster than llama.cpp** for the same model.

**Defaults** (override via env vars or flags):
- `base_url`: `http://localhost:1234/v1` (LM Studio's port)
- `model`: `qwen/qwen3.5-9b`
- `OPENAI_BASE_URL` / `OPENAI_MODEL` env vars override the defaults
- `--base-url` / `--model` CLI flags override env vars

#### LM Studio (GUI; the default config)

1. Download from <https://lmstudio.ai>.
2. In the Discover tab, search for an MLX model (e.g. `qwen3.5-9b`, `qwen2.5-14b-instruct-mlx`). Look for the "MLX" tag.
3. In the Developer / Local Server tab, **load the model** and **start the server** (default port 1234).
4. Run the matcher:

```bash
./run.sh --with-agent --verbose
```

That's it. `./run.sh` will pre-flight a check that the server is reachable and warn you helpfully if it's not.

To verify the model id LM Studio is exposing:
```bash
curl http://localhost:1234/v1/models | python3 -m json.tool
```
If your loaded model has a different id, override with `--model <id>` or `OPENAI_MODEL=<id>`.

#### mlx-lm (headless / scriptable)

Pure CLI, no GUI required:

```bash
uv tool install mlx-lm
mlx_lm.server --model mlx-community/Qwen2.5-14B-Instruct-4bit  # default port :8080

# In another shell:
OPENAI_BASE_URL=http://localhost:8080/v1 \
  OPENAI_MODEL=mlx-community/Qwen2.5-14B-Instruct-4bit \
  ./run.sh --with-agent --verbose
```

The server stays up across runs — model loaded once, stateless requests. Best for cron / overnight / automated workflows.

#### Other compatible servers

The same `--backend openai` works with: vLLM (`:8000/v1`), llama.cpp's `llama-server` (`:8080/v1`), `llama-cpp-python`'s server, and OpenAI proper (set `OPENAI_API_KEY` and `--base-url https://api.openai.com/v1`).

### Backend: Ollama (local, free)

If you'd rather use Ollama instead of an OpenAI-compatible server:

```bash
brew install ollama
ollama serve                    # auto-starts as service after install
ollama pull qwen2.5:14b
./run.sh --with-agent --backend ollama --model qwen2.5:14b
```

Ollama uses llama.cpp under the hood (no MLX), so on Apple Silicon expect ~2× slower than the openai/MLX path for the same model. Trade-off: Ollama auto-starts headless, no GUI dance.

Other vetted models (see commit history for benchmark results): `deepseek-r1:14b` (similar quality, slightly slower), `llama3.1:8b` (faster but hallucinates more).

### Backend: Claude (cloud, costs tokens)

Runs against the Anthropic API via the `claude` CLI. Requires `claude` on `PATH` and authentication already configured (Claude Code login or `ANTHROPIC_API_KEY`).

```bash
./run.sh --with-agent --backend claude --model claude-haiku-4-5
```

Default model is `claude-haiku-4-5` (cheap, ~$0.05/event at our prompt size). `claude-sonnet-4-6` and `claude-opus-4-7` are also fine if you want higher quality at higher cost.

## Repository layout

```
gencon-event-enricher/
├── boardgames_ranks-*.csv          # source dump
├── gencon_events-*.xlsx            # source dump
├── pyproject.toml
├── pipeline/                       # python build + agent runner
└── docs/                           # GitHub Pages site
    ├── index.html
    ├── styles.css
    ├── app/                        # vanilla ES modules
    └── data/events.json            # build output
```

## Testing

`uv run pytest` runs:

- Pipeline unit tests (parsers, matching cascade, group-key derivation, mappings I/O, JSON emission).
- A pipeline integration test against tiny xlsx + CSV fixtures.
- Agent-runner tests using an injected fake `ClaudeInvoker` — no real API calls.
- A Playwright-driven test for filter URL-hash round-tripping.
- A headless smoke test that loads the page against a tiny `events.json`, applies a filter, and clicks through to the detail panel.
