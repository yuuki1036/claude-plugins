# backend-detect — issue-workflow Phase 0 の backend 検出（正本）

issue-workflow の各スキルの Phase 0 に置く backend 検出手順の正本。下の delimiter 区間を消費サイトに複製して埋め込む。
判定述語（「dir が存在し、かつ slug サブディレクトリを 1 つ以上持つ」）は hook 側の `hooks/lib/detect-backend.sh` と揃えている。

- 消費サイト: `issue-workflow/skills/*/SKILL.md` のうち共通の Phase 0 を持つもの（`validate_plugin_quality.py` の `BACKEND_DETECT_CONSUMERS`）。
  init（backend を選ぶ側）・dashboard / linear-maintain（linear 専用のガード）は意図的に別の形なので対象外
- 同期検証: `validate_plugin_quality.py` の backend-detect 同期チェック（Critical）。routing-axes と同じく区間を dedent 後に比較する
- 変更手順: この正本を編集 → 全消費サイトの区間に同じ内容を反映 → `/quality-check` で同期確認。
  スキル固有の例外（issue-design の `BACKEND=none` など）は区間の外に書く

<!-- BACKEND-DETECT:START -->
1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。
<!-- BACKEND-DETECT:END -->
