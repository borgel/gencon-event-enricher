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

# whenever new dumps land
uv run python -m pipeline.build
# optional — let an LLM agent resolve unmatched events (requires `claude` CLI on PATH)
uv run python -m pipeline.match_with_agent --dry-run --limit 5    # preview
uv run python -m pipeline.match_with_agent                        # spend tokens
uv run python -m pipeline.build                                   # re-run to integrate agent results

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

`pipeline/match_with_agent.py` shells out to `claude -p ... --output-format json` with a prompt containing the BGG list + a batch of unmatched events. Validated responses (against `pipeline/agent_response_schema.json`) land in `pipeline/mappings.agent.yaml`. Requires the `claude` CLI on `PATH` and `ANTHROPIC_API_KEY` set.

Useful flags:

- `--dry-run` — print the prompt(s) without spending tokens.
- `--limit N` — cap groups processed in this run (resumable across runs).
- `--batch-size N` — adjust how many groups go in each Claude invocation (default 50).

The runner is resumable: a key already present in `mappings.yaml` or `mappings.agent.yaml` is skipped on subsequent runs, so you can iterate cheaply.

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
