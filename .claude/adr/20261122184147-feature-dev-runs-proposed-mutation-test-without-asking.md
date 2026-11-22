---
id: 20261122184147
status: accepted
phase: current
last-validated: 2026-11-22
supersedes: []
superseded-by: null
append_only: true
tags: [mutation-test, feature-dev, review-guide]
---

# ADR-20261122184147: feature-dev の Phase 7 は、読み合わせの締めが「変異テスト: 提案する」の回を聞かずに回す

## ステータス

accepted（2026-11-22）

## コンテキスト / 背景

- review-guide の読み合わせの締めは `変異テスト: <提案する / 不要 / 道具なし>` の行を出し、回すかは呼び出し元が決める（code-review/references/review-guide-format.md「変異テストの提案」/ GitHub issue #307）
- feature-dev の Phase 7 はこれまで、`提案する` の回に回すかを通常のメッセージで聞き、承認の返信があってから回していた。提案が出る回はたいてい回すので、毎回の確認が手間になっていた（GitHub issue #444）
- ADR-20261025123627 と、それを置き換えた ADR-20261103153228 は、決定の 1 項目として「手元で変異テストを回すのは、新しい lint / 検証ロジックを足したときと、軽量フロー・feature-dev が利用者の承認を得たとき」を持っている。この ADR はその項目のうち feature-dev の部分だけを変える。nightly だけで回す・PR の CI では回さない、という両 ADR の本体は変えない
- この repo は `.claude/mutation-test.sh`（宣言）を置いているので、この決定で、feature-dev の締めが `提案する` の回に変異テストが自動で走る（1 変異ごとにフルスイートを回すので長い）

## 決定

- feature-dev の Phase 7 は、締めの `変異テスト:` が `提案する` で始まる回に、利用者に聞かずに変異テストを回す。回し方が宣言の `.claude/mutation-test.sh` でも、推測した道具（Stryker / mutmut / cargo-mutants）のコマンドでも同じ
- 回す前に行の理由・回し方（回すコマンド）・所要の目安を示し、結果の報告にも回したコマンドを添える。回しているあいだは作業ツリーを編集しない。結果の 4 区分・前後の `git status --porcelain` の突き合わせ・途中で止まったときの扱いは変えない
- 結果が `生存 N 件`（N が 1 以上）の回だけ、テストを足すかを聞いてターンを終える。それ以外の結果ではテストを足すかを聞かない（途中で止まった回は、上の「途中で止まったときの扱い」のとおり、元に戻したと返されるまで次の一手へ進まない）
- issue-workflow の軽量フローは今どおり承認を得てから回し、dev-workflow の git-commit-helper は今どおり回すかを聞くだけで自分では回さない

## 影響 (Consequences)

- **良い影響**: 提案が出るたびの確認の往復が無くなる。2 回目の self-review の後に、修正を含めた diff へそのまま変異をかけられる
- **悪い影響**: 推測した道具のコマンドは diff から組み立てたもので、利用者が見る前に走る（パスの引用の除外と Stryker の `npx --no` が残りの防御）。この repo では feature-dev の締めの所要が変異テストのぶん長くなり、その間は別のセッションでテストを走らせられない（CLAUDE.md Gotchas の変異テストの項）
- **トレードオフ**: 確認の手間と、利用者が見ないままコマンドが走る危険・所要の長さを天秤にかけ、feature-dev では確認の手間を省くほうを取った。軽量フローと git-commit-helper は確認を残した

## 適用方法 (Enforcement)

- `.claude-plugin/scripts/tests/test_feature_dev_scripts.py` の `test_proposed_mutation_runs_without_asking` が、Phase 7 の `提案する` の分岐に「利用者に聞かずに回す」「推測した道具のコマンドでも同じ」があり、聞く手順（「承認の返信が無ければ回さない」など）が残っていないことを検査する。生存の回だけ止めることも同じテストが見る
- `test_canonical_names_feature_dev_as_the_caller_that_runs_without_asking` が、正本の契約の行が呼び出し元ごとの決め方（feature-dev は聞かずに回す・軽量フローは承認を得てから・git-commit-helper は聞くだけ）を持つことを検査する
- 軽量フローが今どおり承認を取ることは `test_issue_workflow_lightweight_flow.py` の既存のテスト（「承認の返信が無ければ回さない」）が守る
- 実行時に本当に聞かずに回したかは、本文の文言の検査では決まらない（skill の本文は自然言語の手順で、model が読んで実行する）。ここは機械強制できない

## 検討した代替案

- **自動で回すのを宣言（`.claude/mutation-test.sh`）の回だけにする**: 宣言はプロジェクトが決めたコマンドなので承認なしで回す重みが軽い。推測した道具の回は diff から組み立てたコマンドで重みが違う。2026-11-22 に利用者が「推測した道具も含める」を選んだので採らなかった
- **今どおり毎回聞く**: 確認の手間が残る（#444 の動機そのもの）
- 再判断の条件: 推測した道具のコマンドが意図しない範囲を変異させた・ローカルに無い道具を取得しようとした回が出たら、自動で回すのを宣言の回だけにする案へ戻すかを判断し直す
- **ADR-20261103153228 を丸ごと supersede する**: 変えるのは手元で回す条件の 1 項目だけで、nightly だけで回す本体は変えない。本体まで置き換えると、変えていない決定の履歴が追いにくくなるので、項目だけを変える新しい ADR にした

## 関連

- 関連 ADR: [[20261103153228-mutation-test-stays-nightly-after-pr-required]]（手元で回す条件の項目のうち feature-dev の部分をこの ADR が変える）/ [[20261025123627-mutation-test-nightly-only-not-on-push]]
- 関連 Issue: GitHub #444（feature-dev の自動実行）・#505（「要るか」の判定）・#307（変異テストの提案の導入）
- 関連 design doc: なし
- 関連 knowledge: なし
