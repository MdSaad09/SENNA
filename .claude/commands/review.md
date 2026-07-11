---
description: Run SENNA's full review battery (code-reviewer + spec-auditor) on the current branch
allowed-tools: Read, Grep, Glob, Task, Bash(git diff:*), Bash(git log:*), Bash(git status:*)
---
Scope:
!`git status --short --branch`
!`git diff main...HEAD --stat`

Run the code-reviewer subagent and the spec-auditor subagent over the diff between main
and this branch. If $ARGUMENTS names specific paths or topics, narrow both agents to
that scope. Merge their findings into ONE report ordered Blocker -> Major -> Minor ->
Nit, each with file:line, the problem, the citation (F-xx, E-xx, interpretability
contract row, or human-code rule), and a concrete fix. End with the list of fixes you
recommend applying now and the question "apply them?". Change no files until Saad
answers.
