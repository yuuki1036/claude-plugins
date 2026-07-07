# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.3.0] - 2026-07-07

### Added
- **イベント駆動の鮮度検知 hook を追加（Phase 2 予約分の実装。GitHub issue #79）**。従来の手動走査（skill）に加え、決定的検証を Hook に置いて遵守率 100% に寄せる:
  - **`frontmatter-guard.sh`（PostToolUse: Edit/Write/MultiEdit）**: frontmatter 必須の project doc（`.claude/designs/` `.claude/adr/`）への .md 作成/編集時に `last-validated` / `phase` の欠落を grep ベースで検知し、`additionalContext` で**非ブロッキング**警告する。frontmatter キーの存在チェックは決定的なので Hook に昇格（ルート CLAUDE.md「ルール配置の意思決定」）。ブロックしないため PreToolUse の failure mode（新規 doc 作成阻害）を回避
  - **`stale-check.sh`（SessionStart: once, opt-in）**: `.claude/doc-freshness.json` の `sessionStartCheck: true` を有効化したときのみ、対象 doc の stale をセッション開始時に 1 回まとめて通知。毎セッションのノイズを避けるため既定 off。`append_only: true` / `phase: superseded` は skill Phase 3 と同基準で免除
- **hook 設定を `references/hook-config.md` に文書化**。`hookTargets`（対象 path prefix）/ `postToolUseCheck` / `sessionStartCheck` を `.claude/doc-freshness.json` に追加
- 対象は frontmatter 必須の project doc（`.claude/designs/` `.claude/adr/`）に限定。プラグイン内部 doc（SKILL.md / references/ / README）は含めない（version + CHANGELOG で鮮度管理され、`last-validated` を付けると恒常 stale 化するため。ルート CLAUDE.md 規約）

## [0.2.0] - 2026-07-02

### Added
- **append-only 履歴文書の stale 免除**: frontmatter に `append_only: true` を持つファイルは Phase 3（stale 判定）を免除する。ADR（`.claude/adr/`）のように作成後に内容が固定される append-only 文書は `phase: current` の stale 閾値（5 日）で作成直後から恒常 stale になり委譲が破綻するため。免除は stale 判定のみで、frontmatter スキーマ・link・superseded 参照は通常どおり検証（adr-keeper のテンプレが付与）
- **走査対象に dot ディレクトリ配下を明示追加**: `.claude/adr/**/*.md`（adr-keeper）と `.claude/designs/**/*.md`（design-doc）を Phase 1 の走査対象に加えた。Glob の `**` は既定で dot ディレクトリを拾わず、両プラグインが謳う鮮度 lint 委譲が silent に不成立だった不具合を修正
- Phase 8 の自動修正（frontmatter 一括追加 / last-validated 更新）を実行できるよう `allowed-tools` に `Edit` / `Write` を追加（command / skill のペアで一致）

### Changed
- **grace period 内の frontmatter 欠落の重大度を warn に統一**（従来は SKILL 本文・Phase 2 表・frontmatter-spec で info / error / warn と不一致）。grace period 内 = warn / grace period 外 = error に 3 箇所を揃えた
- 作成日時取得スニペットを修正: Linux GNU stat の `%W`（birth time）が非対応 fs で `0` を返すケースを検知して mtime（`%Y`）へ明示フォールバックする分岐に変更（従来は `0` を巨大 age として誤用）
- Phase 1 の除外規則を具体化（生成物ディレクトリ・`.claude/adr`/`.claude/designs` 以外の `.claude/` 配下・プロジェクトツリー外を明示）

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#48)。Phase 1 として command + skill のみ実装。hook 連動は Phase 2 で別途検討
- `commands/doc-freshness-check.md`: プロジェクト全体または指定ファイルの鮮度走査
- `skills/doc-freshness/SKILL.md`: frontmatter スキーマ検証 / phase 別 stale 判定 / 行数ガード / internal link 検証 / superseded 参照禁止 / 新規 doc grace period
- `references/frontmatter-spec.md`: `last-validated` / `phase` の定義と運用ルール
- `references/thresholds.md`: 閾値のデフォルト値と上書き方法

### Notes
- PreToolUse hook は採用しない設計（新規 doc 作成時の failure mode を回避）
- knowledge-lint との責務分離（broken wikilink / orphan は knowledge-lint 側）
