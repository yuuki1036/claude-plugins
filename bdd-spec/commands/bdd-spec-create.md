---
description: BDD spec 駆動の user story を scaffold する（user story dir + epic.md + spec.md）
user_invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/create-spec/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/bdd-spec-create` でも `Skill` tool の `bdd-spec:bdd-spec-create` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `bdd-spec@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

create-spec スキルを使って、BDD spec 駆動の user story を scaffold してください。

引数（`$ARGUMENTS`）は `key=value` 形式で渡せる。どのキーが必須で、何が揃えばヒアリングを省くかは SKILL.md の「API 安定保証」の表に従う（`shortPath=true` のときに要るキーもそこにある）。引数が無ければ SKILL.md の Phase 1 のとおり、会話から分からない値だけを聞く。
