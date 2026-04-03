---
name: issue-maintain
description: >
  Issue ファイルのセッション内容反映・品質整理・knowledge 切り出し・completed 管理を行う。
  トリガー: 「/issue-maintain」「Issue整理」「Issueファイルのメンテナンス」「セッション終了前にIssue更新」「Issueファイル更新して」「Issue更新」
  注意: このスキルはローカルの Issue ファイル（.claude/linear/*/issues/*.md）のみを更新する。Linear API の Issue は更新しない。
  引数: [Issue ID（省略時は現在のブランチから抽出、またはissues/配下の全ファイル対象）]
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
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

knowledge の status フロントマターや切り出し時の照合ルール、tags 付与ルールの詳細は quality-checklist.md を参照。

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

1. フロントマターの `status` を `completed` に更新
2. 別 Issue に引き継ぐ残タスクがあれば、フロントマターに `follow_up` を追加
   ```yaml
   follow_up:
     - TEAM-500           # Issue 起票済み
     - "xxx のバグ（未起票）"  # まだ Issue になっていない
   ```
3. 更新履歴に完了を記録
4. 汎用知見があれば `.claude/linear/{slug}/knowledge/` に切り出し
5. follow-up ファイルの棚卸し:
   - `.claude/linear/{slug}/follow-ups/*.md` を Glob で確認
   - `status: open` のファイルがあれば件数を通知:
     「open な follow-up が {N}件あります。`/follow-up list` で確認できます」
   - frontmatter の `follow_up` リストに未起票の文字列がある場合:
     「以下の未起票 follow-up を follow-up ファイルとして記録しますか？」と提案

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

## 処理フロー

```
1. 対象 issue ファイルを読み込み
2. テンプレート準拠チェック（セクション構成の確認）
3. 各セクションを走査し、整理対象を特定
4. 更新履歴のセッション単位統合を確認
5. knowledge/ 切り出し候補を特定（tags の語彙を既存 index.md と照合）
6. タスク完了時フローの適用判定（全タスク完了 → status 更新、follow_up 確認）
7. 整理計画をユーザーに提示:
   - 削除するもの
   - 圧縮するもの
   - 統合する更新履歴
   - knowledge/ 切り出し候補（照合結果を含む）
   - テンプレート不足セクションの追加
   - completed ファイルの削除候補
8. 承認を得てから実行
9. knowledge/ 切り出しがあった場合、knowledge/index.md を更新
10. 更新履歴にメンテナンス内容を記録
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
