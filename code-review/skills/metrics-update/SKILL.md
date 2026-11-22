---
name: metrics-update
description: >
  code-review の計測結果（review:completed の蓄積）を更新し、前回からの差分・比較表・`## 15` の更新条件・語彙落ちを集計して、関連 issue へのコメントと改善案の起票までを固定の手順で回す。投稿・起票は承認を取ってから行う。
  トリガー: 「計測を更新」「計測結果を更新して」「metrics update」「/metrics-update」
  引数: [--split-version <版>]（省略可）
effort: medium
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
---

# metrics-update

code-review が publish する `review:completed` の蓄積を集計し、code-review の開発トラッカー（`yuuki1036/claude-plugins`）の関連 issue に結果を返す。決定的な部分（見た範囲・前回からの差分・比較表・`## 15` の更新条件・語彙落ち）は `scripts/metrics-update.sh` が出す。この skill が決めるのは、どの issue にコメントするか・起票するか・ベースライン doc を書き換えるか、の 3 つだけ。

集計を手で組み直さない。表に無い切り方が要るときは、手で書いた集計で判断せず、スクリプトに足す follow-up を報告に書く（毎回組み直すとフィルタが揃わない / GitHub issue #480）。

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md の 10 原則のうち **採用: 3（段階予算 = `${CLAUDE_EFFORT}` で選定と検証の深さを変える）/ 4（モデルルーティング = 検証 agent は `opus`）/ 7（敵対的独立検証 = xhigh/max で投稿前の本文を独立 agent が照合）/ 8（外部オラクル = 集計はスクリプト）/ 9（構造化受け渡し = `--json`）**。**捨てた**: 1・2（候補の issue は十数件で、絞ると見落とす）/ 5（反復しない単発処理）/ 6（証拠蓄積は failure-journal の役割）/ 10（確信度は判定欄の理由で表す）。

## 絶対厳守ルール

- **公開先への送信は承認の後**。コメントと起票は公開リポジトリへの書き込みで取り消せない（編集しても旧版が履歴に残る）。本文はファイルに書く呼び出しと投稿の呼び出しを分け、その間に AskUserQuestion でプレビューを見せる。起動しただけでは投稿を確定しない
- **計測ストアの中身を公開先に書かない**。貼るのは比較表の数値・retro の「集計」行と「マシン / 版」行・イベントの `ts` まで。語彙落ちの差分（落ちた値そのもの）・`--show-paths` の出力・生のパスは貼らない
- **送信前のガード（guardrail-protect の public-leak-guard）が止めたら迂回しない**。置き換え表を当て直して本文ファイルを書き直す
- **issue の状態を記録から断定しない**。候補は毎回 `gh issue view <N> --json title,body,comments` で本文とコメントを読んでから判定する（CLAUDE.md の Gotchas「記録から現在の状態を断定しない」）

## 実行手順

`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `code-review@…` の `installPath` を使う。以下 `MU` は `bash "${CLAUDE_PLUGIN_ROOT}/scripts/metrics-update.sh"` を指す。

### 0. 計測ストアと main を最新にする

1. 作業ツリーが claude-plugins なら `git fetch origin main` を回す（集計が読む main の commit は `origin/main`。fetch しないと、前回からの commit の差分と `--record` が記録する commit が古いままになる）
2. 計測ストア（`REVIEW_METRICS_DIR`、既定 `~/.claude/review-metrics`。マシン間で合算する private リポジトリの clone）があれば、pull してから、このマシンの分を同期する:

   ```bash
   STORE="${REVIEW_METRICS_DIR:-$HOME/.claude/review-metrics}"
   if [ -d "$STORE/.git" ]; then git -C "$STORE" pull --ff-only; fi
   if [ -x "$STORE/bin/sync" ]; then "$STORE/bin/sync"; fi
   ```

`bin/sync` はこのマシンの分を private のストアへ commit・push する。確認を取らずに回すのは、送り先が利用者自身の private リポジトリで、追記だけの定常の同期だから（行が消える・変わる同期は `bin/sync` 自身が止める）。公開先への送信（Step 5・6）とは扱いを分ける。ストアが無ければ 2 は飛ばす（手元の `events.jsonl` だけで回る）。

**完了基準**: fetch の結果と、ストアの有無・pull・同期の結果（更新した / 最新 / ストアなし / 失敗と理由）を控えた。失敗しても止めず、Step 8 の報告に書く。

### 1. 集計する

作業用の dir を先に作る（本文ファイルと `--json` の出力を置く。毎回新しい名前の 0700 の dir）:

```bash
MU workdir
```

出力の `dir=` のパスを以下 `<dir>` とする（exit 2 なら止めて報告する）。**この後どこで終えても、Step 8 の前に `rm -rf "<dir>"` する**（本文と `--json` には語彙落ちの生の値が入りうる。途中で止めた回も残さない）。

```bash
MU --json [--split-version <版>] > "<dir>/metrics.json"   # 機械可読。判定はこちらで読む
MU --generation <世代> [--split-version <版>]           # 人が読む表（世代は --json の baseline.marker.generation）
```

- 引数に `--split-version` があればそのまま渡す。打ち手の前後を比べたい issue があるときは、その打ち手を入れた版を渡して回し直す（版で切る。日付・直近 N 件では切らない / `orchestration-measurement.md ## 18`）
- exit 2 は判定不能。stderr の理由を出し、`<dir>` を消して終える（集計を手で組み直して先へ進まない）

**完了基準**: 見た範囲（ストアの本数と行数・手元のログ・合算の n・main の commit・版・前回の記録）・前回からの差分・code-review/ の commit・比較表・`## 15` の判定・語彙落ちの件数が手元にある。

### 2. retro を同じ母集団で回す

```bash
MU retro
```

**完了基準**: ⚠️ 行を全件書き出した（0 件なら 0 件と書いた）。「集計」行と「マシン / 版」行を逐語で控えた（Step 5 で本文に付ける）。

### 3. コメント先の候補を決める

候補は次の 2 本で全部出す。`<日付>` は Step 1 の `scope.previous.recorded_at` の日付（前回の記録が無ければ 2 本目は回さず、その旨を報告に書く）:

```bash
gh issue list -R yuuki1036/claude-plugins --state open --search '[code-review] in:title' --json number,title,updatedAt --limit 200
gh issue list -R yuuki1036/claude-plugins --state closed --search '[code-review] in:title closed:>=<日付>' --json number,title,closedAt --limit 200
```

候補ごとに `gh issue view <N> -R yuuki1036/claude-plugins --json title,body,comments` で本文とコメントを読み、「コメントする / しない」と理由 1 行を決める。

- **コメントする**: 本文の着手条件・再監視条件・判定基準が参照する指標を、今回の出力が前回のコメントより多い n か新しい版で測れる（open）/ 打ち手を入れた版で絞った前後比較が出せる（前回以降に close した issue の効果確認）/ ⚠️ 行がその issue の対象を指している
- **しない**: 計測に関わらない / 前回のコメントから n も版も変わっていない / 判定に要る n に届いていない（あと何件かを理由に書く）

`${CLAUDE_EFFORT}` が `low` / `medium` のときは、ここで全候補を読んだうえで、コメントする対象を ⚠️ 行・`## 15` の判定・前回以降に close した issue に関わるものに絞る。`high` 以上は上の基準をそのまま当てる。

**完了基準**: 2 本の出力の全件に判定と理由が付いた（読まずに「しない」にした候補が無い）。

### 4. `## 15` を取り直すか決める

Step 1 の `baseline.due` で分ける:

- `true` で、作業ツリーが claude-plugins（`code-review/references/orchestration-measurement.md` がある）→ `## 15` の表を比較表の値（`--generation <新しい世代>`。新しい世代は `baseline.window_generations` に並ぶ直近 4 回の世代。effort で割った列）で取り直し、節の先頭の `METRICS-BASELINE` の印（世代・`taken`・`review_xhigh_need`）も同時に直す。`taken` は表に入れた最後の回の翌日（UTC の日付。スクリプトは ts の UTC の日付で `taken` 以降を数える）。版上げと CHANGELOG が要ることを報告に書く（コミットは利用者が決める）
- `true` だが作業ツリーが claude-plugins でない → 書き換えず、取り直しの時期であることを報告に書く
- `false` / `null`（印が読めない）→ 書き換えない。`null` なら印の状態（`baseline.marker.status`）を報告に書く

`${CLAUDE_EFFORT}` が `low` / `medium` のときは書き換えず、判定と取り直しに使う表を報告に出すだけにする。

**完了基準**: 書き換えたか、書き換えない理由（時期でない / repo 外 / 印が読めない / effort）が決まった。

### 5. コメントの本文を書き、承認を取って投稿する

入る前に `${CLAUDE_PLUGIN_ROOT}/skills/metrics-update/references/comment-template.md` を Read する（本文の型・置き換え表・貼る行の規則）。

1. Step 3 で「コメントする」にした issue ごとに、置き換え表を当てた後の本文を Write で `<dir>/<N>.md` に書く（このときは投稿しない）
2. `${CLAUDE_EFFORT}` が `xhigh` / `max` なら、プレビューの前に検証 agent を 1 体起動する（下の「投稿前の検証」）
3. issue 1 件ごとに AskUserQuestion を 1 回出す（1 回に問いは 1 つ。プレビューは issue 番号・本文・置き換えた種類と件数）。選択肢は「投稿する / 直す / 投稿しない」。「直す」なら、利用者の指示で本文ファイルを直し（直した内容にも置き換え表を当ててから書く。`xhigh` / `max` なら検証も回し直す）、同じ issue でもう一度出す。この回で直しきれないものが「直して保留」
4. 「投稿する」を選んだものだけ、別の呼び出しで投稿する:

   ```bash
   gh issue comment <N> -R yuuki1036/claude-plugins --body-file "<dir>/<N>.md"
   ```

**完了基準**: 各候補が「投稿した（URL）/ 投稿しない（理由）/ 直して保留」のどれかになった。「直して保留」の本文は作業用 dir と一緒に消えるので、保留した理由と直す点を Step 8 の報告に残す（次の回で書き直す）。

### 6. 改善案を起票するか決める

既存の issue（open と、前回以降に close したもの）に載らない改善案があるときだけ扱う。候補は ⚠️ 行・比較表で前回から崩れた層・語彙落ちのうち code-review 側で直すもの（publish が足したキーを `## 16` の表に載せ忘れた等）。計測ストア側の語彙の追加は、そのリポジトリの作業として報告に書く（ここでは起票しない）。

起票するときは Step 5 と同じ流れ（**タイトルと本文の両方**に置き換え表を当て、本文を `<dir>/new-<連番>.md` に、タイトルの要約（`[code-review] ` を除いた部分だけ）を `<dir>/new-<連番>.title` に Write → `${CLAUDE_EFFORT}` が `xhigh` / `max` なら検証（タイトルのファイルも渡す）→ AskUserQuestion（プレビューにタイトルも出す）→ 別の呼び出しで投稿）で、投稿は次の形にする。`<要約>` には投稿の直前に `.title` を Read した中身を一字一句そのまま写す（会話から書き起こさない）:

```bash
gh issue create -R yuuki1036/claude-plugins --title '[code-review] <要約>' --body-file "<dir>/new-<連番>.md"
```

`${CLAUDE_EFFORT}` が `low` / `medium` のときは、⚠️ 行が既存の issue に対応しないときだけ起票を検討する。

**完了基準**: 案ごとに「起票した（URL）/ 起票しない（理由）/ 案なし」が決まった。

### 7. 今回の実行を記録する

```bash
MU --record
```

投稿も起票もしなかった回も記録する（「ここまで見た」の記録なので）。記録は次回の Step 1 の差分の起点と、Step 3 の 2 本目の日付になる。記録したら作業用の dir を消す（`rm -rf "<dir>"`。本文と `--json` には語彙落ちの生の値が入りうる）。

**完了基準**: stderr に「記録した」と、記録した main の commit・n・版が出た。作業用の dir を消した。

### 8. 実行後レポート

次を全部書く（利用者が「全部見たか」を聞き直さなくて済むように）:

- **見た範囲**: ストアの有無と本数・行数 / 手元のログ / 合算の n / main の commit / 版 / 前回の記録からの期間 / Step 0 の同期の結果
- **集計の要点**: 前回からの新しい回の件数と内訳 / ⚠️ 行（全件）/ `## 15` の判定と Step 4 で決めたこと / 語彙落ちの件数（値は書かない。手元の表示で確かめるよう添える）
- **issue**: Step 3 の候補の全件（番号・判定・理由）/ 投稿・起票した URL / 投稿しなかったものの理由
- **follow-up**: 表に無い切り方が要った・スクリプトの出力で判定できなかった、など

## 投稿前の検証（xhigh / max のみ）

Agent を 1 体だけ起動する（`model: "opus"`、`effort` は `${CLAUDE_EFFORT}` をそのまま渡す。frontmatter を持たない起動なので spawn に書く）。渡すのは本文ファイルのパス（起票ならタイトルのファイルも）と `<dir>/metrics.json` のパスだけで、選んだ理由（こちらの推論）は渡さない。頼むこと:

- 本文の数値と件数が `--json` の出力にあるか（無い数値を列挙する）
- 置き換え表に当たる語が残っていないか（`comment-template.md` を読ませる）
- 起票案なら、open / closed の既存 issue と重複・既決していないか（`gh issue list --search` で探させる）

結果が届くまで Step 5 の 3 に進まない。指摘された箇所は本文ファイルを直してからプレビューに出す。
