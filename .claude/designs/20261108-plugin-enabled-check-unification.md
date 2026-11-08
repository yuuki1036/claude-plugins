---
id: 20261108-plugin-enabled-check-unification
title: 他プラグインの有効判定を plugin-enabled.sh にそろえる（#423）
status: approved
phase: current
last-validated: 2026-11-08
supersedes: []
superseded-by: null
issue: "#423"
spec: null
adrs: []
tags: [plugin-enabled, dormant, check-deps, validate-plugin-quality]
---

# 他プラグインの有効判定を plugin-enabled.sh にそろえる（#423）

## TL;DR

他プラグインが有効かをキーの有無だけで判定している 10 行を、各プラグインに同梱した `plugin-enabled.sh`（正本 `.claude-plugin/lib/plugin-enabled.sh`）の呼び出しに寄せる。同型の判定が新しく書かれたら `validate_plugin_quality.py` の warning で拾う。

## 背景 / 課題

正本の判定は settings を user → project → local の順に読み、`true` / `false` の明示値で決める。次の 10 行は user の `~/.claude/settings.json` だけを見て、キーの有無で判定している。`false` で無効化したものを有効と誤り、project の settings だけで有効化したものを未導入と誤る。

- `design-doc/skills/design-doc/SKILL.md`（bdd-spec・writing-polish・adr-keeper）
- `dev-workflow/skills/git-commit-helper/SKILL.md`・`dev-workflow/skills/pr-creator/SKILL.md`（writing-polish）
- `code-review/references/closing-flow-guide.md`（writing-polish）
- `check-deps.sh` の `check_plugin`（code-review・dev-workflow・issue-workflow・feature-dev）

## ゴール / 非ゴール

- **ゴール**: 上の 10 行が正本と同じ判定を使う。同型の判定が新しく書かれたら機械で拾う
- **非ゴール**: 値まで見ているが正本を使っていない inline の判定（spec-advisor の hook・code-review の worktree-teardown-flow.md・project-hub の living-spec-maintain）の置き換え。誤判定を起こしていないので別の作業にする

## 確定した前提

- 同型の判定はプラグイン配下で上の 10 行だけ（`git grep` で確認。`.claude/designs/` の 2 件は過去の設計書の引用）
- check-deps.sh は SessionStart hook で、`CLAUDE_PLUGIN_ROOT` と `CLAUDE_PROJECT_DIR` が渡される
- Bash tool の環境には `CLAUDE_PLUGIN_ROOT` が無い。md の断片の `${CLAUDE_PLUGIN_ROOT}` は skill・command の本文として注入されたときだけ展開され、references/ や SKILL.md を Read で読んだ経路では文字のまま残りうる
- design-doc には `scripts/` が無く、dev-workflow には `scripts/` はあるが複製が無い
- `validate_ssot.py` が check-deps.sh の `check_plugin "<name>"` の呼び出し行と plugin.json の `_requirements` の一致を見ている

## 採用案

- md の 6 か所は `echo "X=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" <name>)"` の 1 行にする。Bash の状態は呼び出しをまたがないので、値を出力に出す（前例 `issue-workflow/skills/issue-create/SKILL.md`）。出力が空（スクリプトを起動できなかった）なら `${CLAUDE_PLUGIN_ROOT}` を実パスに直して再実行し、起動の失敗を「無効」と同じに扱わない
- check-deps.sh は `check_plugin` の本体だけを替え、呼び出し行は変えない。`state=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" "$name" 2>/dev/null) || state=0` の後に `if [ "$state" = 1 ]; then return 0; fi`。WARN の文言は「未導入か無効です」
- design-doc と dev-workflow の `scripts/` に正本と byte 一致する複製を置き、`validate_plugin_quality.py` の `BYTE_REPLICAS` と CLAUDE.md の構造説明を更新する
- `validate_plugin_quality.py` に per-plugin の warning 検査 `check_plugin_enabled_key_only` を足す
  - 対象: 各プラグインの `**/*.md` と `**/*.sh`
  - md は行内コードを除いてから照合し、sh はコメント行を飛ばす
  - 除外: `CHANGELOG.md`・`scripts/plugin-enabled.sh`・`evals/results/`
  - 検出: grep のフラグの後に `'"<name>@` か `"\"${name}@` が来て、直後に引用が閉じる形。値まで見る grep は `@` の後に `[^"]*"` が続くので掛からない
  - 導入前の検出は対象の 10 件、修正後は 0 件
- テスト: `test_validate_plugin_quality.py` に検査のクラス（黙る条件を厚く）、`test_misc_hooks.py` に check-deps の settings 3 層のケース（project だけで true・user が true で local が false など）
- 版を上げるプラグイン: code-review / design-doc / dev-workflow / feature-dev / issue-workflow

## 検討した代替案

| 観点 | 案 A: plugin-enabled.sh（採用） | 案 B: installed_plugins.json |
|------|------------|------|
| 判定の述語 | SKILL 側の dormant 判定と同じ 1 つ | 「導入済みか」の別の述語 |
| `false` で無効化したもの | 毎セッション WARN（未導入か無効） | 黙る |
| 依存するもの | settings の形（公開の設定） | Claude Code の内部ファイルの形 |

- 案 B は無効化したものに WARN を出さずに済むが、内部ファイルの形への依存と jq / python での読み取りが増えるため採らない（2026-11-08 決定）

## 設計判断ログ

- [local] check-deps.sh は `plugin-enabled.sh` に寄せ、無効化したプラグインにも WARN を出す（2026-11-08 決定）
- [local] 検査は errors ではなく warning にする。導入時点の検出 10 件をすべてこの変更で直すので、以後は新しく書かれた行だけが鳴る

## 未解決事項 (open)

なし

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: 呼び出し元ワークフロー（feature-dev）内で実装を続けるため省略
2. 検証方法: `validate_plugin_quality.py` の新しい検査が repo で 0 件・`BYTE_REPLICAS` の一致・回帰テスト（`run-tests.py`）の緑
3. 実装完了時の doc 更新手順:
   - frontmatter の `phase: target` → `current` に更新、`last-validated` を更新
   - 実装と乖離した箇所があれば追記、方式ごと変わったなら supersede

## 関連

- 関連 Issue: GitHub #423
- 関連 spec: なし
- 関連 ADR: なし
- 関連 design doc: なし
