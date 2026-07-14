---
description: 開発タスクから適切な設計・計画系成果物（bdd-spec / design-doc / adr-keeper / issue-design / feature-dev）を判断して提案する
allowed-tools:
  - Skill
  - AskUserQuestion
  - Bash
  - Read
  - Grep
---

`spec-advise` スキルを起動し、実装着手前に書くべき設計・計画系成果物を判定・提案する。

- 引数 `$ARGUMENTS` があればそれを対象タスクの説明として扱う。無ければ直近の会話文脈から対象タスクを推定する。
- 判定基準・手順・提示方法はスキル本体（`skills/spec-advise/SKILL.md` と `references/routing-rubric.md`）に従う。
- guard に該当する軽微なタスク（bugfix / typo / 設定変更）では提案せず、その旨だけ短く伝える。

`Skill` tool で `spec-advise` を起動すること。
