---
description: "AI が課題を発見して issue を自動起票 トリガー: 「課題を見つけて」「issue を自動で作って」「やることを洗い出して」「バグを探して起票」「タスク発掘」「何かやることない？」「課題発見」「/discover」"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Skill
  - Agent
argument-hint: "[PROJECT-SLUG]"
---

ユーザーの「課題を見つけて」「issue を自動で作って」「やることを洗い出して」リクエストに応じて、プロジェクトを多観点でスキャンし、取り組むべき課題を発見して issue を自動起票する。

`${CLAUDE_PLUGIN_ROOT}/skills/discover/SKILL.md` のワークフローに従って実行する。

起動＝実行確定。止まらずスキャン → 自動起票 → 実行後レポートまで進める。詳細な観点・優先度付け・frontmatter 形式・安全弁（上限 N / status: backlog / 重複除外）はスキル定義を参照。
