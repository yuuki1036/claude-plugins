# routing-axes — spec ルーティング軸対応（正本）

WHAT / HOW / WHY の軸→プラグイン対応の正本。下の delimiter 区間を消費サイトに複製して埋め込む。

- 消費サイト:
  - `spec-advisor/skills/spec-advise/references/routing-rubric.md`
  - `linear-workflow/skills/issue-create/SKILL.md`（Phase 5）
  - `indie-workflow/skills/indie-issue-create/SKILL.md`（Phase 8）
- 同期検証: `validate_plugin_quality.py` の routing-axes 同期チェック（Critical）。
  マーカー行（`ROUTING-AXES:START` / `END`）に挟まれた区間を **dedent 後に比較**する
  （消費サイト側はリスト内などで一様なインデントを付けてよい。それ以外の差分は fail）。
- 変更手順: この正本を編集 → 全消費サイトの区間に同じ内容を反映 → `/quality-check` で同期確認。
  型別の判定（bugfix→不要 等）や拡張軸（Issue 粒度 / 実装）は各サイトの文脈特化であり、
  この区間には含めない（同期対象は 3 軸コアのみ）。
- 設計判断: `.claude/designs/20260708-spec-routing-ssot.md`

<!-- ROUTING-AXES:START -->
| 軸 | シグナル | 委譲先 | 出力先 |
|---|---|---|---|
| **WHAT** | ユーザー可視な振る舞い・受け入れ条件が中心（新機能・仕様変更） | `bdd-spec:create-spec` | Scenario/Examples を `features/` に |
| **HOW** | 技術方式の選定・代替案比較・複数 Issue/コンポーネントに波及 | `design-doc:design-doc` | トレードオフ比較を `.claude/designs/` に |
| **WHY** | 単一の重要な設計判断（ライブラリ・方針）を理由ごと残す | `adr-keeper:adr` | 決定を `.claude/adr/` に append-only |
<!-- ROUTING-AXES:END -->
