# セッションレポート: code-review 計測系の決着と一括発行違反の検出

- **日付**: 2026-08-23（前日 2026-08-22 から継続）
- **対象**: `code-review`（v2.82.2 → **v2.85.1**）
- **コミット**: `8fc8df6` / `11b07ca` / `915de05` / `39808fb` / `51247c4` / `9024d5c` / `1bd8d4e`（すべて push・CI green）
- **クローズした issue**: #153 / #164

---

## 1. 何を持ち越すか（次セッションはここだけ読めばよい）

| # | やること | 状態 | どこに書いてあるか |
|---|---|---|---|
| 1 | **[#162](https://github.com/yuuki1036/claude-plugins/issues/162)** guardrail-protect の hook（gh の外向き書き込みで参照の実在性を検証） | 計測済み・実装待ち。`claimed-fact-without-source` が**全期間 11 回で最多** | issue 本文 |
| 2 | **[#163](https://github.com/yuuki1036/claude-plugins/issues/163)** CLAUDE.md に「未知データの構造を確かめる」手順則 | 同上（30 日 3 回 / 全期間 5 回） | issue 本文 |
| 3 | **effort profile の arm B を 1 回回す** | 34 版・24 レビューで**実行 0 回**。次の self-review で `reviewer_effort_profile=differentiated` を指定するだけ | `code-review/references/design-notes/pending-optimizations.md ## 5`「次の 1 回で取ること」 |
| 4 | `measure-tokens.sh` の **per-agent 内訳** | 3 の前提。sub を合算しているので run 内の対照比較ができない | 同上 |
| 5 | `wave-split` の**偽陽性率**を貯めて WARN 化を判断 | 判定可能 6 / 検出 2 / **偽陽性 0**。skeptic fallback の回が未観測なので保留 | `orchestration-measurement.md ## 16` |
| 6 | **[#154](https://github.com/yuuki1036/claude-plugins/issues/154) 2/3・[#150](https://github.com/yuuki1036/claude-plugins/issues/150)** | 「別マシン待ち」ではなく**未実行**。PR レビューが発生するマシンで `review-retro.sh --logs` / `review-backfill.sh --projects` を回せば今日判定できる | 各 issue |

**1 と 2 は今日その型を実際に踏んでいる**（下の 4 節）。件数の多さでは 1、着手の軽さでは 2。

---

## 2. 入れたもの

### 2.1 #153 の決着（`8fc8df6`）

起票時の主張「反証 1 体を起動するために fleet の 56-70% を払っている」が **指標の読み違い**だった。`max_inter_wave_sec` は **wave N 起動 → wave N+1 起動**なので、`wave_sizes` が 2 本の回では `dispatch.span_sec` と一致するのが**定義上の恒等式**であって「内訳が確定した」ではない。

`wave_clock` で末尾 wave の `end - start` を直接測ると:

| 実測 | 値 |
|---|---|
| 末尾 1 体 wave の占有率 | **中央値 14.8%**（11.6〜25.5% / n=3） |
| fleet に占める orchestrator の待ち | **中央値 8.4%**（最大 14.3% / n=6） |

**fleet の約 92% は agent が回っている時間。** wave の本数を削る余地は残っていない（explorer wave 廃止は `## 4` で、末尾 1 体 wave は `## 11` で決着）。壁時計の打ち手は 1 体あたりの実行時間（#156）へ移した。

### 2.2 後付け計測 CLI（`11b07ca` / `9024d5c`）

`code-review/scripts/review-backfill.sh`。publish 済みイベントの窓（`[t0, t2]`）を `duration_*` から逆算し、生存している `subagents/agent-*.jsonl` に `measure-tokens.sh` を当てて `dispatch` / `tokens` を後付けする。**読むだけで publish しない / retro には混ぜない**（精度が違う値を層別に混ぜると読めなくなる）。

これで #153 が n=1 → 6、#156 が n=2 → 7 になり、判定下限を超えた。窓が汚れる回は捨てる（区間欠測 / 窓外の同セッション agent / 窓が別レビューを内包）。

### 2.3 一括発行違反の全層検出（`39808fb`）

既存の検出は 2 経路とも一部しか見ていなかった:

- `dispatch.verdict == "serial"` は**単独 wave 3 連続**を要求
- `agents.explorer_waves` は **explorer 層しか数えない**

実測 `2026-08-22T04:09` の回は reviewer `bug-detection` だけが 9 分早く単独発行され、`layered`（正常）と判定されていた（**fleet span の 20%**）。`dispatch.waves_expected` と `measurement_gaps` の `wave-split` を追加。

---

## 3. 途中で方針を 3 回ひっくり返した

いずれもユーザーの「精査して」で見つかった。**そのまま進んでいたら 3 件とも誤ったものが入っていた。**

1. **末尾 wave の費用**（上記 2.1）— 恒等式を証拠として読んでいた
2. **`meta.json` の `description` で層を分類する案** — 25 セッションの実データに当てて棄却。書式が LLM の自由文で安定せず（`reviewer bug-detection` / `Review CLAUDE.md compliance` / `R1 bug-detection` / `doc 整合性レビュー（R1）` が混在）、**偽陰性は静か**。加えて窓を切らないと別レビューの agent を数え、Round 2 の正当な分割も違反にする。代わりに**既存フィールドの算術**（期待 wave 本数）にしたら実サンプル 6 件で 6/6 正解・偽陽性 0
3. **effort profile の A/B を畳む提案** — 「走らせていないから畳む」は**循環**。しかも **arm B は 1 run の中で高密度=high / 低密度=medium に割れる**ので、ペア実行なしで対照比較ができる設計だった。見落としたまま撤去していたら 34 版寝ていた実験を根拠薄弱に捨てていた

---

## 4. 今日踏んだ失敗（candidates に記録済み）

- **`claimed-fact-without-source`**（→ #162）× 2: ①「#161 はクローズ漏れかも」を issue 本文を読まずコミットメッセージだけで断定（実際は「サンプル 0 件なので open 維持」と明記されていた）②`agents` の突合式を正本を読まず意味から再構成し、`-1` の偽の食い違いを出した
- **`assumed-api-shape-unverified`**（→ #163）: `wave_clock` の `end` が常に int だと仮定して `TypeError`。実データが全部埋まっていたため表に出ず、**式の一致を見る結合テストを書いて初めて踏んだ**
- **テスト fixture が境界の片側しか無い** × 2: `--derived-*` の単独形（#164 で修正）と、直後に自分で書いた `waves_expected` の explorer 0 体（CI の変異スモークが検出）。**同じ型を同日に 2 回**

---

## 5. 気づいたこと（規約候補）

- **直近 40 issue（#125〜#164）のうち 30 件が計測・検証基盤**で、実際にコストか品質を動かしたのは 6 件（すべて #147 以前）。計測を足すたびに「サンプルが貯まってから」が増えて判断が後ろにずれる構造がある。**ボトルネックは計測不足ではなく、指定済みの A/B が走っていないこと**
- **`bump-version.sh --sync` は `vNEXT` を書き換えるので、SSoT pin の打ち直しは bump の後**（順序を逆にすると即座に古くなる。今日 2 回打ち直した）
- **回帰テストは実装を守り、変異テストはテストの母集団の偏りを守る。** ローカル 765 件緑・変異 0% でも、CI の変異スモークが新規コードの穴を拾った（`--strict` は CI にしかない）
