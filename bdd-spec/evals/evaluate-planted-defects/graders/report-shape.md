---
type: llm
weight: 1
arm: with-only
---

evaluate-spec の型どおりのレポートになっている: 指摘が severity（critical / major / minor 相当の 3 段）で区分され、各指摘に観点（構文 / 粒度 / 網羅性 / トレーサビリティ）と位置（ファイル名と行または節）と修正案が付いている。

3 要素（区分・位置・修正案）が揃っていれば PASS。全文が区分の無い箇条書きや散文なら FAIL。
