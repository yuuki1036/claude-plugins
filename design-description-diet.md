# 設計: plugin description のダイエットと再発防止

- 作成日: 2026-06-10
- ステータス: 設計確定（実装未着手）
- 対象: code-review / writing-polish / feature-dev / dev-workflow

## 1. 背景・問題

`plugin.json` の `description` は本来「これは何のプラグインか」を marketplace 一覧やインストール時に伝える 1〜2 文の紹介文。しかし一部プラグインで、バージョンアップごとに機能詳細を description へ積層した結果、リリースノート化している。

description は `plugin.json` と `.claude-plugin/marketplace.json` の **2 箇所で二重管理**（SSoT 同期対象）のため、長いほど同期コストも増える。

## 2. 現状診断（2026-06-10 計測）

```
915字  code-review     ← 突出（リリースノート状態）
481字  writing-polish  ┐
434字  feature-dev     ├ 長い（要ダイエット）
412字  dev-workflow    ┘
─────────────────────── 健全ライン
147字  failure-journal
136字  bdd-spec
118字  notebooklm-workflow
118字  claude-meta
107字  doc-freshness
 95字  adr-keeper
 92字  guardrail-protect
 82字  plugin-manager
 73字  linear-workflow
 63字  indie-workflow
 52字  plugin-feedback
```

問題は全 15 個ではなく **上位 4 つだけ**。下位 11 個（52〜147字）はすでに健全。80/20 でこの 4 つを削れば足りる。

落とす詳細情報は CHANGELOG.md と各 SKILL.md にすでに存在するため、description から削っても情報は失われない。

## 3. 確定した設計判断

| 項目 | 確定値 | 理由 |
|---|---|---|
| 上限文字数 | **160 字**（超過で warning） | 健全グループ最長（failure-journal 147字）が引っかからず、太った 4 つだけが対象になる閾値 |
| 強制レベル | **warning のみ**（非ブロッキング） | 既存の `auto-quality-check.sh`（Stop hook）の非ブロッキング方針に合わせる。一時的に長くしたい時も止めない |
| リライト対象 | **上位 4 つのみ** | code-review / writing-polish / feature-dev / dev-workflow。最小リスク |

## 4. 目標フォーマット

```
<対象>を<どうする>。<差別化を1文>。
```

例（code-review: 915字 → 約120字）:

> Phase 0 トリアージ + 動的エージェント構成のコードレビュー。confidence × severity の 2 軸でフィルタし、PR レビューとコミット前セルフレビューの両方に対応。

## 5. 実装タスク

### Phase 1: リライト（上位 4 つ）
- 各 description を 160 字以内に圧縮
- 落とす詳細が CHANGELOG.md に既出か確認 → 無ければ先に CHANGELOG へ退避
- `plugin.json` と `.claude-plugin/marketplace.json` の両方を更新

### Phase 2: SSoT 同期 + バージョン
- PATCH bump（× 4 プラグイン）
- 各 CHANGELOG.md に「description 簡素化」エントリ追加
- `.claude-plugin/scripts/validate-ssot.sh` で同期検証

### Phase 3: 再発防止（機械強制 / 設計の本体）
- `validate_plugin_quality.py` に「description > 160 字で warning」チェックを追加
- `auto-quality-check.sh`（Stop hook）経由で発火することを確認

## 6. 設計の根拠

Phase 3 が本体。CLAUDE.md の「CLAUDE.md → Hook 昇格」の判断基準に該当する:

- 同じ違反（description 肥大）が 2 回以上発生している（code-review が v2.25.0 まで積層）
- 判定ロジックがルールベースで表現可能（文字数カウント = 決定的）

→ 規約（CLAUDE.md に「短く書け」と記載）では再発するため、機械強制に昇格させる。手でリライトするだけでは、強制がない限りまた積層する。

## 7. 未確定 / 次アクション

- この設計で実装に進むか、ADR（`/adr`）に判断を記録してから進むかは未確定
- ADR 化する場合のタイトル例: 「plugin description は 160 字以内（warning 強制）」
