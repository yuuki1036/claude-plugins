# chrome-devtools MCP チートシート

ui-verify スキルから参照される MCP tool の使い方メモ。

## ページ管理

### new_page

新しいタブでページを開く。最初のページを開くときはこれを使う。

```
mcp__chrome-devtools__new_page(url: "http://localhost:3000/")
```

### navigate_page

現在のページを別 URL に遷移させる。リロードにも使う（同じ URL を渡す）。

### list_pages / select_page / close_page

複数タブを扱うとき用。基本は1タブで足りる。使い終わりに close_page でクリーンアップする。

## 撮影

### take_screenshot

ページ全体 or 指定要素を PNG で保存。

```
mcp__chrome-devtools__take_screenshot(
  filePath: "/absolute/path/.claude/screenshots/snap-20260418/desktop.png",
  fullPage: true
)
```

**注意:**
- `filePath` は絶対パス推奨
- `fullPage: true` でページ全体、`false` で viewport のみ
- 要素単位で撮りたい場合は先に `take_snapshot` で uid を取得して指定

### take_snapshot

DOM のアクセシビリティツリーを取得。click/fill する要素の uid 特定に使う。screenshot じゃないので注意。

## インタラクション

### click / hover / fill / type_text / press_key

`take_snapshot` で取得した uid を指定して操作する。

```
# 先に snapshot
snapshot = mcp__chrome-devtools__take_snapshot()
# uid を抽出して操作
mcp__chrome-devtools__click(uid: "12345")
mcp__chrome-devtools__fill(uid: "67890", value: "test input")
```

### fill_form

複数フィールド一括入力。ログインフォーム等に便利。

### wait_for

要素やテキストの出現を待つ。SPA の初期描画や遷移後に必須。

```
mcp__chrome-devtools__wait_for(text: "Dashboard")
```

## 観測

### list_console_messages

現在までの console 出力を全取得。`error` / `warning` / `info` / `log` を含む。

```
# エラーだけ抽出するのは返り値側でフィルタ
messages = mcp__chrome-devtools__list_console_messages()
# error level のみをユーザーに報告
```

### list_network_requests

ネットワークリクエスト一覧。status code, URL, method, timing が取れる。

**verify モードでのエラー判定:**
- `status >= 400`
- `failed: true`
- `type === "xhr"` または `"fetch"` で 5xx

### get_console_message / get_network_request

個別詳細。`list_*` で見つけた ID で掘り下げる。

## 環境エミュレーション

### resize_page

viewport サイズ変更。

```
mcp__chrome-devtools__resize_page(width: 375, height: 812)
```

### emulate

デバイス・ネットワーク・CPU throttle。レスポンシブ確認に使う。

## JavaScript 実行

### evaluate_script

任意の JS を実行。scroll 位置調整、data 確認、実 CSS 値取得などに便利。

```
mcp__chrome-devtools__evaluate_script(
  function: "() => window.getComputedStyle(document.querySelector('.header')).padding"
)
```

## 典型フロー

### verify フロー

```
1. new_page(dev server URL)
2. wait_for(主要コンテンツ)
3. list_console_messages → error 抽出
4. list_network_requests → 4xx/5xx 抽出
5. take_snapshot → 重要 UI の存在確認
6. take_screenshot → 最終状態保存
7. 結果整形して報告
```

### tune フロー

```
1. new_page(対象 URL)
2. take_screenshot(before.png)
3. [CSS/tsx ファイル Edit]
4. wait_for(HMR 反映) or navigate_page(reload)
5. take_screenshot(after.png)
6. 差分をユーザーに提示
7. NG なら 3 に戻る
```

### snap フロー

```
for viewport in [mobile, tablet, desktop]:
  resize_page(viewport)
  wait_for(再レイアウト完了)
  take_screenshot(.claude/screenshots/snap-{ts}/{viewport}.png, fullPage=true)
```

## 認証突破ガイド

chrome-devtools-mcp は既定で独立した headless Chrome を起動するため、普段のブラウザのログイン状態は引き継がれない。プロジェクト固有の認証（SSO / OAuth / form login / Cookie session / Bearer）を突破する手段を、推奨度順に列挙する。

### 大原則：id/pass をファイル化しない

`.env` 等に平文で credentials を置くと AI のコンテキストに流出する経路ができる（Read で読まれる / `take_screenshot` に入力済み画面が映る / hook stdout 経由）。**ログイン済みプロファイルを使い回す**運用にすれば、AI は id/pass に一切触れない。どうしてもファイル化が必要な場合は macOS Keychain (`security find-generic-password`) で間接化する。

### パターン 1: 専用プロファイル + `--browserUrl`（鉄板）

認証専用の Chrome を別 user-data-dir で先に起動し、一度だけ手動ログイン。MCP は CDP で attach するだけ。SSO / OAuth / form login すべてに対応。

```bash
# ~/.zshrc にエイリアスを定義
alias chrome-debug='/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-debug-profile" \
  --no-first-run --no-default-browser-check'
```

初回のみ手動ログイン:

```bash
killall -9 "Google Chrome"  # 普段の Chrome を停止
chrome-debug                # → 各サービスへログイン作業
curl -s http://127.0.0.1:9222/json/version  # 疎通確認
```

プロジェクトの `.mcp.json` で MCP を attach 接続にする:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--browserUrl=http://127.0.0.1:9222"]
    }
  }
}
```

⚠️ **Chrome 136+**: デフォルトプロファイルでは `--remote-debugging-port` が無視される。**専用 `--user-data-dir` 必須**。

### パターン 2: `--userDataDir` を MCP に直接渡す（最も省力）

Chrome を別途起動せず、MCP に永続プロファイルパスだけ伝える。初回起動時に開く Chrome で手動ログイン → 次回以降は Cookie が残るので自動。

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest",
               "--userDataDir=/Users/<you>/.chrome-mcp-profile"]
    }
  }
}
```

`--isolated=false`（既定）で永続化される。プロジェクトごとに別パスを指定すれば認証コンテキストを分離できる。

### パターン 3: `--autoConnect`（Chrome 146+ のみ）

普段使いの Chrome に自動接続する新方式。`--user-data-dir` 不要で Google アカウントログイン状態もそのまま使える。

```json
"args": ["-y", "chrome-devtools-mcp@latest", "--autoConnect"]
```

Chrome 146 未満では使えない。バージョン確認は `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version`。

### パターン 4: `--wsHeaders` で Bearer トークン注入

リモート CDP / browserless / Chrome-as-a-Service など、Authorization ヘッダーで認証する経路向け。

```json
"args": [
  "chrome-devtools-mcp@latest",
  "--wsEndpoint=ws://127.0.0.1:9222/devtools/browser/<id>",
  "--wsHeaders={\"Authorization\":\"Bearer ${TOKEN}\"}"
]
```

`${TOKEN}` は direnv + Keychain で間接展開するのが安全:

```bash
# 一度だけ Keychain に登録
security add-generic-password -a "$USER" -s chrome-debug-token -w "ey..."

# .envrc (gitignored)
export TOKEN=$(security find-generic-password -s chrome-debug-token -w)
```

`--wsHeaders` は **`--wsEndpoint` 専用**で `--browserUrl` とは併用不可。

### Basic 認証の注意

- URL 埋め込み（`https://user:pass@host`）は Chrome 64+ で無効化済み。**使えない**
- Bearer 系トークンならパターン 4 が使える
- Basic 認証ダイアログ自体を自動入力する公式オプションは無い。`page.authenticate()` 相当を呼ぶ手段が chrome-devtools-mcp の expose API には無いので、専用プロファイル方式（パターン 1/2）で「一度手動入力 → 認証情報を Chrome に保存」運用が現実解

### 採用フロー

```
プロジェクト固有の認証あり？
  └─ Yes
       │
       ├─ Chrome 146+ で普段の Chrome に依存して良い → パターン 3 (--autoConnect)
       ├─ MCP 起動だけで完結させたい → パターン 2 (--userDataDir)
       ├─ SSO / OAuth で社内ツール多数 → パターン 1 (--browserUrl + 専用プロファイル)
       └─ Bearer ヘッダー認証 → パターン 4 (--wsHeaders + Keychain)
```

## Gotchas

- **stdin/stdout**: MCP server 側で管理されるので気にしなくて良い
- **page の状態永続**: 同一セッションでは new_page しない限りタブが残る。tune モードのループでは navigate_page で遷移するか、既存タブを使う
- **filePath は絶対パス**: 相対パスだと MCP server の CWD 基準になり意図しない場所に保存される
- **Chrome 起動**: 初回呼び出し時に chrome-devtools-mcp が headless Chrome を起動する。少し時間がかかる
- **HMR 待ち**: `wait_for` で特定テキストを待つのが確実。sleep は不確実
- **認証**: 上記「認証突破ガイド」セクションを参照。`.env` への平文 credentials 保存は避け、専用プロファイルか Keychain 経由で扱う
- **Chrome 136+ のセキュリティ変更**: デフォルトプロファイルでは `--remote-debugging-port` が遮断される。`--browserUrl` を使うなら専用 `--user-data-dir` 必須
- **`--wsHeaders` の併用制約**: `--wsEndpoint` 専用。`--browserUrl` とは同時指定不可
