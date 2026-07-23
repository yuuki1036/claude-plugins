# frontmatter スキーマ仕様

doc-freshness が要求するドキュメント frontmatter の定義。

## 必須フィールド

```yaml
---
last-validated: 2026-05-29   # ISO 8601 (YYYY-MM-DD)
phase: current               # current | target | superseded
---
```

### `last-validated`

最終検証日。**手動更新**で、ドキュメントの内容を確認し問題ないと判断した日付を入れる。

- 書式: `YYYY-MM-DD`（ISO 8601 のうち date 部分のみ）
- 時刻 / タイムゾーンは含めない（doc レベルでの精度で十分）
- 検証作業 = レビュー、または「内容を読み直して齟齬がないことを確認」のいずれか

### `phase`

ドキュメントのライフサイクル段階。enum で 3 値:

| 値 | 意味 | stale 閾値（デフォルト） |
|---|---|---|
| `current` | **現行ドキュメント**。本日時点で有効な仕様・規約・運用 | 60 日（warn） |
| `target` | **将来計画**。target architecture / roadmap など、未着手だが目標として残す | 15 日 |
| `superseded` | **廃止済み**。historical な記録として残すが現行には使わない | （stale 判定対象外） |

## 任意フィールド

doc-freshness は以下のフィールドを認識する（必須ではない）:

```yaml
---
last-validated: 2026-05-29
phase: current
owner: team-platform        # 任意: 責任主体
supersedes: ./old-spec.md   # 任意: 廃止した旧 doc への参照
append_only: true           # 任意: append-only 履歴文書（stale 判定を免除）
---
```

- `owner` — レポート時に表示される（責任不明の stale doc を放置しないため）
- `supersedes` — `phase: current` への遷移時に、旧 doc を `superseded` に変える運用補助
- `append_only` — `true` のとき **stale 判定（Phase 3）を免除**する。ADR（`.claude/adr/`）のように「決定時点の記録を append-only で残す」文書は作成後に内容が変わらないのが正常挙動で、`phase: current` の stale 閾値を当てると作成直後から恒常 stale になるため。免除は stale 判定のみで、frontmatter スキーマ・link・superseded 参照は通常どおり検証する。付与するのは adr-keeper のテンプレ（accepted ADR）。design doc は `phase: target → current` で鮮度を測る生きた文書なので付けない

## 運用ルール

1. **新規 doc 作成時**: frontmatter を付けて作成する。grace period（デフォルト 7 日）以内は付与忘れでも warn 扱い
2. **doc 変更時**: 本質的な内容変更があれば `last-validated` を更新する
3. **phase 遷移**:
   - `target` → `current`: 計画が実装され現行になった時
   - `current` → `superseded`: 仕様が変わって旧版を残す時。新版に `supersedes: ./old.md` を付けると追跡しやすい
   - `superseded` への retrograde は禁止しないが、通常は doc 削除のほうが望ましい

## 設計判断

- **`phase` を 3 値に固定**: より細かい状態（draft / review / approved / deprecated）も検討したが、`last-validated` で鮮度を測れば draft / review は不要、approved は `current` で十分、deprecated は `superseded` で表現できる
- **`last-validated` は手動更新**: 自動更新（git の最終コミット日など）も検討したが、「内容変更なしに mtime だけ動く」ケースで誤判定が出るため、明示的なレビュー行為を強制する
- **時刻を含めない**: 監査の厳密さよりも記入の手軽さを優先（doc 鮮度は日単位で十分）

## アンチパターン

❌ **`last-validated` を CI で自動更新** — 「常に新鮮」状態になり stale 検出が機能しなくなる

❌ **すべての doc を `phase: current` にする** — `target`（未来計画）と `current` を混在させると stale 閾値が機能しない

❌ **`superseded` への active link を残す** — superseded は履歴のみ。active doc から参照しない（doc-freshness の Phase 6 がこれを検出）
