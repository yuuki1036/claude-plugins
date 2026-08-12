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




## `## 8.5` 冷や読み skeptic を high 起点へ昇格した根拠（v2.52.0 / 2026-08-07）

`triage-dynamic-gates.md ## 8.5` が定めていた昇格基準は「直近で `skip_reason="effort"` の surface ヒットが**継続的に発生**し、かつ xhigh 実績の価値率（`findings_added > 0` 率）が**明確に非ゼロ**」。**両方とも満たしたので昇格した。**

集計対象は 5 リポジトリの `.claude/events.jsonl` を横断した `review:completed` **50 件**（review 17 / self-review 33）。`recall_skeptic` を持ち `attribution_schema >= 2` のものは 33 件:

| 指標 | 実測 | 基準 |
|---|---:|---|
| surface=true | 24 / 33 | — |
| うち `skip_reason="effort"` で未起動 | **15（63%）** | 「継続的に発生」を満たす |
| `fired=true` | 8 | — |
| うち `findings_added > 0` | **4（50%）** | 「明確に非ゼロ」を満たす |

**待機のコスト**: 価値率 50% が正しいなら、effort skip した 15 件で **約 7〜8 件の fleet 共通盲点を取り逃していた**計算になる。放置すると毎回の high レビューで積み上がる。

**昇格コストが小さい理由**: skeptic は v2.41.0 で reviewer wave への相乗りになっており、**直列 wave を増やさない**（壁時計への影響は wave 内最長を更新したときだけ）。増えるのは opus 1 体ぶんのトークンで、しかも surface=true のときだけ（33 件中 24 件 = 73%）。

**meta-reviewer を昇格しなかった理由**: meta は reviewer 全結果に依存するため相乗りできず、**直列 wave を 1 本足す**。壁時計が wave 数に支配される以上（`## 5.1`）、skeptic と同じ扱いにはできない。meta の昇格は `duration_fleet_min` が層別に貯まってから別途判断する。

### この判断の弱点（記録しておく）

- **n=8 は薄い**。このリポの流儀（「サンプルが貯まるまで判断しない」）に照らすと本来もう少し欲しかった。**需要側（15 件）の明確さと、待機のコストが積み上がる性質**を重く見て前倒しした
- そのため**ロールバック条件を先に決めてある**（`## 8.5`）: `fired=true` かつ schema>=2 が 15 件貯まった時点で価値率 25% を下回ったら戻す。n を倍にしても半分を切るなら昇格根拠が崩れたとみなす
- 以前 design-notes に「`fired=true` 4 件すべてが `findings_added=0` だが、価値ゼロと帰属の喪失を区別できない」と記録していた件は、**schema 2 のサンプルで決着した** — 帰属が壊れていただけで、実際には半分が盲点を破っていた。**壊れた計測を根拠に撤去しなくて正解だった事例**として残す

## `## 7` 体数と fleet 時間は無相関だった（v2.57.0 / GitHub issue #116）

`## 7` は以前「体数削減が壁時計に効いた証拠は現時点で存在しない」と書いていた。**証拠が貯まり、無相関であることが実測で示された**ので断定に変えた。

review 18 件のうち `duration_fleet_min` が**非 `-1`（有効）だった 13 件**を `size_tier` で揃え effort で層別した結果（下表に載るのは `medium` 帯の 10 件。残る 3 件は small / large 帯で本表の対象外）:

| 条件 | fleet 実測（分） | 平均 | 体数レンジ |
|---|---|---:|---|
| medium + high (n=4) | 19 / 27 / 36 / 47 | **32 分** | 6〜10 |
| medium + xhigh (n=6) | 41 / 57 / 60 / 65 / 69 / 73 | **61 分** | 6〜11 |

**体数レンジがほぼ重なっているのに fleet は 1.9 倍**。個別サンプルでも `73 分 / 6 体` と `19 分 / 7 体` が併存しており、体数では説明できない。差は wave 数で説明できる — xhigh では high に対して ①meta-reviewer が起動（+1 wave）②Round 2 が 2 段（規模キャップ帯では 1 段に圧縮）③反証ゲートが「非対称ゾーンのみ」→「報告ゾーン全体 + MAJOR」に拡大、が加算される。

**この記録の用途は「体数を削って時間を稼ごうとする誤った最適化を防ぐ」こと。** 壁時計を縮めたいときの打ち手は `## 7` の ①探索量 ②直列 wave 数 ③メイン複製量であって、体数ではない。

**未確定として残す点**:

- 上の 13 件とは**別に**、欠測（`duration_fleet_min: -1`）が 1 件あった（large + xhigh / 19 体。有効 13 件には含まない＝母数は「取得を試みた 14 件のうち有効 13 件」）。並行セッション汚染（GitHub issue #99）かマーカー欠落かは、そのサンプルが `orchestration-measurement.md ## 13.1` のセッション識別導入の前後どちらかを判別できないため未確定。**この 1 件を「体数が多いと測定不能」と読まないこと**
- 上表は **`medium` 帯のみ**。small / large 帯では wave 構成が変わる（規模キャップが Round 2 を 1 段に圧縮する帯がある）ため、同じ比率が出るとは限らない
- 「medium 帯で xhigh を選ぶと +29 分」から**帯連動ゲート（medium 以下では meta-reviewer をスキップ）**に価値がありうるが、**判断材料が足りない**（meta-reviewer の収量が payload に無く価値率を出せない）。計測を足す議論は GitHub issue #121 に分離した。**本記録をもって帯連動ゲートを入れないこと**
  - **⚠️ v2.60.0 で一部だけ踏み越えた。** 上の禁止は `medium` 以下を対象にした広い帯連動を指しているが、v2.60.0 では **`small` 帯かつ BLOCKER 不在**という狭い条件に限ってスキップを入れた。**根拠は n=1 で、この禁止の趣旨（サンプル不足のうちは入れない）に反している。** 経緯とロールバック条件は下記「meta-reviewer の `small` 帯スキップ」を必ず併読すること

## `recall_skeptic` の価値率は既知の過少計上を含む（GitHub issue #120）

`findings_added`（`[recall-skeptic]` 単独由来）を分子、`findings_overlap`（`[recall-skeptic:dup]`）を分子に**入れない**のが現行の定義。dup を混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる — この判断自体は妥当で変えない。

**ただし二値でしか見ていないため、「同じ問題に独立到達し、かつ根拠・修正案が上位互換だった」ケースの価値が 0 に計上される。**

実測（review 1 件）: reviewer 3 体（bug-detection / spec-compliance / skeptic）が「非活性の理由に不備行の所在が無い」という同一問題に到達し dup 判定になった。しかし **skeptic 版だけが `safeParse` の `error.issues` を捨てている事実を突いており、`path` が行 index と列名を持つので既存の locus 表示機構にそのまま流せる、という修正案の核を持っていた**。reviewer 2 体の版は「件数を出す」程度に留まっていた。**最終レポートに採用した修正案は skeptic 由来**だが、計上は `findings_added: 0 / findings_overlap: 2`。

**判断: 記録だけに留め、第 3 のタグ（`[recall-skeptic:dup-superior]` 等）は増やさない。** 上位互換かどうかの判定には主観が入り、`findings_added` の機械的な明快さ（レポートのタグを数えるだけ）を損なう副作用の方が大きい。

**`## 8.5` のロールバック判断に到達したときは、この偏りを踏まえて読むこと。** 価値率は**実態より低く出る**方向にのみ歪む（上位互換ケースが 0 として積まれるため）。したがって:

- 閾値（15 件・25%）を**下回った**ときは、機械値だけで撤去を決めない。dup 判定になった指摘のうち skeptic 版の修正案が採用されたケースがあったかをレポート本文で確認する
- 閾値を**上回った**ときは追加確認は不要（過少計上でも閾値を超えているなら価値は確定している）

## meta-reviewer の `small` 帯スキップ（v2.60.0 / **n=1 の暫定ゲート**）

`## 6.3` の「規模キャップが削るのは breadth だけ」に対する**唯一の例外**を入れた: **`size_tier: small` かつ BLOCKER 不在なら meta-reviewer（Phase 5.6）をスキップする**（`skip_reason: "size-tier"` / `meta_reviewer.gate_schema: 2`）。

**この判断は n=1 で、このリポジトリの通常の基準を下回る。** `## 8.5` の skeptic 昇格は n=8 で判断し n=15 でロールバック判定、`## 9` の反証縮小は n=19 で判定している。上の「fleet 実測 13 件」の記録にも **「本記録をもって帯連動ゲートを入れないこと」** と明記してあり、それを一部踏み越えている。**根拠の弱さを承知の上での暫定措置**として扱うこと。

### 観測した 1 件

review / `size_tier: small`（doc 1 ファイル `+75 -22`）/ `effort: xhigh` / reviewer 3 + meta 1 + verify 3。

| 項目 | 実測 |
|---|---|
| `duration_fleet_min` | 44 分 |
| agent wave 実時間（各 wave 内最長の和） | 約 24 分（reviewer 8.5 / meta 8.9 / verify 6.2） |
| meta の wave 単価 | **8.9 分**（リトライを含む。**レポートまでの 47 分**の約 2 割 — 締めフローを含む全体 58 分ではない） |
| `meta_reviewer.findings_added` | **0**（4 件出したが報告マトリクスを 1 件も通らず） |
| 反証レイヤーの寄与（対照） | 6.2 分で 6 件中 4 件を落とした（`severity_inflated` 3 / `refuted` 1） |

**meta の 4 件が通らなかった内訳**は「reviewer 指摘との dup」「反証で `severity_inflated`」「報告閾値未達」で、**盲点を破ったものは無かった**。同じレビューで反証レイヤーは同程度の wave 単価で 4 件を較正しており、**同じ 1 wave の使い方として非対称**だった。

### なぜ `small` 帯に限るのか（仮説）

meta の役目は「他の reviewer の見落とし」を探すこと。ところが `small` 帯は規模キャップで **reviewer が 3 体**まで絞られる（`## 6.2`）。**探す相手（fleet の出力）そのものが小さく、fleet 共通盲点が生まれる余地も小さい**。逆に BLOCKER が出ている変更は帯に関わらずリスクが高いので、そこは残す。

### ロールバック / 再評価条件

**機械的な価値率では判定できない**（走らせなかったものの収量は観測できない）。以下のいずれかで差し戻す:

1. **対照実行**: `small` 帯で meta を意図的に起動した実行を **5 件**集め、`findings_added > 0` が **1 件でもあれば即座に差し戻す**（`## 8.5` の skeptic が n=8 の 50% で昇格した前例より緩い基準にする — こちらは recall を削る方向の変更なので、疑わしければ戻す側に倒す）
2. **事後発覚**: `small` 帯 + `gate_schema: 2` のレビューで見逃した BLOCKER / CRITICAL が後から判明した事例が **1 件でも**出たら差し戻す
3. `medium` 帯（meta が従来どおり起動する帯）で `findings_added > 0` の率が高いと判明した場合は、`small` 帯の仮説（「探す相手が小さい」）が帯の違いで説明できているかを再検討する

**差し戻すのは SKILL.md 5.6 / 4.6 のスキップ条件 1 行と triage-dynamic-gates.md `## 8` の起動条件**。`gate_schema` は `1` に戻さず **`3` を新設する**（版は単調増加させる。戻したことも版で識別できるようにする）。

**ユーザー側の即時回避**: このゲートは `size_tier` にしか連動しないので、meta を確実に走らせたい小さな PR は BLOCKER が出るまで待つのではなく **`medium` 帯として扱う運用（対象ファイルを増やす）はしない**。素直に `enable_meta_reviewer` の逆（強制起動）が必要になった時点で userConfig を足す。**現状は強制起動のスイッチが無い**ことを制約として認識しておく。
