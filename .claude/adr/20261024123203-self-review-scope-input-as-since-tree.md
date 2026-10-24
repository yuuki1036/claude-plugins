---
id: 20261024123203
status: accepted
phase: current
last-validated: 2026-10-24
supersedes: []
superseded-by: null
append_only: true
tags: [code-review, self-review, feature-dev, review-scope]
---

# ADR-20261024123203: self-review の範囲を絞る入力は起点の tree（--since）で受け、delta は self-review が作る

## ステータス

accepted（2026-10-24）

## コンテキスト / 背景

- GitHub issue #313: feature-dev の G-V ループの再レビューは、self-review を `--focus` と `--rereview` で呼び直すが、見る範囲は base との分岐点から作業ツリーまでの diff 全体のままだった。#310 の実測では、3 回目の再レビューが 4 体・sub agent のトークン計 約 835k だった
- 再レビューの範囲を delta（前回のレビューの後に変えた分）に絞るには、呼び出し側から self-review へ「どこからの変更か」を渡す必要がある。渡し方は、起点の tree を渡して self-review が diff を取る形と、呼び出し側が patch を作って渡す形の 2 つがあった
- self-review の diff は「分岐点..HEAD・staged・unstaged」の 3 系統で、未追跡ファイルを含まない（`code-review/scripts/triage-signals.sh`）。一方、feature-dev が持つ tree（`gv-loop.py` の `pre_fix_tree`、`review-snapshot.sh` の `save`）は、一時 index に `add -A` して作るので未追跡ファイルを含む
- 2026-10-24 に、利用者が設計の場で前者（tree を渡す）を選んだ

## 決定

1. self-review の範囲を絞る入力は、起点の tree を `--since=<tree>` で受ける。delta は self-review が Step 1 で `git diff <tree>` を、diff 全体と同じ取り方で作る。delta は diff 全体に入るファイルに限る
2. 呼び出し側は patch や行の範囲を渡さない。前回の対象（auto-fix の対象など）は、別の引数 `--prior-findings=<path>` で `[{file, line, focus, title}]` として渡す
3. tree を引けないときは、diff 全体を見て続ける（範囲を絞れないことで指摘を落とさない）

## 影響 (Consequences)

- **良い影響**: delta と diff 全体で、取り方と対象ファイルの集合が揃う（行番号は、delta が作業ツリー基準、diff 全体は 3 系統の連結で版が混ざる）。呼び出し元は tree の ID を持っていれば足り、feature-dev の G-V ループのほかに Phase 6.9（`save` した tree）も同じ引数で使える
- **悪い影響**: code-review の Step 1 に、tree との差分を取る処理と、その検査（tree を引けない・未追跡になったファイルが削除に見える）が増える。呼び出し元は tree を作れる環境（git の作業ツリー）に限られる
- **トレードオフ**: 受け取る形の少なさと、diff 全体との一貫性を取った。呼び出し側で patch を作れば code-review は git を扱わずに済むが、未追跡ファイルの差で delta と diff 全体の対象がずれ、受け取る形（patch と行の範囲）も増える

## 適用方法 (Enforcement)

- self-review の引数の契約に、patch や行の範囲を受け取る引数を設けない（入口が無いので、呼び出し側が patch を渡す経路は構造的に生まれない）
- delta の取り方は `triage-signals.sh --since` の CLI テストで固定する（diff 全体のファイルに限る / 未追跡になったファイルを削除に数えない / 引けない tree で diff 全体に戻る）。テストは `.claude-plugin/scripts/tests/` に置く
- feature-dev の手順書が再レビューで `--since` / `--prior-findings` を渡し `--focus` を渡さないことは、手順書を通すテスト（feature-dev の G-V ループのテスト）に足して固定する
- 新しい呼び出し元が self-review を絞って呼ぶかは、手順の文面の判断を含むので hook では決定的に判定できない。この ADR と design doc を読ませることで守る

## 検討した代替案

- **呼び出し側（feature-dev）が patch を作って渡す**: code-review は git の tree を扱わずに済む。ただし tree 同士の差分には未追跡ファイルの変更が入り、self-review の diff 全体と対象がずれうる。受け取る形（patch と行の範囲）も増える
- **code-review は変えず、`--focus` と共通ブロックの指示で「前回以降」に絞る**: #298 で、範囲を指示文で絞ったために前回の指摘への修正が検証済み扱いになり、どのレビューにも見られなかった。体数も観点の数のままで減らない

## 関連

- 関連 ADR: なし
- 関連 Issue: GitHub issue #313 / #310 / #298
- 関連 design doc: `.claude/designs/20261024-self-review-delta-rereview.md`
- 関連 knowledge: なし
