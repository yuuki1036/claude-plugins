# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.5.1] - 2026-08-17

### Fixed
- **`postToolUseCheck: false` で hook を無効化できなかった**。jq の `//` 演算子は左辺が `false` でも「無い」扱いにするため、明示的な opt-out が既定の `true` に化けていた。素で読んで文字列比較する形に修正（回帰テスト付き）

## [0.5.0] - 2026-07-23

### Changed
- **`thresholds.current` のデフォルトを 5 日 → 60 日に変更し、超過の重大度を error → warn に降格**（`target` は 15 日 error のまま）。旧デフォルトは「current doc は週次レビューされる」前提だったが実運用で成立せず、実装済みスナップショットとして安定した design doc 全件が恒常 stale error のまま放置される「誰も見ない信号」を自リポジトリで実測した（2026-07 精査）。current の乖離は時間でなくコード変更で生じるため、時間閾値は安全網（60 日 warn）に留め、error は放置が実害に直結する target（未実装計画の塩漬け）に限定する。SKILL / thresholds / frontmatter-spec / README / stale-check.sh のデフォルトを一括更新

## [0.4.1] - 2026-07-22

### Fixed
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [0.4.0] - 2026-07-15

### Added

- **`.claude/living-specs/` を走査対象に追加**（living-spec-workflow が `_requirements` で鮮度 lint を委譲するため）。living spec は `phase: target` の生きた文書で `append_only: true` を持たないため、target 閾値（既定 15 日）で stale 判定される
  - `skills/doc-freshness/SKILL.md`: Phase 1 の走査対象リストに `.claude/living-specs/**/*.md` を追加し、**除外規則側**（「`.claude/adr/` / `.claude/designs/` を除く `.claude/` 配下」）にも反映
  - `hooks/scripts/frontmatter-guard.sh` / `hooks/scripts/stale-check.sh`: 両 hook の既定 TARGETS に追加
  - `skills/doc-freshness/references/hook-config.md`: `hookTargets` の既定値と「対象範囲の設計判断」を更新

### Changed

- `references/hook-config.md` の「対象範囲の設計判断」に、**委譲元プラグインを追加するときに同時更新すべき 6 箇所**（挙動に効く 4 + 記述に効く 2）と、受け入れ条件を実測にする旨を明記。**0.1.0 で踏み 0.2.0 で修正した** silent 不成立（走査対象への追加漏れで、委譲を宣言した側が守られていると思い込む）の再発を防ぐ

### Notes

- 除外規則が「特定 dir を**除く** `.claude/` 配下」という反対向きの規定になっているため、走査対象リストへの追加だけでは効かない。両方の更新が必須
- `.claude/doc-freshness.json` に `hookTargets` を設定済みのプロジェクトでは、既定値の変更が反映されない（指定すると配列で**置き換わる**ため）。利用者側での追記が必要

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
