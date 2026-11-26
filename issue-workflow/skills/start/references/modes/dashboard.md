## ダッシュボードモード（BACKEND=local・main/master ブランチ時）

### Phase D1: 全プロジェクトスキャン

1. `{DATA_DIR}/*/project.md` を Glob で列挙する
2. 各プロジェクトの `project.md` を Read で読み込む
3. プロジェクト一覧をサマリー表示する

### Phase D2: アクティブ Issue サマリー

1. `{DATA_DIR}/*/issues/*.md` を Glob でスキャンする
2. 各 Issue ファイルを Read し、`status: in-progress` の Issue をプロジェクト別にリスト表示する
3. 2 の in-progress のうち、放置 Issue（`last_active` フィールドが7日以上前）を警告付きで表示する（放置の定義は maintain・SessionStart hook と同じ in-progress 限定。backlog は放置扱いにしない）
4. `status: backlog` の Issue（discover の自動起票はすべてここに入る）がある**プロジェクトのみ**、件数と `created` が古い順に 3 件を表示する。maintain の件数表を除けば、backlog を表に出すのはここだけなので省かない（出していなかった間、自動起票の Issue が 3 か月近く backlog のまま残っていた実例がある）:
   ```
   **Backlog（未着手）:**
   - {slug}: {N}件
     - {ID} {件名}（{M}日前に起票）
     - ...（残り {X}件）
   ```
   - 経過日数 = 現在日 - frontmatter の `created`
5. `{DATA_DIR}/*/follow-ups/*.md` を Glob で列挙し、各ファイルを Read して frontmatter の `status: open` を抽出する
6. open な follow-up があるプロジェクトのみ、件名・滞留日数付きで表示する（各プロジェクト最新 5 件まで、`created` が古い順に並べる）:
   ```
   **Follow-up:**
   - {slug}: {N}件
     - {件名}（{M}日前）
     - {件名}（{M}日前）
     - ...（残り {X}件）
   ```
   - 件名は frontmatter の `title` または先頭 H1 から取得
   - 滞留日数 = 現在日 - frontmatter の `created`
   - 5 件を超える場合は「...（残り {X}件）」を末尾に表示
7. プロジェクト横断で open な follow-up の合計が 5 件を超える場合は警告を追加表示する:
   ```
   WARNING: open な follow-up が合計 {total}件あります。棚卸しを推奨します。
   `/follow-up list` で一覧、`/follow-up promote` で Issue 化できます。
   ```
8. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/branch-setup.sh" worktrees` を 1 回実行し、出力があれば表示する。1 件ごとに `id=` / `branch=` / `worktree=` の 3 行が並ぶ（メインのチェックアウト・detached HEAD・ディレクトリが消えた worktree と、ブランチ名に Issue ID の無いものはスクリプトが外す）。出力が空・exit が 0 以外なら何も出さない:
   ```
   **worktree で作業中:**
   - {id} `{branch}` — `{worktree}`（`/start {id}` でそこへ移って続ける）
   ```

### Phase D2.5: Knowledge サマリー

1. `{DATA_DIR}/*/knowledge/index.md` を Glob で列挙する
2. 各 index.md を Read で読み込み、プロジェクト別の knowledge 件数を表示する
3. index.md が存在しないプロジェクトは `{DATA_DIR}/*/knowledge/*.md` を Glob でカウントする
4. 表示形式:
   ```
   **Knowledge:**
   - {project}: {件数}件（最新: {直近の knowledge ファイル名}）
   ```
5. knowledge が全プロジェクトで0件の場合はこのセクションをスキップする

### Phase D3: 技術的負債サマリー

1. Phase D2 で読み込んだ Issue のうち、`type: debt` の件数をプロジェクト別に表示する

### Phase D4: 次のアクション提案

以下を状況に応じて提案する:

- 放置 Issue がある場合:
  - 「放置 Issue に対応しませんか？ブランチ: `{type}/{SLUG-N}-{desc}`」
- backlog がある場合:
  - 「古い backlog から着手しますか？（`/start {ID}`。着手すると Phase F3.2 が in-progress に移す）見送るなら `/maintain` で canceled に（二度と取り組まないなら却下記録を残す）」
- 新規タスクを作りたい場合:
  - 「`/issue-create` で新しいタスクを作成」
- メンテナンスが必要な場合:
  - 「`/maintain` でプロジェクト棚卸し」
