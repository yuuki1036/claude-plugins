# Common Spec Template

`{featuresDir}/common_spec.md` のテンプレート。横断 Background / 権限 / 閾値 / エラーメッセージのデフォルトを定義する。

```markdown
---
last-validated: {CREATED_DATE}
phase: current
---

# 共通仕様（common_spec.md）

全フィーチャーが従う共通の前提・閾値・エラー仕様。
個別 `spec.md` はここを参照する。

---

## Background（共通前提）

全 Scenario が暗黙的に持つ前提:

```gherkin
Given システムは稼働中である
And 認証セッションは有効である
And API rate limit に達していない
```

> 個別 spec.md の Background でこれを上書きしたい場合は、明示的に書く。

---

## 権限マトリクス

| ロール | 閲覧 | 作成 | 承認 | 削除 |
|--------|------|------|------|------|
| viewer | ○ | × | × | × |
| editor | ○ | ○ | × | × |
| contract-admin | ○ | ○ | ○ | × |
| super-admin | ○ | ○ | ○ | ○ |

> 各 spec.md で「このフィーチャーを使えるロール」を Background に明示する。

---

## デフォルトエラーメッセージ

| HTTP / 状態 | エラーID | メッセージ | 対応 |
|------------|---------|-----------|------|
| 401 Unauthorized | ERR-AUTH-001 | "認証が必要です。再ログインしてください" | ログイン画面へリダイレクト |
| 403 Forbidden | ERR-AUTH-002 | "この操作を行う権限がありません" | 上位権限者に依頼を案内 |
| 404 Not Found | ERR-RES-001 | "指定されたリソースが見つかりません" | 一覧へ戻る |
| 409 Conflict | ERR-RES-002 | "他のユーザーが先に更新しました。再読み込みしてください" | reload ボタン表示 |
| 422 Unprocessable | ERR-VAL-001 | "入力内容に誤りがあります" | エラー詳細をフィールド横に表示 |
| 429 Too Many Requests | ERR-RATE-001 | "リクエストが多すぎます。しばらく待ってから再試行してください" | retry-after ヘッダー秒数表示 |
| 500 Internal Error | ERR-SYS-001 | "システムエラーが発生しました。時間をおいて再試行してください" | エラー ID を表示してサポート連絡導線 |

> 個別 spec.md は固有エラーのみ独自に定義し、共通エラーは ID 参照で再利用する。

---

## 共通閾値

| 項目 | 値 | 根拠 |
|------|-----|------|
| ページネーション 1 ページあたり | 50 件 | UI 表示パフォーマンス |
| 一括操作上限 | 100 件 | バックエンド処理時間制約 |
| ファイルアップロード上限 | 10MB | S3 multipart 閾値 |
| セッション有効期間 | 30 分 | OWASP 推奨 |
| パスワード最小長 | 12 文字 | NIST SP 800-63B |
| アカウントロック試行回数 | 5 回 | 一般的なベストプラクティス |

---

## 監査ログ要件

全 mutation 操作（作成 / 更新 / 削除 / 承認）は監査ログに記録する:

- timestamp（UTC）
- actor user_id
- action（CRUD + 業務固有動詞）
- resource type + id
- before / after（差分のみ）
- request_id（トレース用）

> 個別 spec.md で「このフィーチャーで監査対象になる操作」を明記する。

---

## 設計判断

### Background を common_spec に集約した理由

- 全 Scenario で「ログイン済み」を毎回書くと冗長
- 認証要件が変わったとき（例: MFA 追加）に common_spec.md 1 箇所修正で済む

### エラーメッセージを ID 化した理由

- 文言だけだとレビューで「言い回し」議論に陥りやすい
- ERR-AUTH-001 のような ID を持つと、Scenario で `Then ERR-AUTH-001 が表示される` のようにテストが書ける
- i18n 対応時もキーとして再利用可

### 閾値の「根拠」列を必須にした理由

- 「とりあえず 100」と書くと、後で変更要求が来た時に根拠不明で議論が止まる
- 業界規格（OWASP, NIST）やビジネス制約を明示することで、変更時の意思決定が早くなる
```

## 運用ルール

1. **common_spec.md は変更頻度が低い**: 共通仕様の変更は影響範囲が広いため、慎重に扱う
2. **個別 spec.md のローカル例外は spec.md に書く**: common_spec.md を上書きしたい場合は spec.md 側で明示
3. **`last-validated` を四半期ごとに更新**: 共通仕様は陳腐化しないか定期レビューする
