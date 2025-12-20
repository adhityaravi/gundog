# ADR-001: Gundog TUI Client Implementation

## Context

The TUI client should:
- Connect to a remote Gundog daemon via WebSocket
- Provide interactive search with real-time results
- Visualize the similarity graph in the terminal
- Support keyboard-driven navigation including graph traversal
- Be lightweight and installable separately from the full Gundog package

## Decision

We will build a TUI client using **Textual** (Python TUI framework) with **Rich** for terminal formatting. The similarity graph will be rendered using **Unicode Braille characters** or **textual-canvas** for sub-character resolution. **NetworkX** will compute force-directed graph layouts.

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| TUI Framework | Textual | Modern async Python TUI, CSS-like styling, excellent widget system |
| Formatting | Rich | Textual's foundation, syntax highlighting, tables |
| Graph Layout | NetworkX | Industry standard, multiple layout algorithms, pure Python |
| Graph Rendering | Braille/textual-canvas | 8x resolution with Braille, good Textual integration with canvas |
| Communication | websockets | Async WebSocket client, pairs well with Textual's async model |
| Config | PyYAML | Simple, human-readable configuration |

## Specification

### 1. Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ gundog                                            Index: my-project ▼   [?] │
├─────────────────────────────────────────────────────────────────────────────┤
│ Search: authentication flow_                                                │
├─────────────────────────────────┬───────────────────────────────────────────┤
│ RESULTS (12 matches)            │ GRAPH                          [R] [+][-]│
│                                 │                                          │
│ ● src/auth/oauth.py             │        oauth.py                          │
│   92% │ code │ L45-89           │           ●━━━━━━━●  jwt.py              │
│                                 │          ╱│╲       ╲                     │
│   src/auth/jwt.py               │         ╱ │ ╲       ╲                    │
│   87% │ code │ L12-34           │        ╱  │  ╲       ╲                   │
│                                 │       ●   │   ●───────●                  │
│   src/middleware/session.py     │  session  │  tokens  README              │
│   76% │ code │ L1-28            │      .py  │  .py     .md                 │
│                                 │           │                              │
│   docs/auth/README.md           │           ●                              │
│   71% │ docs │ L1-50            │       config.yaml                        │
│                                 │                                          │
│ ────────────────────────────    │  ○ Direct   ◐ Related   ◌ Distant       │
│ RELATED via graph (8)           │                                          │
│                                 │  [→] oauth.py (focused)                  │
│   src/utils/crypto.py           │                                          │
│   → via oauth.py │ 82%          │                                          │
│                                 │                                          │
├─────────────────────────────────┴───────────────────────────────────────────┤
│ ● connected │ ws://localhost:9450 │ my-project (1,247 files) │ 2ms         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Component Descriptions

#### 2.1 Header Bar

Single row containing:
- **App Title**: gundog
- **Index Selector**: Displays current index name with dropdown indicator (▼), clickable or activated via `i` key to open index switcher modal
- **Help Button**: `[?]` indicator showing help is available

#### 2.2 Search Bar

- Single-line text input for semantic search queries
- Debounced execution (300ms after typing stops)
- Loading indicator during search
- Keyboard shortcuts: `Ctrl+u` to clear, `Enter` to execute immediately

#### 2.3 Results Pane (Left)

Split into two sections:

**Direct Matches Section:**
- Header showing total match count
- List of results, each displaying:
  - Selection indicator (● for selected, blank otherwise)
  - File path (truncated if needed)
  - Similarity percentage
  - Type badge (code, docs, conf, etc.)
  - Line range if applicable
- Scrollable when results exceed viewport

**Related Results Section:**
- Separator line with "RELATED via graph (N)" header
- Graph-expanded results showing:
  - File path
  - Arrow indicator and source node ("→ via oauth.py")
  - Edge similarity percentage

#### 2.4 Graph Pane (Right)

Interactive network visualization:

**Visual Elements:**
- Nodes: Circles representing files, sized by relevance score
- Edges: Lines connecting similar files, thickness indicates similarity weight
- Labels: File names below/beside nodes
- Focus indicator: Brackets or highlight around keyboard-focused node
- Legend: Shows node type encoding (Direct/Related/Distant)

**Controls:**
- `[R]` Reset button/indicator
- `[+][-]` Zoom controls

**Rendering Approach:**

*Option A - Braille Characters (Preferred):*
Unicode Braille block (U+2800-U+28FF) provides 2×4 dot matrix per character cell, yielding 8× resolution. A custom `BrailleCanvas` class handles:
- Pixel-to-braille-dot mapping
- Line drawing (Bresenham's algorithm)
- Circle drawing (midpoint algorithm)
- Rendering to string output

*Option B - textual-canvas:*
Third-party widget providing half-character pixels (2× vertical resolution). Simpler API but lower resolution than Braille.

**Layout Algorithm:**
NetworkX `spring_layout` (Fruchterman-Reingold force-directed algorithm):
- Nodes repel each other
- Edges act as springs pulling connected nodes together
- Iterates until equilibrium
- Produces normalized (0-1) coordinates scaled to widget dimensions

#### 2.5 Preview Popup Modal

**Availability:** Only enabled when a **local base path** is configured for the current index. The daemon stores relative file paths in the index; the TUI combines these with the user-configured local base path to access files.

**Triggered by:** Pressing `Enter` or `p` on a selected result.

**When local base path is NOT configured:**
- `Enter`/`p` shows a toast: "Configure local path to enable preview (press L)"
- Results can still be navigated and copied

**Modal Layout (when enabled):**
```
┌─────────────────────────────────────────────────────────────────────┐
│ PREVIEW: src/auth/oauth.py                              [e] [y] [x]│
├─────────────────────────────────────────────────────────────────────┤
│  45 │ class OAuthProvider:                                         │
│  46 │     """Handle OAuth2 authentication flow."""                 │
│  47 │                                                              │
│  48 │     def __init__(self, client_id: str, client_secret: str):  │
│  49 │         self.client_id = client_id                           │
│  50 │         self.client_secret = client_secret                   │
│  51 │         self._token_cache: dict[str, Token] = {}             │
│  52 │                                                              │
│  53 │     async def authenticate(self, code: str) -> Token:        │
│  54 │         """Exchange authorization code for access token."""  │
│  55 │         async with aiohttp.ClientSession() as session:       │
│  56 │             response = await session.post(                   │
│  57 │                 self.token_endpoint,                         │
│  58 │                 data={                                       │
│  59 │                     "grant_type": "authorization_code",      │
│  60 │                     "code": code,                            │
│  ...|                     ...                                      │
├─────────────────────────────────────────────────────────────────────┤
│ Lines 45-89 of 150 │ Python │ ↑↓ Scroll  e Open  y Copy  x Close   │
└─────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Syntax-highlighted code using Rich
- Line numbers in dimmed style
- Scrollable content
- Header shows file path and action buttons
- Footer shows line range, language, and keybind hints

**Modal Controls:**
- `↑/↓` or `j/k`: Scroll content
- `e`: Open file in external editor at current line
- `y`: Copy file path to clipboard
- `x` or `Escape`: Close modal

**File Path Resolution:**
```
Index stores:      "src/auth/oauth.py" (relative path)
User configures:   local_base_path = "/home/user/projects/charmarr"
TUI resolves:      "/home/user/projects/charmarr/src/auth/oauth.py"
```

#### 2.6 Status Bar

Single row at bottom showing:
- **Connection Indicator**: Colored dot (● green=connected, ○ red=disconnected, ◐ yellow=connecting)
- **Daemon URL**: WebSocket endpoint address
- **Index Info**: Current index name and file count
- **Local Path Status**: Shows if local base path is configured (📁 = configured, 📁? = not set)
- **Query Timing**: Last query response time in milliseconds

```
│ ● connected │ ws://localhost:9450 │ my-project (1,247 files) │ 📁 ~/code/proj │ 2ms │
```

Or when local path not configured:
```
│ ● connected │ ws://localhost:9450 │ my-project (1,247 files) │ 📁? [L] │ 2ms │
```

#### 2.7 Local Path Configuration Modal

**Triggered by:** Pressing `L` (capital L) from anywhere, or clicking the 📁? indicator.

```
┌───────────────────────────────────────────────────────────────┐
│ CONFIGURE LOCAL PATH                                          │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Index: my-project                                            │
│                                                               │
│  The daemon indexed files with paths like:                    │
│    src/auth/oauth.py                                          │
│    docs/README.md                                             │
│                                                               │
│  Enter the local directory where these files exist:           │
│                                                               │
│  Path: ~/code/my-project_                                     │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ ✓ Path exists                                           │  │
│  │ ✓ Found src/auth/oauth.py                               │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│  Enter: Save   Tab: Browse   Escape: Cancel   Ctrl+D: Clear   │
└───────────────────────────────────────────────────────────────┘
```

**Features:**
- Text input with path expansion (`~` expands to home directory)
- Real-time validation: checks if path exists
- Verification: daemon provides sample file paths, modal checks if they exist at configured path
- Paths are saved per-index in local config file
- `Ctrl+D` clears the configured path (disables preview/edit for this index)

**File Path Resolution:**
```
Index stores:      "src/auth/oauth.py" (relative path from daemon)
User configures:   local_base_path = "/home/user/projects/charmarr"
TUI resolves:      "/home/user/projects/charmarr/src/auth/oauth.py"
```

#### 2.8 Git Integration (Optional)

When an index has git metadata (provided by daemon), an additional option becomes available:

**Open in Git** (`O` - capital O): Opens the file in the browser at the git web URL (GitHub, GitLab, etc.)

This is **independent** of local base path - works even without local files configured.

**Keybind availability based on configuration:**

| Feature | Requires | Keybind | When unavailable |
|---------|----------|---------|------------------|
| Preview file content | Local base path | `Enter`, `p` | Toast: "Set local path [L]" |
| Edit in $EDITOR | Local base path | `e`, `o` | Toast: "Set local path [L]" |
| Copy relative path | Nothing (always works) | `y` | - |
| Open in browser (git) | Git metadata from daemon | `O` | Keybind hidden |
| Copy git URL | Git metadata from daemon | `Y` | Keybind hidden |

#### 2.9 Index Switcher Modal

**Triggered by:** Pressing `i` or clicking index selector in header.

```
┌───────────────────────────────────────────────────────────────┐
│ SELECT INDEX                                                  │
├───────────────────────────────────────────────────────────────┤
│  ● my-project         1,247 files   📁 ~/code/proj           │
│    work-codebase      3,891 files   📁?                      │
│    personal-notes       482 files   📁 ~/notes               │
│    archived-proj      2,103 files   📁?                      │
├───────────────────────────────────────────────────────────────┤
│  [L] Set local path   [r] Reindex                            │
├───────────────────────────────────────────────────────────────┤
│  Enter: Select   Esc: Cancel                                  │
└───────────────────────────────────────────────────────────────┘
```

**Features:**
- List all available indexes from daemon
- Show file count and local path status for each index
- Visual indicator for currently active index
- `L` to configure local path for highlighted index
- Actions for index management

#### 2.10 Help Modal

**Triggered by:** Pressing `?`

Displays categorized keybinding reference:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GUNDOG KEYBINDINGS                     [x] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GLOBAL                           GRAPH NAVIGATION                  │
│  ───────────────────────────      ───────────────────────────       │
│  /        Focus search            g        Enter graph mode         │
│  Tab      Cycle panes             h ←      Move focus left          │
│  Escape   Exit mode / Cancel      j ↓      Move focus down          │
│  q        Quit application        k ↑      Move focus up            │
│  ?        Toggle this help        l →      Move focus right         │
│  i        Switch index            n        Next neighbor            │
│                                   Enter    Select focused node      │
│  RESULTS LIST                     c        Center on focused        │
│  ───────────────────────────      f        Fit graph to view        │
│  ↑/↓ j/k  Navigate results        R        Reset layout             │
│  Enter    Open preview            +/-      Zoom in/out              │
│  p        Open preview                                              │
│  y        Copy path               PREVIEW MODAL                     │
│  o        Open in editor          ───────────────────────────       │
│                                   ↑/↓ j/k  Scroll content           │
│  SEARCH                           e        Open in editor           │
│  ───────────────────────────      y        Copy path                │
│  Enter    Execute search          x Esc    Close preview            │
│  Ctrl+u   Clear input                                               │
│  Ctrl+w   Delete word                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3. Keyboard Navigation

#### 3.1 Global Keybindings

| Key | Action |
|-----|--------|
| `/` | Focus search input |
| `Tab` | Cycle focus: Search → Results → Graph → Search |
| `Escape` | Exit current mode, close modal, or cancel operation |
| `q` | Quit application |
| `?` | Toggle help modal |
| `i` | Open index switcher modal |
| `L` | Open local path configuration modal |

#### 3.2 Results List Keybindings (when focused)

| Key | Action | Requires |
|-----|--------|----------|
| `↑` / `k` | Move selection up | - |
| `↓` / `j` | Move selection down | - |
| `Enter` / `p` | Open preview modal for selected item | Local base path |
| `y` | Copy relative file path to clipboard | - |
| `e` / `o` | Open file in external editor ($EDITOR) | Local base path |
| `O` | Open file in browser (GitHub/GitLab) | Git metadata |
| `Y` | Copy git URL to clipboard | Git metadata |
| `g` | Jump to top of list | - |
| `G` | Jump to bottom of list | - |

#### 3.3 Graph Pane Keybindings (when focused)

| Key | Action |
|-----|--------|
| `h` / `←` | Move focus to nearest node to the left |
| `j` / `↓` | Move focus to nearest node below |
| `k` / `↑` | Move focus to nearest node above |
| `l` / `→` | Move focus to nearest node to the right |
| `n` | Cycle focus to next connected neighbor (along edges) |
| `N` | Cycle focus to previous connected neighbor |
| `Enter` | Select focused node (syncs with results list, opens preview) |
| `Space` | Toggle multi-select on focused node |
| `c` | Center view on focused node |
| `f` | Fit entire graph into view |
| `R` | Reset graph layout and zoom |
| `+` / `=` | Zoom in |
| `-` | Zoom out |

#### 3.4 Search Input Keybindings (when focused)

| Key | Action |
|-----|--------|
| `Enter` | Execute search immediately |
| `Ctrl+u` | Clear entire input |
| `Ctrl+w` | Delete word before cursor |
| `Escape` | Blur input, return focus to results |

#### 3.5 Preview Modal Keybindings

| Key | Action |
|-----|--------|
| `↑` / `k` | Scroll up |
| `↓` / `j` | Scroll down |
| `Page Up` | Scroll up one page |
| `Page Down` | Scroll down one page |
| `g` | Jump to top |
| `G` | Jump to bottom |
| `e` | Open file in external editor at current line |
| `y` | Copy file path to clipboard |
| `x` / `Escape` | Close modal |

#### 3.6 Graph Navigation Algorithm

When navigating with directional keys, find the nearest node in the specified direction:

```python
def find_nearest_node_in_direction(
    current_pos: tuple[float, float],
    all_nodes: dict[str, tuple[float, float]],
    direction: Literal["left", "right", "up", "down"],
) -> str | None:
    """
    Find nearest node in the given direction from current position.

    Uses a cone-shaped search that prefers nodes directly in-line
    with the direction while still considering nearby nodes at angles.
    """
    cx, cy = current_pos
    best_node = None
    best_score = float("inf")

    for node_id, (nx, ny) in all_nodes.items():
        dx, dy = nx - cx, ny - cy

        # Check if node is in correct direction
        in_direction = (
            (direction == "left" and dx < -0.01) or
            (direction == "right" and dx > 0.01) or
            (direction == "up" and dy < -0.01) or
            (direction == "down" and dy > 0.01)
        )

        if not in_direction:
            continue

        # Score: distance with penalty for off-axis deviation
        distance = math.sqrt(dx * dx + dy * dy)

        if direction in ("left", "right"):
            angle_penalty = abs(dy) / (abs(dx) + 0.001)
        else:
            angle_penalty = abs(dx) / (abs(dy) + 0.001)

        score = distance * (1 + angle_penalty)

        if score < best_score:
            best_score = score
            best_node = node_id

    return best_node
```

### 4. Daemon Communication Protocol

#### 4.1 Connection Management

- Transport: WebSocket (wss:// for production, ws:// for local development)
- Default endpoint: `ws://localhost:9450`
- Reconnection: Exponential backoff starting at 1s, max 30s, with jitter
- Heartbeat: Ping every 30s to detect stale connections

#### 4.2 Message Format

All messages are JSON objects with a `type` field.

##### Query Request

```json
{
  "type": "query",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "index": "my-project",
  "query": "authentication flow",
  "top_k": 20,
  "expand": true,
  "expand_depth": 2,
  "min_score": 0.5
}
```

##### Query Response

```json
{
  "type": "query_result",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timing_ms": 2.3,
  "direct": [
    {
      "path": "src/auth/oauth.py",
      "score": 0.92,
      "type": "code",
      "lines": "45-89",
      "chunk_index": 2
    }
  ],
  "related": [
    {
      "path": "src/utils/crypto.py",
      "via": "src/auth/oauth.py",
      "edge_weight": 0.82,
      "depth": 1,
      "type": "code"
    }
  ],
  "graph": {
    "nodes": [
      {"id": "src/auth/oauth.py", "type": "code", "score": 0.92},
      {"id": "src/auth/jwt.py", "type": "code", "score": 0.87}
    ],
    "edges": [
      {"source": "src/auth/oauth.py", "target": "src/auth/jwt.py", "weight": 0.85}
    ]
  }
}
```

##### List Indexes Request

```json
{
  "type": "list_indexes"
}
```

##### List Indexes Response

```json
{
  "type": "index_list",
  "indexes": [
    {
      "name": "my-project",
      "files": 1247,
      "chunks": 4892,
      "last_updated": "2025-01-15T10:30:00Z",
      "config": {
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "chunking_enabled": true
      },
      "sample_paths": [
        "src/auth/oauth.py",
        "docs/README.md",
        "config/settings.yaml"
      ],
      "git": {
        "web_url": "https://github.com/user/my-project",
        "branch": "main",
        "commit": "abc123def456"
      }
    }
  ],
  "current": "my-project"
}
```

**Notes:**
- `sample_paths`: A few example file paths from the index. Used by TUI to help user verify their local path configuration is correct.
- `git`: Optional. Present only if the daemon has git metadata for this index. Enables "Open in browser" feature.

##### Switch Index Request

```json
{
  "type": "switch_index",
  "index": "work-codebase"
}
```

##### Switch Index Response

```json
{
  "type": "index_switched",
  "index": "work-codebase",
  "files": 3891,
  "sample_paths": ["src/main.py", "lib/utils.py"]
}
```

##### Status Push (Daemon → Client)

```json
{
  "type": "status",
  "uptime_seconds": 3600,
  "indexes": [
    {"name": "my-project", "files": 1247, "status": "ready"},
    {"name": "work-codebase", "files": 3891, "status": "indexing", "progress": 0.45}
  ],
  "current_index": "my-project",
  "version": "1.1.0"
}
```

##### Error Response

```json
{
  "type": "error",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "INDEX_NOT_FOUND",
  "message": "Index 'nonexistent' does not exist"
}
```

#### 4.3 Error Codes

| Code | Description |
|------|-------------|
| `INDEX_NOT_FOUND` | Requested index does not exist |
| `QUERY_FAILED` | Search query execution failed |
| `FILE_NOT_FOUND` | Preview file not found or inaccessible |
| `INVALID_REQUEST` | Malformed request message |
| `INDEX_BUSY` | Index is currently being rebuilt |
| `RATE_LIMITED` | Too many requests |

### 5. Widget Implementation

#### 5.1 Class Hierarchy

```
App
└── GundogApp
    ├── Screen (main)
    │   ├── HeaderBar
    │   ├── SearchInput
    │   ├── Container (horizontal split)
    │   │   ├── ResultsPane
    │   │   │   ├── DirectResultsList
    │   │   │   │   └── ResultItem (multiple)
    │   │   │   └── RelatedResultsList
    │   │   │       └── ResultItem (multiple)
    │   │   └── GraphPane
    │   └── StatusBar
    ├── ModalScreen
    │   ├── PreviewModal
    │   ├── IndexSwitcherModal
    │   └── HelpModal
    └── DaemonClient (service, not widget)
```

#### 5.2 Key Widget Specifications

##### GundogApp

```python
class GundogApp(App):
    """Main Gundog TUI application."""

    TITLE = "Gundog"
    CSS_PATH = "styles/app.tcss"
    BINDINGS = [
        Binding("/", "focus_search", "Search", show=True),
        Binding("tab", "cycle_focus", "Next Pane", show=False),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "toggle_help", "Help", show=True),
        Binding("i", "switch_index", "Index", show=True),
    ]

    # Reactive state
    current_index: reactive[str]
    daemon_connected: reactive[bool]
    query_results: reactive[QueryResult | None]
    selected_result: reactive[int]
    focused_graph_node: reactive[str | None]
```

##### ResultsPane

```python
class ResultsPane(Widget):
    """Left pane showing search results."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "open_preview", "Preview", show=True),
        Binding("p", "open_preview", "Preview", show=False),
        Binding("y", "copy_path", "Copy", show=True),
        Binding("o", "open_editor", "Edit", show=True),
    ]

    selected_index: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static("RESULTS", classes="section-header")
        yield DirectResultsList()
        yield Static("RELATED via graph", classes="section-header")
        yield RelatedResultsList()
```

##### GraphPane

```python
class GraphPane(Widget):
    """Right pane showing similarity graph."""

    BINDINGS = [
        Binding("h", "nav_left", "Left", show=False),
        Binding("j", "nav_down", "Down", show=False),
        Binding("k", "nav_up", "Up", show=False),
        Binding("l", "nav_right", "Right", show=False),
        Binding("n", "nav_next_neighbor", "Next", show=False),
        Binding("enter", "select_node", "Select", show=False),
        Binding("c", "center_on_focus", "Center", show=False),
        Binding("f", "fit_view", "Fit", show=False),
        Binding("R", "reset_layout", "Reset", show=True),
        Binding("+", "zoom_in", "Zoom+", show=True),
        Binding("-", "zoom_out", "Zoom-", show=True),
    ]

    focused_node: reactive[str | None] = reactive(None)
    selected_nodes: reactive[set[str]] = reactive(set)
    zoom_level: reactive[float] = reactive(1.0)
    pan_offset: reactive[tuple[float, float]] = reactive((0.0, 0.0))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph_data: GraphData | None = None
        self.node_positions: dict[str, tuple[float, float]] = {}
        self.canvas = BrailleCanvas(80, 24)
```

##### PreviewModal

```python
class PreviewModal(ModalScreen):
    """Modal popup showing file preview with syntax highlighting."""

    BINDINGS = [
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("e", "open_editor", "Edit", show=True),
        Binding("y", "copy_path", "Copy", show=True),
        Binding("x", "close", "Close", show=True),
        Binding("escape", "close", "Close", show=False),
    ]

    def __init__(self, file_path: str, content: str, start_line: int, **kwargs):
        super().__init__(**kwargs)
        self.file_path = file_path
        self.content = content
        self.start_line = start_line

    def compose(self) -> ComposeResult:
        with Container(classes="preview-container"):
            yield Static(f"PREVIEW: {self.file_path}", classes="preview-header")
            yield ScrollableContainer(
                Static(self._render_code(), classes="preview-code"),
                classes="preview-scroll"
            )
            yield Static(self._render_footer(), classes="preview-footer")
```

##### DaemonClient

```python
class DaemonClient:
    """WebSocket client for communicating with Gundog daemon."""

    def __init__(self, url: str = "ws://localhost:9450"):
        self.url = url
        self._ws: WebSocketClientProtocol | None = None
        self._connected = False
        self._reconnect_delay = 1.0
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._message_handlers: dict[str, Callable] = {}

    async def connect(self) -> None:
        """Establish WebSocket connection with auto-reconnect."""
        ...

    async def query(
        self,
        query_text: str,
        index: str,
        top_k: int = 20,
        expand: bool = True,
    ) -> QueryResult:
        """Execute a search query."""
        ...

    async def list_indexes(self) -> list[IndexInfo]:
        """Get list of available indexes."""
        ...

    async def switch_index(self, index: str) -> None:
        """Switch to a different index."""
        ...

    def on_status_update(self, callback: Callable[[StatusUpdate], None]) -> None:
        """Register callback for daemon status updates."""
        ...


class LocalFileReader:
    """
    Reads files from local filesystem for preview.
    Preview is NOT fetched from daemon - files must exist locally.
    """

    def __init__(self, config: TuiConfig):
        self.config = config

    def can_preview(self, index_name: str) -> bool:
        """Check if preview is available for this index (local path configured)."""
        return self.config.get_local_path(index_name) is not None

    def read_file(
        self,
        index_name: str,
        relative_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        context_lines: int = 5,
    ) -> PreviewContent | None:
        """
        Read file content from local filesystem.

        Args:
            index_name: Name of the index (to look up local base path)
            relative_path: Relative file path as stored in index
            start_line: Optional start line (1-indexed)
            end_line: Optional end line (1-indexed)
            context_lines: Extra lines to include before/after range

        Returns:
            PreviewContent with file contents, or None if file not found
        """
        full_path = self.config.resolve_file_path(index_name, relative_path)
        if not full_path or not full_path.exists():
            return None

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            total_lines = len(lines)

            # Apply line range if specified
            if start_line is not None:
                actual_start = max(1, start_line - context_lines)
                actual_end = min(total_lines, (end_line or start_line) + context_lines)
                lines = lines[actual_start - 1 : actual_end]
                display_start = actual_start
            else:
                display_start = 1

            # Detect language from extension
            language = self._detect_language(relative_path)

            return PreviewContent(
                path=relative_path,
                full_path=str(full_path),
                content="\n".join(lines),
                start_line=display_start,
                end_line=display_start + len(lines) - 1,
                total_lines=total_lines,
                language=language,
            )
        except Exception:
            return None

    def _detect_language(self, path: str) -> str:
        """Detect language from file extension for syntax highlighting."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".rb": "ruby",
            ".md": "markdown",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".sh": "bash",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
        }
        ext = Path(path).suffix.lower()
        return ext_map.get(ext, "text")

    def open_in_editor(
        self,
        index_name: str,
        relative_path: str,
        line: int | None = None,
    ) -> bool:
        """
        Open file in external editor.

        Returns True if editor was launched, False if local path not configured.
        """
        full_path = self.config.resolve_file_path(index_name, relative_path)
        if not full_path:
            return False

        editor = self.config.editor or os.environ.get("EDITOR", "vi")

        if line and self.config.editor_line_flag:
            line_arg = self.config.editor_line_flag.format(line=line)
            subprocess.Popen([editor, line_arg, str(full_path)])
        else:
            subprocess.Popen([editor, str(full_path)])

        return True
```

### 6. Styling

#### 6.1 Color Palette

```tcss
$bg-primary: #0d1117;
$bg-secondary: #161b22;
$bg-tertiary: #21262d;
$border: #30363d;
$border-focus: #58a6ff;

$text-primary: #e6edf3;
$text-secondary: #8b949e;
$text-muted: #6e7681;

$accent: #58a6ff;
$accent-emphasis: #1f6feb;

$success: #3fb950;
$warning: #d29922;
$danger: #f85149;

$type-code: #7ee787;
$type-docs: #a371f7;
$type-config: #f78166;
$type-test: #79c0ff;
```

#### 6.2 Main Stylesheet (app.tcss)

```tcss
Screen {
    background: $bg-primary;
}

/* Header */
HeaderBar {
    dock: top;
    height: 1;
    background: $bg-secondary;
    color: $text-primary;
    padding: 0 1;
}

HeaderBar .title {
    text-style: bold;
    color: $accent;
}

HeaderBar .index-selector {
    color: $text-secondary;
}

HeaderBar .index-selector:hover {
    color: $accent;
}

/* Search */
SearchInput {
    dock: top;
    height: 1;
    background: $bg-secondary;
    border-bottom: solid $border;
    padding: 0 1;
}

SearchInput:focus {
    border-bottom: solid $border-focus;
}

/* Main content area */
.main-container {
    layout: horizontal;
}

/* Results pane */
ResultsPane {
    width: 40%;
    border-right: solid $border;
    padding: 0 1;
}

.section-header {
    color: $text-secondary;
    text-style: bold;
    padding: 1 0 0 0;
}

ResultItem {
    height: 2;
    padding: 0 1;
}

ResultItem:hover {
    background: $bg-secondary;
}

ResultItem.selected {
    background: $bg-tertiary;
    border-left: thick $accent;
}

ResultItem .path {
    color: $text-primary;
}

ResultItem .score {
    color: $success;
    text-style: bold;
}

ResultItem .type-code {
    color: $type-code;
}

ResultItem .type-docs {
    color: $type-docs;
}

ResultItem .type-config {
    color: $type-config;
}

ResultItem .lines {
    color: $text-muted;
}

/* Graph pane */
GraphPane {
    width: 60%;
    padding: 1;
}

GraphPane .controls {
    dock: top;
    height: 1;
    text-align: right;
    color: $text-secondary;
}

GraphPane .legend {
    dock: bottom;
    height: 3;
    color: $text-secondary;
}

GraphPane .focused-indicator {
    dock: bottom;
    height: 1;
    color: $accent;
}

/* Status bar */
StatusBar {
    dock: bottom;
    height: 1;
    background: $bg-secondary;
    color: $text-secondary;
    padding: 0 1;
}

StatusBar .connected {
    color: $success;
}

StatusBar .disconnected {
    color: $danger;
}

StatusBar .connecting {
    color: $warning;
}

/* Preview modal */
PreviewModal {
    align: center middle;
}

.preview-container {
    width: 80%;
    height: 80%;
    background: $bg-secondary;
    border: solid $border;
}

.preview-header {
    dock: top;
    height: 1;
    background: $bg-tertiary;
    color: $text-primary;
    padding: 0 1;
}

.preview-scroll {
    scrollbar-gutter: stable;
}

.preview-code {
    padding: 0 1;
}

.preview-footer {
    dock: bottom;
    height: 1;
    background: $bg-tertiary;
    color: $text-secondary;
    padding: 0 1;
}

/* Help modal */
HelpModal {
    align: center middle;
}

.help-container {
    width: 70;
    height: 30;
    background: $bg-secondary;
    border: solid $border;
    padding: 1;
}

.help-title {
    text-align: center;
    text-style: bold;
    color: $text-primary;
}

.help-section {
    color: $accent;
    text-style: bold;
    padding-top: 1;
}

.help-key {
    color: $text-primary;
    width: 12;
}

.help-desc {
    color: $text-secondary;
}

/* Index switcher modal */
IndexSwitcherModal {
    align: center middle;
}

.index-list-container {
    width: 45;
    height: auto;
    max-height: 20;
    background: $bg-secondary;
    border: solid $border;
}

.index-item {
    height: 1;
    padding: 0 1;
}

.index-item:hover {
    background: $bg-tertiary;
}

.index-item.current {
    color: $accent;
}

.index-item .name {
    width: 20;
}

.index-item .count {
    color: $text-muted;
}
```

### 7. Configuration

#### 7.1 Configuration Sources (Priority Order)

1. Command-line arguments (highest priority)
2. Environment variables
3. Config file (`~/.config/gundog/tui.yaml`)
4. Built-in defaults (lowest priority)

#### 7.2 Command-Line Arguments

```
gundog-tui [OPTIONS]

Options:
  -d, --daemon-url URL    Daemon WebSocket URL [default: ws://localhost:9450]
  -i, --index NAME        Initial index to use
  -t, --theme NAME        Color theme (dark, light) [default: dark]
  -c, --config PATH       Config file path [default: ~/.config/gundog/tui.yaml]
  --no-reconnect          Disable auto-reconnect on disconnect
  -v, --verbose           Enable debug logging
  -h, --help              Show this help message
  --version               Show version
```

#### 7.3 Environment Variables

| Variable | Description |
|----------|-------------|
| `GUNDOG_DAEMON_URL` | Daemon WebSocket URL |
| `GUNDOG_DEFAULT_INDEX` | Default index to use |
| `GUNDOG_TUI_THEME` | Color theme |
| `EDITOR` | External editor for file opening |

#### 7.4 Config File Format

```yaml
# ~/.config/gundog/tui.yaml

# Daemon connection
daemon_url: ws://localhost:9450
auto_reconnect: true
reconnect_max_delay: 30

# Default behavior
default_index: my-project
search_debounce_ms: 300

# Display
theme: dark

# Graph settings
graph_layout: spring  # spring, kamada_kawai, circular
graph_zoom_default: 1.0
graph_animation: true

# Preview/Edit settings
preview_context_lines: 5
preview_max_lines: 100
syntax_highlight: true

# Editor integration
editor: $EDITOR
editor_line_flag: +{line}  # Format for opening at specific line

# Local base paths for each index (enables preview and edit)
# These map daemon index names to local filesystem paths
# The daemon stores relative paths; TUI joins with local_paths to access files
local_paths:
  my-project: ~/code/my-project
  charmarr-docs: ~/projects/charmarr
  work-codebase: /home/user/work/main-repo
  # Indexes without entries here will have preview/edit disabled
```

#### 7.5 Config Loading

```python
@dataclass
class TuiConfig:
    daemon_url: str = "ws://localhost:9450"
    auto_reconnect: bool = True
    reconnect_max_delay: int = 30
    default_index: str | None = None
    search_debounce_ms: int = 300
    theme: str = "dark"
    graph_layout: str = "spring"
    graph_zoom_default: float = 1.0
    graph_animation: bool = True
    preview_context_lines: int = 5
    preview_max_lines: int = 100
    syntax_highlight: bool = True
    editor: str | None = None
    editor_line_flag: str = "+{line}"
    local_paths: dict[str, str] = field(default_factory=dict)  # index_name -> local_path

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        cli_args: dict | None = None,
    ) -> "TuiConfig":
        """Load config from file, env vars, and CLI args."""
        ...

    def get_local_path(self, index_name: str) -> Path | None:
        """Get configured local base path for an index, or None if not configured."""
        path_str = self.local_paths.get(index_name)
        if path_str:
            return Path(path_str).expanduser()
        return None

    def set_local_path(self, index_name: str, path: str | None) -> None:
        """Set or clear local base path for an index. Persists to config file."""
        if path:
            self.local_paths[index_name] = path
        elif index_name in self.local_paths:
            del self.local_paths[index_name]
        self._save()

    def resolve_file_path(self, index_name: str, relative_path: str) -> Path | None:
        """
        Resolve a relative file path from the index to an absolute local path.
        Returns None if no local base path is configured for the index.
        """
        base = self.get_local_path(index_name)
        if base:
            return base / relative_path
        return None
```

### 8. Project Structure

```
gundog-tui/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── gundog_tui/
│       ├── __init__.py
│       ├── __main__.py           # Entry point
│       ├── app.py                # GundogApp main class
│       ├── config.py             # Configuration loading
│       ├── client.py             # DaemonClient WebSocket handler
│       ├── local_files.py        # LocalFileReader for preview/edit
│       ├── types.py              # Data classes and type definitions
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── header.py         # HeaderBar widget
│       │   ├── search.py         # SearchInput widget
│       │   ├── results.py        # ResultsPane, ResultItem widgets
│       │   ├── graph.py          # GraphPane widget
│       │   └── status.py         # StatusBar widget (includes local path indicator)
│       ├── modals/
│       │   ├── __init__.py
│       │   ├── preview.py        # PreviewModal (reads local files)
│       │   ├── local_path.py     # LocalPathModal (configure local base path)
│       │   ├── index_switcher.py # IndexSwitcherModal
│       │   └── help.py           # HelpModal
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── layout.py         # NetworkX layout computation
│       │   ├── renderer.py       # Graph rendering logic
│       │   └── braille.py        # BrailleCanvas implementation
│       └── styles/
│           └── app.tcss          # Textual CSS styles
└── tests/
    ├── __init__.py
    ├── conftest.py               # Pytest fixtures
    ├── test_app.py               # App integration tests
    ├── test_client.py            # DaemonClient tests
    ├── test_local_files.py       # LocalFileReader tests
    ├── test_graph.py             # Graph layout/render tests
    └── mocks/
        └── daemon.py             # Mock daemon for testing
```

### 9. Dependencies

#### 9.1 Required

```toml
[project]
dependencies = [
    "textual>=0.50.0",
    "rich>=13.0.0",
    "networkx>=3.0",
    "websockets>=12.0",
    "pyyaml>=6.0",
]
```

#### 9.2 Optional

```toml
[project.optional-dependencies]
canvas = ["textual-canvas>=0.2.0"]
clipboard = ["pyperclip>=1.8.0"]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21.0",
    "pytest-textual-snapshot>=0.4.0",
]
```

### 10. Error Handling

#### 10.1 Connection Errors

| Scenario | Behavior |
|----------|----------|
| Daemon unreachable | Show "disconnected" status, queue queries, auto-reconnect |
| Connection lost | Show "connecting" status, attempt reconnect with backoff |
| Authentication failed | Show error toast, prompt for credentials if applicable |
| Timeout | Retry request once, then show error toast |

#### 10.2 Query Errors

| Scenario | Behavior |
|----------|----------|
| No results | Show "No matches found" in results pane |
| Invalid query | Show error inline in search bar |
| Index not found | Show error toast, offer to switch index |
| Rate limited | Show warning toast with retry countdown |

#### 10.3 Preview Errors

| Scenario | Behavior |
|----------|----------|
| File not found | Show error in preview modal |
| File too large | Show truncated content with warning |
| Binary file | Show "Cannot preview binary file" message |
| Encoding error | Attempt fallback encodings, show raw if fails |

#### 10.4 User Feedback

- **Toast notifications**: Transient errors (connection issues, timeouts)
- **Inline messages**: Contextual errors (no results, invalid input)
- **Modal dialogs**: Critical errors requiring acknowledgment
- **Status bar**: Persistent state (connection status, indexing progress)

### 11. Testing Strategy

#### 11.1 Unit Tests

- Config loading and merging
- Graph layout computation
- Braille canvas rendering
- Message serialization/deserialization
- Navigation algorithms

#### 11.2 Widget Tests

- Use Textual's snapshot testing for visual regression
- Test keyboard navigation flows
- Test focus management
- Test reactive state updates

#### 11.3 Integration Tests

- Mock WebSocket server for client testing
- End-to-end search flow
- Index switching
- Preview loading

#### 11.4 Mock Daemon

```python
class MockDaemon:
    """Mock Gundog daemon for testing."""

    def __init__(self, host: str = "localhost", port: int = 9451):
        self.host = host
        self.port = port
        self.indexes = {
            "test-index": {
                "files": 100,
                "last_updated": "2025-01-15T10:00:00Z"
            }
        }
        self.mock_results = {...}

    async def start(self) -> None:
        """Start mock WebSocket server."""
        ...

    async def stop(self) -> None:
        """Stop mock server."""
        ...

    def set_query_response(self, query: str, response: dict) -> None:
        """Configure response for specific query."""
        ...
```

## Consequences

### Positive

- **Lightweight client**: TUI can be installed without heavy dependencies (no ML frameworks)
- **Remote access**: Works over SSH for remote daemon interaction
- **Keyboard-driven**: Full functionality without mouse, efficient for power users
- **Visual graph**: Unique differentiator, provides intuitive exploration of relationships
- **Consistent UX**: Similar visual language to web UI
- **Flexible file access**: Works with local clones of any repo, not tied to git
- **No daemon file serving**: Preview reads local files, simpler daemon protocol

### Negative

- **Terminal limitations**: Graph rendering quality depends on terminal font/size
- **Additional package**: Separate installation from main gundog package
- **Daemon dependency**: Requires running daemon for search (but not for preview)
- **Local path requirement**: Preview/edit requires user to have files locally and configure path

### Neutral

- **Textual dependency**: Ties to Textual's development roadmap
- **Configuration**: Multiple config sources adds flexibility but complexity
- **Git optional**: Git metadata enables browser links but isn't required

## Implementation Notes

### Local Path Configuration UX

The TUI should guide users to configure local paths naturally:

1. **First search on new index**: If no local path configured, show non-intrusive hint in status bar
2. **Attempting preview**: If user presses Enter/p without local path, show toast with `[L]` hint
3. **Easy configuration**: `L` key opens modal with path validation and sample file verification
4. **Persistence**: Paths saved to config file, survive app restarts

### Feature Availability Matrix

| Daemon State | Local Path | Git Metadata | Available Features |
|--------------|------------|--------------|-------------------|
| Connected | ✗ | ✗ | Search, graph, copy relative path |
| Connected | ✓ | ✗ | + Preview, edit in $EDITOR |
| Connected | ✗ | ✓ | + Open in browser, copy git URL |
| Connected | ✓ | ✓ | All features |
| Disconnected | ✓ | - | None (search requires daemon) |

## References

- [Textual Documentation](https://textual.textualize.io/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [NetworkX Documentation](https://networkx.org/documentation/stable/)
- [Unicode Braille Patterns](https://en.wikipedia.org/wiki/Braille_Patterns)
- [textual-canvas Repository](https://github.com/davep/textual-canvas)
- [Force-Directed Graph Drawing](https://en.wikipedia.org/wiki/Force-directed_graph_drawing)
