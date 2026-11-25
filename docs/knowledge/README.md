# docs/knowledge: project knowledge base

This folder is the project's shared memory, for the whole team and for any AI assistant
(Claude, Copilot, Cursor, Codex, ...). It is synced through git: pull before relying
on it, and commit and push after updating it, so everyone sees the changes.

## Files

| File | Contents |
|---|---|
| `INDEX.md` | One line per file or folder: what is where. Read this first. |
| `problems/YYYY-MM-DD-<slug>.md` | One problem per file: `Status: open/solved`, `Who:`, notes, and the fix with *why* it worked. |
| `architecture.md` | How the system fits together. |
| `decisions/YYYY-MM-DD-<slug>.md` | One real design choice per file: context, decision, why, alternatives, status. |
| `gotchas.md` | Traps worth remembering ("don't do X, it breaks Y"). |

One file per problem and per decision means teammates rarely get merge conflicts.

## Rules

- New problem: add a file to `problems/` (`Status: open`, `Who:`, what's wrong). Add
  dated lines under `## Notes` as you go.
- Solved (confirmed by the person who reported it): set `Status: solved`, add
  `Solved: YYYY-MM-DD` and fill `## Fix` with what fixed it and why that was the cause.
  Keep the file.
- A decision is only recorded when X was chosen over Y for a reason. Before it's pushed
  you can still edit it. After that, don't rewrite it: add a new file and mark the old
  one `Status: superseded by <file>`.
- Everything here is shared with the whole team and stays in git history forever. Never
  write sensitive data down (customer or personal data, credentials, internal hosts,
  notes about people). Write a pointer to where it is instead, e.g. "login: password
  manager, entry 'prod db'".
- Keep entries short. Record the "why"; the diff already shows the "what".
- Commit knowledge changes on their own: `knowledge: <topic>`.
