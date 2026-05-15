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

### E2E への昇格（webapp-testing への委譲）

`verify` の smoke test を越えた **複数ステップの E2E シナリオ** が必要な場合（ログイン→操作→離脱、フォーム送信から DB 反映確認まで等）、本 skill では行わず、公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）を呼び出す。

判定基準:

| 状況 | 採用 skill |
|---|---|
| 単一ページの console/network エラー検知、主要要素の描画確認 | `ui-verify`（verify モード）|
| 複数ページを跨ぐシナリオ、認証フロー、データ永続化を含むテスト | `webapp-testing` |
| 既にプロジェクトに Playwright が導入されている | `webapp-testing` |

切り替え時は `chrome-devtools` MCP の代わりに Playwright を使うため、ブラウザの状態管理（storageState、ファイル分割）に強くなる。

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

`--viewports=light,dark` 指定時は viewport を desktop 固定にし、テーマトグルを操作して 2 枚撮影する。テーマ切り替え方法はプロジェクト固有のため、`prefers-color-scheme` の `emulate` または UI 上のトグルボタン操作のいずれかをユーザーに確認する。

### Step 4: 撮影結果の後処理

- `.claude/screenshots/` が存在しなければ作成（`mkdir -p`）
- `.claude/screenshots/.gitignore` に `*` を書いて git 追跡を防ぐ（初回のみ）
- 結果を報告する際は保存パスを file_path:line_number 形式ではなくプレーンパスで提示
- **pending flag の更新**: PostToolUse hook が UI 変更検知時に作成する `.claude/.ui-verify-pending` を `verified-snap` ステータスで上書きする（verify / tune / snap のいずれも実行完了時点）。これにより commit 前の gate hook が黙る。
  ```bash
  mkdir -p .claude
  printf 'verified-snap\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .claude/.ui-verify-pending
  ```
  pending flag は 3 値仕様（`unverified` / `verified-local` / `verified-snap`）。詳細は `git-commit-helper/SKILL.md` Step 4.5「pending flag 3 値仕様」を参照。

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
