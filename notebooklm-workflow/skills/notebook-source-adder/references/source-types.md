# ソースタイプ別の挙動

NotebookLM が受け付けるソースタイプと、`source_add` MCP tool に渡す入力形式の対応表。

`source_add` は `source_type` で入力種別を指定し、種別ごとに対応するキーワード引数を渡す（現行 notebooklm-mcp のシグネチャ）:

```
source_add(notebook_id, source_type=url|text|drive|file,
           url=..., urls=[...], text=..., title=...,
           document_id=..., doc_type=doc|slides|sheets|pdf,
           file_path=..., wait=false)
```

`source_type` を明示指定するのが基本。`url` は単体、`urls=[...]` は複数一括に使う。

## URL（一般 Web ページ）

```
source_add(notebook_id, source_type="url", url="https://example.com/article")
```

NotebookLM 側で本文抽出される。SPA で本文が取れないケースは事前に PDF にして渡す方が安定。
ログイン必須ページ（社内 Wiki 等）は取得不可。

複数 URL を一括追加する場合は `urls=[...]` を使う:

```
source_add(notebook_id, source_type="url", urls=["https://a.example", "https://b.example"])
```

## YouTube

```
source_add(notebook_id, source_type="url", url="https://www.youtube.com/watch?v=...")
```

YouTube URL も `source_type="url"` で渡す。字幕がある動画のみ実用に足る。字幕なしの動画は追加できても Q&A の品質が著しく落ちる。

## Google Drive

```
source_add(notebook_id, source_type="drive", document_id="<Drive ドキュメント ID>", doc_type="doc")
```

Drive は共有リンク URL ではなく `document_id`（Drive のドキュメント ID）を渡す。`doc_type` は `doc` / `slides` / `sheets` / `pdf` から選ぶ。
`nlm login` で使った Google アカウントから参照可能なファイルのみ。

## テキスト（貼り付け）

```
source_add(notebook_id, source_type="text", text="<本文>", title="<表示名>")
```

Web で取得できない断片や、手元のメモをそのまま投入したいときに使う。`title` で表示名を付けられる。

## ローカルファイル（PDF / テキスト / 音声）

```
source_add(notebook_id, source_type="file", file_path="/path/to/file.pdf")
```

ローカルパスは `source_type="file"` + `file_path` で直接アップロードできる（PDF・テキスト・音声に対応）。Drive 経由の回避策は不要。

## 同期完了を待つ

追加後すぐに Q&A したい場合は `wait=true` を付けるとソース処理完了までブロックする（`wait_timeout` 秒で上限、既定 120 秒）。

## トラブル時のフォールバック

source_add がエラーを返した場合は以下を確認：

- `source_type` と渡した引数の組み合わせが正しいか（url に file_path を渡していないか等）
- URL が認証必須ページではないか
- YouTube 動画に字幕があるか
- Drive の `document_id` / `doc_type` が正しく、共有設定が適切か
- ファイルサイズが NotebookLM の上限（仕様変動するが概ね数百 MB 級）を超えていないか
