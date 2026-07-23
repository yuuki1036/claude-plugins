# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
