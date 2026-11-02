---
id: 20261102225822
status: proposed
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, dev-workflow, ui-verify, issue-workflow, verification, chrome-devtools]
---

# ADR-20261102225822: 動作確認チェックリストの UI 項目のスクショは chrome-devtools に限り、他の基盤への fallback を禁止する

## ステータス

proposed（2026-11-02）。設計書 `.claude/designs/20261102-verification-checklist-gate.md` の実装時に accepted へ更新する。accepted になった時点で、ADR-20261020221214 の決定 1 のうち「スクショが要る回に chrome-devtools が起動できなければ、要らない側の基盤で続け、証跡なしと記録する」を、チェックリストの UI 項目の回に限って上書きする。ADR-20261020221214 のほかの決定と、チェックリストが無い回の ui-verify の挙動は変えないので、ADR-20261020221214 全体は supersede しない。

## コンテキスト / 背景

- 利用者の要望: 設計時に動作確認チェックリストを作り、全項目を満たさないと先へ進めないようにしたい。UI に関わる項目はスクショ必須とし、「chrome-devtools が使えないので他の手段で確かめた」は認めない
- ADR-20261020221214 の決定 1 は、スクショが要る回に chrome-devtools が起動できなければ Claude Browser・Claude in Chrome などで続け、証跡を「なし（理由）」と記録する。この 2 つの基盤はスクショをファイルに保存できない（`dev-workflow/skills/ui-verify/SKILL.md:223`）。そのため、この fallback を通った UI 項目にはスクショが残らない
- chrome-devtools が使えなくなる主な理由は、別のセッションのブラウザがプロファイルを掴んでいることと、`CLAUDE_PID` が無い環境で自分のブラウザか判定できないこと（ADR-20261020221214）。どちらも、利用者がブラウザを閉じる・止めることで解ける

## 決定

1. ui-verify に `--checklist=<path>` が渡され、その中に `ui: true` の項目があるとき、基盤は chrome-devtools に固定する。Claude Browser・Claude in Chrome へは落ちない
2. chrome-devtools を使えない回（起動できない・他のセッションのブラウザを利用者が止めないと答えた・`HOLDER_SESSION=unknown`・`LOCK=foreign-host` など）は、`UI_VERIFY_RESULT=blocked` と `UI_VERIFY_REASON=devtools-required:<理由>` を返す。`UI_VERIFY_BROWSER=none` は使わない（既存の呼び出し元は `none` を手動確認に回すため）
3. 呼び出し元（軽量フロー Step 3・feature-dev Phase 5.5・commit 直前の再確認）は、`devtools-required` のとき、dev-workflow が無効のとき、ui-verify が旧版で `UI_VERIFY_CHECKLIST=` の行を出さないときに、手動確認へ回さずに止める。そのうえで利用者に環境の修正（ブラウザを閉じる・dev-workflow を有効にする・更新する）を頼む
4. スクショは、git toplevel を起点にした絶対パスの filePath で撮る。チェックリストに記録できるのは、dev-workflow の撮影台帳に realpath と sha256 が載った png だけ

## 影響 (Consequences)

- **良い影響**: チェックリストの UI 項目には、必ず chrome-devtools のスクショが残る。手で目視した・pane で確かめた、という証跡のない pass が入り込まない
- **悪い影響**: chrome-devtools を使えない環境（headless・リモート・プロファイルの取り合いが解けない状況）では、UI 項目のある Issue が先へ進まない。逃げ道は、利用者の明示の指示による waived と、利用者自身のターミナルでの commit だけになる。dev-workflow が、チェックリストの UI 項目にとっては事実上の必須依存になる（issue-workflow の `check-deps.sh` では任意のまま）
- **トレードオフ**: 動作確認の手軽さ（pane で済ませる）より、証跡の一貫性（UI 項目は chrome-devtools 一本）を取った。チェックリストが無い回は ADR-20261020221214 のままにして、手軽さを残した

## 適用方法 (Enforcement)

- 機械強制できる部分: 記録スクリプト `checklist-run.py record-ui` は、png の realpath と sha256 が撮影台帳（dev-workflow の PostToolUse hook が `mcp__plugin_dev-workflow_chrome-devtools__take_screenshot` のときだけ書く）に無ければ記録しない。commit gate（issue-workflow の PreToolUse hook）の条件 4 も同じ照合を行う。どちらも python の stdlib の CLI テストと hook_harness のテストで固定する
- 機械強制できない部分: ui-verify が fallback せずに blocked を返すこと、呼び出し元が手動確認に回さずに止めることは、SKILL.md の手順に置く。ただし fallback して撮れなかった場合も、台帳に png が無いので記録と commit の段で止まる。結果として、手順を外れても pass にはならない

## 検討した代替案

- **ADR-20261020221214 のまま（使えなければ他の基盤で続け、証跡なし）**: 要望の「他の手段は認めない」に反する
- **Claude Browser / Claude in Chrome で操作し、スクショだけ Storybook と chrome-devtools で撮る**: e2e の項目では、操作した画面と撮った画面が別物になる。chrome-devtools を基盤から外した回は、Storybook でも撮れない（ADR-20261020221214 の運用）
- **ADR-20261020221214 を丸ごと supersede する**: チェックリストが無い回の基盤の選択（スクショが要らなければ pane）と、既存ブラウザを止める確認の決定は、今も有効。丸ごと置き換える理由が無い

## 関連

- 関連 ADR: ADR-20261020221214（決定 1 の一部を、チェックリストの UI 項目に限って上書き）/ ADR-20261102225845（commit gate の fail-closed）/ ADR-20261102225906（証跡は記録スクリプトだけが書く）
- 関連 Issue: GitHub issue #306（動作確認を正式な段にした）
- 関連 design doc: `.claude/designs/20261102-verification-checklist-gate.md`
- 関連 knowledge: なし
