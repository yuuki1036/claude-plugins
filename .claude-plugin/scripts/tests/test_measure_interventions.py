"""measure-interventions.py — transcript から人の介入点を数える計測の CLI テスト.

使い捨ての `projects/<slug>/<session>.jsonl` を組み立てて本物を走らせ、summary.json と events.jsonl を見る。
期待値は各テストが fixture から独立に書く（スクリプトの集計関数で期待値を作らない）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / ".claude-plugin" / "scripts" / "measure-interventions.py"
SLUG = "-Users-someone-Projects-secret-app"


def human(text, ts="2026-11-01T00:00:00Z", **kw):
    row = {"type": "user", "timestamp": ts, "origin": {"kind": "human"}, "message": {"role": "user", "content": text}}
    row.update(kw)
    return row


def assistant(*blocks, ts="2026-11-01T00:00:01Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": list(blocks)}}


def say(text):
    return {"type": "text", "text": text}


def tool_use(name, tid, inp=None):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp or {}}


def tool_result(tid, content, ts="2026-11-01T00:00:02Z", **kw):
    row = {"type": "user", "timestamp": ts,
           "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]}}
    row.update(kw)
    return row


def wrap(ask, *labels):
    return tool_use("mcp__ccd_turn__wrap_up", "w", {"recap": "r", "ask": ask, "actions": [{"label": x} for x in labels]})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "projects"
        self.out = Path(self.tmp.name) / "out"

    def write(self, rows, session="s1", slug=SLUG):
        d = self.root / slug
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{session}.jsonl", "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")
        return d

    def run_script(self, *args, expect=0):
        p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out", str(self.out), *args],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, expect, p.stderr)
        return p

    def summary(self, *args):
        self.run_script(*args)
        return json.loads((self.out / "summary.json").read_text(encoding="utf-8"))

    def events(self):
        return [json.loads(x) for x in (self.out / "events.jsonl").read_text(encoding="utf-8").splitlines()]


class HumanDetection(Base):
    def test_only_origin_human_rows_count(self):
        self.write([
            {"type": "user", "timestamp": "2026-11-01T00:00:00Z", "promptSource": "sdk",
             "message": {"content": "eval のプロンプト"}},
            human("最初の依頼"),
            {"type": "user", "timestamp": "2026-11-01T00:01:00Z", "origin": {"kind": "peer"},
             "message": {"content": "別セッションからの連絡"}},
            {"type": "user", "timestamp": "2026-11-01T00:02:00Z", "origin": {"kind": "task-notification"},
             "message": {"content": "<task-notification>x</task-notification>"}},
        ])
        s = self.summary()
        self.assertEqual(s["human_prompts"], 1)
        self.assertEqual(s["by_kind"], {"prompt:start": 1})

    def test_session_without_human_is_counted_as_without_human(self):
        self.write([assistant(say("hi"))], session="auto")
        self.write([human("依頼")], session="manual")
        s = self.summary()
        self.assertEqual(s["sessions"], {"total": 2, "with_human": 1, "without_human": 1})

    def test_system_reminder_is_stripped_and_reminder_only_rows_skipped(self):
        self.write([
            human("<system-reminder>\nLinked sessions now\n</system-reminder>"),
            human("<system-reminder>x</system-reminder>\n本当の依頼"),
        ])
        self.run_script()
        self.assertEqual([(e["sub"], e["text"]) for e in self.events()], [("start", "本当の依頼")])

    def test_sidechain_rows_and_subagent_files_are_ignored(self):
        self.write([human("依頼"), human("subagent への指示", isSidechain=True)])
        sub = self.root / SLUG / "s1" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-a.jsonl").write_text(json.dumps(human("agent")) + "\n", encoding="utf-8")
        self.assertEqual(self.summary()["human_prompts"], 1)

    def test_meta_rows_are_not_human(self):
        self.write([human("依頼"), human("<local-command-stdout>x</local-command-stdout>", isMeta=True)])
        self.assertEqual(self.summary()["human_prompts"], 1)

    def test_resume_is_not_counted_as_a_prompt(self):
        self.write([human("依頼"), human("I hit my usage limit while you were working, but it has reset now.")])
        s = self.summary()
        self.assertEqual(s["human_prompts"], 1)
        self.assertEqual(s["by_kind"].get("prompt:resume"), 1)


class PromptKinds(Base):
    def test_start_free_reply_and_buttons(self):
        self.write([
            human("作業して", ts="2026-11-01T00:00:00Z"),
            assistant(say("やりました。"), ts="2026-11-01T00:00:10Z"),
            human("そこは違う、元に戻して", ts="2026-11-01T00:01:00Z"),
            assistant(say("戻しました。\nコミットしますか？"), ts="2026-11-01T00:01:10Z"),
            human("する", ts="2026-11-01T00:02:00Z"),
            assistant(wrap("どうしますか？", "進めて", "やめる"), ts="2026-11-01T00:02:10Z"),
            human("進めて", ts="2026-11-01T00:03:00Z"),
            assistant(wrap("次は？", "A 案", "B 案"), ts="2026-11-01T00:03:10Z"),
            human("B 案", ts="2026-11-01T00:04:00Z"),
            assistant(wrap("次は？", "A 案", "B 案"), ts="2026-11-01T00:04:10Z"),
            human("どちらでもなく C で", ts="2026-11-01T00:05:00Z"),
        ])
        self.run_script()
        self.assertEqual([e["sub"] for e in self.events()],
                         ["start", "free", "reply", "button-primary", "button-alt", "reply"])

    def test_wrap_without_ask_does_not_make_a_reply(self):
        self.write([
            human("作業して"),
            assistant(tool_use("mcp__ccd_turn__wrap_up", "w", {"recap": "done"})),
            human("次もやって"),
        ])
        self.run_script()
        self.assertEqual([e["sub"] for e in self.events()], ["start", "free"])

    def test_ask_tail_without_question_mark(self):
        self.write([human("作業して"), assistant(say("2 件あります。\n直すかどうか決めてください。")), human("直して")])
        self.run_script()
        self.assertEqual(self.events()[-1]["sub"], "reply")

    def test_button_matches_action_message(self):
        self.write([
            human("作業して"),
            assistant(tool_use("mcp__ccd_turn__wrap_up", "w", {
                "recap": "r", "ask": "どうする？",
                "actions": [{"label": "dismiss", "message": "アラートを dismiss して"}, {"label": "残す"}]})),
            human("アラートを dismiss して"),
        ])
        self.run_script()
        self.assertEqual(self.events()[-1]["sub"], "button-primary")

    def test_slash_bash_and_card(self):
        self.write([
            human("<command-message>code-review:self-review</command-message>\n<command-name>/code-review:self-review</command-name>"),
            human("<bash-input>ls</bash-input>"),
            human("このタスクをここで実行してください：「直す」"),
        ])
        self.run_script()
        self.assertEqual([e["sub"] for e in self.events()], ["slash", "bash", "card"])

    def test_forms(self):
        texts = ["次", "ok", "ｙ", "1", "1,2", "A", "n", "no", "ng", "commit push", "merged", "まだ？",
                 "<pasted_content id=\"x\">a</pasted_content>", "README も直して"]
        rows = [human("作業して")] + [human(t) for t in texts]
        self.write(rows)
        self.run_script()
        forms = [e["form"] for e in self.events()[1:]]
        self.assertEqual(forms, ["continue", "continue", "continue", "choice", "choice", "choice", "text", "text", "text",
                                 "routine", "routine", "poll", "pasted", "text"])


class Questions(Base):
    def auq(self, tid, questions, answers, ts="2026-11-01T00:00:05Z"):
        return [
            assistant(tool_use("AskUserQuestion", tid, {"questions": questions})),
            {"type": "user", "timestamp": ts, "toolUseResult": {"questions": questions, "answers": answers},
             "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": "answered"}]}},
        ]

    def test_answer_classes(self):
        marked = {"question": "Q1", "header": "方針", "options": [{"label": "A"}, {"label": "B (Recommended)"}]}
        first = {"question": "Q2", "header": "進め方", "options": [{"label": "X"}, {"label": "Y"}]}
        multi = {"question": "Q3", "header": "対象", "multiSelect": True, "options": [{"label": "m"}, {"label": "n"}]}
        rows = [human("作業して")]
        rows += self.auq("q1", [marked], {"Q1": "B (Recommended)"})
        rows += self.auq("q2", [first], {"Q2": "X"})
        rows += self.auq("q3", [first], {"Q2": "Y"})
        rows += self.auq("q4", [marked], {"Q1": "どちらでもない"})
        rows += self.auq("q5", [multi], {"Q3": ["m", "n"]})
        rows += self.auq("q6", [multi], {"Q3": "m, n"})
        rows += self.auq("q7", [first], {})
        self.write(rows)
        s = self.summary("--names")
        self.assertEqual(s["by_kind"]["question:recommended"], 2)
        self.assertEqual(s["by_kind"]["question:alternative"], 1)
        self.assertEqual(s["by_kind"]["question:free-text"], 1)
        self.assertEqual(s["by_kind"]["question:multi"], 2)
        self.assertEqual(s["by_kind"]["question:unanswered"], 1)
        self.assertEqual(s["question_headers"]["方針"], {"recommended": 1, "free-text": 1})
        q = [e for e in self.events() if e["kind"] == "question"]
        self.assertTrue(q[0]["recommended_marked"])
        self.assertFalse(q[1]["recommended_marked"])

    def test_headers_are_hidden_without_names(self):
        rows = [human("作業して")] + self.auq("q1", [{"question": "Q", "header": "社内の画面名",
                                                         "options": [{"label": "a"}]}], {"Q": "a"})
        self.write(rows)
        s = self.summary()
        self.assertEqual(s["by_kind"]["question:recommended"], 1)
        self.assertNotIn("question_headers", s)
        self.assertNotIn("社内の画面名", (self.out / "summary.md").read_text(encoding="utf-8"))
        self.assertIn("社内の画面名", self.summary("--names")["question_headers"])


class OtherInterventions(Base):
    def test_interrupt_reject_and_hook_block(self):
        self.write([
            human("作業して"),
            {"type": "user", "timestamp": "2026-11-01T00:00:03Z",
             "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
            {"type": "user", "timestamp": "2026-11-01T00:00:04Z",
             "message": {"content": [{"type": "text", "text": "[Request interrupted by user for tool use]"}]}},
            assistant(tool_use("Bash", "b1"), tool_use("AskUserQuestion", "a1"), tool_use("Edit", "e1"),
                      tool_use("Bash", "b2"), tool_use("Bash", "b3")),
            tool_result("b1", "The user doesn't want to proceed with this tool use. The tool use was rejected"),
            tool_result("a1", "The user doesn't want to proceed with this tool use. The tool use was rejected"),
            tool_result("e1", "PreToolUse:Edit hook error: [bash /x/.claude/plugins/cache/mp/guardrail-protect/0.8.0/"
                              "hooks/scripts/g.sh]: [guardrail-protect] だめ"),
            tool_result("b2", "PreToolUse:Bash hook error: [command hook 3]: [adr-keeper] だめ"),
            tool_result("b3", "PreToolUse:Bash hook error: [/opt/guard/deny.sh]: Error: 拒否"),
        ])
        s = self.summary()
        self.assertEqual(s["human_prompts"], 1)
        for key, n in {"interrupt:turn": 1, "interrupt:tool-use": 1, "reject:Bash": 1, "reject:AskUserQuestion": 1,
                       "hook-block:guardrail-protect": 1, "hook-block:adr-keeper": 1,
                       "hook-block:(other)": 1}.items():
            self.assertEqual(s["by_kind"].get(key), n, key)
        s = self.summary("--names")
        self.assertEqual(s["by_kind"].get("hook-block:(non-plugin)"), 1)

    def test_mcp_tool_server_is_hidden(self):
        self.write([human("作業して"), assistant(tool_use("mcp__workserver__deploy", "m1")),
                    tool_result("m1", "The user doesn't want to proceed with this tool use.")])
        self.assertEqual(self.summary()["by_kind"], {"prompt:start": 1, "reject:mcp__(server)__deploy": 1})
        self.assertIn("reject:mcp__workserver__deploy", self.summary("--names")["by_kind"])


class SkillAttribution(Base):
    def test_window_and_builtin_commands(self):
        rows = [human("作業して"), assistant(tool_use("Skill", "k", {"skill": "code-review:self-review"}))]
        rows += [human(f"直して {i}") for i in range(6)]
        rows += [human("<command-name>/clear</command-name>"), human("直して 7")]
        self.write(rows)
        self.run_script("--names")
        skills = [e["skill"] for e in self.events()]
        # 起動の後の 5 回目までが帰属。/clear は帰属を上書きしない
        self.assertEqual(skills, ["(no-skill)"] + ["code-review:self-review"] * 5 + ["(no-skill)"] * 3)
        self.assertEqual(self.summary("--names")["skill_activations"], {"code-review:self-review": 1})

    def test_slash_command_sets_the_skill(self):
        self.write([human("<command-name>/issue-workflow:start</command-name>"), human("次")])
        self.run_script()
        self.assertEqual(self.events()[-1]["skill"], "issue-workflow:start")

    def test_slash_window_counts_five_after_the_launch(self):
        rows = [human("<command-name>/issue-workflow:start</command-name>")] + [human(f"直して {i}") for i in range(6)]
        self.write(rows)
        self.run_script()
        # Skill tool と同じく、起動の後の 5 回目までが帰属（slash 自身も帰属する）
        self.assertEqual([e["skill"] for e in self.events()], ["issue-workflow:start"] * 6 + ["(no-skill)"])

    def test_skills_outside_the_marketplace_are_hidden(self):
        self.write([human("作業して"), assistant(tool_use("Skill", "k", {"skill": "work-plugin:deploy"})),
                    assistant(tool_use("Skill", "k2", {"skill": "local-skill"})), human("直して")])
        s = self.summary()
        self.assertEqual(s["skill_activations"], {"(other-skill)": 2})
        self.assertNotIn("work-plugin", (self.out / "summary.md").read_text(encoding="utf-8"))
        self.assertEqual(self.summary("--names")["skill_activations"], {"work-plugin:deploy": 1, "local-skill": 1})


class Output(Base):
    def test_project_names_hidden_and_events_private(self):
        self.write([human("作業して")])
        self.write([human("作業して"), human("直して")], session="s2", slug="-Users-someone-Projects-other")
        s = self.summary()
        self.assertEqual(sorted(s["projects"]), ["P1", "P2"])
        for name in ("summary.json", "summary.md"):
            self.assertNotIn("secret-app", (self.out / name).read_text(encoding="utf-8"))
        self.assertEqual(os.stat(self.out / "events.jsonl").st_mode & 0o777, 0o600)
        self.assertIn(SLUG, self.summary("--names")["projects"])

    def test_since_until_filter(self):
        self.write([human("古い", ts="2026-10-01T00:00:00Z"), human("新しい", ts="2026-11-02T00:00:00Z"),
                    human("後", ts="2026-11-05T00:00:00Z")])
        self.run_script("--since", "2026-11-01", "--until", "2026-11-05")
        # 窓の外の「古い」もセッション内の発話の順番には数える（「新しい」は 2 回目の発話なので free）
        self.assertEqual([(e["sub"], e["text"]) for e in self.events()], [("free", "新しい")])

    def test_history_copied_into_another_file_is_counted_once(self):
        shared = [human("作業して", uuid="u1"), {**assistant(say("やりました")), "uuid": "u2"}, human("直して", uuid="u3")]
        self.write(shared, session="orig")
        self.write(shared + [human("続きも", ts="2026-11-01T00:05:00Z", uuid="u4")], session="fork")
        self.write(shared, session="orig", slug="-Users-someone-Projects-other")
        s = self.summary()
        # 複製された u1・u3 は 1 回だけ。fork の続き（u4）は複製の後ろの発話として free になる
        self.assertEqual(s["by_kind"], {"prompt:start": 1, "prompt:free": 2})
        self.assertEqual(s["sessions"]["total"], 2)

    def test_project_filter(self):
        self.write([human("a")])
        self.write([human("b")], session="s2", slug="-Users-someone-Projects-other")
        self.assertEqual(self.summary("--project", "other")["human_prompts"], 1)

    def test_broken_lines_are_counted_not_fatal(self):
        self.write(["{broken", human("作業して")])
        self.assertEqual(self.summary()["unreadable_lines"], 1)

    def test_missing_root_and_empty_root_exit_2(self):
        p = self.run_script(expect=2)
        self.assertIn("transcript の dir がありません", p.stderr)
        self.root.mkdir()
        p = self.run_script(expect=2)
        self.assertIn("1 件もありません", p.stderr)

    def test_empty_window_exits_2(self):
        self.write([human("古い", ts="2026-01-01T00:00:00Z")])
        p = self.run_script("--since", "2027-01-01", expect=2)
        self.assertIn("期間に入るセッションがありません", p.stderr)
        self.assertFalse((self.out / "summary.json").exists())
        self.run_script("--since", "2025-12-31")

    def test_out_inside_a_git_worktree_is_refused(self):
        self.write([human("作業して")])
        repo = Path(self.tmp.name) / "repo"
        (repo / ".git").mkdir(parents=True)
        p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out", str(repo / "m1")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("git の作業ツリーの中", p.stderr)
        self.assertFalse((repo / "m1").exists())
        self.run_script()

    def test_tilde_in_out_is_expanded_before_the_check_and_the_write(self):
        self.write([human("作業して")])
        home = Path(self.tmp.name) / "home"
        repo = Path(self.tmp.name) / "repo"
        (repo / ".git").mkdir(parents=True)
        home.mkdir()
        env = {**os.environ, "HOME": str(home)}
        p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out=~/m1"],
                           capture_output=True, text=True, timeout=60, cwd=repo, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((home / "m1" / "events.jsonl").exists())
        self.assertFalse((repo / "~").exists())
        (home / ".git").mkdir()
        p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out=~/m2"],
                           capture_output=True, text=True, timeout=60, cwd=repo, env=env)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse((home / "m2").exists())

    def test_default_out_is_a_fresh_private_dir(self):
        self.write([human("作業して")])
        dirs = []
        for _ in range(2):
            p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root)],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
            line = next(x for x in p.stdout.splitlines() if x.startswith("events:"))
            events = Path(line.split()[1])
            self.addCleanup(shutil.rmtree, events.parent, ignore_errors=True)
            dirs.append(events.parent)
            self.assertEqual(os.stat(events.parent).st_mode & 0o777, 0o700)
        self.assertNotEqual(dirs[0], dirs[1])


class Labels(Base):
    def test_labels_join_by_session_and_ts(self):
        self.write([
            human("作業して", ts="2026-11-01T00:00:00Z"),
            assistant(tool_use("Skill", "k", {"skill": "code-review:self-review"}), ts="2026-11-01T00:00:01Z"),
            human("そこは違う", ts="2026-11-01T00:01:00Z"),
            human("README も", ts="2026-11-01T00:02:00Z"),
            human("どうなった", ts="2026-11-01T00:03:00Z"),
        ])
        labels = Path(self.tmp.name) / "labels.jsonl"
        rows = [
            {"session": "s1", "ts": "2026-11-01T00:01:00Z", "label": "修正", "target": "決定的な検査", "check": "社内の値"},
            {"session": "s1", "ts": "2026-11-01T00:02:00Z", "label": "追加の依頼"},
            {"session": "s1", "ts": "2026-11-01T00:03:00Z", "label": "しつもん", "target": "なんとなく"},
            {"session": "s1", "ts": "2026-11-09T00:00:00Z", "label": "修正"},
        ]
        labels.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        s = self.summary("--labels", str(labels))
        self.assertEqual(s["labels"], {"修正": 1, "追加の依頼": 1, "(語彙外)": 1})
        self.assertEqual(s["label_targets"], {"修正": {"決定的な検査": 1}, "(語彙外)": {"(語彙外)": 1}})
        self.assertEqual(s["labels_by_skill"]["code-review:self-review"], {"修正": 1, "追加の依頼": 1, "(語彙外)": 1})
        self.assertEqual(s["unmatched_labels"], 1)
        for name in ("summary.json", "summary.md"):
            self.assertNotIn("社内の値", (self.out / name).read_text(encoding="utf-8"))

    def test_free_text_answers_in_one_call_are_labelled_apart(self):
        qs = [{"question": f"Q{i}", "header": "h", "options": [{"label": "a"}]} for i in range(2)]
        self.write([
            human("作業して"),
            assistant(tool_use("AskUserQuestion", "q", {"questions": qs})),
            {"type": "user", "timestamp": "2026-11-01T00:00:05Z",
             "toolUseResult": {"questions": qs, "answers": {"Q0": "違う案で", "Q1": "それも違う"}},
             "message": {"content": [{"type": "tool_result", "tool_use_id": "q", "content": "answered"}]}},
        ])
        labels = Path(self.tmp.name) / "labels.jsonl"
        rows = [
            {"session": "s1", "ts": "2026-11-01T00:00:05Z", "qi": 0, "label": "修正", "target": "人の判断"},
            {"session": "s1", "ts": "2026-11-01T00:00:05Z", "qi": 1, "label": "質問"},
            {"session": "s1", "ts": "2026-11-01T00:00:05Z", "qi": 1, "label": "修正"},
            {"session": "s1", "ts": "2026-11-01T00:00:05Z", "label": "修正"},
        ]
        labels.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        s = self.summary("--labels", str(labels))
        self.assertEqual(s["labels"], {"修正": 1, "質問": 1})
        self.assertEqual(s["duplicate_labels"], 1)
        self.assertEqual(s["unmatched_labels"], 1)
        self.assertEqual([e["qi"] for e in self.events() if e["kind"] == "question"], [0, 1])

    def test_missing_target_is_counted_as_unfilled(self):
        self.write([human("作業して", ts="2026-11-01T00:00:00Z"), human("違う", ts="2026-11-01T00:01:00Z")])
        labels = Path(self.tmp.name) / "labels.jsonl"
        labels.write_text(json.dumps({"session": "s1", "ts": "2026-11-01T00:01:00Z", "label": "差し戻し"},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
        s = self.summary("--labels", str(labels))
        self.assertEqual(s["label_targets"], {"差し戻し": {"(未記入)": 1}})

    def test_non_object_label_rows_exit_2(self):
        self.write([human("作業して")])
        bad = Path(self.tmp.name) / "labels.jsonl"
        bad.write_text('["x"]\n', encoding="utf-8")
        p = self.run_script("--labels", str(bad), expect=2)
        self.assertIn("object ではない", p.stderr)

    def test_without_labels_the_keys_are_absent(self):
        self.write([human("作業して")])
        s = self.summary()
        self.assertNotIn("labels", s)
        self.assertNotIn("unmatched_labels", s)

    def test_broken_labels_exit_2(self):
        self.write([human("作業して")])
        bad = Path(self.tmp.name) / "labels.jsonl"
        bad.write_text("{", encoding="utf-8")
        p = self.run_script("--labels", str(bad), expect=2)
        self.assertIn("分類の JSONL を読めません", p.stderr)


class Merge(Base):
    def run_machine(self, rows, label, *args):
        self.write(rows, session=label, slug=f"-Users-someone-{label}")
        out = Path(self.tmp.name) / label
        subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--out", str(out),
                        "--project", label, *args], check=True, capture_output=True, timeout=60)
        return out / "summary.json"

    def test_counts_add_up_and_projects_stay_apart(self):
        a = self.run_machine([human("依頼", ts="2026-11-01T00:00:00Z"), human("次", ts="2026-11-02T00:00:00Z")], "m1")
        b = self.run_machine([human("依頼", ts="2026-10-01T00:00:00Z"), human("直して", ts="2026-10-02T00:00:00Z"),
                              human("<bash-input>ls</bash-input>", ts="2026-10-03T00:00:00Z")], "m2")
        self.run_script("--merge", str(a), str(b))
        s = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s["merged_from"], 2)
        self.assertEqual(s["human_prompts"], 5)
        self.assertEqual(s["by_kind"], {"prompt:start": 2, "prompt:free": 2, "prompt:bash": 1})
        self.assertEqual(s["prompt_forms"]["free"], {"continue": 1, "text": 1})
        self.assertEqual(s["sessions"], {"total": 2, "with_human": 2, "without_human": 0})
        self.assertEqual(sorted(s["projects"]), ["M1-P1", "M2-P1"])
        self.assertEqual((s["window"]["first_ts"][:10], s["window"]["last_ts"][:10]), ("2026-10-01", "2026-11-02"))
        self.assertTrue(s["anonymized"])
        self.assertNotIn("labels", s)
        self.assertFalse((self.out / "events.jsonl").exists())

    def test_unreadable_input_exits_2(self):
        bad = Path(self.tmp.name) / "bad.json"
        for body in ("{", "[1]"):
            bad.write_text(body, encoding="utf-8")
            p = self.run_script("--merge", str(bad), expect=2)
            self.assertIn("summary.json を読めません", p.stderr)

    def test_malformed_summary_exits_2_without_partial_output(self):
        bad = Path(self.tmp.name) / "bad.json"
        for body in ('{"sessions": {}}', '{"sessions": {"total": 1, "with_human": 1, "without_human": 0}, "projects": {"P1": 5}}'):
            bad.write_text(body, encoding="utf-8")
            p = self.run_script("--merge", str(bad), expect=2)
            self.assertIn("形が違います", p.stderr)
            self.assertFalse((self.out / "summary.json").exists())

    def test_mismatched_windows_and_plain_parts_warn(self):
        rows = [human("依頼", ts="2026-11-02T00:00:00Z")]
        a = self.run_machine(rows, "m1", "--since", "2026-11-01")
        b = self.run_machine(rows, "m2", "--since", "2026-11-01")
        p = self.run_script("--merge", str(a), str(b))
        self.assertNotIn("WARN", p.stderr)
        self.assertEqual(json.loads((self.out / "summary.json").read_text(encoding="utf-8"))["window"]["since"],
                         "2026-11-01")
        c = self.run_machine(rows, "m3", "--names")
        p = self.run_script("--merge", str(a), str(c))
        self.assertIn("since が揃っていない", p.stderr)
        self.assertIn("伏せ字なしの summary", p.stderr)
        self.assertIsNone(json.loads((self.out / "summary.json").read_text(encoding="utf-8"))["window"]["since"])


if __name__ == "__main__":
    unittest.main()
