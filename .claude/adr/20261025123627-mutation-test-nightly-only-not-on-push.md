---
id: 20261025123627
status: accepted
phase: current
last-validated: 2026-10-25
supersedes: []
superseded-by: null
append_only: true
tags: [ci, mutation-test, nightly]
---

# ADR-20261025123627: 変異テストは push では回さず、nightly だけで回す

## ステータス

accepted（2026-10-25）

## コンテキスト / 背景

- push 時の CI（`.github/workflows/validate.yml`）は、変更行の変異テストを `--max 5 --strict --related-first` のスモークとして回していた。生存が 1 つでもあれば CI を落とす形で、GitHub issue #138 でブロッキングに切り替えたもの
- 直近 40 回の CI（2026-10-11〜25）では、この step が平均 518 秒・最大 2622 秒で、CI の所要の 57% を占めた（unit-tests は平均 428 秒）。その 40 回で生存を検出したのは 0 回。それより前の約 200 回では 4 回（9/12・9/27・10/1・10/5）
- 2026-10-24 の push（GitHub issue #313 の実装）は、5 変異のスモークを 2622 秒かけて通ったが、同じ範囲を nightly（`mutation-nightly.yml`）が回すと生存 15 件が出た（GitHub issue #317）。浅いスモークは大きな変更の生存を拾えていない
- このリポジトリは main に直接コミットする。スモークが落ちても変更はもう main に入っているので、止める効果は無く、早く知らせる効果だけがある
- 作業側は push のあと CI の結果を見るまで完了にしない決まり（CLAUDE.md の Gotchas）なので、CI の所要はそのまま push ごとの待ち時間になる
- 2026-10-25 に、利用者が「push 時の変異テストをやめて nightly に寄せる」を選んだ

## 決定

- push / PR の CI（`validate.yml`）では変異テストを回さない。変異テストは nightly（`mutation-nightly.yml`）だけで回し、生存・持ち越しは今までどおり nightly が GitHub Issue に起票する
- nightly の範囲・予算・起票の仕方は変えない（nightly は、最後に全件を回し切った head 以降の変更行を対象にするので、push 側をやめても nightly の対象は減らない）
- 手元で変異テストを回すのは、新しい lint / 検証ロジックを足したとき（CLAUDE.md の Gotchas）と、軽量フロー・feature-dev が利用者の承認を得たとき（`.claude/mutation-test.sh`）だけのまま

## 影響 (Consequences)

- **良い影響**: push ごとの CI の待ち時間が平均 518 秒（最大 2622 秒）減る。CI の所要は unit-tests が中心になる
- **悪い影響**: 生存に気づくのが、push の数十分後（CI）から翌朝の issue（nightly）に遅れる。#138 で決めた「push で止める」はなくなる。nightly が予算を使い切った晩は、未実行の変異の検証がさらに 1 晩遅れる（持ち越しは `mutation-nightly-state.py` が扱う）
- **トレードオフ**: 生存の通知の早さ（実績 40 回で 0 回、約 240 回で 4 回）と、push ごとに払う待ち時間（平均 518 秒）を天秤にかけた。main に直接入れる運用では、早く知らせても着地は止まらない

## 適用方法 (Enforcement)

- 機械強制はしない。`validate.yml` から step を消したこと自体が適用で、戻すときはこの ADR を supersede する
- 生存の検出は nightly の起票（`mutation-nightly-report.py`）が担い、こちらは GitHub Issue として残るので、人が見落としても issue が開いたまま残る
- 「push 側に深い検証を戻さない」を lint にする案は採らない。workflow の step 名を検査しても、別名で同じ処理を足せば素通りし、守りたいもの（待ち時間）を測れていない

## 検討した代替案

- **push 側を残し、unit-tests と別の job にして並列に回す**: 変異テストの意味は変わらず、待ち時間は合計から長い方だけ（平均で約 950 秒 → 約 550 秒の見込み）になる。ただし最大 2622 秒の回は残り、実績 0 回の検出に毎回払う形も変わらないので採らなかった
- **変異 1 個ごとに回す関連テストを絞る**: hub.py の変異に関係の薄いモジュールまで付いていた（関連テスト 65 秒・本命 45 秒）。1 変異あたりの短縮が小さく、生存の判定はどのみちフルスイートを払うので採らなかった
- **CI の中で変異を並列に回す**: 変異は作業ツリーの実ファイルへ in-place で書くので、並列にするには作業ツリーの複製が要り、改修が大きい。nightly の予算超過への手当てとして別途検討する
- **今のまま（#138 の決定）**: 上の実測のとおり、払う時間に対して検出が少なく、大きな変更の生存は nightly が拾っていた

## 関連

- 関連 ADR: なし
- 関連 Issue: GitHub issue #138（push 側をブロッキングにした判断）/ GitHub issue #317（2026-10-24 の push の生存を nightly が検出）/ GitHub issue #288（nightly の打ち切りと持ち越し）
- 関連 design doc: なし
- 関連 knowledge: なし
