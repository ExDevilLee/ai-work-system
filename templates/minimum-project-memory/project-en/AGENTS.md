# Agent Instructions

## Default Reading Order

1. `README.md`: confirm the project goals, scope, and sources of truth.
2. `PROJECT-STATE.md`: confirm the current stage, next steps, and blockers.
3. Read the code or documentation directly related to the current task.

Do not load the entire project history by default. Read additional material only when the current task requires it.

## Working Rules

- Inspect the current worktree before making changes, and do not overwrite unrelated work.
- Prefer the project's existing structure and tools. Do not add complex machinery for a one-time problem.
- Modify only the files required for the current task, and explain behavioral or content changes.
- Run the minimum validation commands listed in `README.md` after making changes.
- If a change affects project state, entry points, or long-term rules, update the corresponding files.
- {Add collaboration rules specific to this project.}

## Content Boundaries

- Authoritative content source: {List the files or directories that may be edited directly.}
- Generated output or presentation layer: {List files, directories, or platforms that should not be edited as sources.}
- Local temporary notes: {State where they belong and whether they should be committed.}

## Information Security

- Do not write passwords, tokens, cookies, private keys, or sensitive customer information into documentation, commits, or output.
- Before interacting with external services, production environments, deletion operations, or irreversible actions, explain the impact and validation method.
- If you cannot confirm whether information may be made public, keep it private and ask the project owner.

## Completion Checklist

- The requested changes are complete within the agreed scope.
- Required tests or checks have passed.
- `PROJECT-STATE.md` reflects the new progress and next steps.
- No unrelated files, sensitive information, or unexplained generated output are included.
