---
name: feedback-issue
description: >
  プラグインへの改善要望・バグ報告・使いにくさを GitHub Issue として起票する。
  会話中にプラグインへの不満や要望が出てきたら、Issue 作成を提案する。
  トリガー: 「プラグインの改善」「プラグインに要望」「フィードバック」「バグ報告」
  「プラグインがこうだったらいいのに」「プラグインが使いにくい」「プラグインに機能追加してほしい」
  「このプラグインもっとこうなってほしい」「Issue投げたい」
effort: low
allowed-tools:
  - Bash
  - AskUserQuestion
---

# Feedback Issue

プラグインへの改善要望・バグ報告を検知し、GitHub Issue として起票するスキル。

## いつ使うか

- ユーザーが明示的にフィードバックしたいと言った時
- 会話中にプラグインへの不満・改善要望・バグが言及された時
- ユーザーが「こういう機能があればいいのに」とプラグインについて言及した時

## 重要: 誤検知の回避

以下は対象外。プラグインではなく作業対象への言及:

- 「このコードが使いにくい」→ 作業対象の話（対象外）
- 「このプラグインが使いにくい」→ プラグインの話（対象）
- 「バグがある」→ 作業対象の話（対象外）
- 「プラグインにバグがある」→ プラグインの話（対象）

**「プラグイン」「スキル」「コマンド」「hook」への言及があるかを判断基準にする。**

## ワークフロー

### Step 1: 提案

プラグインへのフィードバックを検知したら:

```
プラグインへの改善要望のようですね。
GitHub Issue として起票しますか？
```

ユーザーが承諾しなければ何もしない。

### Step 2: 情報の整理

1. 対象プラグインを特定する（会話コンテキストから推定 or ユーザーに確認）
2. 種別を判定する。会話文脈で自明ならそれを使い、曖昧なら **AskUserQuestion** で確認する:
   - question: "このフィードバックの種別はどれですか？"
   - header: "Issue 種別"
   - options:
     1. label: "enhancement" / description: "改善要望・機能追加（label: enhancement）"
     2. label: "bug" / description: "不具合・期待通り動かない（label: bug）"
     3. label: "question" / description: "質問・使い方の不明点（label: question）"
3. 会話コンテキストから要望内容を要約する
4. 不足情報があればヒアリングする
5. ユーザーがスクリーンショット・録画のファイルを示していれば添付候補にする（`png` / `jpg` / `jpeg` / `gif` / `webp` / `svg` / `mp4` / `mov` / `webm`、50 件まで）。自分から撮影を求めない

### Step 3: 認証チェック

`gh auth status` で確認。未認証なら案内して中止。

### Step 4: プレビューと承認

Issue の内容（添付候補があればファイル名も）をプレビュー表示し、ユーザー承認を得る。

### Step 5: Issue 作成

本文は `references/issue-template.md`（正本）の種別別テンプレートに従って組み立てる。

```bash
gh issue create \
  --repo yuuki1036/claude-plugins \
  --title "[{plugin-name}] {title}" \
  --label "{label}" \
  --body "{body}" \
  --attach "{file}"   # 添付する場合のみ。1 ファイル 1 フラグ
```

- ラベルが存在しない場合は `--label` を省略する
- `--repo yuuki1036/claude-plugins` は意図的な固定値（フィードバック先はユーザーの CWD に関係なく常にマーケットプレイス本体リポジトリ）
- 添付候補がある場合、`--attach` を付けるのは次の両方を満たすときだけ。満たさなければ `--attach` 無しで作成し、報告時に「Issue ページを開いて画像をドラッグ&ドロップで追加して」と案内する:

  ```bash
  # --attach は gh 2.99.0 以降
  gh issue create --help 2>/dev/null | grep -q -- '--attach'
  # アップロードには WRITE 以上が要る。コラボレーター以外は READ なので添付できない
  gh repo view yuuki1036/claude-plugins --json viewerPermission -q .viewerPermission   # WRITE / MAINTAIN / ADMIN
  ```

- `--attach` 付きで exit 非ゼロになっても、途中までのアップロード分で Issue が作成され URL が出力されていることがある。**再実行する前に出力に Issue URL が無いか確認する**（二重起票を防ぐ）

### Step 6: 報告

作成された Issue URL を報告し、元の作業に戻る。
