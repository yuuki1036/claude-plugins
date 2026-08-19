# 動的ラウンド実行手順（条件付きフェーズ / orchestration-guide 分冊）

<!-- 正本依存（SSoT pin）。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#0 @859d4f21 -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @90899a7e -->
<!-- SSOT: code-review/references/triage-dynamic-gates.md#8 @34e7126b -->
<!-- SSOT: code-review/references/triage-dynamic-gates.md#8.5 @3d150994 -->
<!-- SSOT: code-review/references/triage-dynamic-gates.md#9 @6a1fca18 -->

**このファイルは、対応するフェーズを実行すると決まってから Read する。** スキップ条件は SKILL.md 側にあり、全フェーズがスキップされるなら読む必要はない。中核（常時必要）は `orchestration-guide.md`、起動ゲートと選定ルールは `triage-dynamic-gates.md`。

| 節 | フェーズ | review / self-review |
|---|---|---|
| `## 6` | Adaptive deepening（Round 2） | Phase 5.5 / 4.5 |
| `## 7` | Meta-reviewer | Phase 5.6 / 4.6 |
| `## 9` | 冷や読み skeptic | Phase 5.8 / 4.8 |
| `## 10` | 反証レイヤー | Phase 5.9 / 4.9 |

同期起動（`run_in_background: false`）と並列発行（同一メッセージ内で一括発行）のルールは `orchestration-guide.md ## 0` が正本で、本ファイルの全起動手順に適用される。

**すべての agent wave の回収点に適用（本ファイルの全フェーズ + orchestration-guide.md `## 5` の auto-retry）: agent の結果を回収した直後に `mark wave` を記録する**（v2.60.0）。打点は**後勝ち**なので、どのフェーズがそのレビューの最後の wave になったかを判断しなくてよい — **回収したら毎回書く**のが正しい運用。動的ラウンドは起動可否が実行時に決まるため、「最後の wave の後だけ書く」規約にするとスキップ時に書き忘れて欠測になる。区間の意味は `orchestration-measurement.md ## 14`（`duration_synthesis_min`）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave [--pr N]
```

## 6. Adaptive deepening 実行手順（Round 2 / review Phase 5.5・self-review Phase 4.5）

1. 全 reviewer 出力をパースし、`## unmet_information` セクションを集約する
1.5. **各 target を repo 内 / セッション到達可能 / 到達不能の 3 分類に振り分ける**（triage-dynamic-gates.md `## 8` の分類表。メインコンテキストで判定・agent 不要）。**「repo 外」＝「到達不能」ではない**（v2.60.0。二分のままだと取れる情報を「構造的に空振り」と誤判定して wave ごと捨てる）:
   - **セッション到達可能**（①そのサービスの MCP / CLI がこのセッションで使える外部状態 ②**ディスク上に実体のある他リポジトリ** — 存在確認 1 回で判定・絶対パス・read-only。定義の正本は triage-dynamic-gates.md `## 8` の分類表）は、**Round 2 を起動する前にメインコンテキストで直接照会して解決する**（read-only の照会に限る。書込・破壊的操作は含めない）。これは Round 2 の代替であって追加ではない。解決したら該当指摘の confidence / severity を再評価し、レポートの「動的ラウンド」行に `スキップ（unmet をメインで直接照会して解決）` と出す
   - 照会で解決したぶんを除いて**残りが全件「到達不能」なら本フェーズ全体をスキップ**し、`missing_coverage` に識別子 `round2` を記録して次フェーズへ進む（**理由（到達不能な target の要旨）はレポートの「⚠️ 欠損観点」に書く** — payload は識別子のみ）
   - **1 件でも repo 内 / 未解決のセッション到達可能があれば通常どおり続行する**（迷う target は到達可能側に倒す）
2. **repo 内 + 未解決のセッション到達可能**の target から **最大 3 件** の追加探索ターゲットを選ぶ（多すぎる場合は BLOCKER 候補に関わる unmet を優先）
3. **経路分岐**（実行時 effort = `${CLAUDE_EFFORT}`。triage-dynamic-gates.md `## 8` Phase 5.5）:
   - **high（既定）— 1 段圧縮**: 追加 explorer は起動しない。unmet を申告した reviewer のみ（最大 3 体）を `model: opus`、**初回 reviewer と同じ effort**（orchestration-guide.md `## 5` の連動表）で再起動する（全 call を同一メッセージ内で一括発行 — orchestration-guide.md `## 0` 並列発行の明示）。プロンプトには①初回指摘②担当分の unmet_information（focus, target, why, related_finding）を渡し、「**まず unmet ターゲットを自分で Read / Grep / Glob で探索し、取得した事実に基づいて初回 confidence を再評価せよ**」と指示する
   - **xhigh / max — 2 段**: `prompts/explorer/re-explore.md`で追加 explorer（最大 3 体）を `model: sonnet` で並列起動し（一括発行 — orchestration-guide.md `## 0`）、各 explorer に対応する unmet_information を渡す。完了後、unmet を申告した reviewer のみ（最大 3 体）を `model: opus`、初回と同じ effort で再起動し、初回指摘 + 追加 explorer 結果を context として渡して「初回 confidence を再評価せよ」と指示する
   - いずれの経路も isolation は orchestration-guide.md `## 0` に従う（review は `isolation: "worktree"`（PR ブランチ）、self-review は使用しない）
   - **共通ブロック（`agent_ctx_file`）のパスを渡す**: PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` はそこに入っているので**プロンプトに再掲しない**（v2.63.0 / orchestration-guide.md `## 3.5`。値の意味は `## 1` / `## 1.1`） に従い prompt 冒頭に PR_NUMBER / head ref / head SHA / メインルートを明記し `{{PR_NUMBER}}` / `{{HEAD_SHA}}` / `{{MAIN_ROOT}}` を置換（issue #56 / #98 / #113）。**`{{SEVERITY_THRESHOLD}}` は両 skill 共通で必須**（`## 2` / issue #117）
4. 再起動 reviewer の出力は **初回出力を置換**（dedup のため）
5. レポートに「Round 2 trigger: <reason>」を記録（レポート出力 step = review Step 7 / self-review Step 6 で出力）

**失敗時**: 追加 explorer / 再起動 reviewer が失敗した場合は初回結果のままで続行（missing_coverage には追記しない、Round 2 は best-effort）

## 7. Meta-reviewer 実行手順（review Phase 5.6・self-review Phase 4.6）

> **起動は反証レイヤー（`## 10`）と同一メッセージで行う**（v2.61.0 / triage-dynamic-gates.md `## 8` 起動タイミング）。実行順は `Round 2 → skeptic 統合 → **meta 1 体 + 反証バッチ最大 3 体を一括発行** → 回収して `mark wave` → [meta 由来指摘の追加反証バッチ] → scoring`。**どちらか一方だけが起動条件を満たす場合はそれだけを発行する**（片方のスキップはもう片方の発行を妨げない）。

1. `prompts/meta-reviewer.md` を使用
2. meta-reviewer agent を 1 体、`model: opus`, `effort: max` で起動（反証バッチと同一メッセージ内）
   - 入力: diff、全 reviewer の指摘リスト（フィルタ前）、起動された focus 一覧、explorer 結果
   - isolation は orchestration-guide.md `## 0` に従う。**共通ブロック（`agent_ctx_file`）のパスを渡す**: PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` はそこに入っているので**プロンプトに再掲しない**（v2.63.0 / orchestration-guide.md `## 3.5`。値の意味は `## 1` / `## 1.1`） に従う。**`{{SEVERITY_THRESHOLD}}` は両 skill 共通で必須**（`## 2`）
3. meta-reviewer の出力（追加指摘）を既存指摘に統合
   - 重複は dedup（同一ファイル ±5 行 + 類似内容）
   - meta-reviewer の指摘も通常のスコアリング・フィルタリング対象
   - **由来タグ `[meta]` を付け、レポート本文の指摘行まで持ち越す**（GitHub issue #121）。`recall_skeptic` の `[recall-skeptic]` と同じ扱いで、**タグはレポート契約の一部**。落とすと publish 時点で由来を再構成できず `meta_reviewer.findings_added` が記憶依存になって系統的に 0 へ潰れる
   - dedup で reviewer 指摘と重複した場合は `[meta:dup]` とし、`findings_added` の分子に入れない（`[recall-skeptic:dup]` と同じ理由 — 重複は「盲点でなかった事例」なので混ぜると価値率が張り付く）

**失敗時**: meta-reviewer が失敗した場合は `missing_coverage` に識別子 `meta-reviewer` を追記して続行（**失敗理由はレポートの「⚠️ 欠損観点」に書く**）

## 9. 冷や読み skeptic 実行手順（review Phase 5.8・self-review Phase 4.8）

1. **surface 判定**: 変更 diff に対し triage-dynamic-gates.md `## 8.5` の判定を行う。DB 書込（`INSERT`/`UPDATE`/`DELETE` の生 SQL または ORM 書込 API `.create(`/`.update(`/`.save(`/`.upsert(` 等）/ 金銭・数量 numeric 演算 / 認可・認証、いずれかの正規表現ヒット、**または** reviewer が `[surface:high-risk]` フラグを返した場合に high-risk surface と判定する。review では **PR 自己申告 D1-High** も OR 判定に含める（self-review は PR を持たないため正規表現 + reviewer フラグのみ）
   - **判定は Phase 0（reviewer 起動前）で行う**（v2.41.0）。正規表現 + PR 自己申告は diff だけで決まるため事前に取れる。effort ゲートも通過していれば、下記 2 の skeptic を **reviewer 一括発行と同一メッセージで発火**する（triage-dynamic-gates.md `## 8.5` 起動タイミング）。結果の統合・dedup（下記 3）だけを 5.8 / 4.8 の位置で行う
   - **fallback（直列）**: reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になった場合のみ、reviewer 完了後に単独起動する。正規表現が取り逃した ORM 抽象越えのケースに限られる
2. **手順 1 の相乗りで発火済みの場合、本手順は実行しない**（fallback 経路でのみ実行する。二重起動は「PR あたり skeptic 1 体・1 round」の上限違反であり `recall_skeptic.fired` の計測も壊す）。fallback のときのみ、`prompts/recall-skeptic.md` を使用し、skeptic agent を **1 体**、`model: opus`, `effort: max` で起動する（isolation は orchestration-guide.md `## 0` に従う）
   - **findings / reviewer の推論は渡さない**（独立性の核）。diff と最小 focus、base ref のみ渡す
   - **共通ブロック（`agent_ctx_file`）のパスを渡す**: PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` はそこに入っているので**プロンプトに再掲しない**（v2.63.0 / orchestration-guide.md `## 3.5`。値の意味は `## 1` / `## 1.1`） に従う。**`{{SEVERITY_THRESHOLD}}` は両 skill 共通で必須**（`## 2`）
3. skeptic の指摘（`[recall-skeptic]` タグ付き）を既存指摘に統合。重複は dedup（同一ファイル ±5 行 + 類似内容）。skeptic の指摘も通常のスコアリング・報告マトリクス・**反証レイヤーの対象**に含める
   - **dedup 時はタグを残す側へ引き継ぐ**（どちらの本文を採用するかに関わらず）。reviewer 指摘と重複したときにタグごと捨てると skeptic の寄与が不可視になり過少計上される。**独立の skeptic が同じ問題に到達した事実は、reviewer が先に見つけていても失われない**
   - ただし**タグは 2 種に分ける**。重複の有無で意味が正反対になるため、同一カウンタに載せてはならない:
     - `[recall-skeptic]` — **skeptic 単独由来**（dedup で reviewer 指摘と重複しなかった）。fleet 共通盲点を実際に破った事例＝ skeptic の価値そのもの
     - `[recall-skeptic:dup]` — **重複 survivor**（reviewer も同じ問題に到達していた）。skeptic が独立に到達した記録としては残すが、**盲点でなかった事例なので recall の足し前はゼロ**
   - **`[recall-skeptic:dup]` を価値率の分子に混ぜない**。skeptic は generalist 一頭で reviewer fleet（effort 上限まで最大 6〜10 体）と同じ diff を読むため**重複は常態**であり、混ぜると価値率が 100% に張り付いて「findings_added=0 なら縮小」の分岐が原理的に発火しなくなる（過少計上の裏返しで、過大計上という別の壊れ方になる）
   - タグは**レポート本文の指摘行まで持ち越す**（Step 7 / Step 6 のレポート契約。publish 時に `findings_added` / `findings_overlap` を数える唯一の根拠）

**失敗時 / スキップ時**: skeptic が失敗 / タイムアウトした場合は `missing_coverage` に識別子 `recall-skeptic` を追記して続行する（**失敗理由はレポートの「⚠️ 欠損観点」に書く**）。スキップ条件（effort / config / scope・emergency）に該当した場合でも、surface 判定（正規表現・grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と独立に必ず実施する。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・スキップのいずれでもレポート（review Step 7 / self-review Step 6 の「動的ラウンド」行）に必ず出す**（silent skip で偽の安心を防ぐ・issue #85）

## 10. 反証レイヤー実行手順（review Phase 5.9・self-review Phase 4.9）

> **起動は meta-reviewer（`## 7`）と同一メッセージで行う**（v2.61.0）。対象選定の材料は「Round 2 後 + skeptic 統合済み」の全指摘で、**meta の出力は待たない**（meta 由来指摘は手順 3.5 の追加バッチで拾う）。

1. triage-dynamic-gates.md `## 9 反証レイヤー` の選定ルールで対象指摘を選ぶ（high: 非対称ゾーン BLOCKER 60-94 / CRITICAL 80-94、xhigh/max: 報告ゾーン全体 + MAJOR）。**specialist 由来の指摘は全 effort で除外**
2. 対象指摘に通し番号（finding_id）を振り、**5 件ずつのバッチに分ける**（上限 3 体 = 15 件。超過分の扱いは triage-dynamic-gates.md `## 9`）。バッチごとに `prompts/adversarial-verify.md` で反証エージェントを `model: opus`, `effort: high` で並列起動する（isolation は orchestration-guide.md `## 0` に従う。全 call を同一メッセージ内で一括発行する — orchestration-guide.md `## 0` 並列発行の明示）
   - 指摘の主張（severity / confidence / file:line / 内容）のみ渡し、**reviewer の理由文は渡さない**（アンカリング防止）
   - **バッチの切り方**: **同一ファイル・同一 reviewer 由来の指摘は意図的に散らす**（同一ファイルは 1 バッチ 2 件までを目安に分割）。バッチ化で失うのは reviewer からの独立性ではなく **反証者側の誤読の独立性** — 1 体がその関数の制御フローを 1 回読み違えると同一ファイルの指摘が束で `refuted` になり、MAJOR は confidence −40 で実質まとめて消える（旧構成の「指摘ごと 1 体」はこれを構造的に防いでいた）。diff 読解の共有によるコスト削減は寄せなくても大半が得られるので、寄せる誘惑に乗らない
   - **共通ブロック（`agent_ctx_file`）のパスを渡す**: PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` はそこに入っているので**プロンプトに再掲しない**（v2.63.0 / orchestration-guide.md `## 3.5`。値の意味は `## 1` / `## 1.1`） に従う。**`{{SEVERITY_THRESHOLD}}` は両 skill 共通で必須**（`## 2`）
   - `pre-existing` / `intended` 鮮度の git 判定（`git show <base>:<file>` / `git blame`）を反証エージェントに許可する
3. 各 verdict（refuted / confirmed / uncertain / severity-inflated）を収集し、**finding_id で対象指摘と突合**してスコアリング step に渡す。verdict が返らなかった finding_id は verdict なし扱い（confirmed とも refuted とも解釈しない）
3.5. **meta 由来指摘の追加バッチ**（meta-reviewer と同一 wave で発行しているため / v2.61.0）: 統合後の `[meta]` タグ付き指摘（`[meta:dup]` は除く）に triage-dynamic-gates.md `## 9` のゲート該当分があれば、**追加バッチ 1 体・上限 5 件**を同じ手順（手順 2 の作法）で起動し、verdict を手順 3 と同様に突合する。0 件なら起動しない（wave が増えない）。この 1 体は本体の上限 3 体とは別枠だが `agents.verify` には加算する
4. **レポートの反証行の正本（両 skill・triage-guide からもここを参照する）**: `反証: 対象 N 件（うち実施 X 件 / 予算超過 Y 件 / 反証失敗 Z 件）/ 係争 M 件 / 取り下げ K 件`。
   - `N`（対象）= ゲートで選ばれた全件（予算超過分と手順 3.5 の meta 由来追加分を含む）、`X`（実施）= 実際に verdict が返った件数。**payload の `agents.verify_findings` は `X` と一致させる**（`N` ではない。同じ「対象」の語で別の量を数えない）
   - 0 件の項目は省略してよいが、`Y` / `Z` が 1 以上なら必ず出す（silent に落とさない）
   - **層ごとスキップした回も 1 行出す**（v2.65.0 / GitHub issue #129。skeptic の silent skip 防止と同じ扱い）: `反証: スキップ（<skip_reason>）`。**ゲート該当 0 件のときは特に省略しない** — 既定 high では BLOCKER / CRITICAL 不在なら対象が構造的に 0 件になるので、無言だと「反証を通った」と読まれる。値の語彙と payload 側の記録は orchestration-measurement.md `## 16` の `adversarial_verify`
   - **`no-eligible-findings` だけは「未実施」と分かる文言にする**（v2.67.0 / GitHub issue #136）: `反証: 未実施（対象帯に該当なし。<閾値以下の severity> は較正されていない）`。例: 既定 high で BLOCKER / CRITICAL 不在なら `反証: 未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）`。**「対象 0 件」と書かないこと** — 他の 4 つの skip 理由（`effort` / `config` / `scope` / `emergency`）は「この構成では走らせない」だが、これだけは**走る構成なのに対象が無かった**ので、同じ書き方だと「検証したが問題なし」と読まれる。確信度の表示が実態より高く出る経路になる
   - **verdict 分布の偏りを検知して注記する（GitHub issue #110）**: `X >= 5` かつ**単一 verdict が実施件数の 80% 以上**を占めるとき、反証行の次の行に注記を 1 行足す:

     ```
     ※ severity-inflated が 7/8（88%）と偏っています。降格の妥当性を検算する価値があります
     ```

     - **バッチを正しく散らしても分布が一様に偏るケースがある**（実測: 2 バッチが独立に `severity-inflated` 7/8）。`## 10` 手順 2 のバッチ切り分けはバッチ内汚染を防ぐが、**プロンプト自体が特定 verdict へバイアスしている場合は検知できない**。偏りが観測できないと、バイアスが混入したときに気づく手段が無い
     - **偏り = 誤りではない**。上記の実測ケースでは個々の verdict に Playwright の実幅計測や mutation test が伴っており質は高かった。注記は「検算する価値がある」までで、**自動で verdict を覆さない**
     - `X < 5` では注記しない（少数では偏りが偶然で起きやすく、注記が常時出てノイズになる）
     - 判定は**メインコンテキストで数えるだけ**。agent の追加起動は不要

**失敗時**: 反証エージェントが失敗した指摘は verdict なし（= 反証スキップ）として元の confidence / severity のまま続行する（best-effort、missing_coverage には記録しない）。**バッチ 1 体の失敗は最大 5 件分の verdict を失う**ため、失敗したバッチの件数はレポートの反証行に「反証失敗 N 件」として出す

