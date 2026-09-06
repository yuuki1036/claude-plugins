# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.6.2] - 2026-09-06

### Fixed

- **同名 command の本文に SKILL.md への Read 誘導を置いた**（GitHub issue #219）。command 名と skill 名が
  同名だと `Skill plugin:name` で呼んでも**注入されるのは command 本文**で、SKILL.md には到達しない
  （#206 の本文版）。本文が「X スキルを使って」だけだと model は記憶で手順を再現するか cache を
  `ls | head -1` で掴む — 実測（2026-09-06）では辞書順で旧版を掴み、publish まで丸ごと落ちた。
  `${CLAUDE_PLUGIN_ROOT}` が展開されていない場合の解決先（`installed_plugins.json` の `installPath`）も
  本文に書いた。`validate_plugin_quality.py` の `skill-hop-cmd` が error で強制する。対象: `log-failure` / `retro`

## [0.6.1] - 2026-09-05

### Fixed

- **同名 command の description に `トリガー:` を複製した**（GitHub issue #206）。command 名と skill 名が
  同名だと、スキル選択の一覧に載るのは `commands/*.md` の description だけで **`SKILL.md` 側は
  router に届かない**。`トリガー:` 必須の規約は SKILL.md にだけ掛かっていたので、字面は通るが
  ルーティングには効いていなかった。対象: `log-failure` / `retro`。
  - **移動ではなく複製**（SKILL.md 側は残す） — `check_router_trigger_drift` が SKILL.md の
    `トリガー:` を入力にしており、移動するとその機械ガードが沈黙する
  - 引用符なしの description に `トリガー:` を足すと YAML の `key: value` と解釈されて frontmatter が
    壊れるので、二重引用符で囲んだ（既存の書式に揃えた）
  - `validate_plugin_quality.py` が同名ペアの commands 側にも `トリガー:` 必須を error で強制する
    （`[trigger-cmd]`）

## [0.6.0] - 2026-08-31

### Added

- **umbrella tag の分割宣言**（`.claude/failure-journal/splits.jsonl`）と照会スクリプト
  `scripts/tag-split-lookup.sh`（GitHub issue #195）。**分割を doc の表に書くだけでは
  起票側に降りない** — log-failure Phase 2 が寄せ先候補として見るのは「journal に実在する
  tag」だけで、宣言直後のサブ tag は 0 件だから構造的に候補にならず、次の発生もまた
  umbrella に寄る。宣言を機械が引ける場所へ移し、Phase 2 が起票のたびに照会する。
  照会は**壊れた行で止める**（捨てると「分割なし」に化けて元の状態へ静かに戻るため）
- log-failure Phase 2 に分割宣言の照会ステップ。`redirects` で「umbrella に見えるが
  別ファミリへ送る型」も降ろす（例: 他者の出力を検算せず採用した型は
  `misread-or-trusted-bad-output` へ）
- `retro-aggregate.sh` に `--splits` と 4 フィールド（`split_declared_at` / `sub_tags` /
  `count_after_split` / `split_not_adopted`）。**分割は分子を動かさない** —
  `remediations.jsonl` に相乗りさせると対策を打っていないのにアラームが消え、
  「還流後に再発なし」として報告される
- retro Phase 4 の先頭に「分割宣言の確認」。宣言済みの tag に分割を再提案せず、
  `split_not_adopted` なら打ち手を skill 層（起票側）に向ける。Phase 5 に
  「分割が降りていない tag」の節、Phase 6 に分割の記録

### Changed

- SessionStart / PostCompact hook が `splits.jsonl` も初期化する

## [0.5.0] - 2026-08-30

### Added

- **還流の実施記録**（`.claude/failure-journal/remediations.jsonl`）。閾値超え tag に対して
  実際に打った手を append-only で記録する（`tag` × 還流日 × 還流先）。SessionStart hook が
  空ファイルを初期化する。記録が無ければ従来どおりの集計になるので導入は任意（GitHub issue #193）
- **集計スクリプト** `scripts/retro-aggregate.sh`。窓境界の算出（BSD / GNU date 差の吸収）・
  不正行のスキップ・還流記録との join をまとめた。exit 0 集計成功 / 2 判定不能。
  境界（還流日ちょうどの発生・閾値ちょうどの件数）を回帰テスト 28 本で固定している
- 「**還流後に再発していない tag**」をレポートの独立した節として出す。還流していない tag の
  0 件は無情報だが、還流後の 0 件は対策が効いている可能性の観測で、意味が違う

### Changed

- **retro の閾値判定の分子を「最後の還流日以降の発生」にした。** 還流済みの発生を分子に
  残すと、対策を打った後も 30 日窓を抜けるまで同じ tag が鳴り続け、次の retro が
  **既に入れた対策とほぼ同じ手を再提案**する（実測で起票直前まで進んだ）。
  **分母（窓内の全発生）と除外件数は必ず併記する** — 黙って分子を減らすと「収まった」と
  誤読されるため
- Phase 4 の還流先提案に **既存の還流実績の併記を必須**にした。還流実績があるのに再発して
  いるなら、打ち手は「同じ層の強化」ではなく層の変更か tag の分割を先に検討する
- Phase 2 の集計を SKILL 本文の jq から同梱スクリプトへ移した。Phase 6 に「還流を記録」の
  選択肢を追加（承認後に append）

## [0.4.0] - 2026-08-29

### Added

- **umbrella tag の分割規約**（`journal-schema.md`）。同一 tag が還流のたびに別の機構を
  出してくるなら、それは 1 つの失敗型ではなく複数を束ねている。分割せずに還流を重ねても
  対策は毎回「今回の 1 件」にしか当たらず、閾値だけが鳴り続ける。判定の目安は
  「内訳の還流先が 2 つ以上に割れる」「還流した対策より後に別機構で再発している」。
  分割は**新しい発生から新 tag を使い、既存 journal は書き換えない**（append-only）
- retro の Phase 4 に umbrella tag の判定を追加。閾値超え tag に対して 1 つの還流先を
  選ぶ前に、分割すべきかを見る

### Changed

- 実例として `claimed-fact-without-source`（全期間 17 件・窓内 9 件で最多）の内訳を
  `journal-schema.md` に記載した。4 機構に割れ、還流先も hook / 規約にばらけている。
  うち「未確定の識別子を確定として書く」型は**存在検査では止まらない**ことを実測で
  確認した（起票前に書いた issue 番号が実在する別 issue を指しており、検査を通る）

## [0.3.1] - 2026-07-23

### Changed
- retrospective 連携の参照先を `indie-workflow:retrospective` から `issue-workflow:retrospective` に更新（linear/indie 統合プラグインへの移行。README / log-failure / retro）

## [0.3.0] - 2026-07-23

### Added
- **candidates.jsonl による自己訂正の自己申告フローを追加**（起票導線ギャップの構造対応）。SessionStart hook が自己申告ルール（`rules/self-report-rule.md`）を注入し、Claude が自己訂正した瞬間に候補を 1 行 append する。/retro Phase 0.5 が承認レビューで journal に昇格し、レビュー済み行に verdict（accepted/rejected）を書き戻して却下候補の再浮上を防ぐ。失敗を検知できる唯一の主体（Claude 自身）に検知した瞬間書かせることで、transcript 30 日消滅・grep precision 35%・マシンローカル依存という旧サルベージ設計の制約を回避する
- **PostCompact hook を追加**（同一スクリプトの再実行）。compaction で自己申告ルールが失われるのを防ぐ

### Changed
- **transcript サルベージを Phase 0.6 のフォールバックに降格**（実行条件: `--salvage` 明示 or 集計窓内の候補 0 件。`--no-salvage` はサルベージのみ禁止し候補レビューは実行する）
- retro / journal-schema / README を candidates フロー前提に更新（gitignore 推奨をディレクトリ単位に変更、sidechain 盲点とマルチマシン制約を既知の制約として明文化）

## [0.2.3] - 2026-07-22

### Fixed
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [0.2.2] - 2026-07-21

### Fixed

- **サルベージ手順が記載どおりでは動かなかった 2 件を修正**（self-review で検出）。(1) slug 導出の `sed 's|/|-|g'` が `.` を変換しておらず、`.claude` を含むパスで実在しない dir を指していた。`find` がエラーを握り潰すため**無言で「シグナル 0 件」に化ける**経路だった → `sed 's|[/.]|-|g'` に修正し、dir 不在時に探索パスを提示するガードを追加。(2) 走査手順で使う `$since_date` がどこにも定義されておらず、コピーすると `find -newermt ""` で落ちた → 窓起点の算出（OS 両対応）を追記
- **retro の allowed-tools に `Agent` を追加**（`skills/retro/SKILL.md` / `commands/retro.md` のペア一致を維持）。reference が「30 件超は Agent tool で並列分類」と指示する一方 allowed-tools に `Agent` が無く、実測 111 件は常に 30 件超のため既定運用が許可外ツールに依存していた
- **`${CLAUDE_EFFORT}` 実行時分岐を追加**（CLAUDE.md の深掘り系スキル必須規約）。0.2.0 で retro は全 transcript 走査 + 多段 agent 分類を持つ深掘り系になったが、`effort: medium` の宣言のみで実行時分岐が無かった。low/medium は窓 7 日 + 逐次、xhigh/max は全件並列 + 独立コンテキストでの tag 正規化

### Changed

- **測定値の断定表現に条件を付記**（`README.md` / `INDEX.md` / `CHANGELOG.md` / `transcript-salvage.md`）。「実測で起票率は約 2.5%」を測定条件なしで製品説明文に置いていたが、分母の 9 プロジェクトのうち 8 は log-failure を未運用であり、**導線の弱さと未運用の合算値**だった。単一環境（1 ユーザー・日本語セッション主体）である旨と再現手順を明記
- 「3 週間」を実測どおり「19 日間（2026-07-02〜07-21）」に訂正
- 「REAL 36 件」がどの試行の値か（claude-plugins 単独・全件分類）を明示し、冒頭表（9 プロジェクト横断・1/3 抽出・REAL 13 件）と区別
- 「制約と既知の穴」に 3 件追記: **subagent 内の失敗は原理的に拾えない**（sidechain は assistant 出力の約 30%）/ 却下候補が記録されず毎回再浮上する / transcript の保持期間（既定 30 日）が窓拡大の上限になる
- ユーザー訂正側の測定手順（603 ターン中 2〜3 件）を追記し、再現可能にした

## [0.2.1] - 2026-07-21

### Fixed

- **transcript サルベージの並列分類ガードを追加**（0.2.0 の実運用で 2 件の失敗モードが顕在化）。(1) 並列 agent が互いの語彙を見ないため同一の失敗に別 tag が付き、分散して閾値 3 回に届かなくなる → tag 正規化フェーズを必須化。(2) 担当行番号を勝手に振り直す agent が出て timestamp への逆引きが壊れる → 識別子は ISO 時刻を verbatim で返させる規約に変更（`skills/retro/references/transcript-salvage.md` / `skills/retro/SKILL.md`）

## [0.2.0] - 2026-07-21

### Added

- **retro に Phase 0.5「未起票失敗のサルベージ」を追加**。transcript (`~/.claude/projects/<slug>/*.jsonl`) を集計窓と同じ期間で走査し、Claude の自己訂正シグナルを grep 検知 → LLM で REAL/NOISE 分類 → 承認を経て journal に append する。手動起票の取りこぼしを retro 実行時にまとめて回収する
- `skills/retro/references/transcript-salvage.md` — 走査手順・precision・重複排除・制約（無言修正は拾えない / 日本語正規表現前提 / マシンローカル）を記述
- `/retro --no-salvage` 引数でサルベージをスキップ可能に

### Changed

- retro の Phase 0 が journal 空でも終了しなくなった（Phase 0.5 で起票される可能性があるため）
- Phase 3 で閾値超え 0 件かつサルベージ候補 0 件の場合、「失敗が少ない」ではなく「検知できていない」可能性に触れるようにした

> **背景**: 2026-07-21 の実測で、19 日間（2026-07-02〜07-21）に「再発しうる失敗」が 35〜40 件発生したのに対し journal 起票は 1 件だった。原因は閾値ではなく起票導線で、失敗の大半は Claude が自己訂正するためユーザーの目に触れず手動起票に乗らない。新規 hook 追加ではなく既存 retro の拡張を選択（`claude-meta:component-addition-advisor` の退路確保判定による。新規コンポーネント 0）。
>
> 測定は単一環境（1 ユーザー・1 マシン・日本語セッション主体・9 プロジェクト、うち 8 は log-failure 未運用）。「起票率 ≒2.5%」は導線の弱さと未運用の合算値であり、導線単独の指標ではない。測定条件の詳細は `skills/retro/references/transcript-salvage.md`。

## [0.1.2] - 2026-07-02

### Fixed

- log-failure の `failure:logged` publish スニペットが `SAFE_HOOK_NAME` 未設定で `"plugin":"unknown"` を書いていた問題を修正（source 直後に `SAFE_HOOK_NAME="failure-journal"` を設定するよう `skills/log-failure/SKILL.md` / `references/journal-schema.md` を修正）
- `hooks/scripts/session-start-init.sh` の journal ディレクトリ基準を Event Bus 正本と揃え、相対パス `.claude/failure-journal` を `${CLAUDE_PROJECT_DIR:-$PWD}/.claude/failure-journal` に変更
- `README.md` の「並行 install 可能」と「混ぜると壊れる」が矛盾していた編集残骸を修正

### Changed

- tag 長さ規約を「20 文字以内」から「30 文字以内」に緩和し、正準例 `spec-skipped-without-rationale`（30 字）と整合させた。`journal-schema.md` の自己矛盾（修正例が 20 字超で「※20字超なら更に短縮」と自己言及）も解消（`SKILL.md` / `README.md` / `commands/log-failure.md` / `references/journal-schema.md`）
- retro の allowed-tools から未使用の `Grep` を削除（`skills/retro/SKILL.md` / `commands/retro.md` のペア一致）

## [0.1.1] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#47)。再発する失敗の fingerprint 集計 + retro 自動還流を提供する Phase 1 実装
- `commands/log-failure.md` + `skills/log-failure/SKILL.md`: 再発しうる失敗を JSON Lines に append（単一基準「再発しうるか」/ tag は kebab-case 20 字以内・固有名詞禁止・現象主体 / append-only / `failure:logged` event publish）
- `commands/retro.md` + `skills/retro/SKILL.md`: 直近 30 日で同一 tag が 3 回以上再発したパターンを抽出し、AGENTS.md/CLAUDE.md・hook・skill への還流先を提案
- `skills/log-failure/references/journal-schema.md`: JSON Lines スキーマ / append 手順 / tag 規約
- `skills/retro/references/aggregation-rules.md`: 集計窓・閾値・jq 集計コマンド（macOS/Linux 両対応）/ 還流先判定ルール
- `hooks/`: SessionStart hook で journal ディレクトリ（`.claude/failure-journal/`）と `journal.jsonl` を初期化

### Notes
- `indie-workflow:retrospective`（主観的なセッション振り返り）とは責務が異なり、並行 install 可能
- journal (`.claude/failure-journal/journal.jsonl`) は gitignore 推奨。journal の Read は retro 実行中のみ（fingerprint の AI 出力汚染を回避）
