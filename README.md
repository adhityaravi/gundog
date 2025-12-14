<h1 align="center">gundog</h1>

<p align="center">
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/v/gundog" alt="PyPI"></a>
  <a href="https://pypi.org/project/gundog/"><img src="https://img.shields.io/pypi/pyversions/gundog" alt="Python"></a>
  <a href="https://github.com/adhityaravi/gundog/releases"><img src="https://img.shields.io/github/v/release/adhityaravi/gundog?include_prereleases&label=pre-release&color=orange" alt="Pre-release"></a>
  <a href="https://github.com/adhityaravi/gundog/actions"><img src="https://img.shields.io/github/actions/workflow/status/adhityaravi/gundog/pull_request.yaml?label=CI" alt="CI"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
</p>

Gundog is a local semantic retrieval engine for your high volume corpus. It finds relevant code and documentation by understanding *what you mean*, not just matching keywords.

Point it at your docs and code. It embeds everything into vectors, builds a similarity graph connecting related files, and combines semantic search with keyword matching. Ask "how does auth work?" and it retrieves the login handler, session middleware, and the ADR that explains why you chose JWT even if none of them contain the word "auth".

Use it for LLM context retrieval, exploring unfamiliar codebases, or as a dynamic documentation explorer. Runs entirely on your machine.

<p align="center">
  <img src="assets/webui.png" alt="gundog web UI" width="900">
</p>

## The Problem

Your codebase is full of implicit connections that aren't explicit. The ADR explaining your auth strategy relates to the login handler, which relates to the session middleware but nothing links them. Docs drift from implementation. Knowledge lives in silos.

There are some tools that solves this problem. Especially, credit where it's due - the core idea of gundog is based on the much more mature [SeaGOAT](https://github.com/kantord/SeaGOAT) project. But my particular needs were ever so slightly different. I wanted a clean map of data chunks from wide spread data sources and their correlation based on a natural language query. SeaGOAT provides rather a flat but more accurate pointer to a specific data chunk from a single git repository. Basically, I wanted a [Obsidian graph view](https://help.obsidian.md/plugins/graph) of my docs controlled based on a natural language query without having to go through the pain of using.. well.. Obsidian. And wrapping `SeaGOAT` with some scripts was limiting and also hard to distribute.

Gundog builds these connections automatically. Vector search finds semantically related content, BM25 catches exact keyword matches, and graph expansion surfaces files you didn't know to look for.

## Install

```bash
pip install gundog
```

Optional extras:

```bash
pip install gundog[viz]    # for query graph visualization
pip install gundog[lance]  # for larger codebases (10k+ files)
pip install gundog[serve]  # for web UI server
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

First run downloads the embedding model (~130MB for the default). You can use any [sentence-transformers model](https://sbert.net/docs/sentence_transformer/pretrained_models.html). Subsequent runs are incremental—only re-indexes changed files.

**3. Search:**

```bash
gundog query "database connection pooling"
```

Returns ranked results with file paths and relevance scores.

## Commands

You can use gundog with a config file OR with CLI flags directly. but config files are recommended:

```bash
# With config file (default: .gundog/config.yaml)
gundog index
gundog index -c /path/to/config.yaml

# Without config file
gundog index --source ./docs:*.md --source ./src:*.py
gundog query "auth" --index .gundog/index
```

### `gundog index`

Scans your configured sources, embeds the content, and builds a searchable index.

```bash
gundog index                                      # uses config file
gundog index --rebuild                            # fresh index from scratch
gundog index -s ./docs:*.md -s ./src:*.py         # no config needed
gundog index -s ./docs -i ./my-index              # custom index location
gundog index -s ./src:*.py -e '**/test_*'         # exclude test files
```

Source format: `path`, `path:glob`, or `path:type:glob`

Exclude patterns use fnmatch syntax (e.g., `**/test_*`, `**/__pycache__/*`).

**Exclusion templates** provide predefined patterns for common languages:

```bash
gundog index -s ./src:*.py --exclusion-template python  # ignores __pycache__, .venv, etc.
gundog index -s ./src:*.ts --exclusion-template typescript
```

Available templates: `python`, `javascript`, `typescript`, `go`, `rust`, `java`

### `gundog query`

Finds relevant files for a natural language query.

```bash
gundog query "error handling strategy"
gundog query "authentication" --top 5        # limit results
gundog query "caching" --no-expand           # skip graph expansion
gundog query "auth" --index .gundog/index    # specify index directly
gundog query "api design" --type docs        # filter by type (if sources have types)
gundog query "auth flow" --graph             # opens visual graph of results
```

### `gundog serve`

Starts a web UI for interactive queries with a visual graph.

```bash
gundog serve                              # starts at http://127.0.0.1:8000
gundog serve --port 3000                  # custom port
gundog serve --title "My Project"         # custom title
```

File links are auto-detected from git repos. Files in a git repo with a remote get clickable links to GitHub/GitLab. Non-git files show the path on hover.

Requires the serve extra: `pip install gundog[serve]`

## How It Works

1. **Embedding**: Files are converted to vectors using [sentence-transformers](https://www.sbert.net/). Similar concepts end up as nearby vectors.

2. **Hybrid Search**: Combines semantic (vector) search with keyword ([BM25](https://en.wikipedia.org/wiki/Okapi_BM25)) search using Reciprocal Rank Fusion. Queries like "UserAuthService" find exact matches even when embeddings might miss them.

3. **Storage**: Vectors stored locally via numpy+JSON (default) or [LanceDB](https://lancedb.com/) for scale. No external services.

4. **Graph**: Documents above a similarity threshold get connected, enabling traversal from direct matches to related files.

5. **Query**: Your query gets embedded, compared against stored vectors, fused with keyword results, and ranked. Scores are rescaled so 0% = baseline, 100% = perfect match. Irrelevant queries return nothing.

## Configuration

Full config options:

```yaml
sources:
  - path: ./docs
    glob: "**/*.md"
  - path: ./src
    glob: "**/*.py"
    type: code                    # optional - for filtering with --type
    exclusion_template: python    # optional - predefined excludes
    exclude:                      # optional - additional patterns to skip
      - "**/test_*"

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

chunking:
  enabled: false      # split files into chunks (opt-in)
  max_tokens: 512     # tokens per chunk
  overlap_tokens: 50  # overlap between chunks
```

The `type` field is optional. If you want to filter results by category (e.g., `--type code`), assign types to your sources. Any string works. To use a type without a config file, use the format `path:type:glob` when specifying sources.

### Chunking

For large files, enable chunking to get better search results. Instead of embedding whole files (which dilutes signal), chunking splits files into overlapping segments:

```yaml
chunking:
  enabled: true
  max_tokens: 512   # ~2000 characters per chunk
  overlap_tokens: 50
```

Results are automatically deduplicated by file, showing the best-matching chunk.

## What Gundog Doesn't Do

- **Chat**: It's retrieval, not generation. Feed results to your LLM of choice.
- **Cloud anything**: Everything runs locally. Your code stays on your machine.

## Why "Gundog"?

Gundogs retrieve things. That's the whole job. Point at what you want, they fetch it. Small, focused, good at one thing.

## Development

```bash
uv sync --extra dev      # install dev dependencies
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright src       # type check
uv run pytest            # test
uv run tox               # run all checks
```

---

*Small. Lightweight. Ferocious.*
