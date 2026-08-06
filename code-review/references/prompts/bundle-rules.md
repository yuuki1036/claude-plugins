### 観点バンドル起動時の追加指示（high 以下の体数圧縮 / triage-guide.md `## 7`）

1 体の reviewer に複数観点の Focus テンプレートを束ねて注入する場合（reviewer 上限超過の吸収）、各テンプレートを連結した上で、プロンプト冒頭に以下を必ず追加する:

```
この reviewer には複数観点が割り当てられている: {focus キーの一覧}
- 各観点のチェックリストを 1 観点ずつ順に・独立に適用し、観点ごとに指摘を全件列挙すること
- 指摘の [カテゴリ] と focus キーは原観点のキーをそのまま使う（バンドル名を作らない。embed JSON の focus・missing_coverage の語彙と揃えるため）
- 観点間で指摘を相殺・自己フィルタしない（「別観点で見たから省略」禁止。dedup はオーケストレーターが行う）
- unmet_information / related-observations / [surface:high-risk] の申告は観点ごとでなく出力末尾にまとめてよい
```

1 体あたりのバンドルは 3 観点まで（attention 希釈の上限）。bug-detection / security / spec-compliance / claude-md-compliance は束ねない（triage-guide.md `## 7`）。


### specialist の束ね起動（high 以下 / triage-guide.md `## 7`）

**束ね起動（high 以下 / triage-guide.md `## 7`）**: 複数の red-flag が同時ヒットした場合、specialist-guardrail-bypass のみ単独 1 体を維持し、残りの specialist は 1〜2 体に束ねて該当テンプレートを連結注入する。出力規約は観点バンドル（`## 3` 冒頭）と同じ: focus キーは原 specialist 名（`specialist-injection` 等）をそのまま使い、観点ごとに独立に全件列挙し、自己フィルタしない。トリガー感度（検出正規表現）は変更しない。xhigh / max では従来どおり個別起動（上限 6 体）。
