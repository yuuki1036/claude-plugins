---
id: 20261102-verification-checklist-gate
title: 動作確認チェックリスト（設計時に作成し、全項目を満たすまで commit させない）
status: draft
phase: target
last-validated: 2026-11-02
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: [20261102225822, 20261102225845, 20261102225906]
tags: [issue-workflow, feature-dev, dev-workflow, ui-verify, verification, hook, gate]
---

# 動作確認チェックリスト（設計時に作成し、全項目を満たすまで commit させない）

## TL;DR

設計の段階で動作確認チェックリスト（Issue ID 単位の JSON）を作り、項目ごとに確認の手段（e2e / storybook / db-read / unit-test など）を決める。項目の状態と証跡は記録スクリプトだけが書き、UI 項目には chrome-devtools で撮ったスクショ（dev-workflow の撮影台帳に載ったもの）を必須にする。チェックリストがある Issue では、issue-workflow の PreToolUse hook が Claude の `git commit` を検査し、未充足なら fail-closed で block する。軽量フロー・feature-dev のどちらで進めても、同じ判定スクリプトを通る。

## 背景 / 課題

- 動作確認の段は既にある（軽量フロー Step 3 / feature-dev Phase 5.5 / GitHub issue #306）。ただ、確かめる内容は ui-verify がその場で diff から列挙する。設計時に決めた「これが確かめられたら完了」とは結び付いていない
- 動作確認を通らずに先へ進む経路が複数ある。`skipped` / `blocked` は理由を報告に残して次の Step へ進み、`fail` も利用者が承知すれば進む（`lightweight-flow.md:65-71`）。読み合わせから戻った回は Step 3 を通らず（`:58`）、Step 3 の後に入った画面の変更は「動作確認を通していない」と報告に書くだけになっている（`:189-190`。feature-dev Phase 7 も同じ）
- スクショが要る回でも chrome-devtools が起動できなければ、Claude Browser などで続けて「証跡なし」で終わる（ADR-20261020221214 の決定 1）。利用者の要望は「UI はスクショ必須。chrome-devtools が使えないから他の手段で確かめた、は認めない」
- 画面以外の確認（unit-test・DB read 等）は、何を実行してどうなったかが Claude の自己申告になる。実行していなくても報告は書ける

## ゴール / 非ゴール

- **ゴール**:
  - 設計がある Issue では、実装前に動作確認チェックリストがあり、各項目の手段が決まっている（作成点の手順で担保する）
  - チェックリストがある Issue では、全項目が満たされるまで Claude の `git commit` が通らない（feature-dev を使うかどうかに関わらない）
  - UI 項目の証跡は、chrome-devtools で撮ったスクショだけを認める
  - 状態と証跡は記録スクリプトが書く。Claude が手で書いた「pass」は通らない
  - 確認した後に関係するファイルが変われば、その項目は確認前の状態に戻る。フローは commit の前に、その項目を確認し直す
- **非ゴール**:
  - **「設計があるのにチェックリストが無い」を hook で止めること（v1）**。作成漏れは作成点の手順（Skill）で防ぐ。hook でこれを止めるには、Issue 本文の見出しの解析・backend 判定の複製・プレースホルダの除外・作成点を通らない経路の救済が付いてくるので、作成漏れの実例が出るまで入れない（design-review で決定。open 4）
  - 設計が無いタスク（typo・設定変更・計画の節が無い bugfix など）へのチェックリストの強制
  - 意図的な偽造の防止。台帳・記録・登録簿は、Bash で直接書けば作れる（秘密を持たない hash では改ざんを防げない）。防ぐのは、手で書いた記録・確認していない pass・他の基盤で撮った画像・チェックリストの消去が「うっかり」通ることまで
  - スクショの内容の正しさの判定。ゲートが見るのは「chrome-devtools で撮った png が、確認後に変わっていないコードの状態で、その項目に記録されているか」まで
  - index と作業ツリーの食い違いの検査。ゲートは作業ツリーだけを見る（理由は 4. 条件 3）。確認済みの作業ツリーを分割コミットで部分的に commit することは認める
  - 利用者自身の commit の制限。hook が掛かるのは Claude の tool 呼び出しだけで、利用者が自分のターミナルで打つ `git commit` は止まらない。これを最後の逃げ道として残す
  - main に直接コミットする運用（Issue ID を持たないブランチ）での強制
  - `git merge`（衝突なし）・`rebase --continue`・`cherry-pick` が作る commit の検査。対象は `git commit`（`--amend` と、衝突を解決して merge を完了する commit を含む）だけ
  - CI での強制。証跡はローカル（`.claude/verification/` は gitignore）にしか無い

## 確定した前提

利用者が確定した要求:

- ゲートは `git commit` の PreToolUse で block する。WIP コミットもできなくなるが、それを受け入れる（grill 1）
- 項目を「対象外」（`waived`）にできるのは、利用者の明示の指示があるときだけ。理由と利用者の発言の引用を必須にし、Claude の判断では waived にしない（grill 2）
- UI 以外の項目は、記録スクリプトを通してコマンドを実行し、結果をスクリプトが書く。gate は hook の中でコマンドを再実行しない（grill 3）
- 構成は案 A（issue-workflow が正本と gate を持つ）（grill 4）。撮影台帳の hook は dev-workflow に置く（下の「プラグイン間依存」）
- UI 項目のスクショは chrome-devtools に限る。使えなければ止めて、環境の修正を利用者に頼む（依頼の原文）
- 条件 6（設計があるのにチェックリストが無い）は v1 に入れない（design-review 後の決定）

コードと規約から自己解決した前提:

- **プラグイン間依存**: dev-workflow（ui-verify）と feature-dev からは、issue-workflow のスクリプトを呼べない（CLAUDE.md「各プラグインは独立して動作すること」）。そこで記録スクリプト・判定スクリプト・ui-paths・書式の正本を `.claude-plugin/lib/` に置き、issue-workflow と feature-dev の `scripts/` へ byte 一致で複製する（前例: `plugin-enabled.sh` の 3 か所への複製。`validate_plugin_quality.py:138-147` の `BYTE_REPLICAS`）。ui-verify 自身は記録しない。どの項目をどの png で撮ったかを出力行で返し、呼び出し元が記録する
- **撮影台帳は dev-workflow に置く**: chrome-devtools MCP は dev-workflow に同梱されている（`dev-workflow/.mcp.json`）。台帳をここに置けば、chrome-devtools が使える環境には必ず台帳がある。台帳はファイルの置き場所の取り決め（shared state）だけで受け渡し、コードの依存にはしない
- **キーは Issue ID**: ブランチ名から `branch-setup.sh:266` と同じ式（`(^|[^A-Za-z0-9])([A-Z]+-[0-9]+)`）で取る。issue-workflow の backend は local / linear だけで、GitHub の Issue 番号から Issue ファイルを引く手段は無いので、GitHub 形式は扱わない。Issue ID を取れないブランチ（main への直接コミット・Issue の無い feature-dev）にはチェックリストを作らず、gate も掛けない
- **置き場はメインのチェックアウトに固定する**: チェックリスト・登録簿・台帳はすべて `<main>/.claude/verification/` に置く。`<main>` は、対象の repo で `git rev-parse --path-format=absolute --git-common-dir` を実行した結果の親 dir。チェックリストは worktree を作る前に作られ（issue-create Phase 6 → Phase 7 / feature-dev Phase 4 → 4.8）、`.claude/verification/` は gitignore なので worktree へは写らない（`branch-setup.md:69`）。Issue ファイルの検出がメイン側へ fallback するのと揃える（`detect-backend.sh:34-41`）。Issue ID がキーなので、worktree が並んでも衝突しない。スクショの png は撮った checkout に置き、記録には絶対パスで残す
- **書式は JSON、スクリプトは python の stdlib**: `checklist-run.py` / `checklist-gate.py`。YAML は stdlib では読めない。ui-paths.sh の `UI_PATH_ERE` は、python が代入行を読んで `re.IGNORECASE` で照合する（`grep -iE` と同じ結果になることをテストで固定する）
- **置き場の gitignore**: `.claude/verification/.gitignore`（中身は `*`）は今は ui-verify の初回実行で作られる（`ui-verify/SKILL.md:326`）。チェックリストは ui-verify より先に作られるので、記録スクリプトの `add` も同じ .gitignore を作る
- **画面のファイルの判定は `UI_PATH_ERE` だけ**: `ui-paths.sh:10-13` は `UI_SCRIPT_ERE` を「hook には使わない」と明記している（画面に触れない .ts でも鳴る）。block する gate はなおさら使わない。ui-paths.sh の冒頭の「他所へ複製しない」は、正本を `.claude-plugin/lib/` に移して byte 検査で片方だけの修正を止める形に書き換える
- **hook の fail-closed**: PreToolUse の hook は、exit 2 以外の非ゼロでも timeout でも止めずに通る（`guardrail-protect/README.md:182-186`）。safe-hook.sh の ERR trap と `safe_hook_error` はすべて exit 0 で終わる（`safe-hook.sh:72-90, 145-150`）。commit gate の hook は `public-leak-guard.sh:55-56` と同じく ERR trap を上書きし、safe-hook の縮退を使わない
- hook は matcher / `if:` に単独で依存せず、tool_input で自己判定する（CLAUDE.md Gotchas）
- **既存 ADR との衝突**: ADR-20261020221214 の決定 1 は「スクショが要る回に chrome-devtools が起動できなければ、他の基盤で続けて証跡なし」とする。チェックリストの UI 項目に限り、この fallback を禁止する（新しい ADR で決定 1 の一部を supersede する。ADR 候補 1）。チェックリストが無い回の ui-verify の挙動は変えない

## 採用案

### 全体の流れ

```
設計（issue-design Phase 4 の承認後 / issue-create / 軽量フロー Step 1 / feature-dev Phase 4）
  └─ checklist-run.py add … <main>/.claude/verification/<issue-id>.checklist.json（全項目 pending）
                           と登録簿 .registry.jsonl に Issue ID を追記
実装
動作確認（軽量フロー Step 3 / feature-dev Phase 5.5）
  ├─ ui=true  → ui-verify verify --checklist=<path>       … chrome-devtools のみ・filePath は絶対パス
  │              take_screenshot ─(dev-workflow PostToolUse)→ 撮影台帳に realpath と sha256
  │              ui-verify が UI_VERIFY_CHECKLIST= を返す → 呼び出し元が checklist-run.py record-ui
  ├─ ui=false → Bash: checklist-run.py run <id> -- <target を字面どおり>
  └─ 完了条件: checklist-gate.py が exit 0
self-review / 読み合わせ
commit の直前（新しい段）: checklist-gate.py → 確認前に戻った項目だけ確認し直す（最大 2 往復）
git commit ─(issue-workflow PreToolUse)→ checklist-gate.py → exit 0 以外は hook が exit 2 で block
Issue 完了（軽量フロー Step 8 など）: checklist-run.py close
```

### 1. チェックリストの書式（正本 `.claude-plugin/lib/verification-checklist.md`）

`<main>/.claude/verification/<issue-id>.checklist.json` に置く。トップレベルには shared state の 5 欄（`shared_state_type: verification-checklist` / `producer: [issue-workflow, feature-dev]` / `consumers: [issue-workflow, feature-dev, dev-workflow]` / `schema_version: 1` / `last_updated`）と、`issue` / `branch` / `base`（作成時の起点ブランチ）/ `design`（設計の出典パス）/ `empty_reason`（項目 0 件のときだけ）を持つ。JSON なので frontmatter ではなくキーで持ち、`docs/shared-state.md` に JSON の型として追記する。`items` の 1 件は次の形:

```json
{
  "id": "V1",
  "expect": "ログイン後にダッシュボードの件数カードが 3 枚表示される",
  "means": "e2e",
  "ui": true,
  "target": "/dashboard",
  "paths": null,
  "status": "pending",
  "record": null,
  "history": [],
  "digest": "<定義の欄と record から計算>"
}
```

- `means`: `e2e` | `storybook` | `db-read` | `unit-test` | `api` | `manual`
- `ui: true` になる条件: 手段が `e2e` か `storybook` の項目と、期待が画面に表示される内容の項目。`ui: true` の項目の `means` は `e2e` か `storybook` に限る（`add` が拒否する）
- `target`: e2e は path か URL、storybook は story id、それ以外は実行するコマンド。`db-read` は期待値との照合まで含むコマンドにする（`psql ... | grep -q ...` など）。exit 0 を pass とする
- `paths`（省略可。既定 `null`）: 指紋の対象を狭める glob。`null` なら、`.claude/` と `*.md` を除く変更ファイル全体（`base` との merge-base からの差と未追跡）を対象にする。既定は ui:true でも ui:false でも同じ。画面の内容は API や backend のファイルにも依存するので、ui:true の項目の対象を画面のファイルに絞ると、backend を直しても確認前に戻らない
- `status`: `pending` | `pass` | `fail` | `waived`。`status` と `record` は記録スクリプトだけが書く
- `record`: `{at, fingerprint, evidence}`。`fingerprint` は対象の各ファイルの path → 作業ツリーの内容 hash（`git hash-object`）の表。`evidence` は手段ごとに、png の絶対パスと sha256 / exit code と出力の末尾 40 行（`db-read` と `api` は出力を残さず、出力の hash だけにする。接続情報や秘密が記録に残らないように）/ 利用者の発言の引用
- `history`: `edit` と `reset` の前の定義・記録を残す（報告に before / after を出すため）
- `digest`: 定義の欄（`expect` / `means` / `ui` / `target` / `paths`）と `status` / `record` から計算した hash。手で書き換えた項目を検出する（偽造の防止ではない。非ゴール）
- 項目 0 件のチェックリストは、`add --empty --reason ...` で理由つきの場合だけ作れる

### 2. 作成（作成点の手順で担保する）

「設計がある」の判断は作成点の手順に任せ、hook では判定しない。作成点はどれも「まだ無ければ作る。あれば差分だけ足す」で、項目は `checklist-run.py add`（標準入力に定義の欄の JSON を渡す。`status` / `record` が入っていれば拒否する。ファイルが無ければ作り、登録簿にも追記する）で足す:

| 箇所 | 変更 |
|---|---|
| `issue-design` | Phase 4 で利用者が承認した後に、「完了条件」のうち動作で確かめる条件を項目にし、手段を決めて `add` する（Phase 1 は承認前なので、却下された案の項目が残る）。完了条件の節には、チェックリストへのリンクと項目の一覧（id・期待・手段）を置く。BACKEND=none は Issue ID が無いので作らない |
| `issue-create`（feature / debt） | 計画・対応方針を**実際に書いた**回だけ作る。プレースホルダ（`{…}`）のまま起票した回は作らない（`issue-create/SKILL.md:190`） |
| 軽量フロー Step 1 | 実装前の停止点で、方針・従う規約に加えて、チェックリストの案を出す（target のコマンドを含む）。利用者の返信を受けてから `add` する |
| feature-dev Phase 4 | architect の出力に `Verification Checklist` を足し、採用案が確定したら `add` する（feature-dev 側の複製で）。`Runtime Smoke Test Targets` は、画面になる GET の target を e2e（ui:true）に、それ以外（GET 以外・API・DB の初期化）を `api`（ui:false）に取り込む。足切りの経路（`SKILL.md:44-64`）は Phase 4 を通らないので、停止点で項目の案を出す |

作成時に dev-workflow が無効か入っていないとき（`plugin-enabled.sh dev-workflow` が `0`）に ui:true の項目を作るなら、「この項目を確認するには dev-workflow の chrome-devtools が要る」と利用者に伝える。項目は作り、止めるかどうかは確認の段で決める（3.）。

### 3. 実行

**UI 項目**（ui-verify の変更）:

- `--checklist=<path>` を足す（`--only=<id,...>` で対象を絞れる）。ケースは、チェックリストの `ui: true` で `pending` / `fail` の項目から列挙する（追加のケースを足すのは自由）。各項目について必ず `take_screenshot(filePath=<git toplevel の絶対パス>/.claude/screenshots/verify-<ts>/<id>.png)` を撮る。相対パスは MCP サーバーの cwd 基準で解決されるので使わない（`chrome-devtools-cheatsheet.md:54,331`）
- `--checklist` に `ui: true` の項目があるとき:
  - command 本文の早期終了（`commands/ui-verify.md:59-67`。`UI_IMPACT=no` で SKILL.md を読まずに skipped で終わる）をしない
  - 基盤は chrome-devtools に固定する。起動できない・プロファイルを他のセッションが掴んでいて利用者が止めないと答えた・`HOLDER_SESSION=unknown`・`LOCK=foreign-host` などの回は、pane 系へ落ちずに `UI_VERIFY_RESULT=blocked` と `UI_VERIFY_REASON=devtools-required:<理由>` を返す。`UI_VERIFY_BROWSER=none` は再利用しない（既存の呼び出し元は `none` を手動確認に回す / `lightweight-flow.md:69`、feature-dev `SKILL.md:559-560`）。理由には「自分のブラウザのウィンドウなら閉じて再実行」を含める（`CLAUDE_PID` の無い環境では、自分のブラウザも unknown になる / ADR-20261020221214）
  - `means: storybook` の項目は、Storybook の server を検出し、起動の許可を取ってから（dev server と同じ手順）story を開いて撮る
- 出力の最後に `UI_VERIFY_CHECKLIST=<id>:<pass|fail>:<png の絶対パス>,...` の行を足す

**記録（UI 項目）**: 呼び出し元が `checklist-run.py record-ui <id> <png> <pass|fail>` を呼ぶ。スクリプトは png の realpath と sha256 が台帳にあるかを確かめ、無ければ記録しない。拒否の理由は「png が無い」「台帳ファイルが無い（dev-workflow が無効か旧版）」「台帳に載っていない」「hash が違う」に分けて出す。

**呼び出し元が止める回**（チェックリストに ui:true の項目があるとき。軽量フロー Step 3・feature-dev Phase 5.5・commit 直前の再確認）: 次のどれかなら手動確認に回さずに止め、利用者に環境の修正を頼む。

- `UI_VERIFY_REASON=devtools-required:…`
- `DW=0`（dev-workflow が無効・未導入）
- `UI_VERIFY_CHECKLIST=` の行が出ない（`--checklist` を知らない旧版の dev-workflow）
- record-ui が「台帳ファイルが無い」で拒否した

依頼する内容は、dev-workflow を有効にする・更新する・ブラウザを閉じる。あわせて `issue-workflow/hooks/scripts/check-deps.sh:66` の dev-workflow の説明にも「動作確認チェックリストの UI 項目に要る」と書く。

**撮影台帳**（dev-workflow の PostToolUse hook `screenshot-ledger.sh`）:

- matcher は `mcp__plugin_dev-workflow_chrome-devtools__take_screenshot`。スクリプト内でも tool_name を自己判定する
- `tool_input.filePath` があり、png のある repo の `<main>/.claude/verification/` に `*.checklist.json` が 1 つ以上あるときだけ書く（チェックリストを使わない repo には書かない）
- 書く場所は `<main>/.claude/verification/.screenshot-ledger.jsonl`。1 行に realpath・sha256・時刻を書く
- filePath が相対パスのとき・ファイルが無いときは、書かずに stderr へ理由を出す
- 30 日を超えた行と、ファイルが消えた行は、`checklist-run.py add` / `close` のときに刈る

**UI 以外の項目**: Claude が Bash で `checklist-run.py run <id> -- <target>` を実行する。スクリプトは、`--` 以降が項目の `target` と字面どおり一致するときだけ実行する。一致しなければ拒否する。コマンドが Bash の tool_input にそのまま現れるので、permission の判定と guardrail-protect の PreToolUse hook（`tool_input.command` の文字列を見る / `pre-commit-guard.sh:31-32`）を通る。スクリプトの中で target を間接実行する形にすると、外から見えるのが `run V1` だけになり、どちらの検査も通らなくなる。exit 0 なら pass、それ以外は fail。

**利用者の発言で決める項目**: `checklist-run.py attest <id> --kind manual|waived --quote ... [--reason ...]`。引用が空なら拒否する。`manual` は自動化できない確認（メールの受信など）を pass にするとき、`waived` は対象外にするときに使う。

**項目の修正と状態のリセット**:

- `edit <id>`（標準入力に定義の欄を渡す）: 定義を直し、`status` を `pending` に戻す。前の定義と記録は `history` に残す
- `reset <id>`: 記録を消して `pending` に戻す。手で書き換えて digest が合わなくなった項目は、これで確認し直す
- `remove <id> --quote ...`: 項目を消す。利用者の引用が要る（waived と同じ扱い）
- `edit` と `remove` の before / after は、軽量フロー・feature-dev の報告に必ず出す（target を `true` のような空のコマンドに書き換えても、利用者から見えるようにする）

**書き込みの安全**: 記録スクリプトはすべての書き込みを、lock ファイル（python の `fcntl.flock`）で排他し、tmp に書いてから rename する。rename の前に今のファイルを `.bak` として 1 世代残す（並列の Bash・共有チェックアウトでの更新の消失と、kill による破損を防ぐ）。

**Issue の完了**: `close` でチェックリストを `closed/<issue-id>.checklist.json` へ移し、登録簿に close の行を足す（軽量フロー Step 8・issue-maintain の completed 遷移）。

### 4. ゲート（`checklist-gate.py`。正本は `.claude-plugin/lib/`）

exit 0（緑）/ 1（未充足。理由を項目ごとに出す）/ 2（判定不能。理由と回復の手順を出す）の 3 値。対象の判定と止める条件:

**対象の判定**: 次のどれかに当たれば対象外として exit 0 で黙る。

- commit 先の repo を解決できない（下の hook の項）
- Issue ID を取れないブランチ
- 登録簿にその Issue ID が無い
- 登録簿の最後の行が close

**止める条件**（対象のとき）:

1. `pending` / `fail` の項目がある（`waived` は満たしたものとする）
2. `digest` が合わない項目がある（手で書き換えた記録・定義。回復は `reset <id>`）
3. 指紋が合わない: 項目の対象のファイル（`paths` か既定）について、記録時と今の**作業ツリー**の内容 hash が違う、または対象のファイルの集合が違う → 確認前に戻ったものとして扱う。index は見ない。index も比べると、git-commit-helper の分割コミット（実装とテストを分ける・hunk 単位で stage する / `git-commit-helper/SKILL.md:77-87,103`）の 1 本目が必ず止まるため。この代わりに、確認していない中間の状態を分割コミットの途中で commit することは許す（非ゴール）
4. `ui: true` で `pass` の項目の png が無い、または realpath と sha256 が台帳に無い（`waived` / `manual` の項目には当てない）
5. 誤分類: `base` との merge-base からの差と未追跡のファイルに `UI_PATH_ERE` に当たるものがあるのに、`ui: true` の項目（`waived` を含む）が 0 件
6. 登録簿に Issue ID があり close されていないのに、チェックリストのファイルが無い（Bash で消した経路を止める）

**判定不能（exit 2）**: 対象と分かった後で中身を判定できないとき。

| 状況 | 扱い | 回復の手順（gate の出力に書く） |
|---|---|---|
| JSON が壊れている | block | 同じ dir の `<issue-id>.checklist.json.bak`（記録スクリプトが rename の前に残す 1 世代前）から戻すよう利用者に頼む |
| `schema_version` が gate の知らない値 | block | issue-workflow / feature-dev を更新する（版の食い違い） |
| git の呼び出しに失敗した・`base` が解決できない | block | `base` を確かめる。消えたブランチなら `checklist-run.py rebase-base <ref>` |
| 内部の時間予算（hook の timeout より短い 8 秒）を超えた | block | 対象のファイルが多すぎる。`paths` で絞る |

**commit gate の hook**（issue-workflow の PreToolUse `checklist-commit-gate.sh`）:

- `Bash` の tool_input.command から `git commit` を自己判定する（`--amend` と、merge を完了する commit を含む）
- commit 先の repo を次の順で解決する: command 中の `git -C <dir>`、先頭の `cd <dir> &&`、hook 入力の `cwd`。変数展開を含むなど、字面から解決できないときは対象外として黙る（`branch-drift-guard.sh:27-28` が `-C` を外しているのと違い、こちらは解決できる形を読む。`cd <wt> && git commit` は `branch-setup.md:64` が案内する標準の形なので、読まないと worktree の commit がすべて素通りする）
- safe-hook の `safe_hook_init` で stdin を読んだ後、ERR trap を上書きして exit 2 にする（`public-leak-guard.sh:55-56` と同じ）。gate の exit 1 と 2 を hook の exit 2 と stderr の理由に変換する。hooks.json の timeout は 10 秒。timeout で打ち切られると通ってしまう（PreToolUse の仕様）ので、gate は 8 秒の予算で自分から exit 2 を返す
- block した回は、理由を `.claude/verification/.gate-log.jsonl` に 1 行残す（open 3 の見直しの材料）

**既存の dev-workflow の ui-verify-gate.sh**: 同じ `git commit` の PreToolUse で鳴る。その文言は「`verified-local` を書けば黙る」と案内する（`ui-verify-gate.sh:40`）。今の Issue ID のチェックリストがあるときは、この gate を黙らせる（新しい gate と食い違う案内を出さない）。

**呼び出し元**:

- 軽量フロー Step 3 / feature-dev Phase 5.5 の完了条件。gate が exit 0 を返すまで次の Step へ進まない。チェックリストがある回は、`skipped` / 承知の上の `fail` で先へ進む分岐を無くす
- **commit 直前の再確認（新しい段）**: 軽量フロー Step 6 の前と、feature-dev Phase 7 のコミットの前に gate を回す。条件 3 で確認前に戻った項目・条件 2 で reset した項目だけを、UI なら `ui-verify --checklist --only=<id,...>`、それ以外なら `run` で確認し直す。直してまた戻る往復は 2 回までで、それを超えたら利用者に委ねる（feature-dev の G-V ループと同じ上限）。今のフローは「読み合わせから戻った回は Step 3 を通らない」ので、この段が無いと commit の hook で突然止まる
- issue-workflow の commit gate hook（上）
- feature-dev を単独で使う回（issue-workflow が無効）は、Phase 5.5 の完了条件と commit 直前の再確認だけが掛かり、commit の hook は掛からない

### 変更対象ファイル

| プラグイン | ファイル | 種別 |
|---|---|---|
| repo 共通 | `.claude-plugin/lib/verification-checklist.md`（書式の正本）/ `checklist-run.py` / `checklist-gate.py` / `ui-paths.sh`（dev-workflow から移す正本）/ `validate_plugin_quality.py`（`BYTE_REPLICAS` への登録）/ `docs/shared-state.md`（JSON の型の追記） | 新規・変更 |
| issue-workflow | `scripts/checklist-run.py` / `scripts/checklist-gate.py` / `scripts/lib/ui-paths.sh`（複製） | 新規 |
| issue-workflow | `hooks/scripts/checklist-commit-gate.sh`（PreToolUse）/ `hooks/hooks.json` / `hooks/scripts/check-deps.sh`（dev-workflow の説明） | 新規・変更 |
| issue-workflow | `skills/issue-design/`（Phase 4 の後・template-9sections の完了条件）/ `skills/issue-create/`（feature・debt）/ `skills/start/references/lightweight-flow.md`（Step 1・3・6 の前・8・報告）/ `skills/start/SKILL.md` / `skills/issue-maintain/`（completed 遷移で close） | 変更 |
| feature-dev | `scripts/checklist-run.py` / `scripts/checklist-gate.py` / `scripts/lib/ui-paths.sh`（複製）/ `skills/feature-dev/SKILL.md`（Phase 4・足切りの停止点・5.5・7）/ `agents/code-architect.md`（出力形式） | 新規・変更 |
| dev-workflow | `hooks/scripts/screenshot-ledger.sh`（PostToolUse）/ `hooks/scripts/ui-verify-gate.sh`（チェックリストがあれば黙る）/ `hooks/hooks.json` / `skills/ui-verify/SKILL.md` + `commands/ui-verify.md`（`--checklist`・`--only`・早期終了・chrome-devtools の固定・絶対パス・storybook・出力行）/ `scripts/lib/ui-paths.sh`（複製に置き換え。冒頭の注記を書き換える） | 新規・変更 |
| 文書 | ルートの `CLAUDE.md`（プラグイン一覧の hooks 列・`.claude-plugin/lib/` の構造）/ `INDEX.md` / 3 プラグインの `README.md` / 各 `CHANGELOG.md` | 変更 |
| テスト | `test_verification_checklist.py`（run / gate の CLI。正本を対象にし、期待値はテスト側で独立に作る）/ `test_issue_workflow_hooks.py` / `test_dev_workflow_hooks.py`（発火と黙る条件） | 新規・変更 |

### 移行手順

1. 書式の正本と ui-paths の正本化・`BYTE_REPLICAS` の枠（既存の挙動は変えない）
2. `checklist-run.py` / `checklist-gate.py` の正本と複製、CLI テスト
3. 撮影台帳（dev-workflow）と commit gate（issue-workflow）の hook、ui-verify-gate.sh の黙る条件。チェックリストが無い限りどこにも効かないので、この時点では既存の作業に影響しない
4. ui-verify の `--checklist` / `--only` など
5. 作成点（issue-design / issue-create / 軽量フロー / feature-dev）と commit 直前の再確認。ここで初めてチェックリストが作られ始める

誤って止めたときの戻し方: Issue 単位なら、利用者が自分のターミナルで commit するか、利用者の指示で `attest --kind waived` する。全体なら、issue-workflow の版を戻す（plugin-manager で前の版を入れる）。gate はチェックリストがある Issue にしか効かないので、版を戻すと次の commit から止まらなくなる。

## 検討した代替案

| 観点 | 案 A（採用）: issue-workflow が正本と gate を持つ | 案 B: dev-workflow が持つ | 案 C: Issue ファイル内で完結 |
|------|------------|------|------|
| 変更量 | 大（スクリプト 2 の正本と複製・hook 2・ui-verify） | 中（ui-verify-gate を拡張） | 中 |
| 責務の一致 | 設計時の作成と commit 時の検査を同じプラグインが見る。撮影の事実だけを、chrome-devtools の持ち主の dev-workflow が記録する | 画面以外の手段（unit-test / db-read）まで ui-verify の責務に入る。作成側は結局 issue-workflow / feature-dev に要る | 一致するが、書式が Issue 本文に混ざる |
| 適用範囲 | issue-workflow のあるすべてのフロー。feature-dev 単独は段の完了条件だけ | dev-workflow があれば Issue 無しでも効く | BACKEND=none と Issue の無い feature-dev で使えない |
| 壊れにくさ | 別ファイル・記録スクリプトだけが書く | 同左 | 推敲（writing-polish）や手編集で書式が崩れる |

- 案 B を採らない理由: 「設計に対する完了条件」は Issue 側の概念で、ui-verify は実行手段の 1 つにすぎない
- 案 C を採らない理由: BACKEND=none ではそもそも置き場が無い（`issue-design` Phase 3 はファイルを作らない）。状態（pass / 証跡）を Issue 本文に持たせると、hook が Markdown を解析することになる。v1 では「設計があるか」の判定（Issue 本文の見出しの解析）も hook に持たせないので、hook が読むのは JSON と git だけになる
- 案 A の代償: スクリプト 2 本と ui-paths を issue-workflow と feature-dev に複製する。CLAUDE.md は複製を「分割単位の誤りのシグナル」とするが、プラグイン間依存の禁止の下で 2 つのワークフローに同じ判定を掛けるには避けられない。`plugin-enabled.sh` と同じく byte 検査で食い違いを止める

ゲート位置の代替（grill 1）: push / PR 作成で止める案は WIP コミットを通せるが、self-review・読み合わせの後の画面の変更を commit 前に再確認させられない。フローの完了条件だけにする案は、遵守が LLM 任せになる（CLAUDE.md「ルール配置」: Hook > Skill）。

指紋の代替（design-review）: 対象を「画面のファイル / 全変更ファイル」の固定 2 区分にする案は単純だが、画面の内容が backend に依存する ui:true の項目を確認前に戻せない。既定を 1 つ（全変更ファイル）にし、`paths` で狭めることだけを認めた。

直接編集を止める PreToolUse hook（Edit / Write）の代替（design-review）: digest が手での書き換えを検出し、`reset` で回復できるので、hook は足さない（新しい hook を 3 本から 2 本にした）。

## 設計判断ログ

- [→ADR候補] チェックリストの UI 項目のスクショは chrome-devtools に限り、他の基盤への fallback を禁止する（ADR-20261020221214 の決定 1 の一部を上書き）→ ADR-20261102225822
- [→ADR候補] チェックリストがある Issue では、全項目を満たすまで Claude の `git commit` を PreToolUse で block する。対象と分かった後の判定不能も block する（fail-closed）。対象かどうか判定できないときは黙る。利用者が自分のターミナルで打つ commit を最後の逃げ道に残す → ADR-20261102225845
- [→ADR候補] 動作確認の状態と証跡は記録スクリプトだけが書く（UI は撮影台帳との照合つき、UI 以外はスクリプトが字面の一致を確かめてから実行する）。守るのは「うっかり」までで、Bash による意図的な偽造は防がない → ADR-20261102225906
- [local] 「設計があるのにチェックリストが無い」は v1 では hook で止めず、作成点の手順で担保する（open 4）
- [local] 撮影台帳は、chrome-devtools の持ち主の dev-workflow に置く
- [local] チェックリスト・登録簿・台帳はメインのチェックアウトに置き、Issue ID をキーにする
- [local] 指紋は作業ツリーだけで取り、index は見ない（分割コミットを通すため）
- [local] UI 以外のコマンドは、スクリプトの中で実行せずに Bash の字面に出す（permission と guardrail を通すため）
- [local] waived / manual / remove は、利用者の発言の引用を必須にし、Claude の判断では付けない。edit と remove の before / after は報告に必ず出す
- [local] 書式は JSON、スクリプトは python の stdlib。正本は `.claude-plugin/lib/` に置き、byte 一致で複製する（plugin-enabled.sh と同じ運用）
- [local] 条件 5 は `UI_PATH_ERE` だけで判定する（`UI_SCRIPT_ERE` は ui-paths.sh 自身が hook に使わないと決めている）

## 未解決事項 (open)

1. **チェックリストを別のマシンへ持ち出すか**: gitignore 下なので、別のマシンで作業を続けると、チェックリストも登録簿も無い（gate は対象外として黙る）。(a) チェックリストだけ追跡する（`.gitignore` に `!*.checklist.json`）— 証跡の png と台帳は持ち出せないので、別のマシンでは UI 項目が条件 4 で、全項目が条件 3 で確認し直しになる。`record` の差分もコミットに混ざる / (b) 持ち出さない — 別のマシンでは gate が掛からない。方向性: (b) を v1 にする（作業者は通常 1 台で 1 Issue を進める）。持ち出すときは、`run` が字面の一致を見ても、他人の書いた target を実行することになる点に注意する（(a) を採るなら、取り込んだ target の承認の手順が要る）。確定タイミング: 複数マシンで 1 Issue を進める実例が出たとき
2. **chrome-devtools が恒常的に使えない環境**（headless・リモート）: UI 項目のある Issue は、利用者が自分で commit するまで進まない。方向性: 要望どおりに止める。確定タイミング: 運用で困った実例が出たとき
3. **commit で止める方式の見直し**: 誤 block（条件 3 以外の理由の多発・分割コミットや worktree での想定外の停止）が続くなら、ゲートの位置（push / PR 作成）や条件を見直す。観測の材料は `.gate-log.jsonl` の理由の分布と、利用者の報告。方向性: v1 は commit のまま。確定タイミング: 導入から 1 か月後に `.gate-log.jsonl` を見る
4. **条件 6（設計があるのにチェックリストが無い）を足すか**: (a) 足す — 要望を hook で強制できる。代わりに、Issue 本文の見出しの解析（`## 計画` / `## 対応方針` / `## 対応内容` のプレースホルダの除外）・backend 判定の正本化・feature-dev の足切りの経路の救済・既存 Issue の除外（frontmatter の `created` と導入日の比較）が要る / (b) 足さない — 作成点の手順だけで担保する。方向性: (b)。確定タイミング: 作成点を通ったのにチェックリストが無かった実例が出たとき。足す前に、既存の Issue で述語が何件当たるかを測る（`docs/rule-placement.md` の事前計測）

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（Issue 分解案。番号順に依存する。4 と 5 は 3 の後なら並行できる）:
   1. 書式の正本・ui-paths の正本化・`BYTE_REPLICAS` の枠（挙動は変えない）
   2. `checklist-run.py` / `checklist-gate.py` の正本と複製、CLI テスト
   3. 撮影台帳 hook（dev-workflow）、commit gate hook（issue-workflow）、ui-verify-gate.sh の黙る条件、hook のテスト（黙る条件を厚く）
   4. dev-workflow: ui-verify の `--checklist` / `--only`・早期終了・chrome-devtools の固定・絶対パス・storybook・出力行
   5. issue-workflow / feature-dev: 作成点・呼び出し元の止める分岐・commit 直前の再確認・close・文書の更新
   - 着手前に `harness-keeper:component-addition-advisor` を通す（新しい hook 2・新しいスクリプト 2）
   - feature-dev で進めるなら: `/feature-dev 動作確認チェックリストの書式と gate を足す design=.claude/designs/20261102-verification-checklist-gate.md`
2. **検証方法**:
   - gate: 6 条件と、対象外で黙る 4 つ・判定不能の 4 つのそれぞれについて、使い捨てのリポジトリで exit code を確かめる（期待値はテスト側で独立に作る）。git-commit-helper と同じ形の分割コミット（実装 → テスト、hunk 単位の stage）が 2 回とも通ること、worktree の中から `cd <wt> && git commit` しても `<main>` のチェックリストを引くことを含める
   - 記録スクリプト: `run` が字面の一致しないコマンドを拒否すること、並列の `run` で更新が消えないこと、書き込み中の kill で JSON が壊れないこと（`.bak` が残ること）
   - 撮影台帳: hook_harness で take_screenshot の PostToolUse を流して追記を確かめる。別のツール名・filePath が無い・相対パス・チェックリストの無い repo で黙ることを確かめる
   - commit gate の hook: `git commit` 以外・Issue ID の無いブランチ・登録簿に無い Issue・解決できない `-C` で黙ること、未充足なら exit 2 になることを確かめる。gate の異常終了と時間切れでも exit 2 になること（fail-closed）を確かめる
   - 実機: Web フロントエンドを持つ repo（このリポジトリには無い。どのマシンで行うかは着手時に決める）で、UI を含む Issue を軽量フローで 1 本通す。確かめるのは次の 4 つ:
     - chrome-devtools のプロファイルを他のセッションに掴ませると blocked で止まる
     - 読み合わせで画面を直した後、commit 直前の再確認がその項目だけを撮り直す
     - 同じセッションの 2 回目の ui-verify（再確認）がターミナルの CLI でも通る（`CLAUDE_PID` の有無）
     - worktree で作業しても commit が通る
   - 変異テスト: gate の判定ロジックは新しい検証ロジックなので、利用者の承認を取って回す
3. **実装完了時の doc 更新手順**:
   - frontmatter の `phase: target` を `current` に、`last-validated` を実装完了日に更新する。切り出した ADR の id を `adrs:` に入れる
   - 実装と乖離した箇所は「実装状況」節に追記する。方式ごと変わったなら supersede する

## 関連

- 関連 Issue: GitHub issue #306（動作確認を正式な段にした）
- 関連 spec: なし
- 関連 ADR: ADR-20261020221214（ブラウザ基盤の選択。決定 1 の一部を ADR-20261102225822 が上書き予定）/ ADR-20261102225822 / ADR-20261102225845 / ADR-20261102225906（この doc から切り出した 3 件。いずれも proposed で、実装時に accepted へ更新する）
- 関連 design doc: `.claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md`（ui-verify verify と verification.md）
