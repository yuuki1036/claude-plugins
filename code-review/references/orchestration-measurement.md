# 計測と Event Bus publish（orchestration-guide 分冊）

**このファイルは publish の直前に Read する**（review 締めフロー 4 / self-review Step 6.4）。レビュー本体の実行には不要 — **`## 19` だけは例外**で、重複検出（review Step 2.4 / self-review Step 1.4）の背景を後から引くときに読む（実行自体は SKILL 本文だけで完結する）。

| 節 | 内容 |
|---|---|
| `## 13` | publish 先をメインリポジトリのルートに固定する（worktree で計測ごと消えるのを防ぐ） |
| `## 13.1` | `TS_FILE` のパス導出（並行セッションの衝突回避） |
| `## 14` | 所要時間の区間分割計測（t0 / t1 / wave / t2 / t3） |
| `## 16` | `review:completed` payload 契約（両 skill 共通の正本） |
| `## 17` | トークン消費の計測（transcript からの事後集計。publish とは独立に任意実行） |
| `## 18` | 蓄積イベントの振り返り集計（publish の直後に毎回実行。シグナルの読み方） |
| `## 19` | 直近レビューとの重複検出（**review Step 2.4 / self-review Step 1.4** で参照） |

**マーカー（`t0` / `t1` / `wave` / `t2`）の書き込み自体はレビュー中に行う。** 書き込み位置は SKILL.md の各 Step に埋め込んであり、本ファイルを読まなくても実行できる（`## 14` は意味と算出式の正本）。

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

**実装は `scripts/review-timing.sh` が持ち、パス導出は `scripts/lib/review-paths.sh` が正本**（`start` / `mark`（`t1` / `wave` / `t2` / `published`）/ `durations` / `t0` / `waves` / `gaps` / `publish-pending` / `cleanup` の 8 サブコマンド。SKILL からはこれを呼ぶだけで、パスの組み立てを本文に書かない。`t0` は publish がトークン計測の窓を絞るために使う内部用で、SKILL からは呼ばない）。識別子の仕様:

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

  これは**所有権チェックではなく、そう振る舞う近似**である。ファイルの中身は `t0/t1/we/w/t2 <epoch>` だけで書き手を識別しないため、パスが衝突した場合には「他セッションが書いた `t2`」にヒットしうる。衝突自体は上の `WT` 識別子で塞いでおり、このガードは**万一の衝突時に掃除より他セッションの計測を優先する**ための二段目。「自分が書いたファイルにのみ効く」と読まないこと

## 14. 所要時間の区間分割計測（review / self-review 共通 / v2.41.0 で 3 分割・v2.43.0 で explore 追加・v2.60.0 で synthesis 追加）

`duration_min` 単独では **agent の実行時間・メインコンテキストの思考時間・人間の応答待ち**が 1 個の数字に潰れ、どの改善が効いたかを判定できない（実測: 3 体 210 分のサンプルが 1 件あるだけで、内訳が不明なため次の打ち手を選べなかった）。`TS_FILE` に区間マーカーを追記して分割する。

> **測れないものを先に確定しておく（v2.43.0）**: **オーケストレーターが reviewer プロンプトを書いていた時間は、マーカーでは分離できない。** プロンプトのテキストを書く行為が、そのまま Agent call の発行だからである。「書き終わったが、まだ発行していない」瞬間が存在しないため、マーカーを Agent call より前に置けば書く前に発火し、後ろに置けば agent は既に走り出している。実測（v2.43.0 の self-review、reviewer 5 + specialist 1 体）でも、発行直前に置いたマーカーは**7 秒**を記録した一方で fleet 全体は 22 分だった。**プロンプト組み立てコストは `duration_fleet_min` に含まれる**と受け入れ、外出し（orchestration-guide.md `## 3.5`）の効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る。マーカーを **Agent call の前後に**増やして測ろうとしないこと。

> **上の禁止の射程（v2.60.0 で明確化）**: 上の結論は「**プロンプト組み立て**時間の分離」についてのもので、そこは正しい。ただし fleet 区間には**もう 1 種類の agent 非稼働時間**がある — **最後の agent wave を回収した後の scoring / dedup / verdict 反映 / レポート生成**である。この区間は「回収済み ＝ 全 agent 終了済み」なので **agent が 1 体も走っていないことが構造的に保証される**。Agent call の前後に置くマーカーではないため上の不可能性に当たらず、`wave` → `t2` として分離できる（`duration_synthesis_min`）。
>
> 動機（実測 / review・1 ファイル 97 行の doc PR・xhigh・reviewer 3 + meta 1 + verify 3）: `duration_fleet_min` 44 分に対し agent wave の実時間は約 24 分（reviewer 8.5 + meta 8.9 + verify 6.2、各 wave 内最長）で、**残り約 20 分（46%）がオーケストレーター側**だった。`duration_triage_min` は 3 分しか出ていないため、**この 20 分はどのフィールドにも現れていなかった**。支配的な区間が構造的に不可視だと「時間が長いから体数を減らす」という誤った打ち手に誘導される（triage-guide.md `## 7` が禁じている混同そのもの）。
>
> **`duration_synthesis_min` は「メイン思考時間」の全量ではない。** wave 間のプロンプト構築・分冊 Read は依然として wave 区間に混ざるため、取れるのは「最後の wave 回収以降」だけ。**オーケストレーター時間の下限値**として読み、`duration_fleet_min - duration_synthesis_min` を「agent wave + wave 間のメイン時間」の合計として扱う。

**マーカーの書き込み点**（いずれも `## 13` の `MAIN_ROOT` 導出式で決めた同じ `TS_FILE` に追記する）:

**打点の規約は 1 本にまとめてある（v2.62.0 / GitHub issue #123 B）**: 「**agent wave を回収したら `mark wave` を打つ。explorer wave なら `--explorer` を付ける**」だけを覚える。旧来は explorer 回収が `t1b`・その他の wave 回収が `t1c` と**打点のたびに種類を判断させて**いたが、実測では `duration_synthesis_min` の保有率が **3 / 49**・`agents.explorer_waves` が **2 / 49** と計測として機能していなかった（両フィールドとも v2.60.0 / v2.61.0 以降のサンプルにしか載らないので全件が打ち忘れではないが、**打点した回自体が数件しかない**）。旧キー（`mark` に `t1b` / `t1c` を渡す形）はエイリアスとして受理し続けるが、**規約としては使わない**。

| キー | 書き込む位置 | 意味 |
|---|---|---|
| `t0` | review Step 1 / self-review Step 1 の冒頭（`>` で新規作成） | レビュー開始 |
| `t1` | **最初の agent を一括発行する直前**（explorer を配置していれば explorer 発行直前 = review Step 4 / self-review Step 3、していなければ reviewer 発行直前 = review Step 5 / self-review Step 4） | triage 区間の終わり |
| `wave --explorer` | **初回 explorer 結果を回収した直後**（Step 4 / Step 3 の explorer。**複数 wave に分けてしまった場合は wave ごとに毎回**） | explorer wave の終わり（**行数 = explorer wave の本数** → `agents.explorer_waves`） |
| `wave` | **その他すべての agent wave の回収直後**（reviewer wave / **Round 2（追加 explorer を含む）** / meta + 反証 / 追加反証バッチ の**各回収点で毎回**） | 最後の agent wave の終わり |
| `t2` | **初回レポートを出力した直後**（review Step 7 / self-review Step 6。締めフローに入る前） | fleet 区間の終わり |
| `t3` | publish 時点（ファイルには書かず `date +%s` で取る） | 全体の終わり |

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start [--pr N]              # Step 1
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1 [--pr N]            # 最初の agent 一括発行の直前（二重記録しない）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --explorer [--pr N]  # explorer 結果の回収直後
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave [--pr N]          # その他の agent wave 回収の直後（毎回・後勝ち）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2 [--pr N]            # 初回レポート出力の直後
```

> **`wave` は回収のたびに毎回追記する**（`durations` の awk が後勝ちで最後の値を採る）。「どの wave が最後か」を**オーケストレーターに予測させない**ための設計 — 動的ラウンドは起動可否が実行時に決まるので、「最後の wave の後にだけ書く」という規約にすると、スキップが起きたときに書き忘れて欠測になる。**毎回書けば必ず正しい**。

> **`--explorer` 付きの打点を synthesis 側に混ぜないこと**（スクリプト側で分離済み）。explorer 回収だけ打って reviewer wave の打点を落とした場合、混ぜると `duration_synthesis_min` が reviewer wave を丸ごと含む「もっともらしい過大値」になる。**縮退先は欠測（-1）であって誤値ではない**（`## 13.1` と同じ原則）。

> **`mark` は失敗しない（v2.62.0）**: `start` 未実行・一時ファイル消失でもファイルを作り直し、stderr に警告を出して exit 0 で返す。マーカー 1 個の失敗でレビュー本体を止めない。**逆算による補完はしない** — publish 時刻から wave の打点を推定すれば欠測は消えるが、それは誤値であって計測ではない。欠測は `measurement_gaps` に出して可視化する側で扱う。

> **`t1` を explorer 発行直前に置く理由（v2.41.0 の修正）**: `t1` を reviewer 発行直前に固定すると、explorer wave（high で最大 4 体 / xhigh・max で 6 体）の実時間が triage 区間に丸ごと混入し、「メインコンテキストの思考時間の代理指標」という `duration_triage_min` の定義が成立しない。explorer を配置したレビューで triage が膨らみ、**「思考量が主因」という誤診に誘導される**（そしてプロンプト圧縮という誤った打ち手を選ばせる）。agent wave はすべて fleet 側に入れる。

> **explorer wave 区間（現 `wave --explorer`）を足した理由（GitHub issue #100 D）**: 上の修正の副作用として、fleet 区間に「explorer wave + reviewer wave + 動的ラウンド + プロンプト構築 + scoring」が全部入り、**どの wave が何分かかったのかが分からない**。`t1`→ 最初の `wave --explorer` を切り出すと explorer wave 単独の実時間が取れ、triage-guide.md `## 5.1` が Phase 0 で提示する「wave あたり目安 6〜16 min」を実測で裏付けられる（v2.43.0 の実測: explorer 2 体で 5.9 分）。
>
> **この区間も「純粋な agent 時間」ではない**（explorer プロンプトを書く時間が入る）。ただし explorer は体数も 1 体あたりのプロンプトも reviewer より小さいので汚染は相対的に小さい。**「メインコンテキストの思考時間」を測るフィールドではない** — それは上記のとおり原理的に測れない。
>
> explorer を配置しなかったレビューでは `wave --explorer` を打たず `duration_explore_min` は `-1`（該当なし）にする。0 を publish すると「explorer wave が一瞬で終わった」と誤読される。

> **explorer wave 打点の行数が `agents.explorer_waves` になる（v2.61.0 / GitHub issue #122）**: explorer は「同一メッセージ内で一括発行する」規約（orchestration-guide.md `## 0`）だが、**破ったことが計測に現れないため事後に気づけなかった**（実測: 1 体を単独発行してから残り 3 体を次のメッセージで出したため `duration_explore_min` が 18 分 = 7.7 + 9.2 になった。一括なら wave 内最長の約 9 分で済んでいた）。**wave ごとに `mark wave --explorer` を打てば行数がそのまま wave 本数になる**ので、追加のマーカー種別を増やさずに検知できる。`durations` は最後の explorer 打点を採るため、分割しても `duration_explore_min` は全 wave を覆う。
>
> 値の注入と警告は `publish-review-event.sh` が行う（**SKILL 側は `agents.explorer_waves` を渡さない**）。`>= 2` なら「一括発行が破られた」、`agents.explorer >= 1` かつ `0` なら「マーカーの打ち忘れ」を stderr に WARN し、**どちらもレポート末尾に `⚠️ 計測: ...` を 1 行追記するよう指示する**（v2.67.0 / GitHub issue #135。Round 2 の追加 explorer には `--explorer` を付けない規約があるので、`>= 2` は初回 wave の分割を意味する＝断定してよい）。

**publish 時の算出**（欠測は `-1`。ファイルが無い / マーカーが欠ける場合も 0 と混同しない）は `scripts/publish-review-event.sh` が `review-timing.sh durations` 経由で行い、`duration_*` フィールドを payload に注入する。**SKILL 側は `duration_*` を渡さない**（LLM に時刻計算をさせない）。

- `duration_min`（= `$DUR`）は **従来どおり全体**（t0→t3）。後方互換のため意味を変えない
- `duration_triage_min` = t0→t1: PR/diff 収集・Phase 0・起動前検算。**メイン思考量の代理指標として使わない**（explorer 未配置なら reviewer プロンプト構築が丸ごとここに入り、配置していても explorer プロンプトの構築が入る）
- `duration_fleet_min` = t1→t2: 最初の agent 発火から初回レポートまで。**agent wave の実時間 + プロンプト構築 + scoring/レポート生成**。プロンプト構築コストはここに含まれる（上記のとおり分離できない）
- `duration_explore_min` = t1→ 最後の explorer wave 打点: explorer wave の実時間（`duration_fleet_min` の内数）。explorer 未起動時は `-1`。**wave 単価の実測値**として triage-guide.md `## 5.1` の目安時間を裏付けるのに使う
- `duration_synthesis_min` = 最後の agent wave 打点→t2: **最後の agent wave 回収から初回レポートまで**（`duration_fleet_min` の内数 / v2.60.0）。scoring・dedup・verdict 反映・レポート生成で、**agent 非稼働が構造的に保証される唯一の区間**。オーケストレーター時間の**下限値**として読む（wave 間のプロンプト構築・分冊 Read は wave 区間側に残るため全量ではない）。打点欠測時は `-1`
  - **用途**: `duration_fleet_min` が大きいときの打ち手の切り分け。`duration_synthesis_min` が支配的なら打ち手は**メイン側**（分冊の遅延読み込み・可変部の圧縮・scoring の機械化）であって体数削減ではない。逆に小さければ wave 側（直列 wave 数・1 体あたりの探索量）を見る
  - **`duration_explore_min` と同じく fleet の内数**なので、区間の和を `duration_fleet_min` と一致させる検算をしない
- `duration_closing_min` = t2→t3: 締めフロー（精査・解説・ドラフト）。**大半が人間の応答待ち**なので、他の 2 区間と混ぜて比較しない
  - **publisher 差分（必読）**: review は `レポート → 締めフロー 1〜3（人間待ち）→ 締めフロー 4 publish` の順なので t2→t3 が人間待ちを捉える。**self-review は publish（Step 6.4）が Step 7 の修正方針確認より前**にあり構造上 ≒0 になるため、**self-review は `duration_closing_min` に `-1`（測定不能）を入れる**。0 を publish すると「人間待ちが無かった」と誤読される
  - 同じ理由で **`duration_min`（全体）の意味も publisher 間で非対称**（review は締めフロー込み / self-review は Step 7 手前まで）。集計は `plugin` フィールドで層別してから行い、区間比較には `duration_fleet_min` を使う
  - **publish の脱落と、遅れて気づいた回の扱い（v2.66.0 / GitHub issue #133）**: publish は副作用のみで標準出力に何も足さないため、**踏み忘れても実行中は誰も気づかない**（self-review は Step 6.4 の後に Step 7 の修正作業が控えており、「指摘は全部修正して」と言われている回ほど落ちる）。二重で塞ぐ:
    - `mark t2` が「締めは publish で終わる」ことを stdout に出す（**打点の直後 ＝ 落ちる直前**に言う）
    - `review-timing.sh publish-pending [--pr N]` が「**`t2` があって `pub` が無い**」で未 publish を検出する。呼ぶ位置は self-review Step 7 冒頭（**embed / 指摘 0 件でもここだけは実行する**）/ review 締めフロー 5。**ファイル不在は無言**（publish 済みで掃除された回と「そもそも計測していない」を区別できないので、鳴らす側に倒すと毎回鳴る）
    - **`pub` マーカーと掃除の順序が判定の土台**（v2.66.0 のセルフレビュー指摘）: `publish-review-event.sh` は `event_bus_publish` に**成功したときだけ** `mark published` を打ち、そのときだけ一時ファイルを掃除する。旧版は成否に関わらず掃除していたため、**イベントが書かれなかった回ほど痕跡が残らない**という逆向きの縮退になっていた（打点ごと消えて再 publish もできず、ガードもファイル不在で無言）。失敗回は一時ファイルを残すので、同じ引数で再実行すれば復旧できる
    - 遅れて publish した self-review は **`duration_min` を `-1`（欠測）に倒し `measurement_gaps` に `late-publish` を立てる**（t2→publish が **10 分以上**）。契約と違う区間を「もっともらしい大きい値」として載せない（`## 13.1` と同じ原則）。**review には掛けない** — あちらは締めフロー（人間待ち）を含むのが契約なので大きいこと自体が正常。`duration_fleet_min` 以下の区間は t2 までで閉じているので影響を受けない
- **triage / fleet / closing の和は `duration_min` と一致しない**ことがある（マーカー欠測時）。一致を仮定した検算をしない。`duration_explore_min` は fleet の**内数**なので和に足さない
- 旧サンプルとの層別: `duration_triage_min` フィールドの存在が v2.41.0 以降の publish マーカーになる（triage-guide.md `## 7` のロールバック条件が `agents` フィールドで版を切るのと同じ流儀。日付では切らない）。`duration_explore_min` の存在が v2.43.0 以降・`duration_synthesis_min` の存在が v2.60.0 以降のマーカー
- **`duration_*` が並行セッションに汚染されていないこと**は `## 13.1` の `TS_FILE` セッション識別に依存する。識別子を持たない版（v2.43.0 未満）の値は、同一リポジトリで worktree を並列運用していた期間について「もっともらしい過小値」を含みうるため、ロールバック判断の基準側に使わない

## 16. `review:completed` payload 契約（review 締めフロー 4・self-review Step 6.4 共通 / 正本）

**両 skill で同一フィールド名を使う**（subscriber が publisher を区別せず集計できるようにするため）。skill 固有の差分だけを各 SKILL.md に書き、フィールドの意味はここを正本とする。

### payload テンプレート（v2.62.0 で SKILL から移設）

**`<...>` を実値で埋めてそのまま `--payload` に渡す。渡すのは実行時の事実だけ**（件数 / bool / `skip_reason` / 実効設定値）。

> **版マーカーの整数は渡さない**（v2.65.0 / GitHub issue #125）。`schema` / `gate_schema` / `attribution_schema` / `calibration_schema` は `publish-review-event.sh` が注入する。以前は「常に N を入れる」定数を**テンプレートの一部として手書き**させていたが、版が上がるたびにテンプレ追従が要り、**version drift 中に漏れる**（実測: `recall_skeptic.gate_schema` に導入後の miss / `calibration_schema` は 1 セッション中に 2 版跨いだため落ちた）。落ちるとサンプルが**逆の版バケツに入って集計を汚す**ので、単なる欠測より悪い。スクリプトは版付きディレクトリ配下にあり自分の版の定数を知っているので、注入なら構造的に漏れない。
>
> 同様に `duration_*` / `agents.explorer_waves` / `measurement_gaps` / `diff_digest` / `diff_files` / `tokens` も**渡さない**（スクリプトが注入する）。
>
> **層のオブジェクトそのもの（`pre_adjust_counts` / `adversarial_verify` / `recall_skeptic` / `meta_reviewer`）は必ず入れる。** 落ちた場合は版マーカーを注入する先が無いので、`measurement_gaps` に `payload:<field>` を立てて可視化する（空オブジェクトを捏造すると「起動記録なし」として母集団に混ざるため注入しない）。`fired` を落とした場合も同様に `payload:<field>.fired` が立つ。

### 版マーカーの現行値

**`publish-review-event.sh` の `SCHEMA_MARKERS` と本表は同値でなければならない**（v2.67.0 / GitHub issue #134）。値の意味（どの版が何を指すか）は各フィールドの節が正本で、本表は**現行値だけ**を機械可読な形で持つ。`validate_plugin_quality.py` の `schema-markers` チェックが両者を突合し、ずれていれば Critical で落とす — 注入方式に移した時点で「2 箇所を人手で揃える」関係が SKILL↔doc から script↔doc へ移っただけで、**SSoT pin は md 限定なのでこの関係を宣言できない**（Gotchas / ADR-20260813223000）。

| payload フィールド | 版マーカー | 現行値 |
|---|---|---|
| `findings_class` | `schema` | 1 |
| `pre_adjust_counts` | `schema` | 2 |
| `adversarial_verify` | `calibration_schema` | 2 |
| `adversarial_verify` | `gate_schema` | 2 |
| `recall_skeptic` | `attribution_schema` | 2 |
| `recall_skeptic` | `gate_schema` | 2 |
| `meta_reviewer` | `gate_schema` | 3 |

- **`tokens.schema` は本表に載せない**（＝ `SCHEMA_MARKERS` に入れない）。**片方の skill でしか載らないフィールドの版マーカーは対象外**という例外で、`SCHEMA_MARKERS` は「層のオブジェクトが無ければ `payload:<field>` gap を立てる」経路と対になっているため、review 限定の `tokens` を入れると **self-review で毎回 gap が立つ**。この種のフィールドは構築ブロック側のリテラルで持つ（現行 `tokens.schema: 1`）
- 値を変えるときは**本表と `SCHEMA_MARKERS` を同時に直す**。片方だけ直すと publish の実データ（スクリプトが正）と doc の解釈（本表が正）がずれ、下流の層別が静かに誤る

review 用（`--plugin code-review:review --pr <PR番号>`）:

```json
{
  "pr":"<number>","effort":"<low|medium|high|xhigh|max>","size_tier":"<small|medium|large>",
  "reviewer_effort_profile":"<uniform|differentiated>",
  "head_verified":{"ok":<n>,"mismatch":<n>,"unknown":<n>},
  "agents":{"explorer":<n>,"reviewer":<n>,"specialist":<n>,"round2":<n>,"verify":<n>,"verify_findings":<n>},
  "pre_adjust_counts":{"blocker":<n>,"critical":<n>,"major":<n>,"minor":<n>},
  "severity_threshold":"<BLOCKER|CRITICAL|MAJOR|MINOR>",
  "blocker_count":<n>,"critical_count":<n>,"major_count":<n>,"minor_count":<n>,
  "missing_coverage":[<json-array of focus names>],
  "result_grid":{"high":<n>,"medium":<n>,"low":<n>,"skip":<n>,"error":<n>},
  "findings_class":{"lint":<n>,"test":<n>,"judgement":<n>},
  "adversarial_verify":{"fired":<bool>,"skip_reason":<string|null>,"confirmed":<n>,"refuted":<n>,"uncertain":<n>,"severity_inflated":<n>,"contested":<n>},
  "recall_skeptic":{"surface":<bool>,"fired":<bool>,"skip_reason":<string|null>,"findings_added":<n>,"findings_overlap":<n>},
  "meta_reviewer":{"fired":<bool>,"skip_reason":<string|null>,"findings_added":<n>}
}
```

self-review 用（`--plugin code-review:self-review`）— **`pr` は `"local"` 固定 / `head_verified` を持たない / `comment_polish` を持つ**、の 3 点だけが上との差:

```json
{
  "pr":"local","effort":"<low|medium|high|xhigh|max>","size_tier":"<small|medium|large>",
  "reviewer_effort_profile":"<uniform|differentiated>",
  "agents":{"explorer":<n>,"reviewer":<n>,"specialist":<n>,"round2":<n>,"verify":<n>,"verify_findings":<n>},
  "pre_adjust_counts":{"blocker":<n>,"critical":<n>,"major":<n>,"minor":<n>},
  "severity_threshold":"<BLOCKER|CRITICAL|MAJOR|MINOR>",
  "blocker_count":<n>,"critical_count":<n>,"major_count":<n>,"minor_count":<n>,
  "missing_coverage":[<json-array of focus names>],
  "result_grid":{"high":<n>,"medium":<n>,"low":<n>,"skip":<n>,"error":<n>},
  "findings_class":{"lint":<n>,"test":<n>,"judgement":<n>},
  "adversarial_verify":{"fired":<bool>,"skip_reason":<string|null>,"confirmed":<n>,"refuted":<n>,"uncertain":<n>,"severity_inflated":<n>,"contested":<n>},
  "recall_skeptic":{"surface":<bool>,"fired":<bool>,"skip_reason":<string|null>,"findings_added":<n>,"findings_overlap":<n>},
  "meta_reviewer":{"fired":<bool>,"skip_reason":<string|null>,"findings_added":<n>},
  "comment_polish":{"fired":<bool>,"suggested":<n>}
}
```

| フィールド | 内容 |
|---|---|
| `pr` | PR 番号の文字列。self-review と PR 番号取得失敗時は `"local"` |
| `effort` | 実行時 `${CLAUDE_EFFORT}` の実値（`low`〜`max`。装飾を付けない）。体数上限と動的ラウンドの起動を左右する条件変数なので、下流の集計は必ずこれで層別する（v2.39.0） |
| `size_tier` | Phase 0 が判定した規模帯（`small` / `medium` / `large`。triage-guide.md `## 6.1` の core 基準）。所要時間は規模と体数の両方に効かれるため、帯を混ぜた比較は規模キャップの効果を検出できない（v2.40.0） |
| `reviewer_effort_profile` | reviewer effort profile の arm（`uniform` / `differentiated`。triage-guide.md `## 7.1`）。**A/B の層別キー**で、これが無いと 2 arm がどちらも `effort:"high"` で記録され区別できない。存在が v2.51.0 以降のマーカー（日付では切らない）。**実験フラグに紐づく暫定フィールド**で、A/B の結論が出て profile 機能を撤去するときに一緒に消す（design-notes/pending-optimizations.md） |
| `duration_min` ほか `duration_*` | 区間分割の意味・欠測時の扱い・「混ぜて比較しない」理由は `## 14` が正本。`TS_FILE` のパス導出は `## 13.1` |
| `head_verified` | `{ok, mismatch, unknown}`（review のみ。v2.43.0）。各 agent の `HEAD 検証:` 行の集計で、`unknown` は行が無かった agent 数。`mismatch + unknown > 0` のレビューは指摘の信頼度が落ちる（orchestration-guide.md `## 5`） |
| `blocker_count` / `critical_count` / `major_count` / `minor_count` | severity 別件数（報告マトリクス通過後） |
| `pre_adjust_counts` | `{blocker, critical, major, minor}` + `schema`（**スクリプトが注入**）。**スコアリング手順 1 完了時点**（統合・dedup 後、verdict 反映・加減算・降格・フィルタの**前**）の severity 分布。下の「調整前後の分離」を参照 |
| `severity_threshold` | 実行時の `review_severity_threshold` 実効値（`BLOCKER`〜`MINOR`）。**どの severity が `## below-threshold` に回ったかを事後に判別するために必須**（v2.58.0〜）。これが無いと `pre_adjust_counts` の非可換性を補正できない |
| `missing_coverage` | 欠損観点の識別子配列。空なら `[]`。**語彙は下の「`missing_coverage` の記法」に従う** |
| `findings_class` | **報告した指摘を「何が捕まえるべきだったか」で分類した件数**（v2.68.0 / GitHub 由来ではなく運用課題から）+ `schema`（スクリプトが注入）。`lint`=静的検査（grep / AST / 構造走査）で機械的に検出できた / `test`=回帰テストがあれば捕まえられた（コードの挙動の誤り）/ `judgement`=設計判断・主張の妥当性など機械で判定できない。**合計は報告件数（blocker+critical+major+minor）と一致させる**。下の「`findings_class` の使い方」を参照 |
| `measurement_gaps` | **打点が欠けたマーカーの識別子配列**（v2.62.0 / `publish-review-event.sh` が注入。**SKILL からは渡さない**）。語彙は `start` / `t1` / `wave` / `t2` / `explorer-wave` / `diff-digest` / `tokens`（**review のみ**。transcript を引けなかった / 窓が空振りした）/ `payload:<field>`（**payload 側の欠落**。層のオブジェクトごと落ちた回 + `payload:missing_coverage`）/ `payload:<field>.fired`（発火記録の欠落）/ `late-publish`（**self-review のみ** / v2.66.0。t2 から 10 分以上あけて publish した回 = `duration_min` の契約が壊れているので `-1` に倒した。→ `## 14`）。**`tokens` / `payload:*` / `*.fired` は v2.65.0 で追加**。**識別子ごとに是正先が違う**（打点 / payload テンプレート / transcript 引き当て / 突合キー算出）ので、集計側は種類を混ぜて 1 つの是正先を提示しないこと。**`tokens` は review でしか立たないので分母も review に絞る**。`duration_*` が `-1` になった理由を「打ち忘れ」と「該当なし」に分けるためのフィールドで、**欠測率そのものを計測対象にする**（issue #123 B）。`explorer-wave` は `agents.explorer >= 1` かつ打点 0 のときだけ入る（explorer 未起動は該当なしなので gap ではない）。`diff-digest` は突合キーを算出できなかった回に入る（＝ `## 19` の重複検出が事後に効かない。**「重複が無かった」と区別するために立てる**） |
| `diff_digest` | **diff 全文の cksum**（v2.62.0 / `publish-review-event.sh` が算出。**SKILL からは渡さない**）。重複レビューの**強い突合キー**で、**同一 skill の再実行でのみ一致する** — review は `gh pr diff`、self-review は `git diff BASE..HEAD` + `--cached` + unstaged の **3 本連結**で diff を作るので、同じ変更でもバイト列が違う（実測: 同一 head の PR で `1462260100-1256` vs `2713407599-105966`）。HEAD SHA ではなく diff にしたのは self-review が未コミット変更を含むため |
| `diff_files` | **変更ファイルパス集合の cksum**（v2.62.0 / 同上）。**skill を跨いでも一致する弱いキー**で、連結・index 行・ハンクの分かれ方に影響されない代わりに**別内容の変更でも一致しうる**（＝重複の疑いどまり）。強弱 2 本を持つ理由は上の非対称。算出の正本は `scripts/lib/review-paths.sh` の `review_diff_keys` |
| `tokens` | **トークン消費**（**review のみ** / v2.65.0 / `publish-review-event.sh` が `measure-tokens.sh --json` を呼んで注入。**SKILL からは渡さない**）。`{schema, window, main_output_k, main_cache_write_k, sub_output_k, sub_agents}`。下の「トークンを payload に載せる」を参照 |

**`agents`** — 実際に**起動した**体数（成功・失敗を問わない。v2.39.0 の上限調整の効果測定に使う）:

- `explorer` / `reviewer`: 初回の体数（`reviewer` に specialist を含めない）
- `explorer_waves`: **explorer wave の本数**（v2.61.0 / explorer wave 打点の行数を `publish-review-event.sh` が注入する。**SKILL からは渡さない**）。一括発行が守られていれば explorer 起動時 `1` / 未起動 `0`。**`>= 2` は「1 メッセージにまとめていれば wave 内最長で済んだのに、直列に積んだ」ことを意味する**（orchestration-guide.md `## 0`）。`agents.explorer >= 1` かつ `explorer_waves == 0` は**マーカーの打ち忘れ（欠測）**であって「wave が無かった」ではない。存在が v2.61.0 以降のマーカー
  ```bash
  # 一括発行が破られた回の頻度と、そのときの explore 区間
  grep '"event":"review:completed"' .claude/events.jsonl | \
    jq -s '[.[] | select((.payload.agents.explorer_waves // 0) >= 2)] |
      map({plugin, waves: .payload.agents.explorer_waves, explorer: .payload.agents.explorer, explore_min: .payload.duration_explore_min})'
  ```
- `specialist`: red-flag specialist の実起動体数（束ね後）
- `round2`: Round 2 の再起動 reviewer + 追加 explorer の合計（レポート「動的ラウンド」行の N + M と一致させる）
- `verify`: 反証エージェントの**体数**（v2.61.0 以降は meta 由来指摘の追加バッチ 1 体もここに加算する。triage-dynamic-gates.md `## 9`）。**バッチ化後は ≒ `ceil(実施件数/5)`** なので指摘数の代理指標にならない。**v2.41.0 前後で意味が変わる**（旧: 指摘ごと 1 体）ため `duration_triage_min` の有無で層別してから使う
- `verify_findings`: 反証で**実際に verdict が返った件数**（v2.41.0）。**レポート反証行の「うち実施 X 件」と一致させる**（ゲート対象 N 件ではない）
- meta-reviewer / skeptic は含めない（**それぞれ `meta_reviewer` / `recall_skeptic` の専用フィールドで観測する**。`agents` は体数上限の効果測定用で、1 体固定の検証層を混ぜると上限との対応が崩れる）

**`result_grid`** — 後段 hook / PR コメント自動投稿の dispatch 用の 5 値: `high`=BLOCKER+CRITICAL / `medium`=MAJOR / `low`=MINOR / `skip`=severity スコープ外でフィルタされた件数 / `error`=**agent が失敗した件数**。

- **`error` は `missing_coverage` の length と一致しない**（v2.44.0 で規約を修正）。`missing_coverage` は「agent 失敗」だけでなく「観点未起動（reviewer 上限超過・条件不成立）」「フェーズスキップ（skeptic の effort skip 等）」も含むため、常に `error ≤ len(missing_coverage)` の包含関係になる。旧規約は一致を要求していたが、**実データ 43 件中 11 件で不一致**（うち 10 件は `error=0` で `missing_coverage` が非空 = 未起動のみ）。一致を仮定した検算をしない

**`pre_adjust_counts` の使い方（調整前後の分離 / v2.44.0）** — `major_count` 等は報告マトリクス通過**後**の値なので、**「reviewer が検出しなかった」と「検出したが調整で消えた」を区別できない**。差分で分離する:

```bash
# 「調整で消えた MAJOR」の件数を publisher 別に見る
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select((.payload.pre_adjust_counts.schema // 1) == 2
           and .payload.severity_threshold == "MAJOR")] | group_by(.plugin) | map({
    plugin: .[0].plugin, n: length,
    major_pre: ([.[]|.payload.pre_adjust_counts.major]|add),
    major_post: ([.[]|.payload.major_count]|add),
    lost: (([.[]|.payload.pre_adjust_counts.major]|add) - ([.[]|.payload.major_count]|add))
  })'
```

**`pre_adjust_counts.schema` の意味（v2.58.0 / GitHub issue #117 のセルフレビュー指摘）** — **算出方法が版で非可換に変わったのに、フィールドの有無では層別できない**ため publisher 側の版マーカーを持たせる（`recall_skeptic.attribution_schema` と同じ流儀。日付では切らない。**値の注入は v2.65.0 でスクリプト側へ移した**）:

| `schema` | 算出方法 | 粒度 |
|---|---|---|
| `1`（v2.44.0〜v2.53.x。**フィールド欠落 = 1 と読む**） | reviewer が列挙した指摘のみを数える | 統合・dedup 後 |
| `2`（v2.54.0〜） | 上に各 reviewer の `## below-threshold` の件数を**同名 severity のバケツへ**足す | **足し込む分は dedup されない**（reviewer 横断の生合計） |

- **schema 1 と 2 を同じ列で比較しない。** schema 2 は閾値未満ぶんが非 dedup で載るため、reviewer 間で重複した指摘が重複計上される。#117 の効果（「MINOR 85% 破棄」の改善）を測るときは **schema 2 同士**で比べる
- **`severity_threshold` と併せて読む。** `MAJOR`（既定）なら MINOR だけが非 dedup、`CRITICAL` なら MAJOR も非 dedup になる。閾値を知らずに `major_pre - major_post` を取ると運用差が改善に見える
- 消費側の絞り込み例: `select((.payload.pre_adjust_counts.schema // 1) == 2 and .payload.severity_threshold == "MAJOR")`

- **消えた分の内訳（降格 / confidence 不足）はこの 1 フィールドでは分離できない。** `severity-inflated` 降格・`[scope:out]` 降格・報告マトリクスの confidence 落ちが同じ差分に合流するため。**まず「検出由来か調整由来か」の一段目だけを切る**フィールドであり、二段目が必要と分かってから内訳フィールドを足す（LLM が手で組む JSON なのでフィールド数自体がコスト）
- 版マーカー: **`pre_adjust_counts` の存在が v2.44.0 以降・`schema` サブフィールドが算出方法の版**（欠落 = `1`）。日付では切らない

**`missing_coverage` の記法（v2.44.0 で語彙固定・v2.66.0 で機械検証）** — 要素は **識別子のみ**とし、理由・件数・finding id・自由文を混ぜない:

- 許容形: `<focus 名>`（例 `performance` / `error-handling`）/ `<phase 名>`（例 `explorer` / `round2` / `recall-skeptic` / `meta-reviewer` / `adversarial-verify`）/ `<phase 名>:<focus 名>`（例 `explorer:value-flow-trace` / `head-mismatch:security`）。**正規表現 `^[a-z0-9-]+(:[a-z0-9-]+)?$` に完全一致**（`re.fullmatch`。`re.match` だと末尾改行 1 個を通すので使わない）
- **禁止**: `recall-skeptic (skip: effort=high)` / `adversarial-verify: F2 未反証` / `reviewer-security: surface なしのため未起動（メインで代替評価）` のような理由つき自由文。**理由はレポート本文の「⚠️ 欠損観点」セクションに書く**（payload は集計用）
- 理由: 実データで同一概念が `adversarial-verify:finding-A` / `adversarial-verify-finding3` / `adversarial-verify: F2 未反証` / `adversarial-verify: 対象が実証済み` の **4 通りに分裂**し、`group_by` 集計が成立しなくなっていた。欠損観点の偏り（どの観点が落ちやすいか）は本フィールドの唯一の用途なので、綴りが割れると計測目的そのものが消える
- **`publish-review-event.sh` が上の正規表現で検証し、外れたら publish せず `FATAL` で落ちる**（v2.66.0 / GitHub issue #132。規約だけでは守られず、実データに自由文が 12 種混入していた）。**黙って正規化はしない** — どの識別子に寄せるかを推測すると別の綴り割れを作る。**フィールドごと落として通さないこと**（欠落は `measurement_gaps` の `payload:missing_coverage` として記録され、綴り割れが静かな全欠測に置き換わるだけになる）

**`findings_class` の使い方（v2.68.0）** — **目的は「指摘を減らすこと」ではなく「機械が見つけるべきものを agent に探させない」こと**:

- **0 件を目標にしない。** 300 行の diff で指摘 0 件のレビューの方が疑わしい。見るのは**構成比**で、`lint` の比率が高い＝ linter を足す余地がある、`test` が高い＝回帰テストが足りない、というシグナルとして読む
- **分類はレポート出力後・publish 前に数える**（記憶から再構成しない）。判断に迷う指摘は `judgement` に倒す（`lint` / `test` を過大に見積もると「機械化の余地がある」という誤ったシグナルになる）
- **`lint` は「今ある linter が検出できた」ではなく「静的検査で検出しうる」**。まだ実装されていないルールでも、grep / AST / 構造走査で決まるなら `lint` に数える — そうしないと「lint が無いから lint 可能な指摘は 0 件」という恒真の指標になる
- 集計は `review-retro.sh` が層別して出す。**実測の出発点**（v2.66.0 + v2.67.0 のセルフレビュー計 14 件）: `lint` 6 / `test` 6 / `judgement` 2 ＝ **86% が機械で捕まる層**だった

**`adversarial_verify`** — 反証レイヤーの verdict 集計（`confirmed` / `refuted` / `uncertain` / `severity_inflated` / `contested`=高 severity の係争件数）。スキップ時は全 0。`severity_inflated` は v2.41.0 追加（4 つ目の verdict が集計から漏れていた。バッチ化 + effort 引き下げのロールバック判断に使う。triage-dynamic-gates.md `## 9`）。

- `fired` / `skip_reason`: **発火記録**（v2.65.0 / GitHub issue #129）。他の 2 つの動的層（`recall_skeptic` / `meta_reviewer`）は持っていたのに**この層だけ持たず**、下流は `agents.verify > 0` から起動有無を推定するしかなかった。それでは **「走らなかった」と「走れる対象が無かった」を区別できない**:
  - `skip_reason` の語彙は `"effort"`（low / medium）/ `"config"`（`enable_adversarial_verify: false`）/ `"scope"`（self-review の `--focus` / `--exclude`）/ `"emergency"`（`--emergency` / `skip-mode`）/ **`"no-eligible-findings"`**（triage-dynamic-gates.md `## 9` のゲートに合致する指摘が 0 件）。`fired=true` なら `null`
  - **`"no-eligible-findings"` が本フィールドの主目的**。既定 effort（high）のゲートは非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）だけなので、**BLOCKER / CRITICAL が 1 件も出なければ MAJOR がいくら出ても対象は構造的に 0 件**になる（実測: 本リポジトリの `pre_adjust_counts` を持つ 6 件中 3 件が不発で、いずれも BLOCKER + CRITICAL = 0・MAJOR は 6〜8 件。**「3 回連続」ではない** — 間に起動回が 2 件挟まる。issue #129 が別途「3 回連続」と報告しているのは複数リポジトリを含む実運用の体感で、この 6 件表からは再現しない）。他の 4 つと違い**設計上の非該当ではなく「ゲート幅が実効的に狭いか」の観測点**なので、下流の分母から外さない（`review-retro.sh` の `OUT_OF_SCOPE_SKIPS` に入れない）
  - **ゲート幅の妥当性はこのフィールドが貯まるまで判断しない**。狭いこと自体が問題だとはまだ言えず、**測れないことが問題**だった（再監視条件は triage-dynamic-gates.md `## 9`）
- `gate_schema`: **起動ゲートの版**（v2.65.0 / `meta_reviewer.gate_schema` と同じ流儀）。**`publish-review-event.sh` が注入する**（1 = `fired` を持たない v2.64.x 以前 = 発火を記録していない版 / 2 = 非対称ゾーン + surface-aware 例外 + 追加バッチの confidence 上乗せゲート = v2.65.0 以降）。**旧サンプルは「起動しなかった」ではなく「記録していない」**なので、発火率を出すときは必ず `gate_schema >= 2` で濾す
  - **版マーカーだけでは記録漏れを落とせない**（注入方式の帰結。全 3 層に共通）。版マーカーはスクリプトが入れるので、**`fired` を落とした現行版 payload にも最新版が入る**。「フィールドの有無が版マーカー」の層別は旧版にしか効かないため、**現行版の記録漏れは `measurement_gaps` の `payload:<field>.fired` で外す**（`review-retro.sh` の `layer_stats` が `dropped_unrecorded` として実装）。外さないと記録漏れが `skip_reason=unknown` として分母に混ざり、発火率が実態より薄まる／「1 度も起動していない」という偽のロールバックシグナルまで点灯しうる
- `calibration_schema`: **上流 severity 較正ガードの版**（v2.62.0 / `pre_adjust_counts.schema` と同じ流儀）。**`publish-review-event.sh` が注入する**（1 = base 状態の確認だけを課していた v2.55.0〜v2.61.x / 2 = `prompts/reviewer-common.md` に「降格される典型パターン」の 4 型を明示した v2.62.0 以降）。**これが無いと A の効果を測れない** — `severity_inflated` 比率は累計で読むと施策前サンプルに薄められ、上流ガードが効いたかどうかが判定できなくなる（issue #123 A）。日付では切らない（配布ラグ）

**`meta_reviewer`** — meta-reviewer ラウンドの実行記録（GitHub issue #121）。**帯連動ゲート（`triage-guide.md ## 6.3` の「削らない」判断）を再評価するための計測**で、これが無いと価値率を出せず `## 7` の流儀（「サンプルが無いうちは判断しない」）に従うと永久に判断できない:

- `fired`: meta-reviewer agent が実際に起動したか（bool）
- `skip_reason`: `fired=false` のときの理由。`"effort"`（high 以下）/ `"config"`（`enable_meta_reviewer: false`）/ `"no-high-severity"`（**起動条件の severity 側を満たさない**。`gate_schema: 3` では「BLOCKER / CRITICAL 不在**かつ**報告見込み MAJOR が 3 件未満」を指す）/ `"size-tier"`（`small` 帯かつ BLOCKER 不在 / v2.60.0〜）/ `"emergency"`。`fired=true` なら `null`
- `gate_schema`: **起動ゲートの版**（`recall_skeptic.gate_schema` と同じ流儀 / v2.60.0〜）。**`publish-review-event.sh` が注入する**（1 = 帯非連動＝ effort と高 severity だけで決まる v2.59.x 以前 / 2 = `size_tier: small` かつ BLOCKER 不在でスキップする v2.60.0〜v2.61.x / 3 = MAJOR 3 件以上でも起動する v2.62.0 以降）。**これが無いとロールバック条件のクエリが旧版のサンプルを混ぜてしまう** — 版ごとに `fired` の分母も `skip_reason` の意味も違う。日付では切らない（配布ラグ）
- `findings_added`: **meta 単独由来**（`[meta]` タグ）の指摘のうち報告マトリクスを通過した件数。定義・計測点は `recall_skeptic.findings_added` と同一（**初回レポート本文のタグ付き指摘を数える**。記憶から再構成しない。精査で取り下げた分は減算しない）
- **由来タグ `[meta]` はレポート契約の一部**（`recall_skeptic` の `[recall-skeptic]` と同じ扱い）。タグを落とすと publish 時点で由来を再構成できず `findings_added` が系統的に 0 へ潰れる
- **`findings_added` は meta の価値を捉えきらない**（フィールド設計時に認識済みの非対称）。meta は「単独起動されなかった観点を自分で当たって『指摘なし』と閉じる」という**指摘以外の価値**も出すが、それはこのフィールドに現れない。**価値率が低くても即座に撤去判断をしない** — 撤去を検討する段では、レポート本文で「閉じた観点」の有無も併せて読む
- **v2.60.0 の帯連動ゲートは「撤去」ではなく「帯限定の縮小」**（`small` 帯かつ BLOCKER 不在のみスキップ / `medium`・`large` と BLOCKER 有りは従来どおり起動）。上の非対称を踏まえ、**指摘以外の価値が最も薄い帯に限って**止めている。**判断根拠は n=1 でこのリポジトリの通常の基準（`## 8.5` の skeptic は昇格を n=8 で判断しロールバック判定は n=15、`## 9` の反証縮小は n=19）を下回る** — ロールバック条件と経緯の正本は `design-notes/triage-rationale.md`

**`recall_skeptic`** — 冷や読み skeptic の実行記録。high 昇格判断（triage-dynamic-gates.md `## 8.5`）の計測データ:

- `surface`: high-risk surface 判定の結果（bool）。**skeptic が effort / userConfig でスキップされた場合も、正規表現部分の判定だけは payload 構築時に必ず実施して記録する** — 「surface=true なのに effort ゲートで走らなかった頻度」が昇格判断の核心メトリクスのため
- `fired`: skeptic agent が実際に起動したか（bool）
- `skip_reason`: `fired=false` のときの理由。`"effort"` / `"config"` / `"no-surface"` / `"emergency"`（self-review は `"scope"` = `--focus`/`--exclude` 指定も取りうる）。`fired=true` なら `null`
- `gate_schema`: **起動ゲートの版**（GitHub issue #115）。**`publish-review-event.sh` が注入する**（2 = high 起点に昇格した v2.52.0 以降）。`attribution_schema` が由来タグの版であるのに対し、こちらは**どの effort で起動する構成だったか**を識別する。**これが無いと `## 8.5` の監視クエリ①（「昇格後は `skip_reason="effort"` が消えるはず」）が昇格前の残骸を拾い続け、永久に偽の「信号あり」を返す** — 実装バグが起きても検知できない。日付では切れない（配布ラグで未更新マシンは旧ゲートで publish し続ける）
- `attribution_schema`: 由来帰属の規約バージョン。**`publish-review-event.sh` が注入する**（2 = 由来タグがレポート書式に規定され dedup のタグ生存も定義された版 = 2.35.1 以降）。schema 1 相当の旧サンプルは `findings_added` が記憶依存で系統的に 0 へ潰れており判断に使えないため下流はこれで濾す。**日付では切れない**（配布ラグで未更新マシンは修正日以降も schema 1 を publish する）
- `findings_added`: **skeptic 単独由来**（`[recall-skeptic]` タグ）の指摘のうち報告マトリクスを通過した件数。**レポート「動的ラウンド」行の `実行（N 件追加）` の N と同値**（N はヘッダに置かれるが**本文確定後に数えてヘッダへ反映する**。二重管理にしない）。**価値率の分子はこれのみ**
- `findings_overlap`: **重複 survivor**（`[recall-skeptic:dup]` タグ）の件数。独立到達の記録としては残すが、盲点でなかった事例なので**価値率には算入しない**（混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる）
- 両フィールドとも **初回レポート本文のタグ付き指摘を数えて求める**（skeptic フェーズの記憶から再構成しない。publish は遠く、間に精査・解説・ドラフト生成が挟まるため記憶依存にすると系統的に 0 へ潰れる）。**計測点は報告マトリクス通過時点（精査の前）**であり、精査後の調整レポートではない。**精査で取り下げた分は減算しない**（「報告に値する指摘を出せたか」を測るフィールドで、必要性で落ちたかは別軸）

**`comment_polish`**（**self-review のみ** / v2.45.0）— コメント推敲（`prompts/focus/comment-polish.md`）の実行記録:

- `fired`: **`comment-accuracy` 観点が構成に入り、B 系統ブロックを連結して reviewer を起動したか**（bool）。**単独起動とバンドル相乗りを区別しない**（high 既定では束ねが常態で、束ね時に「comment-accuracy reviewer」という単独 agent は存在しない。「専任 reviewer が立ったか」と読むと既定構成で常に false になる）
- `suggested`: **reviewer が B 系統で挙げた総件数**。掲載上限（10 件）で切る前・二重掲載の除去前の数を入れる。**レポート掲載数とは一致しない**（掲載数は上限と dedup の後）。reviewer が `## コメント推敲提案` ブロックごと出力しなかった場合は **`-1`（測定不能）**とし、`missing_coverage` に `comment-accuracy` を記録する（「該当なし＝観点は効いたが 0 件」と「ブロック欠落＝観点が実質死んだ」を 0 に潰さない）
- **2 フィールド持つ理由**: 「起動したが提案 0 件」（打ち手＝観点の効き・プロンプトの具体性）と「そもそも起動していない」（打ち手＝ triage の起動条件・Step 4 の連結漏れ）は対処が正反対。本機能は *チェック項目に書いてあるのに報告まで到達しない* という失敗の再発防止が目的なので、**出力ゼロが観測できないと同じ穴に落ちる**
  - この失敗の論拠は**構造**（MINOR 95+ ＋ 好みクランプ 40 を推敲提案が通過できない）であって計測ではない。payload は focus 別の属性を持たないため、「v2.44.0 まで報告ゼロだった」を実測で示すことはできない（**この点を実測事実として書かないこと**）
- review 側は publish しない（B 系統は self-review 限定。他人の PR への推敲提案は越権になりやすいという設計判断）

**`tokens`（**review のみ** / v2.65.0 / GitHub issue #126）** — publish 時に `measure-tokens.sh --json` を呼んで注入する。**`## 17` の「skill 実行中に自分の消費量を観測できない」制約は publish 時点には当たらない**（publish はレポートの後 ＝ transcript 確定後）:

| サブフィールド | 内容 |
|---|---|
| `schema` | 算出方法の版（現行 `1`）。スクリプトが注入する |
| `window` | `"since-t0"`（`t0` マーカー以降だけを集計）/ `"session"`（`t0` を撮れずセッション全体を集計）。**集計側は `since-t0` だけを使う** |
| `session` / `first_ts` | どの transcript のどこからを数えたか（取り違えの事後検出用。下記） |
| `main_output_k` | メインループの `output_tokens` / 1000。**プロンプト複製の単価が最も高い項**（`## 17` の表） |
| `main_cache_write_k` | 同 `cache_creation_input_tokens` / 1000。**分冊・遅延読み込みの効果判定には使わない**（#118 の交絡） |
| `sub_output_k` | サブエージェント側の `output_tokens` / 1000。**体数と 1 体あたりの探索量が出る** |
| `sub_agents` | **窓内に usage を持つ**サブエージェント transcript の本数。**`measure-tokens.sh --json` の `sub_files`（glob 総数・窓非適用）は載せない** — 同じオブジェクトに窓ありと窓なしを混在させると、`sub_output_k / sub_agents`（1 体あたりの探索量）が窓外の体数で薄まる |

- **なぜ載せるのか**: triage-guide.md `## 7` の核心テーゼは「**体数削減が確実に効くのは壁時計ではなくトークン**」なのに、payload は所要時間しか持たず、`## 18` の自動集計も時間だけを見ていた。つまり**主要レバーが効かない指標を自動集計し、効く指標を集計していなかった**（issue #126）
- **self-review は載せない**。**`EnterWorktree` は cwd と subagent の slug を変えるだけで、セッション自体はメインリポジトリで始まったまま**なので（`## 17` の候補 dir 探索がこれを前提にしている）、review も「隔離セッション」ではない。両者を分けるのは **publish の位置**で、review は `t0 → レポート → publish` が 1 レビューで閉じる直列区間なのに対し、**self-review は publish（Step 6.4）の後に Step 7 の修正方針確認と修正作業が続く**。窓の外に本作業が続く側では近似が成立しない。**この非対称は仕様**であって欠測ではない
- **窓は `t0` 以降であってレビュー区間そのものではない。** review でも、レビュー中にユーザーが別作業を挟めば混ざる。**「粗い k 値」として読み、前後比較は同じ PR / 同じ diff で行う**（`## 17` と同じ流儀）
- **どの transcript のどこからを数えたかは `session` / `first_ts` に残す。** セッションの選択は「候補 dir の最新 `.jsonl`」という推定で、worktree 並列運用では取り違えうる。値そのものはもっともらしいので、**この 2 つが無いと取り違えを事後に検出する手段が消える**
- **`main.n == 0` は「トークンが 0 だった」ではない。** review は必ずメインループのメッセージを出してから publish するので、0 は「transcript を引けなかった」か「窓が空振りした」を意味する。この回は `tokens` を載せず `measurement_gaps` に `tokens` を立てる（ゼロを実測値として載せると retro の中央値と体数相関が壊れる。実測で相関が 1.00 → 0.18 に落ちた）

**共通ルール**:

- publish に失敗してもレビュー自体は成功扱い（best-effort）。`SAFE_HOOK_NAME` を publisher 名（`code-review:review` / `code-review:self-review`）に上書きして識別する
- 後方互換: subscriber 側は `critical_count` の存在を仮定してよい（旧 payload との互換性のため必須）。それ以外は新規フィールド追加なので旧 subscriber 影響なし（現物確認: `issue-workflow:issue-maintain` は `pr` と件数しか読まない）
- **ゲートを動かす変更には必ず版マーカーを足す**（GitHub issue #115 の一般化）。effort ゲート・起動条件・算出方法を変えると**フィールドの有無は変わらないのに意味が変わる**ため、「フィールドの有無で層別する」という下のルールだけでは新旧を区別できない。`recall_skeptic.gate_schema` / `pre_adjust_counts.schema` と同じく publisher 側の整数を足すこと。**足す先は `publish-review-event.sh` の `SCHEMA_MARKERS` と上の「版マーカーの現行値」表の 2 箇所**（v2.65.0〜。SKILL のテンプレートに手書きさせない — 定数を LLM に持たせると version drift 中に落ちる / issue #125。2 箇所の同値は `validate_plugin_quality.py` が検証する / issue #134）。**例外は「片方の skill でしか載らないフィールド」**（現行 `tokens`）で、そちらは構築ブロックのリテラルに置く（理由は同表の注記）
- **動的層を足すときは `fired` / `skip_reason` / `gate_schema` の 3 点セットを必ず持たせる**（v2.65.0 / issue #129 の一般化）。verdict や件数だけでは **「走らなかった」と「走れる対象が無かった」を区別できず**、ゲート設計の妥当性が永久に測れない。`skip_reason` の語彙には**「設計上の非該当」（effort / config / scope / emergency）と「ゲートに該当する対象が 0 件」を別の値で**入れること（前者だけが下流の分母から外れる）
- 版マーカー: **`duration_triage_min` の存在が v2.41.0 以降・`duration_explore_min` の存在が v2.43.0 以降・`pre_adjust_counts` の存在が v2.44.0 以降（**算出方法の版は `pre_adjust_counts.schema`**）・`comment_polish` の存在が v2.45.0 以降（self-review のみ）・`severity_threshold` の存在が v2.58.0 以降・`duration_synthesis_min` の存在が v2.60.0 以降（**meta の起動ゲートの版は `meta_reviewer.gate_schema`**）・`agents.explorer_waves` の存在が v2.61.0 以降・`measurement_gaps` / `diff_digest` の存在が v2.62.0 以降（**上流 severity 較正の版は `adversarial_verify.calibration_schema`**）・`adversarial_verify.fired` / `tokens` の存在が v2.65.0 以降（**反証の起動ゲートの版は `adversarial_verify.gate_schema`**）**。層別は必ずフィールドの有無で行い、日付では切らない。**v2.43.0 未満の `duration_*` は並行セッション汚染を受けうる**（issue #99）ためロールバック判断の基準側に使わない
- **集計は `scripts/review-retro.sh` が行う**（v2.62.0 / issue #123 E）。上の層別ルール（版マーカーで切る / 累計で読まない / 区間を混ぜない）をスクリプト側に閉じてあるので、**jq を毎回組み立てない**。人間向けレポートは publish の直後に自動で出る（review 締めフロー 4 / self-review Step 6.4）。`--json` で機械可読、`--since` / `--last` で範囲を絞れる

## 17. トークン消費の計測（改修の前後比較 / v2.48.0）

トークンは **transcript から事後に集計する**（各アシスタントメッセージの `usage` が正本）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh"            # 現リポジトリの最新セッション
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh" --list     # セッション候補
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh" --since 2026-08-06T10:00  # 時刻で絞る
bash "${CLAUDE_PLUGIN_ROOT}/scripts/measure-tokens.sh" --json     # 機械可読（publish が使う）
```

> **review の粗い値は payload に自動で載る**（v2.65.0 / issue #126）。「skill 実行中に自分の消費量を観測できない」という制約は **publish 時点（レポート出力後 ＝ transcript 確定後）には当たらない**ため、`publish-review-event.sh` が `--json --since <t0>` で呼んで `tokens` フィールドに入れ、`## 18` の retro がトレンドを出す。**本節の手動実行が要るのは** ①self-review（payload に載らない）②取り込み内訳を見たいとき ③特定セッションを指定したいとき。契約は `## 16` の `tokens`。

> **worktree 内から実行しても引数なしで通る**（GitHub issue #112）。transcript の slug はセッションを**開始した**ディレクトリ由来なので、review 経路（Step 0 で必ず `EnterWorktree`）では cwd 側の slug にメインループの transcript が存在しない。スクリプトは **cwd 側とメインリポジトリ側（`--git-common-dir` 由来）の両方**を候補にして最新の `.jsonl` を採るので、review 後にそのまま実行してよい。dev-workflow の作業用 worktree 内で開始したセッション（transcript が cwd 側にある逆パターン）も同じ仕組みで拾える。**どちらの候補にも無いときは `--session <絶対パス>`** を使う（`--list` が探索したディレクトリを表示する）。

Claude Code の transcript（`~/.claude/projects/<slug>/*.jsonl`）は各アシスタントメッセージに `usage` を持ち、`isSidechain` でメインループとサブエージェントを分離できる。スクリプトはこれを `main` / `sub` に分けて集計する。

| 指標 | 意味 | 何の効果が出るか |
|---|---|---|
| `main.output` | オーケストレーターが**書いた**量 | プロンプト複製（**単価が最も高い**。パス渡し化の効果はここ）。**分冊・遅延読み込み以外の削減はまずこれで見る** |
| `main.cache_write` | オーケストレーターが**新規に読んだ**量 | 参照 doc の読み込み **+ agent 出力の取り込み**（下記の交絡に注意） |
| **取り込み内訳** | main の `tool_result` を経由別に分解した**文字数** | `main.cache_write` の内訳。Agent 経由の占有を見てから `cache_write` を読む |
| `sub.*` | サブエージェント側 | 体数・1 体あたりの探索量 |
| `cache_read` | 再利用ぶん | 単価が低い。**前後比較の指標には使わない** |

> **`main.cache_write` で分冊・遅延読み込みの効果を判定してはならない**（GitHub issue #118）。**参照 doc の読み込みと agent 出力の取り込みが同じバケツに入る**ため、fleet が大きい review では後者が支配的になりうる。実測（agent 13 体）では `main.cache_write` が 1,501.9k だったが、この内訳は分離できていなかった。**分冊を進めても値が下がらない / 体数が増えると値が上がる**という交絡した数字で判断してしまう。
>
> `measure-tokens.sh` は**取り込み内訳**（`tool_result` の実体サイズを経由別に集計）を出すので、まず `Agent` の占有を見る。占有が高いサンプル同士の `cache_write` を比べても doc 側の差は読めない。
>
> **文字数はトークンではない**（換算係数が内容種別で変わる）。**経由別の比率**として読み、絶対値をトークンと混ぜない。
>
> 分冊の効果を単独で見たいときの確実な方法は次の 2 つ:
> - **`main.output` を一次指標にする** — パス渡し化（`orchestration-guide.md ## 3.5`）の効果は output 側に出るので、多くの場合これで足りる
> - **agent を起動しない経路で測る** — Phase 0 までで中断、または `skip-mode` のサンプルなら取り込みが混ざらない
>
> 「同じ PR / 同じ diff で比較する」だけでは交絡は消えない。**体数は effort と規模キャップで変わる**（`triage-guide.md ## 7` / `## 6.2`）ため、**effort を変える A/B ではこの交絡が直接効く**。

- **比較は同じ PR / 同じ diff で行う**（規模が変われば当然変わる）。`size_tier` を揃えるのは `duration_fleet_min` と同じ流儀
- **`duration_*` と混ぜて 1 つの結論を出さない**。体数削減が確実に効くのはトークンであって壁時計ではない（triage-guide.md `## 7`「体数を壁時計のレバーとして扱わない」）
- transcript はセッション単位なので、**1 セッションで 1 レビューだけ回したときが最も読みやすい**。複数回した場合は `--since` で切る

## 18. 蓄積イベントの振り返り集計（publish の直後 / v2.62.0 / GitHub issue #123 E）

`triage-guide.md` / `triage-dynamic-gates.md` には各層の**ロールバック条件・再監視の条件**が随所に書いてあるのに、**それを判定するための集計手段が無かった**。条件は比率と件数で決まる決定的な計算なので、LLM に毎回 jq を組ませずスクリプトへ閉じる（CLAUDE.md「ルール配置の意思決定: 決定的 hook > LLM 判定」）。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh"              # publish 直後に毎回実行する
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh" --last 20    # 直近 N 件だけ
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh" --json       # 機械可読
```

**出力の読み方**（本ファイルの他節が正本である解釈をここに複製しない。以下は「どの節に戻るか」の対応表）:

| 出力 | 戻り先 |
|---|---|
| effort × size_tier の fleet / 体数、体数 vs fleet の相関 | triage-guide.md `## 7`（**体数を壁時計のレバーとして扱わない**）。**結論文は `r` と n で分岐する** — n < 10 は解釈しない / `|r| < 0.3` は上記主張を支持 / 0.3〜0.6 は effort の交絡を疑って帯別に見る / `|r| >= 0.6` は ⚠️ シグナルとして同主張の**再監視条件**に該当。低いこと自体は打ち手にならないが、**高いことは打ち手になる** |
| 区間の中央値（triage / explore / fleet / synthesis / closing） | `## 14`（synthesis が支配的ならメイン側、そうでなければ wave 側） |
| pre_adjust → 報告の歩留まり | `## 16` の `pre_adjust_counts`（**schema 2 同士・同一 `severity_threshold` でのみ比較**） |
| 反証 verdict 分布（`calibration_schema` 層別） | triage-dynamic-gates.md `## 9` / `prompts/reviewer-common.md`「降格される典型パターン」 |
| 動的層の発火率と skip 理由 | 同 `## 8`（meta）/ `## 8.5`（skeptic）/ `## 9`（反証のゲート幅） |
| トークン（main.output / sub.output / 体数との相関） | `## 17` と triage-guide.md `## 7`（**体数が効くのはこちら側**。壁時計の結論と混ぜない） |
| 計測の健全性（欠測内訳） | `## 14` の打点規約 |

**⚠️ シグナル行が出たときだけ行動する。** 各シグナルは対応するロールバック条件・再監視条件のトリガーで、閾値とサンプル数下限はスクリプト側に埋めてある（例: skeptic 価値率は `fired >= 15` かつ 25% 未満、meta は `fired >= 10` かつ 20% 未満）。**シグナルが出ていない指標を眺めて打ち手を決めない** — 「サンプルが無いうちは判断しない」（triage-guide.md `## 7`）を集計側でも守るための設計。

- **人間向けレポートに毎回出す**のは、集計が「気が向いたときにやる作業」に落ちると条件判定が永久に走らないため（本 issue の発端がまさにそれ）。出力は 40 行程度で、レビュー本体のレポートより後に置く
- **publish の後に実行する**（自分の回を集計に含めるため）。失敗してもレビューは成功扱い（best-effort）

## 19. 直近レビューとの重複検出（review Step 2.4 / self-review Step 1.4 / v2.62.0 / GitHub issue #123 D）

`--focus` / `--exclude` は**同一 skill 内**の重複しか防げない。実測では self-review と PR レビューが同一 diff を 2 回舐め、互いを知らないまま同じ 3 件に独立到達していた。skill をまたぐ重複は仕組みで拾えていなかったので、publish 済みの計測イベントを突合キーにする。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh" [--diff <実パス>] [--pr N] [--window-hours 24]
```

**突合キーは強弱 2 本ある**（算出の正本は `scripts/lib/review-paths.sh` の `review_diff_keys`、payload 契約は `## 16`）:

| キー | 一致する範囲 | 読み方 |
|---|---|---|
| `diff_digest`（強） | **同一 skill の再実行のみ** | 「同一 diff」と断定してよい |
| `diff_files`（弱） | **skill を跨いでも一致する** | 「重複の疑い」どまり。**別内容の変更でも一致しうる** |

- **強いキーだけでは skill 跨ぎを拾えない。** review は `gh pr diff`、self-review は `git diff BASE..HEAD` + `--cached` + unstaged の**3 本連結**で diff を作るので、同じ変更でもバイト列が違う（実測で確認済み。`## 16` の `diff_digest` 行）。**動機となったシナリオそのものが強いキーの外にある**ため、弱いキーを併設した
- **判定材料は前回の payload だけ**で、指摘本文は読まない（**前回の結論に引きずられないため**。独立性は反証レイヤー / skeptic と同じ理由で守る）
- **出力が空なら何も報告しない**（no-op を報告させない）。`events.jsonl` が無い / `python3` が無い場合も silent に抜ける。**ただし `--diff` を明示指定して不在だった場合だけは stderr に WARN する** — それは caller のバグであって「重複が無い」ではない
- **`--diff` は省略してよい**（省略時は `review_path diff` を自力導出する。`triage-signals.sh` の既定出力先・publish の digest 算出元と同一関数なので、**省略した方が転記ずれの失敗モードが無い**）
- **突合キーを作れなかった回は `measurement_gaps` に `diff-digest` が立つ**（`## 16`）。「検出できなかった」を「重複が無かった」に潰さないための可視化
- `events.jsonl` の探索は publish 側（`--git-common-dir` の親）と `review_main_root`（`git worktree list`）の**両方**を候補にする。submodule / `--separate-git-dir` では両者が食い違い、片方しか見ないと「書けているのに読めない」で検出が silent に死ぬ。**パスは配列で持つこと**（空白区切り文字列 + 未クォート展開は、空白を含むリポジトリパスで同じ silent 死を招く。実測で再現済み）
