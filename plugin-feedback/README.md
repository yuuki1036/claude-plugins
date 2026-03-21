# plugin-feedback

プラグインへの改善要望・バグ報告を GitHub Issue として作成するプラグイン。

## 使い方

### コマンドで明示的に起動

```
/feedback instinct-memory 学習の自動検知精度を上げてほしい
/feedback
```

### 会話中に自然に起動

会話中にプラグインへの不満や要望を言えば、AI が検知して Issue 作成を提案します。

## 前提条件

- `gh` CLI がインストール済みであること
- `gh auth login` で GitHub 認証済みであること

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/feedback` | 明示的に Issue を作成 |
| スキル | `feedback-issue` | 会話中の要望を検知して Issue 作成を提案 |
