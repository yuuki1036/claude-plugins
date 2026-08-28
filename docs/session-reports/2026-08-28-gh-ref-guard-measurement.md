# gh-ref-guard の設計判断と実測（GitHub issue #162）

`guardrail-protect` に「`gh` の外向き書き込みで実在しない見出しへの参照をブロックする」hook を
入れるにあたり、issue #162 の必須要件だった**パス実在検証を採らないと決めた**。その根拠の一次記録。

## 母集団と再現手順

```bash
gh issue list --state all --limit 400 --json number,title,body,createdAt,comments > issues.json
```

- 対象リポジトリ: `yuuki1036/claude-plugins`
- 取得日: 2026-08-28
- issue 188 件 / コメント 213 件 / 計 531,027 文字

「真の検出 / 偽陽性」は**書いた当時の tree** で判定した（`git rev-list -1 --before <createdAt> main`）。
後のリネームで陳腐化したものを偽陽性に数えないため。

## 結果

| 検証ルール | 候補 | 真の検出 | 偽陽性 |
|---|---:|---:|---:|
| パス実在（issue #162 の記載どおり） | 203 unique | 0 | 116（57%） |
| パス実在（プラグインルート相対 + 履歴を許容） | 203 unique | 0 | 41（20%） |
| `#anchor` 実在（見出し前方一致） | 151 参照 | 8 | 0 |

パス実在の偽陽性 41 件はすべて正当な記述だった:

- プラグインルート相対の参照（最大の族）— `scripts/review-retro.sh` で `code-review/scripts/review-retro.sh` を指す慣習
- placeholder — `path/to/doc.md` / `evals/reports/recall-YYYYMMDD.md` / `tests/foo.spec.ts`
- 他リポジトリのパス — `src/lib/prisma.ts` / `frontend/AGENTS.md`
- 実行時生成ファイル（gitignored）— `.claude/session-context.md`
- そもそもパスでない — `React/Next.js` / `README/CLAUDE.md`（A/B の並記）/ `a/...` `b/...`（diff の接頭辞）

`failure-journal` の `claimed-fact-without-source` 全 13 件を 1 件ずつ当たったが、
**パス実在検証で止まるものは 0 件**。唯一隣接する 2026-08-14「引用元ドキュメントに該当記述が
実在するか確認しなかった」は、ファイルは実在して**記述が不在**なので anchor 検証の領分。

## 「真の検出 8 件」の内訳（`## 5` の重複を含む実数）

| 参照 | 実態 |
|---|---|
| `orchestration-measurement.md ## 5` ×5（#155 / #149） | この分冊は `## 13` 始まり。実測ベースラインは `## 15` |
| `design-notes/pending-optimizations.md ## 11`（#153） | 実在は `## 10` まで |
| `triage-dynamic-gates.md ## 10`（#110） | 実在は `## 9` まで |
| `references/orchestration-guide.md ## 1.2`（#117） | 当時は実在。後の改稿で陳腐化 |

**書いた当時の tree で判定すると 7 件、現 HEAD で判定すると 8 件**（最後の 1 件が当時は実在した）。
実装の docstring と README で 7 / 8 が食い違っていたのはこの差を書き分けていなかったため。
**hook が実際に判定するのは現 HEAD なので、出荷値は 8 件を使う。**

## この母集団の限界（セルフレビューで判明・2026-08-28）

**上表の「偽陽性 0」は導入前の issue 本文に閉じた過去の観測であり、hook の性質ではない。**
セルフレビューで、実際に hook が掛かる入力（今後書く本文・リポジトリ内 md の引用）に当てると
**5 系統の偽陽性**が出ることを再現した。すべて修正済みで、修正後は
**repo 全 297 md の実在見出し 3401 件で偽陽性 0**（回帰テスト `RealRepositoryRegressionTest`）。

| 系統 | 原因 | 対処 |
|---|---|---|
| 行頭インラインコードスパン / 未終端フェンス | `in_fence` の単純トグル | 開始記号の種類と長さで対応を取り、未終端は判定不能として黙る |
| H4 以上の見出し | `ANCHOR_RE` の `#{1,3}` | `#{1,6}` に広げる |
| 複合参照（`## 6 / ## 8`） | `[^`\n]+` の貪欲一致 | anchor に `#` が残る形は判定しない |
| `gh` を呼ばないコマンド | 事前フィルタの部分文字列 glob | `shlex` トークンで `gh <issue\|pr> <write>` を判定 |
| GitHub の anchor slug | 大小文字を区別した前方一致 | slug 正規化して突合 |
