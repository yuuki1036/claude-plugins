---
description: "新機能をコードベース理解 → 設計 → 実装 → 検証まで 8 phase で一気通貫に進める（explorer/architect agent・BDD spec ゲート・静的オラクル・self-review 委譲つき） トリガー: 「機能開発」「新機能を実装」「この機能を作りたい」「実装計画を立てて」「設計から実装まで」「一気通貫で実装」「/feature-dev」 引数: [機能の説明・Issue ID（省略可）]"
argument-hint: "[機能の説明 | Issue ID]（省略時は Phase 1 でヒアリング）"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Agent
  - TodoWrite
  - AskUserQuestion
  - Skill
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/feature-dev/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `feature-dev@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

feature-dev スキルを使用して、機能開発ワークフローを実行してください。

初期リクエスト: $ARGUMENTS

- 引数が Issue ID（`[A-Z]+-\d+` 形式）なら Phase 1.5 の Issue Context Detection で該当 Issue ファイルを読み、そこを要件の出発点にしてください。
- 引数が空なら Phase 1 でユーザーに何を作るのかをヒアリングしてください。
- 引数に `spec=<path>` が含まれていれば Phase 1.3 の BDD spec 作成を skip し、そのパスを spec として Phase 4 へ渡してください。
