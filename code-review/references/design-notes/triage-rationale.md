# Phase 0 トリアージ設計の根拠と観測ログ（実行時には読まない）

`triage-guide.md` / `triage-dynamic-gates.md` から切り出した「なぜそうなっているか」と、判断待ちの観測データ。**レビュー実行中に読む必要はない** — 規範はガイド本体にあり、ここにあるのは規範を将来ゆるめる／変えるときに必要な背景。

## `## 6` 規模キャップを入れた実測（GitHub issue #96）

effort だけで上限を決めると、小さな PR にも effort 上限いっぱいの体数が張り付く。

**実測**: 9 ファイル / `+116 -22`（うち本番コードは 3 ファイル `+22 -13`、残りはテスト 5 + doc 1）の PR を xhigh で流したところ、explorer 4 + reviewer 10 + specialist 1 + Round 2 explorer 2 = **17 体**が起動し、レポートまで 95 分・締めまで 130 分かかった。

旧 `## 6` は「Phase 0 が明確な判断を下せない場合」限定のフォールバックだったため、**diff シグナルが読めてしまうと規模が上限に一切効かなかった**。

切り分けの原則（ガイド本体にも残してある）: **effort は「1 体あたりどれだけ深く読むか」の指定であって、「何体並べるか」の指定ではない。**

## `## 5.1` wave 数を Phase 0 出力に出した理由（GitHub issue #100 B）

**体数はトークンコストのレバー、wave 数は壁時計のレバー**。並列発行が効いている限り 1 wave の実時間は「wave 内最長の 1 体」で決まるので、壁時計は体数ではなく**直列に積み上がる wave の本数**で決まる。ところが従来ユーザーに見えるのは体数だけで、wave 数は最後まで見えなかった。

## `## 7` 縮小のロールバック条件と監視（v2.39.0 の high 既定縮小）

- **縮小のロールバック条件（v2.39.0 の high 既定縮小）**: 効果は `review:completed` の `agents` / `duration_min` / blocker+critical 件数で監視する。**判定に使えるのは `agents` フィールドを持つサンプルのみ**（= v2.39.0 以降の publish。フィールド存在が publish 側の自己申告版マーカーであり、配布ラグに耐える。旧サンプルは `effort` を持たず high 実行と xhigh 実行を層別できないため、「縮小前との比較」の基準側には使えない — triage-dynamic-gates.md `## 8.5` の「日付では切らない」と同じ流儀）。悪化の検証は旧データ比ではなく、**xhigh/max の明示実行（フル構成）を対照群にした縮小後サンプル内の比較**で行う:

  ```bash
  # effort=high（縮小構成）のレビュー 1 件あたり blocker+critical 平均と fleet 区間の中央値
  # 所要時間は duration_fleet_min で見る（duration_min は締めフローの人間待ちを含む）
  grep '"event":"review:completed"' .claude/events.jsonl | \
    jq -s '[.[] | select(.payload.agents != null and .payload.effort == "high")] |
      if length == 0 then "no data" else
        {n: length,
         hi_avg: (([.[] | .payload.blocker_count + .payload.critical_count] | add) / length),
         fleet_med: ([.[] | .payload.duration_fleet_min // -1 | select(. >= 0)] | sort | .[(length/2|floor)] // "no data")}
      end'
  # 対照群は .payload.effort == "xhigh" or "max" に置き換えて同じ式で出す
  # 帯を揃えるときは select(...) に and .payload.size_tier == "small" 等を足す
  ```

  縮小後 30 日で high 群の hi_avg が対照群比で明確に低い状態が続いたら、まず冗長ペアの high 復帰（次に reviewer 上限 10 復帰）を検討する。サンプルが `no data` のうちは判断しない。印象や単発の見落とし報告だけで戻さない（壊れた・不足した計測を根拠に不可逆な判断をしない。skeptic の high 昇格判断 triage-dynamic-gates.md `## 8.5` と同じ流儀）

**所要時間は `duration_fleet_min` で見る**（v2.41.0 で payload に追加。正本: orchestration-measurement.md `## 14`）。`duration_min`（全体）は締めフローの人間待ちを含み（かつ publisher 間で意味が非対称）、人間の都合で 10 倍振れるため体数調整の効果測定には使えない。体数が効くのは fleet 区間だけ。**比較は `size_tier` を揃えて行う**（v2.40.0 追加）— 所要時間は規模と体数の両方に効かれるため、帯を混ぜた中央値は規模キャップの効果と PR 規模の分布変化を分離できない。

**体数を壁時計のレバーとして扱わない（v2.41.0）**: 並列発行が効いている限り fleet 区間の実時間は「wave 内最長の 1 体」で決まるため、**体数削減の効果は線形ではない**。そして**体数削減が壁時計に効いた証拠は現時点で存在しない** — v2.39.0 / v2.40.0 の縮小を評価できる区間別サンプルが無く、唯一あった 210 分のサンプルも `duration_min`（内訳不明）だったため判定不能だった。`duration_fleet_min` が貯まるまでは、**体数を壁時計の打ち手として動かさない**（体数削減が確実に効くのはトークンコスト）。壁時計を縮めたい場合にまず触るのは ①1 体あたりの探索量（`prompts/reviewer-common.md` の探索予算）②直列 wave 数（`## 5.1` で可視化・skeptic 相乗り triage-dynamic-gates.md `## 8.5`・Round 2 の repo 外スキップ triage-dynamic-gates.md `## 8`。実測は `duration_explore_min` が wave 単価を示す）③メインコンテキストのプロンプト複製量（PR コンテキスト等のファイル経由渡し・orchestration-guide.md `## 3.5`）。**③は `duration_triage_min` では観測できない** — プロンプトを書く行為と Agent call の発行が同一なのでマーカーで分離できず、コストは `duration_fleet_min` に含まれる（orchestration-measurement.md `## 14`）。③の効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る。recall だけ落ちて時間が変わらない改悪を避けるため、**この節のロールバック判断に「時間が長いから体数を減らす」を混ぜない**。

**`review` 由来サンプルは v2.40.0 より前は 1 件も存在しない**（GitHub issue #96 B）。publish が EnterWorktree 配下の cwd 相対パスで行われていたため、`review:completed` は worktree 側の `.claude/events.jsonl` に書かれ、直後の `ExitWorktree(remove)` で worktree ごと消えていた。v2.40.0 で publish 先をメインリポジトリのルートに固定（orchestration-measurement.md `## 13`）するまで、蓄積されていたのは worktree を使わない self-review 由来のみ。**したがって v2.39.0 の high 既定縮小は review 経路については測定できていない** — 判断は v2.40.0 以降のサンプルが貯まってから行う

### 未解決の観測: review 経路の MAJOR がゼロに張り付いている（2026-08-06 / 判定は v2.44.0 サンプル待ち）

蓄積済み 43 件（`review` 12 / `self-review` 31）を集計したところ、**publisher 間で MAJOR の分布が極端に非対称**だった:

| publisher | n | `major_count`=0 の回 | b / c / major / minor 合計 | `severity_inflated`（1 回あたり） |
|---|--:|--:|---|--:|
| `code-review:review` | 12 | **12 / 12** | 0 / 1 / **0** / 27 | 9 件（**0.82**） |
| `code-review:self-review` | 31 | 10 / 31 | 2 / 7 / **78** / 59 | 7 件（0.30） |

- **「PR が綺麗だった」では説明できない**: MAJOR と MINOR は報告マトリクス上どちらも confidence 95+ の同一閾値なのに、review では MINOR が 27 件通って MAJOR が 0 件
- **緩和側がゼロ**: review は `recall_skeptic.surface` が 10/10 で true（= 全件 high-risk surface 判定）。surface-aware 閾値により **MAJOR は 85+ に緩和されている状態で 0 件**。緩和していない self-review が 78 件
- 両 SKILL の scoring 手順（review Step 6 / self-review Step 5）は severity 処理の規約が**同一**であることを確認済み。仕様差では説明がつかない

**考えられる経路**（いずれも出口が MINOR なので `minor_count` に合流する）: ① `severity-inflated` 降格 ② `[scope:out]` 降格（他人の PR は「既存の問題」判定が出やすい）③ confidence 95 未満での skip ④ そもそも reviewer が MAJOR を出していない。

**判定手順**: v2.44.0 で追加した `pre_adjust_counts` が貯まったら orchestration-measurement.md `## 16` の jq を回す。`pre_adjust_counts.major` が **0 に近ければ ④（検出由来）**、**post との差が大きければ ①〜③（調整由来）**。

**それまで scoring 規約を変えない。** 特に「MAJOR/MINOR の `severity-inflated` を無条件降格から保護する」（scoring-guide の不変条件を MAJOR へ拡張する）は precision を直接下げる不可逆な変更であり、**降格由来だと確認できていない段階で入れてはならない**。壊れた・不足した計測を根拠に不可逆な判断をしない（triage-dynamic-gates.md `## 8.5` と同じ流儀）。


