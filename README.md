<h1 align="center">gundog</h1>

<p align="center">
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/v/gundog" alt="PyPI"></a>
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/pyversions/gundog" alt="Python"></a>
  <a href="https://github.com/adhityaravi/gundog/actions"><img src="https://img.shields.io/github/actions/workflow/status/adhityaravi/gundog/pull_request.yaml?label=CI" alt="CI"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/6be7d95a-8476-47a8-b530-756801d49b2b" alt="gundog demo" width="540">
</p>

Gundog is a local semantic retrieval engine for your high volume corpus. It finds relevant code and documentation by matching the semantics of your query and not just matching keywords.

Point it at your docs or code or both. It embeds everything into vectors, builds a similarity graph connecting related files, and combines semantic search with keyword matching. Ask "how does auth work?" and it retrieves the login handler, session middleware, and the ADR that explains why you chose JWT even if none of them contain the word "auth".

## Why?

I wanted a clean map of all related data chunks from wide spread data sources based on a natural language query. `SeaGOAT` provides rather a ranked but flat and accurate pointer to specific data chunks from a single git repository. Basically, I wanted a [Obsidian graph view](https://help.obsidian.md/plugins/graph) of my docs controlled based on a natural language query without having to go through the pain of using.. well.. Obsidian.

Gundog builds these connections across repositories/data sources automatically. Vector search finds semantically related content, BM25 catches exact keyword matches, and graph expansion surfaces files you didn't know to look for.

## Install

```bash
pip install gundog
```

Optional extras:

```bash
pip install gundog[lance]  # for larger codebases (10k+ files)
```

### Or from source

```bash
git clone https://github.com/adhityaravi/gundog.git
cd gundog
uv sync
uv run gundog --help
```

## Quick Start

**1. Create a config file** (default: `.gundog/config.yaml`):

```yaml
sources:
  - path: ./docs
    glob: "**/*.md"
  - path: ./src
    glob: "**/*.py"

storage:
  backend: numpy
  path: .gundog/index
```

**2. Index your stuff:**

```bash
gundog index
```

First run downloads the embedding model (~130MB for the default). You can use any [sentence-transformers model](https://sbert.net/docs/sentence_transformer/pretrained_models.html). Subsequent runs are incremental and only re-indexes changed files.

**3. Start the daemon and register your index:**

```bash
gundog daemon start
gundog daemon add myproject .
```

**4. Search:**

```bash
gundog query "database connection pooling"
```

Returns ranked results with file paths and relevance scores. The daemon keeps the model loaded for instant queries (~0.2s).

## Commands

### `gundog index`

Scans your configured sources, embeds the content, and builds a searchable index.

```bash
gundog index                    # uses .gundog/config.yaml
gundog index -c /path/to.yaml   # custom config file
gundog index --rebuild          # fresh index from scratch
```

### `gundog query`

Finds relevant files for a natural language query. **Requires the daemon to be running.**

```bash
gundog query "error handling strategy"
gundog query "authentication" --top 5        # limit results
gundog query "auth" --index myproject        # use specific registered index
```

### `gundog daemon`

Runs a persistent background service for fast queries. The daemon keeps the embedding model loaded in memory, making subsequent queries instant (~0.2s vs ~3s cold start).

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

The `gundog query` command requires the daemon to be running. Daemon settings are stored at `~/.config/gundog/daemon.yaml`.

The daemon also serves a web UI at the same address for interactive queries with a visual graph. File links are auto-detected from git repos - files in a git repo with a remote get clickable links to GitHub/GitLab.

## How It Works

1. **Embedding**: Files are converted to vectors using [sentence-transformers](https://www.sbert.net/). Similar concepts end up as nearby vectors.

2. **Hybrid Search**: Combines semantic (vector) search with keyword ([BM25](https://en.wikipedia.org/wiki/Okapi_BM25)) search using Reciprocal Rank Fusion. Queries like "UserAuthService" find exact matches even when embeddings might miss them.

3. **Storage**: Vectors stored locally via numpy+JSON (default) or [LanceDB](https://lancedb.com/) for scale. No external services.

4. **Graph**: Documents above a similarity threshold get connected, enabling traversal from direct matches to related files.

5. **Query**: Your query gets embedded, compared against stored vectors, fused with keyword results, and ranked. Scores are rescaled so 0% = baseline, 100% = perfect match. Irrelevant queries return nothing.

## Configuration

Gundog uses two config files:

| File | Scope | Purpose |
|------|-------|---------|
| `.gundog/config.yaml` | Per-project | Index settings (sources, model, storage backend) |
| `~/.config/gundog/daemon.yaml` | Per-user | Daemon settings (host, port, registered indexes) |

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
  model: BAAI/bge-small-en-v1.5  # default (~130MB), good balance of speed/quality

storage:
  backend: numpy      # or "lancedb" for larger corpora
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
  enabled: false      # split files into chunks (opt-in)
  max_tokens: 512     # tokens per chunk
  overlap_tokens: 50  # overlap between chunks
```

The `type` field is optional. If you want to filter results by category, assign types to your sources. Any string works.

### Ignore patterns

Control which files are excluded from indexing:

- **`ignore`**: List of glob patterns to skip (e.g., `**/test_*`, `**/__pycache__/*`)
- **`ignore_preset`**: Predefined patterns for common languages: `python`, `javascript`, `typescript`, `go`, `rust`, `java`
- **`use_gitignore`**: Auto-read `.gitignore` from source directory (default: `true`)

### Chunking

For large files, enable chunking to get better search results. Instead of embedding whole files (which dilutes signal), chunking splits files into overlapping segments:

```yaml
chunking:
  enabled: true
  max_tokens: 512   # ~2000 characters per chunk
  overlap_tokens: 50
```

Results are automatically deduplicated by file, showing the best-matching chunk.

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
  auth:
    enabled: false      # require API key
    api_key: null       # set via GUNDOG_API_KEY env var or here
  cors:
    allowed_origins: [] # CORS origins (empty = allow all)

# Registered indexes (managed via `gundog daemon add/remove`)
indexes:
  myproject: /path/to/project/.gundog

default_index: myproject  # used when --index not specified
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
