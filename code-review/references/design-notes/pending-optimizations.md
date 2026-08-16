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

> **1.（meta-reviewer と反証レイヤーの並列化）は v2.61.0 で実装した**（GitHub issue #122）。根拠は `orchestration-rationale.md`「meta-reviewer と反証レイヤーを同一 wave にした経緯」へ移した。

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

## 5. publish 脱落ガードの Stop hook 昇格

**現状**: `review-timing.sh publish-pending` を SKILL の必須ステップ冒頭（self-review Step 7 / review 締めフロー 5）で呼ぶ。判定自体は決定的（`t2` があって `pub` が無い）だが、**呼ぶかどうかは LLM 依存**。

**案**: Stop hook 化する。`.claude/settings.json` の `auto-quality-check.sh` と同型で、ターン終了時に `${TMPDIR}/claude-code-review-<uid>/review-start-*` を glob して未 publish の計測ファイルが残っていれば通知する（`--pr N` を知らなくても glob で当たる）。CLAUDE.md「ルール配置の意思決定」の昇格基準のうち **①判定が if/grep で表現できる ②修復コストが高い（打点は復元不能）** の 2 つに該当する。

**まだ入れていない理由**:

- **誤検知の設計が未確定**。glob は**他セッション・他リポジトリのレビュー**の計測ファイルにも当たる（`TS_FILE` の slug は worktree ルート由来で、hook 側からは自分の回かどうかを判定できない）。並行レビューが常態のマーケットプレイス前提（`dev-workflow:worktree-setup`）では、鳴りっぱなしになって「⚠️ が出たときだけ行動する」契約を壊すリスクがある
- code-review は現在 SessionStart hook しか持たず、**新規 hook の追加は `claude-meta:component-addition-advisor` の退路確保ゲートの対象**（CLAUDE.md）。既存拡張（SKILL 側のガード）で足りるかを先に測る
- **判断材料**: `measurement_gaps` の `late-publish` の発生率（`review-retro.sh` が gap 種別ごとに自分の分母で判定する / v2.66.0）。SKILL 側ガードで頻度が落ちなければ hook へ上げる

## 6. 既定 high で「加減算で報告閾値を超えた MAJOR」を反証対象に含める

**動機（GitHub issue #136）**: `scoring-guide.md` の「複数エージェント検出 +15」は MAJOR を単独で報告閾値（95）へ押し上げられるのに、**押し上げの妥当性は誰も検証していない**。既定 high の反証ゲートは非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）だけなので、BLOCKER / CRITICAL が 0 件の回では反証が構造的に不発になり、**severity 過大が最も起きる帯が最も較正されない**。

**案**: 既定 high のゲートに「**加減算を除いた base confidence が閾値未満**で、加減算後に閾値を超えた MAJOR」を足す。追加バッチの上乗せゲート（`## 9` の `confidence + 15 >= 報告閾値`）と鏡像の関係（あちらは「+15 の最良ケースでも届かないなら no-op」、こちらは「+15 が無ければ届かなかった＝押し上げが未検証」）。

**採らない理由（v2.66.0 時点）— 既定パスに直列 wave を 1 本足すため**:

- meta-reviewer は xhigh / max 起点なので、**既定 high では 4.6 + 4.9 の wave がそもそも存在しない**回が多い。BLOCKER / CRITICAL 不在の回にこのゲートを足すと、**今まで wave が無かったところに wave が生える**（実測の wave 単価は 6〜16 分 / `triage-guide.md ## 5.1`）。token だけの増加ではない
- **xhigh / max では既に MAJOR 全件が対象**（`## 9` の表）。つまり本案が効くのは high 限定で、そこがちょうど wave を新設する帯にあたる
- **`## 9` には既にゲート幅の再監視条件がある**（`gate_schema >= 2` が 10 件かつ `no-eligible-findings` 50% 以上）。v2.65.0 で `fired` / `skip_reason` を記録し始めたばかりで**実測は 2/2 件**。判断の材料は揃いつつあるので、**先に条件を満たすまで待つ**のが repo の流儀（「サンプルが無いうちは判断しない」/ `triage-guide.md ## 7`）

**issue の前提の訂正（実データで確認）**: #136 は実例を「self-review・xhigh / medium・MAJOR 7 件で `no-eligible-findings`」としているが、`.claude/events.jsonl` の該当サンプル（MAJOR 7 件の回）は **effort=high** だった。`skip_reason` を持つ 2 件も両方 high で、**どちらも設計どおりの不発**。xhigh で MAJOR が対象外になっていた事実は無い。

**先に入れたもの**: レポート文言（`no-eligible-findings` のとき「未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）」）。誤読（「対象 0 件」＝「検証したが問題なし」）はゲート幅と独立に潰せるため、コストゼロの側だけ先に採った。

**再判断の材料**: `review-retro.sh` の反証シグナル（`gate_schema >= 2` の母集団 10 件 / `no-eligible-findings` 50% 以上）。点灯したらこの案と「high の非対称ゾーンに MAJOR の一部帯を足す」案（`## 9`）を併せて検討する。

## 7. explorer の一括発行と wave 打点を Agent hook（独立した観測者）へ移す

**動機（GitHub issue #135）**: 並列発行の規約（`orchestration-guide.md ## 0`）と wave 打点（`## 14`）は**どちらもオーケストレーターの自己申告**で、破っても実行中は何も起きない。しかも **2 が 1 を検知不能にする**: `agents.explorer_waves` は「打点の行数 = wave 数」で直列発行を暴くための指標（issue #122）なのに、その行を書くのがオーケストレーター自身なので、**打点を忘れた瞬間に違反の証拠も同時に消える**。実測でも `explorer_waves` は導入以来まともに観測できていない。

**案**: `Agent` の PreToolUse / PostToolUse hook で打点する。**発行時刻**を記録すれば wave 判定は明快 — 一括発行なら発行時刻がほぼ同時刻に固まり、1 体ずつ直列に出すと前の agent の実行時間ぶん離れる（完了時刻のクラスタリングより閾値が要らない）。検知したい対象（オーケストレーターの手順遵守）と検知の担い手が分離するのが要点。

**入れていない理由 — 発火するかを確認できていない**:

- **subagent のツール名が `Agent` であることは確認済み**（CC 2.1.233 の transcript 実測）。未確認なのは「`PreToolUse` / `PostToolUse` が `Agent` に対して発火するか」で、**hook の発火記録は transcript に残らない**ため既存データからは判定できない
- **セッション内での実験は偽陰性を返しうる**。`settings.json` に hook を足しても実行中セッションが再読込する保証が無く、「発火しなかった」がツール非対応なのか設定未反映なのか切り分けられない
- **検証手順**: ①`.claude/settings.json` に `PostToolUse` / matcher `Agent` の hook（マーカーファイルに 1 行 append するだけ）を足す ②**セッションを再起動する** ③任意の agent を 1 体起動する ④マーカーが増えたか見る。発火するなら `tool_name` の実値（`Agent` / `Task`）も同時に控える
- **repo の Gotchas「hooks.json の if:/matcher に単独依存しない」に従い、自己判定を必須にする**: `tool_name` を `safe_hook_input` で読み、さらに**レビュー中か**（`review_path timing` が存在するか）を見てから打点する。そうしないと全セッションの全 Agent 呼び出しで発火する
- **新規 hook の追加は `claude-meta:component-addition-advisor` の退路確保ゲートの対象**（CLAUDE.md）。code-review は現在 SessionStart hook しか持たないので、判定を経てから入れる

**先に入れたもの（案 B / v2.66.0）**: publish の WARN に「レポート末尾に `⚠️ 計測: ...` を 1 行追記せよ」という具体指示を足し、両 SKILL に追記規約を書いた。stderr の警告をユーザーに見える場所へ移すだけで、**自己申告構造そのものは変わっていない**（本命は上の案）。

**案 C（不採用）**: fan-out を Workflow スクリプト（`parallel()` / `pipeline()`）へ移す。explorer wave / reviewer wave / 反証バッチは構造的には `parallel()` そのもので、散文で「一括発行せよ」と指示する代わりに制御構造で保証できる、という筋は成立する。ただし skill の全面書き換えになり費用対効果が悪い。
