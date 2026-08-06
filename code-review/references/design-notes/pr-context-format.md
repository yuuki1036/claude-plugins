# PR コンテキストブロックの構造（参考 / 実行時には読まない）

`scripts/fetch-pr-context.sh` の出力フォーマット。実体はファイルに落として reviewer にはパスだけ渡すため（`orchestration-guide.md ## 3.5`）、**オーケストレーターがこの構造を知っている必要はない**。スクリプトを変更するときの参照用に残している。

## 3. PR コンテキストブロックの構造（review Step 2.5 の参考）

`fetch-pr-context.sh` のスクリプト出力の構造（参考。実体はファイルに落とし、reviewer にはパスだけ渡す → `## 3.5`）:

```
## PR コンテキスト

### PR 情報
- #<番号> <タイトル>
- 著者: @<author>
- Base → Head: <base> → <head>
- State: <state>
- URL: <url>

### PR 説明（著者が明示したスコープ・意図）
<body 全文。空なら「（空）」>

### Issue コメント（PR 全体への議論）
- [@user, YYYY-MM-DD] body
- ...

### レビューサマリ
- [@reviewer, STATE, YYYY-MM-DD] body
- ...

### 行単位レビューコメント（過去の指摘）
- [#id] [@reviewer, path:line] body
  - 返信 [#親id への返信] [@user] body
- ...
```

データが無い項目は `fetch-pr-context.sh` が「（なし）」を出力する。

