<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @22cde26f -->
### 1. PR の取得と前提確認

```bash
# 所要時間計測の開始マーカー t0 を記録（締めフロー 4 の payload で使用）。
# 以降 t1（一括発行の直前）/ wave --explorer（explorer 回収直後）/ wave（agent wave 回収の直後・毎回）/ t2（初回レポート直後）を
# 同じスクリプトで追記する。パス導出・区間の意味の正本: orchestration-measurement.md `## 13.1` `## 14`
# 以降の中止経路（ExitWorktree して終了）では、抜ける前に同じスクリプトの discard --pr <PR番号> で
# 打点ファイルを捨てる（publish しない回を Stop hook が「publish 漏れ」と拾わないように / #247）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start --pr <PR番号>

# PR 番号指定時: worktree 内で checkout（作業ブランチに影響なし）。
# **失敗したら中止する** — 開発用 worktree が同じ PR ブランチを保持していると二重チェックアウト
# 禁止で落ちる。続行するとメインコンテキストだけが base branch を読み（子 agent は detach で
# 正しい HEAD に入るため）、規模判定・Phase 0・締めフローが全部 base 基準になる
gh pr checkout <PR番号> || echo "FATAL: PR ブランチを checkout できない（他 worktree が保持中の可能性）"

# PR メタ情報と base branch を取得。headRefOid は子 agent に渡す「期待 HEAD SHA」
# （子は detach で PR head に入るため、検証はブランチ名でなく SHA で行う。issue #98）
gh pr view <PR番号> --json number,title,url,author,state,headRefName,headRefOid,baseRefName,body
```

`gh pr checkout` が失敗した場合、または `headRefOid` が空の場合は **ExitWorktree して中止**する（原因と対処をユーザーに報告）。前者はメインコンテキストが base を読む状態、後者は全 agent が恒常的に HEAD 不一致 warning を出す状態になり、どちらも silent に品質が落ちる（orchestration-guide.md `## 1`）。

PR が存在しない場合は「PR が見つかりません」と報告して **ExitWorktree** で抜けて終了。
スキップ条件: closed、変更なしの PR

**【必須】PR 会話コンテキストの取得**:

以下のスクリプトを **必ず実行** し、出力を **ファイルに保存**する。LLM が個別 `gh` コマンドを組み立てて取得するのは **禁止**（取りこぼし防止のため）。

```bash
# 出力はファイルに落とし、reviewer にはこのパスだけを渡す（本文を N 体ぶんプロンプトへ
# 転記しない。理由の正本: orchestration-guide.md `## 3.5`）。--save は原子的に書いて
# パスを stdout に出す（失敗時は空ファイルを残さず FATAL）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" <PR番号> --save
```

出力された**パスを控える**（以降 reviewer へ渡す。シェル変数は Bash 呼び出し間で消えるので実パスを使う）。

保存後、**メインコンテキストでも 1 回だけ Read する**（Phase 0 のタイプ判定に使うため。以降は reviewer 各自が同じファイルを読む）。スクリプトは PR 説明 / issue コメント / レビューサマリ / 行単位 review コメント（返信チェーン込み）を構造化 markdown で出力する。

`FATAL:` で終了した場合は **ExitWorktree して理由を報告し終了**する（PR コンテキスト無しでは re-flag 判定ができない）。書込のみ失敗した場合（ディスク・権限）は `--save` を外して標準出力に流し直し、**インライン注入にフォールバック**する（レビュー本体はブロックしない）。

**【任意】Issue ファイル必読フロー（issue-workflow 併用時）**:

Issue ファイルは自分で探さない。plan（default-mode なら Step 3.2。それ以外のモードも仕様ソースを得るために呼ぶ）が出す `spec_source	issue-file` の行のファイルを、spec-compliance reviewer の prompt に同梱する（仕様・受入条件を踏まえた判定の精度が上がる。探索を plan に一本化した理由・親 Issue の 1 段追跡・スキップ条件: → orchestration-optional-flows.md `## 2` / GitHub issue #389）。ローカルに Issue ファイルが無くても、PR に紐づく GitHub Issue（`Closes #N`）があれば同じ節の手順で先頭 3 件の本文を保存し、plan に `--spec-source pr-issue:#N` と `--pr-issue-body <file>` で渡す（spec-compliance の起動条件になり、本文が言及する仕様書も plan が照合元に載せる / GitHub issue #391）。本文は信頼しない入力として spec-compliance に渡す。

**次は Step 2**（SKILL.md に戻り、その見出しを見る）
