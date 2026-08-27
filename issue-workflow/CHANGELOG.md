# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.4.5] - 2026-08-28

### Fixed

- **doc と実装の乖離を掃引した**（GitHub issue #185）。旧 linear-workflow / indie-workflow の
  死んだ参照の張り替え、README が実装と食い違っていた記述（欠落していた表の行・設定キー・
  引数・エラー文言）の訂正が主な内容。挙動の変更は無い

## [1.4.4] - 2026-08-27

### Fixed

- `check-scope-size.sh` の `jq` 不在 fallback にも `|| true` を付けた（GitHub issue #180）。
  jq 分岐は付与済みだったが grep fallback 側に無く、対象キーを欠く payload で
  ERR trap を踏んで自己判定に到達しなかった（dev-workflow の 5 本と同型）

## [1.4.3] - 2026-08-27

### Fixed

- **hook の自己判定ガードが unreachable だった 3 箇所を直した**（GitHub issue #179）。
  `$(... | grep ...)` に `|| true` が無く、対象キーを欠く payload では grep の exit 1 が
  safe-hook の ERR trap を踏み、**以降を実行せず exit 0** していた。正常系が silent exit 0
  なので、外からは「ガードで黙った」と「途中で死んだ」を区別できない:
  - `on-issue-change.sh` — `file_path` キーが無い payload で自己判定に到達しない。
    FileChanged の payload 形が変われば `issue:completed` の publish ごと黙って止まる
  - `on-knowledge-change.sh` — 同型
  - `set-session-title.sh` — `title:` 行を欠く issue ファイルで Validation に到達しない
    （同ファイルの他 3 箇所は `|| true` 済みで、この 1 行だけ漏れていた）
- **`check-scope-size` が 9 セクションテンプレを数えられなかった**（同 issue）。
  チェックリストを `## 進捗` 節だけで数えていたため、`/issue-design` でリライトした Issue
  （チェックリストは `## 完了条件`）では COUNT=0 になり、**スコープ超過の警告が無言で
  無効化**されていた。`issue-create/SKILL.md` は「スコープサイズは全 type で必須
  （check-scope-size hook のリアルタイム警告の前提）」と宣言しており食い違っていた。
  両節を対象にし、両方あるときは `## 進捗` を優先する（移行途中のファイルで二重に
  数えて誤警告しないため）
- `set-session-title.sh` のヘッダが実在しないイベント名 `SessionTitle` を名乗っていたのを
  実際の配線（`UserPromptSubmit` / `once`）に合わせた

## [1.4.2] - 2026-08-17

### Changed
- 削除された `linear-workflow` / `indie-workflow` への参照を `issue-workflow` に張り替えた（旧 2 プラグインは統合後継への移行完了に伴いリポジトリから削除）

## [1.4.1] - 2026-07-29

### Changed
- doc-resolver agent の tools から未使用の `Grep` を削除（全ステップが Read / Glob に割当済み。宣言の除去のみで挙動は不変）
- knowledge-lint Phase 1 の Issue ファイル `[[name]]` 収集を「Grep（pattern 明示）でマッチ行のみ使う」と明記し、`Grep` 宣言と本文の対応の曖昧さを解消

## [1.4.0] - 2026-07-29

### Added
- **却下記録（`kind: rejected`）機構を追加**（mattpocock/skills の triage `.out-of-scope/` KB を翻案）。人間が「対応しない」と明示判断した提案・課題を knowledge に概念単位・理由付きで永続化し、discover の重複除外（Phase 4 に照合ステップ追加。キーワードでなく概念類似で判定）が参照して再提案を機械的に抑止する。書式・照合基準（概念類似の正例・負例・迷ったら backlog に倒す fail-open）の正本は `discover/references/rejected-record.md`（frontmatter は `status: rejected` 固定 + `rejected: 日付`、鮮度フィールドなし）。書き込み導線は discover Phase 7.5（レポート後のユーザー見送り指示）と maintain の破棄フロー（canceled / dismissed / backlog 破棄、処理 2・3・6・7 共通ルール）。「実装済みだった候補は記録しない」「一時的理由（優先度低下）は却下でなく延期」の汚染防止規定つき。knowledge SKILL の kind 表・一覧表示（concept → source → rejected の 3 段）に登録し、knowledge-lint の適用範囲を明文化（項目 7 は却下記録同士のみ・項目 8 鮮度は対象外 = ADR の append_only 免除と同扱い）。discover の allowed-tools に Edit を追加（却下履歴・index.md への追記用、command 側も同期）
- **design-rules にルール6「分割は縦に切る」を追加**（同リポジトリ to-tickets の vertical slice / expand–contract を翻案）。Issue 分割は層で横に切らず単独検証可能な縦のスライスで切る規範と、wide refactor の expand → migrate → contract 3 段分解（各段をルール3 の先行/後続で接続）。issue-maintain の detection-guards スコープ超過警告 (B) からも参照

### Changed
- design-rules.md の冒頭注記を実態に合わせ更新（linear-workflow への byte-identical 複製規約は ADR-20260722164106 のミラー規約廃止に伴い終了。既に diverge していた）

### Fixed
- issue-create Phase 6.5 の writing-polish 保護対象の記述を「9 セクション構造」から「テンプレート構造（type 別テンプレートの見出し階層）」に修正（issue-create が使う type 別テンプレは 9 セクションではなく、9 セクションは issue-design 経由のリライトでのみ適用されるため用語がずれていた）

## [1.3.0] - 2026-07-28

### Added
- **issue-maintain に worktree teardown 連携を追加**。Issue の status が completed / canceled に遷移し、Issue ブランチに紐づく worktree（境界付き grep で検出。`MYAPP-3` が `MYAPP-30` に部分一致しない）が存在する場合、**AskUserQuestion（削除する / 残す）で確認してから** `dev-workflow:worktree-teardown` を起動する（teardown は clean tree の `git worktree remove` を無確認実行するため、削除の同意は呼び出し元で取る。「起動＝実行確定」原則の唯一の例外 = git 復元不能な不可逆操作。allowed-tools に AskUserQuestion を追加、command 側も同期）。worktree 削除のトリガー点は code-review レビュー後と本スキル後の独立した 2 点で、こちらは Issue 完了側を担う。自動起動は「本実行での遷移 && worktree 内 && dev-workflow 有効（enabled-only 判定: `": true"` 明示マッチ × settings 3 ファイル走査）」のときのみ。teardown 候補のレポート列挙（非破壊）は遷移不問で行い、`--all` / main clone での残骸 worktree の受け皿はこちらが担う。cwd 消失事故を防ぐため起動は必ず全処理・最終レポート後、かつ起動前に Issue ファイル編集のコミット状況を確認する
- `_requirements` / check-deps.sh に dev-workflow（optional plugin）を追加

## [1.2.2] - 2026-07-28

### Changed
- **project-rules の「Agent Team の活用」を Opus 5 世代向けに書き換え**。無制限の委譲促進（「積極的に使う」「必要なだけ立ち上げてよい」）は Opus 5 の委譲過剰傾向でコスト増を招くため、体数上限（同時 4 体まで）と小作業の直接実行を明示する形に変更（ルート CLAUDE.md「Opus 5 世代で逆効果になる足場を書かない」①に準拠）

## [1.2.1] - 2026-07-23

### Fixed
- **set-session-title.sh が通常構成（片方 backend のみ）で毎回 silent fail する regression を修正**（self-review CRITICAL・独立反証で confirmed）。`find .claude/indie .claude/linear` は片方の dir が無いとファイルを見つけても exit 1 を返し、pipefail + ERR trap で hook 全体が exit していた。detect-backend.sh で backend を判定し有効側 dir のみを find する方式に変更（both は Validation で明示 silent exit = 他 hook と整合）
- README のスキル一覧に dashboard / linear-maintain（1.1.0 移植分）を追記
- linear-syntax.md の自己言及を統合後の実態に更新（「indie-workflow には適用しない」→ BACKEND=local、「linear-workflow にのみ存在する」→ BACKEND=linear のときのみ Read）
- follow-up N1 の `/init` 誘導と init のトリガーフレーズを `/issue-workflow:init` に統一（組み込み /init との衝突回避。他 11 箇所と同形式に）
- start Phase F4 に「Skill ツールで issue-create を実行」の明示を復元（統合時に旧 linear 版の文面から脱落し、allowed-tools の Skill 宣言が本文未言及になっていた）

## [1.2.0] - 2026-07-23

### Added
- **hooks 統合（backend 両対応）**
  - `hooks/lib/detect-backend.sh` を新設（SKILL の Phase 0 と同一述語「dir が存在し、かつ slug サブディレクトリを 1 つ以上持つ」で判定）
  - inject-rules: backend 判定に基づきルール + knowledge index + 放置 Issue 検知を注入（放置 Issue 検知は linear にも開放）。両 backend 有効時は衝突警告のみ注入、残骸 dir は注意書き + 継続
  - on-issue-change / on-knowledge-change / check-scope-size / set-session-title: パスパターンを `.claude/{indie,linear}` 両対応化（`linear:` frontmatter の ID 抽出 fallback 含む）
  - hooks.json の FileChanged matcher に `.claude/linear/` 系 3 パターンを追加
- **意図的逸脱②: check-deps の backend ゲートを新規実装**。linear-workflow から `check_mcp` を移植し、「backend=linear が有効なときのみ Linear MCP 未設定を警告」する条件分岐を追加（plugin.json の linear MCP は `required: false`。旧 linear-workflow の `required: true` から変更）

## [1.1.0] - 2026-07-23

### Added
- **linear 固有機能を移植（linear-workflow 1.37.4 から挙動等価で移送）**
  - `dashboard` / `linear-maintain` スキル・コマンド（BACKEND=local 時は案内して終了する backend ガード付き。linear-maintain の名前は「Linear と同期する」機能として正確なため現名維持で確定）
  - `linear-sync` agent と start の Context Recovery Agent #3（BACKEND=linear のみ 3 並列）
  - `issue-design` の Linear 記法 Phase + `references/linear-syntax.md`
  - start に Quick Pick / 親 Issue 軽量サマリーモード（BACKEND=linear の分岐）
  - init に Linear MCP チェック・プロジェクト情報取得・プロジェクト doc 生成 Phase
  - issue-create に Linear MCP チェック・`get_issue` 取込・`linear:`/`project:` frontmatter 分岐
  - follow-up に Linear Issue 紐づけ（N3.5）・昇格先選択（P2.5）・`save_issue` 起票分岐
  - issue-maintain に「linear-maintain からの自動呼び出し」節、quality-checklist / テンプレートに `linear:` / `linear_status:` / `project:` の backend 別注記
  - rules/project-rules.md に「Linear MCP 連携（読み取り専用ポリシー）」節

## [1.0.0] - 2026-07-23

### Added
- **初版リリース（linear-workflow / indie-workflow の単一プラグイン統合）**。設計の正本は `.claude/designs/20260722-issue-workflow-unification.md`、決定の経緯は ADR-20260722164106（ミラー規約廃止）
- indie-workflow 1.40.5 を母体に、prefix なし統一命名でスキルを再構成: init / start / issue-create / issue-design / issue-maintain / follow-up / knowledge / knowledge-lint / maintain / discover / retrospective
- **backend 自動判定（全スキル共通 Phase 0）**: `.claude/indie/`（local）/ `.claude/linear/`（linear）の「dir が存在し、かつ slug サブディレクトリを 1 つ以上持つ」を有効条件として判定。両方有効はエラー停止（slug 一覧・issues 件数・最終更新日を提示して片寄せを案内）、残骸 dir は警告 + 継続、どちらも無効は init へ誘導
- init に backend 選択（AskUserQuestion: local / linear）と backend 別ディレクトリ構造の作成を実装
- **意図的逸脱（挙動等価移送の例外）①**: indie 専用だった discover / retrospective / scope_size 管理を両 backend に開放（いずれもローカルファイル読取のみで Linear API 非依存）

### 未移送（次バージョンで移植）
- linear 固有機能: dashboard / linear-maintain / linear-sync agent / Linear 同期 Phase / linear-syntax.md（→ 1.1.0 で移植済み）
- hooks のパスパターン両 dir 対応と check-deps の backend ゲート
