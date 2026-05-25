---
name: indie-issue-maintain
description: >
  Issue ファイルのセッション内容反映・品質整理・knowledge 切り出しを行う。
  スコープ超過警告も実施。
  トリガー: 「Issue整理」「Issue更新」「セッション終了前にIssue更新」「/indie-issue-maintain」
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

`.claude/indie/*/issues/` 内の issue ファイルを整理する。
目的は **次のセッションが素早くコンテキストを把握できる状態** にすること。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/indie-issue-maintain` | 現在のブランチに紐づく issue ファイルを整理 |
| `/indie-issue-maintain ISSUE-123` | 指定した issue ファイルを整理 |
| `/indie-issue-maintain --all` | 全 issue ファイルを整理（in-progress + completed の削除判定） |

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

## last_active の更新

整理実行時にフロントマターの `last_active` を今日の日付に更新する。

```yaml
---
last_active: 2026-03-20
---
```

---

## スコープ超過チェック

フロントマターの `scope_size` と実際のタスク数（進捗セクション内のチェックリスト項目 `[ ]` と `[x]` の合計）を比較し、閾値を超過している場合は警告する。**このチェックは整理計画の冒頭で最優先に表示する**（見落とし防止）。

| scope_size | 想定上限 | 警告発火閾値 | 警告内容 |
|------------|---------|-------------|---------|
| small | 3 | 5 以上 | スコープ膨張（medium 相当）|
| medium | 7 | 8 以上 | スコープ膨張（large 相当）|
| large | 15 | 16 以上 | 分割を推奨 |

**警告フォーマット:**
```
⚠️ {ISSUE-ID} はスコープ膨張を検知
  - 宣言: {size}（想定 {limit} 個以下）
  - 実タスク数: {actual} 個
  - 提案:
    (A) scope_size を {推奨サイズ} に更新する
    (B) タスクを別 Issue に分割する（スコープ外に切り出し）
```

- `small: 5+` → 推奨サイズは `medium`
- `medium: 8+` → 推奨サイズは `large`
- `large: 16+` → 推奨サイズは無し（分割推奨のみ）
- 警告はユーザーに **AskUserQuestion** で対処を確認する:
  - header: "スコープ"
  - options: 「scope_size を更新」「タスクを分割」「現状維持」
- `scope_size` が未設定の場合はチェックをスキップし、設定を促す注意書きのみ表示する

---

## テンプレート準拠チェック

Issue ファイルがフロントマターの `type` に対応するテンプレートに準拠しているか確認する：

| type | 必須セクション |
|------|---------------|
| bugfix | 概要, 進捗, 変更ファイル, 更新履歴 |
| feature | 概要, 計画, 進捗, 変更ファイル, 更新履歴 |
| investigation | 概要, 調査結果, 根本原因, 提案, 関連ファイル, 更新履歴 |
| debt | 概要, 影響範囲, 放置リスク, 対応方針, 進捗, 変更ファイル, 更新履歴 |

**feature の推奨セクション**（省略可、必要に応じて追加）:
- 調査結果、スコープ外、備考

- 不足セクションがあれば追加を提案
- 空のままのセクションは「（なし）」と記載して残す（テンプレート構造を維持）

品質チェックの詳細は以下を参照:
→ Read `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`

---

## knowledge/ への切り出し

整理中に汎用性のある知見を発見した場合、knowledge/ への切り出しまで実行する：

1. **候補の特定**: 特定の Issue に閉じない、再利用可能な知見を特定
   - アーキテクチャの分析結果
   - パフォーマンス調査の発見
   - ライブラリ・フレームワーク固有のノウハウ
   - ドメインロジックの仕様整理
2. **正確性の確認**: コードベースや関連 Issue と照合して内容が正しいか検証
3. **tags の付与**: 既存 knowledge の tags を確認（`knowledge/index.md` または Grep）し、語彙を揃えた上で 3〜7個の tags を決定
4. **切り出し実行**: `knowledge/{topic}.md` に格納し、元の Issue からはリンクで参照。フロントマターに `status`, `tags` を付与
5. **ユーザー承認**: 切り出し内容と格納先をユーザーに提示し、承認を得る
6. **index.md の更新**: 切り出し後、`knowledge/index.md` を更新する（後述）

knowledge の status フロントマターや切り出し時の照合ルール、tags 付与ルール、概念ページ（concept）と wikilink の仕様の詳細は quality-checklist.md を参照。

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
6. concept（`knowledge/concepts/*.md`）はファイル列をパス付き（`concepts/{slug}.md`）で記載する

---

## 概念ページへの波及（concept 統合）

source（個別知見）を切り出した後、複数の source を横断する知見が見えてきたら **概念ページ（concept）** に統合する。これが knowledge の価値の本体になる（個別知見の寄せ集めではなく、繋いで初めて見える構造を残す）。kind / wikilink の定義は `knowledge` スキルの SKILL.md を参照。

### 波及の判断

切り出した／更新した source の tags・トピックを既存 knowledge と照合し、次を判定する:

1. **既存 concept に該当あり**（`knowledge/concepts/*.md` に関連する概念ページがある）:
   - その concept の「関連ソース」に `[[新しい source]]` を追加する
   - 「横断的知見」を読み返し、新しい source で補強・修正できる点があれば追記する（矛盾を見つけたら明記する）
2. **新規 concept の候補**（同じテーマを扱う source が 2 件以上あり、まだ概念ページが無い）:
   - 新規 concept ページの作成を提案する（下記テンプレート）
3. **該当なし**（単発の知見）:
   - source のままにする（無理に concept 化しない）

### concept ページのテンプレート

`knowledge/concepts/{concept-slug}.md` に作成する:

```markdown
---
kind: concept
source: {統合元 Issue ID（複数可）}
status: verified | planned
verified: YYYY-MM-DD
tags: [...]
---

# {概念名}

## 概要
{この概念が何か。1〜2 文}

## 横断的知見
{複数 source を跨いで見えてくる構造・共通パターン・矛盾。concept の核}

## 未解決の問い
{この概念について残っている疑問・検証したい点}

## 関連ソース
- [[source-a]] — {このソースから得た観点}
- [[source-b]] — {このソースから得た観点}
```

- 「横断的知見」が薄い（単一 source の要約に留まる）なら concept にせず source のままにする
- 関連ソースは `[[name]]`（拡張子なし basename）で参照する
- concept も index.md に登録する（ファイル列は `concepts/{slug}.md`）
- frontmatter は source と同じく `kind` / `source` / `status` / `verified`（verified 時のみ）/ `tags`。`kind: concept` を足すのが source との差分

### 承認

concept の作成・更新も他の整理と同様、内容をユーザーに提示し承認を得てから実行する。

---

## 即クローズパターンの検出

Issue 起票後、実装せずに即クローズされた Issue を検出し、経緯が残せているか確認する。

**検出条件**（全て満たす場合）:
1. `status: completed`
2. `created == last_active`（同日作成・同日完了）
3. 進捗セクションの `[x]` タスクが 0 件

**検出時の処理**:
1. 本文に「結論」「スコープ外」「備考」セクションが揃っているか確認
2. 不足セクションがあれば、`references/feature.md` の「即クローズケースの書き方」の構造での補完をユーザーに提案
3. キャンセル理由が `projects doc` の備考に記録されているか確認（無ければ記録を促す）

即クローズは `canceled` ではなく `completed` のまま残す運用（なぜクローズしたかの経緯を残すため）。

---

## タスク完了時のフロー

Issue のタスクが全て完了した場合、以下を実行する：

1. **レビュー実施状況の確認（レビューガード）** — 詳細は次節「レビューガード」参照。未実施が疑われる場合は `/self-review` 起動を提案する
2. フロントマターの `status` を `completed` に更新
3. 別 Issue に引き継ぐ残タスクがあれば、フロントマターに `follow_up` を追加
   ```yaml
   follow_up:
     - ISSUE-500           # Issue 起票済み
     - "xxx のバグ（未起票）"  # まだ Issue になっていない
   ```
4. 更新履歴に完了を記録
5. 汎用知見があれば `.claude/indie/{slug}/knowledge/` に切り出し
6. follow-up ファイルの棚卸し:
   - `.claude/indie/{slug}/follow-ups/*.md` を Glob で確認
   - `status: open` のファイルがあれば件数を通知:
     「open な follow-up が {N}件あります。`/indie-follow-up list` で確認できます」
   - frontmatter の `follow_up` リストに未起票の文字列がある場合:
     「以下の未起票 follow-up を follow-up ファイルとして記録しますか？」と提案

---

## レビューガード（完了マーク前の品質確認）

`/indie-issue-maintain` で Issue を `completed` に遷移させる前、または完了サブタスクが 3 件以上ある時に、コードレビューが実施されたかを確認する。feature-dev 経由を通らず `/indie-issue-maintain` だけで完了マークするケースで、レビュー素通りを防ぐ品質ガード。

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

## スコープ外差分検出（follow-up 自動提示）

Issue ファイルの「スコープ外」「後続 Issue 候補」「やらないこと」セクションへの**前回コミット以降の追加行**を検出し、`/indie-follow-up new` 候補として一括提示する。

### 検出ロジック

1. `git log -1 --format=%H -- {issue-file-path}` で直近コミットの hash を取得（Bash）
   - 未コミットファイル（新規 Issue）の場合は本ステップをスキップ
2. `git diff {hash}..HEAD -- {issue-file-path}` で前回コミット以降の差分を取得（Bash）
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

- question: "上記の follow-up 候補を `/indie-follow-up new` で記録しますか？"
- header: "Follow-up 候補"
- options:
  1. label: "一括記録" / description: "全件を follow-up ファイルとして記録"
  2. label: "個別選択" / description: "1 件ずつ記録するか確認"
  3. label: "スキップ" / description: "follow-up 化せず Issue ファイルにのみ残す"

「一括記録」「個別選択」を選んだ場合は、対応する follow-up ファイルを生成する（indie-follow-up スキルの Phase N5 と同じ手順）。

### 注意事項

- 既存の follow-up 検知（会話中シグナル）とは独立。Issue ファイル更新タイミングでの差分検出という別軸
- 検出対象セクションが Issue ファイルに無い場合はスキップ
- 未コミットの新規 Issue ファイルの場合もスキップ

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

---

## 処理フロー

```
1. 対象 issue ファイルを読み込み
2. last_active を今日の日付に更新
3. スコープ超過チェック（scope_size vs 実タスク数）
4. テンプレート準拠チェック（セクション構成の確認）
5. 即クローズパターン検出（completed && created == last_active && [x]タスク 0 件）
6. 各セクションを走査し、整理対象を特定
7. 更新履歴のセッション単位統合を確認
8. knowledge/ 切り出し候補を特定（tags の語彙を既存 index.md と照合）
9. 概念ページ波及の判定（切り出し候補・更新 source の tags を既存 concept / source と照合し、新規 concept 作成 or 既存 concept への `[[ ]]` 追加を判断）
10. スコープ外差分検出（git diff で「スコープ外」「後続 Issue 候補」セクションの追加行を抽出）
11. タスク完了時フローの適用判定:
    - レビュー実施状況を確認（レビューガード節を参照）
    - 全タスク完了 → status 更新、follow_up 確認
12. 整理計画をユーザーに提示:
    - スコープ超過警告（該当する場合）
    - 即クローズパターン時の経緯セクション補完提案（該当する場合）
    - 削除するもの
    - 圧縮するもの
    - 統合する更新履歴
    - knowledge/ 切り出し候補（照合結果を含む）
    - 概念ページ（concept）への波及候補（新規作成 / 既存 concept への `[[ ]]` 追加）
    - スコープ外差分から検出した follow-up 候補
    - レビュー未実施の警告（該当する場合）
    - テンプレート不足セクションの追加
    - completed ファイルの削除候補
13. 承認を得てから実行
14. knowledge/ 切り出し・concept 波及があった場合、knowledge/index.md を更新（concept はパス付きで登録）
15. 更新履歴にメンテナンス内容を記録
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
