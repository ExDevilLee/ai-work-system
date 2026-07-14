# Minimum Project Memory Template

Chinese version: [README.md](README.md)

This template establishes the minimum context for a project that involves long-term collaboration with AI. It does not require a knowledge base or complex tools. It starts by answering three questions:

1. What is this project?
2. What rules should the AI follow when continuing the work?
3. What is the project's current state?

## Directory Structure

```text
project-en/
├── README.md
├── AGENTS.md
└── PROJECT-STATE.md
```

- `README.md`: the project entry point for people and AI, covering the goal, scope, source of truth, and commonly used entry points.
- `AGENTS.md`: collaboration rules for AI, covering reading order, modification boundaries, validation, and information security.
- `PROJECT-STATE.md`: the current work state, covering the goal, progress, next steps, blockers, and recent decisions.

Each file answers one kind of question: README explains "what this is," AGENTS explains "how to work," and PROJECT-STATE explains "where the work currently stands."

Different AI agent tools may load different rule filenames by default. Codex App and Codex CLI usually use `AGENTS.md`, while Claude Code usually uses `CLAUDE.md`. Before using the template, confirm the rule entry point for your tool. If you need to rename the file, its responsibility and content do not need to change.

## How to Use It

1. Copy the three files from [`project-en/`](project-en/) into your project root.
2. Search for placeholders in the `{...}` format and replace them with real project information.
3. Remove examples that do not apply. Do not keep empty rules just to make the template look complete.
4. Confirm the rule filename used by your tool, and make sure that rule entry point tells the AI to continue reading `README.md` and `PROJECT-STATE.md`.
5. Update `PROJECT-STATE.md` after completing a stage. Only move an experience into the rule entry point after it has been validated and is likely to affect future work repeatedly.

Use the following command to find placeholders that have not been replaced:

```bash
rg -n '\{[^}]+\}' README.md AGENTS.md PROJECT-STATE.md
```

## Maintenance Boundaries

- Keep one source of truth for each fact; use links from other files.
- Put temporary progress in `PROJECT-STATE.md` and stable rules in `AGENTS.md`.
- Do not write passwords, tokens, cookies, private keys, or sensitive customer information into these files.
- Do not preserve every chat transcript. Prefer validated conclusions that can be reused later.
- When files start growing, clean up outdated content before adding more memory tools.

## When to Extend the System

Only consider adding a task ledger, operating guide, automated checks, or knowledge index after these three files have been used in real work and the same kind of problem still occurs repeatedly. Extensions should reduce repeated explanation, not merely make the system look more sophisticated.
