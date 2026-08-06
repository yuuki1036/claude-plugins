### re-explore（Phase 5.5 適応的追加探索 / v2.12.0 追加）

```
## フォーカス: 適応的追加探索（reviewer の unmet_information に応答）

対象: {target_from_unmet_information}
元 reviewer の問い: {why_from_unmet_information}
関連指摘: {related_finding_summary}

### 背景

このタスクは、初回 reviewer が「追加の context があれば確信度が上がる」と申告した unmet_information への応答として起動された。元 reviewer は対象の周辺情報が不足しているため、確定的な判断ができていない。あなたの探索結果が直接 reviewer の確信度を変える。

### 実行手順

1. 元 reviewer の問い（why）を読み、何が分かれば判断できるかを特定する
2. 必要に応じて Read / Grep / Bash (git blame / git log) で対象周辺を調査する
3. 元 reviewer が「自分では届かない」と判断した範囲を重点的に確認する:
   - 呼び出し元の網羅的列挙（直接呼び出しだけでなく、re-export 経由・動的呼び出しも）
   - 関連する type / interface の利用箇所
   - 設定ファイル / 環境変数 / Issue 仕様との整合
4. 「reviewer の確信度を 60-79 から 80+ に押し上げる、または逆に 60 未満に下げる」決定的な事実を探す
5. 結論を簡潔に出す（過剰な情報は逆効果）

### 出力の重点

- 元 reviewer が確信度を確定できる具体的な事実
- 「該当する利用箇所は N 箇所、いずれも X として使われている」のような定量的な事実
- 「該当する利用箇所はない」も重要な事実（確信度を上下する根拠になる）

通常の出力フォーマット（重要な発見・コードフロー・副作用・依存関係）に従いつつ、**末尾に `#### unmet への直接回答` セクションを追加** し、元 reviewer の why に対して 1-3 文で結論を述べること。
```
