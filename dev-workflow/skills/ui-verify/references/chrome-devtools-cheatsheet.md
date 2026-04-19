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

## Gotchas

- **stdin/stdout**: MCP server 側で管理されるので気にしなくて良い
- **page の状態永続**: 同一セッションでは new_page しない限りタブが残る。tune モードのループでは navigate_page で遷移するか、既存タブを使う
- **filePath は絶対パス**: 相対パスだと MCP server の CWD 基準になり意図しない場所に保存される
- **Chrome 起動**: 初回呼び出し時に chrome-devtools-mcp が headless Chrome を起動する。少し時間がかかる
- **HMR 待ち**: `wait_for` で特定テキストを待つのが確実。sleep は不確実
- **認証が必要なページ**: chrome-devtools-mcp は独立した Chrome インスタンスなので、ブラウザのログイン状態は引き継がない。テスト用アカウントでのログインフローを組むか、Cookie を事前注入する
