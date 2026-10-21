---
description: "複数の作業セッションで進める PJ を、1 つの hub セッションから束ねる。状態（作業セッション・PR・Issue・確かめた事実）は ~/.claude/project-hub/ のファイルに置き、作業側の report を取り込み、brief / relay は送る直前に宛先を引き直す。サブコマンド init / status / brief / relay / fact / takeover / close。 トリガー: 「hub を作って」「hub init」「hub status」「hub の状況」「hub から brief」「hub から relay」「hub を引き継ぐ」「/project-hub:hub」"
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - ListAgents
  - SendMessage
  - mcp__linear__list_issues
  - mcp__linear__get_issue
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/hub/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `project-hub@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。SKILL.md と `references/` の中の `${CLAUDE_PLUGIN_ROOT}` も、SKILL.md を読んだのと同じ root に読み替える。

このセッションの id: `${CLAUDE_SESSION_ID}`（SKILL.md の手順で、Bash の `CLAUDE_CODE_SESSION_ID` が空のときだけ `--session-id` に渡す。SKILL.md は Read で読むのでこの変数が展開されない）

引数: `$ARGUMENTS`（サブコマンドと PJ 名。サブコマンドが無ければ `status`）
