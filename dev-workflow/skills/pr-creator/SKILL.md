---
name: pr-creator
description: |
  PRを作成し、差分とコミット履歴からdescriptionを自動生成する。
  ドラフトPRとして作成し、リポジトリのPRテンプレートがあれば自動準拠する。
  Linear Issue連携: ブランチ名からIssue IDを抽出し、タイトル・説明を取得する。
  トリガー: ユーザーが「PR作って」「/pr-creator」「プルリクエスト作成」と言った時。
effort: medium
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Skill
  - mcp__linear__get_issue
  - mcp__github__create_pull_request
  - mcp__github__update_pull_request
---

# PR Creator

## 実行手順

### 1. PRテンプレートを確認

以下の場所を順にチェックし、見つかればそのフォーマットに従う：
`.github/PULL_REQUEST_TEMPLATE.md`, `.github/pull_request_template.md`, `PULL_REQUEST_TEMPLATE.md`

### 2. 状態確認

```bash
git status
git branch -vv
git remote show origin | grep "HEAD branch"
git log <base-branch>..HEAD --oneline
git diff <base-branch>...HEAD
git diff <base-branch>...HEAD --shortstat
```

diff のファイル数・行数を把握する。目安（400 行超 または 10 ファイル超）を大きく超える場合は、PR 作成は継続しつつ Step 5 のレポート末尾に分割検討の advisory を一言添える。判断基準は [references/description-guide.md](references/description-guide.md) の「変更の粒度を小さく保つ（Small CL）」を参照。

### 3. Linear Issue連携（該当する場合）

ブランチ名からIssue ID（`[A-Z]+-[0-9]+`パターン）を抽出し：
- `mcp__linear__get_issue` でタイトル・説明を取得
- `.claude/plans/{issueId}.md` があれば Claude が読んで description 生成の参考にする。ローカルパス自体は PR 本文に出力しない（レビュアーからクリックできないため）

**Linear MCP が利用できない場合のフォールバック:**
Linear MCP が未設定または接続エラーの場合は、以下の情報のみからPR情報を生成する：
- ブランチ名（Issue IDやタスク名を抽出）
- `git log <base-branch>..HEAD` のコミット履歴
- `git diff <base-branch>...HEAD` の差分内容

Linear連携なしでも基本的なPR作成は問題なく動作する。

詳細は [references/linear-integration.md](references/linear-integration.md) を参照。

### 4. PR情報を生成

- タイトル: Linear Issue があればそのタイトル本文のみを使う（Issue ID prefix の `TEAM-123:` 等は含めない）。なければ変更の要約（50 文字以内）
- Description: 人間レビュアーが読んで `What / Why / Outcome` の三要素が即座に分かること。末尾に `<details><summary>詳細情報</summary>...</details>` を置いて、AI やレビュー bot が参照する補足情報を畳む

三要素の定義:
- **What**: 変更の対象 / スコープ（どのコード・機能・領域を触ったか）
- **Why**: 動機 / 背景（何が問題・状況だったか、なぜ変える必要があったか）
- **Outcome**: 結果 / 効果（何が変わって、ユーザーやコードベースから見てどう違うか）

実装の手段（How）は「変更点」セクションに書く。概要で How まで踏み込むと冗長化するので、概要では Outcome（結果・効果）だけに留める。

リポジトリに PR テンプレートがあれば本文はそれに従い、ない場合は概要 / 変更点 / レビューしてほしいところ / 動作確認 / Screenshots / 備考 の構成を使う。

本文の書き方は [references/description-guide.md](references/description-guide.md) に従う。

### 4.3 writing-polish 連携（PR 本文添削・opt-in）

`writing-polish` plugin が同居していれば、生成した PR 本文(description)をユーザー提示（`gh pr create`）の直前に writing-polish へ渡して推敲できる（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。未インストール時は本ステップを完全に skip し、従来どおり提示する（dormant・後方互換 100%）。

1. インストール判定（check-deps.sh と同方式）:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
     WRITING_POLISH=1
   else
     WRITING_POLISH=0
   fi
   ```
   `WRITING_POLISH=0` → 本ステップを skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を呼ぶ。`--embed` を必ず付け、`--tone pr` を伝え、生成した PR 本文(description)を渡す。
3. 返ってきた推敲済みテキストを description の代わりに使う。ただし **本スキルの厳守ルール（体言止め・常体に統一、敬体禁止、AI 署名禁止、装飾絵文字禁止、ローカルパス出力禁止、PR テンプレートのセクション構造は変更しない＝文面のみ推敲）を満たすこと**。満たさない結果は破棄し元案を使う。変更があれば「何を変えたか」を一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で従来どおり完了する。

### 4.5 Screenshots 添付（UI PR のみ）

以下すべてを満たす場合のみ実行する:

- `.claude/.ui-verify-enabled` が存在
- PR 差分（`git diff <base>...HEAD --name-only`）に UI 拡張子ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）が含まれる
- `gh` が認証済み
- ユーザー引数に `--no-screenshots` が含まれない

#### PR タイプ判定（撮影枚数の調整）

ブランチ名・コミットメッセージ・差分内容から PR タイプを推定し、`ui-verify/SKILL.md` の「PR タイプ別ガイドライン」表に従って撮影枚数を決定する。

| PR タイプ | 判定シグナル | 撮影方針 |
|-----------|------------|---------|
| 検証 PR（probe / spike / stage1 / compat） | ブランチ名に `probe\|spike\|stage1\|compat\|verify\|poc` を含む | **撮影スキップを default**。Screenshots セクション自体を省略 |
| リファクタ（UI 変更なし） | 差分が `.test.` / 設定ファイル / 純粋な型変更のみ | スキップ |
| Theme / Token 変更 | 差分に `tokens` / `theme` / `tailwind.config` 等を含む | light + dark の 2 枚 |
| レイアウト / レスポンシブ変更 | 差分に `@media` / `md:` `lg:` `sm:` 等の breakpoint utility / `grid-template` / `flex-direction` を含む | desktop + mobile（必要なら tablet）の 2–3 枚 |
| UI 新機能 | 上記いずれにも当てはまらず UI ファイル差分が一定以上 | desktop 1 枚を default。1–3 枚 |
| バグ修正（UI レンダリング） | コミット message に `fix` を含み UI ファイル差分あり | 修正対象 viewport 1–2 枚 |

判別不能な場合は **desktop 1 枚** を default とし、`AskUserQuestion` で 「desktop 1 枚 / 複数 viewport / スキップ」を確認する。

#### 撮影フローと PR body 添付

1. `.claude/screenshots/` 内の最新 snap ディレクトリを特定。見つからなければ ui-verify スキルを `snap` モードで起動して新規撮影（PR タイプ判定結果に応じた `--viewports=...` を渡す）

   ```bash
   # ui-verify が作る snap-* / git-commit-helper が作る commit-* の両方を対象
   LATEST=$(ls -1dt .claude/screenshots/{snap,commit}-* 2>/dev/null | head -1)
   ```
2. **撮影内容の機密チェック**（次節「機密 UI チェックリスト」を実施）。問題があれば中止
3. `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/upload-screenshots.sh <dir>` を実行して画像を GitHub Release (`cc-screenshots` タグ) にアップロード
4. 標準出力の `<filename><TAB><url>` を解析
5. PR body に以下を追記（テンプレート既存セクションの末尾 or 新規 `## Screenshots` として）。**1 枚のみの場合は table ではなく単独画像で添付する**:

   ```markdown
   <!-- 1 枚の場合 -->
   ## Screenshot

   ![desktop](<url>)

   <!-- 複数枚の場合 -->
   ## Screenshots

   | viewport | preview |
   |----------|---------|
   | mobile   | ![mobile](<url>) |
   | desktop  | ![desktop](<url>) |
   ```

   viewport 名はファイル名から推定（`mobile.png` / `desktop.png` 等）。不明なものは `<name> | ![<name>](<url>)` 形式。

**アップロード失敗時のフォールバック:**
- `gh` 未認証、ネットワークエラー、権限なし等で失敗した場合、`## Screenshots` セクションは PR 本文に含めない（ローカルパスは PR 本文に書かない方針）
- ユーザーに「PR 作成後に画像をドラッグ&ドロップで手動添付してください」と口頭で案内する
- PR 作成自体は継続する

#### 機密 UI チェックリスト（撮影前必須）

`cc-screenshots` release は public release のため、アップロードした画像は誰でも閲覧可能。以下のいずれかに該当する撮影は **アップロードしない**:

- ログイン画面・認証画面（OAuth プロバイダ名・社内 SSO ボタン等のメタ情報を含む）
- 顧客データ・実名ユーザー情報・実メールアドレス・実電話番号
- 社内 URL / 社内 API エンドポイント / 社内サービス名
- 機密 UI（権限管理画面、課金画面、管理者ダッシュボード等）
- 環境変数値・API キー・トークン文字列（DevTools 開いた状態等）

判定不能な場合は AskUserQuestion でユーザーに確認:

- question: "撮影内容に機密情報は含まれていない？（public release にアップロード）"
- header: "機密チェック"
- options:
  1. label: "問題なし、アップロード" / description: "撮影内容を確認済み"
  2. label: "アップロードせずスキップ" / description: "Screenshots セクションを PR 本文から省略し、手動添付をユーザーに口頭案内"
  3. label: "Screenshots を省略" / description: "PR body から Screenshots セクション自体を削除"

### 4.9 PR body の最終検証（gitignored パス検出）

`gh pr create` を実行する直前に、生成した body から gitignored パスを検出して fail-fast する。一度 PR が public になると内部パス参照は外部から見えてしまうため、文書ルール（厳守ルール参照）だけでなく機械チェックで橋渡しする。

```bash
# $pr_body に生成済みの PR 本文が入っている前提
# 1) 代表的な gitignore 対象パスの即時検出（regex）
violations=$(printf '%s\n' "$pr_body" | grep -E '(\.claude/|\.next/|node_modules/|dist/|build/|coverage/|\.env)' || true)

# 2) リポジトリ固有の gitignore も尊重（動的判定）
while read -r path; do
  [ -n "$path" ] && git check-ignore -q "$path" 2>/dev/null && violations="${violations}"$'\n'"gitignored: $path"
done < <(printf '%s\n' "$pr_body" | grep -oE '[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+')

[ -n "$violations" ] && { echo "PR body に gitignored パスが含まれています:"; printf '%s\n' "$violations"; }

# 3) パス文字列を伴わないローカル限定ドキュメント参照の検出（advisory・非 fail-fast）
#    「knowledge に詳細」「設計メモ参照」のように regex (1)(2) をすり抜ける自然言語の言及を拾う。
#    誤検知が出やすい（一般語としての knowledge / plan を含む）ため warning のみで PR は止めない。
soft=$(printf '%s\n' "$pr_body" | grep -nE '(knowledge|設計メモ|実装メモ|作業メモ|ローカル(の)?(メモ|ノート|ドキュメント|ファイル)|plans?/|issues?/).{0,12}(参照|に詳細|を参照|参考|see|詳しくは)' || true)
[ -n "$soft" ] && { echo "[advisory] レビュアーが開けないローカル限定ドキュメントへの言及かもしれません。要点を本文にインライン要約できないか確認してください:"; printf '%s\n' "$soft"; }
```

regex (1)(2) で検出された場合は **PR を作成せず**、該当箇所を body から除去（または GitHub からクリック可能な URL に置換）してから再検証する。除去後に違反 0 件になったことを確認してから Step 5 に進む。

(3) の advisory は PR 作成を止めない。ヒットした箇所が本当にローカル限定ドキュメントへの参照なら、参照させるのではなく要点を本文へ書き写してから進む。一般語としての `knowledge` / `plan`（外部リンク付き・社内 wiki 等のクリック可能リソースを含む）であれば無視してよい。

### 5. PRを作成

```bash
git push -u origin <current-branch>
gh pr create --draft --title "<title>" --body "<description>"
```

作成後はURLを表示する。

#### gh pr create / edit が失敗した場合のフォールバック

`gh pr create` / `gh pr edit` が以下の Projects (classic) 廃止エラーで exit 1 になることがある（Projects classic を使っていないリポでも、gh CLI が PR mutation 時に `projectCards` を取得するため発生する）:

```
GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience ... (repository.pullRequest.projectCards)
```

この場合は github MCP にフォールバックする（GraphQL の `projectCards` field を触らないため deprecation の影響を受けない）:

```
# 新規作成
mcp__github__create_pull_request({ owner, repo, head, base, title, body, draft: true })

# body 更新
mcp__github__update_pull_request({ owner, repo, pullNumber, body })
```

github MCP が未設定の場合は、PR を最小 body で作成し、本文はユーザーに手動更新を案内する。gh CLI 側にパッチが入って `projectCards` 取得を回避するようになれば、このフォールバックは不要になる。

## 厳守ルール

- 常にドラフトPRとして作成
- テンプレートのセクションは空欄にせず内容を埋める。書くことがなければセクションごと削除する
- AI 署名（Generated with 等）は付けない
- 本文は人間向け、末尾の `<details>` 折りたたみは AI 向けの補足情報。レビュアーが行動を変える情報を折りたたみに隠さない
- 文体は体言止め・常体に統一する。敬体（です・ます）は使わない。コミットメッセージの文体と揃える
- 箇条書きの乱発を避ける（並列性のない情報を無理に箇条書きにしない）。並列の手順 / 変更項目 / 動作確認ケースが複数ある場合は箇条書きで OK
- 太字の乱用と装飾絵文字（✅ ❌ 🤖 など）は避ける
- 概要は `What / Why / Outcome` の三要素（変更対象 / 動機 / 結果）を満たすこと。実装手段（How）は「変更点」セクションに書く
- 本文量の上限を数値で守る（質的記述だけだと冗長化するため数値で制限）: **概要は 1〜2 文 / 「変更点」は 1〜5 bullet / 「レビューしてほしいところ」は 1〜3 件**。上限を超える場合は情報を圧縮するか PR 分割を検討する。Screenshots 節は frontend（UI 拡張子）変更を含む場合のみ追加する（Step 4.5 の判定に従う）
- PR title に Issue ID prefix（`TEAM-123:` 等）を含めない。Issue ID は PR 本文側にリンク・参照として記載する
- PR 本文（本文・`<details>` 折りたたみ問わず）にローカルパス（`.claude/plans/...` / `.claude/screenshots/...` 等）を出力しない。GitHub からクリックできないため
- レビュアーがアクセスできないローカル限定ドキュメント（`.claude/` 配下の knowledge / plans / issues 等）は、**パス文字列の有無に関わらず**本文で参照しない。「knowledge に詳細」「設計メモ参照」のような自然言語の言及も含む。必要な情報は本文へインライン要約する（参照させるのではなく要点を書き写す）
- Screenshots は `cc-screenshots` release にアップロードする専用運用。他の release と混ぜない
- 機密情報（ログイン画面、社内 URL、実データ等）が写っていないか撮影前に確認する。アップロードは public release なので漏洩リスクあり
