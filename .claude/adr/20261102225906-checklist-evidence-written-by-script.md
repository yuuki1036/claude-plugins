---
id: 20261102225906
status: proposed
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, issue-workflow, feature-dev, dev-workflow, verification, evidence]
---

# ADR-20261102225906: 動作確認チェックリストの状態と証跡は記録スクリプトだけが書き、守る範囲は「うっかり」までとする

## ステータス

proposed（2026-11-02）。設計書 `.claude/designs/20261102-verification-checklist-gate.md` の実装時に accepted へ更新する。

## コンテキスト / 背景

- 画面以外の動作確認（unit-test・DB read 等）は、何を実行してどうなったかを Claude が自己申告している。実行していなくても「pass」と書ける
- 利用者が求めたのは「全て満たさないと先へ進めない」こと。チェックリストの pass を Claude が手で書けるなら、ゲートは形だけになる
- 一方で、Claude は Bash で任意のファイルを書ける。秘密を持たない hash では、記録の改ざんを防げない。hook が見られるのは tool_input の文字列までで、Bash の中で何が書かれるかは判定できない
- 記録スクリプトの中で target のコマンドを実行すると、外から見えるのは `checklist-run.py run V1` だけになる。そうすると、permission の判定と guardrail-protect の PreToolUse hook（`tool_input.command` の文字列を見る）を通らないコマンドの実行経路ができる

## 決定

1. チェックリストの `status` と `record` は、記録スクリプト `checklist-run.py` だけが書く。定義の欄と記録から `digest` を計算して持たせ、手で書き換えた項目は gate が検出して止める。回復は `reset`（pending に戻す）だけで、digest を書き直す口は作らない
2. UI 項目は、dev-workflow の撮影台帳（chrome-devtools の take_screenshot の PostToolUse で、realpath と sha256 を記録する）に載った png だけを記録できる
3. UI 以外の項目は、Claude が Bash で `checklist-run.py run <id> -- <target>` を実行する。スクリプトは `--` 以降が項目の `target` と字面どおり一致するときだけ実行し、exit code と出力の末尾を記録する（`db-read` と `api` は出力の hash だけを残す）。コマンドを Bash の字面に出すことで、permission と guardrail の検査を通す
4. waived・manual・項目の remove は、利用者の発言の引用を必須にし、Claude の判断では付けない。`edit` と `remove` の before / after は、フローの報告に必ず出す
5. 守るのは「うっかり」まで: 手で書いた記録、確認していない pass、他の基盤で撮った画像、チェックリストの消去（登録簿で検出する）。Bash による意図的な偽造（台帳・記録・登録簿をまとめて書き換える）は防がない

## 影響 (Consequences)

- **良い影響**: 「実行していないのに pass」がゲートを通らなくなる。UI 以外のコマンドも、利用者の permission の判定と guardrail の検査を通る。target の書き換えも報告に出るので、利用者から見える
- **悪い影響**: 記録の操作がすべてスクリプト経由になり、サブコマンド（add / run / record-ui / attest / edit / reset / remove / close など）が増える。Claude 自身の書き間違いを直すにも、スクリプトを通すことになる。意図的な偽造は防げないので、「ゲートを通った＝確認した」は Claude の協力を前提にした保証にとどまる
- **トレードオフ**: 暗号的な改ざん防止（秘密を Claude の手の届かない所に置く手段が無い）を諦め、うっかりの防止に絞った。その代わりに仕組みを軽くし、stdlib だけで実装できるようにした

## 適用方法 (Enforcement)

- 記録スクリプトの CLI テストで固定する: 字面が一致しないコマンドの拒否、`status` / `record` を含む `add` の拒否、引用の空な attest / remove の拒否、並列の `run` で更新が消えないこと、kill で JSON が壊れないこと
- gate の CLI テストで固定する: digest の不一致・台帳に無い png・登録簿にあるのにファイルが無い、の各条件で exit 1 になること
- 撮影台帳の hook は hook_harness のテストで固定する: take_screenshot 以外・filePath が無い・相対パス・チェックリストの無い repo では書かないこと
- 意図的な偽造は機械強制しない（判定の手段が無い）

## 検討した代替案

- **Claude の自己申告を記録するだけ（gate は欄が埋まっているかだけを見る）**: 最も軽いが、書いた内容が本物かを何も保証しない
- **gate が commit のたびにコマンドを再実行する**: 最も強いが、commit が遅くなる。DB を読む項目は、hook の timeout と環境（接続情報）に依存する
- **記録スクリプトの中で target を実行する（`run <id>` だけ）**: 呼び出しは簡単だが、外から見えるのが `run V1` だけになり、permission と guardrail を通らないコマンドの実行経路ができる
- **Edit / Write で記録を書き換えることを PreToolUse hook で止める**: digest で検出でき、`reset` で回復できるので、守れる範囲が重なる。Edit / Write のたびに発火する hook を増やさなかった
- **秘密鍵を使った HMAC で記録に署名する**: Claude が読めない場所に鍵を置く手段が無いので、偽造の防止にならない

## 関連

- 関連 ADR: ADR-20261102225822（UI 項目のスクショは chrome-devtools に限る）/ ADR-20261102225845（commit gate の fail-closed）
- 関連 Issue: GitHub issue #306
- 関連 design doc: `.claude/designs/20261102-verification-checklist-gate.md`
- 関連 knowledge: なし
