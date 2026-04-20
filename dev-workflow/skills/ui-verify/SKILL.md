---
name: ui-verify
description: |
  chrome-devtools MCP を使って Web UI の動作確認・スタイル調整・スクリーンショット取得を自動化する。
  dev server の起動確認から console/network エラー監視、複数 viewport 撮影まで一貫サポート。
  トリガー: 「動作確認」「UIチェック」「スクリーンショット」「スタイル調整」「見た目確認」「レスポンシブ確認」「/ui-verify」「visual check」「screenshot」「UI verification」「responsive check」
  引数: [verify|tune|snap] [target-url-or-path]
effort: medium
allowed-tools:
  - Bash
  - Read
  - Edit
  - mcp__chrome-devtools__navigate_page
  - mcp__chrome-devtools__new_page
  - mcp__chrome-devtools__take_screenshot
  - mcp__chrome-devtools__take_snapshot
  - mcp__chrome-devtools__list_console_messages
  - mcp__chrome-devtools__list_network_requests
  - mcp__chrome-devtools__resize_page
  - mcp__chrome-devtools__click
  - mcp__chrome-devtools__hover
  - mcp__chrome-devtools__fill
  - mcp__chrome-devtools__press_key
  - mcp__chrome-devtools__wait_for
---

# ui-verify

Web UI の動作確認・スタイル調整・スクリーンショット取得を chrome-devtools MCP で自動化するスキル。

## 3つのモード

| モード | 用途 | 出力 |
|--------|------|------|
| `verify` | 動作確認（console/network エラー検知、主要シナリオ smoke test） | 検知した問題一覧 |
| `tune`   | スタイル調整ループ（撮影→編集→リロード→再撮影） | 調整前後の screenshot |
| `snap`   | スクリーンショット収集（複数 viewport × 状態） | `.claude/screenshots/{timestamp}/*.png` |

引数が無ければ対話的にモードを確認する。URL/path 省略時は後述の自動検出ロジックで決める。

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
5. `mcp__chrome-devtools__wait_for` で HTTP が応答するまで待機（最大30秒）

**認証や環境変数が必要な場合:**
- `.env` / `.env.local` が存在するか確認
- 必要な環境変数が未設定なら起動せず、ユーザーに状況を伝える
- ログイン画面が出る場合は認証済みセッションの使い回しをユーザーに相談

### Step 3: モード別の実行

#### verify モード

動作確認の smoke test を実行する。

1. `new_page` で対象 URL を開く
2. `wait_for` で主要コンテンツの描画を待つ
3. `list_console_messages` で `error` レベルのメッセージ収集
4. `list_network_requests` で `status >= 400` または失敗リクエスト収集
5. ユーザー指定のシナリオがあれば `click` / `fill` / `press_key` で実行
6. 各ステップ後に `list_console_messages` を再取得して新規エラー検知
7. `take_screenshot` で最終状態を記録（`.claude/screenshots/verify-{timestamp}.png`）
8. 結果を整形して報告（エラー0件なら OK、1件以上なら詳細表示）

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

複数 viewport × 状態でスクリーンショット一括収集。

**デフォルト viewport:**
- mobile: 375×812 (iPhone 13 相当)
- tablet: 768×1024
- desktop: 1440×900

**手順:**
1. 出力ディレクトリ作成: `.claude/screenshots/snap-{timestamp}/`
2. 各 viewport で `resize_page` → `take_screenshot` → 保存
3. ユーザーが特定の state (hover, focus, open-modal等) を指定した場合、`hover` / `click` 後に追加撮影
4. 最後に保存済みファイル一覧を報告

### Step 4: 撮影結果の後処理

- `.claude/screenshots/` が存在しなければ作成（`mkdir -p`）
- `.claude/screenshots/.gitignore` に `*` を書いて git 追跡を防ぐ（初回のみ）
- 結果を報告する際は保存パスを file_path:line_number 形式ではなくプレーンパスで提示
- **pending flag のクリア**: PostToolUse hook が UI 変更検知時に作成する `.claude/.ui-verify-pending` を削除する（verify / tune / snap のいずれも実行完了時点で削除）。これにより commit 前の gate hook が黙る。
  ```bash
  rm -f .claude/.ui-verify-pending
  ```

## MCP Tool の使い方

chrome-devtools MCP のツール一覧と典型的な呼び出しパターンは `references/chrome-devtools-cheatsheet.md` を参照。

## 絶対厳守ルール

- dev server の勝手な起動禁止。必ずユーザー確認を取る
- 認証情報やシークレットを screenshot に含めないよう、撮影前にログアウト状態 or masked 状態を確認
- 本番環境 URL に対する `verify` 実行時は書き込み系操作（フォーム送信等）を行わない
- `.claude/screenshots/` 以外への screenshot 保存禁止（プロジェクトに不要ファイルを残さない）
- Web プロジェクトでない場合はスキップ（このプラグイン自体のような marketplace リポでは実行しない）

## Additional Resources

### Reference Files

- **`references/chrome-devtools-cheatsheet.md`** - MCP tool の呼び出しパターンと典型的なフロー
