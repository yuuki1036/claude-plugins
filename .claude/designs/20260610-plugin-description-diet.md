---
id: 20260610-plugin-description-diet
title: plugin description のダイエットと再発防止
status: approved
phase: current
last-validated: 2026-08-28
supersedes: []
superseded-by: null
issue: 183
spec: null
adrs: []
tags: [plugin-description, ssot, quality-check, hook]
---

# 設計: plugin description のダイエットと再発防止

> 2026-06-25 リポジトリ root 直置きの孤立メモ（`design-description-diet.md`）を `.claude/designs/` 配下へ移管し design-doc frontmatter を付与（doc-freshness 管理下に入れるため）。
>
> **2026-08-28 実装完了（GitHub issue #183）。** 承認後 63 日 `phase: target` のまま追跡が消えており、その間に対象値は悪化していた（code-review 915 → 2177 字 / writing-polish 481 → 980 字）。放置を検出できなかった構造要因は、doc-freshness の SessionStart stale 監視が opt-in（`.claude/doc-freshness.json` 不在）でこのリポジトリでは一度も走っていなかったこと。
>
> **閾値は 160 → 400 に変えた。** 下の §3 は 2026-06 の分布（超過 4 件）に合わせた値だが、2026-08 に測り直すと 17 中 14 件が超過し、そのまま入れると警告の壁になる（`docs/rule-placement.md`「真陽性ゼロの警告は既存の全警告の信頼度を下げる」）。**方法（健全グループの上に閾値を置き、太ったものだけを対象にする）は維持し、値だけを現在の分布から導き直した** — 358 字と 502 字の間に自然な切れ目があり、400 なら対象は 5 件。全プラグインが健全域へ寄ったら段階的に下げてよい。

- 作成日: 2026-06-10
- ステータス: **実装完了**（2026-08-28）
- 対象: code-review / writing-polish / dev-workflow / feature-dev / living-spec-workflow（当初の 4 つに living-spec-workflow を追加。設計後に新設され同じ経路で肥大した）

## 1. 背景・問題

`plugin.json` の `description` は本来「これは何のプラグインか」を marketplace 一覧やインストール時に伝える 1〜2 文の紹介文。しかし一部プラグインで、バージョンアップごとに機能詳細を description へ積層した結果、リリースノート化している。

description は `plugin.json` と `.claude-plugin/marketplace.json` の **2 箇所で二重管理**（SSoT 同期対象）のため、長いほど同期コストも増える。

## 2. 現状診断（2026-06-10 計測）

```
915字  code-review     ← 突出（リリースノート状態。2.27.0 でさらに増）
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

## 7. 実装結果（2026-08-28 / GitHub issue #183）

| プラグイン | before | after |
|---|---:|---:|
| code-review | 2177 字 | 196 字 |
| writing-polish | 980 字 | 163 字 |
| dev-workflow | 624 字 | 173 字 |
| living-spec-workflow | 586 字 | 183 字 |
| feature-dev | 502 字 | 201 字 |

Phase 3（機械強制）は `validate_plugin_quality.py` の `check_plugin_description_size`
として実装した（`PLUGIN_DESC_CHAR_LIMIT = 400` / 非ブロッキング warning）。
**リライト後は 1 件も発火しない**ことを実測で確認している — 既存 corpus で鳴り続ける
warning を入れないのが `docs/rule-placement.md` の要件。

ADR 化は見送った。閾値は分布に応じて動かす運用値であり、「覆すコストが大きい判断」という
ADR の記録価値ゲート（`adr-keeper`）に当たらない。値を動かす理由と手順は本 doc に残す。

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: Phase 1（リライト ×4）→ Phase 2（bump + CHANGELOG + marketplace 同期）→ Phase 3（`validate_plugin_quality.py` に 160 字 warning 追加 + auto-quality-check 発火確認）
2. 検証方法: `validate-ssot.sh` 同期 OK + `validate_plugin_quality.py` で長い description に warning が出ること（Phase 3 後）
3. 実装完了時: 本 doc の `phase: target → current`、`last-validated` 更新。160 字ルールを ADR 化するなら adr-keeper へ
