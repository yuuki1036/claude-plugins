# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.0.0] - 2026-07-23

### Added
- **初版リリース（linear-workflow / indie-workflow の単一プラグイン統合）**。設計の正本は `.claude/designs/20260722-issue-workflow-unification.md`、決定の経緯は ADR-20260722164106（ミラー規約廃止）
- indie-workflow 1.40.5 を母体に、prefix なし統一命名でスキルを再構成: init / start / issue-create / issue-design / issue-maintain / follow-up / knowledge / knowledge-lint / maintain / discover / retrospective
- **backend 自動判定（全スキル共通 Phase 0）**: `.claude/indie/`（local）/ `.claude/linear/`（linear）の「dir が存在し、かつ slug サブディレクトリを 1 つ以上持つ」を有効条件として判定。両方有効はエラー停止（slug 一覧・issues 件数・最終更新日を提示して片寄せを案内）、残骸 dir は警告 + 継続、どちらも無効は init へ誘導
- init に backend 選択（AskUserQuestion: local / linear）と backend 別ディレクトリ構造の作成を実装
- **意図的逸脱（挙動等価移送の例外）①**: indie 専用だった discover / retrospective / scope_size 管理を両 backend に開放（いずれもローカルファイル読取のみで Linear API 非依存）

### 未移送（次バージョンで移植）
- linear 固有機能: dashboard / linear-maintain / linear-sync agent / Linear 同期 Phase / linear-syntax.md
- hooks のパスパターン両 dir 対応と check-deps の backend ゲート
