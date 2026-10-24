---
id: 20261024-self-review-delta-rereview
title: self-review の再レビューを delta に絞る（--since / --prior-findings）
status: approved
phase: target
last-validated: 2026-10-24
supersedes: []
superseded-by: null
issue: "GitHub issue #313"
spec: null
adrs: ["20261024123203"]
tags: [code-review, self-review, feature-dev, g-v-loop, measurement]
---

# self-review の再レビューを delta に絞る（--since / --prior-findings）

## TL;DR

self-review に `--since=<tree>` と `--prior-findings=<path>` を足し、再レビューで主に見るものを「前回の対象が直ったか」と「delta が新しい欠陥を作っていないか」に絞る。体数は delta の規模で決め、前回の対象の観点は上限の外で必ず起動し、反証は通常のゲートを全指摘に当てる。feature-dev の G-V ループと Phase 6.9 がこれを使い、計測には Step 1 が実際にしたことを `review_scope` として残す。

## 背景 / 課題

- feature-dev の G-V ループの再レビューは、self-review を `--focus` と `--rereview` で呼び直す。観点は絞られるが、見る範囲は base との分岐点から作業ツリーまでの diff 全体のままになる。#310 の実測（core 12 ファイル・effort xhigh）では、3 回目の再レビューが 4 体・sub agent のトークン計 約 835k だった
- #310 の対応（feature-dev 2.25.0）で変えたのは結果の扱いだけ。delta の外の指摘を `deferred` に回すようにしたが、self-review は今も diff 全体を見るので、再レビュー 1 回の費用は変わっていない
- `--focus` を付けるので、反証と skeptic は毎回 `scope` でスキップされる（`code-review/skills/self-review/SKILL.md` の 4.8 / 4.9）。反証の実測では `severity_inflated` が 52% ある（`code-review/references/triage-dynamic-gates.md` の 9 節）。水増しされた BLOCKER がそのまま auto-fix の対象になると、ループが 1 回延びる
- Phase 6.9 には「差分だけを self-review に通すことはできない」とある（`feature-dev/skills/feature-dev/SKILL.md` の Phase 6.9）。レビュー後の小さな変更を確かめるためだけに、diff 全体の self-review を回し直している
- 材料は feature-dev 側に既にある。`scripts/gv-loop.py` は各回の修正前の作業ツリー（`pre_fix_tree`）を、`scripts/review-snapshot.sh` は Phase 6 の後に `save` した tree を持っている

## ゴール / 非ゴール

- **ゴール**:
  - G-V ループの再レビューと Phase 6.9 の確認で、reviewer が主に読む範囲を delta に絞り、体数を delta の規模で決める
  - 前回の対象が直ったかの確認と、delta が持ち込んだ新しい欠陥の検出は落とさない
  - 費用の変化を、計測（payload と retro）で初回・従来の再レビューと分けて比べられるようにする
- **非ゴール**:
  - 利用者が手で頼む「再レビュー」と、Phase 7 の読み合わせ後の self-review は変えない（#300 で「diff 全体を見直す回」と決めた。起点の tree も持たない）
  - review（PR）skill には足さない（PR のレビューは前回の作業ツリーを持たない）
  - G-V ループの auto-fix の閾値・反復の上限・`deferred` の判定（`gv-loop.py` の `DELTA_MARGIN` など）は変えない
  - 未追跡ファイルを self-review の diff に入れる話は扱わない（今も入っておらず、この設計とは別の話）。Phase 6.9 で未追跡の変更を見落とさない手当てだけを feature-dev 側に足す
  - Markdown 推敲の起動判定（`md-prose-lines.sh`）は変えない。予定している呼び出し元はどちらも `--embed` で、推敲はもともと起動しない。`--embed` を付けない呼び出し元が `--since` を使うようになった時点で足す

## 確定した前提

- self-review の diff は「分岐点..HEAD・staged・unstaged」の 3 系統で、未追跡ファイルを含まない（`code-review/scripts/triage-signals.sh` の diff の取得部分）。3 系統の連結なので、同じファイルの hunk が別の版の行番号で並ぶことがある（`code-review/scripts/md-prose-lines.sh` の冒頭のコメント）
- `## files` は 80 件で打ち切られる表示用の節で、全件は内部の `CLASSIFIED` にある（`triage-signals.sh` の `## files` の出力部分）
- `--rereview` の申告は、`invocation.py` が引数を `split()` した完全一致で読む（`code-review/scripts/lib/invocation.py` の `_declares_rereview`）。値を付けた形にすると申告として読まれない
- `--embed` の回は self-review の Step 7 を通らないので、prior-fixes の記録は残らない（`code-review/references/prior-fixes-guide.md` の 2 節）。G-V ループの再レビューには、前回の対象を呼び出し側から渡す必要がある
- prior-fixes の入力形 `[{file, line, focus, title}]` は既にある（`code-review/scripts/lib/prior_fixes.py`）。reviewer が `prior_fixes:` の行を「スコープで絞られても検証済みにしない」読み方も既にある（`code-review/references/prompts/reviewer-common.md` の「前回の指摘への修正」）
- `prior-fixes.sh` は detached HEAD のとき、どのサブコマンドも何も出さずに exit 0 で終わる（`code-review/scripts/prior-fixes.sh` のガード）
- 共通ブロックは reviewer だけでなく skeptic・meta-reviewer・反証にも同じパスで渡る。explorer の確定事実は、skeptic に届くと「findings を渡さない」独立性が崩れるという理由で共通ブロックから外してある（`code-review/references/orchestration-guide.md` の 3.5 節）
- `gv-loop.py` は起点の `start_tree` と各回の `pre_fix_tree` を状態に持つ。auto-fix の対象（`target`）は観点を fingerprint の中にしか持たない。delta の外へ回す判定は `start_tree` からの累積差分と `DELTA_MARGIN`（5 行）で行う（`feature-dev/scripts/gv-loop.py` の `target` / `in_delta` / `cmd_review`）
- `review-snapshot.sh` の tree は一時 index への `add -A` で作るので未追跡ファイルを含み、`check` は `save` した tree を `snapshot=<tree>` の行で出す。feature-dev の Phase 5 は `git add` しない（`feature-dev/skills/feature-dev/SKILL.md` の Phase 5.5）
- feature-dev の Phase 6 Step 4 は「self-review の最終出力（post-loop）」から指摘を列挙し、Phase 6.7 は Phase 6 のレポートの `## コメント推敲提案` の有無で、提案の全件適用と diff 全体の精査を切り替える（`feature-dev/skills/feature-dev/SKILL.md` の Phase 6 Step 4 / Phase 6.7）
- 反証のゲートは high が BLOCKER 60-94 / CRITICAL 80-94、xhigh / max はそれに 95 以上と MAJOR を足す（`triage-dynamic-gates.md` の 9 節）。skeptic は xhigh / max で、high-risk surface を含む回だけ起動する（self-review SKILL.md の 4.8）
- `--focus` の回は規模キャップを掛けず、指定した観点を必ず起動する（self-review SKILL.md の 2.2）。small 帯の上限は reviewer 3 体で、最小保証の 2 体が先に枠を取る（`code-review/references/triage-guide.md` の 6・7 節）
- spec-compliance は focus-signals からではなく、Stage 1 で session-context / Issue / knowledge / `--spec` から起動する（self-review SKILL.md の 2.1）
- Markdown 推敲は `--embed` の回に起動しない（`code-review/references/md-polish-guide.md` の 1 節）
- retro の 2・3 節と 1 体あたり cache_read の表は、`size_tier` を「体数と fleet 時間を決めた帯」として層に使う（`code-review/scripts/review-retro.sh` の 2・3 節 / `orchestration-measurement.md`）。再レビュー（`invocation.rereview`）は主層からは既に外れている（`review-retro.sh` の `is_rereview`）
- 計測ストアは語彙に無いキーを落とす。#296 の `invocation.rereview` は約 10 日落ちた（`code-review/references/orchestration-measurement.md` の計測ストアの節）
- publish は triage-signals.sh が書いた size ファイル（`review_path size`）を読み、機械判定の値を注入している。size ファイルは triage-signals.sh が毎回配る前に消し、publish が成功した回に掃除する（`publish-review-event.sh` / `triage-signals.sh`）
- 既存のテスト `test_re_review_keeps_focus` は、再レビューに `--focus <target の focus 集合>` があることを固定している（`.claude-plugin/scripts/tests/test_feature_dev_scripts.py`）
- 正本の 3.5 節（orchestration-guide）と payload の表（orchestration-measurement の 16 節）は、review / self-review の SKILL.md・orchestration-dynamic-rounds.md・reviewer-prompts.md から SSoT pin で参照されている
- code-review と feature-dev は `<plugin>/evals/` を持たないので、pre-commit の plugin eval の鮮度ゲートは掛からない
- 利用者が 2026-10-24 の会話で確定したこと: delta は self-review が作る / 引数は `--since` と `--prior-findings` の 2 つ / G-V の起点は直前の修正の前 / 観点は delta で選び直す / 反証は通常のゲートで走らせ、範囲では絞らない（design review の後に確定）/ skeptic は delta が surface に当たる回だけ / 計測は Step 1 が実際にしたことを載せる

## 採用案

### 全体像

```
feature-dev G-V ループ（2 回目以降の再レビュー）
  gv-loop.py review ── action=fix ─→ target 行 + since=<pre_fix_tree> + prior_findings=<path>（全回の target の累積）
        │                                      │
        │                           Fix（target だけを直す）
        │                                      │
        └── findings ←── self-review --embed --rereview --since=<tree> --prior-findings=<path> [--spec=...]

feature-dev Phase 6.9
  review-snapshot.sh check ─→ snapshot=<tree> ─→（self-review をもう一度回す）Step 2 の引数 + --since=<tree>
                           └→ 変わったファイルのうち未追跡のものは Phase 7 に「未レビュー」として残す

self-review（--since の回）
  Step 1: triage-signals.sh --base B --since-tree T ─→ diff 全体（従来どおり）+ ## delta（delta の patch・規模・観点・surface・explorer-signals）
                                                       size ファイルに scope_mode= と delta の集計行を書く
          prior-fixes.sh match --extra P            ─→ ## prior-fixes（記録分と渡された分を 1 回で）
  Phase 0: 前回の対象の観点は上限の外。残りの観点と体数を delta で決める
  Step 4:  reviewer は delta の patch を主に、diff 全体を文脈として読む。前回の対象は reviewer にだけインラインで渡す
  4.8 / 4.9: skeptic は delta の surface で判定。反証は通常のゲートを全指摘に当てる
  6.4: publish が size ファイルから review_scope を注入
```

### 引数の契約（code-review の self-review）

| 引数 | 値 | 意味 |
|---|---|---|
| `--since=<tree>` | tree の ID（40〜64 桁の 16 進。`=` でつないで 1 語） | delta = 起点の tree と作業ツリーの差分（追跡済みのファイルだけ）を、diff 全体に入るファイルに限ったもの |
| `--prior-findings=<path>` | JSON 配列 `[{file, line, focus, title}]` | 前回の対象。形は `prior-fixes.sh record` の stdin と同じで、正本は `prior-fixes-guide.md` に置く。各行を `## prior-fixes` と同じ扱いで reviewer に渡す |

- `--rereview` とは独立した引数にする。G-V ループは `--rereview` と合わせて 3 つ、Phase 6.9 は `--since` だけを渡す
- 利用者向けの名前は `--since` のまま（確定済み）。同じプラグインの `measure-tokens.sh` / `review-retro.sh` の `--since` は時刻を受けるので、スクリプト側の引数は `--since-tree` にして取り違えないようにする。`--prior-findings` で受けた行は、内部では従来の `prior_fixes` の枠に載せる
- `--since` の値が 16 進でない・`git cat-file -e <tree>^{tree}` が失敗するときは WARN を出し、diff 全体で続ける（`mode: full`）。git には `--end-of-options` で区切って渡す
- `--prior-findings` のファイルが読めない・形が違うときは WARN を出し、`--since` も無視して diff 全体で続ける（前回の対象なしで delta だけを見ると、修正が対象の行に触れなかった回に、直っていない指摘を誰も見ない）
- `--staged` と一緒に渡されたら `--since` を無視する（staged の diff と作業ツリーとの差分は起点が揃わない）。`## delta` に `scope_mode=full` を書く
- `--focus` / `--exclude` と一緒に渡されたとき:

| 項目 | 扱い |
|---|---|
| 読む範囲 | delta（`--since` は効く） |
| 体数 | 指定した観点は規模キャップの外で必ず起動する（従来の `--focus` と同じ） |
| skeptic / 反証 | `scope` でスキップする（従来どおり） |
| `review_scope.mode` | `delta` |

### self-review の流れ（`--since` の回）

1. **Step 1**:
   - `triage-signals.sh` に `--since-tree <tree>` を足す。分類 → size → signals の処理を、diff ファイルと numstat を引数に取る関数にまとめ、diff 全体と delta で 2 回呼ぶ。副作用のファイル（size・corelist）は diff 全体の回だけが書く
   - 従来の出力に加えて `## delta` の節を出す: `delta_file=`（delta の patch のパス。`review_path delta`）/ `delta_files=` / `delta_lines=` / `delta_size_tier=`（diff 全体と同じ帯の関数を通す）/ delta に対する focus-signals・surface・explorer-signals
   - delta は、打ち切り前の全パス（`CLASSIFIED`）に入るファイルに限る。両側を `--no-renames` で取り、パスを揃える（tree に入っていて今は未追跡のファイルが、削除に見えるのを除く）
   - size ファイルに `scope_mode=delta|full` と `delta_lines=` / `delta_size_tier=` の行を足す。`--since` の無い回も `scope_mode=full` を書く（mode をファイルの有無ではなく中身で持つ）。delta の patch は、size と同じく引数に関わらず毎回、配る前に消す
   - `prior-fixes.sh match` に `--extra <path>` を足し、記録分と `--prior-findings` の分を 1 回の呼び出しで合わせて `## prior-fixes` に出す（同じ `file:line:focus` は 1 行にする）。`--extra` の分は detached HEAD のガードより前で読み、detached HEAD でも出す
2. **Phase 0**:
   - Stage 1 の型判定（spec-compliance・explorer の要否など）は従来どおり行う。`--spec` があれば spec-compliance は起動する
   - 前回の対象の観点は、`--focus` と同じく規模キャップの外に置き、専任の reviewer を必ず起動する
   - 残りの観点（delta の focus-signals で立つ観点・最小保証の 2 体）と explorer の体数に、effort の上限と `delta_size_tier` の規模キャップの小さい方を掛ける
   - run の中のゲート（meta-reviewer の size-tier・Round 2 の圧縮）は delta の帯で判定する。payload の `size_tier` は diff 全体の帯のままにし、delta の帯は `review_scope.delta_size_tier` に載せる
3. **Step 4**:
   - 共通ブロックに `delta_file=` を入れる。reviewer-common に「delta の patch が主な対象で、diff 全体は delta を読むための文脈」の節を足す（範囲の印は付けさせない）
   - `prior_fixes:` は共通ブロックから外し、reviewer にだけインラインで渡す（explorer の確定事実と同じ扱い）。#298 の経路も同じに変える。共通ブロックは skeptic にも届くので、前回の指摘を入れると skeptic の独立性が崩れる
   - meta-reviewer は従来どおり全 findings と diff 全体を見る（もともと非独立の層）
4. **4.8 skeptic**: surface の判定を delta に当てる。delta が surface に当たり、effort が xhigh / max のときだけ、`$DIFF_FILE` に `delta_file` を渡して冷や読みさせる（`recall-skeptic.md` は変えない）。reviewer の `[surface:high-risk]` による fallback の起動も、そのフラグが delta の hunk を指すときに限る
5. **4.9 反証**: `--since` の回は `scope` のスキップ条件に入れない（`--focus` / `--exclude` が無い限り）。effort ごとの通常のゲートを、範囲で絞らず全指摘に当てる。gv-loop.py がループに入れうる指摘は、すべて反証を通る
6. **delta が空のとき**（`delta_files=0`）: 前回の対象があれば、その観点の reviewer で直ったかを確かめる。どちらも無ければ指摘 0 件で終える。`--embed` の回は `findings: []` の FINDINGS_JSON と marker を出し、通常どおり publish する（`mode: delta`・0 件。discard しない）
7. **Step 6 のレポート**: 冒頭に `範囲: delta（N ファイル・M 行 / 起点 <tree の先頭 8 桁>）` の 1 行を出す。diff 全体に戻した回は `範囲: diff 全体（<戻した理由>）`

### feature-dev

- `gv-loop.py`:
  - `target` に `focus` を持たせる
  - `review` が `action=fix` / `action=ask` を返すとき、`since=<pre_fix_tree>` と `prior_findings=<path>` も出す。後者は全回の target を fingerprint で重複を除いて累積し、`[{file, line, focus, title}]` で書いたファイル（直前の回だけにすると、後の修正が先の修正を戻したときに見落とす）
  - ファイルは空白を含まない一時ディレクトリ（`TMPDIR`、無ければ `/tmp`）に書く。パスに空白が入る・書けない回と、`pre_fix_tree` が取れない回は `since=unavailable` を出す。feature-dev はそのとき `--since` も `--prior-findings` も付けずに呼ぶ（diff 全体を見る）
- `references/review-loop.md`: Step 3.2 の 5. の再レビューの引数を `--embed --rereview --since=<since> --prior-findings=<prior_findings>` にする（`--spec=` は従来どおり）。`--focus` / `--exclude` は付けない。71 行付近の「再レビューは diff 全体を見直す」の記述も書き換える
- `skills/feature-dev/SKILL.md`:
  - Phase 6 Step 2 の「`--focus` を使うのは Step 3 の G-V ループの再レビューだけ」を書き換える（どこでも `--focus` を付けなくなる）
  - Phase 6 Step 4 は、Phase 6 Step 2 の初回のレポートとループの最後の再レビューのレポートを合わせて読む。同じ fingerprint は後の回の判定を使う（delta 中心の最後の出力だけを読むと、初回で出た delta の外の指摘が落ちる）
  - Phase 6.7 は、G-V ループが走った回は `--embed` 単独（diff 全体の精査）で呼ぶ。走らなかった回は従来どおり初回のレポートの `## コメント推敲提案` を使う
  - Phase 6.9 の「self-review をもう一度回す」は、Step 2 の引数に `--since=<check が出した snapshot>` を足す。「差分だけを self-review に通すことはできない」の行は消す。推奨の決め方（#304）は変えない
  - Phase 6.9 は `check` が数えたファイルのうち、未追跡のもの（`git ls-files --others --exclude-standard`）を数え、Phase 7 の「レビュー後の変更」に「未追跡 N ファイル（self-review の対象外）」として残す
  - self-review のレポート冒頭に `範囲:` の行が無ければ（code-review が旧版）、Step 4 に「code-review が旧版のため diff 全体で再レビューした」と出す
- `references/triage-guide.md` の「`--focus` を使うのは G-V ループの再レビューだけ」（128 行付近）と「再レビューは diff 全体を見直すので」（215 行付近）、`README.md` の同じ趣旨の行も書き換える

### 計測（code-review）

- `publish-review-event.sh`: size ファイルの `scope_mode=` / `delta_lines=` / `delta_size_tier=` から `review_scope: {schema: 1, mode: "delta"|"full", delta_lines, delta_size_tier}` を注入する（SKILL からは渡さない。呼び出し側が書いた値は `severity_threshold_source` と同じく捨てる）。`delta_lines` と `delta_size_tier` は `mode: delta` のときだけ載せる。掃除の対象に delta の patch を足す
- `orchestration-measurement.md` の payload の表に `review_scope` の行を足す。計測ストアの `vocab/` にも同時に足し、publish したマシンで `bin/sync --refresh` を回す
- `review-retro.sh`:
  - 主層から外す述語を `is_rereview(p) or review_scope.mode == "delta"` にする。G-V ループの回は既に外れているので、新しく外れるのは Phase 6.9 の delta の回。こちらは層タグ `（delta）` を付ける
  - 再レビューの費用を「再レビュー・delta」と「再レビュー・全体」に分け、`tokens.sub_*` の中央値を並べる（新しい「再レビューの費用」の表）。反証・skeptic の分を reviewer の分と分ける集計は別の作業にした（「実装で決めたこと」）。基準の約 835k は反証・skeptic を含まない値なので、比べるときはこの差を念頭に置く
  - `size_tier` で層別する表（2 節の fleet・体数、3 節の相関、1 体あたり cache_read・往復の分布）からは `mode: delta` の回を外す
  - delta の回の反証の価値率は、主層の価値率に混ぜない
  - `review_scope` を持たない回（実装より前）は `full` として読む

### 変更対象ファイル

- code-review:
  - `skills/self-review/SKILL.md` / `commands/self-review.md`（description・argument-hint・引数ごとの本文）/ `README.md`（引数一覧）
  - `scripts/triage-signals.sh` / `scripts/prior-fixes.sh` / `scripts/lib/prior_fixes.py` / `scripts/lib/review-paths.sh`（`delta` の種別）/ `scripts/publish-review-event.sh` / `scripts/review-retro.sh`
  - `references/triage-guide.md` / `references/triage-dynamic-gates.md`（8.5 / 9 節）/ `references/orchestration-guide.md`（3.5 の共通ブロック）/ `references/orchestration-dynamic-rounds.md`（9 / 10 節）/ `references/orchestration-optional-flows.md`（15 節の embed の戻り値）/ `references/orchestration-measurement.md` / `references/prior-fixes-guide.md`（`--prior-findings` の形の正本・22 行の G-V ループの記述）/ `references/prompts/reviewer-common.md`
  - SSoT pin の打ち直しで触るファイル: `skills/review/SKILL.md` / `skills/self-review/SKILL.md` / `references/orchestration-dynamic-rounds.md` / `references/reviewer-prompts.md`
  - `CHANGELOG.md` / `.claude-plugin/plugin.json`
- feature-dev: `scripts/gv-loop.py` / `references/review-loop.md` / `references/triage-guide.md` / `skills/feature-dev/SKILL.md`（Phase 6 Step 2・Step 4・6.7・6.9）/ `README.md` / `CHANGELOG.md` / `.claude-plugin/plugin.json`
- テスト: `.claude-plugin/scripts/tests/` の code-review / feature-dev のスクリプトのテスト（`test_re_review_keeps_focus` の書き換えを含む）
- 計測ストアの `vocab/`（このリポジトリの外）

### 版の組み合わせ

- 新しい feature-dev と古い code-review: 古い self-review は `--since=` / `--prior-findings=` を知らず、`--focus` も来ないので、diff 全体をフル構成で見る。見落としは増えないが、費用は今より増える。feature-dev は self-review のレポートに `範囲:` の行が無いことで旧版を見分け、Step 4 に出す。CHANGELOG にも、code-review の対応版と合わせて更新する旨を書く
- 古い feature-dev と新しい code-review: 引数が来ないので、従来と同じ動きになる
- `--prior-findings` の形を変えるときは、code-review と feature-dev を合わせて版を上げる

## 検討した代替案

| 観点 | 案 A（採用）: self-review が `--since` で delta を作る | 案 B: feature-dev が patch を作って渡す | 案 C: code-review は変えず、`--focus` と共通ブロックの指示で「前回以降」に絞る |
|------|------------|------|------|
| 変更量 | 大（両プラグイン・計測ストアの語彙を含む） | 大（両プラグイン） | 小（feature-dev だけ） |
| delta と diff 全体の揃い | 対象ファイルの集合が揃う（行番号は、delta が作業ツリー基準、diff 全体は 3 系統の連結で版が混ざる） | ずれうる（tree 同士の差分には未追跡ファイルが入る） | 範囲を機械的に持たない |
| 費用 | 体数は delta で決まる。読む範囲は当面は指示による（未解決事項 2） | A と同じ | 体数は観点の数のまま。読む範囲は指示による |
| 前回の修正の見落とし | 前回の対象を検証済みにせず、専任の reviewer で見る | A と同じ | #298 で、前回の修正が「前回以前」に入って検証済みになり、どのレビューにも見られなかった |
| 呼び出し元の広がり | tree があれば使える（Phase 6.9 も） | patch を作れる呼び出し元だけ | ― |

- 案 B を採らない理由: delta と diff 全体で対象ファイルがずれうるうえ、受け取る形（patch と行の範囲）が増える
- 案 C を採らない理由: #298 では、範囲を指示文で絞ったために前回の修正を見落とした。体数も減らない

## 設計判断ログ

- [→ADR候補] self-review の範囲を絞る入力は起点の tree（`--since`）で受け、delta は self-review が diff 全体と同じ取り方で作る。呼び出し側は patch を渡さない（ADR-20261024123203 に切り出し済み）
- [local] 引数は `--since=<tree>` と `--prior-findings=<path>` の 2 つに分ける。Phase 6.9 はファイルを書かずに済み、前回の対象の形は `prior-fixes.sh record` の stdin と揃える
- [local] `--rereview` とは別の引数にする。`invocation.py` の完全一致の申告を変えずに済み、再レビューではない Phase 6.9 でも使える
- [local] G-V ループの起点は直前の修正の前（`pre_fix_tree`）。前回の対象は全回の target の累積で渡すので、先の修正を戻す変更も前回の対象として見る
- [local] 観点は delta で選び直す（delta に立つ観点・最小保証の 2 体）。前回の対象の観点は規模キャップの外で必ず起動し、Stage 1 の型判定（spec-compliance など）も従来どおり行う。G-V ループは `--focus` を付けない
- [local] 規模キャップは delta の core 規模で決める。payload の `size_tier` は diff 全体の帯のまま残し、delta の帯は `review_scope.delta_size_tier` に載せる。`size_tier` で層別する retro の表からは delta の回を外す（体数を決めた帯と payload の帯が食い違うため）
- [local] 反証は `--since` の回も通常のゲートで走らせ、範囲では絞らない（2026-10-24 の design review で変更。delta で絞ると、self-review の delta（直前の修正の前から）と gv-loop の delta（ループの起点から ±5 行）が 2 回目以降ずれ、反証を通らない指摘が auto-fix に入る）。`scope` のスキップは `--focus` / `--exclude` のときだけに残す
- [local] skeptic は、delta が surface に当たり effort が xhigh / max の回だけ、delta だけを冷や読みさせる。fallback の起動もフラグが delta を指すときに限る
- [local] `prior_fixes:` は共通ブロックから外し、reviewer にだけインラインで渡す（共通ブロックは skeptic にも届く）
- [local] 計測には Step 1 が実際にしたことを `review_scope` として載せる。mode は size ファイルの中身（`scope_mode=`）で持ち、書くのは triage-signals.sh だけにする（ファイルの有無で持つと、前の回の残骸で mode が化ける）
- [local] `--prior-findings` が読めないときは `--since` も無視して diff 全体に戻る（前回の対象なしに delta だけを見る経路を作らない）
- [local] delta が空でも前回の対象があれば確かめる。空の回も `--embed` では FINDINGS_JSON を返して publish する
- [local] Phase 6.9 の未追跡の変更は feature-dev 側で数えて Phase 7 に残す（self-review の diff は未追跡を含まないので、code-review 側では見えない）
- [local] Markdown 推敲の起動判定は変えない（呼び出し元はどちらも `--embed` で、推敲は起動しない）

## 実装で決めたこと（2026-10-24 / feature-dev の Phase 4 の delta 提案から）

- **`--prior-findings` の検証は triage-signals.sh が行う**（`prior_fixes.py check`）。読めなければ `fallback=prior-findings-unreadable` で `--since` も無視する。縮退の理由は `pr` / `staged` / `bad-tree-id` / `tree-not-found` / `prior-findings-unreadable` / `delta-diff-failed` の 6 つで、`## delta` の `fallback=` とレポートの `**範囲**:` の行に出る
- **delta を絞るパス集合**は `--no-renames --name-only -z` で取った 3 系統の和集合（`CLASSIFIED` のキーは rename の表記なので使わない）。diff 全体の出力は 1 バイトも変えず、`## delta` はダイジェストの最後に出す（内容シグナルの入力を delta に入れ替えて同じ関数で数える）。delta にも `### red-flags` を出す
- **`## delta` の形**: `scope_mode=` / `since_tree=` / `delta_file=` / `delta_files=` / `delta_lines=`（全クラスの追加と削除の和）/ `delta_core_files=` / `delta_core_lines=` / `delta_size_tier=` と、`### focus-signals` / `### red-flags` / `### surface` / `### explorer-signals`
- **size ファイル**に `scope_mode=`（`--since` の無い回も `full`）と、delta の回だけ `delta_lines=` / `delta_size_tier=` を書く。size ファイルと delta の patch は diff の取得より前に毎回消す
- **`prior-fixes.sh match --extra <path>`** で記録分と渡された分を 1 回で出す（ヘッダは `recorded= extra= in_diff=`）。渡された分は detached HEAD でも出し、記録にも書かない
- **`review_scope` は `{schema, mode, delta_lines, delta_size_tier}`**（`delta_files` と `prior_findings` は読む側が無いので載せない）。`SCHEMA_MARKERS` には入れない
- **retro**: 主層から外す述語は「再レビュー ∨ delta」。再レビューの delta の回は `（再レビュー）` に入り、再レビューでない delta の回が `（delta）` になる。既存の `（再レビュー）` の行は割らず、費用は新しい「再レビューの費用」の表で種別（初回 / 再レビュー・全体 / 再レビュー・delta / delta）ごとに並べる。反証などの価値率の分母からは、再レビューと delta の回をどちらも外す
- **反証・skeptic の分を reviewer の分と分けるトークンの集計は入れなかった**（`tokens` に役割別の内訳が無く、`measure-tokens.sh` が subagent の役割を見分ける必要がある。transcript の構造を先に確かめる別の作業にする）。「再レビューの費用」の表は sub の合計で比べ、未解決事項 1 の判定は合計の比較から始める
- **gv-loop.py の `deferred` を回をまたいで残す**（判定式と `DELTA_MARGIN` は変えない）。delta を主に見る再レビューは前の回の deferred を出し直さず、上書きすると Step 4 から消えて `success` で止まりえた
- **`prior_findings` の置き場所**は `$TMPDIR/feature-dev-<uid>/gv-prior-findings-<run_id>.json`（0700 のディレクトリ）。パスに空白が入る・書けない回は `since=unavailable`
- **Phase 6.9 の未追跡の変更**は `review-snapshot.sh check` の `untracked_files=` で数える（numstat のパスは rename の表記を含みうるので、名前は `-z` で取り直して `git ls-files --others` と突き合わせる）
- **self-review の description（router が読む）は変えない**。`--rereview` / `--spec` と同じく呼び出し元だけが使う引数なので、argument-hint と本文だけに書く（モデルが推して足す誘因も減り、スキル選択の evals も要らない）
- **feature-dev の Step 4** は初回と各回の再レビューのレポートを全部読む（途中の回の指摘も落とさない）。**Phase 6.7** は `gv-loop.py summary` の `iterations` が 1 以上の回に diff 全体を精査する

### self-review で見直したこと（2026-10-24 / 実装の self-review の指摘から）

上の決定のうち、次の 6 つは実装の self-review の指摘を受けて変えた。

- **delta の対象のファイルを広げた**（「delta を diff 全体に入るファイルに限る」を変更）。起点の tree から変わったファイルも足す。修正が base の状態へ戻したファイルは diff 全体から外れ、delta からも落ちていた（戻したことで壊れた呼び出し側を誰も見ないまま 0 件で終わる / 反証が使い捨て repo で再現）。tree にあって今は未追跡のファイルは、消えたファイルと分けて除く。`--prior-findings` の分も diff で絞らない
- **git はすべて repo のルートで回す**（`-C "$WT"`）。`--name-only` はルート相対で出るのに pathspec は cwd 相対で読まれ、サブディレクトリから起動すると delta が黙って空になっていた
- **Phase 6.9 も `--prior-findings` を渡す**（「Phase 6.9 は `--since` だけを渡す」を変更）。6.9 の差分の主な中身は Step 4 で直すと決めた指摘への修正で、前回の対象なしに delta だけを見ると、`prior-findings-unreadable` の縮退が防いでいる状態がそのまま起きる。`gv-loop.py prior-findings` がループの remaining / deferred と直すと決めた指摘を書く。書けなければ `--since` も付けない
- **`prior_fixes:` は specialist にも渡す**（「reviewer にだけ」を変更）。G-V ループの auto-fix 対象で多いのは specialist の BLOCKER で、その修正を確かめるのは同じ specialist。前回の対象のキーが `recall-skeptic` / `meta` / 語彙外なら reviewer-bugs に充てる。前回の対象の専任 reviewer は effort 上限の内側で起動する
- **gv-loop の `deferred` は直前の修正で動いた行へ写してから突き合わせる**。fingerprint は行番号を含むので、写さないと同じ指摘が 2 件並んだ。`regression` は前の回すべての対象と突き合わせる（再レビューに全回の対象を渡す理由と揃える）
- **`prior_findings` の置き場所は自分専用の dir に限る**（symlink・他人の持ち物・グループや他人が読み書きできる dir には書かない。ファイルは 0600）。TMPDIR が無い環境は共有の /tmp に落ち、先に作られた dir に書くと指摘の読み取りと reviewer への注入が成立した。ループを止めたときと、次の `init` で消す
- **3 回目の self-review の後に足したこと**: ループの状態は作業ツリーに残り続け、init を呼ばない run（low effort など）では前の run のものになるので、`prior-findings` は `--with-loop` を付けたとき（今回の run で Step 3 が走った回）だけループの分を足す。同じ指摘の判定は「写した後の行が同じ、または行が近くて要旨も同じ」にした（近いだけだと、同じ観点で近くに出た別の指摘で deferred を捨てた）。findings の `file` は制御文字を通さない（gv-loop・prior_fixes の両方。1 行 1 項目の出力に偽の行を差し込めた）。self-review Step 1 は値をシングルクォートで埋める

## 未解決事項 (open)

1. **費用が減ったと判定する基準と、戻す条件**: (a) 「#310 と同じ規模で sub のトークンが N% 以下」の閾値を置く — Pros: 完了条件が明確 / Cons: 基準の約 835k は計測 1 件だけ (b) 閾値を置かず、retro の「delta / 全体」の並びで判断する — Pros: 実測が溜まるのを待てる / Cons: いつ完了かが曖昧になる。現時点では (b) が有力（1 件の値から閾値を決めると根拠が薄い。新しいゲートは対象を測ってから水準を決める、という `docs/rule-placement.md` と同じ理由）。戻す条件は置く: 同じ帯で delta の回の `tokens.sub_*` の中央値が、従来の再レビュー（`--focus`・diff 全体）を下回らなければ、反証のゲートか `--since` の運用を見直す。基準の約 835k は反証・skeptic を含まないので、合計で上回ったときは、まず反証・skeptic の分を分けて測る（その集計は別の作業）。反証の直列 wave が増える分、1 回あたりの壁時計は伸びうる（xhigh の反証 wave は実測 6〜15 分 / `triage-dynamic-gates.md` の 9 節）。確定タイミング: 実装後、#310 と同じ規模の再レビューを 3 回以上計測した時点
2. **reviewer が delta の外まで読んで費用が下がらないおそれ**: (a) reviewer-common の指示だけで絞る — Pros: 単純 / Cons: 守られないと読む量が減らない (b) diff 全体のパスを共通ブロックに入れず、delta の外は必要なときだけ `diff-slice.sh` で取らせる — Pros: 読む量が確実に減る / Cons: 文脈が足りず偽陽性が増えうる。現時点では (a) で始める（文脈を削る副作用の方が見積もりにくい）。あわせて、diff 全体から作る共通ブロックの材料（`past_reviews_file`・explorer-signals）も読む量を押し上げうるので、delta に絞るかを同じ計測で見る。確定タイミング: delta の回を 3 回以上計測して、sub の `cache_read` が下がっていなければ (b) に切り替える

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（次の順に進める）:
   1. code-review: `--since` / `--prior-findings` の受け口とテスト。`triage-signals.sh`（関数化と `## delta`・size ファイルへの集計行）・`prior-fixes.sh match --extra`・`review-paths.sh`・SKILL.md（Phase 0・Step 4 の `prior_fixes` のインライン化・4.8 / 4.9・空の delta）・commands・README・triage-guide / triage-dynamic-gates・orchestration-guide の 3.5 / orchestration-dynamic-rounds / orchestration-optional-flows・prior-fixes-guide・reviewer-common
   2. code-review: 計測とテスト。publish の `review_scope`・orchestration-measurement.md・`review-retro.sh`・計測ストアの `vocab/`。1. と 2. は同じ code-review の版で出す（1. だけの版で Phase 6.9 を回すと、delta の回が主層に混ざる）。計測ストアの `vocab/` は、publish が `review_scope` を出し始めるより先に足す（後から足すと、それまでの計測が同期で落ちる）
   3. feature-dev: `gv-loop.py` の `since` / `prior_findings`（累積・置き場所）・review-loop.md・triage-guide・README・SKILL.md（Phase 6 Step 2・Step 4・6.7・6.9）とテスト。1. の引数が無いと意味を持たないので最後にする
   - 各プラグインで `bump-version.sh` を回した後に `validate_plugin_quality.py --update-ssot-pins` で pin を打ち直し、review/SKILL.md・self-review/SKILL.md・orchestration-dynamic-rounds.md・reviewer-prompts.md に伝わったかを確かめる（vNEXT の解決で digest が動くので、順番は bump の後）
   - 起動: `/feature-dev self-review の再レビューを delta に絞る（GitHub issue #313） design=.claude/designs/20261024-self-review-delta-rereview.md`。1 回で重ければ 1〜3 を別の作業に分ける
2. **検証方法**:
   - CLI テスト（`.claude-plugin/scripts/tests/`）:
     - `triage-signals.sh --since-tree`: delta を打ち切り前の全パスに限る（81 ファイル以上の diff）/ リネームしたファイルのパスが揃う / tree にあって今は未追跡のファイルを削除に数えない / 16 進でない値・引けない tree で WARN を出して diff 全体に戻る / delta が空 / `--staged` と一緒なら `scope_mode=full` / `--since-tree` なしでも `scope_mode=full` を書き、前の回の delta の patch を消す / `delta_size_tier` の帯の境界が diff 全体の帯と同じ関数で決まる
     - `prior-fixes.sh match --extra`: 形の検査 / 記録分と同じ `file:line:focus` は 1 行にする / detached HEAD でも `--extra` の分を出す
     - `gv-loop.py review`: `fix` / `ask` で `since` と `prior_findings` を出し、`stop` では出さない / `pre_fix_tree` が無い・パスに空白が入る回は `since=unavailable` / ファイルに `focus` が入り、全回の target が重複なく累積される
     - publish: size ファイルの `scope_mode=` から `review_scope` を入れる / 前の回の delta の size ファイルが残っていても、`--since` なしの回は `mode: full` / 呼び出し側が書いた `review_scope` を捨てる
     - `review-retro.sh`: delta の回を主層と `size_tier` の層の表から外す / 再レビューの費用の表が種別（初回 / 再レビュー・全体 / 再レビュー・delta / delta）で分かれる / 再レビューと delta の回が価値率の分母から外れる
   - 手順書: `test_re_review_keeps_focus` を、再レビューの引数が `--since` / `--prior-findings` を含み `--focus` を含まない、という表明に書き換える。feature-dev の手順書を通すテスト（3b3aed7 で足した型）に、Step 4 が初回と最後のレポートを合わせて読むこと、Phase 6.7 が G-V ループの後に全体の精査に倒すことを足す
   - 変異テスト: `python3 .claude-plugin/scripts/mutation-test.py` で、追加した分岐の変異が生き残らないこと
   - 実機: core 10 ファイル以上・effort xhigh の feature-dev で G-V ループを回し、次を確かめる。再レビューの payload に `review_scope.mode: delta` が載る / 反証が `scope` でスキップされていない / 前回の対象の観点に専任の reviewer が付く / skeptic に前回の指摘が渡っていない（Agent の prompt で確認）。「再レビューの費用」の表の `tokens.sub_*` を #310 の約 835k と並べる
   - CI: push の後に `validate.yml` の結果を見るまで完了にしない
3. **実装完了時の doc 更新手順**:
   - frontmatter の `phase: target` → `current`、`last-validated` を更新する
   - 実装で決め直した点（`## delta` の出力・size ファイルの行の形など）を追記する。引数の契約ごと変わったら supersede する
   - 未解決事項 1・2 の結果を追記する

## 関連

- 関連 Issue: GitHub issue #313（本件）/ #310（G-V ループの収束）/ #298（前回の指摘への修正）/ #300（`--focus` を推測で足さない）/ #296（`--rereview`）/ #283（初回に `--focus` を付けない）/ #276（review-snapshot）/ #304（Phase 6.9 の推奨）
- 関連 spec: なし
- 関連 ADR: ADR-20261024123203（範囲を絞る入力は tree で受ける）
- 関連 design doc: `.claude/designs/20260623-review-adversarial-verify-layer.md`（反証レイヤー）/ `.claude/designs/20260703-code-review-recall-high-risk-surface.md`（冷や読み skeptic）
