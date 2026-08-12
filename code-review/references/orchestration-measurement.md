# 計測と Event Bus publish（orchestration-guide 分冊）

**このファイルは publish の直前に Read する**（review 締めフロー 4 / self-review Step 6.4）。レビュー本体の実行には不要。

| 節 | 内容 |
|---|---|
| `## 13` | publish 先をメインリポジトリのルートに固定する（worktree で計測ごと消えるのを防ぐ） |
| `## 13.1` | `TS_FILE` のパス導出（並行セッションの衝突回避） |
| `## 14` | 所要時間の区間分割計測（t0 / t1 / t1b / t2 / t3） |
| `## 16` | `review:completed` payload 契約（両 skill 共通の正本） |
| `## 17` | トークン消費の計測（transcript からの事後集計。publish とは独立に任意実行） |

**マーカー（`t0` / `t1` / `t1b` / `t2`）の書き込み自体はレビュー中に行う。** 書き込み位置は SKILL.md の各 Step に埋め込んであり、本ファイルを読まなくても実行できる（`## 14` は意味と算出式の正本）。

## 13. Event Bus publish 先の固定（review 締めフロー 4・self-review Step 6.4 共通 / GitHub issue #96）

`event_bus_publish` の書込先は `safe-hook.sh` の `__event_bus_init_log` が `${CLAUDE_PROJECT_DIR:-$PWD}/.claude/events.jsonl` として決める。`CLAUDE_PROJECT_DIR` は未設定のことがあり、その場合 **cwd 相対**になる。これは 2 経路で計測を失う:

- **review**: Step 0 の `EnterWorktree` で cwd が `.claude/worktrees/<name>` に移るため、publish は worktree 側の `events.jsonl` に書かれ、締めフロー 6 の `ExitWorktree(remove)` で worktree ごと消える
- **self-review**: worktree は使わないが、dev-workflow の作業用 worktree 内から実行された場合は同様に worktree 側へ書かれ、Step 8 の teardown で消える

**worktree 進入後に `git rev-parse --show-toplevel` を撮っても解決しない**（worktree 自身を返すため）。`--git-common-dir` は linked worktree 内でも**メインリポジトリの `.git`** を返すので、進入後でもメインルートを導出できる。

**実装は `scripts/publish-review-event.sh` が持つ**（両 skill が同じスクリプトを呼ぶので導出式が二重管理にならない）。以下は仕様であって、SKILL 本文に bash として書き下さない:

- `--git-common-dir` でメインの `.git` を得て、その親を `MAIN_ROOT` とする
- **`GCD` が空のとき `cd "$GCD/.."` を無条件に実行しないこと** — `/..` すなわち `/` に cd してしまい `/.claude/events.jsonl` へ書きに行く。空のときだけ `pwd` にフォールバックする
- `CLAUDE_PROJECT_DIR="$MAIN_ROOT"` を `event_bus_publish` の呼び出しに前置して上書きする（環境の設定値より導出値を優先。EnterWorktree が `CLAUDE_PROJECT_DIR` を worktree に張り替える実装でも正しく main へ落ちる）

### 13.1 開始時刻ファイル `TS_FILE` のパス（セッション識別必須 / GitHub issue #99）

`TS_FILE` も worktree 進入前後で `pwd` が変わると欠測になるため `MAIN_ROOT` から導出するが、**`MAIN_ROOT` だけでは足りない**。`--git-common-dir` は linked worktree からもメインリポジトリの `.git` を返すので、**同一リポジトリの全 worktree で `MAIN_ROOT` が同一**になり `TS_FILE` が 1 本に collapse する。Step 1 は `>` の truncate で書くため、後から始まったセッションが先行セッションのマーカーを消す。

これが厄介なのは、汚染が**欠測（`-1`）ではなく「もっともらしい小さい値」**として入る点。`duration_fleet_min` は orchestration-guide.md `## 5` / triage-guide.md `## 7` / triage-dynamic-gates.md `## 9` のロールバック判断の一次指標なのに、並行開発環境では静かに過小報告される（実測: 52 分のレビューが約 8 分と出た。43 分後に別 worktree のセッションが `t0` を上書きしていた）。`dev-workflow:worktree-setup` で worktree を並列運用する前提のマーケットプレイスなので、この衝突は例外ではなく常態になりうる。

**パスの識別子は `--show-toplevel`（= その worktree 自身のパス）から作る**。`--git-common-dir` が全 worktree で同じ値を返すのに対し、`--show-toplevel` は**worktree ごとに異なる**ので、これ 1 つで並行セッションを分離できる。同一セッション内では Step 1 と publish の両方が同じ worktree の中で走る（review は ExitWorktree より前に publish する）ため、決定性も保たれる:

**実装は `scripts/review-timing.sh` が持ち、パス導出は `scripts/lib/review-paths.sh` が正本**（`start` / `mark` / `durations` / `cleanup` の 4 サブコマンド。SKILL からはこれを呼ぶだけで、パスの組み立てを本文に書かない）。識別子の仕様:

- **worktree のルート**（`--show-toplevel`）を cksum で slug 化する。review はさらに `--pr N` で PR 番号を混ぜる（`--pr` は数値のみ受理する）
- `--git-common-dir` は使わない（全 worktree で同じ値を返すので識別子にならない）
- **一時ファイルは `$TMPDIR/claude-code-review-<uid>/`（0700・umask 077）に閉じ込める**。`$TMPDIR` 直下に固定名で置くと、`TMPDIR` 未設定の環境（Linux / CI の多く）で world-writable な `/tmp` に落ち、symlink 先置きによる上書きと未コミットコードの読み取りが成立する
- **この式を他所へ複製しないこと**。以前は 4 スクリプト + ガイドのスニペットに散っており、`fetch-pr-context.sh` だけ空値ハンドリングが違うという乖離が実際に起きていた

- **ブランチ名を識別子に使わないこと**。`git rev-parse --abbrev-ref HEAD` は **detached HEAD でも文字列 `HEAD` を返す**（`git bisect` 中・特定コミットの検証中に発生）。`${VAR:-fallback}` は空でないので発火せず、detached な worktree はすべて同じ slug に collapse する。切り詰め（`cut -c1-40`）も長いブランチ名の共通接頭辞を衝突させる。**「同一ブランチは複数 worktree で checkout できないから強い識別子」という理屈は detached 状態では成立しない**
- **識別子の取得に失敗したときの縮退先は「欠測」であって「誤値」ではない**。`--show-toplevel` が失敗して `pwd` に落ちた場合もパスが変わるだけで、publish 側は別ファイルを読んで `-1`（欠測）になる。他セッションの値を拾って誤報告するより望ましい
- **publish 後の掃除は、`t2` マーカーが残っていることを確認してから行う**:

  ```bash
  grep -q '^t2 ' "$TS_FILE" 2>/dev/null && rm -f "$TS_FILE"
  ```

  これは**所有権チェックではなく、そう振る舞う近似**である。ファイルの中身は `t0/t1/t1b/t2 <epoch>` だけで書き手を識別しないため、パスが衝突した場合には「他セッションが書いた `t2`」にヒットしうる。衝突自体は上の `WT` 識別子で塞いでおり、このガードは**万一の衝突時に掃除より他セッションの計測を優先する**ための二段目。「自分が書いたファイルにのみ効く」と読まないこと

## 14. 所要時間の区間分割計測（review / self-review 共通 / v2.41.0 で 3 分割・v2.43.0 で explore 追加）

`duration_min` 単独では **agent の実行時間・メインコンテキストの思考時間・人間の応答待ち**が 1 個の数字に潰れ、どの改善が効いたかを判定できない（実測: 3 体 210 分のサンプルが 1 件あるだけで、内訳が不明なため次の打ち手を選べなかった）。`TS_FILE` に区間マーカーを追記して分割する。

> **測れないものを先に確定しておく（v2.43.0）**: **オーケストレーターが reviewer プロンプトを書いていた時間は、マーカーでは分離できない。** プロンプトのテキストを書く行為が、そのまま Agent call の発行だからである。「書き終わったが、まだ発行していない」瞬間が存在しないため、マーカーを Agent call より前に置けば書く前に発火し、後ろに置けば agent は既に走り出している。実測（v2.43.0 の self-review、reviewer 5 + specialist 1 体）でも、発行直前に置いたマーカーは**7 秒**を記録した一方で fleet 全体は 22 分だった。**プロンプト組み立てコストは `duration_fleet_min` に含まれる**と受け入れ、外出し（orchestration-guide.md `## 3.5`）の効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る。マーカーを増やして測ろうとしないこと。

**マーカーの書き込み点**（いずれも `## 13` の `MAIN_ROOT` 導出式で決めた同じ `TS_FILE` に追記する）:

| キー | 書き込む位置 | 意味 |
|---|---|---|
| `t0` | review Step 1 / self-review Step 1 の冒頭（`>` で新規作成） | レビュー開始 |
| `t1` | **最初の agent を一括発行する直前**（explorer を配置していれば explorer 発行直前 = review Step 4 / self-review Step 3、していなければ reviewer 発行直前 = review Step 5 / self-review Step 4） | triage 区間の終わり |
| `t1b` | **explorer 結果を回収した直後**（explorer を 1 体以上起動した場合のみ書く） | explorer wave の終わり |
| `t2` | **初回レポートを出力した直後**（review Step 7 / self-review Step 6。締めフローに入る前） | fleet 区間の終わり |
| `t3` | publish 時点（ファイルには書かず `date +%s` で取る） | 全体の終わり |

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start   [--pr N]   # Step 1
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1  [--pr N]  # 最初の agent 一括発行の直前（二重記録しない）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1b [--pr N]  # explorer 結果の回収直後（起動した場合のみ）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2  [--pr N]  # 初回レポート出力の直後
```

> **`t1` を explorer 発行直前に置く理由（v2.41.0 の修正）**: `t1` を reviewer 発行直前に固定すると、explorer wave（high で最大 4 体 / xhigh・max で 6 体）の実時間が triage 区間に丸ごと混入し、「メインコンテキストの思考時間の代理指標」という `duration_triage_min` の定義が成立しない。explorer を配置したレビューで triage が膨らみ、**「思考量が主因」という誤診に誘導される**（そしてプロンプト圧縮という誤った打ち手を選ばせる）。agent wave はすべて fleet 側に入れる。

> **`t1b` を足した理由（GitHub issue #100 D）**: 上の修正の副作用として、fleet 区間に「explorer wave + reviewer wave + 動的ラウンド + プロンプト構築 + scoring」が全部入り、**どの wave が何分かかったのかが分からない**。`t1`→`t1b` を切り出すと explorer wave 単独の実時間が取れ、triage-guide.md `## 5.1` が Phase 0 で提示する「wave あたり目安 6〜16 min」を実測で裏付けられる（v2.43.0 の実測: explorer 2 体で 5.9 分）。
>
> **この区間も「純粋な agent 時間」ではない**（explorer プロンプトを書く時間が入る）。ただし explorer は体数も 1 体あたりのプロンプトも reviewer より小さいので汚染は相対的に小さい。**「メインコンテキストの思考時間」を測るフィールドではない** — それは上記のとおり原理的に測れない。
>
> explorer を配置しなかったレビューでは `t1b` を書かず `duration_explore_min` は `-1`（該当なし）にする。0 を publish すると「explorer wave が一瞬で終わった」と誤読される。

**publish 時の算出**（欠測は `-1`。ファイルが無い / マーカーが欠ける場合も 0 と混同しない）は `scripts/publish-review-event.sh` が `review-timing.sh durations` 経由で行い、`duration_*` フィールドを payload に注入する。**SKILL 側は `duration_*` を渡さない**（LLM に時刻計算をさせない）。

- `duration_min`（= `$DUR`）は **従来どおり全体**（t0→t3）。後方互換のため意味を変えない
- `duration_triage_min` = t0→t1: PR/diff 収集・Phase 0・起動前検算。**メイン思考量の代理指標として使わない**（explorer 未配置なら reviewer プロンプト構築が丸ごとここに入り、配置していても explorer プロンプトの構築が入る）
- `duration_fleet_min` = t1→t2: 最初の agent 発火から初回レポートまで。**agent wave の実時間 + プロンプト構築 + scoring/レポート生成**。プロンプト構築コストはここに含まれる（上記のとおり分離できない）
- `duration_explore_min` = t1→t1b: explorer wave の実時間（`duration_fleet_min` の内数）。explorer 未起動時は `-1`。**wave 単価の実測値**として triage-guide.md `## 5.1` の目安時間を裏付けるのに使う
- `duration_closing_min` = t2→t3: 締めフロー（精査・解説・ドラフト）。**大半が人間の応答待ち**なので、他の 2 区間と混ぜて比較しない
  - **publisher 差分（必読）**: review は `レポート → 締めフロー 1〜3（人間待ち）→ 締めフロー 4 publish` の順なので t2→t3 が人間待ちを捉える。**self-review は publish（Step 6.4）が Step 7 の修正方針確認より前**にあり構造上 ≒0 になるため、**self-review は `duration_closing_min` に `-1`（測定不能）を入れる**。0 を publish すると「人間待ちが無かった」と誤読される
  - 同じ理由で **`duration_min`（全体）の意味も publisher 間で非対称**（review は締めフロー込み / self-review は Step 7 手前まで）。集計は `plugin` フィールドで層別してから行い、区間比較には `duration_fleet_min` を使う
- **triage / fleet / closing の和は `duration_min` と一致しない**ことがある（マーカー欠測時）。一致を仮定した検算をしない。`duration_explore_min` は fleet の**内数**なので和に足さない
- 旧サンプルとの層別: `duration_triage_min` フィールドの存在が v2.41.0 以降の publish マーカーになる（triage-guide.md `## 7` のロールバック条件が `agents` フィールドで版を切るのと同じ流儀。日付では切らない）。`duration_explore_min` の存在が v2.43.0 以降のマーカー
- **`duration_*` が並行セッションに汚染されていないこと**は `## 13.1` の `TS_FILE` セッション識別に依存する。識別子を持たない版（v2.43.0 未満）の値は、同一リポジトリで worktree を並列運用していた期間について「もっともらしい過小値」を含みうるため、ロールバック判断の基準側に使わない

## 16. `review:completed` payload 契約（review 締めフロー 4・self-review Step 6.4 共通 / 正本）

**両 skill で同一フィールド名を使う**（subscriber が publisher を区別せず集計できるようにするため）。skill 固有の差分だけを各 SKILL.md に書き、フィールドの意味はここを正本とする。

| フィールド | 内容 |
|---|---|
| `pr` | PR 番号の文字列。self-review と PR 番号取得失敗時は `"local"` |
| `effort` | 実行時 `${CLAUDE_EFFORT}` の実値（`low`〜`max`。装飾を付けない）。体数上限と動的ラウンドの起動を左右する条件変数なので、下流の集計は必ずこれで層別する（v2.39.0） |
| `size_tier` | Phase 0 が判定した規模帯（`small` / `medium` / `large`。triage-guide.md `## 6.1` の core 基準）。所要時間は規模と体数の両方に効かれるため、帯を混ぜた比較は規模キャップの効果を検出できない（v2.40.0） |
| `reviewer_effort_profile` | reviewer effort profile の arm（`uniform` / `differentiated`。triage-guide.md `## 7.1`）。**A/B の層別キー**で、これが無いと 2 arm がどちらも `effort:"high"` で記録され区別できない。存在が v2.51.0 以降のマーカー（日付では切らない）。**実験フラグに紐づく暫定フィールド**で、A/B の結論が出て profile 機能を撤去するときに一緒に消す（design-notes/pending-optimizations.md） |
| `duration_min` ほか `duration_*` | 区間分割の意味・欠測時の扱い・「混ぜて比較しない」理由は `## 14` が正本。`TS_FILE` のパス導出は `## 13.1` |
| `head_verified` | `{ok, mismatch, unknown}`（review のみ。v2.43.0）。各 agent の `HEAD 検証:` 行の集計で、`unknown` は行が無かった agent 数。`mismatch + unknown > 0` のレビューは指摘の信頼度が落ちる（orchestration-guide.md `## 5`） |
| `blocker_count` / `critical_count` / `major_count` / `minor_count` | severity 別件数（報告マトリクス通過後） |
| `pre_adjust_counts` | `{blocker, critical, major, minor}`（v2.44.0）。**スコアリング手順 1 完了時点**（統合・dedup 後、verdict 反映・加減算・降格・フィルタの**前**）の生の severity 分布。下の「調整前後の分離」を参照 |
| `missing_coverage` | 欠損観点の識別子配列。空なら `[]`。**語彙は下の「`missing_coverage` の記法」に従う** |

**`agents`** — 実際に**起動した**体数（成功・失敗を問わない。v2.39.0 の上限調整の効果測定に使う）:

- `explorer` / `reviewer`: 初回の体数（`reviewer` に specialist を含めない）
- `specialist`: red-flag specialist の実起動体数（束ね後）
- `round2`: Round 2 の再起動 reviewer + 追加 explorer の合計（レポート「動的ラウンド」行の N + M と一致させる）
- `verify`: 反証エージェントの**体数**。**バッチ化後は ≒ `ceil(実施件数/5)`** なので指摘数の代理指標にならない。**v2.41.0 前後で意味が変わる**（旧: 指摘ごと 1 体）ため `duration_triage_min` の有無で層別してから使う
- `verify_findings`: 反証で**実際に verdict が返った件数**（v2.41.0）。**レポート反証行の「うち実施 X 件」と一致させる**（ゲート対象 N 件ではない）
- meta-reviewer / skeptic は含めない（それぞれ `recall_skeptic.fired` とレポートの「動的ラウンド」行で観測できる）

**`result_grid`** — 後段 hook / PR コメント自動投稿の dispatch 用の 5 値: `high`=BLOCKER+CRITICAL / `medium`=MAJOR / `low`=MINOR / `skip`=severity スコープ外でフィルタされた件数 / `error`=**agent が失敗した件数**。

- **`error` は `missing_coverage` の length と一致しない**（v2.44.0 で規約を修正）。`missing_coverage` は「agent 失敗」だけでなく「観点未起動（reviewer 上限超過・条件不成立）」「フェーズスキップ（skeptic の effort skip 等）」も含むため、常に `error ≤ len(missing_coverage)` の包含関係になる。旧規約は一致を要求していたが、**実データ 43 件中 11 件で不一致**（うち 10 件は `error=0` で `missing_coverage` が非空 = 未起動のみ）。一致を仮定した検算をしない

**`pre_adjust_counts` の使い方（調整前後の分離 / v2.44.0）** — `major_count` 等は報告マトリクス通過**後**の値なので、**「reviewer が検出しなかった」と「検出したが調整で消えた」を区別できない**。差分で分離する:

```bash
# 「調整で消えた MAJOR」の件数を publisher 別に見る
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.pre_adjust_counts != null)] | group_by(.plugin) | map({
    plugin: .[0].plugin, n: length,
    major_pre: ([.[]|.payload.pre_adjust_counts.major]|add),
    major_post: ([.[]|.payload.major_count]|add),
    lost: (([.[]|.payload.pre_adjust_counts.major]|add) - ([.[]|.payload.major_count]|add))
  })'
```

- **消えた分の内訳（降格 / confidence 不足）はこの 1 フィールドでは分離できない。** `severity-inflated` 降格・`[scope:out]` 降格・報告マトリクスの confidence 落ちが同じ差分に合流するため。**まず「検出由来か調整由来か」の一段目だけを切る**フィールドであり、二段目が必要と分かってから内訳フィールドを足す（LLM が手で組む JSON なのでフィールド数自体がコスト）
- 版マーカー: **`pre_adjust_counts` の存在が v2.44.0 以降**。日付では切らない

**`missing_coverage` の記法（v2.44.0 で語彙固定）** — 要素は **識別子のみ**とし、理由・件数・finding id・自由文を混ぜない:

- 許容形: `<focus 名>`（例 `performance` / `error-handling`）/ `<phase 名>`（例 `explorer` / `recall-skeptic` / `adversarial-verify`）/ `<phase 名>:<focus 名>`（例 `explorer:value-flow-trace`）
- **禁止**: `recall-skeptic (skip: effort=high)` / `adversarial-verify: F2 未反証` / `reviewer-security: surface なしのため未起動（メインで代替評価）` のような理由つき自由文。**理由はレポート本文の「⚠️ 欠損観点」セクションに書く**（payload は集計用）
- 理由: 実データで同一概念が `adversarial-verify:finding-A` / `adversarial-verify-finding3` / `adversarial-verify: F2 未反証` / `adversarial-verify: 対象が実証済み` の **4 通りに分裂**し、`group_by` 集計が成立しなくなっていた。欠損観点の偏り（どの観点が落ちやすいか）は本フィールドの唯一の用途なので、綴りが割れると計測目的そのものが消える

**`adversarial_verify`** — 反証レイヤーの verdict 集計（`confirmed` / `refuted` / `uncertain` / `severity_inflated` / `contested`=高 severity の係争件数）。スキップ時は全 0。`severity_inflated` は v2.41.0 追加（4 つ目の verdict が集計から漏れていた。バッチ化 + effort 引き下げのロールバック判断に使う。triage-dynamic-gates.md `## 9`）。

**`recall_skeptic`** — 冷や読み skeptic の実行記録。high 昇格判断（triage-dynamic-gates.md `## 8.5`）の計測データ:

- `surface`: high-risk surface 判定の結果（bool）。**skeptic が effort / userConfig でスキップされた場合も、正規表現部分の判定だけは payload 構築時に必ず実施して記録する** — 「surface=true なのに effort ゲートで走らなかった頻度」が昇格判断の核心メトリクスのため
- `fired`: skeptic agent が実際に起動したか（bool）
- `skip_reason`: `fired=false` のときの理由。`"effort"` / `"config"` / `"no-surface"` / `"emergency"`（self-review は `"scope"` = `--focus`/`--exclude` 指定も取りうる）。`fired=true` なら `null`
- `attribution_schema`: 由来帰属の規約バージョン。**常に `2` を入れる**（2 = 由来タグがレポート書式に規定され dedup のタグ生存も定義された版 = 2.35.1 以降）。schema 1 相当の旧サンプルは `findings_added` が記憶依存で系統的に 0 へ潰れており判断に使えないため下流はこれで濾す。**日付では切れない**（配布ラグで未更新マシンは修正日以降も schema 1 を publish する）
- `findings_added`: **skeptic 単独由来**（`[recall-skeptic]` タグ）の指摘のうち報告マトリクスを通過した件数。**レポート「動的ラウンド」行の `実行（N 件追加）` の N と同値**（N はヘッダに置かれるが**本文確定後に数えてヘッダへ反映する**。二重管理にしない）。**価値率の分子はこれのみ**
- `findings_overlap`: **重複 survivor**（`[recall-skeptic:dup]` タグ）の件数。独立到達の記録としては残すが、盲点でなかった事例なので**価値率には算入しない**（混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる）
- 両フィールドとも **初回レポート本文のタグ付き指摘を数えて求める**（skeptic フェーズの記憶から再構成しない。publish は遠く、間に精査・解説・ドラフト生成が挟まるため記憶依存にすると系統的に 0 へ潰れる）。**計測点は報告マトリクス通過時点（精査の前）**であり、精査後の調整レポートではない。**精査で取り下げた分は減算しない**（「報告に値する指摘を出せたか」を測るフィールドで、必要性で落ちたかは別軸）

**`comment_polish`**（**self-review のみ** / v2.45.0）— コメント推敲（`prompts/focus/comment-polish.md`）の実行記録:

- `fired`: **`comment-accuracy` 観点が構成に入り、B 系統ブロックを連結して reviewer を起動したか**（bool）。**単独起動とバンドル相乗りを区別しない**（high 既定では束ねが常態で、束ね時に「comment-accuracy reviewer」という単独 agent は存在しない。「専任 reviewer が立ったか」と読むと既定構成で常に false になる）
- `suggested`: **reviewer が B 系統で挙げた総件数**。掲載上限（10 件）で切る前・二重掲載の除去前の数を入れる。**レポート掲載数とは一致しない**（掲載数は上限と dedup の後）。reviewer が `## コメント推敲提案` ブロックごと出力しなかった場合は **`-1`（測定不能）**とし、`missing_coverage` に `comment-accuracy` を記録する（「該当なし＝観点は効いたが 0 件」と「ブロック欠落＝観点が実質死んだ」を 0 に潰さない）
- **2 フィールド持つ理由**: 「起動したが提案 0 件」（打ち手＝観点の効き・プロンプトの具体性）と「そもそも起動していない」（打ち手＝ triage の起動条件・Step 4 の連結漏れ）は対処が正反対。本機能は *チェック項目に書いてあるのに報告まで到達しない* という失敗の再発防止が目的なので、**出力ゼロが観測できないと同じ穴に落ちる**
  - この失敗の論拠は**構造**（MINOR 95+ ＋ 好みクランプ 40 を推敲提案が通過できない）であって計測ではない。payload は focus 別の属性を持たないため、「v2.44.0 まで報告ゼロだった」を実測で示すことはできない（**この点を実測事実として書かないこと**）
- review 側は publish しない（B 系統は self-review 限定。他人の PR への推敲提案は越権になりやすいという設計判断）

**共通ルール**:

- publish に失敗してもレビュー自体は成功扱い（best-effort）。`SAFE_HOOK_NAME` を publisher 名（`code-review:review` / `code-review:self-review`）に上書きして識別する
- 後方互換: subscriber 側は `critical_count` の存在を仮定してよい（旧 payload との互換性のため必須）。それ以外は新規フィールド追加なので旧 subscriber 影響なし（現物確認: `issue-workflow:issue-maintain` は `pr` と件数しか読まない）
- 版マーカー: **`duration_triage_min` の存在が v2.41.0 以降・`duration_explore_min` の存在が v2.43.0 以降・`pre_adjust_counts` の存在が v2.44.0 以降・`comment_polish` の存在が v2.45.0 以降（self-review のみ）**。層別は必ずフィールドの有無で行い、日付では切らない。**v2.43.0 未満の `duration_*` は並行セッション汚染を受けうる**（issue #99）ためロールバック判断の基準側に使わない

## 17. トークン消費の計測（改修の前後比較 / v2.48.0）

`review:completed` payload は**所要時間しか持たない**。トークンは payload に載せられない（skill 実行中に自分の消費量を観測する手段が無い）ため、**transcript から事後に集計する**:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh"            # 現リポジトリの最新セッション
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh" --list     # セッション候補
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh" --since 2026-08-06T10:00  # 時刻で絞る
```

> **worktree 内から実行しても引数なしで通る**（GitHub issue #112）。transcript の slug はセッションを**開始した**ディレクトリ由来なので、review 経路（Step 0 で必ず `EnterWorktree`）では cwd 側の slug にメインループの transcript が存在しない。スクリプトは **cwd 側とメインリポジトリ側（`--git-common-dir` 由来）の両方**を候補にして最新の `.jsonl` を採るので、review 後にそのまま実行してよい。dev-workflow の作業用 worktree 内で開始したセッション（transcript が cwd 側にある逆パターン）も同じ仕組みで拾える。**どちらの候補にも無いときは `--session <絶対パス>`** を使う（`--list` が探索したディレクトリを表示する）。

Claude Code の transcript（`~/.claude/projects/<slug>/*.jsonl`）は各アシスタントメッセージに `usage` を持ち、`isSidechain` でメインループとサブエージェントを分離できる。スクリプトはこれを `main` / `sub` に分けて集計する。

| 指標 | 意味 | 何の効果が出るか |
|---|---|---|
| `main.output` | オーケストレーターが**書いた**量 | プロンプト複製（**単価が最も高い**。パス渡し化の効果はここ） |
| `main.cache_write` | オーケストレーターが**新規に読んだ**量 | 参照 doc の読み込み（分冊・遅延読み込みの効果はここ） |
| `sub.*` | サブエージェント側 | 体数・1 体あたりの探索量 |
| `cache_read` | 再利用ぶん | 単価が低い。**前後比較の指標には使わない** |

- **比較は同じ PR / 同じ diff で行う**（規模が変われば当然変わる）。`size_tier` を揃えるのは `duration_fleet_min` と同じ流儀
- **`duration_*` と混ぜて 1 つの結論を出さない**。体数削減が確実に効くのはトークンであって壁時計ではない（triage-guide.md `## 7`「体数を壁時計のレバーとして扱わない」）
- transcript はセッション単位なので、**1 セッションで 1 レビューだけ回したときが最も読みやすい**。複数回した場合は `--since` で切る
