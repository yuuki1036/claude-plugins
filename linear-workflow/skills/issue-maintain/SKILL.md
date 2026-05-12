---
name: issue-maintain
description: >
  Issue ファイルのセッション内容反映・品質整理・knowledge 切り出し・completed 管理。
  ローカル Issue ファイルのみ更新（Linear API は更新しない）。
  トリガー: 「/issue-maintain」「Issue整理」「Issue更新」「セッション終了前にIssue更新」
  引数: [Issue ID（省略時はブランチから抽出）]
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - AskUserQuestion
---

# Issue メンテナンス

## 概要

`.claude/linear/*/issues/` 内の issue ファイルを整理する。
目的は **次のセッションが素早くコンテキストを把握できる状態** にすること。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/issue-maintain` | 現在のブランチに紐づく issue ファイルを整理 |
| `/issue-maintain TEAM-123` | 指定した issue ファイルを整理 |
| `/issue-maintain --all` | 全 issue ファイルを整理（in-progress + completed の削除判定） |

---

## 整理対象

### 削除してよいもの

| 対象 | 判断基準 | 例 |
|------|----------|-----|
| 完了済みサブタスクの詳細 | チェック済み `[x]` で、実装内容が変更ファイルに反映済み | 調査手順の詳細ステップ |
| 不採用になったアプローチ | 別の方法を採用した検討メモ | 「案A: xxx → 不採用（理由: yyy）」 |
| 解決済みの問題・疑問 | 結論が出て実装に反映済み | 「Q: xxxは必要？ → 不要と判明」 |
| 重複した記載 | 同じ内容が複数セクションにある | 概要と調査結果で同じ説明 |
| 一時的なデバッグメモ | ログ出力やテスト結果の生データ | 「console.log の結果: ...」 |

### 残すもの

| 対象 | 理由 |
|------|------|
| 未完了タスク `[ ]` の詳細 | 次のセッションで作業に必要 |
| 採用した設計判断と理由 | 後から「なぜこうしたか」を追えるように |
| スコープ外の記載 | 意図的に除外した理由のトレーサビリティ |
| 変更ファイル一覧 | 実装の全体像把握に必要 |
| 備考（副次的な発見） | 将来の参考情報 |

### 圧縮するもの

完了済みサブタスクは詳細を削って1行サマリーにする：

**Before:**
```md
- [x] IntensitySearchInput コンポーネントの実装
  - props: modelValue, placeholder, disabled, ideaVersions
  - emit: update:modelValue, select
  - El-Autocomplete ベースで実装
  - fetchSuggestions で API 呼び出し
  - IDEA バージョンラベルをドロップダウン内に表示
  - テスト作成済み
```

**After:**
```md
- [x] IntensitySearchInput コンポーネント実装（PR #84）
```

### 更新履歴の統合

同日に複数エントリがある場合、セッション単位にまとめる：

**Before:**
```md
| 2026-03-03 | 実装完了 |
| 2026-03-03 | バグ修正: xxx |
| 2026-03-03 | リファクタ: yyy |
```

**After:**
```md
| 2026-03-03 | 実装完了。バグ修正（xxx）、リファクタ（yyy）を実施 |
```

---

## テンプレート準拠チェック

Issue ファイルがフロントマターの `type` に対応するテンプレートに準拠しているか確認する：

| type | 必須セクション |
|------|---------------|
| bugfix | 概要, 進捗, 変更ファイル, 更新履歴 |
| feature | 概要, 計画, 進捗, 変更ファイル, 更新履歴 |
| investigation | 概要, 調査結果, 根本原因, 提案, 関連ファイル, 更新履歴 |

**feature の推奨セクション**（省略可、必要に応じて追加）:
- 調査結果、スコープ外、備考

- 不足セクションがあれば追加を提案
- 空のままのセクションは「（なし）」と記載して残す（テンプレート構造を維持）

品質チェックの詳細は以下を参照:
→ Read `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`

---

## knowledge/ への切り出し

整理中に汎用性のある知見を発見した場合、knowledge/ への切り出しまで実行する：

1. **破壊的変更パターンの検出（最優先）**: Issue 本文・進捗・更新履歴から以下キーワードを Grep ベースで走査する：
   - 「破壊的変更 / breaking change」「rename された / renamed to」「deprecated / 非推奨」
   - バージョン跨ぎ表記（例: `v\d+ ?→ ?v\d+`）「dead element / 空振り / lint は通るが」
   - 「衝突する / conflict with / 配列順序」「実機テストで判明 / ランタイムで発覚」
   - 検出時は **必ず** y/n で切り出し提案する（通常の判断基準より優先）
   - 提案 tags は quality-checklist.md §5.1 の対応表から選び、ユーザーに提示
2. **候補の特定**: 特定の Issue に閉じない、再利用可能な知見を特定
   - アーキテクチャの分析結果
   - パフォーマンス調査の発見
   - ライブラリ・フレームワーク固有のノウハウ
   - ドメインロジックの仕様整理
3. **正確性の確認**: コードベースや関連 Issue と照合して内容が正しいか検証
4. **tags の付与**: 既存 knowledge の tags を確認（`knowledge/index.md` または Grep）し、語彙を揃えた上で 3〜7個の tags を決定
5. **切り出し実行**: `knowledge/{topic}.md` に格納し、元の Issue からはリンクで参照。フロントマターに `status`, `updated`（当日日付）, `tags` を付与
6. **ユーザー承認**: 切り出し内容と格納先をユーザーに提示し、承認を得る
7. **index.md の更新**: 切り出し後、`knowledge/index.md` を更新する（後述）

knowledge の status フロントマターや切り出し時の照合ルール、tags 付与ルール、破壊的変更パターン検出キーワード一覧の詳細は quality-checklist.md を参照。

**既存 knowledge 編集時の注意:** frontmatter の `updated` を当日の日付に書き換える（鮮度判定に使用される）。

---

## knowledge/index.md の管理

knowledge ファイルの切り出し・更新・削除を行った際は、`knowledge/index.md` を必ず同期する。

### フォーマット

```markdown
# Knowledge Index

| ファイル | tags | status | 概要 |
|---------|------|--------|------|
| api-patterns.md | api, rest, pagination | verified | REST API のページネーションパターン |
| cache-strategy.md | cache, redis, ttl | planned | キャッシュ戦略の設計案 |
```

### 更新ルール

1. knowledge ファイルの新規作成時: 行を追加
2. knowledge ファイルの更新時: 該当行の tags・status・概要を更新
3. knowledge ファイルの削除時: 該当行を削除
4. 概要はファイルの最初の見出し直後の1文を使用する（30文字以内に要約）
5. index.md 自体は knowledge ファイルとしてカウントしない

---

## タスク完了時のフロー

Issue のタスクが全て完了した場合、以下を実行する：

1. **レビュー実施状況の確認（レビューガード）** — 詳細は次節「レビューガード」参照。未実施が疑われる場合は `/self-review` 起動を提案する
2. フロントマターの `status` を `completed` に更新
3. 別 Issue に引き継ぐ残タスクがあれば、フロントマターに `follow_up` を追加
   ```yaml
   follow_up:
     - TEAM-500           # Issue 起票済み
     - "xxx のバグ（未起票）"  # まだ Issue になっていない
   ```
4. 更新履歴に完了を記録
5. 汎用知見があれば `.claude/linear/{slug}/knowledge/` に切り出し
6. follow-up ファイルの棚卸し:
   - `.claude/linear/{slug}/follow-ups/*.md` を Glob で確認
   - `status: open` のファイルがあれば件数を通知:
     「open な follow-up が {N}件あります。`/follow-up list` で確認できます」
   - frontmatter の `follow_up` リストに未起票の文字列がある場合:
     「以下の未起票 follow-up を follow-up ファイルとして記録しますか？」と提案

---

## レビューガード（完了マーク前の品質確認）

`/issue-maintain` で Issue を `completed` に遷移させる前、または完了サブタスクが 3 件以上ある時に、コードレビューが実施されたかを確認する。feature-dev 経由を通らず `/issue-maintain` だけで完了マークするケースで、レビュー素通りを防ぐ品質ガード。

### 検出ロジック

以下を満たすときに「レビュー未実施の疑い」と判定する:

1. **遷移条件**: 以下のいずれか
   - status が `in-progress` → `completed` に遷移する
   - 完了サブタスク `[x]` の合計が 3 件以上
2. **未実施シグナル**: Issue 本文（特に更新履歴・進捗）に以下のキーワードが**含まれていない**
   - `self-review` / `セルフレビュー` / `/self-review`
   - `code-review` / `/review` / `コードレビュー実施`
   - `code-reviewer` agent / `reviewer agent`
3. 例外: type が `investigation`（実装を伴わない調査 Issue）の場合はスキップ

### 提示フォーマット

AskUserQuestion で以下を提示する:

- question: "コードレビュー未実施の可能性があります。`/self-review` を起動しますか？"
- header: "レビュー実施"
- options:
  1. label: "`/self-review` を起動" / description: "セルフレビューを実行してから完了マーク"
  2. label: "レビュー済み" / description: "更新履歴に記録して完了マーク（説明文を入力）"
  3. label: "スキップ" / description: "レビューせずに完了マーク（推奨されません）"

「レビュー済み」選択時は更新履歴に `| YYYY-MM-DD | レビュー実施: {説明} |` を追記する。
「`/self-review` を起動」選択時は本スキルを中断し、ユーザーに `/self-review` 起動を促す。

### 注意事項

- 検出は機械的に行い、最終判断はユーザーに委ねる
- 完了済みサブタスクが 3 件未満かつ status 遷移がない場合は本ガードを発火させない
- レビュー実施キーワードを検出した時点でガードはスキップする

---

## completed ファイルのライフサイクル

completed / canceled の Issue ファイルは、メンテナンス完了後に**削除を提案**する。

### 削除の前提条件

1. テンプレート準拠チェックが完了していること
2. 圧縮（サブタスク詳細の1行化、デバッグメモ削除等）が完了していること
3. 汎用知見が knowledge/ に切り出し済みであること
4. projects doc の「関連 Issue」テーブルに以下が記録されていること:
   - Issue ID、担当者、ステータス（Done / Canceled）、PR リンク
5. canceled の場合、キャンセル理由が projects doc の備考に記録されていること

### 削除フロー

```
1. 上記前提条件を全て確認
2. 削除対象ファイルの一覧をユーザーに提示
3. 承認を得てから削除
```

### linear-maintain からの自動呼び出し

`/linear-maintain` 実行時に completed が検知された場合、本スキルの処理フローが自動実行される。
手動で `/issue-maintain` を実行した場合も同じルールが適用される。

---

## スコープ外差分検出（follow-up 自動提示）

Issue ファイルの「スコープ外」「後続 Issue 候補」「やらないこと」セクションへの**前回コミット以降の追加行**を検出し、`/follow-up new` 候補として一括提示する。

### 検出ロジック

1. `git log -1 --format=%H -- {issue-file-path}` で直近コミットの hash を取得（Bash）
   - 未コミットファイル（新規 Issue）の場合は本ステップをスキップ
2. `git diff {hash}..HEAD -- {issue-file-path}` で前回コミット以降の差分を取得（Bash）
   - 比較対象は作業ツリー（未コミット変更を含む）
3. 差分から以下条件のセクション内の追加行（`+` 始まり、`+++` を除く）を抽出:
   - 見出しが「スコープ外」「後続 Issue 候補」「やらないこと」を含むセクション
   - 抽出単位: 箇条書き行（`- ` で始まる行）
4. 抽出した行をユーザーへの提示用に整形

### 提示フォーマット

検出が 1 件以上の場合のみ、AskUserQuestion で提示:

```
スコープ外 / 後続 Issue 候補 から N 件の follow-up 候補を検出:
1. {1 件目の要約}
2. {2 件目の要約}
...
```

- question: "上記の follow-up 候補を `/follow-up new` で記録しますか？"
- header: "Follow-up 候補"
- options:
  1. label: "一括記録" / description: "全件を follow-up ファイルとして記録"
  2. label: "個別選択" / description: "1 件ずつ記録するか確認"
  3. label: "スキップ" / description: "follow-up 化せず Issue ファイルにのみ残す"

「一括記録」「個別選択」を選んだ場合は、対応する follow-up ファイルを生成する（follow-up スキルの Phase N5 と同じ手順）。

### 注意事項

- 既存の follow-up 検知（会話中シグナル）とは独立。Issue ファイル更新タイミングでの差分検出という別軸
- 同じ行を 2 回提示しないよう、検出後は対応行に `<!-- follow-up-checked -->` マーカーを付けてもよい（任意。記録または明示スキップ済みの行は次回スキップ対象）
- 検出対象セクションが Issue ファイルに無い場合はスキップ

---

## 処理フロー

```
1. 対象 issue ファイルを読み込み
2. テンプレート準拠チェック（セクション構成の確認）
3. 各セクションを走査し、整理対象を特定
4. 更新履歴のセッション単位統合を確認
5. 破壊的変更パターン検出（quality-checklist.md §5.1 のキーワードを Grep）
6. knowledge/ 切り出し候補を特定（5 の検出結果 + 通常基準。tags の語彙を既存 index.md と照合）
7. スコープ外差分検出（git diff で「スコープ外」「後続 Issue 候補」セクションの追加行を抽出）
8. タスク完了時フローの適用判定:
   - レビュー実施状況を確認（レビューガード節を参照）
   - 全タスク完了 → status 更新、follow_up 確認
9. 整理計画をユーザーに提示:
   - 削除するもの
   - 圧縮するもの
   - 統合する更新履歴
   - knowledge/ 切り出し候補（破壊的変更検出は 🔴 マーカー付きで先頭表示、tags 候補を併記）
   - スコープ外差分から検出した follow-up 候補
   - レビュー未実施の警告（該当する場合）
   - テンプレート不足セクションの追加
   - completed ファイルの削除候補
10. 承認を得てから実行（既存 knowledge を編集した場合は frontmatter `updated` を当日日付に更新）
11. knowledge/ 切り出しがあった場合、knowledge/index.md を更新
12. 更新履歴にメンテナンス内容を記録
```

## 更新履歴への記録形式

```md
| YYYY-MM-DD | メンテナンス: 完了済み詳細を圧縮、xxx を knowledge/ に切り出し |
```

---

## 注意事項

- **情報を減らすのではなく、ノイズを減らす**
- 判断に迷う場合は残す（過剰な削除よりは冗長な方がマシ）
- knowledge/ 切り出し時は必ずコードベースとの照合を行う
- 整理前に必ずユーザーに計画を提示し、承認を得る
