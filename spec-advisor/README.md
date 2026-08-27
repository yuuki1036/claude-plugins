# spec-advisor

開発タスクの内容から、**実装に着手する前に**「どの設計・計画系成果物を先に書くべきか」を判断して提案するプラグイン。

## 何をするか

タスクを 5 つの軸に分類し、該当する既存プラグインの skill を提案・起動する。

| 軸 | 何を残すか | 委譲先 |
|---|---|---|
| WHAT | ユーザー可視な振る舞い・受け入れ条件 | `bdd-spec:create-spec` |
| HOW | 技術方式の選定・代替案比較（面の設計） | `design-doc:design-doc` |
| WHY | 単一の重要な設計判断（点の記録） | `adr-keeper:adr` |
| Issue 粒度 | 1 Issue の作業設計（9 セクション） | `issue-design`（issue-workflow） |
| 実装一気通貫 | 設計から実装まで進める | `feature-dev` |

判定の正本は [`skills/spec-advise/references/routing-rubric.md`](skills/spec-advise/references/routing-rubric.md)。

## 2 つの起動経路

- **Ambient**: SessionStart hook が短い標準指示を注入し、開発タスクを説明したときに自動でルーティングを促す。提案先の設計プラグインが 1 つも入っていなければ何も注入しない（inert）。
- **明示**: `/spec-advise` または「何から設計する？」「先に仕様書く？」等のフレーズで `spec-advise` skill を起動。

## 設計方針

- **over-suggestion 抑制**: bugfix / typo / 設定変更 / 軽微 refactor には提案しない。ファネルの先頭で「不要」を落とし、確信を持てたときだけ提案する。
- **確信度ベース**: 明確なら質問せず 1 文の根拠で提案、迷うときだけ `AskUserQuestion`。提案は 1 回のみ。
- **プラグイン独立**: 連携先はすべて optional。`grep settings.json` の dormant 判定で未導入プラグインは提案肢から外す。全て未導入なら沈黙する。
- **effort 分岐**: `high` 以上ではタスク説明だけでなく関連 Issue / コードを軽く読んで影響範囲を裏取りしてから判定する。

## 依存（すべて optional）

`bdd-spec` / `design-doc` / `adr-keeper` / `feature-dev` / `issue-design`（`issue-workflow`）。1 つも無い環境では advisor は inert。
