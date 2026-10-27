---
description: "project-hub の hub が束ねる PJ の sub（作業セッション）から、決まった形の report（hello / in_progress / blocked / ready_for_review / done・PR・lead の判断待ち・hub への質問・follow-up・出典つきの主張・決まったこと・待っている PR）を hub の inbox にファイルで置き、hub には「置いた」とだけ知らせる。 トリガー: 「hub に報告」「hub に report」「hub に hello」「report を置いて」「/project-hub:report」"
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - ListAgents
  - SendMessage
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/report/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `project-hub@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。SKILL.md と `references/` の中の `${CLAUDE_PLUGIN_ROOT}` も、SKILL.md を読んだのと同じ root に読み替える。

このセッションの id: `${CLAUDE_SESSION_ID}`（SKILL.md の手順で、Bash の `CLAUDE_CODE_SESSION_ID` が空のときだけ `--session-id` に渡す。SKILL.md は Read で読むのでこの変数が展開されない）

引数: `$ARGUMENTS`（`--project <PJ>` と state。brief が渡した形のまま）
