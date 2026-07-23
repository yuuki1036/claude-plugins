---
name: knowledge-lint
description: >
  プロジェクトの knowledge の健全性を点検・修復する（lint）。検索・参照ではなくグラフの保守が目的。
  broken wikilink・孤立 / 重複ページ・index 不整合・tags 表記ゆれ・doc 鮮度（stale）・glossary 用語重複を検出し、機械的に直せるものは承認制で修正する。
  トリガー: 「knowledge lint」「ナレッジ点検」「リンク切れチェック」「リンク切れ」「孤立した知見」「knowledge の健全性」「knowledge を整理」「knowledge の鮮度」「stale な知見」「/knowledge-lint」
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

## Phase 0: backend 検出（全スキル共通）

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。

## Phase 0.5: プロジェクト特定

1. `git branch --show-current` でブランチ名から Issue ID プレフィックスを抽出し、小文字化してスラッグ候補とする
2. `{DATA_DIR}/{slug}/knowledge/` の存在を確認する
3. ブランチから特定できない場合:
   - `{DATA_DIR}/*/knowledge/` を Glob で全プロジェクト検索
   - 単一なら確定。複数なら **AskUserQuestion** で「どのプロジェクトを lint しますか？」と選択させる
4. 引数でスラッグ指定があればそれを優先する

---

## Phase 1: グラフ構築

1. `{DATA_DIR}/{slug}/knowledge/**/*.md` を Glob で列挙（`index.md` を除く）
   - basename（拡張子なし）→ 相対パス のマップを作る。`concepts/` 配下は `kind: concept`、直下は `kind: source`（frontmatter の `kind` 明示があればそれを優先）
2. 各ファイルを Read し、本文中の `[[name]]` を全て抽出してリンク集合を作る。あわせて frontmatter から `last-validated` / `phase` / `updated` / `verified` / `status` / `kind` / `subkind` を読み取り、項目 8（鮮度）・項目 9（glossary）の判定用に保持する
3. `knowledge/index.md` を Read し、登録済みファイル一覧を取得する（存在しなければ「未整備」として記録）
4. 各 Issue ファイル（`{DATA_DIR}/{slug}/issues/*.md`）の `[[name]]` 参照も補助的に収集する（orphan 判定の参照元に含める）

`${CLAUDE_EFFORT}` が `low` / `medium` のときは決定的チェック（broken wikilink・index 整合・鮮度〔項目 8〕）を優先し、LLM 判定（表記ゆれ・重複概念・glossary 用語重複〔項目 9〕）は件数が多い場合に上位のみ提示する。`xhigh` / `max` のときは全ファイルを対象に LLM 判定まで網羅的に行う。項目 8（stale knowledge）は決定的なので effort によらず常時実行する。

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
| 8 | **stale knowledge** | 有効鮮度日が phase 別閾値（current 90日 / target 180日）を超過。superseded は対象外 | 🟡 warn（last-validated 基準）/ 🔵 info（fallback・欠落） | 提案のみ（再検証 + `last-validated` 記入を促す。error にしない） |
| 9 | **glossary 用語重複** | `kind: concept` + `subkind: glossary` ページ間で同一用語が複数定義（用語 SSoT 単一性違反） | 🟡 medium | 提案のみ（統合先を提示） |

- broken wikilink の編集距離判定: basename の Levenshtein 距離が 2 以下、または大文字小文字・ハイフン/アンダースコア違いのみの候補を「張替候補」とする。候補が複数なら自動提案せず列挙のみ
- orphan / isolated は記事の "orphaned pages" に相当。これらは「まだ繋がっていない知見」のシグナルであり、エラーではなく統合の機会として提示する
- **項目 8（鮮度判定）**: `last-validated` / `phase` は任意フィールド。未記入でも error にせず warn / info に留める（transitional period）。判定は次の決定的 fallback chain で行う:
  - 有効鮮度日: `last-validated` → 無ければ `updated` → 無ければ `verified` → いずれも無ければ判定スキップ + 記入を促す info。fallback を使った場合はレポートに `(updated fallback)` 等を明記
  - 有効 phase: `phase` → 無ければ `status` から推定（`verified`→current / `planned`→target、`(status→phase 推定)` と明記）→ 両方無ければ current 扱い（安全側）+ info
  - 閾値（knowledge 専用デフォルト固定。current=90日≒四半期 / target=180日≒半期。superseded は対象外）。`last-validated` の形式が `YYYY-MM-DD` でない / `phase` が enum 外なら warn（修正を促す）
  - 経過日数: `date -j -f "%Y-%m-%d" "$d" "+%s" 2>/dev/null || date -d "$d" "+%s"` で macOS/Linux 両対応に算出し、`(now - ts) / 86400` で日数化
- **項目 9（glossary 用語重複）**: `kind: concept` かつ `subkind: glossary` のページが対象（0 件ならスキップ）。用語エントリは ①テーブル記法（各行の第 1 セルを正規用語とみなす。ヘッダ行・区切り行・`用語`/`名前` 等のヘッダ語は除外）②見出し記法（`### {用語}`）の 2 記法から抽出。正規化キー（trim + 小文字化）が 2 ページ以上または同一ページ内 2 回以上に出現したら SSoT 単一性違反として提示。別名禁止リスト掲載語が他ページで正規定義されていれば「別名衝突」として 🔵 low で併記。項目 6（tags フィールドの表記ゆれ）・項目 7（ページ粒度の類似）とは対象フィールド・粒度が異なり衝突しない

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
   🟡 stale knowledge: 2件
     - concepts/auth-model.md（current, 124日 > 90日。再検証を推奨）
     - cache-strategy.md（target, updated fallback で 190日 > 180日。last-validated 記入を推奨）→ info
   🟡 glossary 用語重複: 1組
     - "テナント" が concepts/glossary.md と concepts/domain-terms.md の両方で定義（SSoT は 1 ページに統合）
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
4. LLM 判定項目（orphan / isolated / 表記ゆれ / 重複概念）は提案として残し、自動では変更しない。表記ゆれの正規化や概念ページへの統合は、ユーザーが望めば続けて対応する（`/issue-maintain` の concept 生成・波及更新フローに接続）

---

## 処理フロー

```
1. Phase 0: backend 検出 → Phase 0.5: プロジェクト特定
2. Phase 1: knowledge を列挙し wikilink グラフ・index 状態・frontmatter（鮮度 / glossary 判定用）を構築
3. Phase 2: 9 項目を検出（決定的 → LLM の順、effort で深さ調整）
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
- 項目 8・9 は提案のみで、機械修正（index 同期・broken link 張替）の対象に含めない

**doc-freshness との住み分け**: knowledge-lint は鮮度の最小コア（`last-validated` / `phase` 検証 + stale 判定〔項目 8〕）のみ担当する。行数ガード・Markdown 相対リンク `[](path)` の実在検証・superseded 参照追跡は doc-freshness プラグインに委譲する。knowledge の wikilink `[[name]]` 切れ・孤立・glossary 用語重複は従来どおり knowledge-lint の責務。閾値の外部設定（`knowledge-lint.json`）は段階Aでは持たず、デフォルト固定とする。
