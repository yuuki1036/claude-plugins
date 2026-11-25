### 5. PRを作成

```bash
git push -u origin <current-branch>
gh pr create --draft --title "<title>" --body "<description>" \
  --attach <ATTACH[0]> --attach <ATTACH[1]>   # Step 4.5 / 4.6 で添付がある場合のみ。1 ファイル 1 フラグ
```

リポジトリ規約（Step 1）が draft 以外を指定している場合は `--draft` を外す。**Step 4.95 で提示した種別どおりに実行する**（提示と実作成を食い違わせない）。`--attach` は `--web` / `--dry-run` と併用できない。

作成後は、Step 1 の 4. で取り込んだ「その他」手順のうち作成後に行うもの（ラベル付与・reviewer 割当・PR 分類など）を実行する。

作成後のレポートには URL と、**取り込んだ手順ごとの実行結果**（`実行済み` / `未実行: <理由>`）を出す。repo に PR 分類・リスクラベル手順があるのに実行していなければ、`未実行` の行として必ず書く（黙って省略しない）。

#### `--attach` 付きで exit 非ゼロになった場合

gh は最初のアップロード失敗で止まるが、**それ以前に上がった分を書き込んだうえで PR を作成し、URL を出力してから非ゼロで終わる**ことがある。再実行すると PR が二重にできるので、先に作成済みかを確かめる:

```bash
gh pr view --json url,body -q '.url, .body' 2>/dev/null
```

- PR が無い → 失敗理由を確認し、添付なし（Screenshots 節と「図で見る要点」節を除いた body）で作り直すなら **body が変わるので Step 4.9 → 4.93（ゲート再出力）→ 4.95 をやり直す**
- PR がある → body にローカルパスの参照（アップロードに失敗した分）が残っていないか見る。残っていれば該当行を除いた body を提示し、承認を得てから `gh pr edit --body` で更新する。未添付のファイルはレポートに列挙して手動添付を案内する

#### gh pr create / edit が失敗した場合のフォールバック

`gh pr create` / `gh pr edit` が以下の Projects (classic) 廃止エラーで exit 1 になることがある（Projects classic を使っていないリポでも、gh CLI が PR mutation 時に `projectCards` を取得するため発生する）:

```
GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience ... (repository.pullRequest.projectCards)
```

この場合は github MCP にフォールバックする（GraphQL の `projectCards` field を触らないため deprecation の影響を受けない）:

```
# 新規作成（draft は Step 4.95 で提示した種別に合わせる）
mcp__github__create_pull_request({ owner, repo, head, base, title, body, draft: <4.95 で提示した値> })

# body 更新（承認済み body と同一内容に限る）
mcp__github__update_pull_request({ owner, repo, pullNumber, body })
```

github MCP はファイルをアップロードできない。**`ATTACH` が空でないときは Screenshots 節と「図で見る要点」節を除いた body になり承認内容と変わる**ので、その body を提示して改めて承認を得てから作成し、作成後に `gh pr comment <番号> --attach ...` で画像をコメントとして添付するかを確認する（コメント投稿も外部公開なので承認を取る）。

github MCP も未設定の場合は、**承認済み body で作成できないため PR を作成しない**（Step 4.95 の承認と異なる内容を公開しないため）。承認済みの title / body をチャットに再掲し、ユーザーに手動作成を案内して終了する。どうしても最小 body での作成が必要な場合は、その旨（最小 body で作成し手動更新が必要になること）を提示して**改めて承認を得てから**作成する。gh CLI 側にパッチが入って `projectCards` 取得を回避するようになれば、このフォールバックは不要になる。

**ここで終わり**
