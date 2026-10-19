---
description: BDD spec (spec.md / epic.md) を 5 観点で静的レビューする品質ゲート
user_invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/evaluate-spec/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/bdd-spec-evaluate` でも `Skill` tool の `bdd-spec:bdd-spec-evaluate` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `bdd-spec@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

evaluate-spec スキルを使って、埋めた BDD spec を静的レビューしてください。

## 引数

`$ARGUMENTS`:
- 未指定 → `{featuresDir}/*/spec.md`（`featuresDir` の既定は `features`）から対象を選ぶ。選び方は SKILL.md の Phase 0
- パス指定（例: `features/{dirname}/spec.md` または story ディレクトリ）→ その spec を対象
- `spec=<path>` 形式 → 非対話で対象を確定（feature-dev embed 用途）
