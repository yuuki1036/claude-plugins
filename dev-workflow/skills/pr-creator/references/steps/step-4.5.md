<!-- 正本依存（SSoT pin）。この Step が言い換えている ui-verify の節。正本が変わったら本ファイルへの伝播を確認して pin を書き換える -->
<!-- SSOT: dev-workflow/skills/ui-verify/references/modes/snap.md#PR @99f5f200 -->

### 4.5 Screenshots 添付（UI PR のみ）

以下すべてを満たす場合のみ実行する:

- `.claude/.ui-verify-enabled` が存在
- PR 差分（`git diff <base>...HEAD --name-only`）に UI 拡張子ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）が含まれる
- `gh` が認証済み
- ユーザー引数に `--no-screenshots` が含まれない
- `gh` が `--attach` に対応し、base リポジトリへの書き込み権限がある:

  ```bash
  # --attach は gh 2.99.0 で入った。GitHub.com / GHE.com のみ（GHES と GitHub App トークンは非対応）
  gh pr create --help 2>/dev/null | grep -q -- '--attach' && ATTACH_OK=1 || ATTACH_OK=0
  # アップロードには WRITE / MAINTAIN / ADMIN が要る（fork から upstream への PR では通常満たさない）
  case "$(gh repo view --json viewerPermission -q .viewerPermission 2>/dev/null)" in
    WRITE|MAINTAIN|ADMIN) ;;
    *) ATTACH_OK=0 ;;
  esac
  ```

  `ATTACH_OK=0` なら本ステップを skip し、Step 5 のレポートで理由（gh が古い → `gh upgrade` 等で 2.99.0 以降へ / 権限不足）と「PR 作成後にブラウザで画像を手動添付」を一言添える

#### PR タイプ判定（撮影枚数の調整）

ブランチ名・コミットメッセージ・差分内容から PR タイプを推定し、ui-verify の snap モード（`${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/references/modes/snap.md`）の「PR タイプ別ガイドライン」表に従って撮影枚数を決定する。

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

1. 添付する撮影ディレクトリを同梱スクリプトで選ぶ。`.claude/screenshots/` はチェックアウトに 1 つでブランチを切り替えても残るので、最新をそのまま使うと、前に別のブランチで撮った画面をこの PR に添付する。スクリプトは ui-verify の snap / verify / tune モードのディレクトリ（`snap-*` / `verify-*` / `tune-*`）のうち、このチェックアウトが今のブランチに切り替わった後に撮ったものだけから最新を選ぶ:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/pick-screenshot-dir.sh"
   ```

   `SCREENSHOT_DIR=<パス>` が出たらそのディレクトリを使う。`SCREENSHOT_DIR=none`（`REASON=` が理由）なら ui-verify スキルを `snap` モードで起動して新規撮影し（PR タイプ判定結果に応じた `--viewports=...` を渡す）、snap が報告した保存先のディレクトリを使う（今撮ったものなので選び直さない）。`SINCE=` / `SINCE_SOURCE=` / `SKIPPED=`（どの時刻より後を今のブランチの撮影と見たか・外した数）の定義はスクリプト冒頭のコメント
2. **撮影内容の機密チェック**（次節「機密 UI チェックリスト」を実施）。問題があれば中止
3. 添付ファイルを `ATTACH` 配列に集める。対象は `png` / `jpg` / `jpeg` / `gif` / `webp` / `svg` と、録画があれば `mp4` / `mov` / `webm`（gh が受け付ける形式はこの 9 種のみ）。**1 回の gh 呼び出しで 50 件まで**
4. PR body に以下を追記（テンプレート既存セクションの末尾 or 新規 `## Screenshots` として）。画像の参照先は **`ATTACH` に入れたローカルパスをそのまま書く** — `gh pr create --attach` がアップロード時に同じパスの Markdown 参照を GitHub 上の URL へ書き換える（alt text は保持される）。**1 枚のみの場合は table ではなく単独画像で添付する**:

   ```markdown
   <!-- 1 枚の場合 -->
   ## Screenshot

   ![desktop](<ATTACH のパス>)

   <!-- 複数枚の場合 -->
   ## Screenshots

   | viewport | preview |
   |----------|---------|
   | mobile   | ![mobile](<ATTACH のパス>) |
   | desktop  | ![desktop](<ATTACH のパス>) |
   ```

   **tune モードのディレクトリ（`before.png` / `after.png`）は対で出す** — 変更前後を並べないと、何が変わったかがレビュアーに伝わらない:

   ```markdown
   | before | after |
   |--------|-------|
   | ![before](<before のパス>) | ![after](<after のパス>) |
   ```

   viewport 名はファイル名から推定（`mobile.png` / `desktop.png` 等）。不明なものは `<name> | ![<name>](<ATTACH のパス>)` 形式。動画は alt text を持てないので table に入れず `![recording](<ATTACH のパス>)` を単独行で置く（単独行は動画プレーヤーの URL に書き換わる。reference 形式 `![x][id]` は gh が拒否する）

アップロードは Step 5 の `gh pr create` 実行時に行われる（本ステップではまだ何も送信しない）。したがって Step 4.95 で「中止」してもリモートに画像は残らない。

#### 機密 UI チェックリスト（撮影前必須）

添付した画像は PR 本文に埋め込まれ、PR を閲覧できる人全員（public repo なら誰でも）が見られる。以下のいずれかに該当する撮影は **添付しない**:

- ログイン画面・認証画面（OAuth プロバイダ名・社内 SSO ボタン等のメタ情報を含む）
- 顧客データ・実名ユーザー情報・実メールアドレス・実電話番号
- 社内 URL / 社内 API エンドポイント / 社内サービス名
- 機密 UI（権限管理画面、課金画面、管理者ダッシュボード等）
- 環境変数値・API キー・トークン文字列（DevTools 開いた状態等）

判定不能な場合は AskUserQuestion でユーザーに確認:

- question: "撮影内容に機密情報は含まれていない？（PR 本文に添付）"
- header: "機密チェック"
- options:
  1. label: "問題なし、添付する" / description: "撮影内容を確認済み"
  2. label: "添付せず手動に回す" / description: "Screenshots セクションを PR 本文から省略し、手動添付をユーザーに口頭案内"
  3. label: "Screenshots を省略" / description: "PR body から Screenshots セクション自体を削除"

**次は Step 4.6**（SKILL.md に戻り、その見出しを見る）
