# StrataLedger - instructions for Codex

The project rules are in CLAUDE.md; read it first. It wins over anything here.

- Done, review gate and fix mode: .claude/rules/workflow-standards.md.
- Work only in your own worktree, never in this folder:
  `git worktree add ..\StrataLedger-codex -b codex/<task> origin/main`. Never push to main; stage files by explicit
  path. A Codex branch is reviewed (copilot-reviewer) before it is merged.
- The subagent definitions in .codex/agents/ mirror .claude/agents/; where they differ, .claude/agents/ wins.
