# high-risk recall 回帰 fixture（GitHub issue #75）

code-review の high-risk recall 補強（Tier3 v2.30.0 / Tier2 v2.31.0 / Tier1 v2.32.0）が、
実レビューで見落とした実バグ（issue #75 #1 / #7）を捕捉できるかを測る回帰 fixture。
設計は [design doc](../../../.claude/designs/20260703-code-review-recall-high-risk-surface.md) の「検証方法」を実装したもの。

> `evals/runner.py` は「トリガーフレーズ → skill 選択」の決定的回帰のみを扱う。
> この fixture は **レビュー指摘レベルの recall / precision** を測るランタイム検証で、
> LLM 実行を伴うため runner.py には統合しない（半自動 runbook 方式）。

## fixture 一覧

| id | 種別 | 再現対象 | 期待 |
|---|---|---|---|
| `01-value-flow-insert` | recall | #75 #1: 空文字が `?? null` を素通り → NUMERIC 列へ生 INSERT → 22P02 → 500 | **CRITICAL 以上**で報告 |
| `07-handler-bypass` | recall | #75 #7: 共有エラーハンドラ迂回で SERVICE_UNAVAILABLE の error ログが消える | **MAJOR 以上**で報告 |
| `90-precision-minor-unit` | precision | 副単位ゲート（正しいコード）への誤検出 | CRITICAL/MAJOR が**出ない** |

期待値の詳細（対象ファイル・キーワード・判定根拠）は [expected.yaml](expected.yaml)。

## 実行手順（半自動 runbook）

### 前提

- `code-review` plugin **>= 2.32.0** がインストール済み（Tier1 の skeptic / surface-aware 閾値を含む）。
  古い場合は `/update-all` か `claude plugin update code-review` で更新する
- effort は **xhigh** で実行する（self-review skill の frontmatter 既定。skeptic の起動条件）

### 1 fixture の実行

```bash
# 1. fixture repo を構築（surface 判定の発火チェックまで自動）
cd evals/fixtures/recall
./setup.sh 01-value-flow-insert

# 2. 出力された temp dir で self-review を実行（対話モード必須・下記注意）
cd <出力された target dir>
claude
# プロンプト: 「コミット前にセルフレビューして」

# 3. レポートを expected.yaml と照合して記録
```

> **⚠️ headless（`claude -p`）+ plan mode では skill が起動しないことがある**
> （2026-07-04 スモークで確認。素の Claude の単騎レビューになり、Tier1 パイプラインを
> 測れない）。本計測は**対話モードで実行**し、出力に **「Phase 0 トリアージ結果」表が
> 出ること**で skill 起動を確認してから記録する。skill 起動が確認できない run はカウント
> せず再実行する。
>
> **合成 fixture の解釈上の注意**: fixture は最小 diff（実 PR より探索空間が狭い）なので
> 実バグより見つけやすい。PASS は「デグレしていない」ことの回帰確認であり、
> 「実バグ級を必ず捕捉できる」の証明ではない。

### 判定ルール

- **recall fixture（01 / 07）**: k=3 回実行し **2 回以上**で期待指摘（severity・対象ファイル・キーワード）が
  報告されれば PASS。LLM の非決定性を吸収するため 3/3 は要求しない
- **precision fixture（90）**: k=3 回実行し **1 回でも** `false_positive_patterns` に合致する
  CRITICAL/MAJOR が出たら FAIL（誤検出の復活は surface-aware 緩和の失敗を意味するため厳格）
- 01 では **skeptic（Phase 4.8）が起動したこと**もレポートで確認する
  （起動しなかった / 失敗した場合は `missing_coverage` に `recall-skeptic:` が出るはず。
  silent 失敗はそれ自体が Tier1 のバグ）

### 結果の記録

実行結果は `evals/reports/recall-YYYYMMDD.md` に以下の形式で記録する:

```md
# recall fixture 実行結果 (YYYY-MM-DD, code-review vX.Y.Z)

| fixture | run | 期待指摘の報告 | severity | skeptic 起動 | 判定 |
|---|---|---|---|---|---|
| 01 | 1/3 | ✅ | CRITICAL | ✅ | - |
| ... | | | | | |

総合: 01 PASS (3/3) / 07 PASS (2/3) / 90 PASS (0/3 FP) → recall 回帰 PASS
```

判定後、design doc の「実装状況」に結果と `last-validated` を反映する。

## Tier1 縮小の出口条件（design doc open「Tier1 打ち切り条件」）

01 / 07 が **skeptic なし（`enable_recall_skeptic: false`）でも安定して捕捉できる**場合、
Tier2（敵対的入力逆算 + 帰結接続義務化）だけで十分な可能性がある。その場合は
skeptic の起動ゲートをさらに絞る（または既定 false にする）縮小判断の材料にする。
比較実行: 同じ fixture を userConfig `enable_recall_skeptic: false` で k=3 追加実行し、
捕捉率の差分を見る。
