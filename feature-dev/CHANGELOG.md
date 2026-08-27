# Changelog

All notable changes to feature-dev plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.11.6] - 2026-08-28

### Changed

- **`plugin.json` の description を 502 → 201 字に圧縮した**（GitHub issue #183 /
  設計 `.claude/designs/20260610-plugin-description-diet.md`）。description は「これは何の
  プラグインか」を伝える 1〜2 文だが、バージョンアップごとに機能詳細を積層してリリースノート化
  していた。落とした詳細は CHANGELOG / README / SKILL.md に既出で情報は失われない。
  あわせて `validate_plugin_quality.py` に 400 字の上限検査（非ブロッキング warning）を追加し、
  再発を機械強制に寄せた

## [2.11.5] - 2026-08-17

### Changed
- 削除された `linear-workflow` / `indie-workflow` への参照を `issue-workflow` に張り替えた（旧 2 プラグインは統合後継への移行完了に伴いリポジトリから削除）

## [2.11.4] - 2026-07-29

### Changed
- code-architect / code-explorer の agent frontmatter から `LS` を削除（現行 Claude Code に存在しないツール名であることをインストール済みバイナリのツール名トークン実測で確認。無効宣言の除去のみで挙動は不変。agents 本文はツール名を明記しない形式のため skill 系の「本文割当」基準は適用していない）

## [2.11.3] - 2026-07-28

### Changed
- Phase 1.6 (Vault Recall) の存在理由の記述を世代非依存に更新（「Opus は recall tool を省略しがち」は Opus 4.8 世代の挙動。Opus 5 でも必須ステップとして構造化する理由づけに書き換え。動作は不変）

## [2.11.2] - 2026-07-22

### Fixed
- **triage-guide.md から存在しない公式 skill `web-design-guidelines` への参照を除去**（UI 変更のレビュー観点は code-review 委譲時に modern-web チェックリストでカバーされる旨に差し替え）
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [2.11.1] - 2026-07-16

### Fixed
- **並列起動した code-explorer / code-architect の結果取りこぼしを修正**。CC 2.1.198 で Agent tool の既定が background 実行に変わったため、Phase 2 / Phase 4 / Phase 6 escalation の agent 起動に `run_in_background: false` の明示を追加（省略すると完了を待たずに次フェーズへ進み結果を取りこぼす）

## [2.11.0] - 2026-07-14

### Changed
- **code-architect の model を `fable` → `opus` に変更**（プロジェクト方針で `fable` を全廃）。Phase 4 で毎回起動する設計 blueprint 生成は load-bearing なため強モデルで質を担保する。ルート CLAUDE.md のモデルルーティング規約（統合・設計 blueprint → `opus`）と整合。command / README の `architect:fable` 表記も更新

## [2.10.0] - 2026-07-07

### Added
- **Phase 1.4「BDD Spec Evaluation」を新設**（bdd-spec:evaluate-spec への dormant 連携。GitHub issue #78）。Phase 1.3 で spec.md を生成した場合、architect（Phase 4）の入力にする前に `bdd-spec:evaluate-spec` を `spec=<path> --embed` で呼び、網羅性（同値分割表⇔Scenario）・トレーサビリティ（epic AC⇔Scenario）の穴を機械判定する。🔴 critical（未カバー AC・リンク切れ）検出時は AskUserQuestion で「修正してから設計に進む（推奨）」を提示。穴のある spec が実装に伝播するのを安いオラクルで実装前に止める（Clearwing 原則 8）。bdd-spec 未インストール / Phase 1.3 skip 時は何もしない（後方互換）。評価失敗時は warning を出して best-effort で継続（設計フローをブロックしない）

## [2.9.1] - 2026-07-07

### Changed
- feature-dev.md に **コスト×精度パイプライン 10 原則の採用/不採用宣言を集約**（ルート CLAUDE.md 規約への準拠）。採用: 1（ファネル=Phase 1.7 triage）/ 3（段階予算=effort→agent 数）/ 4（モデルルーティング=explorer:sonnet / architect:fable）/ 8（外部オラクル=Phase 5.3 + Phase 6 fail-fast）。捨てた: 2/10（スコアリングは code-review へ委譲）/ 5（G-V ループは固定リトライ上限）/ 6（failure-journal へ委譲）/ 7（反証は code-review 側）。従来は各 Phase に散在していた言及を Effort Adaptation 直下に一言で集約

## [2.9.0] - 2026-07-02

### Added
- **check-deps.sh に「kvault はあるが `KNOWLEDGE_VAULT_ROOT` 未設定」検知を追加**。kvault CLI が PATH にあるのに環境変数が未設定だと Phase 1.6 (Vault Recall) が黙って skip される設定漏れを、SessionStart hook で 1 行 warning として気づかせる。あわせて「`~/.zshenv` に書く（`.zshrc` は非対話 shell で読まれず hook / spawn shell に効かない）」という設定先の落とし穴も明示する（従来の `check_cli "kvault"` は未導入しか検知できず、この設定漏れを取りこぼしていた）

## [2.8.1] - 2026-07-02

### Fixed
- **command の allowed-tools に `Agent` / `Edit` / `Write` を追加**。Phase 2 / 4 の explorer / architect 並列起動（Agent）と Phase 5 の実装本体（Edit / Write）に必須のツールが宣言されていなかった
- **「feature-dev は hooks/lib を持たない」記述の矛盾を修正**。実際は `hooks/lib/safe-hook.sh` を同梱しているため、Phase 7 の `feature:implemented` publish を JSON Lines 直書きから `event_bus_publish` 経由に統一（規約準拠、`SAFE_HOOK_NAME="feature-dev"` で publisher 識別）
- **check-deps.sh の未インストール警告文を連携先ごとに出し分け**。従来は bdd-spec / design-doc にも一律「Phase 6 は fail-fast」と表示していたのを、bdd-spec は「Phase 1.3 fallback」、design-doc は「Phase 4.5 skip」に修正（fail-fast は code-review のみ）
- **code-review の version 確認記述を実装に合わせて修正**。Phase 6 Step 0 は存在チェックのみで version ゲートは張らないため、「version 確認済み前提」の記述を「存在チェックのみ・旧版は markdown フォールバックで吸収」に修正
- **kvault vault 既定パスの個人環境パスハードコードを撤去**。`VAULT_ROOT="${KNOWLEDGE_VAULT_ROOT:-$HOME/Projects/knowleadge}"`（typo 込み個人ディレクトリ）を廃止し、`KNOWLEDGE_VAULT_ROOT` 未設定なら Phase 1.6 を skip する形に変更

### Added
- **README の Phase 表・prose に Phase 5.3（静的オラクルゲート）を追記**。v2.8.0 で追加された phase が README に未記載だった
- **kvault を `_requirements` に宣言**。Phase 1.6 Vault Recall で使う任意の外部 CLI を `cli_tool` / `required: false` として宣言し、`hooks/scripts/check-deps.sh` に `check_cli "kvault"` を追加（未導入時は skip、後方互換）

## [2.8.0] - 2026-07-01

### Added
- Phase 5.3「静的オラクルゲート」を新設。runtime smoke test（Phase 5.5）と LLM 品質レビュー（Phase 6）の**手前**で、型チェック / lint / テストという決定的オラクルを変更範囲に絞って実行し、exit≠0 なら Phase 5 Fix Mode に差し戻す（fail-closed）。型/テストを exit code で判定する決定的ゲートがパイプラインに一つも無く、機械的に落とせる欠陥まで multi-agent レビューに投げていた穴を塞ぐ。オラクルはプロジェクトの package.json scripts / tsconfig / Cargo.toml / go.mod / pyproject を検出（不在時は graceful skip、fail-open は summary に明記）、テスト実行は effort 連動（low/medium は型チェックのみ、high 以上で関連テスト）、ゲート↔Fix の往復は最大 2 回の暴走ガード付き。ルート CLAUDE.md「コスト×精度パイプライン設計指針」（Clearwing 原則 8: 外部オラクル + fail-closed）に準拠

## [2.7.2] - 2026-06-25

### Fixed
- bdd-spec / design-doc への委譲キャプションの version 直書き（v0.1.0）を撤去し「安定保証セクション参照」に抽象化（実 API は追従済みだが version 表記が stale だった）

## [2.7.1] - 2026-06-15

### Changed
- README を 8 phase 実態に同期。本文が「7 phase」表記のままで Phase 1.3 / 1.5 / 1.6 / 1.7 / 4.5（bdd-spec / design-doc 連携・Vault Recall・動的トリアージ）等の中核機能が未記載だったのを、現行の plugin.json（v2.7.0 以降）・commands・agents の実態に合わせて全面改稿。dormant 連携（bdd-spec / design-doc / kvault は未導入時 skip）と Phase 6 の code-review fail-fast を明記
- 煽り表現を除去。README 本文と references/triage-guide.md の「フル活用」、README / commands / agents の英語煽り語（comprehensive / thorough）を誇張のない表現に置換
- README 末尾の Version 行を撤去（plugin.json が version の SSoT のため二重管理を解消）

### Fixed
- 隣接プラグイン code-review へのパス直参照を skill 名参照に置換（プラグイン間依存禁止規約に準拠）。`commands/feature-dev.md` の `${CLAUDE_PLUGIN_ROOT}/../code-review/skills/self-review/SKILL.md` という相対パス直参照を「`code-review:self-review` skill の SKILL.md 参照」に変更。cache 配置で壊れうる隣接プラグインへの相対パス依存を解消

## [2.7.0] - 2026-06-11

### Added
- **Phase 4.5: Design Doc Export（design-doc plugin handoff）**。Phase 4 の architect 比較とユーザー採用決定（プロンプト内で揮発する）を、design-doc plugin の export 非対話 API（`mode=export`）で `.claude/designs/` に永続化する opt-in ステップ。`spec=`（Phase 1.3）/ `issue=`（Phase 1.5）を frontmatter に転記。未インストール時は完全 skip（dormant・後方互換 100%）、呼び出し失敗時も warning のみで実装フローを止めない
- Phase 7 サマリに design doc follow-up を追加（export 済みの場合、実装完了に伴う `phase: target → current` 更新を案内）
- `_requirements` / `check-deps.sh` に design-doc（required: false）を追加

## [2.6.0] - 2026-06-10

### Changed
- **code-architect agent を `model: opus` → `model: fable` に変更**。Phase 4 で実装 blueprint を一度に設計し後続フェーズに伝播する単一・高レバレッジの設計判断スロットに、Opus 上位ティアの Fable 5（claude-fable-5）を割り当て、知能上限を設計判断に集中させる。書き捨てが伝播する判断のため誤りのコストが高く、単一インスタンスで出力単価 2 倍（$50/1M）が bounded。並列起動する code-explorer (sonnet) は据え置き

## [2.5.0] - 2026-06-08

### Added
- **Phase 1.6 Vault Recall** (#67)。Phase 1.5 (Issue Context Detection) と Phase 1.7 (Triage) の間に、knowledge vault から横断知見（落とし穴・設計判断・移行ノウハウ）を recall して Phase 4 architect に注入するフェーズを追加。Opus が recall 系 tool を省略しがちな問題に対し、設計着手直前の必須ステップとして構造強制する
  - **外部 CLI 依存の二段存在確認**: `kvault` は feature-dev plugin 外の外部 app のため、CLI 本体（`command -v kvault`）と vault ディレクトリ（`KNOWLEDGE_VAULT_ROOT` 既定 `$HOME/Projects/knowleadge`）の両方が揃ったときのみ有効化。いずれか欠けたら skip し後方互換を壊さない（Phase 1.3 BDD spec の detect→skip パターンを踏襲）
  - **運用知見を明記**: クエリは自然文ではなくキーワード寄せ（JP embedding は自然文に弱い実測あり）、関連判断は `similarity` の絶対閾値ではなく rank + 1 位からの gap で行う（similarity の絶対水準はクエリ依存で変動するため）
  - recall は `kvault recall "<キーワード列>" --top 5 --min-sim 0`、stderr（HF warning / weights loading）を捨てて stdout の JSON `results[]` のみ消費
- `agents/code-architect.md` に **Vault Knowledge Injection** セクションを追加。注入知見は **advisory（参考情報）** であり authoritative ではないことを明示。優先順位は **BDD spec > 現コードベースのパターン > vault knowledge**、矛盾時は現コードベース優先。採用した知見は `title` を Critical Details に出典明記させる
- Phase 4 architect prompt に "Vault knowledge injection" の注入手順を追加

## [2.4.0] - 2026-06-03

### Changed
- **Phase 3 (Clarifying Questions) を grill 化**。一括の質問リスト提示を、design tree を 1 分岐ずつ潰す grill プロトコルに置き換えた（Matt Pocock "grill-me" / Brooks『The Design of Design』に由来）。Step 1 候補列挙 → Step 2 コードで答えられる問いは Phase 2 explorer 結果 / Grep / BDD spec / Issue context で自己解決して質問から落とす → Step 3 依存順ソート → Step 4 `AskUserQuestion` で 1 問ずつ・推奨案を先頭に `(Recommended)` 付きで確認 → Step 5 確定した前提 + ユーザー決定を design contract として集約。proportionality（残り 1〜2 問は圧縮）で過剰質問を抑制
- Core Principles の "Ask clarifying questions" を "Grill, don't list" に改訂

### Added
- `references/grill-protocol.md` を追加（grill 3 原則の正本: ①コードで答えられる問いは聞かない ②1 問ずつ依存順 ③各問いに推奨回答。over-question 抑制の proportionality ルール込み）

## [2.3.0] - 2026-06-01

### Changed
- **Phase 6 が self-review の構造化 findings JSON を消費（dual format、code-review ≥ 2.18.0）**。Step 3 / Step 4 はまず `<!-- FINDINGS_JSON_START -->` 〜 END の JSON ブロックを決定的にパースして findings（`severity` / `confidence` / `focus` / `file` / `line` / `suggested_fix`）を取得し、markdown 正規表現パースへの依存を解消。fingerprint (`file:line:focus`) も JSON の安定 focus キーから算出
  - JSON ブロックが無い旧 code-review (< 2.18.0) では従来の markdown 正規表現パースにフォールバック（後方互換）
  - 消費する schema 契約は self-review SKILL.md 「6.5」が SSoT（`schema_version: 1`）

## [2.2.1] - 2026-06-01

### Changed

- `agents/code-explorer.md` / `agents/code-architect.md` の `tools` から未使用の `WebFetch` / `WebSearch` / `TodoWrite` を削除（allowed-tools 最小性 #14b）。両 agent は既存コードベースの解析・設計に閉じており外部 web 参照・タスク管理を使わない。Permission Pruning 原則に従いツール宣言を最小化（`Glob` / `Grep` / `LS` / `Read` のみ）

## [2.2.0] - 2026-05-29

### Added

- **Phase 1.3 BDD Spec Creation** (#59)。`bdd-spec` plugin が同居する前提で、Phase 1 直後に BDD `spec.md` を architect 入力契約として生成するフェーズを追加
  - bdd-spec の `Skill bdd-spec:create-spec` を非対話 API (引数 `role` / `want` / `why` / `shortPath`) で呼び出し、生成された spec.md パスを `BDD_SPEC_PATH` として保持
  - Phase 4 architect prompt に `BDD spec path: <path>` を渡し、各 architect が冒頭で Read して Feature / Scenario / Examples / 同値分割表 / トレーサビリティ表を **authoritative requirements** として扱う
  - 「曖昧な Issue から実装が暴走する」失敗パターンを構造的に潰す（Phase 6 self-review の評価基準も spec が真実）
- `agents/code-architect.md` に **BDD Spec Injection** セクションを追加。spec 構造（epic/spec/all_spec/common_spec）の読み方、トレーサビリティ保持ルール、conflict resolution を明示
- `.claude-plugin/plugin.json` の `_requirements` に bdd-spec を optional 依存として追加
- `hooks/scripts/check-deps.sh` で bdd-spec の未インストール時 warning を出力

### Changed

- `feature-dev/commands/feature-dev.md` Phase 4 で BDD_SPEC_PATH が設定されている場合は各 architect prompt に注入する指示を追加

### Notes

- bdd-spec 未インストール時は Phase 1.3 を完全 skip し、既存の Issue 解釈フロー（Phase 1.5 linear/indie handoff）に fallback。**後方互換性 100%**
- bdd-spec API は v0.1.0 で安定化済み（#49）。引数で全要素が埋まっていれば非対話実行されるため feature-dev embed 用途に適合

## [2.1.0] - 2026-05-29

### Added

- **Phase 5.5 Step 0: Self-lock guard** を追加（GitHub issue #58）。TTL 600s の lock file (`/tmp/feature-dev-${HASH}.lock`) で同一プロジェクトでの Phase 5.5 重複起動を防止する template
  - 目的: 将来 feature-dev に PostToolUse hook が入って Phase 5.5 を自動トリガーする構成になった場合、Phase 5.5 内の Edit / Bash が再度 PostToolUse を発火させて無限ループに陥る事故を構造的に予防
  - 実装: `git rev-parse --show-toplevel` (失敗時 pwd fallback) の sha1 を 12 文字 cut してハッシュ化し lock path を決定
  - 互換性: macOS BSD `stat -f %m` / Linux GNU `stat -c %Y` の dual path で `stat` 呼び出しを portability 確保。両方失敗時は `echo 0` で安全側
  - active 時の挙動: `SKIP_PHASE_5_5=1` フラグを立てて Step 1〜4 を skip し、Phase 6 へ進む（hook 経由起動時はハーネス側が早期復帰として扱う）
  - TTL 切れ時は `touch` で lock を取り直し

### Notes

- 現状の command 経由手動実行ではループは発生しないが、doc-freshness (#48) / failure-journal (#47) など今後の評価系 hook 連携時の事故防止 template を先に入れる方針

## [2.0.1] - 2026-05-29

### Changed

- **Phase 6 Step 2** の `Skill code-review:self-review` 呼び出しに **`--embed`** 引数を必須化（GitHub issue #57）。code-review v2.17.0 の embed mode に乗り換えることで、self-review 終端の修正方針確認 AskUserQuestion を skip し、ユーザー操作を 1 回削減。findings は従来通り feature-dev Step 4 の集約処理に流す
- **Phase 6 Step 3.2** の Generator-Verifier ループ内 re-review 呼び出しにも `--embed` を追加。loop 中の各 iteration で AskUserQuestion が発火しないことを保証
- v2.0.0 の Migration Guide に記載した「Phase 7 の AskUserQuestion で skip 相当を選ぶ」workaround は本リリースで不要になる（既知の制約解消）

### Notes

- code-review v2.17.0 以上を前提とする（embed mode 未対応の旧バージョンでは workaround が必要）。SessionStart hook (`check-deps.sh`) は plugin の存在のみ確認しており version までは見ていないため、ユーザー側で `claude plugin install code-review@yuuki1036-claude-plugins` で最新化する必要がある

## [2.0.0] - 2026-05-28

### ⚠️ BREAKING CHANGES

- **`code-reviewer` agent を削除し、Phase 6 を `code-review:self-review` skill 呼び出しに置換** (#52)。同一リポジトリ内で reviewer ロジックが二重化していた DRY 違反を解消し、品質基準を `code-review` plugin の 2 軸スコアリング × 15 観点 × specialist × meta-reviewer 構造に一本化
  - **MIGRATION**: `code-review` plugin が **事実上の必須依存** になった。`plugin.json` の `_requirements` では `required: false`（プラグイン間の強制依存は claude-plugins 規約で避けるため）だが、未インストール環境では Phase 6 が **fail-fast** で停止する。先に `claude plugin install code-review@yuuki1036-claude-plugins` を実行
  - SessionStart hook (`hooks/scripts/check-deps.sh`) で code-review 未インストール時に強い warning を表示
  - 削除ファイル: `agents/code-reviewer.md`
  - 追加ファイル: `hooks/hooks.json`, `hooks/scripts/check-deps.sh`, `hooks/lib/safe-hook.sh`
  - 内蔵 agent: 3 → 2（code-explorer / code-architect のみ）

### Changed

- **Phase 6 Step 2 を self-review 呼び出しに変更**: 従来 N 体の `code-reviewer` agent を並列起動していた箇所を `Skill code-review:self-review --focus <list>` 1 回の呼び出しに集約。self-review 内部で Phase 0 triage → Phase 3/4 並列 reviewer → Phase 4.5 adaptive deepening → Phase 4.6 meta-reviewer → Phase 5 2 軸スコアリングが走る
- **Phase 6 Step 3 G-V loop の auto-fix トリガーを再定義**: 従来 `confidence ≥ 90` 単独判定だったところを、self-review の severity × confidence 出力に合わせて以下にマップ
  - `BLOCKER` (any confidence) → auto-fix 対象（最高優先度）
  - `CRITICAL && confidence ≥ 90` → auto-fix 対象（従来閾値を維持）
  - `CRITICAL && confidence < 90` / `MAJOR` / `MINOR` → 報告のみ
  - **Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は誤検知防止のため従来の高 confidence 閾値を維持
- **Phase 6 Step 3.2 re-review** を `Skill code-review:self-review --focus <persisting> --exclude <resolved>` に変更。`--exclude` で既に解決した観点をスキップしてコスト削減
- **README.md の Agents セクションから `code-reviewer` 記述を削除**、Phase 6 説明を self-review 呼び出しベースに更新

### Migration Guide

#### v1.x → v2.0.0

**必須対応**:
1. `code-review` plugin を install: `claude plugin install code-review@yuuki1036-claude-plugins`
   - 未インストール時、SessionStart hook が warning を出す
   - Phase 6 冒頭で existence check し、未インストール時は fail-fast（Phase 5 までは正常動作）
2. Phase 6 の挙動が変わることを確認:
   - 従来: N 体 reviewer 並列起動 → confidence ≥ 90 で auto-fix
   - v2.0.0: self-review 1 回呼び出し → BLOCKER 全部 + (CRITICAL && conf ≥ 90) で auto-fix

**カスタムシナリオへの影響**:
- 手動で `code-reviewer` agent を呼んでいたコード（`Agent` tool subagent_type）は動作しなくなる → 代わりに `Skill code-review:self-review` を呼ぶ
- feature-dev の Phase 6 出力フォーマットが変わる（confidence のみ → severity × confidence）。下流で出力を parse している自動化があれば修正必要

**既知の制約**:
- self-review skill は Phase 7 で AskUserQuestion (修正方針確認) を出す設計。feature-dev からの呼び出し時は **「skip — feature-dev 側で集約します」相当の選択肢** を選んで findings を返してもらう必要あり。将来的に self-review 側へ embed mode 引数を追加する想定（別 Issue で議論）

## [1.6.1] - 2026-05-22

### Changed
- `commands/feature-dev.md` Step 3.2 の re-review launch 設定記述を修正。`effort: max` ハードコード表記を Step 2 の動的 effort (`${CLAUDE_EFFORT}`) と整合する表現に変更。Step 2 自体は元々動的展開で max ハードコードはしておらず、再 review 時の記述ミスを是正

## [1.6.0] - 2026-05-18

### Added

- **Phase 7 で `feature:implemented` イベントを発行** (#33)。`.claude/events.jsonl` に JSON Lines 1 行を直接追記する fire-and-forget publisher。payload は `{"feature":"<desc>","files_changed":<n>,"phases_completed":[...]}`
  - feature-dev は hooks/lib を持たないため、Classmethod 記事の Message Bus パターンに沿ったまま safe-hook.sh を経由せず Phase 7 内の Bash で直接書き込む方式を採用
  - subscriber がいなくても無害（既存挙動を一切変えない）。失敗しても Phase 7 全体は成功扱い

## [1.5.0] - 2026-05-17

### Added

- **Phase 6 Generator-Verifier ループ** を Step 3 として追加。reviewer が confidence ≥ 90 で出した致命指摘を自動的に Phase 5 Fix Mode に差し戻して修正、再 review、収束まで（または予算切れまで）反復する
  - Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Generator-Verifier パターンを「reviewer の confidence スコア」という客観基準で gate して実装
  - **effort 別ループ予算**: `low` = 0（skip）/ `medium` = 1 / `high` = 2 / `xhigh` = 3 / `max` = 3 iteration
  - **Regression 検知**: `fingerprint = file:line:focus` を `/tmp/feature-dev-loop-state.json` に蓄積し、連続 2 iteration で同一 fingerprint が残存したら自動 fix 不能と判定してループを break、ユーザに引き渡し（無限ループ防止）
  - **修正不能時の逃げ道**: メインスレッドが Edit で直接修正できない場合、`code-architect` を `delta-proposal` focus で起動して設計レベルの delta を取得（1 iteration 消費）
  - **再 review の選択性**: critical 指摘を出した reviewer focus のみを re-launch、他は再実行しない（コスト削減）
- **Phase 5 Fix Mode** を追加。Phase 6 ループから起動された場合、Phase 4 で選んだ architect 設計を維持しつつ reviewer 指摘の file:line のみピンポイント修正（スコープ拡大禁止）
- **Phase 7 G-V loop summary**: ループ実行履歴を `/tmp/feature-dev-loop-state.json` から読み取り、iteration 数 / termination reason / auto-fixed count / persisting issues を最終サマリに含める
- `references/triage-guide.md` に Section 10「Generator-Verifier ループ予算」を追加。effort 別 max_iterations / confidence 閾値 / regression 検知 / 終了条件 / fix の責務分離 / Phase 5 Fix Mode 仕様を一元的に定義

### Notes

- v1.4.0 の Phase 1.7 動的トリアージ（Orchestrator-Subagent パターンの拡張）と組み合わせて、Classmethod 記事の 2 つのパターン（Orchestrator-Subagent + Generator-Verifier）のハイブリッド構成が feature-dev でも完成。code-review プラグインが先行実装した思想を機能開発側にも展開
- `low` / `medium` effort では従来通り「critical 指摘もユーザ判断」を維持しつつ、`high` 以上で自動 fix が有効化される段階的設計

## [1.4.0] - 2026-05-17

### Added

- **Phase 1.7: Triage（動的エージェント構成決定）** を Phase 1.5 と Phase 2 の間に追加。code-review プラグインの Phase 0 トリアージパターンを移植・3 種 agent（explorer / architect / reviewer）に拡張
  - メインコンテキストで feature 要件・Issue context・プロジェクト特性（`package.json` / CLAUDE.md）を分析し、explorer / architect / reviewer の体数・focus・angle を動的決定
  - Stage 1: タイプ判定（bugfix / extension / new-feature / refactor / migration / cross-cutting）と各 agent の必要観点判定
  - Stage 2: 体数・focus・冗長度決定。effort 別上限（low/medium/high/xhigh/max）に従いキャップ
  - Phase 6 で **mini-triage 再判定**：Phase 1.7 暫定構成を実装後の diff ベースで refine（try-catch 追加で error-handling 追加、認証関連変更で security 昇格 等）
- `references/triage-guide.md` 新規作成。Phase 1.7 のロジック・体数ルール・effort 適応・フォールバック構成・最小保証を定義
- Phase 2 / 4 / 6 を「Phase 1.7 構成テーブルに従う」形式に書き換え。固定 2-3 体起動から動的体数へ移行
- Phase 2 / 4 に **partial failure tolerance** 追加。個別 agent 失敗時も成功した結果で続行、`missing_coverage` リストに記録

### Changed

- `Effort Adaptation` セクションを再構成。低レベルな「何 phase 圧縮するか」記述から、triage-guide.md Section 5 の effort 別上限テーブルへのポインタに変更
- Phase 1.5 の「Skip Phase 2」directive を「Phase 1.7 への信号送信」に変更（Phase 1.7 が 0 explorer 判定すれば結果的に Phase 2 skip）

### Notes

- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の `Orchestrator-Subagent` パターンに「動的トリアージ」と「mini Generator-Verifier ループ準備」を組み合わせた構成。code-review が達成済みのパターンを feature-dev に展開し、プラグイン横断で同じオーケストレーション思想を確立する第一歩
- explorer の固定 2-3 体起動 → 0-6 体動的化により、単純 bugfix では Phase 2 完全 skip で 30 秒〜1 分短縮、複雑な refactor では 5-6 体起動で多角的検証

## [1.3.0] - 2026-05-15

### Added

- `feature-dev` command に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて 8-phase flow を圧縮・展開（low/medium: 4-phase 圧縮、high: 既定、xhigh/max: 多重 explorer + 二重 reviewer）

## [1.2.0] - 2026-05-12

### Added

- **Phase 5.5: Runtime Smoke Test** を Phase 5 (Implementation) と Phase 6 (Quality Review) の間に追加。tsc / lint / build では検知できない runtime 初期化バグ（Prisma client 初期化、env var 読み込み、middleware 設定ミス、proxy lazy-init 等）を Quality Review 前に検出する
  - Step 1: 決定的検出 — `git diff` から DB client / env var / middleware / 新規 route のパターンを grep し、smoke test が必須か任意かを判定（CLAUDE.md「決定的検証 > LLM 判定」方針に整合）
  - Step 2: `AskUserQuestion` で実行可否を確認（REQUIRED 時は実行推奨、OPTIONAL 時は skip 推奨）
  - Step 3: 既存の `dev-workflow:ui-verify` skill を呼び出して dev server 起動 + console error / network 4xx-5xx を検査（component-addition-advisor の「退路確保」原則に従い新 agent 追加せず既存資産を再利用）
  - Step 4: 失敗時は Phase 6 に進ませず修正を促す。chrome-devtools MCP 未設定時は手動確認にフォールバック（hard fail しない）
- `code-architect` agent の出力フォーマットに **Runtime Smoke Test Targets** セクションを追加。Phase 5.5 が叩く URL / route を architect 段階で明示。runtime surface に触れない変更では `none (static-only change)` を明示してスキップ判断を支援
- `commands/feature-dev.md` の `allowed-tools` に `Skill` を追加（`dev-workflow:ui-verify` 呼び出しのため）

### Notes

- Issue #29 の Prisma v7 adapter 必須化のような「全静的チェックを通過したのに初回 runtime アクセスで死ぬ」事故を構造的に予防する
- description を「7 phase」→「8 phase」に更新

## [1.1.1] - 2026-05-01

### Changed

- 全 3 agent (code-explorer / code-architect / code-reviewer) の `tools` を 10 個から 7 個に最小化。削除: `NotebookRead`（Jupyter 用途は本プラグインの主流ではない）、`KillShell`（Phase 内シーケンシャル実行で非同期タスク不要）、`BashOutput`（agent は Bash を保持しないため呼び出せず無効）。Permission Pruning の原則（claude-plugins CLAUDE.md の Hook > LLM 判定とも整合）に従い、宣言ツールを必要最小限に絞ることで判定精度を上げる

## [1.1.0] - 2026-05-01

### Changed

- `code-architect` agent のモデルを `sonnet` → `opus` に変更。設計推論・複数案比較で adaptive thinking の深さを活用する
- `code-reviewer` agent のモデルを `sonnet` → `opus` に変更。confidence ≥80 フィルタの判定精度を上げ、誤検知を最小化する
- `code-explorer` は `sonnet` 維持（並列 2-3 起動・量重視・コスト効率）

### Added

- `code-architect` system prompt に **Issue Context Injection** セクション追加。linear-workflow / indie-workflow から upfront 引き渡された Issue メタ・親 Issue サマリー・関連 knowledge・既存の `feature_dev_plan:` を設計の起点として使用する
- `code-architect` system prompt に **Hook-First Rule Placement** セクション追加。新ルール提案時に Hook → Skill/Agent → CLAUDE.md の優先順位で配置先を判定する（CLAUDE.md の決定的検証優先ルールに整合）
- `commands/feature-dev.md` に **Phase 1.5: Issue Context Detection** 追加。`Issue ファイル:` パスや `feature_dev_plan:` frontmatter を検出すると Phase 2 (Codebase Exploration) をスキップし、context を Phase 4 architect に直接引き渡す
- `commands/feature-dev.md` の frontmatter に `allowed-tools`（Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion）を明示宣言（command はオーケストレーター責務、低レベル探索は agent 側に委譲）

## [1.0.1] - 2026-05-01

### Fixed

- `README.md` の Author セクションに残っていた本家元著者の連絡先を内製化後の表記に修正（quality-check の固有情報混入チェックで検出）。元著者情報は `CHANGELOG.md` の fork 経緯記述で参照する形に変更

## [1.0.0] - 2026-05-01

### Added

- claude-plugins-official/feature-dev からフォークし、yuuki1036-claude-plugins マーケットプレイス配下に取り込み
- `/feature-dev` コマンド（7 phase ワークフロー: Discovery → Codebase Exploration → Clarifying Questions → Architecture Design → Implementation → Quality Review → Summary）
- `code-explorer` agent（実行パス追跡・抽象層マッピング・依存関係分析）
- `code-architect` agent（既存パターン分析・実装ブループリント設計）
- `code-reviewer` agent（信頼度 ≥80 のみ報告するバグ・規約レビュー）

### Notes

- 本リリースは無改造の fork。本家はメタデータ未整備（version フィールド無し）のため、内製化により version 管理・linear-workflow との深い連携・モデル切り替え自由度を確保する
- 後続マイルストーンで code-reviewer と code-review プラグインの責務整理、Linear Issue メタの agent prompt 反映、モデル選択の柔軟化を検討予定
