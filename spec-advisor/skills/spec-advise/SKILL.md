---
name: spec-advise
description: >
  開発タスクの内容から、実装着手前に書くべき設計・計画系成果物（WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / Issue粒度=issue-design / 実装一気通貫=feature-dev）を判断して提案する。
  トリガー: 「何から設計する」「spec 選択」「どの設計手法を選ぶ」「設計いる?」「先に仕様書く?」「bdd と design-doc どっち」「実装前に何を用意する」「/spec-advise」「spec advisor」
allowed-tools:
  - Skill
  - AskUserQuestion
  - Bash
  - Read
  - Grep
effort: medium
---

# spec-advise — 設計・計画の spec ルーティング

開発タスクを受けて、**実装に入る前に**「どの設計・計画系成果物を先に書くべきか」を判定し提案する。
判定の正本は `references/routing-rubric.md`（この skill と ambient rule が共有する SSoT）。

## このスキルの責務境界

- **する**: タスク → 軸（WHAT / HOW / WHY / Issue 粒度 / 実装）の分類と、該当 skill の起動提案・委譲。
- **しない**: 成果物そのものの生成（各 skill の領分）。spec/doc の品質評価（`bdd-spec:evaluate-spec` / `design-doc:design-review` の領分）。コードレビュー（`code-review`）。
- 分類が「実装した方が速い」に落ちたら **黙って実装へ**（提案しないのも正しい出力）。

## 手順

1. `references/routing-rubric.md` を Read する。
2. **guard を先に適用**（ファネル第 1 段）: bugfix / typo / 設定変更 / 軽微 refactor / 影響が数行に閉じる / 既存 spec に沿うだけ → **提案せず終了**。
3. **dormant 判定**（Bash・enabled-only）: グローバル + プロジェクトローカルの settings（`$HOME/.claude/settings.json`・`$CLAUDE_PROJECT_DIR/.claude/settings.json`・同 `settings.local.json`）を `grep -Eq '"<plugin>@[^"]*"[[:space:]]*:[[:space:]]*true'` で走査し、`bdd-spec` / `design-doc` / `adr-keeper` / `feature-dev` / `linear-workflow` / `indie-workflow` の**有効**を確認する（`": false"` の無効化-but-インストール済みは除外＝#74 の誤検知回避。project-scoped 有効化も取りこぼさない）。有効な軸だけを提案候補にする。
4. **effort 分岐**（`${CLAUDE_EFFORT}`）:
   - `low` / `medium`: タスク説明のみで軸を判定。
   - `high` / `xhigh` / `max`: 関連 Issue / コードを Read・Grep で軽く確認し、影響範囲・複数コンポーネント波及・既存 spec の有無を裏取りしてから判定（over-suggestion 抑制の精度を上げる）。
5. rubric の signal 表で軸を判定する（複数該当は組み合わせる）。
6. 提示:
   - 確信度が高い → 質問せず 1 文の根拠を添えて「{推奨} を先に書くのを勧める」と提案。
   - 迷う → **AskUserQuestion**（question:「着手前に {推奨} を書きますか？（{根拠}）」／ header: `spec 選択` ／ options: 導入済みの軸のみ、推奨を先頭に `(推奨)`、「不要（直接実装）」を必ず含む）。
7. ユーザーが軸を選んだら該当コンポーネントを起動する（**委譲手段は軸ごとに異なる**）:
   - WHAT → `Skill` tool で `bdd-spec:create-spec`（role / want / why を渡せれば非対話 API、不足なら通常起動）
   - HOW → `Skill` tool で `design-doc:design-doc`
   - WHY → `Skill` tool で `adr-keeper:adr`
   - Issue 粒度 → `Skill` tool で `linear-workflow:issue-design` または `indie-workflow:issue-design`（導入済みの方。両者は**同名 skill** なので namespace を明示して起動する）
   - 実装 → `feature-dev` は **command 専用**プラグイン（skill を持たない）。`Skill` tool では起動できないので、`/feature-dev` の実行を案内する。
   - 「不要」→ 起動せず実装へ。
8. **提案は 1 回のみ。** 断られたら同一タスクで再提案しない（作業の流れを止めない）。

## 設計メモ（コスト×精度・モデルルーティング）

- 採用原則: **#1 ファネル**（over-suggestion guard を先頭で安価に落とす）、**#10 確信度フィールド化**（迷い時のみ AskUserQuestion、断定で提案を押し付けない）、**#3 段階予算の縮小版**（`${CLAUDE_EFFORT}` で裏取りの深さを変える）。
- あえて捨てた原則: **#5 暴走ガード / #7 敵対的独立検証 / #8 外部オラクル fail-closed** — 単一の分類判断に多段検証は過剰。
- モデルルーティング: 本 skill はエージェント fan-out を持たない単一分類判断のため適用外（メインループのモデルで実行する）。

## dormant / 独立性

- 連携先（`bdd-spec` / `design-doc` / `adr-keeper` / `feature-dev` / `issue-design`）はすべて optional。未導入は提案肢から外し、全て未導入なら沈黙する（プラグイン独立性）。
- ambient 経路: SessionStart hook が `rules/advisor-rule.md` を注入し、明示起動でなくても開発タスク検知時に本ルーティングを促す。対象プラグインが 1 つも無ければ注入しない。
