"""Help text for the TUI."""

from gundog_client._tui._theme import Colors

HELP_TEXT = f"""[{Colors.SECONDARY.value} bold]NAVIGATION[/]
[{Colors.ACCENT.value}]j / [/]        Next result
[{Colors.ACCENT.value}]k / [/]        Previous result
[{Colors.ACCENT.value}]g / G[/]        First / Last result
[{Colors.ACCENT.value}]Enter[/]        Open in editor

[{Colors.SECONDARY.value} bold]SEARCH[/]
[{Colors.ACCENT.value}]/[/]            Focus search
[{Colors.ACCENT.value}]Esc[/]          Back to results

[{Colors.SECONDARY.value} bold]MANAGEMENT[/]
[{Colors.ACCENT.value}]i[/]            Switch index
[{Colors.ACCENT.value}]L[/]            Set local path
[{Colors.ACCENT.value}]D[/]            Set daemon URL
[{Colors.ACCENT.value}]R[/]            Force reconnect
[{Colors.ACCENT.value}]?[/]            Toggle help
[{Colors.ERROR.value}]q[/]            Quit

[{Colors.MUTED.value}]Press ? to close[/]"""
