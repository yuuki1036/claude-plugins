# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [2.45.0] - 2026-08-06

self-review に**コメント推敲**を組み込んだ版。毎回手で頼んでいた作業をスキル側に載せる。

### Added
- **コメント推敲（B 系統）を self-review に追加**（reviewer-prompts.md `### コメント推敲（B 系統）` + self-review SKILL.md Step 4 / Step 5 手順 1・7 / Step 6 / Step 6.4 + triage-guide 観点判定表）。diff で追加・変更されたコメントを **①読み手にとって必要な情報のみか ②冗長表現が排除されているか** の 2 観点で推敲し、`before` → `after` の最小差分でレポートの「✏️ コメント推敲」セクションに出す:
  - **severity マトリクスを通さない別経路にした**。`comment-accuracy` はチェック項目に「冗長コメント」「what ではなく why」を持つが、推敲提案は**構造上 2 段のフィルタを通過できない**: ①報告マトリクスは MINOR を confidence 95+ でしか通さない ②scoring-guide の好みクランプが「CLAUDE.md / style guide / 計測データ / file:line の具体的不具合」の 4 つのいずれの根拠も持たない指摘を confidence 40 に落とす（文体規約を持たないプロジェクトの推敲提案がこれに該当）。**どちらもバグ指摘の precision を守るための正しい機構**なので、推敲側をパイプラインから外す。severity / confidence を付けず、手順 1〜6 と反証レイヤーをすべてバイパスする
    - **根拠は構造であって計測ではない**: payload は focus 別の属性を持たないため「報告ゼロだった」を実測で示すことはできない（v2.44.0 の 43 件集計でも focus 別の内訳は取り出せない）。doc 側にも実測断定を書かない旨を明記した
  - **体数は増やさない**。既存の `comment-accuracy` reviewer に相乗りさせる（起動条件も共用）。バンドルで束ねられた場合も出力契約は削らず、`comment_polish.fired` は `true` を記録する（専任 reviewer の有無で切ると high 既定で常に false になる）
  - **過剰修正の抑制**: 対象は diff で追加・変更されたコメントのみ / 意味が変わらない同義変換は出さない（短くなる・曖昧さが減る、のどちらかが無い提案は却下）/ 非自明な why・TODO の背景・regex や境界条件の意図・外部制約への言及・ハマりどころの警告は残す（迷ったら残す側に倒す）
    - **件数上限は reviewer にかけない**（発見段階の重要度による自己間引きは CLAUDE.md「Opus 5 世代で逆効果になる足場」③に該当する）。掲載上限 10 件はオーケストレーター側（Step 6）で切り、`suggested` には切る前の総数を入れる
  - **二重掲載の除去は「報告マトリクスを通過して残った指摘」とだけ突合する**。「A 系統が指摘として挙げた」を条件にすると、A で MINOR 95+ に阻まれ B でも dedup される二重落ちが起き、B 系統を作った理由そのものを打ち消す
  - **review 側には入れない**。他人の PR に文面の推敲を投稿するのは越権になりやすく、review の返答ドラフトは PR コメントとして投稿される前提のため。B ブロックは Focus テンプレートと同格の見出しに置きつつ「Focus テンプレートではない」と明示し、**両 skill の Step 4 に連結可否を 1 行ずつ書いて**混入と不発の両方を塞いだ（散文 1 行のガードだけでは、両 skill の起動指示が同一文言のため review 側に混入する経路が残る）
  - **embed mode の findings JSON には含めない**（severity を持たず、auto-fix の対象にしない。採否は人間が決める）
- **`comment_polish` を `review:completed` payload に追加**（self-review のみ。`{fired, suggested}`）。「起動したが提案 0 件」（打ち手＝観点の効き・プロンプトの具体性）と「そもそも起動していない」（打ち手＝ triage の起動条件・Step 4 の連結漏れ）は対処が正反対なので 2 フィールド持つ。本機能は *チェック項目に書いてあるのに報告まで到達しない* という失敗の再発防止が目的であり、**出力ゼロが観測できないと同じ穴に落ちる**:
  - `fired` は**観点として起動されたか**で判定する（単独／バンドル相乗りを問わない）。`suggested` は reviewer が挙げた**総件数**（掲載上限・dedup の前）で、レポート掲載数とは一致しない。reviewer が `## コメント推敲提案` ブロックごと落とした場合は `-1`（測定不能）とし `missing_coverage` に記録する — 「該当なし」と「ブロック欠落」を 0 に潰さないため
  - 版マーカー: `comment_polish` の存在が v2.45.0 以降（self-review のみ）

## [2.44.0] - 2026-08-06

蓄積済み 43 件（`review` 12 / `self-review` 31）を実際に集計して、**計測が答えられない問い**と**規約と実データの乖離**を 3 つ見つけて塞いだ版。仕様（scoring / 報告マトリクス）には手を入れていない — 切り分けデータが無い段階で precision に関わる不可逆な変更をしないため。

### Added
- **`pre_adjust_counts` を `review:completed` payload に追加**（orchestration-guide `## 16` + 両 SKILL のスコアリング手順 1）。スコアリング手順 1 完了時点（統合・dedup 後、verdict 反映・加減算・降格・フィルタの**前**）の severity 別件数。既存の `*_count` は報告マトリクス通過**後**の値しか持たないため、**「reviewer が検出しなかった」と「検出したが調整で消えた」を事後に区別できなかった**:
  - 動機は下記の観測（triage-guide `## 7` の「未解決の観測」に記録）。**review 経路 12 件すべてで `major_count`=0** の一方 self-review は 31 件で MAJOR 78 件。MAJOR と MINOR は報告マトリクス上どちらも confidence 95+ の同一閾値なのに review では MINOR だけ 27 件通っており、しかも review は `recall_skeptic.surface` が 10/10 で true（= surface-aware 閾値で MAJOR が 85+ に**緩和されている**状態）でゼロ。両 SKILL の scoring 規約は同一であることを確認済みで、仕様差では説明がつかない
  - **一段目（検出由来 / 調整由来）だけを切るフィールド**。降格（`severity-inflated` / `[scope:out]`）と confidence 落ちは同じ差分に合流するので内訳は分離できない。二段目が必要と分かってから内訳フィールドを足す（LLM が手で組む JSON なのでフィールド数自体がコスト）
  - 版マーカー: `pre_adjust_counts` の存在が v2.44.0 以降

### Fixed
- **`missing_coverage` の語彙を固定**（orchestration-guide `## 16` + 両 SKILL のレポート出力）。要素を **識別子のみ**（`<focus 名>` / `<phase 名>` / `<phase 名>:<focus 名>`）に限定し、理由・件数・finding id・自由文の混入を禁止した。理由はレポート本文の「⚠️ 欠損観点」セクションに書く。実データでは同一概念が `adversarial-verify:finding-A` / `adversarial-verify-finding3` / `adversarial-verify: F2 未反証` / `adversarial-verify: 対象が実証済み` の **4 通りに分裂**しており、`group_by` 集計が成立していなかった（欠損観点の偏りを見るのが本フィールドの唯一の用途なので、綴りが割れると計測目的そのものが消える）
- **`result_grid.error` = `len(missing_coverage)` の一致要件を撤回**（orchestration-guide `## 16`）。`missing_coverage` は agent 失敗だけでなく「観点未起動（reviewer 上限超過・条件不成立）」「フェーズスキップ」も含むため、正しい関係は `error ≤ len(missing_coverage)` の包含。**実データ 43 件中 11 件で不一致**（うち 10 件は `error=0` で `missing_coverage` が非空）。一致を仮定した検算をしない旨を明記した

## [2.43.0] - 2026-08-04

`review` 経路で 2 つの構造的な壊れ（子 agent が base branch を読む / 計測が並行セッションに汚染される）を塞ぎ、壁時計の残る主因である「メインコンテキストのプロンプト複製」と「直列 wave 数」に手を入れた版。

### Fixed
- **子 worktree の `gh pr checkout` が構造的に必ず失敗し、agent が base branch のファイルを読んでいた**（GitHub issue #98。explorer-prompts / reviewer-prompts の共通指示 + orchestration-guide `## 1`）。review skill は Step 0 で `EnterWorktree`、Step 1 で `gh pr checkout` するため**親 review worktree が PR ブランチを保持している**。子 worktree は親 branch を継承せず origin/default から派生するので `HEAD != {{HEAD_REF}}` が常に成立し、else 分岐の `gh pr checkout` が git の二重チェックアウト禁止で失敗する。テンプレートは失敗時に続行するため、**テンプレート自身が「深刻な偽陽性の原因」と警告している状態のままレビューが走っていた**。issue #69 の `{{HEAD_REF}}` ガードは「親が checkout 済みなら子でスキップ」の意図だったが、子の HEAD が PR ブランチになることはないため review 経路では一度も発火しない:
  - ブランチ名での checkout を廃止し、`git fetch origin refs/pull/<N>/head` + `git checkout --detach FETCH_HEAD` に変更（detach なら親と競合しない）
  - 検証を **期待 HEAD SHA（`{{HEAD_SHA}}`）との突合**に変更。`{{HEAD_REF}}` はブランチ名なので detach 後の検証には使えず、プロンプト冒頭の文脈情報としてのみ残す。オーケストレーターは Step 1 の `gh pr view --json headRefOid` で取得して全 agent に注入する
  - 不一致時は「レビュー結果の冒頭に warning を明記し confidence を下げる」を明示（silent に続行させない）
- **`TS_FILE` が worktree 間で衝突し `duration_*` が「もっともらしい誤値」で publish されていた**（GitHub issue #99。orchestration-guide `## 13.1` + 両 SKILL）。`--git-common-dir` は linked worktree からもメインリポジトリの `.git` を返すため、publish 先をメインルートに固定する目的（#96）には正しい一方、**同一リポジトリの全 worktree で `MAIN_ROOT` が同一**になり `TS_FILE` が 1 本に collapse していた。Step 1 は `>` の truncate で書くので後発セッションが先行のマーカーを消し、締めフローの `rm -f` は走行中の他セッションのマーカーを削除していた。**汚染が欠測（`-1`）ではなく過小値として入る**ため、ロールバック判断の一次指標 `duration_fleet_min` が静かに壊れる（実測: 52 分のレビューが約 8 分）:
  - **パスの識別子を `git rev-parse --show-toplevel`（その worktree 自身のパス）から作る**。`--git-common-dir` が全 worktree で同じ値を返すのに対しこれは worktree ごとに異なるので、1 つで並行セッションを分離できる。review はさらに PR 番号を混ぜる。識別に失敗したときの縮退先は「別ファイル ＝ 欠測」であって誤値ではない
  - **ブランチ名は識別子に使わない**。`git rev-parse --abbrev-ref HEAD` は **detached HEAD でも `HEAD` を返す**ため `${VAR:-fallback}` が発火せず、detached な worktree がすべて同じ slug に collapse する（`git bisect` 中に発生）。切り詰めによる長いブランチ名の接頭辞衝突も同様。初版はブランチ slug を使っていたが、セルフレビューで両方の反例が実測されたため差し替えた
  - `rm -f` を `t2` マーカーの存在確認つきに変更。ただし**これは所有権チェックではなく近似**（ファイル内容に書き手の識別子が無い）。衝突自体は上記のパス識別子で塞ぎ、このガードは万一の衝突時に掃除より他セッションの計測を優先する二段目、という位置づけを doc に明記した
  - v2.43.0 未満の `duration_*` は汚染を受けうるため、ロールバック判断の基準側に使わない旨を doc に明記

### Added
- **大きい共有コンテキストのファイル経由渡し**（GitHub issue #100 A。orchestration-guide `## 3.5`）。Step 2.5 の「LLM による再構築・要約・編集は禁止」は正しいが、素直に実装するとオーケストレーターが同一ブロックを N 体ぶん**書き出す**設計になっていた（実測: PR コンテキスト約 15,000 字 × 6 体。52 分のレビューのうち agent 実時間 29 分を除いた約 20 分がメインコンテキスト）:
  - `fetch-pr-context.sh` の出力を `$PR_CTX_FILE`（`$TMPDIR` 配下・PR 番号入り）に保存し、reviewer には**パスのみ**渡して自分で Read させる。**忠実性はむしろ上がる**（バイト同一で転記リスクがゼロ＝「再構築禁止」を機械的に保証）。子 worktree でも `$TMPDIR` は同一ホストなので読める
  - AGENTS.md / CLAUDE.md の階層注入も**元ファイルのパス渡し**に変更（既にディスク上にあるのでコピーも不要）
  - explorer 結果は**従来どおりインライン**（選択的注入で複製係数がほぼ 1。ファイル化すると explorer 体数ぶんの Write が増えて逆効果）
  - ファイル書込に失敗した場合はインライン注入にフォールバックする（レビュー本体をブロックしない）
  - パス導出の `WT` は**それを使う bash ブロック内で導出する**。別ブロックの変数は消えており、空のまま `printf %s "" | cksum` を通すと**エラーにならず定数 `4294967295` が返って**パスが「ホスト上の全リポジトリで共有される固定値」に潰れる（＝別リポジトリの PR コンテキストを掴む誤値縮退）。初版はこれを踏んでおり、セルフレビューで 4 体が独立に検出した
  - 保存は**一時ファイルに書いて成功時のみ `mv`** する。`>` はスクリプト失敗時も空ファイルを残し、空ファイルは「読める」ため reviewer の「読めなかった場合」ガードをすり抜けて「過去指摘なし」と誤判定される
- **Phase 0 の構成テーブルに「直列 wave」行を追加**（GitHub issue #100 B。triage-guide `## 5` / `## 5.1`）。ユーザーに見えていたのは体数だけで、壁時計を決める直列 wave 数は最後まで見えなかった。**体数はトークンコストのレバー、wave 数は壁時計のレバー**という `## 7` の切り分けをそのまま表示する（下限＝ Phase 0 で確定している wave / 上限＝条件付き wave が全部発火した場合、wave あたりの目安時間つき）
- **`duration_explore_min` の計測**（GitHub issue #100 D。orchestration-guide `## 14`）。`t1` を explorer 発行直前に置いた v2.41.0 の修正の副作用で、fleet 区間に「explorer wave + reviewer wave + プロンプト構築 + scoring」が全部入り、どの wave が何分かかったか分からなくなっていた。explorer 回収直後に `t1b` を置き、`t1`→`t1b` を explorer wave の実時間として切り出す（`duration_fleet_min` の内数。explorer 未起動時は `-1`）。triage-guide `## 5.1` が Phase 0 で提示する「wave あたり目安 6〜16 min」を実測で裏付けるフィールド（実測: explorer 2 体で 5.9 分）
  - **「メインコンテキストのプロンプト構築時間」はマーカーでは測れないと確定した**（同節）。プロンプトのテキストを書く行為がそのまま Agent call の発行であり、「書き終わったが未発行」の瞬間が存在しないため、マーカーを発行より前に置けば書く前に発火し、後ろに置けば agent が既に走っている。初版では `t1c` / `duration_prep_min` でこれを測ろうとしたが、セルフレビュー実測で**発行直前マーカーが 7 秒**（同じ fleet 区間は 22 分）を記録して構造的に不可能と判明したため撤回した。`## 3.5` の外出し効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る
- **HEAD 検証の機械的回収**（GitHub issue #98 の未達分。orchestration-guide `## 5` + 両プロンプトテンプレート）。SHA を注入しても、検証結果を報告する必須欄が無ければ「検証を怠った / 一致した / 不一致だが warning を書き忘れた」がオーケストレーターから区別できず、issue #98 が名指しした「自己申告に委ねている」構造が残る。出力フォーマットに **`HEAD 検証: <実測 SHA> / 期待 <SHA> / 一致|不一致|未実行` の必須 1 行**を置き、不在・不一致なら `missing_coverage` へ記録し当該 agent の指摘全件に `[unverified: HEAD 不一致]` を付ける。`review:completed` payload に `head_verified: {ok, mismatch, unknown}` を追加し、「何体が正しい HEAD を見ていたか」を事後集計できるようにした。**行の不在自体が信号**になるので agent の善意に依存しない
- **xhigh / max の反証ゲートと非対称ゾーン論の緊張を明文化**（GitHub issue #100 補足。triage-guide `## 9`）。xhigh / max のゲートは「報告ゾーン全体 + MAJOR」なので confidence 95+ の最も取り下がりにくい層が全件対象になり、直列 wave 1 本（6〜16 min）を要する。据え置く理由（明示 escalation での偽陽性コストの非対称性）と、壁時計を縮める必要が出たときの最初の候補（MAJOR 95+ をゲートから外す）を記録した

### Changed
- **Round 2 のスキップ条件に「unmet が全件 repo 外」を追加**（GitHub issue #100 C。triage-guide `## 8` + orchestration-guide `## 6` + 両 SKILL）。実測では unmet 8 件のうち 7 件が構造的に到達不能だった（DB / 本番の実データ、外部サービスの実挙動、repo に存在しない旧実装、意図的にスキップした lint 実走）。target の分類は文字列を読めば決まるのでメインコンテキストで判定でき、agent を要さない。**ただし無条件スキップは有害**なので「全 target が repo 外のときだけ」に限定する — 実測で到達可能だった 1 件（DB 制約）を Round 2 が repo 内 doc で解決した結果、指摘 1 件の severity が MAJOR → MINOR に変わっている。判定に迷う target は repo 内側に倒す。スキップ時は `missing_coverage` とレポートの「動的ラウンド」行に理由を出す
- **`duration_triage_min` を「メイン思考量の代理指標」として使うのをやめた**（issue #100 D）。`duration_fleet_min` の説明に「プロンプト構築を含む（分離できない）」を明記し、triage-guide `## 7` の打ち手③（壁時計を縮めるときにまず触る箇所）も「メインコンテキストの思考量（`duration_triage_min` で観測）」から「プロンプト複製量（`## 3.5` のファイル経由渡し。効果は `duration_fleet_min` の層別で見る）」に差し替えた — 定義変更が消費サイトに伝播していなかった
- **agent の checkout ブロックに dirty tree ゲートを追加**（両プロンプトテンプレート）。`git checkout --detach` は**未コミット変更があっても exit 0 で成功し変更を持ち越したまま detach する**（実測）。隔離 worktree はレビュー開始時点で必ず clean なので、dirty なら「ユーザーの作業ツリー」と自己判定して checkout をスキップする。散文の「self-review からは PR 番号が渡らないためスキップ可」という許可形だけでは、PR 番号が紛れる経路が 1 つでもあればユーザーの作業ツリーを silent に detach しうる
- **`git fetch` と `git checkout` の失敗を切り分け**（両プロンプトテンプレート）。`A && B || C` の結合では fetch 失敗でも checkout 失敗でも同じメッセージが出て、agent が誤った原因を報告していた
- **`gh pr checkout`（親 worktree・review Step 1）の失敗時に中止**するよう明記。子 agent は detach で正しい HEAD に入るため、続行するとメインコンテキストだけが base branch を読む非対称が生じる（規模判定・Phase 0・締めフローが全部 base 基準になる）
- **`HEAD_SHA` が空のまま agent を起動しない**よう明記（orchestration-guide `## 1`）。空を注入すると detach が成功していても全 agent が恒常的に「不一致」warning を出して confidence を下げ、`git rev-parse` 自体が失敗する環境では空同士が一致して checkout をスキップしたうえ「一致」と判定する
- `grep ... && ...` 形のマーカー記録・掃除を `{ ...; } || true` で包み、正常系（explorer 未起動・`t2` 欠測）でブロックが exit 1 を返して「失敗」と誤読されるのを防いだ
- triage-guide `## 5.1` の worked example を `2〜5` → `2〜6` に修正し、上限の算式（表の各行の最大値の総和）を明記。括弧内に 6 本を列挙しながら上限を 5 と書いていた
- `orchestration-guide` `## 14` の見出し・導入文と INDEX.md の説明を「3 分割」から実体に合わせて更新

## [2.42.0] - 2026-08-03

### Changed
- **投稿コメントの署名を `— Created by Claude` に変更**（reply-tone-guide `## 0.1`。GitHub issue #97 提案 1）。旧署名「— Claude Code によるレビュー」は、このガイドが扱う文面の主対象が**レビューではなくレビューへの返答**（著者として対応・釈明・据置を返す文面）であるため実態と食い違っていた（実例: 著者としてレビューコメント 11 件に返答した際、全件で「対応しました」の末尾に「レビュー」が付いた）:
  - **voice を問わず 1 本**（レビュアー発信の 2.6 / 2.7 も含む）。voice で分ける案も検討したが、レビュアー発信でも「レビューによる」と名乗る必要はなく、voice の情報はメタ行（0.5）が既に運んでいるため、分岐を増やさず中立な 1 本に寄せた
  - **リポジトリ規約が署名文言を定めている場合はそちらを優先**する旨を明記（`CONTRIBUTING.md` が特定の文言を要求するケースとの衝突を解消）。根拠にできるのは Step 2 のコンテキスト収集で**実際に読んだ**規約ファイルに限る（PR テンプレートは収集対象外である点も明記）
  - 2.1〜2.7 のテンプレート全件と 5 章の例外に署名を明示（一部にしか無いと生成時に落ちるため。簡潔さが正の 5 章ほど落ちやすい）
- **署名 literal の複製点を 1 つ減らした**（closing-flow-guide `## 3`）。SKILL.md が締めフローの正本として指す `closing-flow-guide.md` にも署名文言が literal で書かれており、**reply-tone-guide だけ更新して旧署名 4 箇所・旧締め文言 1 箇所・旧チェックリスト文言 2 箇所が取り残された**（セルフレビューで 3 体が独立に検出）。few-shot 例が旧文言で揃っていると規則文より強く効くため、この状態では変更が実運用でほぼ効かない:
  - closing-flow-guide の出力例 3 件の署名と 2.1 例の締め（**新ルールで「避ける」に指定した文言そのものだった**）を更新
  - 規則本文からは literal を除去し「reply-tone-guide `0.1` の正本に従う」の参照に変更。0.6 チェックリストの項目複写も「0.6 を読む」に置換（複写がある限り片方だけ更新される事故が再発する）
- **「いかがでしょうか」系の許可範囲を番号列挙から原理に変更**（reply-tone-guide `## 1.1` / `## 1.2`）。旧文は 2.4 / 2.5 に限定していたが、**2.6 の部分対応**（残存指摘があり対応要否の判断が要る＝メタ行に「マージブロッカー: はい」が入りうる）を取りこぼしており、規則とテンプレート（2.6）が矛盾していた。判定基準を「**相手の応答がなければ次に進めない場合**」に置き換え、番号は例示に降格
- 2.2（部分対応）の締めを明示し、`## 3` の必須要素に 0.6 と同じ適用除外（2.7 承認・5 章は締めの一文を持たない構成が正）を追記
- **締めの既定形を「応答不要な形」に変えた**（reply-tone-guide `## 1.1` / `## 1.2` / `## 2.1` / `## 2.3`。issue #97 提案 2）。従来は判断委譲として「ご確認いただけると助かります」「いかがでしょうか」を既定にしていたが、**対応が完了している報告にこれを付けるとレビューの往復が 1 回増える**（レビュアーは必要なら再度コメントする）:
  - 既定形を **「認識に誤りがあればご指摘ください。」** に統一（誤りがなければ相手は何もしなくてよく、誤りがあれば指摘できる＝判断委譲の意図を保ったままラウンドトリップを増やさない）
  - **「いかがでしょうか」系は相手の判断が実際に必要な場面（2.4 意図確認 / 2.5 反証・両論提示）に限定**。2.3 で判断を委ねたくなったらそれは据置報告ではなく両論提示なので 2.5 を使う、という切り分けも明記
  - 0.6 チェックリストと `## 3` の生成手順（必須要素）にも反映

## [2.41.0] - 2026-08-03

壁時計時間の主因が「体数（breadth）」ではなく「**1 体あたりの探索量・直列 wave 数・メインコンテキストの思考量**」にあると特定し、そちらを削る版。v2.39.0 / v2.40.0 の体数縮小はトークンコストには効いたが、並列発行が効いている限り fleet 区間の実時間は wave 内最長の 1 体で決まるため壁時計には構造的に効かなかった（実測: 3 体・210 分のサンプル）。

### Changed
- **reviewer 共通指示の契約を圧縮し、1 体あたりの探索予算を明示**（reviewer-prompts.md `## 1`）。指示に忠実な世代のモデルでは、指摘 1 件あたりに課した 10 個超の契約をすべて律儀に実行するため、思考時間とツールループが「契約数 × 指摘数」で膨らんでいた:
  - **評価原則 1 を「PASS が証明されるまで FAIL」→「未確認は SKIP と書く」に改訂**。旧文は「問題なし」に証拠を要求することで探索を無限定に延長させていた。求めているのは「未確認を PASS と偽らないこと」であって「PASS を証明しきること」ではない
  - **探索予算を新設**: diff 外の追加 Read は 10 ファイルまで / 1 つの主張の裏取りは 1 往復まで（届かなければ confidence を下げるか `unmet_information` へ）/ 予算を使い切ったらその時点で確定する。**予算は探索にかけ、報告にはかけない**（指摘の件数・severity に上限は設けない。発見段階の自己間引きは recall を落とすため従来どおり禁止）
  - invariant 検算・claim grounding を**手順（やり方の記述）から出力要件（根拠欄が埋まらなければ confidence を下げる）へ格下げ**。`[unverified:]` タグ等の機構は据え置き
  - 「静的検査優先の自己問い」を指摘ごとの自問プロセスから、該当時のみ 1 行併記する出力規約へ縮小
- **冷や読み skeptic を reviewer wave に相乗り発火**（triage-guide `## 8.5` / orchestration-guide `## 9`）。skeptic は findings 非注入が設計の核で reviewer 出力に一切依存しないにもかかわらず、Phase 5.8/4.8 に直列配置されていたため、依存関係が無いのに opus 1 体分の実時間を積み増していた。surface 判定（正規表現 + PR 自己申告）を Phase 0 に前倒しし（review Step 3.4 / self-review Step 2.4）、ゲート通過時は reviewer 一括発行に含める。結果の統合・dedup は従来位置のまま。**fallback**: reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になった場合のみ従来どおり直列で単独起動する
- **反証レイヤーをバッチ化し effort を `max` → `high` に引き下げ**（triage-guide `## 9` / orchestration-guide `## 5`・`## 10`）。反証は既定パスで走り体数が指摘数に比例する**唯一の変動費**で、既定パスのコストの主要項だった:
  - **1 体あたり最大 5 件**のバッチ（上限 3 体 = 15 件）。反証が要求する独立性は「指摘を出した reviewer と別コンテキスト」であって「指摘同士が別コンテキスト」ではない。同一 diff の読み直しを N 体で重複させる意味がないため束ねる
  - effort 引き下げの根拠は、誤判定コストの非対称性を **verdict の扱い側**で既に吸収していること（BLOCKER / CRITICAL は refuted でも消さず係争注記＝ scoring-guide の不変条件）。扱い側で保険が効いている層に effort でも保険をかけるのは二重。**体数が 1 体固定の meta-reviewer / 冷や読み skeptic は `max` 据え置き**
  - バッチ内の相互汚染（1 件の verdict を別件の根拠にする）を reviewer-prompts.md `## 7` の鉄則で禁止。全 finding_id に verdict を返させ、欠落は verdict なし扱いで突合する
  - 対象が 15 件を超えた場合は severity → confidence 順で上位 15 件のみ反証し、溢れた件数をレポートに明示する（silent に落とさない）

### Added
- **所要時間を 3 分割して計測**（orchestration-guide `## 14`。payload に `duration_triage_min` / `duration_fleet_min` / `duration_closing_min` を追加）。`duration_min` 単独では agent 実行時間・メインコンテキストの思考時間・人間の応答待ちが 1 個の数字に潰れ、どの改善が効いたか判定できなかった（210 分のサンプルが 1 件あるだけで内訳不明だった）:
  - `TS_FILE` に区間マーカー（`t0` 開始 / `t1` reviewer 一括発行の直前 / `t2` 初回レポート出力の直後）を追記し、publish 時に awk で 4 値を算出する。欠測はすべて `-1`（0 と区別する）
  - `duration_triage_min` = メインコンテキストの思考時間の代理指標 / `duration_fleet_min` = agent wave の実時間 / `duration_closing_min` = 大半が人間の応答待ち（**効果測定に使わない**）
  - `duration_min`（全体）は後方互換のため意味を変えない。3 区間の和は全体と一致しないことがある（マーカー欠測時）ため一致を仮定しない
  - **`duration_triage_min` の存在が v2.41.0 以降の publish マーカー**（日付では切らない＝配布ラグに耐える。`agents` フィールドと同じ流儀）
- `agents.verify_findings`（反証の**対象指摘数**）を payload に追加。バッチ化で `agents.verify`（体数）と件数が分離したため別フィールドにする

### Fixed
- **`severity-inflated` verdict で高 severity 指摘が silent に消える穴を塞いだ**（scoring-guide）。旧規約は「全 severity で 1 段階下げる」だったため、**BLOCKER 60-79 → CRITICAL（要 80）/ CRITICAL 80-94 → MAJOR（要 95）** が報告マトリクスを割って消え、係争注記も残らなかった。`refuted` 経路しか塞いでいない不変条件を「反証 effort を下げてよい唯一の根拠」に昇格させていたため、この修正なしでは effort 引き下げの前提が成立しない。高 severity は**降格後にマトリクスを割る場合は severity 据え置き + 反証メモ**に変更
- **`duration_triage_min` に explorer wave が混入していた**。`t1` を reviewer 発行直前に固定していたため、explorer（最大 4〜6 体）の実時間が「メインコンテキストの思考時間の代理指標」に計上され、explorer を配置したレビューで「思考量が主因」という誤診に誘導していた。`t1` を**最初の agent 一括発行の直前**（explorer があればその直前）へ移し、`grep` ガードで二重記録を防ぐ。**agent wave はすべて fleet 側**に入る
- **self-review の `duration_closing_min` が構造上 ≒0 になる問題**。self-review は publish（Step 6.4）が Step 7 の修正方針確認より前にあるため t2→t3 に人間待ちが入らない。0 を publish すると「人間待ちが無かった」と誤読されるため **`-1`（測定不能）** を入れるよう変更し、`duration_min`（全体）の意味が publisher 間で非対称であることを両 SKILL と orchestration-guide に明記
- **review Step 3.4 の skeptic 相乗りゲートが `--emergency` / `skip-mode` を取りこぼしていた**。相乗りで起動が前倒しされる以上、Phase 5.8 に到達してからスキップ判定しても手遅れ（緊急モードで `effort: max` の skeptic が余計に走る）。条件の個別列挙をやめ Phase 5.8 の定義への単一参照に変更
- 反証バッチの切り方を「同一ファイルを寄せる」から**「同一ファイル・同一 reviewer 由来は散らす」に反転**。バッチ化で失うのは reviewer からの独立性ではなく**反証者側の誤読の独立性**で、1 体の誤読が同一ファイルの指摘を束で `refuted` にしうる（MAJOR は −40 で実質消える）
- 探索予算の**適用範囲を reviewer / specialist に限定**（独立検証レイヤーは対象外）。打ち切り時の痕跡を選択式から **AND**（confidence を下げる場合も `unmet_information` に `予算切れ:` を必ず記録）に変更し、探索予算経由の recall 低下が事後に検出できるようにした。low / medium では Round 2 が走らず回収経路が無いことも明記
- triage-guide `## 7` のロールバック条件が `duration_min`（全体）で所要時間を見ていたため、締めフローの人間待ちに支配されて体数調整の効果を検出できなかった。**jq スニペット本体を `duration_fleet_min` に修正**（散文での置換指示をやめた）。あわせて「体数は壁時計に効かない（実測）」という断定を、**「効いた証拠が現時点で無い（旧サンプルは内訳不明で判定不能）」**に緩めた（同じサンプルを一方で使用不能・他方で結論の根拠にしていた循環の解消）。「時間が長いから体数を減らす」判断を混ぜない規範は維持
- 反証の 2 縮小（バッチ化 + effort 引き下げ）に**ロールバック条件を追加**（`adversarial_verify` の `uncertain` 比率と MAJOR/MINOR の `refuted` 比率を版マーカーで層別して監視）
- `adversarial_verify` に **`severity_inflated`** を追加（4 つ目の verdict が集計から漏れていた）。`agents.verify_findings` の定義を「ゲート対象数」から**「実際に verdict が返った件数」**に明確化し、レポートの反証行の書式を orchestration-guide `## 10` に一本化。`agents.verify` は v2.41.0 前後で意味が変わるため層別が必要な旨を明記
- orchestration-guide `## 9` 手順 2 に**「相乗りで発火済みなら実行しない」ガード**を追加（skeptic の二重起動と `recall_skeptic.fired` の計測汚染を防ぐ）
- 反証 effort 引き下げ後も「補償層はいずれも `max` 据え置き」という旧前提が同一セクションに残り、新表と矛盾していたのを解消。triage-guide から orchestration-guide への effort 方針の参照（存在しない `## 7` 引用）も修正

## [2.40.0] - 2026-07-31

### Fixed
- **`review:completed` が worktree ごと消えて review 経路の計測が 1 件も残っていなかった問題を修正**（GitHub issue #96 B）。`event_bus_publish` は `CLAUDE_PROJECT_DIR` 未設定時に cwd 相対で書くため、review では Step 0 の `EnterWorktree` 後に publish → 締めフロー 5 の `ExitWorktree(remove)` で worktree ごと消えていた（self-review も作業用 worktree 内から実行された場合は Step 8 teardown で同型の消失）。publish 先をメインリポジトリのルートに固定する:
  - 導出は `git rev-parse --path-format=absolute --git-common-dir` の親。**worktree 内の `--show-toplevel` は worktree 自身を返すため使えない**（`--git-common-dir` は linked worktree 内でも main の `.git` を返す）
  - publish 呼び出しに `CLAUDE_PROJECT_DIR="$MAIN_ROOT"` を前置して環境値より導出値を優先する
  - `duration_min` の開始時刻ファイル（`TS_FILE`）のパス導出も `pwd` 基準から同じ `MAIN_ROOT` 基準へ変更（worktree 進入前後で `pwd` が変わり欠測になるのを防ぐ）。publish 後に `rm -f` で掃除し、中断したレビューの残骸が次回を汚さないようにする
  - `GCD` が空（git 2.31 未満 / 非 git）のときだけ `pwd` へフォールバックする。無条件に `cd "$GCD/.."` と書くと `/` に cd して `/.claude/events.jsonl` へ書きに行くため、この分岐は必須。導出式と落とし穴の正本は orchestration-guide `## 13`
  - **影響**: v2.39.0 で追加した計測フィールドは review 経路では 1 件も蓄積されていなかった。v2.39.0 の high 既定縮小の効果測定は本修正以降のサンプルで行う（triage-guide `## 7` のロールバック条件に注記）

### Changed
- **体数上限を「effort 上限 × 規模キャップ」の 2 系統 min に変更**（GitHub issue #96 A）。従来は effort 上限しか効かず、9 ファイル `+116 -22`（うち本番コード 3 ファイル `+22 -13`、残りはテスト 5 + doc 1）の PR に xhigh で 17 体が起動しレポートまで 95 分・締めまで 130 分かかっていた。旧 `## 6` の規模別構成は「Phase 0 が明確な判断を下せない場合」限定のフォールバックだったため、diff シグナルが読めると規模が上限に一切効かなかった:
  - **規模キャップ**（triage-guide `## 6.2`）: small = explorer 0 / reviewer 3 / specialist 1、medium = 2 / 5 / 2、large = キャップなし。最小保証の 2 体はキャップより優先。収まらない観点は `missing_coverage` に「規模キャップ: <帯>」として記録（脱落を silent にしない）
  - **帯は core で判定する**（`## 6.1`）: lock / 生成物 / vendor を除外し、さらにテスト・doc を除いた本番コードで数える。テスト・doc は観点の起動根拠にはなるが体数を押し上げる根拠にはしない。判定用の `git diff --numstat` + フィルタを両 SKILL に同梱
  - **削るのは breadth だけ**（`## 6.3`）: reviewer 個々の effort・meta-reviewer（5.6）・冷や読み skeptic（5.8）・反証レイヤー（5.9）は帯に関わらず effort 指定どおり動かす。規模キャップが effort 上限を下回った帯では Round 2 を effort に関わらず 1 段圧縮経路にする。「effort は 1 体あたりの深さの指定であって並べる体数の指定ではない」を設計原則として明記
  - 旧 `## 6` のフォールバック構成は `## 6.4` に温存（キャップではなく初期値としての役割は変わらない）

### Added
- **`review:completed` payload に `size_tier` を追加**（`small` / `medium` / `large`）。規模キャップの効果測定と `duration_min` の層別に使う。所要時間は規模と体数の両方に効かれるため、帯を混ぜた中央値ではキャップの効果と PR 規模の分布変化を分離できない（triage-guide `## 7` のロールバック jq に層別の注記を追加）
- レポート冒頭に **`size:` と `実効上限` 行**を追加（review / self-review 共通）。effort 上限と規模キャップのどちらが効いたかを人間が事後に検証できるようにする

## [2.39.0] - 2026-07-30

### Changed
- **high 既定のレビュー構成を縮小し、直列 wave を圧縮**（レビュー時間・トークン削減。品質側の補償層＝反証 / skeptic / 最小保証 / specialist トリガー感度は据え置き、xhigh/max のフル構成は現行維持で深さは明示 escalation に残す）
  - **effort 適応上限の正本を triage-guide `## 7` に集約**: high は explorer 4 / reviewer 6 / specialist 3、xhigh・max は従来どおり 6 / 10 / 6。上限超過の観点は近接観点バンドル（1 体 3 観点まで。bug-detection / security / spec-compliance / claude-md-compliance は単独維持）で可能な限り吸収し、容量（単独 4 + バンドル枠 = high 最大 10 観点）を超えた分は missing_coverage として欠損観点セクションに明示する。バンドル時の出力規約（focus キーは原観点・観点ごと独立列挙・自己フィルタ禁止）を reviewer-prompts `## 3` 冒頭に規定
  - **冗長ペアを xhigh/max 専用化**: high 以下はペア条件成立時も 1 体とし Angle A/B を両方内挿（reviewer 1 体あたりの固定注入コンテキスト＝diff + PR コンテキスト + AGENTS.md の複製数が減る）。反証 confirmed による補償は報告マトリクス通過見込み帯に限られ、**閾値直下の指摘をペアの +15 が押し上げていた効果は補償されない**（この帯の recall 低下は縮小のコストとして許容し severity 別件数で監視。「ペア合意 +10」「片方のみ -5」は angle 内挿 1 体に適用しないことを scoring-guide に注記）
  - **specialist の束ね起動**: high 以下は複数 red-flag ヒット時に 1〜2 体へテンプレート連結注入（guardrail-bypass のみ単独維持）。トリガー感度（検出正規表現）は不変
  - **Phase 5.5/4.5 を high で 1 段圧縮**: 追加 explorer を廃し、再起動 reviewer（最大 3 体）が unmet ターゲットを自力探索してから confidence を再評価（sonnet 経由の要約受け渡しロスも解消）。xhigh/max は現行 2 段を維持
  - **観点カバレッジ検算を Phase 0 直後へ前倒し**（orchestration-guide `## 8` を 8a 起動前検算 / 8b 事後突合に分割）: 漏れ focus は本隊 wave に合流し、旧 5.7/4.7 の事後補完起動（直列 wave 1 本）を廃止。事後は logging のみの突合に（issue #69 の常時検査の意図は 8a で維持）。`default-mode` 以外（emergency / doc-review / dba / supply-chain / skip）では検算による構成追加を行わず missing_coverage 記録のみ（モード構成の優先を維持）。旧 5.7 の「失敗 reviewer の補完起動」は wave 削減とのトレードオフで廃止（8b に明記。失敗 focus は欠損観点として必ず可視化）

### Added
- **`review:completed` payload に計測フィールドを追加**: `effort`（実行時 effort での層別用）/ `duration_min`（Step 1 で開始時刻を TMPDIR 配下のファイルに記録し publish 時に算出。シェル変数受け渡しは Bash 呼び出し間で消えて epoch/60 のゴミ値になるため禁止と明記。欠測は -1）/ `agents`（explorer / reviewer / specialist / round2 / verify の実起動体数）。縮小のロールバック判断は `agents` フィールド存在を版マーカーに、xhigh/max 明示実行を対照群として縮小後サンプル内で比較する（旧 payload は effort 層別不能のため基準に使わない。判定 jq を triage-guide `## 7` に同梱）

## [2.38.2] - 2026-07-29

### Changed
- **review SKILL.md の締めフロー 1〜3 を `references/closing-flow-guide.md` に分割**（skill-size warning 対応: 本文 506 行 → 377 行）。精査（1）は指摘ありのときのみ実行、1・2 は `--emergency` でスキップ、ドラフト生成（3）は Approve 系でも到達するが AskUserQuestion で opt-out できる末端フローであり、progressive disclosure の押し出し対象（docs/skill-writing.md の branch 判定）。SKILL.md 側には実行条件・実行順・「残存」確定集合の定義を残し、AskUserQuestion 文言・3 分類基準・パターン×voice 表・writing-polish 推敲手順を reference 側へ移した。挙動の変更なし。reply-tone-guide の writing-polish 正本参照も追随

## [2.38.1] - 2026-07-29

### Fixed
- **並列起動の実現手段を明文化**（GitHub issue #95）。「並列起動する」という指示に対し実現手段（**同一アシスタントメッセージ内に対象フェーズの全 Agent call を並べて一括発行する**）が未記述で、orchestration-guide `## 0` の同期起動ルール（`run_in_background: false`）を素直に読むと 1 体ずつの逐次実行が仕様準拠に見えていた（実測: 12 体レビューが相内最長 20.9 min で済むところ逐次合計 72.9 min、約 3.5 倍）。`## 0` に「並列発行の明示」段落を追加し、取りこぼし防止（`run_in_background: false`）と並列性（同一メッセージ一括発行）が直交する独立の要件であることを明記。review / self-review 両 SKILL の explorer / reviewer 起動 bullet と guide `## 6`（追加 explorer）/ `## 10`（反証）の起動手順にも一括発行の 1 行を追加。単体起動フェーズ（meta-reviewer / 冷や読み skeptic = issue 記載の `## 9`）は適用対象がないため対象外と明記

## [2.38.0] - 2026-07-28

### Added
- **worktree teardown 連携を追加**（worktree 削除の独立した 2 トリガー点のうち「レビュー完了後」側。Issue 完了後側は issue-workflow:issue-maintain 1.3.0 が担う）
  - self-review Step 8: 非 embed・worktree 内・worktree-setup マーカー（`envs/.backend.env.worktree`）あり・clean tree・dev-workflow 有効（enabled-only 判定）の全条件成立時、修正方針フロー完了後に AskUserQuestion（残す / 削除する）で確認し、削除選択時は `dev-workflow:worktree-teardown` を Skill 起動する。allowed-tools に Skill を追加（command 側も同期）。embed 契約（Step 1）にも Step 8 skip を明記
  - review 締めフロー 6: ExitWorktree 後に PR ブランチへ紐づく開発用 worktree を「ブランチ一致 + `.claude/worktrees/` 除外 + worktree-setup マーカー」の 3 条件で検出し、`/worktree-teardown` の実行を案内する（ブランチ一致だけではレビュー用一時 worktree を誤検出するため。teardown は worktree 内からしか実行できないため自動起動せず案内のみ・非ブロッキング）
  - `_requirements` / check-deps.sh に dev-workflow（optional plugin）を追加

## [2.37.5] - 2026-07-28

### Changed
- **reviewer fan-out の effort を実行時 `${CLAUDE_EFFORT}` 連動に変更**（review / self-review 共通）。従来の固定 `xhigh` から、既定パス（low/medium/high）は `high`、明示 escalation（xhigh/max）時のみ `xhigh` に。reviewer は全レビューで必ず走る最大コスト項のため最大のコストレバー（max→xhigh に続く 2 段目）。根拠は Opus 5 のレビュー系低 effort 耐性 + 反証/skeptic/meta の補償層（これらの `max` は据え置き）。Round 2 再起動・カバレッジ補完起動は「初回 reviewer と同 effort」に統一。効果は review:completed メトリクスで監視し悪化時は差し戻す

## [2.37.4] - 2026-07-28

### Changed
- orchestration-guide のオーケストレーター effort 説明を Opus 5 基準に更新（既定 `high` は Opus 4.8 と同値のため運用は不変。ドキュメント上の世代表記のみ）

## [2.37.3] - 2026-07-23

### Changed
- Issue ファイル必読フローの併用プラグイン参照を linear-workflow / indie-workflow から issue-workflow に更新（統合プラグインへの移行。dir スキャン（.claude/indie・.claude/linear）はデータ dir 温存により無改修）

## [2.37.2] - 2026-07-22

### Fixed
- **triage-guide.md の Phase 参照 typo を修正**（skeptic の effort ゲート説明が「既存 5.6/5.8 と対称」となっていたが 5.8 は skeptic 自身。SKILL.md と同じ「5.6/5.9」に統一）
- **緊急モードのスキップ対象列挙を 5.7〜5.9 追加後の実態に更新**（triage-guide と SKILL.md 本文が「Phase 5.5 / 5.6」のみ列挙していたが、5.7 カバレッジ self-check / 5.8 冷や読み skeptic / 5.9 反証レイヤーも各スキップ条件で --emergency を含む）
- **最小保証の reviewer 名に focus 語彙の対応を併記**（reviewer-bugs = bug-detection / reviewer-claude-md = claude-md-compliance。findings JSON の focus 語彙との二重語彙による混乱を防止）
- **self-review レポート例の MAJOR 指摘の連番重複を修正**（CRITICAL 例と同じ「3.」だったのを「4.」に。連番は findings JSON の id と 1:1 契約のため例の誤りが伝播しやすい）
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [2.37.1] - 2026-07-22

### Fixed
- **`scoring-guide.md` の surface-aware 閾値の根拠 ADR 参照が廃版を指していたのを修正**。`ADR-20260703155637` は同日に `ADR-20260703204045`（Enforcement 訂正版）へ supersede されており `status: superseded` だが、現行仕様書が旧 ID を引用したままだった。参照先を accepted 側の `20260703204045` に更新した（CHANGELOG 内の過去エントリは当時の記録として旧 ID のまま残す）
  - supersede 時に**被参照側の更新が漏れる**構造的な穴の実例。adr-keeper の supersede 機械化は「新規作成 + 旧 ADR の 4 フィールド更新」までで、外部からの被参照を追跡していない

## [2.37.0] - 2026-07-17

### Added
- **投稿コメントドラフトに重大度・確信度・マージブロッカー可否のメタ行を必須化**（GitHub issue #88）。レポート本体には `[confidence][severity]` が載るが投稿コメントには引き継がれず、著者が対応の優先度を判断する材料が届いていなかった。reply-tone-guide `0.5` を新設し、締めフロー 3 の生成手順と出力例にも反映:
  - 書式は本文冒頭に 1 行（`**重大度: CRITICAL / 確信度: 90 / マージブロッカー: はい**`）。値はレポートの確定値（精査で降格していれば降格後）を引き継ぐ
  - マージブロッカー可否は severity から**決定的に導く**（BLOCKER / CRITICAL → はい、MAJOR / MINOR → いいえ）。scoring-guide「レビュー結論（総合判定）」と同じ導出で、文面ごとに判断しない
  - **適用範囲は「レビュアーとして自分の指摘を著者に伝える文面」に限る**。判定はパターン番号ではなく **voice（文面の声）** で行い、voice は指摘の出所で決める（こちらのレポート由来＝レビュアー発信 / 他者の review comment への返答＝著者発信）。同じ 2.5 でも `[re-flag]` 経由はレビュアー発信・本来の用法は著者発信に分かれるため、パターン番号だけでは決まらない。締めフロー 3 のパターン選択表に voice 列を追加して対で決めさせる
  - 対象外は著者発信の文面（相手の指摘を自分がスコアリングして返す形になり `0.2` の敬意と衝突する）/ 承認コメント（Approve 確定でブロッカーが存在しない）/ 5 章の例外 / 2.6 の全面解決の確認文（残存指摘がなく埋める確定値が存在しない）
  - confidence 80 未満・反証メモ付きの指摘は未確定である旨を 1 文添える（数値だけ出して断定で押し切らない）
- **著者への配慮をドラフト提示前のチェックリストとして明示**（issue #88）。方針は `0.2` / `1.1` / `1.3` に既出だったが生成時に一貫適用されていなかったため、reply-tone-guide `0.6` に自己点検項目（謝辞 / 敬称 / 判断委譲の余地 / 既存対応への言及 / 人でなくコードへの指摘 / 良い点 1 文 / 署名）として列挙し、1 つでも欠けたら直してから提示することを締めフロー 3 に規定した
  - **適用範囲は 0.5 と同じ**（承認コメント・5 章の例外は署名のみ必須）。0 章は「1〜5 章より優先する」ため範囲を書かないと、5 章の「緊急性の高い指摘への返信は感謝表現を最小化」「typo 返信は 1 文で十分」という特則を 0.6 の謝辞・判断委譲の必須化が無効化してしまう

### Changed
- **ドラフト提示前に `writing-polish` を通すことを必須化**（issue #88）。締めフロー 3 に推敲規定がなく冗長な初稿がそのまま提示され、ユーザーが都度短縮を指示していた。pr-creator と同方式の dormant 連携（`--embed --tone review`）で soft 委譲し、未インストール時のみ skip して従来どおり提示する（プラグイン独立性・後方互換 100%）。推敲結果がメタ行・署名・謝辞・敬称・判断委譲を落としていたら破棄して元案を使う
  - `_requirements` に `writing-polish`（`required: false`）を追加、review skill / command の allowed-tools に `Skill` を追加

## [2.36.1] - 2026-07-16

### Fixed
- **fanout した agent の結果取りこぼしを修正**。CC 2.1.198 で Agent tool の既定が background 実行に変わり、`run_in_background` 未指定の explorer / reviewer / meta-reviewer / skeptic / 反証エージェントがすべて background で飛んでいた。オーケストレーターは「完了を待つ」つもりでも同期的には待てず、完了前に次フェーズへ進んで agent の出力を取りこぼしていた（「反応が返ってこない agent」問題。結果自体は tool result として後から返るが、消費するフェーズが先に走ってしまう順序の問題）。orchestration-guide `## 0` に「全 agent 起動で `run_in_background: false` を必ず明示する」横断ルールを追加し、review / self-review の explorer・reviewer 起動手順にも明記した

## [2.36.0] - 2026-07-15

### Changed
- **reviewer 本体の effort を `max` → `xhigh` に変更**（review / self-review）。**reviewer は全レビューで必ず走り体数も最大（典型 2〜10 体）＝総コストの最大項**なのに対し、v2.34.0 が既定 opt-in 化した meta-reviewer / 冷や読み skeptic は内容条件を満たしたときだけ 1 体走る層で、その内容条件（BLOCKER/CRITICAL 検出）の充足率も 20 件中 6 件＝30% にとどまる `[unverified: gist 集約のうち adversarial_verify 規約追加(2026-06-24)以降の 20 件。events.jsonl は gitignored のため repo からは検証不能]`。つまり v2.34.0 の変更は**削減量が小さいまま、high-risk 変更での見落とし側の保険だけを落としていた**。`max` からの 1 段引き下げは全レビューに効く**最大の**コストレバーになる:
  - adaptive deepening の reviewer 再起動（orchestration-guide `## 6`）と観点カバレッジ・セルフチェックの追加 reviewer（`## 8`）も初回 reviewer と同 effort に揃えて `xhigh` に変更（非対称な深さの指摘が同じ confidence 軸で合流するのを避けるため）
  - **独立検証レイヤー（meta-reviewer / 冷や読み skeptic / 反証エージェント）は `max` 据え置き**。据え置きの根拠は体数ではなく**誤判定コストの非対称性**（反証の誤却下は指摘を落とし＝消えるのは MAJOR/MINOR のみ、BLOCKER/CRITICAL は係争注記が機械保証される／skeptic の見落としは recall 補強そのものを無効化する）。**下げるのは全レビューで必ず走る常時レイヤー、据え置くのは誤判定コストが非対称な検証レイヤー**という切り分け
  - CLAUDE.md モデルルーティング規約「判断・検証は `opus` + effort 引き上げ」は維持（`xhigh` は既定 `high` からの引き上げであり、規約は `max` を要求していない）。偽陽性は従来どおり confidence ≥80 フィルタと反証レイヤーで刈り取る
  - **次点の変動費は反証（既定 high でも起動し、体数は指摘ごと 1 体＝指摘数に比例）と specialist（reviewer 枠とは別枠で上限 6 体）**。コストが再び問題化したらこの 2 つが次の検討対象（reviewer の effort が「唯一の」レバーではない）
  - **既知の制約**: `review:completed` payload に `effort` フィールドが無いため、この変更が指摘の質に与えた影響は**事後に相関できない**。効果測定を要する場合は payload への `effort` / `agent_count` 追加が前提になる

## [2.35.1] - 2026-07-15

### Fixed
- **`recall_skeptic.findings_added` の帰属が失われ、skeptic の価値率が系統的に 0 へ潰れていた問題を修正**。実測（gist 集約 69 件）で `fired=true` 4 件すべてが `findings_added=0` だったが、これは「skeptic に価値がない」ことの証拠になっていなかった。由来の帰属チェーンが 3 箇所で切れており、**「価値ゼロ」と「帰属の喪失」を区別できない**状態だった:
  - **レポート書式に由来タグの居場所が無かった**。`reviewer-prompts.md` は skeptic に「各指摘の冒頭に `[recall-skeptic]` タグを付ける（由来を追跡するため）」と指示していたのに、Step 7 / Step 6 のレポート書式のタグ枠は `[confidence][severity][カテゴリ]` の 3 つだけで、由来タグはレポートを書いた時点で消えていた。書式に由来タグを明記し、実例も追加してレポート契約の一部と位置づけた
  - **dedup でタグごと消えうる**。`orchestration-guide` の「重複は dedup（同一ファイル ±5 行 + 類似内容）」はどちらが生き残るか未規定で、reviewer 指摘と重なると skeptic の寄与が不可視になった。**残す側へタグを引き継ぐ**ことを規定
  - **publish が計測点から遠すぎた**。Phase 5.8 → Step 6 scoring（計測点）→ 締めフロー 4 publish と 200 行以上離れ、間に精査・解説・ドラフト生成という指摘リストを書き換える対話ステップが 3 つ挟まる。かつ payload は LLM が手で JSON を組む。両フィールドを「**Step 7 で最初に出力したレポート本文のタグ付き指摘を数えて求める**」と再定義し、記憶からの再構成をやめた。計測点（報告マトリクス通過時点＝精査の前＝ Step 7 の初回レポート。精査が再出力する調整後レポートではない）を明示し、精査で取り下げた分を減算しないことを規定。「動的ラウンド」行の `実行（N 件追加）` の N と `findings_added` は同値であり、本文確定後に数えてヘッダへ反映する（二重管理にしない）ことも明記
- **由来タグを 2 種に分離し、価値率の分子から重複を排除**。上記の「dedup 時にタグを残す」規定だけでは、**過少計上（0 潰れ）を過大計上へ反転させるだけ**だった。dedup 規定は重複を残す理由を「fleet 共通盲点でなかったことの記録」と自ら述べており、**重複＝ skeptic が recall を足していない事例**である。それを `findings_added`（＝ triage-guide が読む「価値率」の分子）に混ぜると、skeptic は generalist 一頭で reviewer 最大 10 体と同じ diff を読むため**重複が常態**となり、価値率が 100% に張り付いて「`findings_added=0` が続くなら縮小」の分岐が原理的に発火しなくなる:
  - `[recall-skeptic]` = **skeptic 単独由来**（dedup で重複しなかった＝実際に破った盲点）→ `findings_added` に計上。**価値率の分子はこれのみ**
  - `[recall-skeptic:dup]` = **重複 survivor**（reviewer も到達していた）→ 新設の `findings_overlap` に計上。独立到達の記録として残すが**価値率には算入しない**
- **`attribution_schema` 版マーカーを `recall_skeptic` payload に追加**（常に `2`）。当初は「修正日より前のデータは使えない」と日付で切る注記にしていたが、**日付では原理的に切れない**。マーケットプレイス配布のため未更新マシンは修正日以降も schema 1 の payload を publish し続けるからで、`plugin-manager` による一括更新が前提＝**ラグは常態**（本リポジトリ自身、修正当日まで pre-commit hook が未設定のマシンが存在した）。publish 側が自己申告する版マーカーだけが配布ラグに耐えるため、この方式に変更。`triage-guide` の価値率 jq に `attribution_schema >= 2` フィルタを**式として埋め込み**（散文の警告だけでは、コピペ実行時に汚染データで判断してしまうため）
- review / self-review 対称に反映。self-review 側の publish は Step 6.4（Step 6.5 は構造化 JSON / Step 7 は修正方針確認）

## [2.35.0] - 2026-07-14

### Added
- **返答ドラフト生成の前に「PR・指摘の解説」ステップを追加**（review SKILL.md の締めフロー）。従来は精査の直後にいきなり返答ドラフトの要否を訊いていたため、指摘の背景を理解しないまま返答方針を決める必要があった。締めフローを `1. 指摘の精査 → 2. 解説 → 3. 返答ドラフト → 4. Event Bus publish → 5. ExitWorktree` に組み替え、解説を判断材料の供給ステップとして挟む（既存の 2〜4 を 1 つずつ繰り下げ。全ステップ番号を記すのは、次回の挿入時に繰り下げ漏れを CHANGELOG 側から検知できるようにするため）:
  - **解説対象は AskUserQuestion の複数選択（`解説不要` / `PR について` / `指摘について`）**。`指摘について` は残存・降格した指摘が 1 件以上あるときのみ提示するため、指摘 0 件でも 2 択が成立し PR 単体の解説は可能。`解説不要`（既定）が選ばれたら他と同時選択でも優先して 3 へ抜ける
  - **選択肢は指摘件数に比例させない（最大 3 択）**。AskUserQuestion の選択肢上限（4 個）と衝突するため「指摘ごとに選択肢を並べる」形は採らず、`指摘について` 選択時に指摘番号を free-text 入力（例: `1,3,5` / `all`）させる 2 段構えにした。既存の返答ドラフト「個別選択」と同じ入力パターンで揃えている。`all` = 残存・降格した指摘の全件（取り下げ済みは含まない）、範囲外番号・空入力は対象なしとして扱う
  - **指摘の解説は `なぜ問題か` / `直し方` / `取り下げ材料` の 3 点**。取り下げ材料は「取り下げを推す」のではなく、著者が指摘を覆すための材料を対称に置く目的（Step 1 の必要性ゲートと同じく人間が覆せる形を保つ）。PR の解説は `変更の全体像` / `設計意図` / `変更の流れ` / `影響範囲`
  - **解説はチャット出力のみで投稿コメントではない**ため `reply-tone-guide.md` は適用しない（Claude 署名・敬語テンプレは不要）。Step 1 と同じ断定抑止ルール（`file:line` 典拠 / 外部状態は「要確認」/ `[unverified:]` の引き継ぎ）は継承する
  - 解説の結果ユーザーが取り下げ・降格を望んだ場合は Step 1 の 3 分類に差し戻して調整後レポートを再出力し、以降の返答ドラフト・publish は再確定値を使う
  - `--emergency` 時はスキップ（Step 1 と同じ扱い）。self-review は締めが「修正方針確認」で返答ドラフトを持たないため対象外（review / self-review の意図的な非対称）

### Fixed
- **返答ドラフトの AskUserQuestion が `Approve with nits` の全ケースで選択肢 5 個になり仕様上限（4 個）を超えていた問題を修正**。`scoring-guide.md` の総合判定表は `Approve with nits` を「BLOCKER/CRITICAL なし・MAJOR が 1 件以上」または「MINOR のみ残存」と定義しており、**`Approve with nits` ≡ 残存指摘 ≥ 1** が成り立つ。このため `承認コメント`（Approve 系のみ提示）と `重要指摘のみ` / `全件` / `個別選択`（残存指摘ありのみ提示）の条件が常に同時成立し、`不要` と合わせて 5 個が提示条件を満たしていた。エッジケースではなく最頻の承認経路の全ケースで発生し、LLM は仕様エラーを避けるためどれか 1 つを独断で落とすしかなく、どれが消えるかは非決定的だった（silent degradation）:
  - 修正は `重要指摘のみ` の提示条件を「残存指摘があるとき」→「**BLOCKER / CRITICAL が 1 件以上あるとき**」に締める 1 行。`Approve with nits` は定義上 BLOCKER/CRITICAL を持たないため、この選択肢はそもそも空振りする死に選択肢だった。上限超過と死に選択肢が同時に解消し、`承認コメント` を Approve with nits に残せる（`承認コメント` 側を落とす案より選択肢の意味が保たれる）
  - 再発防止として options 直下に**選択肢数の不変条件テーブル**（Approve=2 / Approve with nits=4 / Needs work=4）を明記。提示条件を変更する際の再検算を強制する
  - self-review 側の AskUserQuestion は 3 択固定・無条件のため同種の超過なし（確認済み）
- **Step 1 で「そのまま」（精査なし）を選んだ場合の「残存」の定義を明示**。後続ステップ（解説の `指摘について` 提示条件・返答ドラフトの実行条件）が「残存・降格した指摘」を参照するが、精査を行わなかった経路ではこの語が未定義で、指摘が N 件あっても条件を満たさない読みが成立しえた。「精査を行わなかった場合は報告マトリクス通過後の全指摘を残存とみなす」と定義を追記した

## [2.34.0] - 2026-07-14

### Changed
- **既定 effort を `xhigh` → `high` に変更**（review / self-review 両 SKILL.md）。frontmatter の `effort: xhigh` は Opus 4.7 向け orchestrator 調整（`097e4f7`）の名残で、その後に追加された effort ゲート付きレイヤー（meta-reviewer / 冷や読み skeptic）の設計上の既定「`high`」と矛盾し、本来 opt-in のはずの高コスト独立レイヤーが常時起動していた。triage-guide が一貫して呼ぶ「high（既定）」に実装を揃える:
  - **meta-reviewer（Phase 4.6/5.6）と冷や読み skeptic（Phase 4.8/5.8）が既定で不発**になる（従来通り xhigh/max を明示すれば escalation として起動）。反証レイヤー・adaptive deepening（high で起動）と reviewer 本体（`effort:max`）は不変のため、偽陽性フィルタ・レビュー品質のコアは落ちない。落ちるのは high-risk 変更での見落とし側の保険のみ
  - 副次効果として issue #77 の計測前提（skeptic の `skip_reason="effort"` 蓄積による high 昇格判断）が復活する。実効既定が xhigh だと skeptic は毎回起動し `skip_reason="effort"` が永久に貯まらなかった
- **モデルルーティングから `fable` を全廃し `opus` に統一**（プロジェクト方針）。meta-reviewer を `model: fable` → `model: opus` に変更（review / self-review / orchestration-guide）。design doc `20260703` が「独立検証は強モデル＝opus」と結論済みの方針とも整合。plugin description の `meta-reviewer(fable)` 表記も更新

## [2.33.2] - 2026-07-08

### Fixed
- **冷や読み skeptic の silent skip を修正**（issue #85）。high-risk surface HIT なのに Phase 4.8/5.8 が effort/config/scope スキップで畳まれた際、その事実が Step 6/7 の human レポートにも `missing_coverage` にも出ず観測不能だった問題を修正:
  - Step 6/7 レポートの「動的ラウンド」行に **冷や読み skeptic の起動有無を明示**（実行＝追加件数 / 未起動＝skip 理由 / 非該当＝surface なし）。従来は Meta-reviewer と反証のみで skeptic 項目が欠落していた
  - Phase 4.8/5.8 のスキップ条件に該当しても、surface 判定（正規表現・grep で安価）は Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** し、surface=true なら未起動事実と skip_reason を human レポートに必ず出す契約を追加（`--embed` / event 発火の有無に依存しない observability）
  - orchestration-guide `## 9` / triage-guide `## 8.5` の「失敗時のみレポート」文言を「失敗・スキップのいずれでも」に拡張
  - これにより #77（high 昇格判断）の `recall_skeptic.skip_reason` 計測が headless 通常実行でも成立する

## [2.33.1] - 2026-07-07

### Changed
- **review / self-review SKILL.md を references/ に分割**（review 531→418 行 / self-review 477→397 行）。実行フェーズの共通詳細（PR 番号注入・Issue ファイル必読フロー・AGENTS.md 階層動的選択・部分失敗耐性・auto-retry・動的ラウンド 5.5〜5.9 / 4.5〜4.9 の実行手順・Vault 照合・訂正の伝播前ガード）を新設の `references/orchestration-guide.md` に正本として集約し、SKILL.md 本文は高レベルワークフロー（Phase 一覧・スキップ条件・スコアリング規則・レポート契約・AskUserQuestion 仕様）に絞った。挙動の変更なし

## [2.33.0] - 2026-07-05

### Added
- **`review:completed` payload に `recall_skeptic` 実行記録を追加**（`surface` / `fired` / `skip_reason` / `findings_added`）。冷や読み skeptic（Phase 5.8/4.8）を effort=high へ昇格するかの計測基盤:
  - skeptic が effort / userConfig でスキップされた場合も**正規表現部分の surface 判定だけは必ず実施して記録**する（「surface=true なのに effort ゲートで走らなかった頻度」が昇格判断の核心メトリクスのため）
  - `triage-guide.md` §8.5 に「high 昇格の判断基準」を追記（events.jsonl の jq 集計 2 本 + 判断の目安）
  - review / self-review 両 publisher で同一フィールド名（subscriber が publisher を区別せず集計可能）。新規フィールド追加のみで旧 subscriber への影響なし

## [2.32.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier1（冷や読み skeptic + surface-aware 閾値・GitHub issue #75）**。段階投入（Tier3→2→1）の最終段。トリアージが絞り込んだ結果 fleet 全員が同じ盲点（層跨ぎ値フロー）を共有して high-risk バグを見落とす false negative を、recall 側の独立レイヤーで救済する:
  - **冷や読み skeptic ラウンドを新設**（review=Phase 5.8 / self-review=Phase 4.8）。high-risk surface を含む変更に限り、findings も reviewer 推論も渡さない独立 skeptic を `model: opus` で 1 体起動し、fleet 共通盲点を冷や読みで破る。反証レイヤー（false-positive 潰し）の鏡像＝ false-negative hunter。テンプレートに敵対的入力逆算の核を内挿し独立性に「破り方」を持たせる（`reviewer-prompts.md` `## 8`、`triage-guide.md` `## 8.5`）
  - **surface-aware 報告閾値を追加**（`scoring-guide.md`、ADR-20260703155637）。high-risk surface（DB 書込 / 金銭・数量 / 認可、または PR 自己申告 D1-High）に限り CRITICAL 80→70 / MAJOR 95→85 に緩め、recall を非対称補正。precision の本丸（≤40 好みクランプ・高 severity 非削除・specialist 反証除外）は不変で、緩和は適用順序 手順 7 の一点のみ
  - **surface 判定ロジック**: performance 観点の INSERT/UPDATE 正規表現を surface 判定に転用 + ORM 書込 API + D1-High 検出（`reviewer-prompts.md` `## 2.5`）。ORM 抽象越えの偽陰性は reviewer の `[surface:high-risk]` フラグを保険に OR 判定
  - **F4 吸収整合**: surface-aware で新規報告化する CRITICAL 70-79 / MAJOR 85-94 帯を high でも反証レイヤーの対象に含める例外ゲートを追加（`triage-guide.md` `## 9`）
  - **反証レイヤーを Phase 5.9 / 4.9 にリナンバリング**（skeptic を 5.8/4.8 に挿入したため）。userConfig に `enable_recall_skeptic`（既定 true、effort xhigh/max で動作）を追加。skeptic 失敗時は `missing_coverage` に記録し起動条件を満たしたのに未実行だった事実をレポートに必ず出す
- 設計は design doc `.claude/designs/20260703-code-review-recall-high-risk-surface.md`（Tier1 完了で phase: current）

## [2.31.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier2（explorer/reviewer プロンプト・GitHub issue #75）**。段階投入の 2 段目として層跨ぎバグの捕捉手段を追加:
  - **value-flow-trace explorer focus を新設**（`explorer-prompts.md`）。1 つの値が schema→domain→DB / FE→BE をどう通るかを入口から末端まで辿り、前提がズレる境界を判定せず可視化して bug reviewer に集約注入する。`triage-guide.md` の explorer 判定（層跨ぎの値フロー）に dispatch 導線を追加
  - **explorer 出力に「要注意シグナル」欄を追加**（`explorer-prompts.md`）。判定禁止のまま suspicion を落とさず reviewer に運ぶ
  - **bug-detection に「敵対的入力逆算」を追加**（`reviewer-prompts.md`）。受理入力の端点（`''` / 0 / null / 最大長 / 部分入力）を末端の DB 制約まで前進させて素通り経路を探す（#1 直撃）
  - **claude-md-compliance に「帰結接続の義務化」を追加**（`reviewer-prompts.md`）。パターンの有無でなく共有機構が実際に呼ばれ帰結を生むかまで見る（#7 直撃）
- Tier1（冷や読み skeptic + surface-aware 閾値）は未実装。設計は `.claude/designs/20260703-code-review-recall-high-risk-surface.md`

## [2.30.0] - 2026-07-03

### Added
- **high-risk コードでの recall 補強 Tier3（プロンプトのみ・GitHub issue #75）**。実レビューで xhigh フルパイプラインが high-risk な DB 書込 PR の実バグ（空文字が numeric 列へ INSERT → 500）を見落とした事例を受け、段階投入（Tier3→2→1）の先行分として reviewer プロンプトを補強:
  - **CRITICAL 以上に「発現シナリオ / テスト未検知理由」を必須化**（`reviewer-prompts.md` 出力フォーマット）。端点の具体値と既存テストが捕まえられない理由を書けなければ severity 過大評価を疑う自己較正欄
  - **spec-compliance に「契約の前提を呼び出し側で実地検証せよ」を昇格**（既存の「整合性の罠」注記を focus プロンプトへ）。宣言と整合の確認を正しさの確認の代用にしない
  - **comment-accuracy に「メッセージ時制 × 制御フロー照合」を追加**。ログ/エラーメッセージの主張する事後状態とコードが実際に到達する状態のズレを検出
- 設計は design doc `.claude/designs/20260703-code-review-recall-high-risk-surface.md`（Tier1/2 は未実装。ADR-20260703155637 で surface-aware 報告閾値の判断を記録）

## [2.29.1] - 2026-07-02

### Fixed
- **allowed-tools に `Agent` 未宣言を修正**。review / self-review の各 SKILL.md とペアの command（`commands/review.md` / `commands/self-review.md`）は explorer / reviewer / meta-reviewer / 反証エージェントを並列起動するのが核心なのに `Agent` を allowed-tools に宣言していなかった。4 ファイルすべてに追加
- **`/review` command の argument-hint に `--emergency` を追記**。skill 側では受け付けているが command のヒントに載っていなかった
- **AGENTS.md 階層選択の実装不一致を修正**。review Step 4.9 / self-review Step 3.9 の「Glob で発見」記述を、直後のコード例（`git diff | dirname` の bash ループ）に合わせて「Bash で探索」に修正

### Changed
- **plugin.json の description を圧縮**。変更履歴が約 3000 字堆積していたのを、機能を端的に説明する数行に圧縮（履歴は CHANGELOG が正本）

### Added
- **コスト×精度 10 原則の採用/不採用を SKILL.md に明記**。review / self-review に採用原則（1 ファネル / 2 二軸スコア / 3 段階予算 / 4 モデルルーティング / 7 敵対的独立検証）と捨てた判断（5/6/8）の宣言行を追加（ルート CLAUDE.md 指針に準拠）
- **kvault を `_requirements` に宣言**。self-review Step 1.5 の Vault 照合で使う任意の外部 CLI を `cli_tool` / `required: false` として宣言し、`hooks/scripts/check-deps.sh` に `check_cli "kvault"` を追加（未導入時は skip、後方互換）

## [2.29.0] - 2026-06-26

### Added
- **指摘の精査ゲート（必要性の第3軸 / review skill Step 7）**。返答ドラフト生成の選択肢を出す前に、報告された指摘を「**本当に著者の対応に値するか（必要性 = signal/noise）**」の観点で精査するか AskUserQuestion で確認するステップを追加。Step 6（severity×confidence の機械フィルタ）・Phase 5.8 反証レイヤー（正しさ＝偽陽性の独立検証）と直交する第3軸を人間に委ねる
  - **既存機構との非重複**: 反証は「正しいか」、精査は「正しいとして対応に値するか」。settled な設計判断の蒸し返しや既存コード由来の nit は反証では refuted にならない（事実は正しい）が必要性軸では取り下がる。≤40 好みクランプを擦り抜けた残滓を人間ゲートが補う
  - **再評価ロジック**: 取り下げ（純粋な好み / settled な蒸し返し / 実害極小 MINOR nit / 既存コード由来）/ 降格（severity 過大 → 1 段階下げ + Optional:・Nit:）/ 残存（実害・規約違反の根拠あり）の 3 分類。**BLOCKER / CRITICAL は降格はあっても取り下げない**（反証レイヤーの「高 severity 非削除」不変条件を継承）。取り下げは理由明示で人間が覆せる reversible 設計
  - **下流反映**: 精査後（post）の確定件数を返答ドラフト対象・総合判定再導出・`review:completed` publish に反映。指摘 0 件・`--emergency` 時はスキップ
- **投稿コメントのトーン徹底（reply-tone-guide.md `## 0 必須ルール`）**。返答コメント・承認メッセージの両方に適用する最上位ルールを新設
  - **Claude の署名**: Claude 作成のコメント（ドラフト含む）末尾に署名 1 行 `— Claude Code によるレビュー` を付す（**絵文字なし** — 既存の emoji 禁止規約に準拠。標準の `🤖 Generated with Claude Code` は使わない）。人間が大幅に書き換えた場合は不要
  - **PR 作成者・他レビュアーへの敬意**: 敬称を添える / 他レビュアーの指摘を否定せず議論を立てる方向で書く
  - **簡潔さ**: 要点を先頭に・1 コメント 1 論点・専門用語を噛み砕く
  - **良い点を 1 文で称賛**: 中身のない称賛は禁止、file:line に紐づけ、SKILL.md「良かった点」と同基準
- **承認メッセージパターン（reply-tone-guide.md `### 2.7`）**。総合判定が Approve / Approve with nits のとき投稿する承認コメント（簡潔な承認 + 良い点 1 文 + nits は任意と添える + 署名）のテンプレを新設。Needs work では出さない。返答ドラフト step を「投稿コメントドラフト」に拡張し、Approve 系では指摘 0 件でも承認コメントを生成可能に

## [2.28.0] - 2026-06-26

### Added
- **doc-substance を 2 軸に拡張（文書としての成立性 = B 軸を追加）**。従来の doc-substance は `comment-accuracy` の「主張⇔コード一致」を doc 本文へ一般化したもので、**「書かれた主張が正しいか」（A 軸）だけ**を見ており、「**書かれるべきことが書かれ、読み手が目的を達成できる構造か**」という文書としての構造的妥当性が素通りしていた（完全性・doc 種別適合・読み手前提・WHY 根拠・ナビゲーションがどのツールにも担当されない gap だった）。Diátaxis / Write the Docs の functional quality 観点を取り込み、prose polish（語句・トーン）では捕まらない構造欠陥を検出可能にした
  - **B 軸の検出対象（reviewer-prompts.md `doc-substance`）**: 完全性（missing content: 手順の前提・成功条件・失敗時挙動の欠落、パラメータ網羅、**コードに追加された新 API / フラグに対応する doc の不在**、ユースケース例の不在）/ doc 種別適合（how-to に理論混入・reference に手順混入・design doc に代替案比較なし・ADR に context/帰結なし）/ 読み手前提・順序（prerequisite 後出し・対象読者/前提環境の不明示）/ 判断根拠 WHY（規約・閾値・制約に「なぜ」がない）/ ナビゲーション（新規ページ・ADR の index/上位リンクからの孤立）。A 軸にも「例の整合（コード例 vs 現行 API、code:line）」を追加
  - **2 軸で裏取りの相手が違う**: A 軸は code:line（内部矛盾は doc:line ×2）、**B 軸は doc:line（欠落・誤配置・孤立の発生箇所）＋ 破られた期待（doc 種別の契約 / その doc が宣言する対象読者・スコープ / 手順が参照する未記載の前提）**。B 軸はコード照合不要（triage-guide.md grounding 節に分岐を追加。新 API 追加に対する doc 不在の完全性指摘のみ A 軸同様コードを読む）
  - **scoring の好みクランプを 2 軸対応に修正（最重要 / load-bearing）**: 従来は「code:line または doc:line ×2 で裏取りできない doc 指摘は表現の好みとみなし ≤40 クランプ」だったため、**code:line で裏取りできない B 軸（完全性・doc 種別適合等）が生まれた瞬間に好み扱いで除外されていた**。`scoring-guide.md` の doc-substance クランプ条項を 2 軸に分け、**B 軸は doc:line + 破られた期待を示せていればクランプ対象外**に。逆に「語句を最小差分で言い換えれば済む」だけの指摘（writing-polish の領分）は B 軸を騙ってもクランプ
  - **prose polish との分界**: 判別線は「**語句を最小差分で言い換えれば済むか**」。済む → writing-polish、内容の追加・再配置・根拠補完・例修正が要る → doc-substance（triage-guide.md 境界記述に明示）。decided 系 doc（`.claude/adr/**` / `.claude/designs/**`）は既存の design-review soft 委譲が優先
  - **反証レイヤー統合**: `reviewer-prompts.md` `## 7` の doc-substance 反証ブロックに **B 軸の読み替え**を追加（pre-validated=欠落情報が別箇所に実在 / intended=明示的スコープ外 / misread=doc 種別の誤判定 / pre-existing=base から既存。ただし新 API 追加に対する doc 不在は diff が生んだ乖離なので pre-existing としない）。review skill は effort=xhigh 既定のため B 軸 MAJOR も Phase 5.8 で独立検証され、クランプ（一次抑制）＋ 反証（偽陽性摘出）の二段構えになる
  - **severity 目安**: B 軸の致命欠落（手順書の必須 prerequisite/step 欠落で読者が実行不能・コード例が現行 API と食い違い動かない）= CRITICAL、doc 種別不適合・WHY 欠如・完全性の重大欠落・孤立 doc = MAJOR

## [2.27.0] - 2026-06-24

### Added
- **doc-substance 観点（ドキュメント内容妥当性）**。review 系スキルが docs を含む PR を整合性（リンク / 構造 / コード片安全性）だけでレビューし、書かれた内容の本質的な妥当性を見ていなかった問題に対応。`comment-accuracy` の「主張⇔コード一致」を doc ファイル本文へ一般化した観点を追加（`reviewer-prompts.md` `## 3` Focus テンプレート）
  - **検出対象**: ground-truth 正確性（主張がコードと食い違う、code:line 裏取り）/ 規範の正しさ（規約 doc の指示で動かない・既存ルールと矛盾）/ 論理的健全性（自己矛盾）/ 有用性（曖昧・hand-wavy）/ 意味の陳腐化（リンク切れでなく内容の陳腐化）。表現・語句・トーンは対象外（writing-polish の責務）
  - **重要度ゲート（triage-guide.md）**: 起動を「変更ファイル数比率」でなく **doc の意味的重要度**で判定。`doc-review-mode`（`*.md` ≥ 80%）に doc-substance を追加し整合性のみから「整合性 + 内容妥当性」へ。混在 PR（`*.md` < 80%）は観点判定表に `doc-substance` 行を追加（高価値 doc パス〔CLAUDE.md / AGENTS.md / CONTRIBUTING / README / .claude/adr / .claude/designs〕の prose 変更 OR 実質 prose ≥10 行）。ファイル数では小さいが意味的に重要な doc（ADR 1 件 / CLAUDE.md 1 行）の取りこぼしを防ぐ
  - **effort 別起動制御**: low=skip / medium=高価値 doc のみ / high+=全面（反証レイヤーが効かない effort では起動自体を抑制し偽陽性の素通りを防ぐ）
  - **grounding**: 専用 explorer を必須化せず既存の条件付き起動に乗せ、読み取り対象を **diff 変更 doc が参照するコード ∩ リポジトリ実在パス**に限定（信頼できない doc 本文に任意パスを選ばせない）
  - **scoring（scoring-guide.md）**: 裏取り報酬は新規 +15 を作らず既存「explorer 裏付け +10」に統合。根拠なしの論理 / 有用性指摘は既存 ≤40 クランプで除外（doc-substance の MAJOR は既定 effort で反証対象外のためクランプが主たる抑制機構）。裏取りできた内容誤りは CRITICAL 昇格、ただし `git blame` で doc 変更とコード変更の前後関係を検算しコードが doc より古い場合は昇格しない（doc 先取り・コード未追従での誤昇格と高 severity 非削除不変条件への直撃を防ぐ）
  - **反証レイヤー統合**: doc-substance の裏取り CRITICAL は既存 Phase 5.8/4.8 の反証対象に自動的に含まれる（specialist でないため）。反証軸に doc 向け読み替え（misread / pre-validated / intended / pre-existing は git blame でコードと doc のどちらが現在の正かを判定）を追加
  - **dormant 連携**: 決定系 doc（ADR / design doc）は `design-doc` 導入時のみ design-review の minimal / risk チェックリストを内挿（settings.json grep 判定、未導入時は内製代替、スキル間呼び出し非依存）。境界は doc-freshness（frontmatter / link）/ writing-polish（語句）/ doc-substance（本文の主張）で機械的に分離

## [2.26.0] - 2026-06-23

### Added
- **反証レイヤー（adversarial verification / Phase 5.8 / self-review Phase 4.8）**。reviewer が出した指摘を、それを形成していない独立エージェントが報告前に反証する工程を追加。観点カバレッジ self-check の後・スコアリングの前に挿入。meta-reviewer（見落とし＝false negative を足す係）の鏡像で、偽陽性（false positive）を独立に潰す。人間が「これ本当？」と詰めて取り下がる指摘を先回りして摘出する
  - **対象選定（triage-guide.md `## 9`）**: 「詰めると取り下がる」非対称ゾーン（BLOCKER 60-94 / CRITICAL 80-94）を high 既定で狙い撃ち、xhigh/max で報告ゾーン全体 + MAJOR に拡大。**security specialist 由来（injection / secret-handling / destructive-op / input-validation / guardrail-bypass）は全 effort で対象外**（誤反証で人間の警戒度を下げる代償が非対称）
  - **反証エージェント（reviewer-prompts.md `## 7`）**: reviewer の推論を渡さず（アンカリング防止）コードを独立に読み直す。両方向に file:line 証拠を要求し、「たぶん大丈夫 / おそらく問題」は uncertain 止まり。反証軸は独立性が効くもの（unreachable / pre-validated / misread / pre-existing / intended）に限定し、既存自己検算（invariant 検算 / `[unverified]` クランプ）と重複する軸は再利用。`pre-existing` / `intended` 鮮度は LLM 前に `git show <base>` / `git blame` で機械判定
  - **verdict→scoring 統合（scoring-guide.md `## 反証レイヤーの verdict 反映`）**: 適用順序の冒頭で機械適用。**高 severity（BLOCKER/CRITICAL）の `refuted` は confidence/severity を据え置き本文に `⚠️ 反証メモ:` を付すのみ＝報告から消さない**（false-negative の構造的防止をプロンプトでなく手順で保証）。MAJOR/MINOR の `refuted` のみ confidence −40 で取り下げ（理由をレポート付録に記録、人間が覆せる）。`confirmed` は既存「複数エージェント +15」の発火源として扱い二重計上を排他。`severity-inflated` は既存 severity 調整ルールに統合し二重降格しない
  - **計測**: `review:completed` payload に `adversarial_verify`（confirmed / refuted / uncertain / contested 件数）を review / self-review 両 publisher で追加。後から偽却下率を計測して verdict→delta を調整
  - **userConfig `enable_adversarial_verify`**（デフォルト true、effort high 以上で動作）。`enable_meta_reviewer` と同型運用で無効化可能
  - レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」サマリ行と「🔁 反証で取り下げた指摘」付録を追加。embed JSON は schema_version 据え置き（反証効果は severity/confidence に反映済み、係争指摘は `title`/`impact` に反証メモ）

## [2.25.1] - 2026-06-15

### Changed
- README の confidence 説明を severity × confidence 2 軸マトリクスに更新、主要引数（--emergency / base branch / --staged / --focus / --exclude / --embed）を記載、Version 行を撤去

## [2.25.0] - 2026-06-10

### Added
- **事実主張のツール接地（claim grounding）**（GitHub issue #71）。`reviewer-prompts.md` 共通指示に「事実主張のツール接地」を追加。指摘の load-bearing な事実主張を confidence 確定前に検証可能性で 3 分類（① repo 検証可 → `file:line` 引用必須 / ② 正本 doc 検証可 → spec・PR・Issue・ADR の典拠引用必須 / ③ repo 検証不能 = DB・本番状態・外部数値・運用設定 → 事実として断定禁止）。③ を根拠にする指摘は「要確認（典拠=X）」と明示し confidence ≤75 + `[unverified: ...]` タグを付け、単独根拠で severity を上げない。「内部的に一貫しているが実態と異なる」主張が整合性レビューを素通りする罠も明記
- **scoring の未検証クランプ**（GitHub issue #71）。`scoring-guide.md` に「上限クランプ: 未検証の外部状態主張」を追加。`[unverified: ...]` タグ付き指摘は confidence を `min(値, 75)` に機械クランプ（BLOCKER 級の疑いのみ報告マトリクスを通過、CRITICAL 以下の未検証断定は自動除外）。好みベースクランプ（min 40）と両該当時は低い方を採用。適用順序に未検証クランプのステップを挿入
- **findings 反映段の over-correction ガード**（GitHub issue #71）。`self-review` Step 7 に「訂正の伝播前ガード」を追加。findings をコード/文書本文に反映する前に load-bearing な事実主張を一次ソースで再確認（repo 確認可は Read/Grep で現物確認、repo 確認不能は「要確認」マーカー保持）、暫定入力（「〜かも」）を確定として複数箇所へ伝播しない、訂正は 1 箇所先行確認 → 確証後に展開、複数観点の独立一致は高信頼として扱う。`review` Step 7 の返答ドラフト生成にも未検証主張の断定抑止（`[unverified]` の不確実性を返答に引き継ぐ）を追記

## [2.24.0] - 2026-06-10

### Changed
- **meta-reviewer (Phase 5.6 / self-review Phase 4.6) を `model: opus` → `model: fable` に変更**。全 reviewer の指摘を統合して最終判断する単一インスタンスの判断スロットに、Opus 上位ティアの Fable 5（claude-fable-5）を割り当て、知能上限を最終判定に集中させる。入力は蒸留済み findings、出力は verdict のため Fable の出力単価 2 倍（$50/1M）はトークン量で bounded。並列起動する reviewer (opus) / explorer (sonnet) はコストがボリューム × 単価で効くため据え置き。`effort: max`（adaptive thinking 前提）は維持（Fable は `thinking:{type:"disabled"}` が 400 だが本スロットは該当しない）

## [2.23.0] - 2026-06-08

### Added
- **reviewer 非レビュー出力の検知 + auto-retry**（GitHub issue #69）。`review` Step 5 / `self-review` Step 4 で各 reviewer 出力を機械検証し、`### レビュー結果` 構造と（指摘ありの場合）`[confidence][severity]` タグを欠く非レビュー出力（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了）を検出したら同一プロンプトで 1 回 auto-retry。retry も非レビュー出力なら `missing_coverage` に記録して欠損観点扱いにし、フィルタ素通りを防ぐ
- **観点カバレッジ・セルフチェックの常時化**（GitHub issue #69）。`review` Step 5.7 / `self-review` Step 4.7 を新設。meta-reviewer の厳しい起動条件（effort=xhigh/max かつ高 severity あり）に依存せず、`triage-guide.md` の観点判定表を実際の diff シグナルに対してメインコンテキストで再評価し、「条件を満たすのに未起動の focus」を検出して `missing_coverage` に追記する（high effort 以上なら 1 体だけ追加起動可）。`--emergency` / `skip-mode` / `--focus`・`--exclude` 指定時はスキップ
- **`self-review` Step 1.5「Vault 照合」**（GitHub issue #68）。`kvault recall` / `/vault-recall` skill を検出（未導入なら no-op skip / 後方互換）、変更ファイルのパス・識別子・技術語で過去のレビュー指摘・落とし穴を retrieval し、`similarity` + gap で関連判断して各 reviewer に `## Vault prior findings` セクションとして注入する。`--embed` 呼び出し（feature-dev Phase 6 等）でも動作。feature-dev Phase 1.6 Vault Recall と同一 retrieval 基盤を呼ぶ対の改善

### Fixed
- **EnterWorktree 配下での `isolation:worktree` agent の二重 checkout 衝突**（GitHub issue #69）。`explorer-prompts.md` / `reviewer-prompts.md` の開始時セットアップを、`{{HEAD_REF}}` と現在 HEAD を比較して一致時は `gh pr checkout` をスキップする形に変更。親 review worktree が PR を checkout 済みのとき、子 worktree での再 checkout が "already checked out at <親worktree>" で失敗する問題を解消（fallback の `git log` 確認に頼らず衝突自体を回避）。`review` SKILL Step 4/5 のプレースホルダ注入に `{{HEAD_REF}}` を追加

### Changed
- **退行（regression）指摘の invariant 検算**（GitHub issue #69）。`reviewer-prompts.md` 共通指示に「退行指摘の invariant 検算」を追加。「旧挙動が失われた → 退行」と判断する前に、その挙動が隣接コード経路（類似関数・兄弟ハンドラ）でも一貫強制される invariant か検算し、特定経路だけの偶発的副作用（incidental）なら confidence / severity を下げる。`scoring-guide.md` の severity 調整に incidental 退行の 1 段階降格ルールを追加。単一経路の旧挙動を invariant とみなして severity を過大評価する誤判定を抑制

## [2.22.1] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の `~/.claude/mcp.json` / `.mcp.json` の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。github を user スコープ追加済み環境で ERROR になる誤検知を解消

## [2.22.0] - 2026-06-04

### Added
- **`modern-web-checklist.md` 同梱 reference**（Chrome [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance) を [Baseline](https://web.dev/baseline) ベースで照合可能にしたチェックリスト）。`ui-quality` Focus に「自前実装 → ネイティブ API 置き換え」（自前モーダル→`<dialog>`、自前ツールチップ→Popover API + Anchor Positioning、viewport メディアクエリ→Container queries 等）と **Baseline ゲート判定**（Limited availability 機能のフォールバックなし本番投入を MAJOR で検出 / widely available 化で不要になった polyfill 削除提案）を追加。ネイティブ API 化の任意改善は `Optional:` prefix・confidence ≤ 60 に抑え、好み抑制ルール（reviewer-prompts.md「好みではなく原則」+ scoring-guide の confidence クランプ）と整合させた。a11y / セマンティック HTML は既存 ui-quality 本体が担当し二重指摘しない棲み分けを明記

### Changed
- **`web-design-guidelines` 公式 skill 参照のローカル化**。`reviewer-prompts.md`（ui-quality Focus）と `triage-guide.md`（React/Next.js 判定）が参照していた `~/.agents/skills/web-design-guidelines/SKILL.md`（現環境に存在しない dangling 参照・WebFetch 前提）を、同梱の `${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md` に差し替え。外部 fetch 依存と参照切れを解消し、`${CLAUDE_PLUGIN_ROOT}` でポータブル化
- **`context7` の dangling skill 参照を MCP 参照に修正**。`reviewer-prompts.md`（外部ライブラリ最新仕様の確認）が参照していた `~/.agents/skills/context7/SKILL.md`（同じく現環境に存在しない dangling 参照）を、context7 MCP（`resolve-library-id` → `query-docs`）経由の記述に差し替え

## [2.21.0] - 2026-06-03

### Added
- **`--emergency` 緊急レビューモード**（Google eng-practices "Emergencies"）。`review` skill に `--emergency` 引数を追加し、本番ホットフィックス向けに reviewer-bugs + reviewer-security の最小 2 体のみで実行（explorer / 冗長ペア / Phase 5.5 / 5.6 をスキップ、specialist は red-flag 検出時のみ起動）。レポート冒頭に `⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること` バナーを必須化。`triage-guide.md` に緊急モード定義（緊急の定義 / 他モードより優先 / レビューは省略しない原則）を追記
- **`self-review` の修正指針「Fix the code, not the reviewer」**（eng-practices "Handling reviewer comments"）。Step 7 の修正フローに、「分かりにくい / 誤解を招く」系の指摘は説明コメントで取り繕わずコード・命名・型・構造そのものを直して解消する原則を追加（将来の読み手も同じ箇所でつまずくため）。feature-dev Phase 6 の自動 fix にも委譲経由で波及

## [2.20.0] - 2026-06-03

### Added
- **総合判定（レビュー結論）の導出**（Google eng-practices "The Standard of Code Review" の continuous improvement 原則）。`scoring-guide.md` に「レビュー結論（総合判定）」セクションを追加し、報告マトリクス通過後の残存指摘から `Approve` / `Approve with nits` / `Needs work` を決定的に導出する（BLOCKER/CRITICAL 残 → Needs work、MAJOR/MINOR のみ → Approve with nits、ゼロ → Approve）。`review` / `self-review` のレポート冒頭に `総合判定` 行を追加。「完璧でなくともコード健全性が向上すれば Approve」とし、nit の積み残しで承認を保留しない（LGTM with comments）
- **severity プレフィックス規約**（`Nit:` / `Optional:` / `FYI:`、eng-practices "How to write code review comments"）。`reviewer-prompts.md` の出力フォーマットに、必須指摘と任意改善を著者が一目で区別できる文面マーカーを定義。MINOR 非ブロッキング → `Nit:`、任意改善 → `Optional:`、focus 外の教育的共有 → `FYI:`（related-observations に最大 2 件）。BLOCKER/CRITICAL/MAJOR の必須指摘には付けない

### Changed
- **好みベース指摘の confidence 上限クランプ**（eng-practices "principles over personal preference"）。`reviewer-prompts.md` の評価原則を 5 → 6 原則に拡張し「好みではなく原則」を追加。`scoring-guide.md` の適用順序に、CLAUDE.md / style guide / 計測データ / file:line のいずれの根拠も伴わない個人的スタイル選好は confidence を `min(値, 40)` に制限するルールを追加。LLM レビューの偽陽性（根拠なき好み指摘）を半機械的に刈り取る

## [2.19.0] - 2026-06-02

### Added
- `self-review` に **`review:completed` Event Bus publish（Step 6.4）** を追加（Workflow 監査 2026-06-01 の rollout Step3-C 計測仕込み）。embed / 非 embed の両モードで `.claude/events.jsonl` に集計を fire-and-forget で追記し、review skill と同じ `review:completed` イベントで集計を揃える。LLM 駆動 fan-out の「観点取りこぼし」「severity / confidence のパース安定性」を後から定量化するための計測データ蓄積が目的
  - `SAFE_HOOK_NAME=code-review:self-review` で publisher を識別、`pr` は `"local"` 固定。payload 規約（`missing_coverage` / `result_grid`）は review skill と同一
  - 副作用のみで標準出力にレポート文字を足さないため、embed mode の出力フォーマット（Step 6.5 の findings JSON → marker の順序）に影響しない

## [2.18.0] - 2026-06-01

### Added
- **self-review `--embed` の構造化 findings JSON 出力（schema_version: 1）**。embed mode 時に Step 6 の markdown レポート直後へ、`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲んだ機械可読な findings ブロックを出力する（dual format）。呼び出し元（feature-dev Phase 6 等）が `severity` / `confidence` / `focus`（安定 focus キー）/ `file` / `line` / `suggested_fix` を決定的にパースでき、markdown の正規表現パース依存を解消する
  - Step 6.5 として SKILL.md にフィールド契約を明文化（findings は Step 6 報告と 1:1、`focus` は triage-guide の英語 focus キーを使用）
  - 後方互換: 非 embed 実行（`/self-review` 単独）では JSON ブロックを出力せず従来通り

## [2.17.1] - 2026-05-29

### Changed
- **剪定 (Opus 4.7→4.8)**: review / self-review SKILL.md の effort 設計意図にあった「Opus 4.7 のコーディング向け推奨設定」という stale な世代参照を更新。Opus 4.8 では `high` が既定 effort のため、オーケストレーターの `xhigh` を「demanding task 向けに一段引き上げた設定」と明記し直した。reviewer の `effort: max`（Confidence ≥80 フィルタで偽陽性を刈る意図的設計）は維持（cc-catch-up Phase P 剪定レビューで「文言更新のみ」を選択）

## [2.17.0] - 2026-05-29

### Added
- `self-review` skill に **`--embed` フラグ** を追加（GitHub issue #57）。他 plugin（feature-dev Phase 6 等）からプログラム的に呼び出される場合に、Step 7 の修正方針確認 AskUserQuestion を skip して findings をそのまま return するモード
  - `commands/self-review.md` の `argument-hint` と本文に `--embed` を反映
  - SKILL.md Step 1 の引数解説に embed mode の return 仕様（Step 6 レポート + 末尾 marker `[embed-mode: findings-only, no-prompt]`）を明文化
  - SKILL.md Step 7 冒頭に embed mode 分岐を追加（指定時は本ステップを skip）
  - 後方互換: `--embed` 未指定の `/self-review` 単独実行は従来通り Step 7 まで完走

### Notes
- 動機: feature-dev v2.0.0 (#52, commit 655987d) で Phase 6 が self-review 呼び出しに変わった際、self-review の Phase 7 AskUserQuestion がユーザー操作を 1 回追加してしまう UX 負債が残っていた。本変更で feature-dev / 将来の linear-workflow / indie-workflow 等が同じ汎用 IF で findings を集約できる

## [2.16.0] - 2026-05-28

### Fixed
- **worktree branch 継承バグ修正**（GitHub issue #56, Critical）。`isolation: "worktree"` で起動された子 worktree は親 branch を継承せず origin/default-branch から派生していたため、explorer / reviewer が古い main を見て深刻な偽陽性を量産していた（Vue プロジェクトで BLOCKER 3 件 + CRITICAL 1 件の偽陽性が観測済み）
  - `references/explorer-prompts.md` / `references/reviewer-prompts.md` の共通指示先頭に「開始時の必須セットアップ」セクションを追加。worktree 起動時は最初の Bash 呼び出しで `gh pr checkout {{PR_NUMBER}}` を実行し、`git rev-parse --abbrev-ref HEAD` で PR ブランチ名と一致することを確認する
  - `skills/review/SKILL.md` Step 4 / 5 / 5.5 / 5.6 で agent 起動箇所に PR_NUMBER と head ref の prompt 注入を必須化（`{{PR_NUMBER}}` プレースホルダを実数値に置換）
  - `skills/self-review/SKILL.md` は `isolation: "worktree"` を使わないため修正不要

### Added
- **PR 種別分岐ルール表**（GitHub issue #43, High）を `references/triage-guide.md` に追加。Stage 1 より先に `## 2.5 PR 種別分岐ルール` で doc-only / migration / lockfile / generated code 等の特殊 PR を判定し、即興構成での skill スキャフォールド無視を防ぐ
  - `doc-review-mode`: `*.md` 比率 ≥ 80% → リンク健全性・コード片安全性・構造整合性に絞った 1〜2 reviewer
  - `dba-mode`: SQL migration ファイル含む → migration reviewer + specialist-destructive-op
  - `supply-chain-mode`: lockfile 主体 → dependency reviewer 1 体に絞る
  - `skip-mode`: vendor / generated code 主体 → AskUserQuestion で確認後 spec-compliance のみ
  - `default-mode`: 上記いずれでもない場合のみ通常の Stage 1 / Stage 2 へ
- **Issue ファイル必読フロー**（GitHub issue #43, High）を `skills/review/SKILL.md` Step 1 に追加。PR head / base branch 名から `[A-Z]+-\d+` パターンで Issue ID を抽出し、`.claude/linear/` / `.claude/indie/` 配下の Issue ファイルを探索して spec-compliance reviewer の prompt に同梱する。親 Issue リンクは 1 段だけ追跡（深い再帰禁止）
- **適用モードのレポートヘッダ表示**（GitHub issue #43, Low）。レビュー結果冒頭に `[mode: doc-review, agents: [doc-reviewer]]` 形式の 1 行ヘッダを表示し、レビュー判断のコンテキストをユーザーに透明化

### Changed
- `skills/review/SKILL.md` Step 3 に Stage 0（PR 種別分岐の先行判定）を追加し、triage-guide.md `## 2.5` の参照を明示
- `plugin.json` の description を 2.16 機能反映に更新

### Notes
- issue #56 の 🟡 High 項目（既存バグ自動除外 / effort 動的調整）および 🟢 Medium 各種は本リリースのスコープ外（別 issue として残置）
- issue #43 の Medium / Low 項目のうち「出力テンプレート標準化」「gh コメント投稿フラグ」は scope creep のため別 issue として残置
- `plugin.json` の userConfig 追加（`force_checkout_pr_branch` 等）は今回スコープ外

## [2.15.0] - 2026-05-28

### Added
- `reviewer-prompts.md` の共通指示節に **評価 5 原則** を追加（GitHub issue #51）。PASS が証明されるまで FAIL / 自己交渉禁止 / 証拠ファースト / spec が真実 / 関心の分離。reviewer・specialist・meta-reviewer 全てに共通の判断基準として明文化
- `reviewer-prompts.md` に **静的検査優先の自己問い** を追加。指摘出力前に「linter / ast-grep / 型検査に落とせるか」を自問する原則を明記
- `triage-guide.md` Red-flag pattern table に **ガードレール骨抜き検出**（lint/hook/static check 設定の削除・無効化・severity 降格・適用範囲縮小・ブロック判定反転）を追加。BLOCKER 固定で `specialist-guardrail-bypass` を自動起動
- `reviewer-prompts.md` §5 Specialist テンプレートに **specialist-guardrail-bypass** を新規追加
- `review/SKILL.md` Step 4.9 と `self-review/SKILL.md` Step 3.9 に **AGENTS.md 階層動的選択** を追加。変更ファイルパスから対応する `{dir}/AGENTS.md` / `{dir}/CLAUDE.md` を遡って Glob で発見し、該当層だけを reviewer プロンプトに同梱（入力 token 30〜50% 削減）
- `review:completed` event payload に **`result_grid`** フィールドを追加（high/medium/low/skip/error の 5 値集計）。後段 hook / PR コメント自動投稿の dispatch ロジックが分岐爆発しない標準スキーマ

## [2.14.0] - 2026-05-26

### Added
- `skills/review/SKILL.md` のレポートに「良かった点」セクションを追加（Google Engineering Practices の looking-for「Good things」由来）。著者が意図的に良くした箇所を 0〜2 件、該当ファイル:行つきで具体的に挙げ、指摘偏重を避けてメンタリング効果を持たせる。中身のない称賛はノイズになるため禁止、特筆点がなければ省略。PR レビュー専用（self-review は品質ゲート用途のため対象外）

## [2.13.0] - 2026-05-25

### Added
- `self-review` skill に `--focus <観点>` / `--exclude <観点1,観点2>` 引数を追加（GitHub issue #40）。同一セッションで既に reviewer agent を走らせた後の再実行時に、既検証の観点を再報告しないようレビュー対象を絞り込み・除外できる
  - `--focus`: Phase 0 で該当観点の reviewer のみ構成（最小保証も focus に含まれない限り起動しない）
  - `--exclude`: 該当観点の reviewer を構成から外す
  - reviewer プロンプトに `review focus:` / `already verified (do not re-report):` を注入
- `commands/self-review.md` の `argument-hint` と本文に `--focus` / `--exclude` を反映

## [2.12.0] - 2026-05-19

### Added
- **Red-flag pattern による specialist 自動起動**（Idea 3-a）。triage-guide.md の `## 3 Red-flag pattern による specialist 自動起動` で diff の危険パターンを検出し、対応する specialist reviewer を Phase 0 で自動追加起動する
  - `specialist-injection`: `eval(` / `child_process` / `exec(` / `subprocess.run` / `shell=True` 等のコード/コマンドインジェクション
  - `specialist-destructive-op`: `fs.unlink` / `rm -rf` / `DROP TABLE` / `TRUNCATE` / WHERE 句なし DELETE/UPDATE 等の破壊的操作
  - `specialist-secret-handling`: `password =` / `BEGIN PRIVATE KEY` / `Bearer` / `console.log(.*token)` 等のシークレット漏洩
  - `specialist-input-validation`: `JSON.parse(req.*)` / `RegExp(user_input)` 等の信頼境界
  - specialist の指摘は大半が BLOCKER/CRITICAL になる前提で、2軸マトリクスにより低 confidence でも人間に届く設計
- **Phase 5.5 Adaptive deepening (追加 explorer ラウンド)**（Idea 1）。reviewer の `unmet_information` 申告をトリガーに、対応する re-explore explorer を 1 ラウンドだけ起動して該当 reviewer のみ再実行する
  - reviewer-prompts.md 共通指示に `## unmet_information` 出力フィールド仕様を追加。「BLOCKER 候補で context 不足」「呼び出し元全件確認が必要」等のケースのみ申告
  - explorer-prompts.md に `re-explore` フォーカステンプレートを追加。元 reviewer の why に直接回答する形式
  - 上限 3 体ずつ。失敗時は best-effort で続行
- **Phase 5.6 Meta-reviewer ラウンド**（Idea 1+3 統合）。BLOCKER または CRITICAL 検出時に、別 reviewer が「他の reviewer の見落とし観点」を探すメタレビューを 1 ラウンド実行
  - 観点の偏り検出、指摘の盲点、複合リスク、正常系の見落としを重点的に検証
  - 重複指摘禁止、追加指摘なしも健全
- **explorer 配置条件の緩和**（Idea 3-b）。共通モジュール（`utils/` / `shared/` / `lib/` / `common/` / `helpers/` / `core/`）の変更は **行数・関数数に関わらず必ず shared-module-impact explorer を 1 体起動**。小規模変更で依存元への波及を見落とすリスクを構造的に解消
- `plugin.json` の userConfig に `enable_adaptive_rounds` (boolean, default: true) と `enable_meta_reviewer` (boolean, default: true) を追加。トークンコスト・レイテンシを抑えたい場合は false に

### Changed
- `triage-guide.md` の `## 7 最小保証とフェーズ上限` に specialist 上限 6 体を追加（reviewer 枠 10 体とは別カウント）
- `triage-guide.md` に `## 8 動的ラウンド (Phase 5.5 / 5.6)` セクションを新設、effort 適応ルール表 (low/medium はスキップ、high は 5.5 のみ条件付き、xhigh/max は両方) を明文化
- `review` skill / `self-review` skill にレポート出力時の動的ラウンド可観測性を追加 (`Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由}`)
- skill description / `marketplace.json` の説明を 2.12 機能反映に更新

### Notes
- effort 適応により、デフォルト effort=high では Phase 5.5 (unmet 起動時のみ) のみ動作し、Phase 5.6 はスキップ。深掘りが必要な場合は effort=xhigh / max で実行
- 動的ラウンド全体のトークンコスト増分は「unmet 申告がない場合 0」「申告ありでも追加 explorer 最大 3 + 再 reviewer 最大 3」「meta-reviewer +1」のため、保守的設計
- 本リリースは Phase B (Idea 1 + Idea 3 統合) に該当。Phase A (2軸スコアリング) は v2.11.0

## [2.11.0] - 2026-05-19

### Added
- **2 軸スコアリング** (confidence × severity) を導入。`scoring-guide.md` を全面改訂し、severity 4 段階 (BLOCKER / CRITICAL / MAJOR / MINOR) と報告マトリクスを定義。「重大だが不確実」(race condition 疑い 等) と「軽微だが確実」(typo 等) を従来の単一軸 confidence では区別できなかった構造的ジレンマを解消
  - 報告マトリクス: BLOCKER は confidence ≥ 60 で報告、CRITICAL は ≥ 80、MAJOR / MINOR は ≥ 95
  - これにより「疑わしい重大問題は人間判断を促す」「ノイズ的 nitpick は自動除外される」の非対称運用が可能に
- `reviewer-prompts.md` の共通指示に severity 必須付与を追加、出力フォーマットに `[severity: XXX]` ラベルを追加。各 Focus テンプレート (bug-detection / security / migration / performance / api-design / cross-cutting 等) に severity 目安を追加
- `plugin.json` の userConfig に `review_severity_threshold` を追加 (デフォルト: `MAJOR`)。ユーザーが報告閾値を `BLOCKER` (厳しめ) / `MINOR` (緩め) に変更可能

### Changed
- `review` skill / `self-review` skill の Phase 6 / 5 のフィルタリングロジックを 2 軸マトリクスベースに変更
- `review` skill の Step 7 出力フォーマットを severity 別グルーピング (🚨 BLOCKER / ⚠️ CRITICAL / 📋 MAJOR) に変更
- `review:completed` event payload に `blocker_count` / `major_count` / `minor_count` を追加。`critical_count` は subscriber 互換のため維持
- `self-review` skill の修正方針 AskUserQuestion を「BLOCKER/CRITICAL のみ」に変更 (旧: `confidence >= 90 のみ`)。BLOCKER 指摘を残したままコミットしようとした場合は再確認
- `review` skill の返答ドラフト生成の「重要のみ」を severity ベース (BLOCKER または CRITICAL) に変更
- `review` / `self-review` skill の description を 2 軸スコアリング対応に更新

### Notes
- **後方互換性**: severity が付与されていない reviewer 出力は CRITICAL とみなして処理されるため、移行期間中も既存挙動が維持される (旧 confidence ≥ 80 と等価)
- userConfig の `review_confidence_threshold` は後方互換のため残置 (CRITICAL severity 以下のフィルタに使用)
- 本リリースは Phase A (スコア再定義) に該当。Phase B (Idea 1+3 統合: 動的ラウンド + 検出ミス対策) は別リリース予定

## [2.10.0] - 2026-05-19

### Added
- `references/reply-tone-guide.md` を新規追加 (#37 軽量版)。レビュー後の返答ドラフトのトーン・テンプレ・禁則・パターン別ガイド（完全対応/部分対応/据置/意図確認/反証/レビュアー再返信）を集約
- `review` skill の Step 7 にレポート出力後の **返答ドラフト生成** ステップを追加（AskUserQuestion で `不要 / 重要のみ / 全件 / 個別選択` を選択、reply-tone-guide.md に従いドラフトのみ生成、投稿は手動）
- `review` skill と `commands/review.md` の allowed-tools に `AskUserQuestion` を追加

### Notes
- Issue #37 の thread skill 構想（check / reply / status）からスコープを大幅に縮小。状態管理・GitHub 投稿自動化・未対応スレッド一覧は本リリースに含めず、将来 skill 化が必要になった時点で再検討する（退路確保）
- `self-review` skill は PR コメントの返答対象がないため変更なし

## [2.9.0] - 2026-05-18

### Added
- `review` skill の Step 7（レポート出力後）に `review:completed` イベント発行を追加 (#33)。payload は `{"pr":"<number>","critical_count":<n>,"warning_count":<n>,"missing_coverage":[...]}`
  - publisher は `safe-hook.sh` の `event_bus_publish` を `SAFE_HOOK_NAME="code-review:review"` 上書きで呼び出す形式（fire-and-forget、失敗してもレポートは成功扱い）
  - retrospective / instinct-memory 等の subscriber がレビュー傾向（critical 数推移・missing_coverage の偏り）を集計できるようにするための土台

## [2.8.1] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。code-review 自身は現時点で event を発行しないが、将来 `review:completed` イベント発行用の土台として整備

## [2.8.0] - 2026-05-15

### Added
- 公式 skill 連携を 2 系統追加。
  - `ui-quality` reviewer Focus を新設し、`web-design-guidelines` 公式 skill（`~/.agents/skills/web-design-guidelines/`）のチェックリストに準拠した WCAG 違反 / セマンティック HTML 違反 / フォーカス管理 / 状態フィードバック欠落の指摘を confidence ≥ 80 で報告
  - `triage-guide.md` に UI/フロントエンド観点判定ルールを追加（`.tsx`/`.jsx`/`.vue`/`.svelte`/`components/`/`pages/`/`app/` の変更、または diff の `aria-`/`role=`/`tabindex`/`<button`/`onClick`/`onKeyDown` を検出）
- reviewer 共通指示に外部ライブラリ最新仕様確認（公式 skill `context7` 経由）を opt-in で追加。モデル学習データ cutoff を越える破壊的変更による誤判定を防止し、裏付け不能な仕様ベース指摘は confidence ≤ 75 に下げて自動除外させる

## [2.7.0] - 2026-05-15

### Added
- review SKILL.md に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて explorer/reviewer の上限体数を自動調整（low/medium: 速度優先、high: 既定、xhigh/max: 深掘り）

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [2.6.2] - 2026-05-13

### Added
- `code-review/scripts/fetch-pr-context.sh` を追加。PR メタ・issue コメント・レビューサマリ・行単位 review コメント（返信チェーン込み）を一括取得し、SKILL.md Step 2.5 の構造化フォーマットで markdown 出力する

### Changed
- review SKILL.md Step 1 を更新: PR 会話コンテキスト取得を `fetch-pr-context.sh` の **必須実行** に変更。LLM が個別 `gh` コマンドで組み立てる方式を禁止し、PR コメントの取りこぼしを防止
- review SKILL.md Step 2.5 を更新: スクリプト出力をそのまま PR コンテキストブロックとして使用するよう簡略化（LLM による再構築・要約・編集を禁止）

### Fixed
- review スキルで PR コメント取得がスキップされるケースを解消（取得手順をスクリプトに集約することで決定的に取得保証）

### Removed
- review / self-review の allowed-tools から未使用ツールを削除（Permission Pruning 原則に基づく最小化）
  - review: `Glob`, `Grep`, `mcp__github__pull_request_read`
  - self-review: `Glob`, `Grep`
  - 対応する commands/*.md の allowed-tools も同期

## [2.6.1] - 2026-04-25

### Changed
- `reviewer-prompts.md` の Confidence スコアリングに段階的思考誘導を追加（Opus 4.7 対応）。境界値（75-85）や他 reviewer との矛盾時に diff 意図確認・既存問題誤検知チェック・証拠裏付け確認の 3 ステップを明記

## [2.6.0] - 2026-04-24

### Added
- review スキルに PR 会話コンテキストの reviewer プロンプト注入を追加
  - `gh api repos/{owner}/{repo}/pulls/<PR>/comments` で行単位レビューコメントを取得
  - `gh pr view --json reviews` でレビューサマリを取得
  - PR 説明・issue コメントと合わせて PR コンテキストブロックとして構造化（SKILL.md Step 2.5）
- reviewer-prompts.md に「PR コンテキスト注入テンプレート」(#2.5) を追加
  - 検出ルールはタグベース: `[re-flag: @<user>]` / `[resolved: @<user>]` / `[intent-conflict]` / `[scope:out]`
  - 重複指摘の回避（既指摘かつ diff で修正済みは出力除外）
  - 著者意図の尊重（PR 説明のスコープ・意図と照合）
- scoring-guide.md にタグベースの加減算ルールを追加（正本）
  - `[re-flag: ...]`: +15（既指摘かつ diff で未修正の押し戻し）
  - `[intent-conflict]`: -20（spec-compliance の仕様違反は対象外）
  - `[resolved: ...]`: -30（PR 会話で LGTM/resolved）
  - `[scope:out]`: -50（PR 説明で明示されたスコープ外）
  - 行単位 review comment で既指摘 かつ diff で修正済み: 報告対象外
- triage-guide.md の Stage 1 に PR コンテキストによる観点追加・冗長化ロジックを追記（review skill のみ）

### Changed
- scoring-guide.md と reviewer-prompts.md の責務分離を明確化: reviewer は検出・タグ付けに集中、confidence 数値の加減算は scoring-guide.md を正本として Step 6 で適用

## [2.5.0] - 2026-04-22

### Added
- review / self-review スキルに部分失敗耐性ロジックを追加。explorer / reviewer が並列実行中に失敗しても成功した結果で合成継続し、欠損観点を最終レポートに明示する（最小保証 reviewer-bugs + reviewer-claude-md の両方失敗時のみ中止） (#25)
- self-review スキルに「Generator と分離された Evaluator」設計原則セクションを追加。dev-workflow:git-commit-helper との連携フローを明示 (#27)

## [2.4.2] - 2026-04-19

### Changed
- `check-deps.sh` を `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [2.4.1] - 2026-04-17

### Changed
- review/self-review の skill frontmatter effort を `max` → `xhigh` に変更（Opus 4.7 のコーディング向け新推奨設定）
- reviewer subagent の起動を `effort: max` 明示指定に変更（深い推論を優先、偽陽性は Confidence ≥80 フィルタで除去）
- effort 設計意図を SKILL.md に明文化（orchestrator: xhigh、reviewer: max の役割分担）

## [2.4.0] - 2026-04-13

### Added
- review: EnterWorktree/ExitWorktree による worktree 分離実行（レビュー中の並行作業を可能に）

### Changed
- review: `gh pr checkout` を worktree 内で実行するよう変更（作業ブランチへの影響を排除）

## [2.3.3] - 2026-04-04

### Fixed
- review/self-review スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

## [2.3.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [2.3.1] - 2026-03-30

### Changed
- explorer のモデルを opus → sonnet に変更（情報収集タスクの effort 最適化、reviewer は opus 維持）

## [2.3.0] - 2026-03-29

### Changed
- self-review: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（修正方針選択 + 後処理）

### Removed
- rules/self-review-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）

## [2.2.1] - 2026-03-29

### Fixed
- userConfig.review_confidence_threshold に type/title を追加し manifest バリデーションエラーを修正

## [2.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（review/self-review: max）
- userConfig: review_confidence_threshold でレビュー閾値をカスタマイズ可能に

## [2.1.0] - 2026-03-26

### Added
- Phase 0 トリアージ: diff 分析による動的エージェント構成決定（Stage 1 タイプ判定 → Stage 2 体数・フォーカス・冗長度決定）
- explorer エージェントタイプ: 事実収集特化（function-flow, dependency-trace, branch-impact, history-context, shared-module-impact）、上限 6 体
- reviewer 冗長化: 対象コードの複雑さに応じて同一観点を複数体（angle 違い）で起動、上限 10 体
- spec-compliance 観点: session-context / Issue / knowledge との仕様整合性チェック
- references/triage-guide.md: Phase 0 判定ロジック・パターンマトリクス・フォールバック構成
- references/explorer-prompts.md: explorer プロンプトテンプレート集
- references/reviewer-prompts.md: 観点別 reviewer プロンプトテンプレート集（現行 #1-#16 から移行・再構成）
- scoring-guide: explorer 裏付け (+10)、冗長ペア合意 (+10)、冗長ペア片方のみ (-5) ルール追加

### Changed
- 固定2フェーズ構成（Phase 1 固定6+条件2 → Phase 2 動的8）を廃止し、Phase 0 トリアージ → 探索 → レビューの動的3フェーズ構成に移行
- CLAUDE.md 準拠チェック: 冗長2体 → Phase 0 判断で 1-2 体（複雑さに応じた冗長化）
- diff-first 原則を改訂: 変更箇所を含む関数の全体確認・類似名称の確認を Read 許可用途に追加

### Removed
- references/agent-prompts.md: 3ファイル（triage-guide, explorer-prompts, reviewer-prompts）に分割移行

## [2.0.0] - 2026-03-25

### Added
- 2フェーズレビュー構成: Phase 1 (コアレビュー) → Phase 2 (専門レビュー動的起動)
- Phase 2 専門エージェント8種: セキュリティ(OWASP)、パフォーマンス、API設計、依存関係、マイグレーション、設定、クロスカッティング影響、パターン統一
- Phase 2 起動判定: diff パターンマッチ（静的）+ Phase 1 結果からの動的判定
- Phase 2 スキップ条件: 小規模かつ懸念なしの場合は Phase 1 のみで完了

### Changed
- 全エージェントを `model: opus` で起動（品質最大化）
- scoring-guide: 複数エージェント同一指摘の加算を +10 → +15 に引き上げ
- scoring-guide: Phase 2 専門エージェント関連のスコアリングルールを追加

## [1.5.0] - 2026-03-25

### Changed
- review: diff 取得を `git diff` から `gh pr diff` に変更（ローカル状態に依存しない）
- review: 全エージェントを `isolation: "worktree"` で起動（PR ブランチの正しい状態でファイルを読む）
- review: diff-first 原則を追加（diff が真のソース、ファイル Read はコンテキスト確認のみ）
- Agent #3: ファイル全文分析→依存先の仕様確認のみに限定

## [1.4.0] - 2026-03-24

### Added
- self-review/review: セッションコンテキスト読み込み（Step 2.5）を追加。`.claude/session-context.md` から Issue の設計判断を取得し、エージェントプロンプトに注入
- scoring-guide: セッションコンテキストによるスコア減算ルールを追加（設計判断一致: -30、スコープ外: -50）

## [1.3.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（GitHub MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.2.0] - 2026-03-23

### Added
- self-review: レポート出力後に修正方針選択ステップ（Phase 6）を追加
- rules/self-review-interaction.md を新規追加

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- code-review プラグインを新規作成
- 並列エージェントによる PR レビュー / セルフレビュー機能
