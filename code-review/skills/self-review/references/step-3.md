<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#0 @d7242421 -->
### 3. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 3.9 へ。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- プロンプト冒頭で次の **2 パスを Read せよ**と指示する（本文は書かない。組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md`。パスの渡し方は Step 4 の冒頭と同じ）:
  - `${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer-common.md`
  - `${CLAUDE_PLUGIN_ROOT}/references/prompts/explorer/<focus>.md`
- 可変部として Phase 0 が決定した focus・対象ファイル・関数、**プラグインの実パス**（explorer-common.md の `{{PLUGIN_ROOT}}` の読み替え先。explorer は共通ブロックを受け取らないので、ここで渡すのが唯一の経路）、および **Step 1 の `$DIFF_FILE` のパスと担当ファイル名**を渡す（`diff-slice.sh` で自分の担当ぶんを切り出せることも明記する。`--since` の回は `$DIFF_FILE` として `delta_file` を渡す）
- `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため）
- **全 explorer の Agent call を同一メッセージ内で一括発行し、全体の結果が届くまで次へ進まない**（orchestration-guide.md `## 0`。起動は常に非同期で、結果は完了通知で届く）。**`mark t1` の応答で出す explorer を列挙してから発行に移る**（発行直前チェックポイント / `## 0`。実測の違反のうち 1 件は explorer を 1 体ずつ出した型 — #220）

一括発行の**直前**に fleet 区間の開始マーカーを記録する（**agent wave はすべて fleet 側に入れる**。explorer を triage 区間に含めると `duration_triage_min` が「メイン思考の代理指標」でなくなる。orchestration-measurement.md `## 14`）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1
```

全 explorer の完了を待ち、結果を収集する。**回収した直後**に explorer wave の終了マーカーを記録し（`t1`→ explorer 打点 = explorer wave の実時間。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）、各 explorer の `#### 確定事実` 欄を集約して **合計 10 行以内**にまとめておく（Step 4 で全 reviewer に注入する枠。無ければ no-op）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --explorer   # 複数メッセージに分けてしまった場合も wave ごとに毎回打つ（行数が agents.explorer_waves になる・#122）
```

**部分失敗耐性:** orchestration-guide.md `## 5` に従う（個別失敗で全体を中止せず `missing_coverage` に記録して続行）。

**次は Step 3.9**（SKILL.md に戻り、その見出しを見る）
