"""Help text for the TUI."""

from gundog_client._tui._theme import DraculaColors

HELP_TEXT = f"""[{DraculaColors.PINK.value} bold]NAVIGATION[/]
[{DraculaColors.CYAN.value}]j / [/]        Next result
[{DraculaColors.CYAN.value}]k / [/]        Previous result
[{DraculaColors.CYAN.value}]g / G[/]        First / Last result
[{DraculaColors.CYAN.value}]Enter[/]        Open in editor

[{DraculaColors.PINK.value} bold]SEARCH[/]
[{DraculaColors.CYAN.value}]/[/]            Focus search
[{DraculaColors.CYAN.value}]Esc[/]          Back to results

[{DraculaColors.PINK.value} bold]MANAGEMENT[/]
[{DraculaColors.CYAN.value}]i[/]            Switch index
[{DraculaColors.CYAN.value}]L[/]            Set local path
[{DraculaColors.CYAN.value}]D[/]            Set daemon URL
[{DraculaColors.CYAN.value}]R[/]            Force reconnect
[{DraculaColors.CYAN.value}]?[/]            Toggle help
[{DraculaColors.RED.value}]q[/]            Quit

[{DraculaColors.COMMENT.value}]Press ? to close[/]"""
