---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Skill]
---

相談対象のプラグイン `demo-plugin` の全ファイルを以下に貼ります（手元にファイルは無いので、これが実物です。これ以外のファイルは存在しません）。

demo-plugin に新しい skill `blame-check` を追加したいと思っています。やりたいことは「コミットを作る前に、変更した行の `git blame` を見て、直近でその行を触った人が他にいれば注意として提示する」です。新 skill として追加してよいか、退路確保の観点で判断してください。判断の根拠は demo-plugin の実際のファイル内容（allowed-tools・phase 構成・トリガー）を引いて示してください。

## demo-plugin/.claude-plugin/plugin.json

```json
{
  "name": "demo-plugin",
  "version": "1.2.0",
  "description": "Git コミット作成を補助する開発ワークフロー",
  "author": { "name": "demo" }
}
```

## demo-plugin/commands/commit.md

~~~markdown
---
description: "変更を分析して原子性重視のコミットを作成する トリガー: 「コミットして」「/commit」"
allowed-tools:
  - Bash
  - Read
  - Grep
  - AskUserQuestion
---

`git-commit-helper` スキルを実行する（`${CLAUDE_PLUGIN_ROOT}/skills/git-commit-helper/SKILL.md` を Read して従う）。

引数: $ARGUMENTS
~~~

## demo-plugin/skills/git-commit-helper/SKILL.md

~~~markdown
---
name: git-commit-helper
description: >
  変更を分析し、論理的な作業単位に分割して Conventional Commits 準拠のメッセージでコミットする。
  トリガー: 「コミットして」「変更をコミット」「/commit」
allowed-tools:
  - Bash
  - Read
  - Grep
  - AskUserQuestion
---

# Git Commit Helper

## Phase 1: 変更の把握

`git status` と `git diff` で変更ファイルと内容を把握する。

## Phase 2: 作業単位への分割

変更を論理的な単位（機能追加 / 修正 / リファクタ）に分け、単位ごとにステージする。混在していれば `git add -p` で分ける。

## Phase 3: メッセージ生成

Conventional Commits（`<type>(<scope>): <description>`）でメッセージを組み立てる。本文には「なぜ」を書き、「何を」は diff に任せる。

## Phase 4: 確認とコミット

生成したメッセージを提示し、AskUserQuestion で承認を得てから `git commit` する。Protected branch（main / master）への直接コミットは `--no-protect` が無い限り止める。
~~~
