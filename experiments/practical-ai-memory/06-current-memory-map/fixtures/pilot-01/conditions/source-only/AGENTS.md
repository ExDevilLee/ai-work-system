# Agent Instructions

- Navigate the synthetic Markdown records directly.
- Do not assume that a separate index or state projection exists.
- Compare all records relevant to the assigned topic before deciding what can
  guide current action.
- Cite only the relative source paths actually used.
- Do not use information outside this isolated synthetic workspace.
- Use only `cat`, `sed`, `nl`, and `rg` for workspace navigation and reading.
- Do not run Python, Node, shell scripts, or other interpreters.
