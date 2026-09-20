---
type: llm
weight: 2
---

同値分割表の「パスワード / 空 / null」行が「カバー Scenario」列で Scenario 4 を指しているが、spec.md に Scenario 4 は存在しないため、この同値クラスがどの Scenario からもカバーされていないことを指摘している。

指摘があれば PASS。「空 / null」の未カバーに一切触れていなければ FAIL。
