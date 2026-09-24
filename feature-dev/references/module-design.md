# モジュール設計の語彙（Phase 4 architect）

設計案を比べるときの共通語彙と原則。翻案元: [mattpocock/skills](https://github.com/mattpocock/skills) の codebase-design（`skills/engineering/codebase-design/SKILL.md`・`DEEPENING.md`）。Copyright (c) 2026 Matt Pocock / MIT License。許諾文は repo 直下の NOTICE。

## 語彙（言い換えない）

- **module**: interface と実装を持つもの全部。関数・クラス・パッケージ・層をまたぐ縦の切れまで、大きさを問わない
- **interface**: 呼び出し側が正しく使うために知る必要のあること全部。型シグネチャだけでなく、不変条件・呼び出し順の制約・エラーの出方・必要な設定・性能特性を含む（TypeScript の `interface` キーワードや public メソッドの一覧ではない）
- **depth**: interface で得られるてこの大きさ。覚える interface あたりに呼び出し側（やテスト）が使える振る舞いの量。小さな interface の裏に多くの振る舞いがあれば **deep**、interface が実装とほぼ同じ複雑さなら **shallow**
- **seam**: その場所を編集せずに振る舞いを差し替えられる位置。module の interface が置かれる場所で、どこに置くかはそれ自体が設計判断（「boundary」とは言わない — DDD の bounded context と紛れる）
- **adapter**: seam で interface を満たす具体物。中身ではなく役割を指す
- **leverage**: depth が呼び出し側にもたらすもの。1 つの実装が N 個の呼び出し元と M 個のテストに効く
- **locality**: depth が保守者にもたらすもの。変更・バグ・知識・検証が 1 か所に集まる

## 4 原則

1. **depth は interface の性質で、実装の性質ではない**。deep な module の中身が小さく差し替え可能な部品の組み合わせでもよい（interface に出さないだけ）。module は interface にある外部 seam のほかに、自分のテスト用の内部 seam を持てる
2. **削除テスト**: その module を消したと想像する。複雑さが消えるなら素通しだった。N 個の呼び出し元に複雑さが戻るなら役に立っている
3. **interface がテストの面**。呼び出し側とテストは同じ seam を通る。interface を越えて中を確かめたくなるなら、module の形が間違っている
4. **adapter が 1 つなら仮の seam、2 つなら本物**。何かが実際に差し替わらない限り seam を作らない（本番 + テストで 2 つが典型）

## 依存の 4 分類（seam の置き方とテスト方法が決まる）

| 分類 | 例 | seam とテスト |
|---|---|---|
| in-process | 純粋な計算・メモリ上の状態 | module をまとめ、新しい interface を直接テストする。adapter 不要 |
| ローカルで代替できる | PGLite（Postgres の代わり）・メモリ上のファイルシステム | 代替物をテストで動かす。seam は内部に置き、外部 interface に port を出さない |
| 自前だがリモート | 自社のマイクロサービス・内部 API | seam に port を定義し、本番は HTTP / gRPC / キューの adapter、テストはメモリ上の adapter |
| 外部 | Stripe・Twilio 等の第三者サービス | port として注入し、テストは mock の adapter |

shallow な module を deep にまとめたら、古い module 単位のテストは消して新しい interface にテストを書き直す（重ねない）。

## 設計案を比べる軸

minimal-changes / clean-architecture / pragmatic-balance のどれでも、案ごとに次を書く: **depth**（呼び出し側が覚える interface に対して得る振る舞い）・**locality**（変更が何か所に散るか）・**seam の位置**（テストをどこに置くか、依存の分類はどれか）。
