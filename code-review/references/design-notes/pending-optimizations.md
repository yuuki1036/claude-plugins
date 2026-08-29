# 未実装の最適化案（実行時には読まない）

実測で効きそうだと分かっているが、**まだ入れていない**打ち手。トレードオフか複雑度のどちらかで判断が要るものを置く。実装したらこのファイルから消して、根拠を対応する rationale ファイルへ移す。

## 計測の基準値（改修効果はここと比べる）

v2.49.0 の「agent 側ツール使用規約」を入れる**前**の実測。PR 1 件・effort xhigh・規模 medium・23 体（GitHub issue #104 のセッション）:

> **世代は Opus 5 期の実測**（`models` を payload に載せる前なので retro 上は `unrecorded` に落ちる / GitHub issue #191）。世代を踏み下げると 1 体あたりのコストも recall も動くので、**別世代の実測をこの表と直接比べない**。比べるなら世代を明記したサンプル同士で行う

| | msgs | tool calls | output | cache_write | cache_read |
|---|---:|---:|---:|---:|---:|
| main | 167 | — | 675k | 3,126k | 43,152k |
| sub (23 体) | 1,202 | 558 | 483k | 7,676k | 115,896k |

- コスト比（output×5 / cache_write×1.25 / cache_read×0.1 で重み付け）: **cache_read 45% / cache_write 38% / output 17%**
- 1 体平均: 52 msgs / 24 tool calls / cache_write 334k / cache_read 5,039k / peak context 142〜185k
- **バッチ率 1.00**（558 回のツール呼び出しが 100% 単発）、**Read の範囲指定率 16%**、**Bash の `cd` 始まり 61%**

次に実 review を流したら `scripts/measure-tokens.sh` で同じ指標を取り、この表と比較する。

> **1.（meta-reviewer と反証レイヤーの並列化）は v2.61.0 で実装した**（GitHub issue #122）。根拠は `orchestration-rationale.md`「meta-reviewer と反証レイヤーを同一 wave にした経緯」へ移した。

## 2. メインコンテキスト側のツール呼び出しバッチ化（**冒頭だけ採用 / 一般則は不採用** / GitHub issue #147）

**採用したぶん**: 情報収集フェーズの隣接呼び出しだけを 1 本にまとめた — self-review の Step 1 + 1.4（`review-timing.sh start` / base 検出 / `triage-signals.sh` / `detect-recent-review.sh` = 3 往復 → 1）と review の Step 2 + 2.4（2 → 1）。**判断基準は「間に LLM の判断が挟まるか」**であって、コマンド同士が独立かどうかではない。後段が前段の**出力を読んで決める**なら分ける、同じシェルの変数とファイルを使うだけなら畳む。

**含めなかったもの**:
- **機械層の先行実行（self-review 1.7）**。直前の 1.4 に「中止する」＝ agent を 1 体も起動せず終える経路があり、lint / 型 / テストを前倒しすると**中止しても払い戻せない実行時間**を先に払う
- **review の Step 1**。`gh pr checkout` の失敗が中止経路で、失敗したまま `triage-signals.sh` を走らせると base branch の diff を掴む

**一般則としては今も採らない**: main の呼び出しは agent と違い**逐次判断が本質**（Phase 0 の判定 → 構成決定 → 起動）。畳める箇所は上の 2 つで打ち止めで、残りは全部「前の出力を読んで次を決める」形をしている。

**効果の見積もりは issue #147 の値より小さい（過大評価に注意）**: issue は「main は 1 往復あたり平均 350k」から 2 往復ぶんを見積もっていたが、**`cache_read` は 往復回数 × その時点の文脈量**なので、往復単価はセッション後半ほど高い。ここで畳んだのは**セッション中で文脈が最も小さい冒頭**であり、平均単価を当てると数倍過大になる。往復数でも main 42 往復のうち 2 本（≒5%）にすぎない。**「往復を減らせば効く」は正しいが、減らす場所によって単価が桁で違う**ことを次に測るときの前提にする。

## 3. `reviewer-common.md` の圧縮

**現状**: 21.8k bytes ≒ 9.6k tokens。これを全 agent が読むので、23 体なら 221k tokens。

**採らない理由（現時点）**: cache_write 全体（7.7M）の **3%** にしかならない。一方で共通指示は precision を支える契約（評価 6 原則 / claim grounding / 探索予算 / 出力フォーマット）の集まりで、削ると recall・precision に直接効く。**費用対効果が悪い**。圧縮するなら 1〜2 を先にやる。

## 5. reviewer effort profile の A/B（`differentiated`）— **実測して不採用で決着**（v2.89.0 / GitHub issue #171）

**結論: 撤去した。** userConfig・マップ（旧 triage-guide `## 7.1`）・両 SKILL の分岐・payload テンプレート・orchestration-guide の注記をすべて削除した（payload の `reviewer_effort_profile` は**旧サンプルの層別のため語彙だけ残す** — `orchestration-measurement.md ## 16`）。

**仮説**: Opus 5 の素の性能なら、低密度観点（comment-accuracy / pattern-consistency / config / dependency / type-design / ui-quality / cross-cutting / doc-substance / test-quality / api-design）は `medium` でも recall が落ちない。落ちなければ output/thinking ぶんを節約できる。

**実測**（2026-08-25 / self-review / medium 帯 / reviewer 5 体を high 2 + medium 3 に割った 1 run 内の対照）:

| 群 | 体数 | subagent tokens 中央値 | 実行時間 中央値 |
|---|---:|---:|---:|
| `high`（bug-detection / claude-md-compliance） | 2 | 201,532 | 9.7 分 |
| `medium`（test-quality / doc-substance / comment-accuracy） | 3 | 197,907 | 10.4 分 |

**差が出なかった。** 事前見積もり（effort が削るのは output/thinking で、コスト内訳は cache_read 45% + cache_write 38% + output 17% なので**節約は modest**）と整合する。

**recall は測っていない**（この回は BLOCKER / CRITICAL が 0 件で指標が存在せず、反証レイヤーも `no-eligible-findings` で未実施）。**それでも不採用にできる**のは、②で差が出ない以上 recall がどちらでも結論が変わらないため — recall が同じならコストが下がらないので採用する意味が無く、recall が落ちるなら当然不採用。

**再検討の条件**: **無い。** 「effort を focus 別に差別化する」という発想を再び持ち出すときは、まず**コスト内訳のどの項に効くのか**を確かめること（この案は 17% の項の一部にしか効かず、それが実測で観測限界を下回った）。**「走らせていないから畳む」で畳んだのではない** — 34 版寝ていた実験を 1 回走らせた結果として畳んだ。

**副産物**: この 1 回で `models`（#169）と `appendix`（#168）の初の実サンプルが取れ、`waves` の変数上書きによる恒常的な偽陽性（v2.84.0 で混入 / v2.88.2 で修正）を検出した。**実験フラグの決着そのものより、走らせたこと自体の収穫が大きかった。**

## 4. explorer wave の廃止（直列 wave −1）— **採らないで決着**（v2.78.2 / GitHub issue #155）

**現状**: explorer → reviewer の直列 1 wave。explorer の結果を reviewer へ選択的に注入する。

**案**: explorer を廃し、reviewer に「必要なら自分で探索」させる。

**保留条件は満たされた**: 旧版の保留理由は「`duration_explore_min`（v2.43.0 で追加）が貯まって wave 単価が分かってから判断する」だった。n=29 / 中央値 **6 分**（`orchestration-measurement.md ## 15`）で材料が揃ったので決着させる。

**採らない理由**:

- **explorer wave は直列 wave の中で最も安い**（6 分。reviewer 以降の wave は 14〜34 分）。廃止して減るのは 6 分だけで、**削る対象として最も割が悪い**
- 一方で reviewer の探索量（＝ cache_write と往復）は増えるので、wave を 1 本減らす代わりに wave 内の時間が伸びる。旧版が「トレードオフの向きが不明」としていた点は、**片側だけ実測が付いて「採らない」に確定した**
- explorer の「判定せず事実だけ集める」独立性は reviewer の確証バイアスを避ける設計上の要で、これは実測と無関係に維持される
- **wave を削るなら見るのは reviewer → 反証 の間**（`## 15`）— ただしそこも実測で決着済みで、末尾 1 体 wave を畳んでも fleet の 15% 程度しか縮まない（`## 11`）

**再検討の条件**: `duration_explore_min` の中央値が reviewer 以降の wave 単価に近づいたとき（= explorer 側の探索量が膨らんだ兆候）。**「wave 数を減らしたい」を理由に再検討しない** — 本節はその動機を実測で棄却した節である。

## 6. publish 脱落ガードの Stop hook 昇格

**現状**: `review-timing.sh publish-pending` を SKILL の必須ステップ冒頭（self-review Step 7 / review 締めフロー 5）で呼ぶ。判定自体は決定的（`t2` があって `pub` が無い）だが、**呼ぶかどうかは LLM 依存**。

**案**: Stop hook 化する。`.claude/settings.json` の `auto-quality-check.sh` と同型で、ターン終了時に `${TMPDIR}/claude-code-review-<uid>/review-start-*` を glob して未 publish の計測ファイルが残っていれば通知する（`--pr N` を知らなくても glob で当たる）。CLAUDE.md「ルール配置の意思決定」の昇格基準のうち **①判定が if/grep で表現できる ②修復コストが高い（打点は復元不能）** の 2 つに該当する。

**まだ入れていない理由**:

- **誤検知の設計が未確定**。glob は**他セッション・他リポジトリのレビュー**の計測ファイルにも当たる（`TS_FILE` の slug は worktree ルート由来で、hook 側からは自分の回かどうかを判定できない）。並行レビューが常態のマーケットプレイス前提（`dev-workflow:worktree-setup`）では、鳴りっぱなしになって「⚠️ が出たときだけ行動する」契約を壊すリスクがある
- code-review は現在 SessionStart hook しか持たず、**新規 hook の追加は `claude-meta:component-addition-advisor` の退路確保ゲートの対象**（CLAUDE.md）。既存拡張（SKILL 側のガード）で足りるかを先に測る
- **判断材料**: `measurement_gaps` の `late-publish` の発生率（`review-retro.sh` が gap 種別ごとに自分の分母で判定する / v2.66.0）。SKILL 側ガードで頻度が落ちなければ hook へ上げる

## 7. 既定 high で「加減算で報告閾値を超えた MAJOR」を反証対象に含める

**動機（GitHub issue #136）**: `scoring-guide.md` の「複数エージェント検出 +15」は MAJOR を単独で報告閾値（95）へ押し上げられるのに、**押し上げの妥当性は誰も検証していない**。既定 high の反証ゲートは非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）だけなので、BLOCKER / CRITICAL が 0 件の回では反証が構造的に不発になり、**severity 過大が最も起きる帯が最も較正されない**。

**案**: 既定 high のゲートに「**加減算を除いた base confidence が閾値未満**で、加減算後に閾値を超えた MAJOR」を足す。追加バッチの上乗せゲート（`triage-dynamic-gates.md ## 9` の `confidence + 15 >= 報告閾値`）と鏡像の関係（あちらは「+15 の最良ケースでも届かないなら no-op」、こちらは「+15 が無ければ届かなかった＝押し上げが未検証」）。

**採らない理由（v2.67.0 時点）— 既定パスに直列 wave を 1 本足すため**:

- meta-reviewer は xhigh / max 起点なので、**既定 high では 4.6 + 4.9 の wave がそもそも存在しない**回が多い。BLOCKER / CRITICAL 不在の回にこのゲートを足すと、**今まで wave が無かったところに wave が生える**（生えるのは reviewer 以降の wave なので実測 14〜34 分 / `orchestration-measurement.md ## 15`）。token だけの増加ではない
- **xhigh / max では既に MAJOR 全件が対象**（`triage-dynamic-gates.md ## 9` の表）。つまり本案が効くのは high 限定で、そこがちょうど wave を新設する帯にあたる
- **`## 9` には既にゲート幅の再監視条件がある**（閾値の正本は `triage-dynamic-gates.md ## 9`。**ここに数値を書き写さない** — 閾値が動いたときに片方だけ古くなる）。v2.65.0 で `fired` / `skip_reason` を記録し始めたばかりで**実測は 3/3 件**。判断の材料は揃いつつあるので、**先に条件を満たすまで待つ**のが repo の流儀（「サンプルが無いうちは判断しない」/ `triage-guide.md ## 7`）

**issue の前提の訂正（実データで確認）**: #136 は実例を「self-review・xhigh / medium・MAJOR 7 件で `no-eligible-findings`」としているが、`.claude/events.jsonl` で `skip_reason` を持つサンプルは **3 件とも effort=high / size_tier=medium**（`2026-08-13T23:49:52Z` `major_count=8` / `2026-08-15T06:14:04Z` `major_count=6` / `2026-08-16T09:09:55Z` `major_count=8`。いずれも `pre_adjust_counts.major=9`）で、**issue の挙げる「xhigh・MAJOR 7 件」に一致する回は存在しない**。MAJOR 7 件・high・medium の回は実在するが `blocker_count=1` で反証は実際に発火しており、別種の回。3 件はいずれも既定 high で BLOCKER / CRITICAL 不在＝**設計どおりの不発**で、xhigh で MAJOR が対象外になっていた事実は無い。**この照合はこのマシンの `events.jsonl` に対するもの**（gitignored でマシン間同期されないため、別マシンに該当サンプルがある可能性は排除できない）。

**先に入れたもの**: レポート文言（`no-eligible-findings` のとき「未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）」）。誤読（「対象 0 件」＝「検証したが問題なし」）はゲート幅と独立に潰せるため、コストゼロの側だけ先に採った。

**再判断の材料**: `review-retro.sh` の反証シグナル（条件は `triage-dynamic-gates.md ## 9` が正本）。点灯したらこの案と「high の非対称ゾーンに MAJOR の一部帯を足す」案（`triage-dynamic-gates.md ## 9`）を併せて検討する。

## 8. explorer の一括発行と wave 打点を Agent hook（独立した観測者）へ移す

**動機（GitHub issue #135）**: 並列発行の規約（`orchestration-guide.md ## 0`）と wave 打点（`## 14`）は**どちらもオーケストレーターの自己申告**で、破っても実行中は何も起きない。しかも **2 が 1 を検知不能にする**: `agents.explorer_waves` は「打点の行数 = wave 数」で直列発行を暴くための指標（issue #122）なのに、その行を書くのがオーケストレーター自身なので、**打点を忘れた瞬間に違反の証拠も同時に消える**。実測でも `explorer_waves` は導入以来まともに観測できていない。

**案**: `Agent` の PreToolUse / PostToolUse hook で打点する。**発行時刻**を記録すれば wave 判定は明快 — 一括発行なら発行時刻がほぼ同時刻に固まり、1 体ずつ直列に出すと前の agent の実行時間ぶん離れる（完了時刻のクラスタリングより閾値が要らない）。検知したい対象（オーケストレーターの手順遵守）と検知の担い手が分離するのが要点。

**入れていない理由 — 発火するかを確認できていない**:

- **subagent のツール名が `Agent` であることは確認済み**（CC 2.1.233 の transcript 実測）。未確認なのは「`PreToolUse` / `PostToolUse` が `Agent` に対して発火するか」で、**hook の発火記録は transcript に残らない**ため既存データからは判定できない
- **セッション内での実験は偽陰性を返しうる**。`settings.json` に hook を足しても実行中セッションが再読込する保証が無く、「発火しなかった」がツール非対応なのか設定未反映なのか切り分けられない
- **検証手順**: ①`.claude/settings.json` に `PostToolUse` / matcher `Agent` の hook（マーカーファイルに 1 行 append するだけ）を足す ②**セッションを再起動する** ③任意の agent を 1 体起動する ④マーカーが増えたか見る。発火するなら `tool_name` の実値（`Agent` / `Task`）も同時に控える
- **repo の Gotchas「hooks.json の if:/matcher に単独依存しない」に従い、自己判定を必須にする**: `tool_name` を `safe_hook_input` で読み、さらに**レビュー中か**（`review_path timing` が存在するか）を見てから打点する。そうしないと全セッションの全 Agent 呼び出しで発火する
- **`SubagentStop` を先に試す**（本 repo の `.claude-plugin/schema/hooks.schema.json` が正式イベントとして許可し、`claude-meta` の `cc-catch-up/references/plugin-features.md` に「v1.0.41+ / サブエージェント停止時」と記録がある）。**体数を数えるだけならこちらで足りる**ので「`Agent` で発火するか不明」は打ち手全体のブロッカーにはならない。ただし**発行時刻が取れない**ので、wave 推定は完了時刻のクラスタリング＝閾値が要る側に戻る。→ **打点漏れの検知は `SubagentStop`、一括発行違反の検知は `Agent` の PreToolUse**、と役割を分けるのが現時点の第一候補
- **新規 hook の追加は `claude-meta:component-addition-advisor` の退路確保ゲートの対象**（CLAUDE.md）。code-review は現在 SessionStart hook しか持たないので、判定を経てから入れる

**先に入れたもの（案 B / v2.67.0）**: publish の WARN に「レポート末尾に `⚠️ 計測: ...` を 1 行追記せよ」という具体指示を足し、両 SKILL に追記規約を書いた。stderr の警告をユーザーに見える場所へ移すだけで、**自己申告構造そのものは変わっていない**（本命は上の案）。

**射程の縮小（v2.82.0 / GitHub issue #161）**: 本項の動機は 2 つあった — ①一括発行違反が検知できない ②打点漏れで区間が欠測する。**どちらも hook 無しで決着している**。①は #142 が `dispatch` を transcript から機械計測して解決（`agents.explorer_waves` に依存しなくなった）。②は #161 が同じ transcript の実測時刻で `t1` / `wave` / `explorer-wave` を補完して解決（`## 14`）。**hook が要るのは「実行中に止める」用途だけ**になった — 事後計測は違反も欠測も後から見えるが、一括発行違反そのものを**その場で防ぐ**ことはできない。それを取りに行くかは、`dispatch.verdict` の `serial` 発生率が実測でどれだけ残るかで決める（schema=2 以降の実測では 0 件）。**「発火するか確認できていない」というブロッカーは残っているが、払う価値のある対象が縮んだ**。

**案 C（不採用）**: fan-out を Workflow スクリプト（`parallel()` / `pipeline()`）へ移す。explorer wave / reviewer wave / 反証バッチは構造的には `parallel()` そのもので、散文で「一括発行せよ」と指示する代わりに制御構造で保証できる、という筋は成立する。ただし skill の全面書き換えになり費用対効果が悪い。

## 9. 版ラベルの追随漏れを機械検出する

**動機**: v2.67.0 で、追加した注記 5 箇所の版ラベルが `v2.66.0`（bump 前の値）のままだった。この repo は版ラベルで効果測定の母集団を切るので、CHANGELOG と doc が 1 版ずれる。

**試した実装（v2.68.0 で入れて同版で外した）**: 変更した md の**追加行**の `vX.Y.Z` が `plugin.json` の現行版と一致するかを `git diff HEAD` で検査する warning。

**外した理由 — 初回実行で 6/6 が偽陽性**:

- CHANGELOG の新エントリは**履歴を語る**（「v2.67.1 で実際に踏んだ」）ので、現行版と違って当然
- references の doc も**過去版を参照する**（「v2.62.0 で追加した区別」「v2.66.0 + v2.67.0 のセルフレビュー計 14 件」）
- markdown だけでは「**この変更**を指すラベル」と「**履歴への参照**」を区別できない。両者は同じ `（vX.Y.Z / GitHub issue #N）` の形

**3 回目の再発（v2.68.0）**: 同じ失敗をこの版でも踏んだ — 2.67.2 で書いた注記 11 箇所が、2.68.0 へ bump した後もそのまま残った（前版のセルフレビュー指摘 1 と同型）。**検出できる形をもう 1 つ測ったが、これも使えなかった**: 「CHANGELOG にリリース記録が無い版を参照している行」は未リリース版（2.67.2 のような中間版）を確実に捕まえるが、**repo 全体で版ラベル参照 429 件中 147 件（34%）が偽陽性**だった — doc がプラグイン版ではなく **Claude Code の版**（`v2.1.163` 等）を参照しているため。プラグイン版と CC 版はどちらも `2.x` で、表記だけでは区別できない。

**決着（`vNEXT` プレースホルダ / 検出をやめて発生を消した）**: 2 度の測定で出た結論は「**表記の規約が先に要る**」だった。そこで**検出側を諦め、書く側を変えた** — プラグイン配下の md / sh / py には `vNEXT` と書き、`bump-version.sh` が bump 時に実版へ一括置換する。

- **根本原因は「書く時点で正しい値が確定していない」こと**（bump は後）。確定していない値を手書きさせている限り、どんな検出器も後追いになる。`vNEXT` なら書いた瞬間から正しい
- `vNEXT` は**履歴参照と曖昧にならないトークン**なので、置換も残存検出も偽陽性ゼロで済む（`v2.66.0` が「この変更」か「履歴」かを判定する問題が消える）
- 残存検出は **bump が起きた作業ツリーでだけ**判定する（開発中の `vNEXT` は正常。無条件に鳴らすと毎ターン鳴る warning になる）。取りこぼす典型は「別のプラグインを bump したので自分の `vNEXT` が残った」
- **repo 直下の共通スクリプト・doc は対象外**。プラグイン版に属さないので版ラベルを持たせず issue 番号で参照する（複数プラグインを同時に bump したときどちらへ解決するか決まらない）
- 残る穴は「習慣で具体版を書いてしまう」。これは検出できない（履歴参照と同型）ので規約に留める

## 10. 担当ファイルを `class` で機械的に絞る

**現状**: 担当ファイルの割り当ては観点ごとの判断（`orchestration-guide.md`「diff-first 原則」）。GitHub issue #144 で「reviewer 側の担当ファイル割り当てを絞る」を検討したとき、`triage-signals.sh` が既に持っている `class`（core / test / doc / gen）で機械的に絞る案を最初に検討した — 「担当は `class=core` のみ、残りは参考リスト」。判断が不要で決定的なので、この repo の「決定的 hook > LLM 判定」の並びにも合う。

**採らない理由**: **`class` の定義がこの repo で退化する。** 分類は `\.md$|(^|/)docs/` を doc とするので（`triage-signals.sh` の awk）、**プラグインリポジトリでは成果物そのものが丸ごと doc に落ちる**。`claude-md-compliance` の担当が空集合になり、絞るどころかレビュー対象が消える。同じことは docs-as-code なリポジトリ全般で起きる。

- **`class` は「規模の帯を決める」ための分類**（`size_tier` の core 判定 / GitHub issue #96）であって、「誰が読むべきか」の分類ではない。転用すると、md が本体のリポジトリで前者は正しく後者だけが壊れる — **同じフィールドの誤用なので、壊れたときに原因が見えにくい**
- 代わりに #144 で入れたのは**全件を渡してよい観点を 3 つに閉じる**規約（`cross-cutting` / `pattern-consistency` / `spec-compliance`）。絞り方そのものは観点ごとの判断に残し、**既定で全件に落ちる経路だけを塞いだ**
- 機械化するなら `class` ではなく `## focus-signals` の根拠ファイル（観点ごとにヒットしたパスが既にある）が材料。ただし**根拠ファイルだけに絞ると「シグナルは出ていないが違反はある」ファイルを構造的に落とす**ので、recall への影響を測ってからでないと入れられない
