# issue-workflow 移行チェックリスト（全マシン）

linear-workflow / indie-workflow → issue-workflow の移行状況をマシン単位で管理する。
**全マシンにチェックが入ったら旧 2 ディレクトリ（`linear-workflow/` / `indie-workflow/`）を削除する**（独立コミット。未移行マシンが後から見つかったら削除コミットを revert すれば marketplace 解決先が復活する）。

- 設計の正本: `.claude/designs/20260722-issue-workflow-unification.md`（移行手順 7〜8）
- 決定の経緯: ADR-20260722164106（ミラー規約廃止）

## 移行手順（各マシンで連続実行する）

**新旧の同時 install は禁止**（issue-workflow は indie 母体のため、同居すると SessionStart / FileChanged / PostToolUse hook が同一 `.claude/indie` に対して二重発火し、prefix なし統一名によりトリガーフレーズも衝突する）。

```bash
claude plugin uninstall linear-workflow
claude plugin uninstall indie-workflow
claude plugin install issue-workflow@yuuki1036-claude-plugins
```

- データディレクトリ（`.claude/indie/` / `.claude/linear/`）はそのまま使える（rename 不要）
- 移行後に任意のプロジェクトで `/issue-workflow:start` を実行し、backend が正しく検出されることを確認する
- 完了したら下表にチェックを入れてコミットする

## マシン一覧

| マシン | 移行完了 | 実施日 | 備考 |
|--------|:-------:|--------|------|
| yukis-MacBook-Pro-2023 | [ ] | | このリポジトリの主開発機 |
<!-- 他のマシンは移行実施時にこの表へ追記する（auto-memory はマシンローカルで同期されないため、一覧の完全性は各マシンでの追記に依存する） -->

## 全マシン完了後のタスク

- [ ] eval 回帰テスト実行（`evals/cases/issue-workflow.yaml`、pass^k=3。旧 2 プラグイン uninstall 済み状態で実行）
- [ ] 両 backend のスモーク: `.claude/indie` 持ちと `.claude/linear` 持ちプロジェクトで start / issue-create / issue-maintain を実走
- [ ] 旧 2 ディレクトリの削除（独立コミット・revert 可能に他の変更と混ぜない）
- [ ] design doc「関連」に削除コミット hash を追記
