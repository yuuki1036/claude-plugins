# Changelog

このプロジェクトのすべての注目すべき変更を記録する。

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に準拠し、
[Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [0.6.1] - 2026-06-26

### Fixed

- **textlint v15 のルール解決失敗を検出できず警告が出ない問題を修正**（GitHub issue #73）。config が参照する `@textlint-ja/preset-ai-writing` 等が未インストールだと textlint v15 は全ルールを黙って drop し、stdout に `== No rules found, textlint hasn't done anything ==`（非 JSON）を出して **stderr は空・exit 1** になる。従来の検出は「①stdout が valid JSON ②stderr 文字列マッチ（`could not find` 等）」の 2 分岐だったため、この失敗形はどちらにも当たらず素通りし、決定的チェックが落ちたまま silent に LLM フォールバックしていた（preset 1 つの欠落で全決定的チェックが無効化される）
  - 検出を **「stdout が valid JSON でなければ＝ルール解決失敗」に一本化**し、stderr 文字列依存を撤廃（`references/linter-integration.md`「ルール解決失敗の検出」の bash 分岐を `elif grep ... stderr` → `else` に変更、SKILL.md step 2.5 の判定記述も同期）。`--format json` 成功時は指摘ゼロでも `[]` 相当の JSON を返すため、JSON でなければ失敗と決定的に判定できる
  - textlint v15.7.1 で失敗形（stdout `No rules found`・stderr 空・exit 1）を実機再現し、修正後の `else` 分岐が確実に警告を発火することを確認

## [0.6.0] - 2026-06-24

### Added

- tone-guide カテゴリ 5（用語と正確性）に **行為主体を消す無生物主語（false agency）** の検出を追加。「データが示す」「設計が物語る」のように主張・意志を伴う動詞の主語が無生物で、誰の主張か（出典・責任）が消える AI 生成 tell を、能動/受動の態とは別軸（主語の意味カテゴリ）で判定する。慣用化した擬人表現・一人称を省く文書種別（PR description 等）では保全し、固定対訳にはしない（外部スキル stop-ai-slop-jp の False agency 観点を既存設計言語に翻訳して取り込み）
- tone-guide カテゴリ 2（曖昧さの除去）に **反証不能な締め** の検出を追加。「重要だ」「本質的だ」で文・段落を閉じ後続に具体・固有名・数値が続かない＝反証できない主張を、曖昧「語」から曖昧「主張」へ一段上げて拾う。原文に無い立場は注入せず「主張がぼやけている」と指摘 or 削る案に留める over-correction ガード付き
- textlint `@textlint-ja/preset-ai-writing` を同梱 config（`references/textlintrc.json`）で有効化。装飾絵文字・リスト項目の機械的な太字+区切り・過剰強調・hype 表現を決定的に拾い、tone-guide カテゴリ 4 が出典に挙げていたが config 未設定だった不整合を解消。`_requirements` の導入コマンドと `linter-integration.md` の ruleId 対応表・導入手順を同期
- **ルール解決失敗の検出**を追加（`references/linter-integration.md`「ルール解決失敗の検出」, SKILL.md Step 2.5）。textlint 本体は導入済みでも config が参照するルールパッケージ（preset-ai-writing 等）が未解決だと textlint は JSON を返さず落ちるため、stdout が valid JSON でなく stderr にルール解決エラーが出たケースを検出し、欠落パッケージの導入コマンドを一度警告して LLM フォールバックする（embed / `WRITING_POLISH_SKIP_LINTER_PROMPT` / セッション内既出は silent）

### Changed

- tone-guide カテゴリ 4（AIっぽさ）に **情感記号の濫用**（全角ダッシュ「──」多用・心情語の「」囲み・中黒 3 項並列）を LLM 観点として追加。preset-ai-writing で決定的に拾える分は委譲境界へ明記し、preset が拾えない `──`/中黒の density 判断は LLM が担う棲み分けを明文化

## [0.5.0] - 2026-06-22

### Added

- 提示・採否 UX の正本 `references/presentation-guide.md` を新設（tone-guide が「何を直すか」、presentation-guide が「どう見せて採否させるか」の SSOT として責務分離）。人間が採否しやすい提示を規定: 冒頭サマリ行（件数・カテゴリ内訳・字数/最長文インパクト）、確信度ラベル `[確実]`/`[任意]` の 2 群分離、意味が動きうる修正の `[要確認]` フラグ、理由を内部語彙でなく読み手目線の効能で書く規約、「あえて直さなかった箇所」の保全明示、リスク昇順の採否選択肢、冪等到達の可視化、連続変更のインライン囲み `〔原文 → 修正〕`。設計原則「提示は軽く、情報は厚く」で行頭マーカーを 2 軸（確信度＋要確認）に制限し、出自(textlint)・測定値・想定読者・認知効果は理由文に溶かしてマーカー乱立を防ぐ

### Changed

- tone-guide: 文書種別表に「想定読者」列を追加（理由文の主語に使う根拠）、「適用の優先順位」に確信度（確実/任意）の判定軸を SSOT 化、カテゴリ 2 に誤読シナリオの言語化、カテゴリ 5/7 に認知効果ラベル運用（concreteness effect 等）、アンチパターン 2 の保全を「提示でも明示」に拡張
- SKILL.md のステップ 3（差分提示）・ステップ 4（採否フロー）・embed 返却・effort 連動を presentation-guide 参照に更新。`references/linter-integration.md` に textlint 由来指摘の出自を理由文へ非対称表記で残す節を追加

## [0.4.0] - 2026-06-21

### Changed

- textlint 未導入時に silent skip せず、skip 前に一度ユーザーへ確認するフローを追加（GitHub Issue #72）: `AskUserQuestion` で「導入する／LLM 判定のみで続行」を提示し、決定的レイヤーが落ちたまま推敲が走ったことに気づけるようにした。導入案内に mise/nvm 環境向けの PATH/shim 注意（`mise reshim`、install 直後も `command -v textlint` が false なら shim 未解決を疑う）を併記
- 確認の煩わしさ対策として退路を 3 つ用意: embed モード（`--embed`）は終端 prompt を出さない原則を優先して silent フォールバック、環境変数 `WRITING_POLISH_SKIP_LINTER_PROMPT` で恒久 opt-out、同一セッションで「LLM のみで続行」を選んだら再確認しない。SKILL.md Step 2.5 と `references/linter-integration.md`（「未導入時の確認フロー」節）、plugin.json の `_requirements` 説明を更新

## [0.3.1] - 2026-06-10

### Changed

- tone-guide カテゴリ 7 の発火条件を精緻化（GitHub Issue #70）: 文脈依存の固定対訳例（「非自明な意味論」→…）を撤去し「固定対訳を正本に載せない」方針を明文化。抽象名詞/具体語の操作的定義と 4 段階の判定手順を追加し、density・共起・構造シグナルによる再現可能な判定基準として記述（単語存在ベースの発火を排除）。文脈非依存の決定的変換（軽動詞構文）のみ例示を許容
- カテゴリ 7 の保全基準と束ね判定の境界を明確化: 束ね位置の抽象漢語に**置換テスト**（平易な指示表現に置換しても情報が失われないなら発火）を導入。保全基準は「情報を担っている語」にのみ適用し、置換テストが成立する束ね語は正当な専門用語でも飾り用法として保全しない。緩用・比喩的転用の学術用語は保全対象外、読者の語彙共有は文書種別から推定（eval 校正で「冪等性は保全 / 緩用の意味論は発火」が分離できなかった二値不安定を解消）
- カテゴリ 7 の判定校正 eval ケースを追加（`evals/cases/writing-polish.yaml`）: 発火すべき入力（束ね位置の抽象漢語・density 超過）と発火させてはいけない入力（専門用語の保全・既に具体的な文）を pass^k=3 で回帰検証。トリガーフレーズ回帰ケースも同時追加

## [0.3.0] - 2026-06-09

### Added

- textlint 実行連携（任意・required:false）。`references/linter-integration.md` に連携手順、`references/textlintrc.json` に同梱 config。`command -v textlint` で存在チェックし未導入時は LLM 判定にフォールバック。SKILL/command の allowed-tools に Bash 追加、plugin.json に `_requirements`（textlint, required:false）

### Changed

- tone-guide「委譲境界」を textlint 実行委譲に合わせて更新（未導入時の LLM フォールバックを明記）

## [0.2.0] - 2026-06-09

### Added

- tone-guide カテゴリ 7「平易性 / 過剰抽象（over-abstraction）」: 語彙の抽象度を見る検出軸。具体例が並ぶ文脈の抽象漢語・動作を隠す名詞化（軽動詞構文）・借り物の荘厳さ・density 判定で発火を構造的に絞り、専門用語を残す 3 条件で over-correction を回避（GitHub Issue #70。既存カテゴリ 2 は口語曖昧、4 は「語彙を縛らない」、5 は測定可能性に閉じており抽象漢語がどのレバーにも掛からなかった穴を埋める）
- カテゴリ 4（AI っぽさ）に構文 tell を追加: negative parallelism（「〜ではなく〜だ」の濫用）・三点強迫・総括の宣言
- 「textlint / Vale 委譲境界」セクション: 決定的に拾える観点（表記・文法・確実な冗長構文・しきい値・差別語）は linter、文脈判断（名詞化の良性/悪性・衒学語の言い換え・ヘッジ採否・AI っぽさの density 判断）は LLM が担う棲み分けを明文化

### Changed

- カテゴリ 7 と構文 tell は high/xhigh/max effort 限定で発火（low/medium の速度・安全性を維持し、over-correction リスクの高い観点を浅い effort で暴発させない）

## [0.1.0] - 2026-06-03

### Added

- `writing-polish` スキル: 文章を語句レベルで推敲・添削する。最小差分の diff 提示 → 採否フロー。RFC / Issue / PR 本文 / コミットメッセージ / レビューコメント対応、日英両対応
- `/writing-polish` コマンド: スキルのスラッシュコマンド版。`--embed` / `--tone` / `--aggressive` オプション対応
- `references/tone-guide.md`（校正ルール正本 / SSOT）: textlint（preset-ja-technical-writing / japanese / ai-writing / JTF-style）と Vale の 11 チェックタイプ、Google / Microsoft style guide を統合したカテゴリ分類。文体メタルール（文書種別で敬体/常体を使い分け）、6 カテゴリ、過剰修正アンチパターンを収録
- 中核原則として over-correction（過剰修正）抑制を採用（一次研究 arXiv 2512.12544 HyperEdit / 2502.13358 FineEdit 由来）
- `--embed` による他プラグインからの soft 委譲インターフェース（POLISH_RESULT マーカー付き機械可読返却）
