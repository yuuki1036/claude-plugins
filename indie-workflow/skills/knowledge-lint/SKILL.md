---
name: knowledge-lint
description: >
  knowledge の健全性を点検・修復する（lint）。検索・参照ではなくグラフの保守が目的。
  broken wikilink・孤立 / 重複ページ・index 不整合・tags 表記ゆれを検出し、機械的に直せるものは承認制で修正する。
  トリガー: 「knowledge lint」「ナレッジ点検」「リンク切れチェック」「リンク切れ」「孤立した知見」「knowledge の健全性」「knowledge を整理」「/knowledge-lint」
effort: medium
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
---

# Knowledge Lint

knowledge グラフ（`source` ↔ `concept` を `[[name]]` で繋いだ集合）の健全性を点検するスキル。
人間が維持すると指数的に増えるクロスリファレンスの保守コストを肩代わりする。検出は決定的チェックを優先し、機械的に直せるものだけを承認制で修正する。判断が要るものは提案に留める。

knowledge の種類（source / concept）と wikilink 記法の定義は `knowledge` スキルの SKILL.md を参照。

---

## Phase 0: プロジェクト特定

1. `git branch --show-current` でブランチ名から Issue ID プレフィックスを抽出し、小文字化してスラッグ候補とする
2. `.claude/indie/{slug}/knowledge/` の存在を確認する
3. ブランチから特定できない場合:
   - `.claude/indie/*/knowledge/` を Glob で全プロジェクト検索
   - 単一なら確定。複数なら **AskUserQuestion** で「どのプロジェクトを lint しますか？」と選択させる
4. 引数でスラッグ指定があればそれを優先する

---

## Phase 1: グラフ構築

1. `.claude/indie/{slug}/knowledge/**/*.md` を Glob で列挙（`index.md` を除く）
   - basename（拡張子なし）→ 相対パス のマップを作る。`concepts/` 配下は `kind: concept`、直下は `kind: source`（frontmatter の `kind` 明示があればそれを優先）
2. 各ファイルを Read し、本文中の `[[name]]` を全て抽出してリンク集合を作る
3. `knowledge/index.md` を Read し、登録済みファイル一覧を取得する（存在しなければ「未整備」として記録）
4. 各 Issue ファイル（`.claude/indie/{slug}/issues/*.md`）の `[[name]]` 参照も補助的に収集する（orphan 判定の参照元に含める）

`${CLAUDE_EFFORT}` が `low` / `medium` のときは決定的チェック（項目 1〜4）を優先し、表記ゆれ・重複概念（項目 5〜6, LLM 判定）は件数が多い場合に上位のみ提示する。`xhigh` / `max` のときは全ファイルを対象に表記ゆれ・重複概念まで網羅的に判定する。

---

## Phase 2: 検出項目

決定的チェック（機械判定）を上に、文脈判断（LLM 判定）を下に置く。

| # | 種別 | 判定 | 重大度 | 修正 |
|---|------|------|--------|------|
| 1 | **broken wikilink** | 本文の `[[name]]` に一致する knowledge ファイルが存在しない | 🔴 high | 候補が編集距離で 1 つに絞れる場合のみ張替を提案（承認制） |
| 2 | **stale index entry** | index.md に在るがファイル実体が無い | 🔴 high | index.md の該当行を削除（機械修正） |
| 3 | **unregistered file** | ファイル実体が在るが index.md に無い | 🟡 medium | index.md に行を追加（機械修正、概要は見出し直後の1文） |
| 4 | **orphan concept** | `kind: concept` だが「関連ソース」の `[[ ]]` が 0 個（統合元が無い） | 🟡 medium | 提案のみ（統合元の追記をユーザーに促す） |
| 5 | **isolated source** | どの concept からも `[[ ]]` 参照されない source（統合候補のヒント） | 🔵 low | 提案のみ（概念ページへの統合を促す） |
| 6 | **tags 表記ゆれ** | 意味が同じで表記が異なる tag（`rl`↔`reinforcement-learning`、単複、大小、和英） | 🟡 medium | 提案のみ（正規化先を提示、適用はユーザー承認後 Edit） |
| 7 | **重複概念** | 概要・tags が酷似する複数ページ | 🟡 medium | 提案のみ（統合候補として提示） |

- broken wikilink の編集距離判定: basename の Levenshtein 距離が 2 以下、または大文字小文字・ハイフン/アンダースコア違いのみの候補を「張替候補」とする。候補が複数なら自動提案せず列挙のみ
- orphan / isolated は記事の "orphaned pages" に相当。これらは「まだ繋がっていない知見」のシグナルであり、エラーではなく統合の機会として提示する

---

## Phase 3: レポートと承認制修正

1. 検出結果を重大度順（🔴→🟡→🔵）にまとめて提示する:

   ```
   ## Knowledge Lint 結果（{slug}）

   🔴 broken wikilink: 2件
     - concepts/data-fetching.md → [[api-pattern]]（候補: api-patterns）
     - foo.md → [[bar]]（候補なし）
   🔴 stale index entry: 1件
     - index.md: removed-topic.md（実体なし）
   🟡 unregistered file: 1件
     - cache-strategy.md（index 未登録）
   🟡 tags 表記ゆれ: 1組
     - "rl" / "reinforcement-learning" → 正規化先: reinforcement-learning
   🔵 isolated source: 3件（概念ページへの統合候補）

   機械的に修正可能: stale index 1 / unregistered 1 / broken link 張替 1
   ```

2. 機械修正が 1 件以上ある場合、**AskUserQuestion** で適用方針を確認する:
   - question: "機械的に修正可能な項目を適用しますか？"
   - header: "Lint 修正"
   - options:
     1. label: "自動修正" / description: "index 同期・確定的な broken link 張替を一括適用"
     2. label: "個別選択" / description: "項目ごとに適用するか確認"
     3. label: "提案のみ" / description: "修正は適用せず検出結果だけ残す"

3. 承認された機械修正を Edit で適用する:
   - **index.md 同期**: stale 行の削除 / unregistered 行の追加。概要はファイルの最初の見出し直後の1文を 30 文字以内に要約
   - **broken link 張替**: 候補が 1 つに確定している `[[ ]]` のみ置換
4. LLM 判定項目（orphan / isolated / 表記ゆれ / 重複概念）は提案として残し、自動では変更しない。表記ゆれの正規化や概念ページへの統合は、ユーザーが望めば続けて対応する（`/indie-issue-maintain` の concept 生成・波及更新フローに接続）

---

## 処理フロー

```
1. Phase 0: プロジェクト特定
2. Phase 1: knowledge を列挙し wikilink グラフと index 状態を構築
3. Phase 2: 7 項目を検出（決定的 → LLM の順、effort で深さ調整）
4. Phase 3: 重大度順にレポート
5. 機械修正があれば AskUserQuestion で適用方針を確認
6. 承認に従い index 同期・broken link 張替を Edit で適用
7. LLM 判定項目は提案として提示（自動修正しない）
```

---

## 注意事項

- **決定的に直せるものだけ自動修正する**。意味の統合（重複概念のマージ、表記ゆれの正規化）は人の判断を挟む
- 検出 0 件の場合は「knowledge グラフは健全です」と報告する
- knowledge が 0 件の場合は「まだ knowledge がありません」と案内して終了する
- index.md が無い場合は項目 2・3 をスキップし、index 新規作成を提案する
