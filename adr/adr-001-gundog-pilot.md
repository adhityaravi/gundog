# Gundog: Semantic Retrieval for Architectural Knowledge

## Context and Problem Statement

Large projects accumulate architectural knowledge across ADRs, documentation, and code. As this corpus grows, it becomes impossible to fit into LLM context windows:

- Charmarr's ADRs alone consume ~72k tokens today
- With Flintarr, Configuratarr, o11y, IAM, scaling concerns → 150-200k+ tokens projected
- Codebases grow faster than documentation, compounding the problem
- Full context loading causes token pressure, auto-compaction, and degraded coherence

The core question: **How do we give LLM agents accurate architectural context without loading everything?**

Manual file selection doesn't scale - it requires maintaining manifests and deep familiarity with the entire corpus. We need semantic retrieval that understands conceptual relationships, not just keyword matching.

## Considered Options

* **Lossy summarization** - Synthesize ADRs into compressed summaries
* **Manual manifests** - Curate file lists per task/epic
* **Existing RAG tools** - LlamaIndex, Langchain, Obsidian with plugins
* **Purpose-built semantic retrieval** - Lightweight tool optimized for this specific problem

## Decision Outcome

Chosen option: **"Purpose-built semantic retrieval (Gundog)"**, because:

- Lossy summarization discards the reasoning and alternatives that make ADRs valuable
- Manual manifests don't scale with corpus growth or cross-cutting concerns
- Existing tools are either too heavy (LlamaIndex), too opinionated (Obsidian), or solve adjacent problems
- A focused tool can be small (~300-500 lines), dependency-light, and optimized for the exact workflow: index docs + code → query → get relevant files for LLM context

### Design Philosophy

**Small**: Minimal dependencies, single-purpose, easy to understand
**Lightweight**: No servers, flat file storage, fast startup
**Ferocious**: Accurate retrieval, sub-second queries, zero friction

### Core Architecture

```
Documents + Code → Embed → Vector Store → Query → Ranked Results
                              ↓
                        Graph Structure → Visualization
```

**Indexing phase:**
1. Scan configured source directories
2. Embed each file using sentence-transformers model
3. Store vectors with metadata (path, type, mtime, content hash)
4. Build similarity graph from vector relationships

**Query phase:**
1. Embed query string
2. Compute cosine similarity against stored vectors
3. Return top-k results with paths, line numbers, scores

**Visualization phase:**
1. Construct graph with documents as nodes
2. Create edges where similarity exceeds threshold
3. Export as self-contained HTML or JSON for custom UIs

### Key Design Decisions

#### Vector Storage

Abstraction layer supporting multiple backends:

| Backend | Use Case |
|---------|----------|
| numpy+JSON (default) | Simple, zero deps, sufficient for <10k documents |
| LanceDB (optional) | Better performance at scale, optional dependency |

```bash
pip install gundog           # numpy backend
pip install gundog[lance]    # lancedb backend
```

The abstraction is ~100 lines total. Both backends implement:
```python
class VectorStore(Protocol):
    def upsert(self, id: str, vector: list[float], metadata: dict) -> None
    def query(self, vector: list[float], top_k: int) -> list[Result]
    def delete(self, id: str) -> None
```

#### Embedding Model

**bge-small-en-v1.5** via sentence-transformers:
- 384 dimensions
- ~130MB download
- Trained specifically for retrieval tasks
- Good quality-to-size ratio

Model is configurable for users who want smaller (all-MiniLM-L6-v2, 80MB) or higher quality (all-mpnet-base-v2, 420MB).

#### What Gets Embedded

The full text content including:
- File path (contributes tokens like directory/file names)
- Docstrings and comments
- Code structure (class/function names)
- All prose content

This works because embedding models understand semantic relationships - "StatefulSet patching" in an ADR clusters with `_patch_statefulset()` in code, even without exact keyword match.

#### Incremental Indexing

Hybrid mtime + content hash approach:

```python
def needs_reindex(file_path: str, cached: CacheEntry) -> bool:
    # Fast path: mtime unchanged = skip
    if file_path.stat().st_mtime == cached.mtime:
        return False
    # Mtime changed - verify with content hash
    return hash_file(file_path) != cached.content_hash
```

- Usually just checks mtime (fast)
- Falls back to hash when mtime differs (reliable)
- Handles git clone, CI environments, accidental touches

#### Query Output

Machine-optimized JSON for LLM consumption:

```json
{
  "query": "vpn consumer patching",
  "results": [
    {
      "path": "adr/networking/adr-002-vpn-egress.md",
      "type": "adr",
      "score": 0.94,
      "lines": [45, 78]
    },
    {
      "path": "charms/qbittorrent/src/charm.py",
      "type": "code",
      "score": 0.91,
      "lines": [156, 203]
    }
  ]
}
```

No snippets in default output - keeps queries fast, lets consumers load what they need.

#### Visualization

Two modes:

**Built-in minimal**: Self-contained HTML using pyvis, works standalone
```bash
gundog graph                  # opens in browser
```

**Export for custom UIs**: JSON graph data for rich visualizations
```bash
gundog graph --format json    # for custom D3/Cytoscape builds
gundog graph --format dot     # graphviz format
```

Enables projects to build fancy documentation sites using gundog's engine without gundog itself needing that complexity.

### CLI Interface

Hybrid flags + config file approach:

```yaml
# .gundog/config.yaml
sources:
  - path: ./adr
    type: adr
    glob: "**/*.md"
  - path: ./src
    type: code
    glob: "**/*.py"

embedding:
  model: bge-small-en-v1.5

storage:
  backend: numpy  # or "lancedb"
  path: .gundog/index
```

```bash
# Uses config
gundog index
gundog query "vpn consumer patching"
gundog graph

# Override via CLI
gundog index --rebuild
gundog query --top 5 --type adr "vpn consumer patching"
gundog graph --format json --output graph.json
```

### What Gundog Does NOT Do

- **Trigger decisions**: User wires up git hooks, CI, or manual invocation
- **LLM integration**: Just retrieval; consumers (Claude Code, etc.) handle generation
- **Chat interface**: Not a chatbot, just a retrieval tool
- **Chunking strategies**: Whole-file embedding initially (extension path for later)

### Consequences

**Good:**
- Solves the context window pressure problem without losing architectural fidelity
- Generic enough to use on any project with docs + code
- Small enough to understand, maintain, and trust
- No runtime dependencies beyond sentence-transformers and numpy
- Graph visualization helps humans understand architecture too

**Bad:**
- Retrieval quality depends on embedding model's understanding of domain
- ~70-80% accuracy on ADR↔code connections out of the box (improvable with good docstrings)
- 130MB model download on first run
- Another tool to maintain (though minimal surface area)

**Mitigations:**
- Docstrings referencing ADRs boost semantic connection
- Explicit links in frontmatter can supplement semantic edges (future enhancement)
- Model is configurable if defaults don't work for a domain

### Future Extension Paths

Not designed for now, but possible later:

**Embedding:**
- Pluggable models (API-based, domain-specific)
- Chunking strategies (by function, by markdown section)

**Query:**
- Filters (`--type`, `--path`)
- "More like this" mode

**Graph:**
- Cluster auto-labeling
- Explicit link extraction (markdown links, imports)
- Temporal evolution view

**Integrations:**
- MCP server wrapper
- GitHub Action for CI indexing
- VS Code extension

### Validation Plan

Before full implementation:

1. Embed a sample of Charmarr ADRs + corresponding implementation code
2. Run test queries ("vpn consumer patching", "shared storage hardlinks", "indexer sync")
3. Verify top-5 results match human intuition
4. If retrieval quality is poor, investigate chunking or model alternatives

---

## Summary

Gundog is a semantic retrieval tool for architectural knowledge. It embeds documentation and code, stores vectors efficiently, and returns relevant files for LLM context. Small, lightweight, ferocious.

```
gundog index → gundog query "topic" → relevant files → Claude Code context
```

That's it. One job, done well.
