---
description: プラグインの改善要望・バグ報告を GitHub Issue として作成する
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

プラグインへの改善要望・バグ報告を GitHub Issue として起票してください。

## 引数

`$ARGUMENTS` にプラグイン名や要望内容が含まれていればそれを使う。

## ワークフロー

### Phase 1: 認証チェック

`gh auth status` で GitHub CLI の認証状態を確認する。
未認証なら `gh auth login` の実行を案内して中止する。

### Phase 2: 対象プラグインの特定

1. `$ARGUMENTS` にプラグイン名が含まれていればそれを使う
2. 未指定なら、プラグイン一覧を **動的取得** して選択を促す（一覧をハードコードしない。更新忘れを構造的に防ぐ）:

   ```bash
   # インストール済みプラグインから feedback マーケットプレイス（plugin-feedback が属する marketplace）のものを列挙
   MP_NAME=$(claude plugin list 2>/dev/null | grep -oE 'plugin-feedback@[^ )]+' | head -1 | cut -d'@' -f2)
   claude plugin list 2>/dev/null | grep -oE "[a-z0-9-]+@${MP_NAME}" | sort -u
   ```

   - `claude plugin list` が使えない環境では、feedback マーケットプレイスの `marketplace.json`（`~/.claude/plugins/marketplaces/*/.claude-plugin/marketplace.json` のうち `.name` が `MP_NAME` のもの）の `.plugins[].name` を参照する
   - どちらも取得できない場合のみ、ユーザーに対象プラグイン名を直接尋ねる

### Phase 3: 種別の特定

| label | 用途 |
|-------|------|
| enhancement | 機能追加・改善要望 |
| bug | バグ報告 |
| question | 質問・相談 |

- 会話コンテキストから自動判定できればそれを使う
- 判断に迷う場合はユーザーに確認する

### Phase 4: 内容のヒアリング

1. タイトルを決定する（簡潔に、50文字以内目安）
2. 詳細を決定する
3. 既にユーザーが説明している場合はそれを使い、重複して聞かない
4. 会話中に出てきた改善要望の場合、そのコンテキストを自動で要約する
5. ユーザーがスクリーンショット・録画のファイルを示していれば添付候補にする（`png` / `jpg` / `jpeg` / `gif` / `webp` / `svg` / `mp4` / `mov` / `webm`、50 件まで）。自分から撮影を求めない。添付の可否は Phase 5 の確認と Phase 6 の判定で決まる

### Phase 4.5: 本文の組み立てと匿名化（必須）

起票先は公開リポジトリで、投稿した本文は編集しても履歴とアーカイブに残る。

1. Issue 本文は `feedback-issue` スキルの `references/issue-template.md`（正本）の種別別テンプレート（enhancement / bug / question）に従って組み立てる。本文フォーマットをここに重複定義しない（乖離防止）
2. `${CLAUDE_PLUGIN_ROOT}/skills/feedback-issue/references/anonymize.md` を Read し、その置き換え表をタイトル・本文・添付ファイル名に当てる。完了基準も同ファイルに従う
3. cwd のリポジトリが公開かを調べる:

   ```bash
   gh repo view --json visibility -q .visibility 2>/dev/null || echo UNKNOWN
   ```

   `PUBLIC` 以外（`PRIVATE` / `INTERNAL` / `UNKNOWN`＝git 外・GitHub 外・取得失敗）は「公開でない」として扱う。業務リポジトリから起票するセッションは会話に業務の固有名が多く混ざるので、Phase 5 の匿名化確認が必須になる

### Phase 5: プレビューと承認

以下のヘッダを添えて Issue プレビューを提示し、ユーザーの承認を得る。本文は要約せず全文を出す:

```
## Issue プレビュー

**リポジトリ**: yuuki1036/claude-plugins
**タイトル**: [{plugin-name}] {title}
**ラベル**: {label}
**添付**: {添付候補のファイル名。無ければ行ごと省略}
**匿名化**: {置き換えた種類と件数。無ければ「なし」}

**本文**:
{Phase 4.5 で組み立て・匿名化した本文}
```

- cwd が公開でないときは、承認を **AskUserQuestion** で取る（チャットの「OK」で代えない）:
  - question: "公開 Issue に載る本文です。業務のリポジトリ名・PR 番号・Issue ID・ホスト名・社内のコード名やパスが残っていませんか？"
  - header: "匿名化の確認"
  - options:
    1. label: "残っていない。この内容で投稿する" / description: "表示した本文のまま投稿する"
    2. label: "直す箇所がある" / description: "チャットで直す箇所を伝える。直したら Phase 5 をやり直す"
    3. label: "やめる" / description: "投稿しない"
  - 1 以外なら投稿しない
- 添付候補があれば、業務の画面が写っていないかを **AskUserQuestion** で確かめる。画像の中身は置き換えられず、送信前の検査も届かない:
  - question: "添付ファイルに、業務の画面・データ・社内 URL・ホスト名・人名が写っていませんか？"
  - header: "添付の確認"
  - options:
    1. label: "添付しない (Recommended)" / description: "Issue は本文だけで作る"
    2. label: "写っていない。添付する" / description: "自分で中身を確認した"
  - 2 を選んだときだけ Phase 6 で `--attach` を付ける。ファイル名に置き換え対象の語があれば、一時ディレクトリへ汎用名（`screenshot-1.png` など）でコピーしてそちらを添付する

### Phase 6: Issue 作成

承認後、以下を実行:

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
     --attach "{file}"   # Phase 5 で「添付する」を選んだときだけ。1 ファイル 1 フラグ
   ```

- タイトルに `"` `` ` `` `$` を入れない（`--title` はシェルの二重引用符の中に入る）。要るなら言い換える
- ラベルが存在しない場合は `--label` を省略する
- `--repo yuuki1036/claude-plugins` は意図的な固定値（フィードバック先はユーザーの CWD に関係なく常にマーケットプレイス本体リポジトリ。marketplace.json には repo URL フィールドが無いため導出不可）
- 作成された Issue URL を報告する
- Phase 5 で「添付する」が選ばれたら、次の両方を満たすときだけ `--attach` を付ける。満たさなければ `--attach` 無しで作成し、報告時に「Issue ページを開いて画像をドラッグ&ドロップで追加して」と案内する（「添付しない」が選ばれたときは案内しない）:

  ```bash
  # --attach は gh 2.99.0 以降
  gh issue create --help 2>/dev/null | grep -q -- '--attach'
  # アップロードには WRITE 以上が要る。コラボレーター以外は READ なので添付できない
  gh repo view yuuki1036/claude-plugins --json viewerPermission -q .viewerPermission   # WRITE / MAINTAIN / ADMIN
  ```

- `--attach` 付きで exit 非ゼロになっても、途中までのアップロード分で Issue が作成され URL が出力されていることがある。**再実行する前に出力に Issue URL が無いか確認する**（二重起票を防ぐ）
- 投稿に成功したら本文ファイルを消す（`rm -f "{1 で表示されたパス}"`）。失敗したときは再実行に使うので残す

### Phase 7: 報告

```
Issue を作成しました: {URL}
```
