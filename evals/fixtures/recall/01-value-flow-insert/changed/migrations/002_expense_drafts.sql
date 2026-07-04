-- 下書きは未入力項目を許容するため NULL 可
CREATE TABLE expense_drafts (
  id     SERIAL PRIMARY KEY,
  title  TEXT NOT NULL,
  amount NUMERIC
);
