---
id: 20261020221214
status: accepted
phase: current
last-validated: 2026-10-20
supersedes: [20260912195236]
superseded-by: null
append_only: true
tags: [architecture, dev-workflow, ui-verify, mcp, browser, e2e]
---

# ADR-20261020221214: ui-verify のブラウザ基盤はスクショの要否で選び、chrome-devtools の既存ブラウザは利用者の確認を取ってから止める

## ステータス

accepted（2026-10-20）。ADR-20260912195236（認証の要否を第 1 キーにし、chrome-devtools --autoConnect を認証あり E2E の第 1 基盤、内蔵 pane / Claude in Chrome を証跡なしの fallback にする）を supersede する。

## コンテキスト / 背景

- GitHub issue #306（ユーザー本人による見直しの依頼）: 動作確認を feature-dev と軽量フローの正式な段にする。スクショが要る回は chrome-devtools、要らない回は Claude アプリのブラウザ pane（Claude Browser）か Claude in Chrome で行う。chrome-devtools の起動前に既存のプロセスを検知し、ユーザーの確認なしには止めない
- ADR-20260912195236 は基盤の優先順を**認証の要否**で決め、pane を第 1 にする案を「保存口が無く、認証不要ケースの証跡保存（snap の鎖）が死ぬ」として却下した。動作確認が既定の段になると、スクショの要らない回が大半になる。その回には保存口が要らないので、この却下理由は当たらない。ただし決定そのもの（第 1 キー・第 1 基盤）は変わる
- chrome-devtools-mcp は既定で 1 つのプロファイル（`~/.cache/chrome-devtools-mcp/chrome-profile`）を全セッションで共有し、同時に 1 ブラウザしか使えない（2 つ目は `The browser is already running for <dir>` で失敗する。1.2.0 / 1.11.0 の実装で確認）。開発機では chrome-devtools-mcp が 3 つ並走していた。プロファイルの SingletonLock は、Chrome が落ちた後も死んだ pid を指したまま残っていた（stale lock の実例）
- Bash tool の環境には `CLAUDE_PID`（このセッションの claude の pid）があり、同梱の chrome-devtools-mcp とそれが起動する Chrome はその子孫になる（開発機の Desktop app で確認）

## 決定

1. **verify のブラウザ基盤はスクショの要否を第 1 キーにして選ぶ**。要否は `--screenshot=need|none` → 依頼（証跡・スクショ・PR 添付・動画の指定）→ それ以外は要らない、の順で決める
   - 要る → chrome-devtools（認証の扱いは ADR-20260912195236 のまま: 認証不要は既定プロファイル、認証必要は `--autoConnect`）。起動できなければ下の「要らない」側の基盤で続け、証跡は「なし（理由）」と記録する
   - 要らない → Claude Browser → Claude in Chrome → chrome-devtools → どれも使えなければ blocked
   - tune / snap は撮影が目的なので常に chrome-devtools。PR に添付するスクショは pr-creator の Step 4.5 が選ぶ: 今のブランチで撮った snap / verify / tune のディレクトリ（このチェックアウトが今のブランチに切り替わった後の mtime を持つもの。判定は dev-workflow の `scripts/pick-screenshot-dir.sh`）があればその最新を使い、無ければ snap で撮る（証跡の鎖は chrome-devtools 一本のまま）
2. **chrome-devtools の既存ブラウザは、利用者の明示確認の後だけ止める**。ui-verify は chrome-devtools の最初のツール呼び出しの前に `scripts/chrome-profile-lock.sh status` を 1 回見る（呼び出しが `already running` で失敗した回も同じ分岐を通る）
   - 確認を出すのは `LOCK=held` かつ `HOLDER_SESSION=other` / `orphan` のときだけ。選択肢は「止めない」を先頭、「止めて続行」を 2 番目にし、どちらにも (Recommended) を付けない。無操作の自動続行は「止めない」扱い
   - `HOLDER_SESSION=self`（このセッションの MCP のブラウザ）は止めない。`HOLDER_SESSION=unknown`（祖先に chrome-devtools-mcp がいるが `CLAUDE_PID` が無効で、self か other か決められない）・`LOCK=foreign-host` / `LOCK=unknown` は止めずに報告し、chrome-devtools を基盤から外す
   - stop は `--pid` を必須にし、止める直前に lock を読み直して pid・`--user-data-dir=<dir>`・hostname の一致を確かめる。送るのは SIGTERM だけ（SIGKILL はプロファイルの書き出しと lock の解放を飛ばす）。self と unknown はスクリプト側でも拒否する
   - `--dir` を省いた status が見る dir は、Bash から読める `.claude/dev-workflow.json` の `browser_connect` で決まる。userConfig の値は `.mcp.json` の env で MCP プロセスにだけ渡り、Bash tool の環境には無い（開発機で確認: Bash の環境にあるのは `CLAUDE_PID` だけ）。userConfig だけで設定した接続方式は見えず、既定の dir を見る
3. **Claude in Chrome は実 Chrome の書き込みの歯止めの対象に入れる**。Claude in Chrome は利用者の実プロファイルにつながる（ADR-20260831120000 が `--autoConnect` を既定にしなかったのと同じ privacy posture）。スクショをファイルに保存しないので、ADR-20260831120000 の懸念（snap の出力が public な raw URL になる経路）は当たらない。書き込み系は `--autoConnect` と同じく既定 blocked で、dev backend が隔離環境だとユーザーが確認したときだけ解禁する

## 影響 (Consequences)

- **良い影響**: 動作確認を既定の段にしても、多くの回はゼロインストールの pane で済み、chrome-devtools のプロファイルの取り合い（別セッションのブラウザ）に当たらない。当たった回も、誰のブラウザかを示したうえで利用者が止めるかを決め、止める相手は確認時の表示と一致する
- **悪い影響**: `/ui-verify verify` の単独起動の既定基盤が chrome-devtools から Claude Browser に変わり、ケースごとの verify-* スクショは既定では撮られない（PR に添付するスクショは、今のブランチで撮ったものが無ければ pr-creator が snap で撮る。判定は `scripts/pick-screenshot-dir.sh`）。基盤が 2 系統になり、tool 名・引数形のドリフトを 2 系統ぶん抱える（ADR-20260831120000 の懸念）。`CLAUDE_PID` が無い環境（ターミナルの CLI では未確認）では、MCP から起動されたブラウザは自分のものでも別セッションのものでも `HOLDER_SESSION=unknown` になり、止める手段が無い（利用者がそのウィンドウを閉じる）。祖先に MCP がいないブラウザは orphan として確認の後に止められ、そのとき自分のブラウザを止めない保証は is_mcp の判定（祖先のコマンド行に chrome-devtools-mcp の起動形があるか）だけに依る。userConfig だけで `browser_connect` を `autoConnect` / `userDataDir=<path>` にした環境では、起動前の status が MCP の使わない既定の dir を見る。その結果、使わないプロファイルを掴む別セッションのブラウザに停止の確認を出し、「止めない」の回と `HOLDER_SESSION=unknown` の回は本当は動く chrome-devtools を基盤から外す（スクショが要る回は証跡を失う）。`<path>` の holder は起動前には検知できず、失敗時の保険でしか拾えない。`.claude/dev-workflow.json` に同じ値を書けば避けられる。根本の対処（MCP 側で解決した接続方式を Bash から読める場所に書く）は起動ラッパの処理を変えるので、この決定の範囲に入れていない
- **トレードオフ**: 証跡の鎖の単一性（chrome-devtools 一本）は、スクショが要る回と tune / snap にだけ残した。誤停止の防止を、確認 UI の文言だけでなくスクリプトの判定（self / unknown の拒否・lock の確かめ直し）にも置いた

## 適用方法 (Enforcement)

- `scripts/chrome-profile-lock.sh` の判定と拒否（self / session-unknown / pid-mismatch / not-held、SIGKILL を送らない、同じプロファイルを持つ別プロセスに触れない）は `.claude-plugin/scripts/tests/test_dev_workflow_chrome_profile_lock.py` が実プロセスで固定する
- 「確認を取ってから止める」「選択肢の順と (Recommended) を付けない」「自動続行を確認と見なさない」は ui-verify の SKILL.md（絶対厳守ルール）にある。AskUserQuestion の回答が自動続行だったかは実行時にしか分からず、hook で決定的に判定できないので機械強制はしない。代わりに、止める側の最後の歯止めをスクリプトに置いた
- スクショの要否による基盤の選択は依頼の読み取り（文脈判断）を含むので機械強制しない

## 検討した代替案

- **ADR-20260912195236 のまま（認証の要否を第 1 キー、chrome-devtools を常に第 1）**: issue #306 の要望（スクショが要らない回は pane / Claude in Chrome）に合わない。動作確認を既定の段にすると、chrome-devtools のプロファイルの取り合いに当たる回も増える
- **内蔵 pane への全面移行**: snap と PR の証跡の鎖が死ぬ（保存口が無い）。ADR-20260831120000 / ADR-20260912195236 の却下理由がそのまま当たる
- **`--isolated` を既定にする**: 取り合いは消えるが、永続プロファイルのログイン状態を毎回失い、認証画面の動作確認が常にログイン待ちで止まる。`--isolated` は `--autoConnect` と conflicts でもある
- **起動ラッパ（launch-chrome-devtools.sh）で検知する**: ラッパの stdout は MCP の通信路で何も出せず、走るのはセッション開始時の 1 回だけで、利用者に確認を取る手段も無い。ブラウザが起動するのは最初のツール呼び出しのとき
- **呼び出しが `already running` で失敗したときだけ status を見る**: 起動前の検知（issue #306 の完了条件）にならず、失敗の文言は chrome-devtools-mcp の版で変わりうる。失敗時の経路は保険として残した

## 再評価のトリガー

- Claude Browser に保存先のパス指定が入ったら、スクショが要る回も pane に寄せることを検討する
- chrome-devtools-mcp が 1 プロファイルで複数ブラウザを扱えるようになったら（既定でセッションごとのプロファイルになる等）、停止の確認ごと外す
- `CLAUDE_PID` が Bash tool の環境から消えたら、self の判定を別の手段に替える
- userConfig の値が Bash tool の環境から読めるようになったら、または MCP 側で解決した接続方式を書き出す経路を足したら、`chrome-profile-lock.sh` の読み取り順にそれを足す

## 関連

- 関連 ADR: ADR-20260912195236（supersede）/ ADR-20260831120000（privacy posture・単一基盤）
- 関連 Issue: GitHub issue #306
- 関連 design doc: `.claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md`（A-1）
- 関連 knowledge: なし
