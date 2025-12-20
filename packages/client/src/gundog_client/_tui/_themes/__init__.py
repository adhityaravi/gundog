"""Available TUI themes.

To add a new theme:
1. Create a new file in this folder (e.g., _catppuccin.py)
2. Define a Colors enum with the same semantic names
3. Define a THEME using textual.theme.Theme
4. Export them here
"""

from gundog_client._tui._themes._dracula import THEME as DRACULA_THEME
from gundog_client._tui._themes._dracula import Colors as DraculaColors

__all__ = [
    "DRACULA_THEME",
    "DraculaColors",
]
