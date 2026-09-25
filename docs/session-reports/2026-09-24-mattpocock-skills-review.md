# セッションレポート: mattpocock/skills の再精査（2026-09-24）

- **日付**: 2026-09-24（精査は 2026-09-23 開始）
- **基準コミット**: MP `c55ee46`（2026-09-18）/ OWN `663e069`。前回精査（2026-07-29）の基準は MP `2ab9580`（推定）
- **次回の始め方**: `git -C <mp-skills> log --first-parent c55ee46..main` で差分だけを見る
- **方法**: MP の全スキルを 11 ペアに割り当て、ペアごとに比較 → 独立検証 2 観点（事実反証 / 適合性）→ 統合・批評・改訂（37 エージェント）。
  下の「統合レポート」はその最終版で、行番号はすべて上の基準コミット時点のもの

## 決定事項（2026-09-24、ユーザー判断）

| 論点 | 決定 |
|---|---|
| MP スキルへの置き換え / プラグイン丸ごと導入 | しない（wayfinder は living-spec の上位互換ではない） |
| living-spec-workflow の存廃 | **残す**。メイン機（会社 PC）で使っている。このマシンの transcript だけの利用頻度（0 回）は過小評価だった |
| notebooklm-workflow の存廃 | 残す（A7 の alwaysLoad 解除は未実施） |
| grill を「前提の決まった問いを最大 4 問ずつ」にするか（B2） | **しない**。1 問ずつを維持（GitHub issue #3 と同じ判断） |
| `~/.claude` の設定（A6 ほか） | 破壊的 git 操作の `permissions.ask` 12 ルールと `Read(.env)` の deny を追加。psql の deny は残し、worktree 系はスキル側で対応（S6） |

## このセッションで実施したもの

- S1: git-commit-helper の `git checkout -- <file>` 指示を削除（dev-workflow 1.34.0）
- S2: design-doc の grill-protocol を正本と同期し、`validate_plugin_quality.py` に byte-replica 検査を追加（design-doc 0.4.8）
- S3: feature-dev Phase 5.3 が宣言オラクル（`.claude/review-oracles.sh`）を優先する（feature-dev 2.15.2）
- S6: worktree-setup / teardown が DB クライアントの deny 下でコマンド提示に切り替える（dev-workflow 1.34.0）
- A1: repo 直下に NOTICE、翻案した各ファイルに出典と MIT の 1 行（issue-workflow 1.6.2 / adr-keeper 0.3.3 ほか）
- A2: diagnose に「秘密情報を伏せる」節（dev-workflow 1.34.0）
- C1: living-spec の散文の改善（到達点・まだ詰められないこと・スコープ外・使い分けの軸。living-spec-workflow 0.4.0）
- `~/.claude/scripts/env-check.sh`（マシンごとの環境点検、読み取り専用）を追加。`~/.claude/skills` の旧コピー 6 件と
  `commands/revise-claude-md.md` の撤去はユーザーが手で行う（auto mode の分類器が削除を止めたため）

- セルフレビュー（/code-review:self-review、MAJOR 1 件 + 付録の推奨 3 件）を受けた修正: S3 の宣言オラクルの実行が exit code を判定に届けず、既定 120 秒の Bash timeout で打ち切られる問題（feature-dev 2.15.3。契約の正本 machine-layer.md `## 5` への SSoT pin も追加）/ teardown が Step 8 でマーカーごと worktree を消す問題（dev-workflow 1.34.1）/ living-spec README の行数（0.4.1）

- A3: grill の一般則（事実と決定の分離・未決を埋めない・説明とコードの食い違い）を feature-dev / design-doc / issue-design に取り込み、要約している 4 か所に正本への SSoT pin を置いた（2026-09-24、ユーザー指示）

- S4: feature-dev の Phase 6 が spec-compliance と BDD spec（`--spec`）を self-review に渡す。focus 名を code-review の語彙に揃え（`migration-safety` に加え `vercel-best-practices` も語彙外だった）、self-review 側は語彙外の focus を欠損観点に出す / S5: 有効判定を feature-dev の `scripts/plugin-enabled.sh` に寄せた（同じ型の判定は他 5 プラグインに約 24 か所残る）

- A4: `docs/skill-writing.md` を MP `c55ee46` の writing-for-agents / SKILL-MECHANICS / docs ページと再同期した。翻案時の取りこぼし（variance bug・co-location・後続を隠す対策が効く条件・統合の逆向き・legwork・relevance の 2 経路・no-op はモデル依存）と、前回以降の差分（cache・分割の基準・over-fitting・終わりの目安・長さでなく挙動で判定）を入れた。claude-meta に入れる C03 / C14（eval の鮮度ゲートに掛かる）は C8 の束に残した

- A5: spec-compliance に仕様の行の引用を必須にし、引用して diff と突き合わせられる指摘は確信度 95 まで可とした（code-review 2.130.1）。scoring-guide の脱落経路に「③ 最初から閾値未満」を足した

- A7: notebooklm-workflow の `.mcp.json` から `alwaysLoad` を外した（0.2.9）。スキルは関数一覧に無いだけで未導入と案内せず、先に ToolSearch で読み込む

- S7: start のダッシュボード（D2）に backlog の件数と古い順 3 件を出すようにし、discover の記述を合わせた（issue-workflow）

- S8: bdd-spec の glossary-ssot.md から、実装の無い「evaluate が別名に warning を出す」を外し、事実に合わせた。既存プロジェクトの all_spec.md は手で直す

- S9: issue-design が backend の無い repo でも新規本文の設計を続けるようにした（BACKEND=none）。独立検証 2 体の指摘（新規起票の案内・貼り付けたリライト・記法・順序）も取り込んだ

- S10: design-doc の実装ブリッジの `spec=` を「BDD spec.md のパス（無ければ省く）」と 4 か所で明記した

- S10: 実際のコミットは 4eb10e3（別セッションとの index 共有でコミットが混線し、そちらで amend して分けた）
- S11: `docs/shared-state.md` の登録簿を実態に合わせた。knowledge の consumers に code-review（spec-compliance）・dev-workflow（diagnose）・feature-dev / design-doc（grill）を足し、`glossary`（`all_spec.md`。producer: bdd-spec）の行を足した

- S12: 「推測を含む」とされていた前提を独立調査 3 体 + 反証 1 体で確かめた。実害は `ts`: 過去に入った原因を診断した時刻で書くと、retro が還流前の失敗を還流後の再発に数え、窓の外の古い失敗を窓内に戻す（`retro-aggregate.sh` は `timestamp` だけで数える）。diagnose は原因 commit（`Co-Authored-By: Claude` があるものだけ）の author date を `ts` にし、特定できなければ書かない（dev-workflow 1.34.4。手順は `skills/diagnose/references/journal-candidate.md`）。failure-journal 側は `ts` を発生時刻と定義し、retro が `（由来 <sha>）` で diagnose の行を見分けて同じ原因をまとめる（0.6.3）。差分レビュー（3 観点・37 件 → 反証後 22 件、major 1: `log.showSignature=true` で `ts` が壊れる）を反映した。残したもの: dev-workflow 1.34.3 以前の diagnose が書いた行（由来なし・`ts` は診断時刻）は見分けられない / retro の description の「自己訂正の候補」は据え置き（ルーティングに効かず、変えると evals の再実行が要る）

- S13: adr-keeper の SKILL.md を README の「本文の節はすべて必須」に合わせた（0.3.4）。埋められない節は推測で埋めず完了報告に挙げる。差分レビュー（2 観点・24 件 → 反証後 8 件、すべて minor 以下）を反映した。id の丸め（秒が 00 の 4 件）は transcript で由来を確かめた: 残っている 3 件はどれも adr スキルを通さず直接 Write され、`date` も走っていない（節の構成もテンプレと違い、適用方法の節が無いものがある）。スキルの外で書かれる経路にはスキル本文が届かないので、記述の修正では塞げない。既存 ADR の id は相互参照のキーなので直さない。続けて、ユーザー判断で adr-keeper に PreToolUse hook（adr-write-guard）を足した（0.4.0。component-addition-advisor で doc-freshness 拡張と比べ、新 hook を選んだ）: `.claude/adr/` 直下への新規作成で id・ファイル名・現在時刻との差・必須見出しを検査して止める。差分レビュー（3 観点・32 件 → 反証後 28 件、major 2: 64KB 超の本文で pipefail の SIGPIPE により誤ブロック / 素通り、シェルと hook の TZ 差で止まり続ける）を反映し、本文の解析を jq 1 回にまとめた。同じ SIGPIPE の型が他の hook 4 本にあり、別タスクに切り出した

- S14: issue-workflow の template-9sections.md から廃止済みのミラー指示（両プラグインへの反映）を外し、design-rules.md と同じ書き方に揃えた。プラグイン配下に同じ型の残りは無い（`.claude/designs/` の旧記述は S15）

- S15: living-spec の design doc（`.claude/designs/20260715-living-spec-workflow.md`）の未決 4(a) に、ミラー規約の廃止で「実装量 2 倍」の cons が成り立たなくなった旨を追記した（元の記述は判断の経緯として残した）

- S16: push-reminder を、heredoc の本文と複数行のクオートを除いたうえで、コマンドの位置に来る `git push` だけで鳴るようにした。黙るべき条件のテスト（引数としての並び・heredoc 本文・複数行クオート）と、64KB 超のコマンドで見落とさないこと（SIGPIPE）を足した。手で入れた変異 11 件はすべてテストで殺せる

- S17: CLAUDE.md Gotchas の vNEXT 規約 2 行を 1 行にまとめた（片方にしか無かった「置換はそのプラグイン配下だけ」「共通スクリプトは issue 番号か設計ノートで参照」を残す側へ移した）

- B1: diagnose に、翻案時に落ちた core dump・本番 / 再現環境への計装・PR 本文を足し、Phase 4 完了時に確証した仮説・原因の file:line・修正方針を提示して待たずに進む手順を入れた。Phase 0 の性能劣化を肯定形にした

- B2: 見送り（ユーザー判断。確認は 1 問ずつの方針と衝突する）
- B3: feature-dev の Phase 3 Step 5 で、設計契約を architect 起動前に 1 問で確認するようにした。ラウンドへの相乗りではなく独立した 1 問にした（1 問ずつの方針に合わせた）。ユーザーの決定も未決も無い契約では聞かない

- B4: feature-dev に `references/testing-discipline.md`（Phase 5 がテスト基盤のあるときだけ読む）と `references/module-design.md`（clean-architecture の architect に渡す語彙・4 原則・依存の 4 分類）を足し、architect の出力に Test Seams、Phase 4 の比較に depth・locality・seam の位置を足した。トートロジーは plugin 独立のため testing-pitfalls を参照せず本文に書いた。design-doc への複製は同期検査を入れるまで見送り

- B5: code-review の test-quality に名前付きアンチパターン（実装への結合・同語反復・境界外の mock）を足し、起動条件に「新しいソースがあるのにテストの変更が 0」を足した（code-review と feature-dev の triage を対で直した）

- B6: ADR まわり。adr-keeper の記入例に 7 類型、grill の前提確認（正本・複製・要約 3 か所）と diagnose・issue-create・issue-design に「既存 ADR との矛盾を明示する」、3 条件ゲートを design-doc Phase 6 経由で免除、feature-dev Step 5 に ADR 候補の列挙（adr-keeper 有効時のみ・0 件が普通）

- B7: Issue 系の規範。完了条件の悪い 3 つの形（discover・template-9sections）、出典の無い決定を open に・デモ点検・prefactor 先行（design-rules）、同義語で探して探した場所を報告（issue-create）、起票前に既存 Issue を open / closed で検索（plugin-feedback）

- B8: CLAUDE.md の常駐量を約 55KB から 50KB に減らした。plugin eval のケース作成・運用の詳細を `docs/plugin-eval.md` へ、Event Bus の永続化と API を `docs/event-bus.md` へ移し、ポインタを残した（イベント表は機械照合の対象なので残した）。`docs/skill-writing.md` の対象を rules / agents / prompts / CLAUDE.md に広げた。Gotchas は事故由来なので手を付けていない

- B11: 候補の昇格が止まった原因は retro が 08-30 以降回っていないこと（未レビュー 39 件、レビュー済み 39 件は全件採用・却下 0。数えたのは verdict と ts だけ）。SessionStart で未レビューが 15 件以上か最古 14 日以上なら `/retro` を提案させる 1 行を足した。還流先の判定に「配線されていない検査の修理」と「ナビゲーション用のポインタ」を足した

- B12: pr-creator に tune の before / after の対・diagnose の red→green の引用・「不可逆:」と「このPRではやらない:」の定型文・構造変化の最小の図を足した（show-me の文面は転載せず考え方だけ）

- B13: review で PR に紐づく Issue を 1 段取得して spec-compliance の仕様ソースに（信頼しない入力として同梱）、単独観点の優先順（最小保証 → spec-compliance → security）、レポートに「仕様整合」の 1 行、CONTRIBUTING.md / CODING_STANDARDS.md を規約ソースに。レポートが挙げた triage-guide と orchestration-measurement の食い違いは、該当行が別の記述に変わっていて現行では再現しなかった（spec-compliance の起動条件の正本は triage-guide の 1 か所だけ）

- C5: feature-dev の実装承認前に「同じセッションで続けるのが既定、`/compact` は最後の手段」（150k の数値は書き写していない）
- C9: `docs/pipeline-design.md` の原則 5 に再委譲させない旨、reviewer 共通指示に「Skill / Agent tool は呼ばない」
- C11: issue-workflow の Phase 0 を `.claude-plugin/lib/backend-detect.md` を正本にした `BACKEND-DETECT` 区間にし、`validate_plugin_quality.py` で byte 比較する（10 スキル。消費サイトは走査で集め、件数の下限で消失も止める）
- C12: discover の観点 D の優先順位付けにだけ git log のホットスポット

**未着手**（統合レポートの ID）: B9、B10、C2、C3、C4、C6、C7、C8、C10。

---

## 統合レポート

- 比較対象: MP = mattpocock/skills のクローン（HEAD `c55ee46`、2026-09-18）、OWN = claude-plugins（HEAD `663e069`）。
- MP のパスはリポジトリのルートからの完全なパスで書く（例: `skills/engineering/wayfinder/SKILL.md`）。
- **日付は、MP の main に入った日で書く。** author date は使わない。確認には `git rev-list --first-parent main` と `git merge-base --is-ancestor` を使った。
  - 前回精査（2026-07-29）の基準は、その時点の MP main の先端 `2ab9580`（2026-07-28 マージ）とみなした。前回どの ref をクローンしたかの記録は無いので、これは推定。
  - v1.2 のリリースブランチ（改名・cache・frontier ラウンドなど）は、2026-08-05 に PR #593（`b405fe0`）で main に入った。確認済み。
- 利用頻度はこのマシンの transcript だけから測った（2026-06-27〜09-23、約 88 日）。別マシンの分は含まない。hook 経由の稼働は Skill の起動回数に出ない（§6.3）。
- MP の docs ページには SKILL.md より古い記述が残っている箇所がある。例:
  - `docs/engineering/wizard.md:44`
  - `docs/engineering/diagnosing-bugs.md:21, 48, 54, 71`
  - `docs/engineering/codebase-design.md:52, 72`
  - `skills/engineering/ask-matt/SKILL.md:42`
  - `skills/in-progress/README.md:18-19`

  そのため、docs だけを根拠にした要素には〔docs〕と付けた。
- 自分で一次ソースに当たって確かめた主張には「確認済み」と書いた。それ以外は検証者の照合結果に依拠している。

---

### 1. 結論

1. **置き換えるべきものは無い。** wayfinder は living-spec の上位互換ではない（§2）。MP のプラグインを丸ごと入れることも勧めない。
   - プラグインのスキルは skillOverrides で個別に止められない（code.claude.com の skills / settings-reference）。
   - MP のモデル起動スキル 11 件のうち、code-review・diagnosing-bugs・domain-modeling・writing-for-agents の 4 件は、OWN のスキルと起動条件が重なる（§6）。
2. **最優先は OWN 内部の欠陥（§4 の S 群、18 件）。** MP との比較の途中で見つかったもので、MP とは関係ない。影響の大きい順に:
   - S1: git-commit-helper が、未ステージの変更を消す `git checkout -- <file>` を指示している（データ消失）
   - S2: design-doc の grill-protocol は「byte 一致の複製」と宣言しているのに 14 行欠けていて、検知の仕組みも無い（#233 と同じ失敗が再発しうる）
   - S3: feature-dev の静的ゲート（Phase 5.3）が、宣言済みのオラクル（`.claude/review-oracles.sh`）を使わない。この repo では何も検査せずに通る
   - S4: feature-dev から self-review に Spec 軸（spec-compliance）が渡らない。観点名 `migration-safety` も code-review 側の語彙と一致しない
   - 機能が黙って働かない型として、S5（feature-dev の dormant 判定が古い）と S6（worktree の psql がユーザーの deny とぶつかる）も直す。ユーザー環境の側には、`~/.claude/skills` の旧コピーとリンク切れ（S18）がある
3. **MP から取り込む価値が高いもの（§4 の A 群）:**
   - A1: 翻案元の MIT 表示
   - A2: diagnose の伏せ字。MP より広く、永続化するテキストまで対象にする
   - A3: grill の「事実は自分で調べ、決定はユーザーに委ねる」一般則
   - A4: `docs/skill-writing.md` の再同期。翻案時に取りこぼした分と、前回以降に MP で増えた分を分けて扱う
   - A5: spec-compliance の確信度の付け方を直す
   - A6: 破壊的な git 操作を `permissions.ask` で確認制にする（コードは書かない）
   - A7: notebooklm の alwaysLoad をやめる
   - A8: 今回の採否を 1 か所に記録する
4. **見送るもの（§7）:** wayfinder の frontier・claim・blocking、living-spec の表スキーマ変更、research / prototype / teach / wizard の翻案、Fowler の smell リスト、changesets、em-dash の禁止、Codex 対応。
5. **前提の訂正は 2 つに分かれる。**
   - **wayfinder 単体:** 前回精査の時点で既に main にあった（`639df6e`、main 反映 07-08）。その後の変更も文言だけ。
   - **スキル群全体:** 前回以降に実際に強化されている。いずれも前回精査より後に main に入った:
     - grill のラウンド方式と書式の固定（08-05）
     - 執筆指針の writing-for-agents への再構成と cache 概念（08-05）
     - 診断の Redact（08-06）と post-mortem 削除（08-15）
     - wizard / to-questionnaire / wait-what の昇格（08-05）
     - PHASE-BOUNDARIES（08-05）、docs の FAQ 化（08-05）
     - retro / pr / implement-spec の追加（08-21〜09-17）

   つまり「MP が強化された」という前提は、群全体については正しく、wayfinder については当たらない。前回の時点で既にあったのに比較の記録が残っていない要素もある（§5.2）。
6. **取り込みに投資する前に決めること:** living-spec・spec-advisor・diagnose・bdd-spec・notebooklm は、このマシンでは Skill としての起動が 0 回だった。進め方は「別マシンで同じ集計 → living-spec と notebooklm-workflow の存廃を決める → 残すものにだけ投資する」の順に固定する（§2.7、§8）。hook 経由で働く部分（spec-advisor の常駐ルールなど）は起動回数に出ない点に注意。

---

### 2. wayfinder ↔ living-spec の判定

#### 2.1 判定

| 問い | 答え |
|---|---|
| 関係 | overlap。中核の目的は重なるが、担っている層が違う |
| 上位互換か | いいえ |
| 置き換えるべきか | いいえ |
| 取り込むべきか | 散文で書ける数点だけを 1 回の bump で入れる。スキーマ変更と subagent 化は見送る。ただし順序は固定する: 別マシンで集計 → 存廃を決める → 残すなら (a) を実施（§2.7） |

#### 2.2 重なっている部分

どちらも、Issue 化や実装の前に、複数セッションをかけて未確定の点を決定まで詰めるための道具。対応はおおむね次のとおり。
- OQ ≒ decision ticket
- Decision log ≒ ticket の解決コメントと「Decisions so far」
- status の「次に決めるもの」≒ frontier

#### 2.3 上位互換でない根拠（living-spec にあって wayfinder に無いもの）

| living-spec の機能 | OWN の根拠 | wayfinder 側 |
|---|---|---|
| 確度ラベル（確定 / 方向性(仮) / 未定）と since を持つ、現時点の仕様表 | `living-spec-workflow/skills/living-spec/references/format-spec.md:47-58, 97-107` | ticket は open / closed の 2 値。map は 5 節だけ（MP `skills/engineering/wayfinder/SKILL.md:31-53`） |
| 収束率・確度の内訳・未解決 OQ の残数・経過日数 | `living-spec/SKILL.md:293-319` | 数値の指標は無い |
| 追記のみの運用と reopen 禁止（議論が再燃したら新しい OQ を立て、旧 OQ / D# を参照する） | `format-spec.md:72, 206-213`、`SKILL.md:256` | 決定が他の ticket を無効にしたら更新か削除（MP `skills/engineering/wayfinder/SKILL.md:126`）。決定の覆し方は「公式の指針なし」（MP `docs/engineering/wayfinder.md:84`） |
| 決定の記録形式（確信度・根拠・出典・残課題） | `format-spec.md:76-93` | 解決コメントは自由記述 |
| 8 段の整合・鮮度検証と doc-freshness 連携 | `living-spec-maintain/references/check-rules.md:9-24` | 検証の仕組みは無い。setup の verify モードも MP 自身が却下（MP `.out-of-scope/setup-skill-verify-mode.md`） |
| 外部依存が無く、日本語で、repo にコミットしたファイルとして残る | `living-spec/SKILL.md:48` | issue tracker が前提。未設定なら setup を案内し、そのうえで `.scratch/` の local markdown に落ちる（MP `skills/engineering/wayfinder/SKILL.md:25`）。ただし MP 自身が repo 内への保存を勧めていない（MP `docs/engineering/wayfinder.md:78`） |

割り引いて見るべき点がある。8 段検証のうち 1〜7 段は「機械判定」と呼ばれているが、実際は LLM が perl / grep を実行する手順で、専用スクリプトも回帰テストも無い（`living-spec-maintain/SKILL.md:111`「専用スクリプトは起こさない」。`.claude-plugin/scripts/tests/` に living-spec のテストは 0 件）。

#### 2.4 上位互換に見える理由（wayfinder にあって living-spec に無いもの）

- **OQ を「解く」手順。** ticket を research / prototype / grilling / task の 4 類型に分け、人が要るもの（HITL）と要らないもの（AFK）を区別する（MP `skills/engineering/wayfinder/SKILL.md:73-80`）。living-spec のサブコマンドは記録用しか無い（`living-spec/SKILL.md:51-59`）。
- **到達点（Destination）** を最初に決め、スコープの判断基準にする（同 `:32-34, 111`）。
- **霧（Not yet specified）とスコープ外を分けて扱う**（同 `:82-101`）。
- **並列セッション用の claim と frontier**（同 `:67-69`）。
- **早期退出。** 霧が無ければ地図を作らずに終える（同 `:112`）。
- **下流への引き渡し。** to-spec → to-tickets へ渡す（MP `docs/engineering/wayfinder.md:18, 66`）。

「wayfinder の方が上」という直感は、この「解く手順」に関しては正しい。ただし living-spec の台帳と検証の代わりになるものは wayfinder に無い。

#### 2.5 置き換えない理由

1. **wayfinder は単体では動かない。** 下で grilling・domain-modeling・research・prototype を呼ぶ（MP `docs/engineering/wayfinder.md:103`）。tracker を使うなら setup も要る。skills.sh を使えばこの 4〜5 スキルと setup だけを入れられるが、それでも OWN の規約や成果物の置き場とぶつかる（下記 3・4）。
2. **他のスキルから呼べない。** 利用者起動専用で（MP `skills/engineering/wayfinder/SKILL.md:4`）、MP 自身の規約でも他スキルからは呼べない（MP `.agents/invocation.md:8, 22`）。
3. **置き場が合わない。**
   - issue-workflow の local backend には blocking も assignee も無い（`issue-workflow/skills/issue-create/references/feature.md:1-14`）。
   - Linear への書き込みは明示的な指示があるときに限っている（`issue-workflow/rules/project-rules.md:25`）。
   - GitHub で使うと、公開リポジトリの claude-plugins に計画用の ticket が並ぶ。MP 自身もこれを問題に挙げている（MP `docs/engineering/wayfinder.md:78`）。
4. **ADR が二重になる。** domain-modeling が `docs/adr/NNNN-slug.md` と `CONTEXT.md` を作る（MP `skills/engineering/domain-modeling/SKILL.md:40`、`ADR-FORMAT.md:3`）ので、adr-keeper と重複する。
5. **MP 自身が未解決と認めている失敗がある**（MP `docs/engineering/wayfinder.md`）。
   - grill が冗長になる（:80-81）
   - Notes 欄に書いた例外を、エージェントが自分への許可として読む（:68-69）
   - 27 枚の ticket に分けたらウォーターフォールになった（:71-72）
   - 並列に grill すると質問が重複する（:74-75）

#### 2.6 取り込む要素（検証者の判定が割れた点の裁定）

適合性の検証者の判断に寄せた。決め手は利用実態で、次を確認した。
- `~/Projects/*/.claude/living-specs` は 0 件（ls で確認）。
- 作成（`03cfaa1`、07-15）以降のコミットは 7 件。うち 6 件は repo 全体の一括修正。残る 1 件（`b56378d`）は eval をきっかけにした description の修正。実際に使ったことがきっかけの変更は 0 件（確認済み）。

| 区分 | 候補 | 中身と着地点 |
|---|---|---|
| 残す場合に採用（1 回の bump） | P1-C09 + C08 | 「いつ使うか」の表と README に軸を 1 本足す（「1 セッションで収束するなら design-doc / feature-dev の grill、複数セッションなら living spec」）。init の冒頭に判定を 1 行置く（`living-spec/SKILL.md:23-31`、`README.md:90-100`）。description は変えない |
| 同上 | P1-C01 / C02 / C03（散文版） | 到達点は「現在地サマリ」の先頭 1 行にする。スコープ外は散文の節にし、OQ は decision で閉じて見出しに「スコープ外:」を付ける。霧は「進め方フェーズ」の中の小見出しにする。パース対象の 3 節（`format-spec.md:36`）には触れない |
| 同上 | P1-C11 / C12 / C13 | status の最後の案内を「HOW → design-doc、WHAT → bdd-spec、作業 → issue-design」にする（`SKILL.md:319`）。decision の完了報告では ID に問いの先頭を添える（`:252`）。「実装に踏み込まない」を 1 行足す |
| 残す場合でも、1 回使ってから決める | P1-C04（resolve）、P1-C10（spec-advisor の軸） | resolve は grill-protocol の 3 つ目の複製を作らず、issue-design のルール 5 と同じ粒度の言い換えにする。spec-advisor の軸は、design doc 自身が置いた条件（「1 プロジェクトで運用してから」、`.claude/designs/20260715-living-spec-workflow.md:351-357`）をまだ満たしていない |
| 残しても廃止しても採用 | P1-C23（修正版） | 今回の比較結果と見送り理由は A8 の記録（`docs/session-reports/`）に入れる。living-spec の design doc には、その記録へのポインタを 1 行置くだけにする（本文は複製しない） |
| 裁定で見送り | P1-C24（Notes 節） | 事実検証は keep、適合性検証は drop。drop に寄せた。Notes 欄は MP でもエージェントが許可を書き足す穴として報告されており（MP `docs/engineering/wayfinder.md:68-69`）、「進め方フェーズ」と「参照ソース」で足りる |
| 見送り | C05, C06, C07, C14, C15, C16, C20〜C22, C25 | §7 を参照 |

#### 2.7 推奨

§8 の判断事項 1 として 3 案を示す。**順序は「別マシンで集計 → 存廃を決める → (a) を実施」に固定する。**

- **(a) 最小限の投資で残す。** 上の「残す場合に採用」を 1 回の bump で入れる。description は変えないので runner の再実行は要らない。維持費は bump と CHANGELOG だけでは済まない。runner の eval を 15 ケース抱えており（`evals/cases/living-spec-workflow.yaml`、確認済み）、eval をきっかけにした修正も実際に起きている（`b56378d`）。「使われないまま次の repo 全体の一括修正が来たら廃止する」という条件を design doc の未解決事項に書いておく。
- **(b) 廃止する。** 後始末の範囲は次のとおり。
  - marketplace.json、INDEX.md、CLAUDE.md のプラグイン一覧
  - `evals/cases/living-spec-workflow.yaml` の 15 ケース
  - doc-freshness の既定の監視対象（`doc-freshness/hooks/scripts/frontmatter-guard.sh:49`、`stale-check.sh:31`）
  - feature-dev の living spec への言及（`feature-dev/references/grill-protocol.md:39`、`feature-dev/skills/feature-dev/SKILL.md:279`）

  代わりには、design-doc の「未解決事項」の書式を使う。living-spec 自身の design doc も、この書式で未確定事項を管理している（`.claude/designs/20260715-living-spec-workflow.md:326-357`）。
- **(c) wayfinder を試す。** 非公開リポジトリで、local markdown に限って、MP を skills.sh で個別に入れる。claude-plugins では行わない。

別マシンでも使われていなければ (b) を推す。使われていれば (a)。

---

### 3. ペア別の判定表

| ペア | 関係 | 置き換え判定 | 主な取り込み候補 | 検証・批評で直した点 |
|---|---|---|---|---|
| P1 wayfinder ↔ living-spec | overlap | 残す（上位互換ではない）。先に存廃を決める | 散文の改善（C09 / C08 / C01〜C03 / C11〜C13）、比較記録（C23 → A8） | wayfinder は 07-29 時点の main に含まれていた（`639df6e`、main 反映 07-08、確認済み）。MP プラグインのスキル数は 25 件（確認済み）。tracker が未設定のとき、黙って local に切り替わるのではなく、先に setup を案内する（MP `skills/engineering/wayfinder/SKILL.md:25`）。C14 は既に OWN にある。8 段検証はテストの無い LLM 手順 |
| P2 grilling 群 ↔ grill-protocol | overlap | 残して翻案を更新する | 事実と決定の分離（C2）、答えられない問いを未決のまま残す（C7）、複製の同期（C6 → S2）、feature-dev の確認ゲート（C3）、frontier をまとめて聞く（最大 4 問、C1 + C10）、無操作での自動継続（C15） | 翻案元は当時の grill-me（`800201f` の main 反映は 06-17、OWN `dc5dd95` は 06-03、確認済み）。前回時点で main にあったのは `e5932a7` と `0e9a072` だけ。frontier ラウンド（`a4b2009`）と書式の固定は、前回より後に main に入った（08-05、確認済み）。「参照を決定的にロードしている」は誤り。確認ゲートは実装の直前以外にもある |
| P3 domain-modeling・wait-what ↔ adr-keeper・knowledge・用語 | overlap | 残す | 誤った記述の訂正（C04 → S8）、ADR の 7 類型（C08）、ADR との矛盾を明示する（C10）、design-doc 経由ではゲートを免除（C12）、grill 終了時に ADR 候補を並べる（C11）、ユーザーの説明とコードの食い違いを問う（C14）、wait-what の日本語版（C06）、all_spec.md の読み取り側だけの最小形（C01 / C03、条件付き）、shared-state への登録（C02 の一部 → S11） | 「concepts が見つからない」は誤り（yatima に約 50 件）。ただし `subkind: glossary` は 0 件。C05 は writing-polish の eval ゲートに掛かるのでコストは低くない。C13 は §3 の裁定で見送り |
| P4 diagnosing-bugs ↔ diagnose | overlap（OWN は MP の 06/17 版の翻訳） | 残す | 伏せ字（C01〜C03 → A2、範囲を広げる）、翻案で落ちた core dump・本番・PR（C13, C14）、Phase 4 の後で待たずに提示する（C05）、Phase 0 を肯定形で締める（C09） | seam の受け皿は MP にもある。伏せ字の範囲は MP #674（OPEN）がさらに広く求めている。HITL テンプレートは非 TTY で rc=1 |
| P5 code-review・pr ↔ code-review・pr-creator | overlap | 残す | feature-dev で spec-compliance を起動する（→ S4）、確信度の修正と spec 行の引用（C3 + C17 → A5）、仕様整合の 1 行（C5）、`--spec`（→ S4b）と `Closes #N`（B13）、pr-creator の添付・不可逆の 1 行・任意の図（C10 / C9 / C8） | 「スコープ逸脱は構造上本文に載らない」は言い過ぎ。キャップで落ちたのは最大 10 件。OWN の spec-compliance は既に単独の reviewer。spec-compliance は BDD spec を読まない（確認済み）。MP の retro は STUB |
| P6 to-spec・to-tickets・triage・setup ↔ issue-workflow・bdd-spec・design-doc | overlap | 残す（取り込みは縮める） | 完了条件の悪い 3 形（C03〔docs〕）、prefactor（C04a）、出典の無い決定は open に回す（C16）、同義語で探し、探した場所を報告する（C09）、plugin-feedback の重複検索（C19）、ADR との矛盾を明示する 1 行（C14）、Phase 0 の同期検査（C12、低優先）、新規本文モードの backend 依存を外す（C13 → S9）、設計書からの一括起票（C01 + C17、条件付き） | frontier / claim の出典は wayfinder 専用の操作（MP `skills/engineering/setup-matt-pocock-skills/issue-tracker-github.md:36-45`）。Phase 0 が同じなのは 10 ファイル。triage の前提（他人が作った issue）はこの repo では成り立たない |
| P7 implement 群 ↔ feature-dev・design-doc | overlap | 残す | テストの規律（C1）、Test Seams（C2）、interface の定義（C8）、依存の 4 分類（C10）、それらをまとめて置く語彙ファイル（C7、feature-dev のみ）、比較軸に depth・locality・seam 配置を足す（C9、新しい focus は作らない）、test-quality のアンチパターン（C6）、宣言オラクルの優先（→ S3）、discover 観点 D の tie-breaker（C13）、`design=` の入口（C5、条件付き） | ブリッジの `spec=` は BDD spec を指していて誤配線ではないが、文言が曖昧（→ S10。対象に `design-doc/SKILL.md:129` を追加）。explorer の結果は architect に渡っていない |
| P8 writing-for-agents・ask-matt ↔ skill-writing・spec-advisor | overlap | 残す | skill-writing の再同期（C01 / C02 / C05 / C06 / C07 / C08 / C10 / C31 / C32 / C33 → A4）、対象範囲を広げる（C04）、CLAUDE.md を必要時に読む形へ（C30）、cache の注記（C03）と分割基準の 1 項（C14）を claude-meta の束に入れる（→ C8）、living-spec の軸（C17、条件付き）、トリガー語の剪定（C29） | 「MP が後から足した」とされた項目の大半は、改名前の GLOSSARY に既にあった。C15 の節約は約 1.2k 字。MP `skills/engineering/ask-matt/SKILL.md:42` は、`1dab982` で削除済みの diagnosing-bugs → improve-codebase-architecture の post-mortem 引き継ぎを今も案内している（MP 側が古い） |
| P9 retro・handoff・loop-me ↔ failure-journal・session-context | retro は overlap、handoff は complementary、loop-me は disjoint | 残す | 未検証の断定を格下げする（A8→B10 の一部、〔docs〕）、handoff を個別に試す（A9 → B10）、配線されていない検査の分類（A2 → B11）、pointer を優先する（A4 修正版 → B11）、revise-claude-md の振り分け（A1 → C8）、guardrail が無いことの検出を claude-code-setup の Phase 1 へ（A7 → C8） | CC 2.1.280 に組み込みの `/handoff` は無く、`/fork`・`/branch` はある（バイナリで確認済み）。revise-claude-md は Anthropic 公式の逐語訳。cache と改名は、前回精査の時点では main に無かった後追いの差分（main 反映 08-05）。variance bug・co-location・コンテキスト境界の条件は翻案時の取りこぼし |
| P10 OWN に対応物の無い MP スキル | complementary | 残す | 破壊的 git 操作の確認（→ A6）、notebooklm の alwaysLoad をやめる（→ A7）、staging-patterns の修正（→ S1）、wizard / teach / merge は個別に入れる | wizard の昇格（`b3376f8`）と model-invoked 化（`61accb0`）はどちらも main 反映 08-05 で、前回精査より後（確認済み）。wizard は範囲決めの段で `.env` 本体を読む。`.env.example` はユーザーの deny `Read(.env.*)` で読めない（確認済み、→ C7） |
| P11 丸ごと導入・運用慣行 | overlap | 丸ごとは入れず、置き換えもしない | NOTICE（A01 → A1）、伏せ字（A06 → A2）、grill の同期（A05 → S2 / B2）、skill-writing の再同期（A07 → A4） | setup が書く英語ブロックは書く前に編集できる。setup が必須なのは 3 件だけ。MP の `docs/adr` は doc-freshness の全体走査で誤検出される。`--strict` は実測で常に失敗する |

#### 主な裁定

| 論点 | 割れ方 | 裁定 | 自分で確認した一次ソース |
|---|---|---|---|
| MP の日付の数え方 | 草稿は author date と committer date が混在 | main に入った日で統一。前回の基準は `2ab9580` | `git rev-list --first-parent`、`--is-ancestor 2ab9580`。v1.2 は PR #593（`b405fe0`、08-05） |
| living-spec への取り込みの幅 | 事実検証: ほぼ残す / 適合性検証: 大半を見送る | 適合性に寄せる。散文の改善だけ | `~/Projects/*/.claude/living-specs` は 0 件 |
| design-doc の `spec=` は誤配線か | 事実検証: 有効 / 適合性検証: 誤配線 | 意図は BDD spec で、誤配線ではない。文言は S10 で直す（対象 3 か所） | `feature-dev/commands/feature-dev.md:27`、`design-doc/skills/design-doc/SKILL.md:129, 166`、`template.md:94`、`section-guide.md:68` |
| grill の翻案元 | 比較: grilling@`800201f` / 事実検証: grill-me | grill-me | `800201f` の main 反映は 06-17、OWN `dc5dd95` は 06-03 |
| bdd-spec の別名禁止チェック | 事実検証: 実装する / 適合性検証: 記述を削る | 記述を訂正する（S8） | `bdd-spec/skills/create-spec/references/glossary-ssot.md:49` |
| grill の複製をどう同期するか | byte 比較 / SSoT pin | **両方を使い分ける。** ファイル丸ごとの複製（design-doc 版）は byte 比較、言い換えの消費サイトは pin。ADR-20260813223000 が 2 つの機構の併存を定めている | ADR-20260813223000 の「検討した代替案」1 と「決定」（初期スコープは code-review だけ）。`validate_plugin_quality.py:318-331` |
| 破壊的 git ガードの実装 | hook を追加 / permissions.ask | permissions.ask にする（A6）。S1 の修正は「何もしない」にし、`git restore --staged` を案内せずに済むようにする | `staging-patterns.md:36`。ユーザー settings に ask ルールは無い |
| diagnose の伏せ字の格 | 草稿: 利用 0 回なので B 群 / P4・P11 の検証者: 高価値・低コスト | A 群に上げる（A2）。永続化されるテキストに漏れる経路があることが決め手 | `diagnose/SKILL.md:128-133` |
| S4 と `--spec` の関係 | 草稿: `--spec` は B13 で後回し | spec-compliance は BDD spec を読まない。そのため S4a の効果は Issue ベースの repo に限られると明記し、`--spec` を S4b として同じ変更束に入れる | `spec-compliance.md:5-8`、`feature-dev/SKILL.md:560-566` |
| P3-C13（場面で概念の境界を揺さぶる） | 事実検証: design-doc と issue-design に限って modify / 適合性検証: drop | 見送る。feature-dev には候補列挙が既にある（`SKILL.md:42, 272`）。design-doc は 6 回、issue-design は 1 回しか使われておらず、質問が増える費用に見合わない | ― |
| P6-C13（setup を soft 依存にする） | 事実検証: modify / 適合性検証: drop | 採る（S9）。issue-design の新規本文は DATA_DIR を使わないのに、Phase 0 で終了する | `issue-design/SKILL.md:46-51`（確認済み） |
| P1-C24（Notes 節） | 事実検証: keep / 適合性検証: drop | 見送る（§2.6） | ― |
| handoff の導入経路 | MP プラグインと併用 / skills.sh で単体導入 | 単体で入れる。ただし §6.2 の注意つき（`~/.claude/skills` 旧コピーやリンク切れと同じ型の壊れ方） | MP `.claude-plugin/plugin.json` は 25 件。`~/.claude/skills` のリンク切れ 7 件（確認済み） |
| MIT 表示の置き場 | プラグインごとに CREDITS / repo 直下の NOTICE | 直下の NOTICE と、各翻案ファイルの冒頭 1 行。プラグイン内には NOTICE ファイルを置かないので、CLAUDE.md:86 と衝突しない | MP `LICENSE:3, 12-13`、OWN `CLAUDE.md:86`（確認済み） |
| diagnose を MP 版に置き換えるか | ― | 残す | `grep` で redact 系は 0 件（確認済み） |

---

### 4. 取り込み候補の優先順位

判断の軸は「価値 × コスト × 対象スキルの利用頻度」。コストの目安:
- repo 直下の doc: 無料（bump 不要）
- プラグイン内の変更: bump と CHANGELOG
- claude-meta と writing-polish: plugin eval の鮮度ゲートに掛かる（1 ケース約 1.5〜3 USD、`.githooks/pre-commit:111-136`）
- description の変更: `evals/runner.py` の回帰テスト

〔docs〕は、MP の docs ページだけを根拠にした要素（SKILL.md とは照合していない）。

#### S 群: OWN 内部の欠陥（MP とは無関係。影響の大きい順）

| ID | 要素 | OWN 着地点 | 価値 | コスト | 根拠 |
|---|---|---|---|---|---|
| S1 | git-commit-helper の破壊的な指示 | `dev-workflow/skills/git-commit-helper/references/staging-patterns.md:36` | 高 | 低 | 本文に「パッチ適用失敗時は `git checkout -- <file>` でステージをリセット」とある（確認済み）。実際には index の内容で作業ツリーを上書きし、未ステージの変更を消す（検証者が使い捨て repo で再現）。`git apply --cached` は失敗しても index を変えないので「何もしない」に直す。それまでに積んだステージを戻したい場合に限り `git restore --staged <file>` を案内する。同じ型の事故が `.claude/failure-journal/journal.jsonl:44` にある。OWN 版の commit 系が確実に使われたのは 5 回。名前空間なしの 12 回は `~/.claude/skills/git-commit-helper`（旧コピー。この行は無い）に解決されている（確認済み） |
| S2 | grill-protocol の複製のずれと、その検知 | design-doc 版（`design-doc/skills/design-doc/references/grill-protocol.md`）を、正本 `feature-dev/references/grill-protocol.md` に同期する。#233 節（:37-50）の実例に出てくる architect などの feature-dev 固有の語は、汎用化してから同期する。検知: ファイル丸ごとの複製は `check_safe_hook_sync`（`validate_plugin_quality.py:318-331`）と同じ型の byte 比較にする。言い換えの消費サイトは SSoT pin にする（`design-doc/SKILL.md:99-104`、`design-doc/commands/design-doc.md:34`、`feature-dev/skills/feature-dev/SKILL.md:42` と Phase 3、`issue-design/references/design-rules.md` のルール 5、`issue-design/SKILL.md:105-117`）。pin の適用範囲を広げることを ADR-20260813223000 に追記する（append-only）。pin の打ち直しは bump-version.sh の後に行う。あわせて `design-doc/SKILL.md:101` と issue-design の「決着済みならユーザーに聞かない」に、「衝突は自分で解決しない」という例外を入れる | 高 | 低〜中（検査関数 1 つとテスト。変異テストで効き目を確認） | 正本の :37-50（`6eb4f4c` / #233）が design-doc 版に無い（diff で確認済み）。一方で `design-doc/SKILL.md:40, 250`、`README.md:76`、`CHANGELOG.md:113` は byte 一致の複製だと宣言している。grill の検査は存在しない |
| S3 | feature-dev の Phase 5.3 で、宣言されたオラクルを優先する | `feature-dev/skills/feature-dev/SKILL.md:430-445`（Step 1 で `.claude/review-oracles.sh` があればそれを使い、無ければ今の推測にフォールバックする） | 中〜高 | 低 | 5.3 は package.json からの推測しかしない。self-review は `--embed` のとき機械層をスキップする（確認済み）。そのため、宣言済みのオラクルが feature-dev の中で一度も走らない。この repo には package.json が無いので、5.3 は何も検査せずに通る。宣言を優先する探索順は、issue-workflow の軽量フローに先例がある（`start/references/lightweight-flow.md:28-32`） |
| S4 | feature-dev から self-review への観点の受け渡し | S4a: `feature-dev/skills/feature-dev/SKILL.md:545-557` と `feature-dev/references/triage-guide.md:82-91` に「Issue ファイルか session-context があれば spec-compliance を足す」を追加し、`migration-safety`（`SKILL.md:552`、`triage-guide.md:90, 134, 233`）を `migration` に揃える。S4b（任意）: self-review に `--spec <path>` を足し、feature-dev から BDD spec のパスを渡す（B13 から移動） | 中〜高 | S4a 低 / S4b 中（code-review も変える） | spec-compliance が読むのは session-context / Issue / knowledge だけで、BDD spec は読まない（`spec-compliance.md:5-8`、確認済み）。feature-dev は spec のパスを渡していない（`SKILL.md:560-566`、確認済み）。そのため **S4a の効果は Issue ベースで回すリポジトリ（yatima など）に限られ**、この repo（`.claude/indie` が無い）では効かない。BDD spec と照合するには S4b が要る。focus 名で一致しないのは migration-safety だけ（`code-review/references/prompts/focus/` の一覧と照合、確認済み） |
| S5 | feature-dev の dormant 判定 | `feature-dev/skills/feature-dev/SKILL.md:86, 346` を、spec-advisor と同じ述語（グローバルとプロジェクトの settings を見て、`: true` だけを有効とする。`routing-rubric.md:80`）に揃える | 中 | 低 | 今は `$HOME/.claude/settings.json` にキーがあるかだけを見ている（確認済み）。無効にしたプラグインを有効と誤認し、プロジェクトだけで有効にしたものは見落とす。spec-advisor が #74 で直した誤検知と同じ型。feature-dev の起動は 3 回 |
| S6 | worktree の psql とユーザーの deny の衝突 | `dev-workflow/skills/worktree-setup/SKILL.md:153`、`worktree-teardown/SKILL.md:90-104, 179-180` | 中 | 低 | グローバルの deny `Bash(psql:*)` があるので（確認済み）、DB の作成も drop も実行できない。worktree 系は 0 回なので実害はまだ出ていない。直し方は、deny 下ではコマンドを提示して手動実行を頼む形にするか、deny を見直すか（§8） |
| S7 | discover と start で backlog の扱いが食い違う | `issue-workflow/skills/start/SKILL.md` の D2 に backlog の件数と古い順の数件を出す。または `discover/SKILL.md:191` の記述を直す | 中 | 低 | `discover/SKILL.md:191` は「start ダッシュボードもこの status を集計する」と書いているが、start に backlog は 0 件。artist-portfolio の YAS-29〜32 は 06-29 から backlog のまま（検証者が確認） |
| S8 | bdd-spec の、約束だけで実装の無い記述 | `bdd-spec/skills/create-spec/references/glossary-ssot.md:49` を削るか、「evaluate は検査しない」に直す。yatima の `features/all_spec.md:46` にある同じ記述も、手で直すよう案内する | 中 | 低 | 実装されていない（`bc43d49` の計画が、`55df308` の出荷時に抜けた）。lint を作る案は見送る（実データで一般語が大量に当たる） |
| S9 | issue-design の新規本文モードが backend 無しで止まる | `issue-workflow/skills/issue-design/SKILL.md:46-51`（Phase 0 手順 4）。Phase 0.1 が新規本文と判定したら、DATA_DIR が無くても続けるようにする | 低〜中 | 低 | 手順 4 は backend が無効なら init を案内して終了する（確認済み）。新規本文の設計は DATA_DIR を使わない。spec-advisor は issue-design を提案先に持っているので、backend の無い repo では案内された先で止まる |
| S10 | 実装ブリッジの引数の文言 | `design-doc/skills/design-doc/references/section-guide.md:68`、`template.md:94`、`design-doc/SKILL.md:129` に「BDD spec のパス（あれば）」と明記する（`:166` は既にそうなっている） | 低〜中 | 低 | §3 の裁定を参照 |
| S11 | shared-state の登録簿が古い | `docs/shared-state.md:27` の knowledge の consumers に dev-workflow の diagnose を足す。表に `features/all_spec.md`（producer: bdd-spec、consumer: feature-dev の code-architect）を 1 行足す | 低 | 無し（repo 直下） | 登録されている consumers は issue-workflow だけ（確認済み）。diagnose は knowledge を読み（`diagnose/SKILL.md:22`）、code-architect は all_spec.md を読む |
| S12 | diagnose の candidates 追記の意味のずれ（推測を含む） | `dev-workflow/skills/diagnose/SKILL.md:133` | 低 | 低（A2 と同じ bump） | 自己申告ルールは「このセッション中に自分の誤りを訂正したとき」の記録で（`failure-journal/rules/self-report-rule.md:3`、確認済み）、/retro は Claude の自己訂正として集計する。診断で見つかる作業パターンは、過去の人や別のセッションに由来することもありうる。対象を「このセッションで自分が踏んだもの」に限るか、summary に由来を書く |
| S13 | adr-keeper の必須節の不一致と、id の丸め | `adr-keeper/README.md:37-46`（8 節すべて必須）と `adr-keeper/skills/adr/SKILL.md:157`（「必要に応じて補完」）を揃える | 低 | 低 | 両者の食い違いは確認済み。既存 ADR 9 件のうち 4 件は、id の秒が 00 になっている（ls で確認済み）。`date` で取得せず手で書いた可能性がある（推測） |
| S14 | template-9sections に廃止済みの指示が残っている | `issue-workflow/skills/issue-design/references/template-9sections.md:6-7` | 低 | 低 | 「編集したら両プラグインに同じ内容を反映すること」が残っている（確認済み）。ミラー規約は ADR-20260722164106 で廃止された |
| S15 | living-spec の design doc にある古い判断根拠 | `.claude/designs/20260715-living-spec-workflow.md:351-357` の 4(a) | 低 | 無し | 「linear / indie の両方に対称実装が要る（ミラー規約）＝実装量 2 倍」は、ミラー規約の廃止で成り立たなくなった（確認済み）。存廃の判断材料として直す |
| S16 | push-reminder の誤発火 | `dev-workflow/hooks/scripts/push-reminder.sh:26-27` | 低 | 低 | クォートの中しか除外しないので、heredoc の本文や echo の引数など、クォートの外に `git push` という並びがあると発火する（正規表現は行頭を要求しない、確認済み）。止めはせず、注入が増えるだけ。hook_harness に「黙るべき条件」のテストを足す |
| S17 | CLAUDE.md の vNEXT 規約の重複 | `CLAUDE.md:283` と `:290` を 1 つにまとめる | 低 | 無し | 同じ規約が 2 行ある |
| S18 | （ユーザー環境）旧スキルのコピーとリンク切れ | `~/.claude/skills/` の旧コピー 6 件（claude-code-setup / claude-md-improver / git-commit-helper / pr-creator / pr-review / self-review）と `~/.claude/commands/revise-claude-md.md`。`../../.agents/skills/*` を指すリンク切れ 7 件（chrome-devtools / context7 / frontend-design / seo-audit / skill-creator / vercel-react-best-practices / web-design-guidelines） | 中 | 低 | どれも `~/.claude`（git 管理、origin は yuuki1036/.claude）で追跡されており、マシン間で同期される（確認済み）。旧コピーは OWN と並んで常駐し、名前空間なしの起動（`/self-review`、`git-commit-helper`）を奪っている。evals の runner はインストール済みの環境をそのまま測るので、この影響を受ける。`~/.agents` はこのマシンに存在しない（確認済み）。ユーザー設定の変更なので、実施するかは §8 で判断する |

#### A 群: MP 由来で、安く効くもの

| ID | 要素 | MP 出典 | OWN 着地点 | 価値 | コスト | 根拠 |
|---|---|---|---|---|---|---|
| A1（P11-A01） | 翻案元の MIT 表示 | MP `LICENSE:3, 12-13` | repo 直下に `NOTICE`（MP の著作権表示・許諾文・翻案したファイルの一覧）。各翻案ファイルの冒頭に出典を 1 行（例: 「mattpocock/skills の <skill> を翻案（MIT、repo 直下 NOTICE 参照）」）。一覧は手で書かず、CHANGELOG の翻案の記述と `git grep -i "pocock\|grill-me"` から作る。`docs/skill-writing.md:3` の出典名の更新は A4 と一緒に行う | 高 | 低 | 今回抽出した一覧: `dev-workflow/skills/diagnose/SKILL.md` と `dev-workflow/commands/diagnose.md`（`dev-workflow/CHANGELOG.md:285`）、`docs/skill-writing.md`、`feature-dev/references/grill-protocol.md` と feature-dev SKILL.md の Phase 3（`feature-dev/CHANGELOG.md:226`）、design-doc 版の grill-protocol.md、`issue-workflow/skills/issue-design/references/design-rules.md`（ルール 5 は grill-me 由来 `:51`、ルール 6 は to-tickets 由来 `issue-workflow/CHANGELOG.md:175`）、`issue-workflow/skills/discover/references/rejected-record.md`（同 `:174`）、`adr-keeper/skills/adr/SKILL.md` の 3 条件（`adr-keeper/CHANGELOG.md:34`）。出典の行があるのは `docs/skill-writing.md:3`、2 つの grill-protocol.md の `:3`、`design-rules.md:51`（「"grill-me" に由来」とあるだけで著作権表示は無い）の 4 か所だけ（確認済み）。インストール後の cache に直下の LICENSE は入らないので、配布物に表示が届くのは各ファイル内の 1 行だけ。**各ファイルの 1 行は、S 群・A 群で同じプラグインを bump するコミットに相乗りさせる**（対象 5 プラグインはどれも S 群で bump する予定。§4.5）。これで価値「高」と実施時期が揃う |
| A2（P4-C01〜C03、P11-A06） | diagnose の伏せ字 | MP `skills/engineering/diagnosing-bugs/SKILL.md:12-16, 55, 59`（`efce423` / `bda79a3`、main 反映 08-06）、`scripts/hitl-loop.template.sh:15-16` | `dev-workflow/skills/diagnose/SKILL.md`: `:22` の後に節を足す。`:66` の成果物依頼と `:70` の完了基準に「伏せ字で」を入れる。`:54` の人間参加ループでは観測値だけを貼ってもらい、サインインはユーザー側の手順に残す | 高 | 低 | diagnose に redact 系の記述は 0 件（確認済み）。範囲は MP より広く取る。(1) 対象に cookie と個人情報を含める（MP #674 は OPEN で、#779 より広い範囲を求めている）。(2) 表示だけでなく、残るものにも効かせる。loop スクリプト・harness・回帰テストは環境変数で参照する。コミットメッセージと PR 本文、Phase 6 で journal や Issue に書く文章も対象。OWN の diagnose は failure-journal と issue-workflow に書き出す（`:131-134`）ので、MP には無い永続化の経路がある。dev-workflow は plugin eval を持たないので bump だけで済む |
| A3（P2-C2 + C15 + C19 の一部、P2-C7、P3-C14） | grill の「人間が決める」一般則 | MP `skills/productivity/grilling/SKILL.md:26-28`（`e5932a7`、`0e9a072`。どちらも前回精査の時点で main にあった）、〔docs〕`docs/productivity/grilling.md:64` | feature-dev の grill-protocol.md ①（`:11-17`）、S2 で同期した design-doc 版、`issue-design/references/design-rules.md:55`。追記する内容: (1) 自分で解決してよいのは、事実と、明示的な決定記録（ADR・Issue の決定事項・spec）が問いに直接答えている場合だけ。コードに前例があっても推奨の根拠にとどめ、推奨を添えて聞く。(2) `askUserQuestionTimeout` による自動継続は「おまかせ」と区別し、未決として残す。(3) 「分からない」「他者が決める」問いは推奨で埋めず、未決のまま確定する場所とタイミングを残す（P2-C7。issue-design はルール 1 / 4 を指すだけでよい）。(4) 前提節に「ユーザーの説明がコードと食い違ったら、該当箇所を示してどちらが正しいか聞く」を 1 bullet（P3-C14） | 中 | 低 | OWN の ① は、MP が自問自答の原因として `e5932a7` で書き直した旧文言と同じ形をしている。#233 の例外（`grill-protocol.md:45`）も一般則として包める。S2 が前提になる。design-doc は 6 回、feature-dev は 3 回使われている |
| A4（P8-C01/C02/C05〜C08/C10/C31〜C33、P9-A15、P11-A07） | `docs/skill-writing.md` の再同期 | 下記 (i)(ii) | `docs/skill-writing.md`。`:3` に出典名と MP の基準コミット（`c55ee46`）を記録する。行数はほぼ据え置き | 中 | ほぼ無し（repo 直下の doc なので bump 不要） | **(i) 翻案時の取りこぼし**（`2ab9580` の `skills/productivity/writing-great-skills/GLOSSARY.md` に既にあった、確認済み）: 必須の素材が弱い pointer の後ろにあると結果がばらつく〔variance bug〕（`:39`）。co-location（`:107-109`）。後続を隠す対策は実コンテキスト境界（subagent・新しいセッション）を越える場合にしか効かない（`:157`）ので、OWN `:28` と `:54` を訂正する。sequence を統合したときの逆向きの警告（`:63`）。legwork と demand（`:139-143`）。relevance の 2 経路（`:185`）。no-op はモデル依存で、実行して決着をつける（`:199`）。**(ii) 前回以降に main に入った差分**（release/v1.2、08-05）: 改名と対象の一般化（`1fc6573`）、cache（`f054def`、現行 `writing-for-agents/SKILL.md:79`）、SKILL-MECHANICS への分離。ほかに、完了条件の 1 行（C31〔docs〕）、exemplar の過特化（C32〔docs〕）、剪定は行動の基準で決め長さでは決めない（C33〔docs〕）。予測可能性は MP でも今なお目的なので（`writing-for-agents/SKILL.md:6-7`）、見直さない |
| A5（P5-C3 + C17） | spec-compliance の確信度の付け方と spec 行の引用 | MP `skills/engineering/code-review/SKILL.md:70, 74-87` | `code-review/references/prompts/focus/spec-compliance.md:16, 22`。spec の該当行を引用でき、diff と突き合わせられるスコープ逸脱や設計判断との矛盾は、確信度 95 まで付けてよい。行の引用を必須にする。`scoring-guide.md` の脱落経路の表に「③ 最初から閾値未満」の行を足す（見出しは変えない） | 中 | 低（S4b と同じ code-review の bump） | 確信度の付け方（2026-03 の `6e23c70`）と報告閾値（05-19 の `b67ecc7`）が噛み合っていない。self-review は 60 回使われている |
| A6（P10） | 破壊的な git 操作を確認制にする | 着眼点だけ MP から借りる（MP `skills/misc/git-guardrails-claude-code/SKILL.md:12-16`） | `~/.claude/settings.json` の `permissions.ask` に `Bash(git checkout -- *)`、`Bash(git restore *)`、`Bash(git reset --hard*)`、`Bash(git clean *)`、`Bash(git branch -D *)`、`Bash(git stash drop*)` を足す（ユーザー設定なので、実施はユーザーが判断する） | 中 | 低（コード無し） | 実際の事故は 2 件（`journal.jsonl:44`、`candidates.jsonl:46`）で、どちらも `checkout --`。MP のスクリプトはこの型を素通しする。ユーザー settings に ask ルールは今無い（確認済み）。`Bash(git restore *)` は `git restore --staged` にも確認を出すが、S1 の修正を「何もしない」にすれば正規の手順とは衝突しない。限界: `git -C` などを前に付けるとすり抜ける。dontAsk モードでは確認ではなく拒否になる |
| A7（P10） | notebooklm-workflow の alwaysLoad をやめる | ―（OWN の実測） | `notebooklm-workflow/.mcp.json:6` | 中 | 低（1 行、元に戻せる） | 39 ツールが全セッションで常駐しているが、スキルが使うのは 3 ツールだけ。Skill の起動も MCP の呼び出しも 0 回。chrome-devtools は MCP を直接 24 回呼んでいるので、別に判断する |
| A8（P1-C23 を一般化） | 今回の採否を記録する | MP `.out-of-scope/` の考え方 | 記録は 1 か所にまとめる: `docs/session-reports/2026-09-24-mattpocock-skills-review.md`（repo 直下なので bump 不要）。載せるもの: 基準コミット（前回 `2ab9580`〔推定〕、今回 `c55ee46`）、日付の規則（main に入った日で数える）、§5.2 の区分、見送った理由。living-spec の design doc にはポインタを 1 行置くだけにする | 中 | 低 | 前回の時点で wayfinder・smell リスト・2 軸構成が既に main にあったのに、見送った記録が OWN のどこにも無く、今回また同じ評価をした。ADR にはしない。adr-keeper の 3 条件の①「覆すコストが大きい」を満たさない（方針は次回の精査でいつでも覆せる）。次回は `git log --first-parent c55ee46..main` から始める |

#### B 群: 中程度（コストが中くらい、または対象の利用頻度が低いもの）

| ID | 要素 | MP 出典 | OWN 着地点 | 価値 | コスト | 根拠 |
|---|---|---|---|---|---|---|
| B1（P4-C05, C09, C13, C14） | diagnose の残り | MP `ee8bae4:49, 132`、MP #124（OPEN） | `dev-workflow/skills/diagnose/SKILL.md`。`:66` に core dump と「本番 / 再現環境への計装」を足す。`:129` に PR 本文を足す。`:111` の Phase 4 完了時に、確証した仮説・原因の file:line・修正方針を**提示して待たずに進む**（止めるのは起動時に頼まれた場合だけ。止めて待つ形にするなら、command と skill の両方の allowed-tools に AskUserQuestion が要る）。`:29` の Phase 0 の「使う」を「以前より遅くなったという症状がある劣化」と肯定形で締める | 中 | 低（A2 と同じ bump） | 翻案で落ちた部分と、MP でも未実装の確認ゲートの非ブロッキング版 |
| B2（P2-C1 + C10、P11-A05b） | grill で、前提の決まった問いをまとめて聞く | MP `skills/productivity/grilling/SKILL.md:8, 24`（`a4b2009`、main 反映 08-05）、〔docs〕`docs/productivity/grilling.md:31, 45-52` | feature-dev の grill-protocol.md の ②（`:19-25`）と複製、`feature-dev/SKILL.md:42` と Step 4、`design-doc/commands/design-doc.md:34`、issue-design の effort 分岐。前提が決まった問いは、AskUserQuestion 1 回で最大 4 問まで聞く。「CLAUDE.md が 1 問ずつを指示していればそれに従う」を 1 行添える。事実調査を subagent に任せる部分は取り込まない | 中 | 中（3 プラグインの bump） | S2 が前提。OWN にも 1 回で複数問を聞く前例がある（`code-review/skills/self-review/SKILL.md:485`）。MP 自身も 1 問ずつへの opt-out を正式に支えている |
| B3（P2-C3、feature-dev のみ） | grill の後の確認 | MP `skills/productivity/grilling/SKILL.md:28`（`0e9a072`） | `feature-dev/skills/feature-dev/SKILL.md:302-304`。Step 5 の設計契約を最後の問いのラウンドに 1 問相乗りさせて確認し、そのあと architect を起動する（ユーザーが決めた事項が 0 件なら省く） | 中 | 低 | architect（opus、最大 3 体）を起動する直前に、理解のずれを止められる |
| B4（P7-C1 / C2 / C7 / C8 / C9 / C10 / C23、P11-A18） | テストの規律と設計の語彙 | MP `skills/engineering/tdd/SKILL.md:18-38`、`tests.md`、`mocking.md`、`skills/engineering/to-spec/SKILL.md:15-17`、`skills/engineering/codebase-design/SKILL.md:16`、`DEEPENING.md:5-25`、〔docs〕`docs/engineering/tdd.md:61-63` | `feature-dev/references/testing-discipline.md` を新設し、Phase 5 の Normal Mode（`SKILL.md:390-402`）から Read させる（テスト基盤があるときだけ）。`feature-dev/references/module-design.md`（40 行程度）に語彙と 4 原則、interface の定義（C8）、依存の 4 分類（C10）をまとめ、clean-architecture focus の定義（`SKILL.md:314`、`triage-guide.md:72`）から参照する（C7。design-doc への複製は同期検査を入れてからにする）。architect の比較軸に depth・locality・seam 配置を足す（C9。新しい focus は作らない）。Test Seams 節を `code-architect.md:105-116` に足す | 中〜高 | 低〜中 | Phase 5 にはテストの指示が 1 行も無い。トートロジーの項は OWN の `docs/testing-pitfalls.md` §3 を正本にする。GitHub issue #89（保留中）との役割分担を明記する |
| B5（P7-C6） | test-quality にアンチパターン名を書く | MP `skills/engineering/tdd/tests.md:25-77` | `code-review/references/prompts/focus/test-quality.md:5-10`。起動条件を広げるのは「新しいソースファイルがあり、テストの変更が 0」の場合だけにする（`code-review/references/triage-guide.md:120` と `feature-dev/SKILL.md:549` を対で直す） | 中 | 低〜中 | 重大度の目安と起動条件が食い違っている |
| B6（P3-C08 / C10 / C11 / C12、P6-C14） | ADR まわり | MP `skills/engineering/domain-modeling/ADR-FORMAT.md:39-47`、`skills/engineering/setup-matt-pocock-skills/domain.md:47-51` | 7 類型を `adr-keeper/skills/adr/references/examples.md` に書く。「読んだ ADR と矛盾するなら明示する」を diagnose の `:22` と grill-protocol の `:43` に入れる。ADR の 3 条件ゲートを、design-doc の Phase 6 経由なら免除する。feature-dev の grill 終了時の要約で、3 条件を満たす判断を「ADR 候補」として並べる（0 件が普通。adr-keeper が未導入なら何も出さない。C11）。issue-create の Phase 5.5 で、提示した ADR と矛盾する内容を書くなら明示する 1 行（P6-C14） | 中 | 低 | ADR はこの repo に 9 件、yatima に 6 件ある |
| B7（P6-C03 / C04a / C16 / C09 / C19） | Issue 系の規範 | 〔docs〕MP `docs/engineering/to-tickets.md:61-62, 76-77`、MP `skills/engineering/to-tickets/SKILL.md:23`、〔docs〕`docs/engineering/to-spec.md:26-28`、`skills/engineering/triage/SKILL.md:70` | 草稿と同じ（discover / template-9sections / design-rules / issue-create / plugin-feedback） | 中 | 低 | 242 件のうち 95 件が plugin-feedback 経由 |
| B8（P8-C30 / C04） | CLAUDE.md の常駐量を減らす | MP `skills/productivity/writing-for-agents/SKILL.md:24-27, 39` | 特定の作業でしか使わない節を docs/ に移し、ポインタだけ残す。skill-writing の対象を rules / agents / prompts / CLAUDE.md に広げる | 中 | 中 | 事故から生まれた Gotchas は残す |
| B9（P3-C06） | wait-what の日本語版をユーザーコマンドにする | MP `skills/productivity/wait-what/SKILL.md:1-7` | `~/.claude/commands/` に `disable-model-invocation: true` で置く | 中 | 低 | repo の外なので OWN の不採用方針の対象外。数回試してから決める |
| B10（P9-A8 + A9） | 引き継ぎの形式化 | MP `skills/productivity/handoff/SKILL.md:8-16`、〔docs〕`docs/productivity/handoff.md:59-60` | 1 台で `npx skills add mattpocock/skills --skill=handoff` を試す。定着したら、「確認済み / 未検証」の区分を持つ薄いコマンドに翻案する | 中 | 低 | 未検証の断定を格下げする規則は MP でも docs にしか無い。横道への fork は CC 組み込みの `/fork` で足りる。**注意:** global に入れた skills CLI 系のスキルは、このマシンで既に `~/.agents/skills` へのリンク切れになっている（S18）。複数マシンで使うとずれたり壊れたりしうる（推測） |
| B11（P9-A2 + A4 修正版） | failure-journal の還流先の分類 | MP `skills/in-progress/retro/SKILL.md:18`（`0243b6e`） | `failure-journal/skills/retro/references/aggregation-rules.md:86-108` | 中 | 低 | 先に、候補の昇格が止まっている原因を調べる |
| B12（P5-C10 / C9 / C8 / C11） | pr-creator の証跡 | MP `skills/in-progress/pr/SKILL.md:21-33, 39-154, 156-168` | 草稿と同じ | 中 | 低 | 出典は in-progress。Summary の書式は Humanlayer の show-me を「ほぼ逐語」で取り込んだもの（MP `skills/in-progress/pr/CREDITS.md`、確認済み）で、show-me のライセンスは確認できていない。考え方だけを借り、文面は転載しない |
| B13（P5-C2 限定 / C4 / C5 最小 / C15） | review の仕様ソースとレポート | MP `skills/engineering/code-review/SKILL.md:25-36` | review（PR）経路で、PR 本文とコミットの `Closes #N` を gh で 1 段だけ取得する（信頼できない入力として扱う）。spec ソースがある回は 3 枠目を spec-compliance に優先して割り当てる。レポートに仕様整合の 1 行を足す。規約ソースとして CONTRIBUTING.md と CODING_STANDARDS.md を「あれば読む」。`--spec` は S4b に移した | 中 | 中 | 先に `triage-guide.md:107` と `orchestration-measurement.md:330` の食い違いを解消する |

#### C 群: 条件付き、または利用頻度の低い対象

| ID | 要素 | 条件 / 着地点 | 価値 | コスト |
|---|---|---|---|---|
| C1 | living-spec の散文の改善（§2.6） | 存廃の判断で残すと決めた場合だけ | 中 | 低 |
| C2（P1-C10、P8-C17） | spec-advisor に living-spec の軸を足す | 残して 1 回使った後。提案先の一覧が約 7 か所に複製されているので、正本に寄せてから runner の回帰を回す | 中 | 中 |
| C3（P7-C5 修正版） | feature-dev に `design=` の入口を作る | 既存の feature_dev_plan の baseline 経路で受ける。Phase 3 は前提確認だけにする | 中 | 中 |
| C4（P6-C01 + C17） | 設計書から Issue をまとめて起票する | issue-create の利用は 1 回。description を変えるので回帰テストが要る。分割元の親 Issue は候補から外す | 中 | 高 |
| C5（P8-C21 + C22） | フェーズ境界の判断 | `feature-dev/skills/feature-dev/SKILL.md:393-397` に 1〜2 行。約 150k という数値は書き写さない | 低 | 低 |
| C6（P8-C29） | トリガー語の剪定 | 次にそのスキルを触るときに行う。living-spec は 18 語、ui-verify は 12 語 | 中 | 中 |
| C7（P11-A02、P10、P2-C8） | MP スキルを個別に試す | tdd と codebase-design は組にする。そのほか resolving-merge-conflicts、wizard、to-questionnaire、teach。対象のプロジェクトに skills.sh で入れる。`scripts/link-skills.sh` は使わない（in-progress の retro / pr まで入る）。claude-plugins では行わない。**wizard の範囲決めは、ユーザーの deny `Read(.env.*)` のため `.env.example` を読めない一方、`.env` 本体は読める（確認済み）。** 保護の向きが逆なので、範囲を workflows の `secrets.*` / `vars.*` 参照とユーザーが示すキー名に限るよう指示する。deny の見直しは §8。merge はグローバルの deny `Bash(git rebase:*)` にぶつかる | 中 | 低 |
| C8（P9-A1 / A7 / A14、P8-C03 / C14） | claude-meta の束（1 回の bump にまとめる） | revise-claude-md の振り分け。claude-md-improver に「挙動を変えない行」の判定と cache の注記を足す（why や実例は除外）。component-addition-advisor に「新しい description は常駐の context load になる」分割基準を 1 項。claude-code-setup の Phase 1 に「guardrail が無い」「配線されていない検査がある」の検出を足す。plugin eval の鮮度ゲートに掛かる（約 1.5〜3 USD。変更と関係ないケースなら `PLUGIN_EVAL_SKIP=1` で迂回し、コミット本文に書く）。三段防御との方針衝突は §8 で判断する | 中 | 中 |
| C9（P10、P5-C18） | 再委譲のガード | `docs/pipeline-design.md` の原則 5 に 1〜2 行。code-review のプロンプトには、他の改修と一緒のときに 1 行足す | 低 | 低 |
| C10（P3-C01 / C03 最小形） | 用語集の読み取り側だけを入れる | feature-dev の grill 前提節に「all_spec.md があれば、別名禁止語が使われていたら指摘する」を 1 行。diagnose `:22` の読み先に all_spec.md を加える（無ければ黙る）。§8-6 の判断が前提 | 低 | 低 |
| C11（P6-C12） | Phase 0 の同期検査 | 同じ backend 検出ブロックを持つ 10 ファイルをマーカー区間にし、routing-axes と同じ方式で byte 比較する | 低 | 低〜中 |
| C12（P7-C13） | discover の観点 D の tie-breaker | 観点 D（テストの欠落）の優先順位付けにだけ git log のホットスポットを使う。バグ兆候の走査範囲は絞らない | 低 | 低 |

#### 4.5 実施計画（プラグイン単位で bump をまとめる）

| 着地点 | 含める項目 | ゲート |
|---|---|---|
| repo 直下（bump 不要） | A1 の NOTICE、A4、A8、S2 の検査コードと ADR 追記、S11、S15、S17、B8、C9 | pre-commit / CI。S2 は変異テストで効き目を確かめる |
| dev-workflow | S1、S6、S16、A2、B1、S12、B12、A1 の出典行 | bump + CHANGELOG（plugin eval なし） |
| feature-dev | S2（正本の汎用化）、S3、S4a、S5、A3、B2、B3、B4、B6 の一部、C10 の一部、A1 の出典行 | bump + CHANGELOG |
| design-doc | S2（複製の同期と pin）、S10、A3 の複製、B2 の該当箇所、A1 の出典行 | bump + CHANGELOG |
| issue-workflow | S7、S9、S14、A3（ルール 5）、B2（effort 分岐）、B6（issue-create 5.5）、B7、C11、C12、A1 の出典行 | bump + CHANGELOG |
| code-review | A5、S4b、B5、B13、C9 の 1 行 | bump + CHANGELOG（S4b は feature-dev と同時に出す） |
| adr-keeper | S13、B6、A1 の出典行 | bump |
| bdd-spec | S8 | bump |
| claude-meta | C8 の束 | bump + plugin eval の鮮度ゲート（実行するなら事前に概算を示す） |
| failure-journal / plugin-feedback / notebooklm-workflow | B11 / B7 の重複検索 / A7 | それぞれ bump |
| living-spec-workflow / spec-advisor | C1 / C2（存廃の判断の後、条件付き） | bump。description を変えるなら runner の eval |
| ユーザー設定（`~/.claude`） | A6、S18、B9、§8-10 の `.env` の扱い | 実施するかはユーザーが判断する |

---

### 5. 前回の翻案が古くなっている箇所（drift）

#### 5.1 取り込み済み要素の drift

| 前回取り込んだもの | OWN の場所 | 前回の時点で既にあった（見落とし） | 前回以降に main に入った変化 | 対応 |
|---|---|---|---|---|
| grill-me → grill-protocol（`dc5dd95`、06-03） | feature-dev の grill-protocol.md、design-doc の複製、`issue-design/references/design-rules.md` ルール 5 | 事実と決定の分離（`e5932a7`、main 07-06）、grill 直後の確認ゲート（`0e9a072`、main 07-03） | frontier ラウンド（`a4b2009`）、書式の固定（`294a2c9`〜`1495d01`、`85f83d3` は 08-20）、wayfinder の grilling ticket から「1 問ずつ」を削除（`38d62e7`）。`85f83d3` 以外は main 反映 08-05。07-29 時点の grilling はまだ「one at a time」だった（`2ab9580` で確認済み）。OWN 内部でも design-doc 版が #233 の分だけずれている | S2 → A3 → B2 / B3 |
| writing-great-skills → `docs/skill-writing.md`（`6683612`、07-29） | `docs/skill-writing.md` | GLOSSARY にあった variance bug・co-location・コンテキスト境界の条件・legwork・relevance・モデル依存の no-op（A4 の (i)） | 改名と対象の一般化（`1fc6573`）、cache（`f054def`）、SKILL-MECHANICS への分離。どれも main 反映は 08-05。07-29 時点の main は改名前だった（確認済み） | A4 |
| diagnosing-bugs → diagnose（`7b189bf`、07-29。翻案元は MP `ee8bae4` の 06/17 版） | `dev-workflow/skills/diagnose/SKILL.md` | 翻案時に core dump・本番・PR が落ちた（MP `ee8bae4:49, 132`） | Redact 節（`efce423` / `bda79a3`、main 08-06）、post-mortem の引き渡しを削除（`1dab982`、main 08-15。OWN はスキルを呼ばずに提案するだけなので追随不要） | A2 / B1 |
| domain-modeling「Offer ADRs sparingly」→ 3 条件ゲート（`02564d4`） | `adr-keeper/skills/adr/SKILL.md` | 「What qualifies」の 7 類型 | description の拡張（`bd8e81b` ほか、main 08-13） | B6 |
| triage の .out-of-scope → `kind: rejected`（`253fc8f`） | `issue-workflow/skills/discover/references/rejected-record.md` | ― | 実質的な変化なし。OWN 側の実運用も 0 件 | 手を加えず、記録がたまるか様子を見る |
| to-tickets の縦切り → ルール 6（`253fc8f`） | `issue-design/references/design-rules.md:61-74` | blocking edge、prefactor、1 スライス = 1 コンテキスト、integration branch | 〔docs〕docs の改稿（`c33ce1c`、main 08-05） | B7 |

#### 5.2 前回の時点で既にあった要素と、前回以降に入った要素

| 区分 | 要素 |
|---|---|
| 07-29 時点の main（`2ab9580`）に既にあった。前回、比較の記録が残っていない | wayfinder（`639df6e`、main 07-08）。code-review の 2 軸と Fowler の smell 基準線（`cac4704` / `0894b33`、main 06-30）。grilling の `e5932a7` / `0e9a072`。tdd / codebase-design / improve-codebase-architecture / prototype / research / resolving-merge-conflicts / ask-matt。domain-modeling の CONTEXT.md 用語規律。writing-great-skills の GLOSSARY の各項目。handoff / teach。in-progress のベータ（wizard・to-questionnaire は利用者起動、claude-handoff、loop-me、batch-grill-me）。misc への降格（`7efc3d2`）。deprecated / personal の 6 本（すべて `2ab9580` のツリーで確認済み） |
| 前回以降に main に入った | 08-05: release/v1.2（PR #593 `b405fe0`。writing-for-agents への改名と cache、grilling の frontier ラウンドと書式、wayfinder の「1 問ずつ」削除、to-questionnaire の昇格）、wizard の昇格（`b3376f8`）と model-invoked 化（`61accb0`）、wait-what（`355fa74` / `50777fc`）、PHASE-BOUNDARIES（`fa1e322`）、docs の FAQ 化（`c33ce1c`）、6 本の削除（`c66bdee`）。それ以降: Redact（08-06）、domain-modeling の description 拡張（08-13）、post-mortem の削除（08-15）、em-dash の除去（08-19）、書式の追加修正（`85f83d3`、08-20）、implement-spec（`84b5ee5`、08-21）、retro（`8fa1886` 08-24、`0243b6e` 09-15）、pr（`d75dcf1`、09-17） |

#### 5.3 MP の廃止判断から得られる教訓

- **使っていないものは、後継を明記して削除する**（`c66bdee`）。deprecated / personal の 6 本を削除し、後継は changeset に書いた。削除の理由は「使われていない」ことと、obsidian-vault については「作者個人のパスを直書きしたうえでモデル起動になっていて、他人の環境でも発火しうる」こと（コミットメッセージで確認済み）。§8 の存廃判断の前例になる。
- **発火がまれな還流は消す**（`1dab982`）。OWN の diagnose Phase 6 の還流と、`kind: rejected`（実運用 0 件）にも同じ問いが当てはまる。
- **実験は本体に吸収してから消す**（`a4b2009` が batch-grill-me を grilling に吸収）。
- **改名には alias を残さない**（MP `CHANGELOG.md` 1.2.0）。OWN の `_superseded_by` による自動移行のほうが利用者にやさしい。

---

### 6. 置き換え・丸ごと導入について

#### 6.1 勧めない理由

0. **名前の衝突は、MP と関係なく既に起きている**（S18）。`~/.claude/skills` の旧コピー 6 件と `~/.claude/commands/revise-claude-md.md` が OWN と並んで常駐し、名前空間なしの起動を奪っている。MP を同居させれば、この問題がさらに広がる。
1. **個別に止められない。** プラグインのスキルは skillOverrides の対象外。MP のモデル起動スキル 11 件（description 合計 2,194 字）のうち、4 件は OWN と起動条件が重なる。
2. **名前の衝突。** MP の code-review は、CC 同梱の `/code-review` とも OWN とも紛らわしい。MP 自身が、この衝突は未解決だと書いている（MP `docs/engineering/code-review.md:50-52`）。
3. **状態の置き場が二重になる。** MP が生成する `docs/adr/*.md`・`CONTEXT.md`・`docs/agents/*.md` は、doc-freshness の全体走査で frontmatter 欠落の error として拾われる（`doc-freshness/skills/doc-freshness/SKILL.md:49, 84-88`）。
4. **前提になる setup。** setup が英語のブロックを書くのは、書く前に編集できるので「衝突」ではなく「手間」。setup が必須依存になっているのは to-spec / to-tickets / triage の 3 件（MP `.agents/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md:7`）。Linear は「Other」扱い（MP `.out-of-scope/mainstream-issue-trackers-only.md`）。
5. **OWN との結合が切れる。** MP の code-review を使うと review:completed が publish されない。
6. **MP の既知の不具合。** code-review の再帰起動が未修正（MP `docs/engineering/code-review.md:54-56`）。未コミットの変更を見ない（同 `:74-76`）。implement が名前空間なしでスキルを指示している（MP `skills/engineering/implement/SKILL.md:9, 13`）。
7. **更新の仕組み。** 公式に掲載される版は sha が固定され、main より遅れる。in-progress はプラグインでは届かない。
8. **言語。** MP はすべて英語。

#### 6.2 部分的に勧めるもの

- **個別に入れる（C7、B10）:** skills.sh でスキル単位に入れれば、OWN の保守は増えない。注意点:
  - 既定の書き込み先はプロジェクト（MP `README.md:68`）。
  - global に入れた skills CLI 系のスキルは、このマシンで既に `~/.agents/skills` へのリンク切れになっている（S18、確認済み）。複数マシンでは同じ壊れ方をしうる（推測）。
  - 試すなら 1 台に限り、S18 の掃除を先に済ませる。
- **claude-handoff は不要。** CC 2.1.280 の組み込み `/fork` で足りる（確認済み）。
- **MIT は翻案を許しているので、価値のある差分は翻案で取り込める**（A1 で表示を入れる）。

#### 6.3 利用頻度から見た OWN 側の存廃（このマシン、88 日）

| 区分 | スキル（起動回数） |
|---|---|
| よく使われている | code-review:self-review 60（49 セッション）、plugin-manager:update-all 70（**うち 69 回は `~/.claude` の 1 つの長寿命セッション（07-23〜09-20）に集中**していて、広く使われている証拠ではない。確認済み）、writing-polish 13、issue-workflow:start 9、failure-journal:retro 7、design-doc 6、design-review 5、dev-workflow:pr 5、dev-workflow:commit 5（名前空間付きだけ） |
| 少し使われている | adr 4、plugin-feedback 4、component-addition-advisor 4、knowledge-lint 4、issue-maintain 4、feature-dev 3、issue-design 1、issue-create 1、comment-polish 1 |
| 0 回（Skill の起動） | living-spec / living-spec-maintain、dev-workflow:diagnose、bdd-spec（2 件）、spec-advisor、discover / maintain / retrospective / follow-up / dashboard / init / linear-maintain、log-failure、review / review-guide / review-triage、ui-verify（chrome-devtools MCP の直接呼び出しは 24 回）、worktree-*、eval-runner、doc-freshness、notebooklm（MCP も 0 回） |
| Skill の起動回数に出ない稼働（hook 経由。未計測） | failure-journal の自己申告（candidates: claude-plugins 74、yatima 11、knowleadge 11。確認済み）、doc-freshness の frontmatter-guard / stale-check、guardrail-protect、spec-advisor の常駐ルール |
| 集計から外したもの | 名前空間なしの git-commit-helper 12 回（`~/.claude/skills` の旧コピーに解決される）、名前空間なしの self-review 3 回（同）、名前空間なしの knowledge 10 回（すべて knowleadge プロジェクトの `.claude/commands/knowledge.md`。確認済み） |

セッションの 97% は claude-plugins 自身で、ほかのプロジェクトでの実利用は yatima に偏っている。

存廃の候補（別マシンのデータを確認してから決める）:
- **notebooklm-workflow:** Skill も MCP も 0 回なのに、39 ツールが常駐している。最低でも A7 は入れる。
- **living-spec-workflow:** §2.7 の順序で判断する。
- **spec-advisor:** 直接の起動は 0 回。ただし SessionStart でルールを注入しているので、hook 経由で効いている可能性がある。
- **bdd-spec:** 直接の起動は 0 回。yatima の all_spec.md は 1 コミット以降、更新されていない。

MP に置き換えれば解決する存廃の問題は無い。

#### 6.4 ペアで正面から比べていなかった OWN スキルの簡易比較

| OWN | 近い MP の要素 | 判定 |
|---|---|---|
| claude-meta:claude-code-setup | setup-matt-pocock-skills、misc の git-guardrails / setup-pre-commit | 役割が違う（OWN は推奨を出し、MP は規約ファイルを生成する）。MP retro の「guardrail が無いこと自体を所見にする」は、claude-code-setup の Phase 1 に移せる（C8） |
| doc-freshness | writing-for-agents の cache / relevance（考え方だけ） | MP には鮮度を機械的に検出する仕組みが無く、MP 自身の docs が SKILL.md と食い違っている例が複数ある（冒頭の注記）。OWN の強み |
| dev-workflow:git-commit-helper | implement の「現在のブランチに commit」（MP `skills/engineering/implement/SKILL.md:15`）、resolving-merge-conflicts | MP には原子性を重視したコミット分割が無い。OWN を維持し、S1 を先に直す |
| issue-workflow:dashboard / linear-maintain | wayfinder / to-tickets の frontier | dashboard は Linear 専用で、local の backlog は表に出ない（S7）。frontier と blocked_by は見送る（§7） |
| plugin-manager:update-all、claude-meta:cc-catch-up、eval-runner | 無し（MP は changesets と `npx skills update`） | OWN 固有 |

---

### 7. 見送り表

| 要素（元 ID） | 見送る理由 |
|---|---|
| OQ の類型列・依存列・frontier の算出（P1-C05 / C06）、Issue の blocked_by・frontier・claim（P1-C21、P6-C02 / C24） | 表のヘッダは完全一致で判定しているので、スキーマを変えると段 1 が Critical になる（`format-spec.md:69`）。価値が出るのは並列で claim する運用のときだけ。実 Issue 25 件で依存関係の記述は 0 件。frontier / claim は MP でも wayfinder 専用の操作 |
| research 型 OQ の subagent 化、grill 中の非同期調査、explorer のメモの外部ファイル化（P1-C07、P2-C5、P7-C20） | Opus 5 世代の委譲過剰を招く足場になる |
| 決定の影響範囲の洗い出し（P1-C14） | 中核部分は OWN に既にある（`living-spec/SKILL.md:256, 289`） |
| map を index にして store にしない分割、Notes 節、tracker を置き場にする（P1-C16 / C24 / C25） | 「情報を move しない」という OWN の原則とぶつかる。Notes は MP でも穴として報告されている |
| 1 セッション 1 OQ（P1-C15）、start に living spec の要約を出す（P1-C22） | 並列運用が前提で、living spec は 0 件 |
| prototype（P1-C20、P7-C16 / C17 / C18）、ICA の深化候補サーベイ（P7-C12 / C14）、境界 lint（P7-C15） | 新しいコンポーネントが増え、需要の証拠が無い。C13 だけは tie-breaker として採る（C12） |
| 書式の固定、単体の入口、proportionality の撤廃、成功基準、README の失敗モード、description に grill を入れる（P2-C4 / C9 / C11 / C12 / C13 / C14） | AskUserQuestion が構造を担っている。C11 は出典の読み違い |
| to-questionnaire の翻案（P2-C8） | 送る相手がいない。必要なら C7 で単体で入れる |
| 用語集の作り手側の規律（P3-C01 の書き込み側）、消費サイト 6 か所への展開（P3-C03 の全面展開）、writing-polish への用語集連携、lint、パーサ、決着の履歴、マルチコンテキスト、ブートストラップ（P3-C05 / C15〜C19） | all_spec.md は 1 コミット以降更新されていない。`subkind: glossary` は 0 件。読み取り側の最小形だけ C10 で採る |
| 場面で概念の境界を揺さぶる技法（P3-C13） | §3 の裁定を参照 |
| ADR の最小形、Update 節での追記、adr の遅延作成、編集トリガー（P3-C09 / C22 / C20 / C21） | 実際の ADR 15 件はすべて完全な形で書かれている。追記のみの原則とぶつかる |
| HITL テンプレートの同梱（P4-C04） | 非 TTY では `read` が rc=1 ですぐ終わる |
| 段階的に重くする、description の否定形、否定の eval、README の表、DEBUG hook、MCP 連携、openai.yaml（P4-C06 / C07 / C08 / C10〜C12 / C15〜C17） | diagnose の利用は 0 回。否定形は OWN の規約に反する |
| 軸ごとのサマリ（P5-C6） | B13 のレポートの 1 行に吸収する |
| Fowler の smell リスト（P5-C7、P7-C21、P11-A21） | CC 組み込みの `/simplify` と重なる。Spec 軸は OWN に既にある |
| PR の読み順、ADR との矛盾の明記、用語を PR に揃える、Left out の独立節（P5-C12 / C13 / C14、P5-C11 の独立節化） | MP の作者自身が削った。Left out は B12 の定型文にとどめる |
| guardrail 不在の通知、収束しないことの注記（P5-C16 / C19） | lint は指摘の約 43% を占めるので、通知が鳴りっぱなしになる。ADR-20260817170000 に反する。（P9-A7 はここではなく C8 で採る） |
| 長く寝かせる Issue に brief の原則、冪等キー、再現検証、委譲の可否マーカー（P6-C06 / C07 / C08 / C10） | 既に満たしているか、使われる場面が無い |
| GitHub backend、soft 依存の一般化、横断的な用語、needs-info、AI 生成の注記、snippet 例外、外部 PR、repo ローカルの triage（P6-C11 / C21 / C23 / C25 / C26 / C20、P6-C14 の用語部分） | backend が増える保守負担。本人と bot しかいない repo では triage の前提が成り立たない。soft 依存は issue-design の 1 例だけ S9 で直す。Phase 0 の同期は C11、ADR との矛盾は B6 で採る |
| red→green ループへの組み替え、focus の新設、テストの置き換え、implement-spec、グラフ並列、自動コミット、タイトルの復唱（P7-C3 / C11 / C19 / C24 / C28、P7-C9 の focus 新設部分） | B4 の参照文書で足りる。比較軸の追加は B4 で採る |
| tdd-phase-gate の seam 対応（P7-C25） | 有効化のフラグが 0 件 |
| disable-model-invocation の部分採用（P8-C15、P11-A04） | 節約できるのは約 1.2k 字だけで、自然言語による起動を確かめている eval を失う |
| 呼び出し表記の規約化、新しい validate、gloss の Read、境界の書式、フローマップ、配布スキル化、エージェント向けの推敲、grounding、記事執筆、README の 4 節、Negation の一括監査、失敗モード表の分散（P8-C16 / C18 / C19 / C20 / C23〜C28 / C12 / C13） | 表記は既に揃っている。利用者は本人 1 人 |
| reviewer 層を 4 層目にする、失敗の対象を摩擦に広げる、単発の retro、英語サルベージ、Tool economy の計測、loop-me とその語彙、suggested skills、`/compact` の指示（P9-A3 / A5 / A6 / A19 / A20 / A17 / A18 / A11 / A13） | 上位の失敗タグは diff に現れない型。候補のレビューが既に詰まっている |
| background への fork（P9-A10） | CC の組み込み `/fork` で足りる |
| MP の git ガードをそのまま入れる、push を全面ブロックする（P10） | 偽陽性・偽陰性があり、jq が無いと素通りする（実測）。pr-creator の正規の手順が壊れる |
| research → knowledge ほか（P10 の各候補） | 主な作業 repo に knowledge の書き先が無い |
| grill の frontier 化のうち、事実を subagent に調べさせる部分（P11-A05c） | 委譲過剰になる |
| 変更を切り替えて比べる eval（P11-A03） | runner にプラグインを切り替える仕組みが無い。丸ごとは入れないので不要 |
| docs の 4 節化、ルーター、ベータチャネル、repo 直下の .out-of-scope、changesets、em-dash 禁止、`--strict`、Codex 対応、分岐の表記規約、用語集（P11-A08 / A10〜A17 / A22） | 17 プラグインぶんの bump が要る。利用者は 1 人。`--strict` は実測で常に失敗する |

---

### 8. 不確実な点と、ユーザーに決めてもらう必要があること

#### 決めてもらう必要があること

1. **living-spec-workflow を残すか**（§2.7 の (a) / (b) / (c)）。順序は「別マシンで集計 → 存廃を決める → (a)」に固定する。集計スクリプト（`analyze_usage.py`、`build_report.py`）は今このセッションの scratchpad にしか無い。`docs/session-reports/`（A8 の記録と同じ場所）か、review metrics と同じ secret gist に移すかを決める。
2. **notebooklm-workflow を残すか。** 最低でも A7 は入れてよいか。
3. **grill の既定を「1 問ずつ」（issue #3）にするか、「前提の決まった問いを最大 4 問ずつ」（B2）にするか。**
4. **三段防御と MP の「CLAUDE.md は pointer 専用」のどちらを優先するか**（`claude-meta/skills/claude-md-improver/references/three-tier-defense.md:3-13` と MP `skills/in-progress/retro/SKILL.md:41`）。B8 と C8 の範囲がこれで決まる。
5. **破壊的な git 操作の確認をどこで行うか**（A6 の permissions.ask か、hook への昇格か）。範囲も決める。
6. **用語の正本を all_spec.md に一本化し、`subkind: glossary` と knowledge-lint の項目 9 をやめるか**（C10 の前提）。
7. **B4 と GitHub issue #89 の役割分担。**
8. **MP スキルを個別に試すか**（C7、B10）。試すならどのマシンのどのプロジェクトにするか。S18 の掃除を先に行う。
9. **`~/.claude/skills` の旧コピー 6 件と `commands/revise-claude-md.md` を撤去し、リンク切れ 7 件を掃除するか**（S18）。`~/.claude` は git で管理しているので、他のマシンにも反映される。
10. **`.env` の読み取りをどう扱うか。** 今の deny は `Read(.env.*)` だけで、`.env.example` は塞ぐのに `.env` 本体は塞がない。`Read(.env)` を deny に足すか、`.env.example` を許可するか。同様に、`Bash(psql:*)` の deny と worktree 系（S6）をどう両立させるか。

#### 不確実な点

- 利用頻度は 1 台のマシン、88 日分だけ。hook 経由の稼働は数えていない。
- 前回精査の基準を MP main の `2ab9580` とみなしたのは推定。前回どの ref をクローンしたかの記録は無い。
- MP と同居させたとき、名前空間なしの `/code-review` がどこに解決されるか。一次ソースどうしが食い違っている。
- self-review が語彙に無い観点名（`migration-safety`）をどう扱うか。黙って落としているというのは推測。
- 日本語の発話で、MP の英語の description が OWN より先に選ばれる頻度。
- 翻案が MIT の「substantial portions」に当たるかどうか（法的な判断）。表示を置く費用は小さいので、置く側に倒す。
- MP の pr が取り込んでいる Humanlayer の show-me のライセンスを確認できていない。B12 では文面を転載しない。
- skills.sh で user スコープに入れられるか。このマシンのリンク切れが skills CLI の global インストールと同じ仕組みで生じたものかどうか（推測）。
- diagnose `:133` の意味のずれ（S12）は推測を含む。
- PreToolUse の hook が返す `"ask"` を auto mode でどう扱うか（permissions.ask の扱いは docs で確認済み）。
- failure-journal の候補の昇格が 08-30 以降止まっている原因。
- Linear MCP で親子関係や blocking を作れるか（C4 を採る場合だけ関係する）。
- AskUserQuestion で 1 回に複数問を出したときの CLI での表示。

---

### 批評で採らなかった点

- main に入った日を「07-31」とした点: 実際に main に入ったのは 08-05（release/v1.2 を取り込んだ PR #593、`b405fe0`）。07-31 はリリースブランチ上の committer date。「07-29 時点で main に無い」という結論は採った。
- 名前空間なしの `knowledge` 10 件を OWN の可能性が高いとした点: 10 件すべてが knowleadge プロジェクトの中で、`/Users/yuki/Projects/knowleadge/.claude/commands/knowledge.md` がある。プロジェクトローカルのコマンドなので、集計から外したままにした。
- feature-dev の dormant 判定と psql の衝突を最上位に置く案: 中位（S5・S6）に置いた。feature-dev は 3 回、worktree は 0 回しか使われておらず、データ消失（S1）、#233 型の再発（S2）、静的ゲートの fail-open（S3）より実害が小さい。
- A6（旧 A5）の対象を `Bash(git restore -- *)` に絞る案: `git restore <file>`（`--` なし）も作業ツリーを書き換えるので、この形では漏れる。代わりに S1 の修正を「何もしない」にして衝突を避け、`--staged` にも確認が出ることは許容した。
- A8（旧 A7）の記録先を design-notes か ADR にする案: どちらでもなく `docs/session-reports/` にした。design-notes はプラグイン内の設計根拠の置き場で、この記録は repo 全体にかかわる。ADR は adr-keeper の 3 条件の①を満たさない。記録を 1 か所にする点は採った。
- S2 を (a) byte 比較か (b) pin のどちらかに決める案: 両方を使い分けた。ADR-20260813223000 自身が、byte 一致の複製には一致比較、言い換えには pin を使うという 2 機構の併存を定めている。
- push-reminder が「行頭の」git push で発火するという条件: 行頭に限らず、クォートの外に `git push` の並びがあれば発火する（`push-reminder.sh:27` の正規表現）。欠陥の指摘そのものは S16 として採った。
- living-spec の維持費を「bump と CHANGELOG の更新くらいではない」とした点: 一部だけ採った。(a) は description を変えないので runner の再実行は要らない。ただし 15 ケースを保守し続ける費用（`b56378d` は eval がきっかけの修正）は維持費として数えた。