# 階層化された AGENTS.md / CLAUDE.md 運用

中規模以上のプロジェクトで `backend/AGENTS.md` / `frontend/AGENTS.md` のように層別にコンテキストを分離するパターン。

## 階層化のしきい値

以下のいずれかに該当する場合、階層化を検討する。

| シグナル | しきい値 |
|---|---|
| トップレベル機能領域数 | 3 以上（例: backend, frontend, infrastructure） |
| 単一 CLAUDE.md の行数 | 300 行超 |
| 領域固有の規約数 | 領域あたり 10 項目超 |
| 異なる技術スタック | 2 以上（例: Go + TypeScript + Terraform） |
| チームの境界 | 領域ごとに別チーム |

しきい値未満なら **単一 CLAUDE.md / AGENTS.md で十分**。階層化は overhead を生むため、規模に応じて選択する。

## ディレクトリ構成例

### パターン A: 機能領域別

```
CLAUDE.md                    # @AGENTS.md 1 行参照 (3 章 OpenAI/Devin 互換性)
AGENTS.md                    # root SSoT（リポジトリ全体規約）
backend/
  AGENTS.md                  # Go / Python の規約・依存・テスト
  go/AGENTS.md               # Go 固有
  python/AGENTS.md           # Python 固有
frontend/
  AGENTS.md                  # React / TypeScript の規約
infrastructure/
  AGENTS.md                  # Terraform / CI/CD
```

### パターン B: monorepo packages 別

```
CLAUDE.md / AGENTS.md
packages/
  api/AGENTS.md
  web/AGENTS.md
  shared/AGENTS.md
  cli/AGENTS.md
```

## 階層化判定の AskUserQuestion

improver は Phase 冒頭で以下を問う:

```
question: "root 以外に backend/frontend 等の階層別 AGENTS.md / CLAUDE.md を持つ規模ですか？"
header: "階層化判定"
options:
  1. label: "単一構成（root のみ）" / description: "300 行以下、機能領域 2 以下、単一スタック。階層化なしで進める"
  2. label: "機能領域別に階層化" / description: "backend / frontend / infrastructure 等の領域別に AGENTS.md を分割"
  3. label: "monorepo packages 別に階層化" / description: "packages/{name}/AGENTS.md で package 単位に分割"
  4. label: "判定不能・相談" / description: "現状を見せて improver の suggest を聞きたい"
```

選択結果に応じて improver の suggest 内容を切り替える:

- 単一構成 → 1 ファイルに集約する template を提示
- 階層化 → 各層にどの規約を移動すべきか cross-reference を整理

## 階層化のメリット・デメリット

### メリット

- reviewer agent / Claude が **変更層の AGENTS.md のみ Read** する運用が成立（context token 削減）
- 領域固有の規約が分散しないので、領域の専門家が単独でメンテできる
- 新規参画者が領域単位でキャッチアップ可能

### デメリット

- root の SSoT がぼやけやすい → root AGENTS.md は **領域横断の規約のみ** に絞る
- 規約の重複・矛盾が発生しやすい → improver / lint で定期チェック
- 階層が深くなるほど読み手の認知負荷が増える

## アンチパターン

- **全ディレクトリに CLAUDE.md**: 細分化しすぎで context fan-out が爆発する。3 階層以下に抑える
- **領域別 AGENTS.md に root と同じ内容を複製**: 重複は規約ドリフトの温床。**差分のみ** を書く
- **階層化したのに root AGENTS.md が肥大化**: 領域固有の内容が root に残っている。定期的に下位層へ移動

## 階層化の漸進的導入

最初から完璧な階層構造を作る必要はない。以下の順で漸進的に導入する:

1. 単一 CLAUDE.md / AGENTS.md でスタート
2. 行数が 300 を超え、領域 3 以上になったら最初の階層化を検討
3. 領域別 AGENTS.md を 1 つだけ作り、root から領域固有規約を移動
4. 各領域の improver / code-review で「分割後の重複・乖離」を継続的にチェック

## 関連: 階層 AGENTS.md を活用する skill

- `code-review`: 変更ファイルパスから対応する `{dir}/AGENTS.md` を `scripts/triage-signals.sh` が探索し（`## agents-md` セクション）、ヒットしたパスを reviewer プロンプトに渡して agent 自身に Read させる（本文は転記しない。規約は `references/prompts/reviewer-common.md`）
- `feature-dev`: Phase 1 の探索フェーズで該当層の AGENTS.md を優先読み込み
