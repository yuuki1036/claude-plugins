# ソースタイプ別の挙動

NotebookLM が受け付けるソースタイプと、`source_add` MCP tool に渡す入力形式の対応表。

## URL（一般 Web ページ）

```
source_add(notebook_id, "https://example.com/article")
```

NotebookLM 側で本文抽出される。SPA で本文が取れないケースは事前に PDF にして渡す方が安定。
ログイン必須ページ（社内 Wiki 等）は取得不可。

## YouTube

```
source_add(notebook_id, "https://www.youtube.com/watch?v=...")
```

字幕がある動画のみ実用に足る。字幕なしの動画は追加できても Q&A の品質が著しく落ちる。

## Google Drive

```
source_add(notebook_id, "https://drive.google.com/file/d/.../view")
```

`nlm login` で使った Google アカウントから参照可能なファイルのみ。共有リンクの権限を「リンクを知っている全員」にすれば確実。

## PDF（ローカルファイル）

`source_add` がローカルパス入力をサポートしているかは jacob-bd 実装の挙動次第。サポートしていない場合は次の手順で代替する：

1. 対象 PDF を Google Drive にアップロード
2. 共有設定を「リンクを知っている全員」に変更
3. 共有 URL を `source_add` に渡す

## トラブル時のフォールバック

source_add がエラーを返した場合は以下を確認：

- URL が認証必須ページではないか
- YouTube 動画に字幕があるか
- Drive ファイルの共有設定が適切か
- ファイルサイズが NotebookLM の上限（仕様変動するが概ね数百 MB 級）を超えていないか
