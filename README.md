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

- `--backend ollama|claude` — which matcher to use (default: `ollama`).
- `--model NAME` — override the per-backend default model.
- `--dry-run` — print the prompt(s) without invoking the model.
- `--limit N` — cap groups processed in this run.
- `--batch-size N` — events per request (default 50).
- `-v` / `--verbose` — per-batch progress with token + cost stats.

### Backend: Ollama (default, local, free)

Runs against a local model server. Setup once:

```bash
brew install ollama          # macOS
# (or download from https://ollama.com)

# In one shell, start the server (it auto-starts as a service after install):
ollama serve

# In another, pull a model. Recommended:
ollama pull qwen2.5:14b      # default; ~9 GB, good at JSON/structured output
# Alternatives:
ollama pull llama3.1:8b      # ~5 GB, faster, slightly less precise
ollama pull qwen2.5:32b      # ~20 GB, higher quality if you have RAM/GPU

# Verify:
ollama run qwen2.5:14b "say hi briefly"

# Then run the pipeline:
./run.sh --with-agent
```

The runner POSTs to `http://localhost:11434/api/generate` with `format: json` and `options.num_ctx: 65536` (the BGG popular-5k slice plus events comes to ~50k tokens). No API key. No cost.

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
