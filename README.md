<h1 align="center">gundog</h1>

<p align="center">
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/v/gundog" alt="PyPI"></a>
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/pyversions/gundog" alt="Python"></a>
  <a href="https://github.com/adhityaravi/gundog/actions"><img src="https://img.shields.io/github/actions/workflow/status/adhityaravi/gundog/pull_request.yaml?label=CI" alt="CI"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
</p>

<p align="center">
  <img src="assets/demo_webui.gif" alt="gundog demo" width="540">
</p>

Gundog is a local semantic retrieval engine for your high volume corpus. It finds relevant code and documentation by matching the semantics of your query and not just matching keywords.

Point it at your docs or code or both. It embeds everything into vectors, builds a similarity graph connecting related files, and combines semantic search with keyword matching. Ask "how does auth work?" and it retrieves the login handler, session middleware, and the ADR that explains why you chose JWT even if none of them contain the word "auth".

## Why?

I wanted a clean map of all related data chunks from wide spread data sources based on a natural language query. [`SeaGOAT`](https://github.com/kantord/SeaGOAT) provides rather a ranked but flat and accurate pointer to specific data chunks from a single git repository. Basically, I wanted a [Obsidian graph view](https://help.obsidian.md/plugins/graph) of my docs controlled based on a natural language query without having to go through the pain of using.. well.. Obsidian.

Gundog builds these connections across repositories/data sources automatically. Vector search finds semantically related content, BM25 catches exact keyword matches, and graph expansion surfaces files you didn't know to look for.

## Performance

Gundog uses [ONNX Runtime](https://onnxruntime.ai/) and [HNSW](https://github.com/nmslib/hnswlib) indexing by default for fast queries:

<div align="center">

| Metric | Value |
|--------|-------|
| Query latency | ~15ms (after model warmup) |
| First query | ~200-300ms (model loading) |
| Accuracy | 96-100% |
| Index time | ~1 min per 100 files (depends on no. of threads) |

</div>

*Based on personal testing with 60-120 files and 50 queries. Not extensively validated at scale. Your mileage may vary. See [`benchmark/BENCHMARK.md`](benchmark/BENCHMARK.md) for details.*

## Install

```bash
pip install gundog[client]    # full install with daemon + TUI + indexing

pip install gundog            # server only (daemon + indexing)
pip install gundog-client     # client only (TUI + query)
```

### Or from source

```bash
git clone https://github.com/adhityaravi/gundog.git
cd gundog
uv sync
uv run gundog --help
```

## Quick Start

**1. Index your stuff:**

```bash
gundog index
```

First run downloads the embedding model (~130MB) and converts it to ONNX format (cached at `~/.cache/gundog/onnx/` for reuse across projects using the same model). Subsequent runs are incremental and only re-index changed files.

**2. Start the daemon and register your index:**

```bash
gundog daemon start
gundog daemon add myproject .
```

**3. Search:**

```bash
gundog query "database connection pooling"

# or launch the interactive TUI
gundog tui

# stop the daemon if you will
gundog daemon stop
```

Returns ranked results with file paths and relevance scores. The daemon keeps the model loaded for instant queries (~15ms). The TUI provides an interactive interface with real-time search, vim-style navigation, and a visual graph.

## Commands

### `gundog index`

Scans your configured sources, embeds the content, and builds a searchable index.

```bash
gundog index                    # uses .gundog/config.yaml
gundog index -c /path/to.yaml   # custom config file
gundog index --rebuild          # fresh index from scratch
```

### `gundog daemon`

Runs a persistent background service for fast queries. The daemon keeps the embedding model loaded in memory, making subsequent queries instant (~15ms vs ~300ms cold start).

```bash
gundog daemon start                           # start daemon (bootstraps config if needed)
gundog daemon start --foreground              # run in foreground (for debugging)
gundog daemon stop                            # stop daemon
gundog daemon status                          # check if daemon is running

# Index management
gundog daemon add myproject /path/to/project  # register an index
gundog daemon remove myproject                # unregister an index
gundog daemon list                            # list registered indexes
```

The daemon also serves a web UI at the same address for interactive queries with a visual graph. File links are auto-detected from git repos - files in a git repo with a remote get clickable links to GitHub/GitLab.

### `gundog query`

Finds relevant files for a natural language query. **Requires the daemon to be running.**

```bash
gundog query "error handling strategy"
gundog query "authentication" --top 5                        # limit results
gundog query "auth" --index myproject                        # use specific index
gundog query "auth" --daemon http://192.168.1.10:7676        # use specific daemon
```

The `gundog query` command requires the daemon to be running. Daemon settings are stored at `~/.config/gundog/daemon.yaml`.

### `gundog tui`

Launches an interactive TUI for exploring search results with vim-style navigation and a visual relation graph.

<p align="center">
  <img src="assets/demo_tui.gif" alt="gundog TUI" width="540">
</p>

```bash
gundog tui                                        # connect to daemon from config
gundog tui --daemon http://192.168.1.10:7676      # connect to specific daemon
gundog tui --daemon https://gundog.example.com   # connect over HTTPS
```

The TUI connects to the daemon over websocket and provides:
- Real-time search with debounced input
- Syntax-highlighted file preview (local only for now)
- Index switching on the fly
- Daemon URL configuration

#### TUI Keybindings

| Key | Action |
|-----|--------|
| `/` | Focus search input |
| `j` / `↓` | Next result |
| `k` / `↑` | Previous result |
| `g` / `G` | First / Last result |
| `Enter` | Open file in `$EDITOR` |
| `i` | Switch index |
| `L` | Set local path for file preview |
| `D` | Set daemon URL |
| `R` | Force reconnect to daemon |
| `?` | Toggle help |
| `Esc` | Back to results / Cancel |
| `q` | Quit |

### `gundog indexes`

List available indexes registered with the daemon.

```bash
gundog indexes                                    # list all indexes
gundog indexes --daemon http://192.168.1.10:7676  # list indexes on specific daemon
```

### `gundog config`

Manage client configuration for the TUI and CLI.

```bash
gundog config --show    # display current config
gundog config --init    # create default config file
```

Client config is stored at `~/.config/gundog/client.yaml` and includes settings like local paths for file preview in the TUI.

## How It Works

1. **Embedding**: Files are converted to vectors using [sentence-transformers](https://www.sbert.net/). Similar concepts end up as nearby vectors.

2. **Hybrid Search**: Combines semantic (vector) search with keyword ([BM25](https://en.wikipedia.org/wiki/Okapi_BM25)) search using Reciprocal Rank Fusion. Queries like "UserAuthService" find exact matches even when embeddings might miss them.

3. **Storage**: Vectors stored locally using a vector DB: plain numpy; or HNSW. No external services.

4. **Two-Stage Ranking**: Coarse retrieval via vector+BM25 fusion, then fine-grained ranking using per-line TF-IDF scores to pinpoint the best matching line within each chunk.

5. **Graph**: Documents above a similarity threshold get connected, enabling traversal from direct matches to related files.

6. **Query**: Your query gets embedded, compared against stored vectors, fused with keyword results, and ranked. Scores are rescaled so 0% = baseline, 100% = perfect match. Irrelevant queries return nothing.

## Configuration

Gundog uses three config files:

| File | Scope | Purpose |
|------|-------|---------|
| `.gundog/config.yaml` | Per-project | Index settings (sources, model, storage) |
| `~/.config/gundog/daemon.yaml` | Per-user | Daemon settings (host, port, registered indexes) |
| `~/.config/gundog/client.yaml` | Per-user | Client settings (local paths for TUI file preview) |


### Project config

Each project has its own `.gundog/config.yaml` that defines what to index and how:

```yaml
sources:
  - path: ./docs
    glob: "**/*.md"
  - path: ./src
    glob: "**/*.py"
    type: code                    # optional - for filtering with --type
    ignore_preset: python         # optional - predefined ignores
    ignore:                       # optional - additional patterns to skip
      - "**/test_*"
    use_gitignore: true           # default - auto-read .gitignore

embedding:
  # Any sentence-transformers model works: https://sbert.net/docs/sentence_transformer/pretrained_models.html
  model: BAAI/bge-small-en-v1.5   # default (~130MB), good balance of speed/quality
  enable_onnx: true               # default. forces ONNX conversion
  threads: 2                      # CPU threads for embedding (increase for faster indexing)

storage:
  use_hnsw: true                  # default - O(log n) search, scales to millions. Uses numpy if false.
  path: .gundog/index

graph:
  similarity_threshold: 0.7  # min similarity to create edge
  expand_threshold: 0.5      # min edge weight for query expansion
  max_expand_depth: 2        # how far to traverse during expansion

hybrid:
  enabled: true       # combine vector + keyword search (default: on)
  bm25_weight: 0.5    # keyword search weight
  vector_weight: 0.5  # semantic search weight

recency:
  enabled: false      # boost recently modified files (opt-in, requires git)
  weight: 0.15        # how much recency affects score (0-1)
  half_life_days: 30  # days until recency boost decays to 50%

chunking:
  enabled: true       # default - split files into chunks for better precision
  max_tokens: 512     # tokens per chunk
  overlap_tokens: 50  # overlap between chunks
```

The `type` field is optional. If you want to filter results by category, assign types to your sources. Any string works.

### Embedding options

| Option | Default | Description |
|--------|---------|-------------|
| `model` | `BAAI/bge-small-en-v1.5` | Any sentence-transformers model |
| `enable_onnx` | `true` | Use [ONNX Runtime](https://onnxruntime.ai/) |
| `threads` | `2` | CPU threads for embedding operations |

ONNX models are automatically and forcefully converted on first use and cached at `~/.cache/gundog/onnx/`. This cache is shared across all your projects that use the same model.

The `threads` setting controls CPU parallelism for embedding. The default of 2 is conservative to prevent system slowdown during indexing. Increase for faster indexing on multi-core machines, decrease if your system becomes unresponsive:

```yaml
embedding:
  threads: 4  # use 4 CPU threads
```

**Note on GPU support**: Gundog uses ONNX Runtime for inference by default, which runs on CPU. The default installation includes CPU-only PyTorch (~176MB) rather than CUDA PyTorch (~3GB+). This is intentional - ONNX provides fast CPU inference without GPU dependencies.

If you want GPU acceleration (only useful with `enable_onnx: false`):
```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu121 --reinstall
```

### Storage options

| Option | Default | Description |
|--------|---------|-------------|
| `use_hnsw` | `true` | Use [HNSW](https://github.com/nmslib/hnswlib) index for O(log n) search |
| `path` | `.gundog/index` | Where to store the index |


### Ignore patterns

Control which files are excluded from indexing:

- **`ignore`**: List of glob patterns to skip (e.g., `**/test_*`, `**/__pycache__/*`)
- **`ignore_preset`**: Predefined patterns for common languages: `python`, `javascript`, `typescript`, `go`, `rust`, `java`
- **`use_gitignore`**: Auto-read `.gitignore` from source directory (default: `true`)

### Chunking

Enabled by default for better search precision. Instead of embedding whole files (which dilutes signal), chunking splits files into overlapping segments:

```yaml
chunking:
  enabled: true
  max_tokens: 512   # ~2000 characters per chunk
  overlap_tokens: 50
```

Results are automatically deduplicated by file, showing the best-matching chunk with line numbers.

### Recency boost

For codebases where recent changes matter more, enable recency boosting. Files modified recently get a score boost based on their git commit history:

```yaml
recency:
  enabled: true
  weight: 0.15        # boost multiplier (0.15 = up to 15% boost)
  half_life_days: 30  # file modified 30 days ago gets 50% of max boost
```

Uses exponential decay: a file modified today gets full boost, one modified `half_life_days` ago gets half, and older files approach zero. Requires files to be in a git repository.

### Daemon config

The daemon config at `~/.config/gundog/daemon.yaml` controls the background service:

```yaml
daemon:
  host: 127.0.0.1       # bind address
  port: 7676            # port number
  serve_ui: true        # serve web UI at root path
  auth:                 # Auth not supported by the clients yet
    enabled: false      # require API key
    api_key: null       # set via GUNDOG_API_KEY env var or here
  cors:
    allowed_origins: [] # CORS origins (empty = allow all)

# Registered indexes (managed via `gundog daemon add/remove`)
indexes:
  myproject: /path/to/project/.gundog

default_index: myproject  # used when --index not specified
```

### Client config

The client config at `~/.config/gundog/client.yaml` stores TUI and client preferences:

```yaml
# Daemon URL (set via TUI with 'D' key or --daemon flag)
daemon_url: http://127.0.0.1:7676

# Local paths for file preview (set via TUI with 'L' key)
local_paths:
  myproject: /home/user/projects/myproject
  docs: /home/user/docs
```

When you set a daemon URL in the TUI (press `D`), it's saved to this config file. Local paths map index names to your local checkout for syntax-highlighted file preview.

## Network & SSL

Gundog downloads embedding models from HuggingFace on first run. If you're behind a corporate proxy or firewall that intercepts SSL traffic (e.g., Zscaler), you may see certificate errors.

### Quick fix (disable SSL verification)

```bash
gundog index --no-verify-ssl
```

Or set permanently:
```bash
export GUNDOG_NO_VERIFY_SSL=1
```

### Proper fix (use your network's CA certificate)

```bash
export GUNDOG_CA_BUNDLE=/path/to/your-network-ca.pem
gundog index
```

## Development

- Fork the repo
- Create a PR to gundog's main
- Make sure the CI passes
- Profit

To run checks locally

```bash
uv run tox               # run all checks (lint, fmt, static, unit)
uv run tox -e lint       # linting only
uv run tox -e fmt        # format check only
uv run tox -e static     # type check only
uv run tox -e unit       # tests with coverage
```
