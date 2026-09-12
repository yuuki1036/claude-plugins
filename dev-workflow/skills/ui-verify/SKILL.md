---
name: ui-verify
description: |
  Web UI の動作確認（実機 E2E）・スタイル調整・スクリーンショット取得を自動化する。
  verify は正常・準正常・異常系を実機ブラウザで通し、合否と証跡を .claude/verification/ に残す。
  認証あり画面はログイン済みブラウザの状態を再利用する（パスワード入力はしない）。
  トリガー: 「動作確認」「UIチェック」「E2E」「スクリーンショット」「スタイル調整」「見た目確認」「レスポンシブ確認」「/ui-verify」「visual check」「screenshot」「UI verification」「responsive check」
  引数: [verify|tune|snap] [target-url-or-path]
effort: medium
allowed-tools:
  - Bash
  - Read
  - Edit
  - AskUserQuestion
  - Skill
  - mcp__plugin_dev-workflow_chrome-devtools__navigate_page
  - mcp__plugin_dev-workflow_chrome-devtools__new_page
  - mcp__plugin_dev-workflow_chrome-devtools__take_screenshot
  - mcp__plugin_dev-workflow_chrome-devtools__take_snapshot
  - mcp__plugin_dev-workflow_chrome-devtools__list_console_messages
  - mcp__plugin_dev-workflow_chrome-devtools__list_network_requests
  - mcp__plugin_dev-workflow_chrome-devtools__resize_page
  - mcp__plugin_dev-workflow_chrome-devtools__emulate
  - mcp__plugin_dev-workflow_chrome-devtools__click
  - mcp__plugin_dev-workflow_chrome-devtools__hover
  - mcp__plugin_dev-workflow_chrome-devtools__fill
  - mcp__plugin_dev-workflow_chrome-devtools__press_key
  - mcp__plugin_dev-workflow_chrome-devtools__wait_for
  - mcp__Claude_Browser__navigate
  - mcp__Claude_Browser__computer
  - mcp__Claude_Browser__find
  - mcp__Claude_Browser__read_page
  - mcp__Claude_Browser__form_input
  - mcp__Claude_Browser__read_console_messages
  - mcp__Claude_Browser__read_network_requests
  - mcp__Claude_Browser__preview_start
  - mcp__Claude_Browser__preview_logs
  - mcp__claude-in-chrome__navigate
  - mcp__claude-in-chrome__computer
  - mcp__claude-in-chrome__find
  - mcp__claude-in-chrome__read_page
  - mcp__claude-in-chrome__form_input
  - mcp__claude-in-chrome__read_console_messages
  - mcp__claude-in-chrome__read_network_requests
  - mcp__claude-in-chrome__tabs_context_mcp
  - mcp__claude-in-chrome__tabs_create_mcp
---

# ui-verify

Web UI の動作確認（実機 E2E）・スタイル調整・スクリーンショット取得を自動化するスキル。

## 3つのモード

| モード | 用途 | 出力 |
|--------|------|------|
| `verify` | 実機ブラウザで正常・準正常・異常系を通し、合否と証跡を残す | `.claude/verification/<branch>.md` + 証跡 |
| `tune`   | スタイル調整ループ（撮影→編集→リロード→再撮影） | 調整前後の screenshot |
| `snap`   | スクリーンショット収集（複数 viewport × 状態） | `.claude/screenshots/{timestamp}/*.png` |

引数が無ければ対話的にモードを確認する。URL/path 省略時は後述の自動検出ロジックで決める。

### verify は実機 E2E（役割分担）

`verify` は**実機ブラウザで E2E を通す**。console/network のエラー検知に留めず、ケースごとに操作して期待結果を確認し、合否（pass/fail/blocked）と証跡を `.claude/verification/<branch>.md` に残す。結果は `pr-creator` が動作確認セクションの材料に読む。

役割は 3 つに分ける（前提: E2E の合否は実機ブラウザでしか決めない）:

| 目的 | 手段 |
|---|---|
| E2E の実行と合否判定 | 実機ブラウザ（chrome-devtools / Claude Browser / Claude in Chrome。後述 Step 3 の優先順位） |
| スクショ（添付用証跡） | Storybook があればそれ、なければ chrome-devtools / Playwright |
| 動画（添付用証跡） | Playwright の recordVideo（webm） |

**Playwright / Storybook は証跡撮影係であって E2E の代替にしない**。複数ステップの Playwright script が要る撮影は公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）に委譲する。repo に Playwright が入っていればそれを使う。

`snap` モードは追加引数 `--viewports=...` を受け付ける（デフォルトは desktop 1 枚）。詳細は後述「snap モード」参照。

## 実行手順

### Step 1: 対象プロジェクトの Web 判定

プロジェクトが Web フロントエンドを持つか判定する。該当しないプロジェクトで起動された場合は中止し、理由をユーザーに伝える。

```bash
# package.json に Web フレームワーク依存があるか
jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys | .[]' package.json 2>/dev/null | \
  grep -E '^(next|react|vue|svelte|@angular/core|nuxt|astro|solid-js|remix)$' | head -3
```

マッチが無い場合は「Web プロジェクトとして検出できません。対象 URL を明示してください」と確認する。

### Step 2: dev server の確保

起動中のポートを lsof で確認し、未起動なら立ち上げる。

```bash
# 候補ポート（package.json の scripts.dev から推定 → fallback: 3000, 5173, 4321, 8080）
DEV_PORT=$(jq -r '.scripts.dev // empty' package.json 2>/dev/null | grep -oE '\-\-port[= ][0-9]+|PORT=[0-9]+' | grep -oE '[0-9]+' | head -1)
DEV_PORT=${DEV_PORT:-3000}

# 起動中か確認
lsof -nP -iTCP:${DEV_PORT} -sTCP:LISTEN 2>/dev/null
```

**起動してない場合の対応:**

1. `package.json` の `scripts.dev` (または `start`, `preview`) を読む
2. パッケージマネージャを推定（`pnpm-lock.yaml`→pnpm / `yarn.lock`→yarn / `bun.lockb`→bun / else npm）
3. **ユーザーに起動許可を確認**（勝手に port を占有しない）
4. 許可されたら background で起動: `pnpm dev &` 相当を Bash の `run_in_background: true` で実行
5. HTTP が応答するまで Bash で待機する（`wait_for` は**ページ上のテキスト出現待ち**であって
   疎通待ちではないので使えない）:
   ```bash
   for _ in $(seq 30); do
     curl -sSf -o /dev/null "http://localhost:${DEV_PORT}/" && break
     sleep 1
   done
   ```
   疎通後、ページ描画の完了は `wait_for(text: ["..."])` で待つ

**認証や環境変数が必要な場合:**
- `.env` / `.env.local` が存在するか確認
- 必要な環境変数が未設定なら起動せず、ユーザーに状況を伝える
- ログイン画面が出る場合は認証済みセッションの使い回しをユーザーに相談

#### dev server ライフサイクル（セッション中は保持する）

dev server はセッション開始時に **1 回だけ** 起動し、以後は **保持** する。タスク完了ごとに停止・再起動しない。再起動を繰り返すと HMR WebSocket 断（`ERR_CONNECTION_REFUSED`）、認証セッションの再ハンドシェイク、ユーザーが並行で開いている server との二重起動衝突、port 競合解消ループ（1 サイクル ~10s）が発生する。1 セッション内で 4 回の再起動が観測された実例あり。

- セッション開始時に **1 回だけ** 起動。以後は **保持** する
- コード変更は **HMR** で反映 / chrome-devtools `navigate_page reload` で手動 reload
- `TaskStop`（server 停止）するのは下記のみ:
  1. ユーザーが明示的に「dev server 止めて」と言ったとき
  2. セッション終了時（PR 作成完了などの最終出口）
- ターン途中で再検証が必要なときは、起動中の server を **そのまま使う**（再起動しない）
- Tailwind v4 + Turbopack で「新規 utility class の初出で HMR に乗らない」等の特殊事情があるときだけ例外的に restart

##### 検出ロジック

- 起動前: `lsof -i :$DEV_PORT -t` が空なら起動
- 起動中: そのまま使う、止めない

```bash
# 1 行で判定
if [ -z "$(lsof -i :${DEV_PORT} -t 2>/dev/null)" ]; then
  : # 未起動 → 起動許可をユーザーに確認してから background 起動
else
  : # 起動中 → そのまま使う（kill / restart 禁止）
fi
```

E2E への昇格（`webapp-testing` / Playwright）時も、Playwright の `webServer.reuseExistingServer: true` 相当で起動中 server を再利用する方針に揃える。

### Step 3: モード別の実行

#### verify モード（実機 E2E）

正常・準正常・異常系を実機ブラウザで通し、合否と証跡を `.claude/verification/<branch>.md` に残す。手順は「基盤選択 → ケース列挙 → 実行と判定 → 証跡 → 記録」。

##### (a) ブラウザ基盤の選択

対象 URL を開いてログイン画面（`/login` `/signin` へのリダイレクト、password 型 input）を検知したら「認証必要」と判定する。事前にユーザーへ聞かない。

```
認証不要 ─→ chrome-devtools（既定プロファイル）
認証必要 ─→ chrome-devtools --autoConnect（実 Chrome のログイン状態。userConfig browser_connect=autoConnect）
              ↓ 起動不可（Chrome 144 未満 / npx 不在 / 接続失敗）
            Claude Browser（mcp__Claude_Browser__*）
              ↓ 無い（CLI など）
            Claude in Chrome（mcp__claude-in-chrome__*）
              ↓ 未接続 / 別アカウント
            ログイン画面で停止し、ユーザーにログインを依頼して続行
```

- `--autoConnect` を使うには `userConfig.browser_connect` を `autoConnect` にする（既定は `default`）。ADR-20260831 の privacy posture から既定では実プロファイルに繋がない
- **Claude Browser / Claude in Chrome はスクショをファイルに保存できない**。この 2 基盤に落ちた回は E2E の操作と合否判定だけを行い、証跡は (d) で別途撮るか「証跡なし」と記録する
- **期待ユーザーの確認**（アカウント切替対策）: E2E 起動時にユーザーへ 1 回「どのアカウントでログイン中か」を確認し、`expected_user` として verification.md に記録する。最初のケースで画面の表示ユーザー名を読み取り `signed_in_as` に記録し、`expected_user` と照合する。違えば停止して報告（自動で切り替えない）。表示名が読めない場合はその旨を記録し、意図したアカウントかを起動時に確認する

##### (b) ケース列挙

次の順に材料を集めて 1 つのケース表に統合する。各ケースは `id` / `種別`（正常/準正常/異常）/ `手順` / `期待結果` / `列挙元` を持つ。

| 列挙元 | 探し方 |
|---|---|
| spec.md | `features/**/spec.md` を Glob。diff で触ったモジュールの Feature / Scenario / 同値分割表の各行 |
| Issue 本文 | `.claude/indie/*/issues/*.md` / `.claude/linear/*/issues/*.md` をブランチ名で照合。受け入れ条件・エッジケース |
| diff 推定 | 追加されたバリデーション・分岐・エラーハンドリング・空配列判定の反対側 |
| 固定 5 項目 | 入力エラー / 空状態 / 権限なし / 通信失敗 / 二重送信。該当しない項目は「対象外」と明記して残す |

**`${CLAUDE_EFFORT}` 分岐**: `low` / `medium` は spec + Issue + 固定 5 項目。`high` 以上で diff 推定も加える。

列挙したケース表はユーザーに提示して確認を取ってから実行する（削る・足す）。

##### (c) 実行と判定

- ケースごとに `navigate → 操作 → 期待結果の確認 → console/network のエラー収集 → 撮影` を回す
- 合否は 3 値: `pass` / `fail`（期待と実際の差分を 1 行）/ `blocked`（認証・環境で実行できなかった）
- **書き込み系（フォーム送信・削除・確定）の歯止めは 2 段**:
  - 本番 URL では一切書き込まない（従来どおり）
  - `--autoConnect` / 実 Chrome 基盤では破壊的操作を**既定 blocked**。dev server の backend が隔離環境（テスト DB / seed データ）だとユーザーが 1 回確認したときだけ解禁し、verification.md の `backend_isolation: confirmed` に記録する。確認が取れなければ読み取り系のみ実行し、破壊的ケースは `blocked: 書き込み先未確認` で残す
- 二重送信は連打せず「送信直後にボタンの disabled / 二重リクエストの有無を network で確認」

##### (d) 証跡撮影（E2E とは別係）

- スクショ: 基盤が chrome-devtools なら `take_screenshot(filePath=.claude/screenshots/verify-<timestamp>/<case-id>.png)`。pane / Claude in Chrome 基盤のときは Storybook があればその story を chrome-devtools で開いて撮る。撮れなければ「証跡なし」
- 動画: ユーザーが要求したケース、または `fail` したケースで Playwright recordVideo（webm）。認証画面は chrome-devtools 側 cookie から storageState を生成
- **初版（v1）の最小形は「chrome-devtools スクショ + fallback 基盤は証跡なし」**。Storybook 再現・Playwright 動画は必要になった回に足す
- **autoConnect / 実 Chrome の証跡は実ユーザー情報を含みやすい**ので、既定で PR 添付対象外（ローカル保持）とし、PR 添付は dev アカウント画面に限りユーザー承認で opt-in する（pr-creator の機密チェックと重ねる）

##### (e) verification.md への記録

`.claude/verification/<branch>.md` に次を書く（Shared State 規約の frontmatter 必須）:

```markdown
---
shared_state_type: verification
producer: dev-workflow:ui-verify
consumers: [dev-workflow:pr-creator]
schema_version: 1
last_updated: <ISO8601>
branch: <branch>
base: <base-branch>
head: <commit sha>
browser: chrome-devtools(autoConnect) | chrome-devtools | browser-pane | claude-in-chrome
expected_user: <起動時に確定した期待ユーザー or null>
signed_in_as: <表示ユーザー名 or null>
backend_isolation: confirmed | unconfirmed
---

## ケース
| id | 種別 | 手順 | 期待 | 結果 | 証跡 | 列挙元 |
|----|------|------|------|------|------|--------|

## 環境
- dev server / console error / network 4xx-5xx

## 未実施
- <ケース id と理由>
```

- 2 回目実行は上書きする（最新の head が正）。ただし `expected_user` は消さず引き継ぐ
- 出力先を作る: `mkdir -p .claude/verification` し、`.claude/verification/.gitignore` に `*` を書く（初回のみ）
- 記録後に pending flag を `verified-snap` で上書きする（Step 4 参照）

#### tune モード

スタイル調整の対話ループ。

1. 初回の `take_screenshot` を `.claude/screenshots/tune-{timestamp}/before.png` に保存
2. ユーザーに調整内容を確認（例: 「ヘッダーの余白を広げたい」「ボタンの色を primary に」）
3. 該当 CSS/tsx ファイルを特定し Edit で修正
4. dev server の HMR 反映を待つ（`wait_for` + 短い sleep）
5. `take_screenshot` で after.png を保存
6. 差分をユーザーに提示し、OK なら終了、NG ならループ

**HMR が効かない場合:**
- `navigate_page` で再読み込み
- ビルドエラーなら `list_console_messages` で原因特定

#### snap モード

スクリーンショット一括収集。**デフォルトは desktop 1 枚のみ**。複数 viewport が必要な PR タイプの場合のみ opt-in する。

**デフォルト viewport:** desktop 1440×900 のみ（1 枚）

**opt-in 引数:**

| 引数 | 撮影対象 |
|------|---------|
| なし（デフォルト） | desktop のみ |
| `--viewports=mobile,desktop` | 指定した viewport |
| `--viewports=mobile,tablet,desktop` | 3 viewport 全部 |
| `--viewports=light,dark` | テーマ切り替え（後述「テーマ撮影」参照） |

**プリセット viewport サイズ:**
- mobile: 375×812（iPhone 13 相当）
- tablet: 768×1024
- desktop: 1440×900

**PR タイプ別ガイドライン:**

`pr-creator` / `git-commit-helper` から呼ばれた時、PR の性質に応じて以下を目安に viewport を選択する。撮影目的は「証跡」「レビュー補助」「レスポンシブ検証」のいずれかに分類できる。

| PR タイプ | 推奨枚数 | viewport |
|-----------|---------|---------|
| 検証 PR (probe / spike / stage1 / compat) | 0–1 | desktop のみ、または省略 |
| リファクタ（UI 変更なし） | 0 | — |
| UI 新機能 | 1–3 | desktop + 必要なら mobile |
| レイアウト / レスポンシブ変更 | 2–3 | desktop + mobile (+ tablet if breakpoint) |
| Theme / Token 変更 | 2 | light + dark |
| バグ修正（UI レンダリング） | 1–2 | 修正対象の viewport |

PR タイプ判定はブランチ名・コミットメッセージ・差分から推定する。判別不能な場合はユーザーに確認。

**手順:**
1. 出力ディレクトリ作成: `.claude/screenshots/snap-{timestamp}/`
2. 引数で指定された viewport（無ければ desktop のみ）について `resize_page` → `take_screenshot` → 保存
3. ユーザーが特定の state (hover, focus, open-modal等) を指定した場合、`hover` / `click` 後に追加撮影
4. 最後に保存済みファイル一覧を報告

**テーマ撮影:**

`--viewports=light,dark` 指定時は viewport を desktop 固定にし、テーマを切り替えて 2 枚撮影する。

既定は `emulate` による `prefers-color-scheme` のエミュレート（プロジェクト非依存で決定的）:

```
mcp__plugin_dev-workflow_chrome-devtools__emulate(colorScheme: "light")  # → light.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(colorScheme: "dark")   # → dark.png
mcp__plugin_dev-workflow_chrome-devtools__emulate(colorScheme: "auto")   # 撮影後に解除
```

アプリが `prefers-color-scheme` ではなく自前のトグル（class / localStorage 等）でテーマを持つ場合は emulate が効かないため、その場合のみ UI 上のトグル操作に切り替える（どちらを使うかをユーザーに確認する）。

### Step 4: 撮影結果の後処理

- `.claude/screenshots/` が存在しなければ作成（`mkdir -p`）
- `.claude/screenshots/.gitignore` に `*` を書いて git 追跡を防ぐ（初回のみ）
- 結果を報告する際は保存パスを file_path:line_number 形式ではなくプレーンパスで提示
- **pending flag の更新**: PostToolUse hook が UI 変更検知時に作成する `.claude/.ui-verify-pending` を `verified-snap` ステータスで上書きする（verify / tune / snap のいずれも実行完了時点）。これにより commit 前の gate hook が黙る。
  ```bash
  mkdir -p .claude
  printf 'verified-snap\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```
  pending flag は 3 値仕様（正本はここ）:

  | 値 | 意味 | 書き込む主体 |
  |----|------|------------|
  | `unverified` | 未確認。gate hook が `git commit` 直前に reminder を出す | `ui-change-reminder.sh`（UI ファイル変更検知時） |
  | `verified-local` | ローカル目視済み。gate hook は黙る | 手動（撮影せず黙らせたいとき） |
  | `verified-snap` | snap 撮影済み。gate hook は黙る | ui-verify（verify / tune / snap の完了時） |

  撮影せず黙らせる場合は次を実行する:
  ```bash
  printf 'verified-local\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```

## MCP Tool の使い方

chrome-devtools MCP のツール一覧と典型的な呼び出しパターンは `references/chrome-devtools-cheatsheet.md` を参照。

## 絶対厳守ルール

- dev server の勝手な起動禁止。必ずユーザー確認を取る
- 一度起動した dev server をタスク完了ごとに停止・再起動しない。セッション中は保持する（詳細は Step 2「dev server ライフサイクル」）
- 認証情報やシークレットを screenshot に含めないよう、撮影前にログアウト状態 or masked 状態を確認
- 本番環境 URL に対する `verify` 実行時は書き込み系操作（フォーム送信等）を行わない
- `.claude/screenshots/` 以外への screenshot 保存禁止（プロジェクトに不要ファイルを残さない）
- Web プロジェクトでない場合はスキップ（このプラグイン自体のような marketplace リポでは実行しない）

## Additional Resources

### Reference Files

- **`references/chrome-devtools-cheatsheet.md`** - MCP tool の呼び出しパターンと典型的なフロー
