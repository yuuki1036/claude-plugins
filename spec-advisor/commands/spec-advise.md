---
description: "開発タスクから適切な設計・計画系成果物（bdd-spec / design-doc / adr-keeper / issue-design / feature-dev）を判断して提案する トリガー: 「何から設計する」「spec 選択」「どの設計手法を選ぶ」「設計いる?」「先に仕様書く?」「bdd と design-doc どっち」「実装前に何を用意する」「/spec-advise」「spec advisor」"
allowed-tools:
  - Skill
  - AskUserQuestion
  - Bash
  - Read
  - Grep
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/spec-advise/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `spec-advisor@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

`spec-advise` スキルを起動し、実装着手前に書くべき設計・計画系成果物を判定・提案する。

- 引数 `$ARGUMENTS` があればそれを対象タスクの説明として扱う。無ければ直近の会話文脈から対象タスクを推定する。
- 判定基準・手順・提示方法はスキル本体（`skills/spec-advise/SKILL.md` と `references/routing-rubric.md`）に従う。
- guard に該当する軽微なタスク（bugfix / typo / 設定変更）では提案せず、その旨だけ短く伝える。

