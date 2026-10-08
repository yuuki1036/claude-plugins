# ドキュメント優先度規約テンプレ

複数ドキュメントが矛盾するときに「どれが真か」を明示するための 3 要素テンプレ。AI agent の迷いを構造的に減らす。

## 3 要素

| 要素 | 役割 |
|---|---|
| **ノード列挙** | プロジェクト内で参照される doc / spec / 規約を全列挙 |
| **順序** | 矛盾時の優先度を `>` で表現 |
| **交渉不可ライン** | 「どれが真でも変更不可」な不変条件を明示 |

## 空テンプレート

CLAUDE.md / AGENTS.md に以下のセクションを追加する:

```markdown
## ドキュメント優先度（衝突解消ルール）

複数の規約・spec が矛盾した場合、以下の優先順位で解決する:

<高>
SPEC.md (不変条件 AC-XX は交渉不可)
  > domain-model.md
  > functional-design.md
  > API-design.md
  > CLAUDE.md / AGENTS.md（メタ規約）
  > ADR (Architecture Decision Record)
  > README.md
  > inline コメント
<低>

### 交渉不可ライン

以下は AI / 人間レビュー問わず変更不可:
- SPEC.md の `AC-001` ~ `AC-NNN`（受け入れ条件）
- セキュリティポリシー（auth/, security/ 配下の docs）
- データ保護要件（個人情報・PCI-DSS 関連）

変更が必要な場合は別途 ADR を起票し、ステークホルダー合意を経ること。
```

## ノード列挙の網羅性チェック

improver は CLAUDE.md / AGENTS.md からドキュメント参照を Grep し、漏れがあれば指摘する:

```bash
# CLAUDE.md / AGENTS.md / README.md / docs/ 配下から外部 doc 参照を抽出
grep -rohE '\[[^\]]+\]\([^)]+\.md\)' CLAUDE.md AGENTS.md README.md docs/ 2>/dev/null \
  | sort -u
```

抽出結果と「ドキュメント優先度」セクションのノード列挙を比較し、未列挙のものを suggest する。

## 順序設計の原則

優先度を決めるとき、以下の原則に従う:

1. **抽象度の高い doc が上**: spec > 設計 > 実装規約 > inline コメント
2. **不変条件が上**: 「変えてはいけないこと」を書く doc が高優先度
3. **業務要件が技術選定より上**: SPEC > API design（API design は SPEC を満たす手段）
4. **メタ規約は spec の下**: CLAUDE.md は「AI 向けガイド」であり、業務 spec を上書きしてはいけない

### アンチパターン

- **CLAUDE.md が最優先**: AI 向けガイドが業務 spec を上書きする構造は事故の温床
- **inline コメントが doc より上**: コメントは局所最適。横断規約はファイル外部に置く
- **順序が曖昧（カンマ区切り）**: `SPEC.md, design.md` のような表現は「どちらが上か」を伝えられない。必ず `>` を使う

## 交渉不可ラインの抽出ルール

improver は spec / requirements / security 関連 doc を Grep し、以下のパターンを「交渉不可候補」として抽出する:

- `AC-\d+` / `REQ-\d+` 等の番号付き受け入れ条件
- セキュリティポリシー（auth, security, crypto, secret 系のキーワード）
- 法規制関連（GDPR, CCPA, PCI-DSS, HIPAA 等のキーワード）
- データ保護（個人情報, PII, 機密データ）

抽出結果を「交渉不可ラインに含めるべきか」として suggest する。

## 既存 CLAUDE.md への適用例

### Before（優先度規約なし）

```markdown
# CLAUDE.md

## ルール
- API は OpenAPI 仕様に従う
- 関数は 50 行以内
- テストカバレッジ 80% 以上
```

### After（優先度規約あり）

```markdown
# CLAUDE.md

## ドキュメント優先度（衝突解消ルール）

SPEC.md (AC-XX 交渉不可) > openapi.yaml > CLAUDE.md > README.md

交渉不可ライン:
- SPEC.md の AC-001 ~ AC-042
- セキュリティ要件（docs/security/policy.md）

## ルール
- API は OpenAPI 仕様（openapi.yaml）に従う
- 関数は 50 行以内（ガイドライン、SPEC 要件と矛盾するなら SPEC 優先）
- テストカバレッジ 80% 以上（運用基準）
```

`openapi.yaml` の制約と関数行数制限が矛盾した場合、`openapi.yaml` を満たすために 50 行を超えても OK と明示できる。
