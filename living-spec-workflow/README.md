# living-spec-workflow

Issue 化する前段の「設計収束ドキュメント」(living spec) を作成・運用するプラグイン。**未確定を抱えていることが正常状態**の文書を、採番・書式・相互参照を機械化しながら「仮 → 確定」へ収束させる。

## 使い方

```text
/living-spec init auth-redesign                    # .claude/living-specs/auth-redesign.md を scaffold
/living-spec oq セッションストアに Redis を使うか    # OQ1 として起票（採番・since は機械付与）
/living-spec spec 認証方式 方向性(仮)               # 仕様表の確度を更新（since も機械付与）
/living-spec decision 認証は OAuth 2.0 を採用       # D1 を append し、関連 OQ を close
/living-spec oq list                               # open な OQ の一覧（--all で closed 込み）
/living-spec status                                # 収束率 + open OQ 残数 + 次に決めるもの
/living-spec                                       # usage
```

（スラッシュコマンドはシェルを経由しないので、引数はエスケープや引用符なしでそのまま書く）

第 1 引数は**常にサブコマンド**として解釈する（slug は `init` の後ろにしか置けない）。既定のサブコマンドは持たず、未知の第 1 引数も slug とみなさずエラーにする。サブコマンド名と slug 名を同じ名前空間に置くと、後からサブコマンドを追加するたびに、その語を slug に使っていた利用者の意味が変わるため。

`init` 以外は `--spec <slug>` で対象ファイルを明示指定できる（省略時: 1 件なら自動 / 複数なら選択 / 0 件なら init を案内）。

```text
/living-spec-maintain                  # 整合・鮮度を 8 段のファネルで検証
/living-spec-maintain --all            # .claude/living-specs/ の全件を点検
```

## 何が機械化されるか

| 手作業だとズレるもの | どう機械化したか |
|---|---|
| D# / OQ# の目視採番 | 既存 ID の**数値の最大 + 1**。HTML コメントを除去してから数えるので、記入例を実在 ID と誤認しない |
| close した OQ と Decision の相互参照 | `decision` が **1 コマンドで双方向を書き、直後に Read で検証**する。片方向ならその場で直す |
| 確度ラベルの `since` 更新漏れ | `spec` が `date` から機械付与する。確度が変わらなくても `since` は更新する（「今日この確度で確認した」の意味） |
| 「仮 → 確定」の収束の手集計 | `status` が確度ラベルを集計して収束率と open OQ 残数を出す |
| frontmatter `last_updated` の更新漏れ | 書き込むサブコマンドがすべて機械更新する（`last-validated` は人が maintain で更新するので触らない） |

## 成果物

`.claude/living-specs/<slug>.md`（**committed 前提**。Decision log を履歴として残すので gitignore しない）

```yaml
---
phase: target                  # doc-freshness 契約（収束中 = target）
last-validated: 2026-07-15     # doc-freshness 契約。人が内容を確認した日（maintain 実行時に更新）
last_updated: 2026-07-15       # 機械更新。init / oq / decision / spec が書き込みのたびに更新
notion_page_id: null           # v1 未使用（予約）
sync: null                     # v1 未使用（予約）
---
```

本文は 7 セクション構成。うち機械パース対象は「仕様」「Open Questions」「Decision log」の 3 つ。

| セクション | 役割 |
|---|---|
| 現在地サマリ | いま何が確定していて次に何を決めるか（3 行以内） |
| 仕様 | 項目ごとの確度ラベル（`確定` / `方向性(仮)` / `未定`）と `since` |
| Open Questions | OQ 台帳。`open` / `closed` と関連 D# の双方向参照 |
| Decision log | append-only の決定記録（D# 採番） |
| 進め方フェーズ / タイムライン / 参照ソース | 散文セクション |

## 設計の核心: 情報を move しない

OQ を close するとき、台帳から行を消して Decision へ移す設計にはしない。効き目の範囲は次のとおり。

- **情報の消失**（close した OQ が消える / 移動の途中で失敗して片方にしか無い）→ 削除を含む操作が存在しないので**構造的に起きない**
- **参照の片側漏れ**（OQ に `関連 D#` が無い等）→ 表を書くのは LLM なので起こりうる。maintain の事後検知で担保する

つまり move をやめることで消えるのは消失であって、不整合ではない。不整合の検知器を持つのはそのため。

## 点検（/living-spec-maintain）

整合と鮮度を 8 段のファネルで検証する。**安い機械判定を先頭に置き、LLM 判断は通過分にだけ当てる**。

| 段 | 何を見るか | severity |
|---|---|---|
| 1 | 表スキーマ違反 | Critical |
| 2 | 採番の重複・欠番 | Critical |
| 3 | OQ ⇔ Decision の双方向参照 | Critical |
| 4 | 「参照ソース」の外部 URL の死リンク | Warning |
| 5 | OQ の `status` と `関連 D#` の行内整合 | Warning |
| 6 | 確度ラベルの塩漬け | Warning |
| 7 | frontmatter `last_updated` の整合 | Info |
| 8 | 現在地サマリと実態のズレ（LLM 判断・`high` 以上） | Info |

段 1-3 で Critical が出たらファイルが壊れているので、段 8 には進まない。**検証を通過したときだけ** `last-validated` の更新を提案する（「内容を確認し問題ないと判断した日」なので、契約違反が残った状態で更新するのは意味に反する）。

**直すのは人**。機械的に直すのは `last-validated`（承認つき）だけで、他は修正方針を示すに留める。特に段 2 の欠番は**番号を詰めて直さない** — Critical が指しているのは「欠番という状態」ではなく「行が消えた事実」で、詰めるとその事実が見えなくなる。

## 隣接プラグインとの棲み分け

| やりたいこと | 使うもの |
|---|---|
| Issue 化前に、未確定を抱えたまま設計を収束させる | **living-spec-workflow**（本プラグイン） |
| 代替案を比較して採用案を確定し、スナップショットとして残す | `design-doc` |
| 単一の設計判断（WHY）を点で記録する | `adr-keeper` |
| Issue 1 件の作業設計（9 セクション） | `issue-workflow` の issue-design |
| 設計から実装まで一気通貫 | `feature-dev` |

living spec で確度が `確定` に寄った塊ができたら Issue 化する。living spec 側からプラグインは呼ばない（疎結合）。ユーザーが `/issue-create` / `/indie-issue-create` に手で渡す。

## doc-freshness との住み分け

| 責務 | 担当 |
|---|---|
| ファイル単位の鮮度（`last-validated` / `phase` stale）の**検出** | doc-freshness |
| frontmatter スキーマ検証 / 内部相対リンクの実在検証 | doc-freshness |
| 表スキーマ・採番・相互参照・確度ラベルの `since` stale | living-spec-workflow |
| `last-validated` の**更新**（点検を通過したときに承認つきで） | living-spec-workflow（`/living-spec-maintain` の完了処理） |

doc-freshness 未導入でも動作する。失われるのはファイル単位の stale 検出だけで、OQ / Decision / 収束の可視化は単体で成立する。

## 既知の制約

- **doc-freshness は 0.4.0 以降が必要**。`.claude/living-specs/` の走査対象への追加は doc-freshness 0.4.0 で入った。それ未満のバージョンでは鮮度 lint の委譲が成立しない（living spec が走査されず、stale が検出されない）
- **`.claude/doc-freshness.json` に `hookTargets` を設定済みのプロジェクトは注意**。`hookTargets` を指定すると hook の対象がその配列で**置き換わる**（部分追加ではない）ため、既定への追加が効かない。利用者側で `.claude/living-specs/` を配列に追記する必要がある

## install

```bash
claude plugin install living-spec-workflow@yuuki1036-claude-plugins   # マーケットプレイス経由
claude plugin install /path/to/claude-plugins/living-spec-workflow    # ローカル
```

## 構成

| 種別 | 名前 | 説明 |
|---|---|---|
| コマンド | `/living-spec` | init / oq / oq list / decision / spec / status |
| コマンド | `/living-spec-maintain` | 整合・鮮度の 8 段検証（`--spec` / `--all`） |
| スキル | `living-spec` | living spec の作成・運用（CRUD 系） |
| スキル | `living-spec-maintain` | 整合・鮮度の検証（深掘り系・`${CLAUDE_EFFORT}` 分岐あり） |
| references | `living-spec/format-spec.md` | 対象ファイル特定・表スキーマ・確度ラベル・採番規約・パース正規表現の**正本** |
| references | `living-spec/template.md` | scaffold テンプレ |
| references | `living-spec-maintain/check-rules.md` | 段 1-8 の判定内容・severity・修正方針の**正本** |
