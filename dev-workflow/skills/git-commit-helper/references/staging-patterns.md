# ステージングパターン詳細

## 同一ファイル内の hunk 分割ステージング

`git add -p` は対話的操作のため Claude Code では使用不可。
代わりに以下のパッチベース手法で同一ファイル内の変更を分割ステージングする。

### 手法: git diff + パッチ編集 + git apply --cached

```bash
# 1. 対象ファイルの diff を取得
git diff <file> > /tmp/full.patch

# 2. パッチファイルを編集し、ステージしたい hunk だけ残す
#    - 不要な hunk ブロック(@@ ... @@から次の@@ or ファイル末尾まで)を削除
#    - Read/Edit ツールで /tmp/full.patch を編集する

# 3. 編集したパッチをインデックスに適用
git apply --cached /tmp/full.patch

# 4. ステージ内容を確認
git diff --cached <file>
```

### パッチ編集のルール

- hunk ヘッダー (`@@ -a,b +c,d @@`) と対応する変更行をセットで残す/削除する
- 残す hunk: `+` 行（追加）と `-` 行（削除）をそのまま維持
- 削除する hunk: hunk ヘッダーごと丸ごと削除する（行番号の再計算は不要）
- コンテキスト行（` ` で始まる行）はそのまま維持する
- ファイルヘッダー (`diff --git`, `index`, `---`, `+++`) は必ず残す

### 注意事項

- hunk が隣接・重複している場合はパッチ適用が失敗する可能性がある。その場合は `git apply --cached --3way /tmp/full.patch` を試す
- パッチ適用失敗時は `git checkout -- <file>` でステージをリセットし、別の分割方法を検討する
- 分割が複雑すぎる場合は無理に分けず、ファイル単位のコミットに妥協する

## 分割判断の具体例

### 分割する
- 同一ファイル内でバグ修正 + 新機能追加 → 2コミット
- コンポーネントAのリファクタ + コンポーネントBの新規作成 → 2コミット
- import整理 + ロジック変更 → 2コミット

### 分割しない
- 1つの機能に必要な複数ファイルの変更 → 1コミット
- リネームに伴う全ファイルのimport修正 → 1コミット
- 1つのバグの原因と影響箇所の修正 → 1コミット

## subject 行（description）の品質規約

subject は **それ単体で「何を変えたか」が分かる完結した一文** にする（git log / version control history に単独で残るため、本文を読まなくても変更が追えること）。Google eng-practices "Writing good CL descriptions" 由来。

### 禁止例（情報量が不足する曖昧 subject）

| 禁止 subject | 何が問題か | 改善例 |
|---|---|---|
| `fix: バグ修正` / `fix: bug` | どのバグか不明 | `fix: ログイン時のトークン期限切れで500が返る不具合を修正` |
| `fix: build` | 何の build を何のために | `fix: TypeScript 5.4 の型エラーで CI build が落ちる問題を解消` |
| `chore: 対応` / `update` | 何をどうしたか皆無 | `chore: ESLint を v9 にアップグレード` |
| `refactor: いろいろ整理` | 範囲・意図が不明 | `refactor: 認証ロジックを auth-service に切り出し` |
| `docs: 修正` | どの doc の何か | `docs: README のセットアップ手順に hook 有効化を追記` |

### 原則

- 「この subject だけ見て、半年後の自分や他人が変更内容を理解できるか？」を自問する
- type と scope で機械的に分類できるからこそ、description は **具体的な対象と意図** を書く（`修正` / `対応` / `update` 単体で終わらせない）
- 詳細な背景・理由は body に書く（subject は要約に徹する）

## Conventional Commits Type一覧

| Type | 用途 |
|------|------|
| feat | 新機能 |
| fix | バグ修正 |
| docs | ドキュメント |
| style | フォーマット（機能影響なし） |
| refactor | リファクタリング |
| test | テスト |
| chore | ビルド・補助ツール |
| perf | パフォーマンス改善 |
| ci | CI設定 |
| build | ビルドシステム |
| revert | 取り消し |
