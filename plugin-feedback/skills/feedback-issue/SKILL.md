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
  - Read
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

### Step 3.5: 既存 Issue の確認

同じ要望・不具合が既に起票されていないかを、**open と closed の両方**で探す。要望の言葉だけでなく、同じ概念の別名でも探す:

```bash
gh issue list --repo yuuki1036/claude-plugins --state all --search "<キーワード> in:title,body" \
  --limit 10 --json number,title,state,url
```

- 見つからなければ、探した語を 1 行添えて Step 3.7 へ進む
- 同じものが見つかったら、番号・タイトル・状態を示し、**AskUserQuestion** で確認する:
  - question: "同じ内容の Issue が既にあります。どうしますか？"
  - header: "既存 Issue"
  - options:
    1. label: "既存 Issue にコメントする (Recommended)" / description: "open なら状況や再現例を足す。closed なら再発・未解決の報告として足す"
    2. label: "新しく起票する" / description: "別の観点・別の不具合として起票する"
    3. label: "やめる" / description: "起票しない"
  - コメントするときも Step 3.7 と Step 4 を通してから、Step 5 の手順で `gh issue comment` として投稿する

### Step 3.7: 本文の組み立てと匿名化（必須）

起票先は公開リポジトリで、投稿した本文は編集しても履歴とアーカイブに残る。

1. 本文を `references/issue-template.md`（正本）の種別別テンプレートで組み立てる（コメントならテンプレートは使わない）
2. `${CLAUDE_PLUGIN_ROOT}/skills/feedback-issue/references/anonymize.md` を Read し、その置き換え表をタイトル・本文（コメントならその全文）・添付ファイル名に当てる。完了基準も同ファイルに従う
3. cwd のリポジトリが公開かを調べる:

   ```bash
   gh repo view --json visibility -q .visibility 2>/dev/null || echo UNKNOWN
   ```

   `PUBLIC` 以外（`PRIVATE` / `INTERNAL` / `UNKNOWN`＝git 外・GitHub 外・取得失敗）は「公開でない」として扱う。業務リポジトリから起票するセッションは会話に業務の固有名が多く混ざるので、Step 4 の匿名化確認が必須になる

### Step 4: プレビューと承認

タイトルと本文の**全文**（要約しない）、ラベル、添付候補のファイル名、Step 3.7 で置き換えた種類と件数を示して承認を得る。

- cwd が公開でないときは、承認を **AskUserQuestion** で取る（チャットの「OK」で代えない）:
  - question: "公開 Issue に載る本文です。業務のリポジトリ名・PR 番号・Issue ID・ホスト名・社内のコード名やパスが残っていませんか？"
  - header: "匿名化の確認"
  - options:
    1. label: "残っていない。この内容で投稿する" / description: "表示した本文のまま投稿する"
    2. label: "直す箇所がある" / description: "チャットで直す箇所を伝える。直したら Step 4 をやり直す"
    3. label: "やめる" / description: "投稿しない"
  - 1 以外なら投稿しない
- 添付候補があれば、業務の画面が写っていないかを **AskUserQuestion** で確かめる。画像の中身は置き換えられず、送信前の検査も届かない:
  - question: "添付ファイルに、業務の画面・データ・社内 URL・ホスト名・人名が写っていませんか？"
  - header: "添付の確認"
  - options:
    1. label: "添付しない (Recommended)" / description: "Issue は本文だけで作る"
    2. label: "写っていない。添付する" / description: "自分で中身を確認した"
  - 2 を選んだときだけ Step 5 で `--attach` を付ける。ファイル名に置き換え対象の語があれば、一時ディレクトリへ汎用名（`screenshot-1.png` など）でコピーしてそちらを添付する

### Step 5: Issue 作成

1. 承認された本文を一時ファイルに書き、パスを表示する。**この呼び出しでは gh を実行しない**（送信前に本文を検査する hook は投稿コマンドの実行前にファイルを読むので、同じコマンドの中で書くと検査時にはまだ中身が無い）:

   ```bash
   BODY_FILE=$(mktemp "${TMPDIR:-/tmp}/plugin-feedback.XXXXXX") && cat > "$BODY_FILE" <<'PLUGIN_FEEDBACK_BODY_EOF'
   {承認された本文}
   PLUGIN_FEEDBACK_BODY_EOF
   echo "$BODY_FILE"
   ```

2. 別の Bash 呼び出しで、1 で表示された絶対パスを `--body-file` に渡す。`--body "{body}"` は使わない（本文のバッククォートや `$(...)` がシェルに展開され、検査もすり抜ける）:

   ```bash
   gh issue create \
     --repo yuuki1036/claude-plugins \
     --title "[{plugin-name}] {title}" \
     --label "{label}" \
     --body-file "{1 で表示されたパス}" \
     --attach "{file}"   # Step 4 で「添付する」を選んだときだけ。1 ファイル 1 フラグ
   ```

   既存 Issue へのコメントは `gh issue comment <番号> --repo yuuki1036/claude-plugins --body-file "{1 で表示されたパス}"`。

- タイトルに `"` `` ` `` `$` を入れない（`--title` はシェルの二重引用符の中に入る）。要るなら言い換える
- ラベルが存在しない場合は `--label` を省略する
- `--repo yuuki1036/claude-plugins` は意図的な固定値（フィードバック先はユーザーの CWD に関係なく常にマーケットプレイス本体リポジトリ）
- Step 4 で「添付する」が選ばれたら、次の両方を満たすときだけ `--attach` を付ける。満たさなければ `--attach` 無しで作成し、報告時に「Issue ページを開いて画像をドラッグ&ドロップで追加して」と案内する（「添付しない」が選ばれたときは案内しない）:

  ```bash
  # --attach は gh 2.99.0 以降
  gh issue create --help 2>/dev/null | grep -q -- '--attach'
  # アップロードには WRITE 以上が要る。コラボレーター以外は READ なので添付できない
  gh repo view yuuki1036/claude-plugins --json viewerPermission -q .viewerPermission   # WRITE / MAINTAIN / ADMIN
  ```

- `--attach` 付きで exit 非ゼロになっても、途中までのアップロード分で Issue が作成され URL が出力されていることがある。**再実行する前に出力に Issue URL が無いか確認する**（二重起票を防ぐ）
- 投稿に成功したら本文ファイルを消す（`rm -f "{1 で表示されたパス}"`）。失敗したときは再実行に使うので残す

### Step 6: 報告

作成された Issue URL を報告し、元の作業に戻る。
