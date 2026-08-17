# 機械層の先行実行（self-review Step 1.7 / 原則 8）

`run-oracles.sh` が `status=green` 以外を返したときだけ読む。green と「出力が空（宣言なし）」は SKILL 側の記述だけで完結する。

設計判断の正本: `.claude/adr/20260817170000-machine-layer-before-self-review-agents.md`（fail-fast の粒度・「既知」の渡し方・撤回条件）。

## 1. status ごとの扱い

| status | 意味 | 扱い |
|---|---|---|
| `green` | 機械層で落ちるものは無い | Phase 0 へ。Step 6 レポート冒頭に `機械層: green (<elapsed>s)` |
| `red` | 検査が問題を検出した | 下の AskUserQuestion で続行可否を確認 |
| `timeout` | 既定 300 秒で打ち切った | **緑と読まない**。欠測として Phase 0 へ進む |
| `error` | 前提が無く判定できなかった（126/127 等） | 同上。欠測として Phase 0 へ進む |

`timeout` / `error` を green に倒さないのがこの層の要点。倒すと「機械層が死んでいる」と「機械層が通っている」が区別できず、reviewer は空の「既知」リストを見て**機械層が何も検出しなかった**と読む。どちらもレポート冒頭に status をそのまま出す（`機械層: timeout (301s)` 等）。

## 2. `red` のときの続行可否確認（AskUserQuestion）

- question: 「機械層が問題を検出しました（exit `<exit_code>` / `<出力の先頭 1 行>`）。agent を起動する前に直しますか？」
- header: 「機械層」
- options:
  1. label「中止して直す」/ description「安い層で落とせるものに reviewer の予算を使わない（推奨）」
  2. label「このまま続行」/ description「機械層は赤いが、設計・構造のレビューを先に受けたい」

**「中止して直す」なら Phase 0 に進まず終了する**（agent を 1 体も起動しない）。終了時は `log=` のパスと出力の先頭を提示して、何を直すのかが分かる状態で終わる。

**無条件 fail-fast にしない理由**: 「lint は赤いが設計レビューを先に受けたい」を潰すと recall が落ちる。原則 8 の fail-closed は「曖昧なとき保守側に倒す」であって「赤なら人間の判断を奪う」ではない。

## 3. 続行する場合の agent への渡し方

explorer / reviewer プロンプトへ注入するのは**次の 2 行だけ**（機械層の出力本文を転記しない。ディスク上にあるので体数ぶんの複製がそのまま消える）:

```
machine layer (already reported): <log= のパス>
scope: 機械判定で決まる層（lint / 型 / テストの機械的失敗）は担当外。**同一 file:line × 同一ルールの再報告のみ**を避け、同じ箇所の別の欠陥は報告する
```

- **機械層の結果を agent に再検証させない**（`docs/pipeline-design.md` の Opus 5 節。検証が要るなら別コンテキストの独立層で行う）
- **抑制は `同一 file:line × 同一ルール` に限る。** 過剰抑制は「機械層が浅く検出した箇所の別の欠陥」を消す
- スコープによる除外なので severity 自己フィルタの禁止には触れない（同節の「対象外」に該当）

## 4. 計測

- **機械層の指摘は `findings_class` に数えない**（数えるのは agent が報告した指摘だけ。orchestration-measurement.md `## 16`）
- 効果は `findings_class.lint` の減少として現れる想定。**`judgement` が減ったら「既知」の注入をやめる**（ADR の撤回条件。サンプル 5 回まで判断しない）
- レポート冒頭の 1 行は status に関わらず必ず出す（silent skip を作らない）

## 5. プロジェクト側の宣言（`.claude/review-oracles.sh`）

- **存在自体が宣言**。無ければ `run-oracles.sh` は何も出さず exit 0（後方互換の no-op）
- 契約: exit 0 = 緑 / 1 = 検出あり（stdout に内容）/ 2 = 判定不能。実行時間は数分以内（既定 300 秒で timeout ＝欠測）
- **プラグイン側でコマンドを推測しない**。`package.json` から lint を当てにいくと、誤検出時に任意のコマンドを走らせることになり、プロジェクト非依存の原則も壊れる
