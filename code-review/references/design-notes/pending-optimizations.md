# 未実装の最適化案（実行時には読まない）

実測で効きそうだと分かっているが、**まだ入れていない**打ち手。トレードオフか複雑度のどちらかで判断が要るものを置く。実装したらこのファイルから消して、根拠を対応する rationale ファイルへ移す。

## 計測の基準値（改修効果はここと比べる）

v2.49.0 の「agent 側ツール使用規約」を入れる**前**の実測。PR 1 件・effort xhigh・規模 medium・23 体（GitHub issue #104 のセッション）:

| | msgs | tool calls | output | cache_write | cache_read |
|---|---:|---:|---:|---:|---:|
| main | 167 | — | 675k | 3,126k | 43,152k |
| sub (23 体) | 1,202 | 558 | 483k | 7,676k | 115,896k |

- コスト比（output×5 / cache_write×1.25 / cache_read×0.1 で重み付け）: **cache_read 45% / cache_write 38% / output 17%**
- 1 体平均: 52 msgs / 24 tool calls / cache_write 334k / cache_read 5,039k / peak context 142〜185k
- **バッチ率 1.00**（558 回のツール呼び出しが 100% 単発）、**Read の範囲指定率 16%**、**Bash の `cd` 始まり 61%**

次に実 review を流したら `scripts/measure-tokens.sh` で同じ指標を取り、この表と比較する。

## 1. meta-reviewer と反証レイヤーの並列化（直列 wave −1）

**現状**: Phase 5.6（meta）→ Phase 5.9（反証）の直列。どちらも reviewer 完了後に走る。

**着眼**: 両者は**互いに独立**している。meta は findings を**足す**係、反証は**潰す**係で、入力はどちらも「reviewer の全指摘」。依存があるのは「meta が足した指摘も反証対象に含める」という一点だけ。

**案**: meta と反証を同時発火し、**meta が足した指摘だけを追加の反証バッチに回す**。meta が 0 件なら wave が 1 本減り、足した場合だけ現状と同じ wave 数になる（期待値で削減）。

**採らない理由（現時点）**: 実装の複雑度が上がる（反証を 2 段に分ける・verdict の突合が 2 系統になる）。かつ **xhigh / max でしか meta が走らない**ので、既定 high の運用では効果ゼロ。壁時計の実測（`duration_fleet_min`）が貯まって「meta の wave が実際に効いている」と分かってから入れる。

## 2. メインコンテキスト側のツール呼び出しバッチ化

**現状**: agent 側には v2.49.0 で規約を入れたが、オーケストレーター（main）には入れていない。main も 167 msgs / cache_read 43M を使っている。

**採らない理由（現時点）**: main の呼び出しは agent と違い**逐次判断が本質**のものが多い（Phase 0 の判定 → 構成決定 → 起動、のように前の結果が次を決める）。独立に並べられるのは Step 1〜2 の情報収集くらいで、既に `triage-signals.sh` が 1 回の Bash に畳んである。**効果が小さいのに SKILL 本文が伸びる**（SKILL は常時読み込みなので、書いた分だけ確実にコストが増える）ほうが損。agent 側の効果を測ってから再検討する。

## 3. `reviewer-common.md` の圧縮

**現状**: 21.8k bytes ≒ 9.6k tokens。これを全 agent が読むので、23 体なら 221k tokens。

**採らない理由（現時点）**: cache_write 全体（7.7M）の **3%** にしかならない。一方で共通指示は precision を支える契約（評価 6 原則 / claim grounding / 探索予算 / 出力フォーマット）の集まりで、削ると recall・precision に直接効く。**費用対効果が悪い**。圧縮するなら 1〜2 を先にやる。

## 5. reviewer effort profile の A/B（`differentiated` の採否 / v2.51.0 で仕込み済み）

**現状**: reviewer は high 帯で全員 `high`（`uniform`）。userConfig `reviewer_effort_profile=differentiated` で、high 帯に限り低密度観点だけ `medium` に下げられる実験フラグを入れた（マップ: triage-guide.md `## 7.1`）。**まだ採否を決めていない**。

**仮説**: Opus 5 の素の性能なら、低密度観点（comment-accuracy / pattern-consistency / config / dependency / type-design / ui-quality / cross-cutting / doc-substance / test-quality / api-design）は `medium` でも recall が落ちない。

**効果の見積もり（過大評価を避ける）**: effort が削るのは output/thinking トークン。コスト内訳は cache_read 45% + cache_write 38% + output 17%（本ファイル冒頭の基準値）なので、**削れるのは 17% の一部だけ＝ modest**。壁時計も wave 数と探索往復が支配で thinking 量ではないため、短縮も小さい。**「大きく効く」と期待しないこと**。

**A/B 手順（`differentiated` を採用してよいかの判定）**:
1. **同一 PR・同一 diff** で 2 回流す。arm A = `uniform`（既定）/ arm B = `reviewer_effort_profile=differentiated`。`size_tier` は自動で揃う（同一 diff のため）
2. 各 arm で計測を取る:
   - **recall（最重要）**: レポートの severity 別件数と `pre_adjust_counts` の **blocker+critical**。`review:completed` payload の `reviewer_effort_profile` で arm を層別
   - **トークン**: `scripts/measure-tokens.sh`（`## 17`。`sub.output` / `sub.cache_write` の差を見る。同一 PR・1 セッション 1 レビューで取る）
   - **壁時計**: `duration_fleet_min`
3. **判定基準**: arm B の **blocker+critical recall が arm A から落ちていない**ことが採用の必要条件。落ちていなければトークン/壁時計の差分を採用のうまみとして評価する。1 PR では足りず、`size_tier` を揃えた複数 PR（できれば high-risk surface を含む PR を 1 本以上）で確認する（このリポの流儀＝サンプルが貯まるまで判断しない）
4. **結論後の後始末**:
   - **採用**: `differentiated` を既定化するか検討し、実験フラグ（userConfig）と payload の `reviewer_effort_profile` の暫定注記を整理する
   - **不採用**: フラグ・マップ（triage-guide.md `## 7.1`）・payload フィールド・本節を撤去する（実験スカフォールドを残さない）

**注意**: 高密度観点（bug-detection / security / spec-compliance / claude-md-compliance / error-handling / migration / performance）と specialist を `medium` に混ぜて測らないこと。難所の recall を落とすと A/B の結論が「安く見えて実は劣化」に倒れる。検証層（meta / skeptic / 反証）は 1 体固定なので profile 対象外のまま。

## 4. explorer wave の廃止（直列 wave −1）

**現状**: explorer → reviewer の直列 1 wave。explorer の結果を reviewer へ選択的に注入する。

**案**: explorer を廃し、reviewer に「必要なら自分で探索」させる。

**採らない理由**: reviewer の探索量（＝ cache_write と往復）が増えるので、wave を 1 本減らす代わりに wave 内の時間が伸びる。**トレードオフの向きが不明**なうえ、explorer の「判定せず事実だけ集める」独立性は reviewer の確証バイアスを避ける設計上の要でもある。`duration_explore_min`（v2.43.0 で追加）が貯まって wave 単価が分かってから判断する。
