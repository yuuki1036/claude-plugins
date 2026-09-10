---
description: プラグインの改善要望・バグ報告を GitHub Issue として作成する
user_invocable: true
allowed-tools:
  - Bash
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
5. ユーザーがスクリーンショット・録画のファイルを示していれば添付候補にする（`png` / `jpg` / `jpeg` / `gif` / `webp` / `svg` / `mp4` / `mov` / `webm`、50 件まで）。自分から撮影を求めない。添付の可否は Phase 6 の判定で決まる

### Phase 5: プレビューと承認

Issue 本文は `feedback-issue` スキルの `references/issue-template.md`（正本）の種別別テンプレート（enhancement / bug / question）に従って組み立てる。本文フォーマットをここに重複定義しない（乖離防止）。

以下のヘッダを添えて Issue プレビューを提示し、ユーザーの承認を得る:

```
## Issue プレビュー

**リポジトリ**: yuuki1036/claude-plugins
**タイトル**: [{plugin-name}] {title}
**ラベル**: {label}
**添付**: {添付候補のファイル名。無ければ行ごと省略}

**本文**:
{references/issue-template.md の種別別テンプレートで組み立てた本文}
```

### Phase 6: Issue 作成

承認後、以下を実行:

```bash
gh issue create \
  --repo yuuki1036/claude-plugins \
  --title "[{plugin-name}] {title}" \
  --label "{label}" \
  --body "{body}" \
  --attach "{file}"   # 添付する場合のみ。1 ファイル 1 フラグ
```

- ラベルが存在しない場合は `--label` を省略する
- `--repo yuuki1036/claude-plugins` は意図的な固定値（フィードバック先はユーザーの CWD に関係なく常にマーケットプレイス本体リポジトリ。marketplace.json には repo URL フィールドが無いため導出不可）
- 作成された Issue URL を報告する
- 添付候補がある場合、`--attach` を付けるのは次の両方を満たすときだけ。満たさなければ `--attach` 無しで作成し、報告時に「Issue ページを開いて画像をドラッグ&ドロップで追加して」と案内する:

  ```bash
  # --attach は gh 2.99.0 以降
  gh issue create --help 2>/dev/null | grep -q -- '--attach'
  # アップロードには WRITE 以上が要る。コラボレーター以外は READ なので添付できない
  gh repo view yuuki1036/claude-plugins --json viewerPermission -q .viewerPermission   # WRITE / MAINTAIN / ADMIN
  ```

- `--attach` 付きで exit 非ゼロになっても、途中までのアップロード分で Issue が作成され URL が出力されていることがある。**再実行する前に出力に Issue URL が無いか確認する**（二重起票を防ぐ）

### Phase 7: 報告

```
Issue を作成しました: {URL}
```
