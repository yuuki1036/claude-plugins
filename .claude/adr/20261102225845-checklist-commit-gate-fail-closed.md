---
id: 20261102225845
status: proposed
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, issue-workflow, hook, gate, verification, fail-closed]
---

# ADR-20261102225845: 動作確認チェックリストがある Issue では、全項目を満たすまで Claude の git commit を fail-closed で block する

## ステータス

proposed（2026-11-02）。設計書 `.claude/designs/20261102-verification-checklist-gate.md` の実装時に accepted へ更新する。

## コンテキスト / 背景

- 利用者の要望: 動作確認の段で、チェックリストの全項目を満たさないと先へ進めないようにしたい
- 今の軽量フロー・feature-dev では、`skipped` / `blocked` のとき理由を報告に残せば先へ進め、`fail` も利用者が承知すれば進む（`lightweight-flow.md:65-71`）。読み合わせの後に画面を変えても、報告に一行書くだけになっている。フローの手順（Skill）で決めたことは LLM 任せで守られ、遵守率は約 90% にとどまる（CLAUDE.md「ルール配置」）
- PreToolUse の hook は、exit 2 以外の非ゼロでも timeout でも止めずに通る（`guardrail-protect/README.md:182-186`）。repo の hook の作法（safe-hook.sh）は異常時に exit 0 で黙るので、そのまま書くと判定不能のときに素通りする
- 同じ PreToolUse でも、壊れた入力では止めない hook（pre-commit-guard）と、止める hook（public-leak-guard）の両方が repo にある。どちらにするかは hook ごとに決めている

## 決定

1. issue-workflow の PreToolUse hook が、Bash の `git commit`（`--amend` と、merge を完了する commit を含む）を自己判定し、判定スクリプト `checklist-gate.py` を呼ぶ
2. 対象は、ブランチ名から取った Issue ID が登録簿にあって close されていないものだけ。commit 先の repo を解決できない・Issue ID を取れない・登録簿に無い、のどれかなら**黙る**（対象かどうか判定できないときは止めない）
3. 対象のときは、項目の未充足・記録の改ざん・指紋の不一致・UI 項目の欠落・UI の変更があるのに UI 項目が無い・登録簿にあるのにファイルが無い、のどれかで block する。**対象と分かった後に判定できないとき（JSON の破損・schema_version の不一致・git の失敗・時間切れ）も block する**。block するときは、回復の手順を理由と一緒に出す
4. hook は safe-hook の縮退（ERR trap と `safe_hook_error` による exit 0）を使わない。ERR trap を exit 2 に上書きし、gate の exit 1 と 2 を hook の exit 2 に変換する。gate は hook の timeout（10 秒）より短い 8 秒の予算で、自分から exit 2 を返す
5. 逃げ道は 2 つだけ残す。利用者が自分のターミナルで打つ commit（hook は Claude の tool 呼び出しにしか掛からない）と、利用者の明示の指示による項目の waived
6. 「設計があるのにチェックリストが無い」は、v1 では hook で止めない。作成点の手順（Skill）で担保する

## 影響 (Consequences)

- **良い影響**: チェックリストがある Issue では、未確認のまま Claude が commit することが無くなる。読み合わせや self-review の後の変更も、指紋の不一致として commit の前に必ず捕まる
- **悪い影響**: WIP コミットができなくなる（利用者が受け入れた）。判定不能でも止めるので、チェックリストが壊れたときや版がずれたときは、利用者の手当てが要る。sub セッションや headless の実行では、利用者のターミナルという逃げ道が実際には使いにくい。timeout で hook が打ち切られると通ってしまう点（PreToolUse の仕様）は、gate 自身の時間予算で狭めるだけで、ゼロにはできない
- **トレードオフ**: 止めすぎる側（作業が止まる）と止め損ねる側（未確認の commit）を比べ、対象と分かった後は止めすぎる側を取った。止めすぎる範囲は「チェックリストがある Issue」に限り、対象の判定では止め損ねる側を取った

## 適用方法 (Enforcement)

- この決定そのものが hook による機械強制。fail-closed であることは hook のテストで固定する。gate が exit 1 / 2 を返したときと、異常終了・時間切れのときに、hook が exit 2 を返すことを確かめる。黙る条件（`git commit` 以外・Issue ID の無いブランチ・登録簿に無い Issue・解決できない `git -C`）も同じテストで厚く確かめる
- 誤って止めた回の理由を `.claude/verification/.gate-log.jsonl` に残し、ゲートの位置や条件を見直す材料にする（設計書の open 3）

## 検討した代替案

- **push / PR 作成で止める**: WIP コミットを通せる。しかし、self-review や読み合わせの後に入った画面の変更を、commit 前に再確認させられない
- **フローの段の完了条件だけにする（hook なし）**: 運用は軽いが、遵守が LLM 任せになる
- **判定不能のときは黙る（fail-open）**: 作業は止まらない。しかしチェックリストが壊れた・版がずれたときに、検査がまるごと素通りになり、要望の「全て満たさないと先へ進めない」が崩れる
- **条件 6（設計があるのにチェックリストが無い）も hook で止める**: 要望を最も強く守れる。代わりに、hook が Issue 本文の見出しを解析し、backend 判定を複製し、プレースホルダを除外し、作成点を通らない経路を救う必要がある。作成漏れの実例が出るまで見送った

## 関連

- 関連 ADR: ADR-20261102225822（UI 項目のスクショは chrome-devtools に限る）/ ADR-20261102225906（証跡は記録スクリプトだけが書く）
- 関連 Issue: GitHub issue #306
- 関連 design doc: `.claude/designs/20261102-verification-checklist-gate.md`
- 関連 knowledge: なし
