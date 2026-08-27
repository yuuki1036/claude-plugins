# issue-workflow 移行チェックリスト（全マシン）

**移行は完了している。** 旧 `linear-workflow/` / `indie-workflow/` は 2026-08-17 の
[`314413c`](https://github.com/yuuki1036/claude-plugins/commit/314413c9f4243cf24e054ee9f6c3dd8cfbf2e1b5)
（GitHub issue #94）でリポジトリから削除した。本 doc は移行の記録として残す。

- 設計の正本: `.claude/designs/20260722-issue-workflow-unification.md`（移行手順 7〜8）
- 決定の経緯: ADR-20260722164106（ミラー規約廃止）

## 未移行マシンが後から見つかったら

**`/update-all` による自動移行はもう使えない**（GitHub issue #184）。marketplace.json から
旧 2 プラグインのエントリごと消えたため、`_superseded_by: issue-workflow` を検出する経路が
存在しない。手動で以下を実行する（`issue-workflow` のエントリは健在なので install は解決する）:

```bash
claude plugin uninstall linear-workflow
claude plugin uninstall indie-workflow
claude plugin install issue-workflow@yuuki1036-claude-plugins
```

**新旧の同時 install は禁止**（issue-workflow は indie 母体のため、同居すると SessionStart /
FileChanged / PostToolUse hook が同一 `.claude/indie` に対して二重発火し、prefix なし統一名に
よりトリガーフレーズも衝突する）。

- データディレクトリ（`.claude/indie/` / `.claude/linear/`）はそのまま使える（rename 不要）
- 移行後に任意のプロジェクトで `/issue-workflow:start` を実行し、backend が正しく検出されることを確認する

## マシン一覧

| マシン | 移行完了 | 実施日 | 備考 |
|--------|:-------:|--------|------|
| yukis-MacBook-Pro-2023 | [x] | 2026-08-17 | このリポジトリの主開発機（旧 2 プラグインが未インストールであることを 2026-08-28 に確認） |
<!-- 他のマシンは移行実施時にこの表へ追記する（auto-memory はマシンローカルで同期されないため、一覧の完全性は各マシンでの追記に依存する） -->

## 全マシン完了後のタスク

- [x] 旧 2 ディレクトリの削除（`314413c` / 2026-08-17・独立コミット）
- [x] design doc「関連」に削除コミット hash を追記（2026-08-28 / #184）
- [ ] eval 回帰テスト実行（`evals/cases/issue-workflow.yaml`、pass^k=3。旧 2 プラグイン uninstall 済み状態で実行）
- [ ] 両 backend のスモーク: `.claude/indie` 持ちと `.claude/linear` 持ちプロジェクトで start / issue-create / issue-maintain を実走

> 残り 2 件は**削除の前提条件ではなく事後の確認**なので、削除済みの現状でも未実施のまま残せる。
> evals はローカル実行のみで通常セッション枠を消費するため（`evals/README.md`）、実施するときは
> 意図的に時間を取る。
