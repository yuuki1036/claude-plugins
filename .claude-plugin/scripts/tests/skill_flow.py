"""分けた SKILL.md（validate_plugin_quality.py の SPLIT_SKILLS）を、分ける前の 1 本の本文に戻す.

本文の文言を見るテストは SKILL.md を ``read_text`` して見出しで切り出す。phase の本文を
``skills/<skill>/references/`` へ分けた後は、SKILL.md には見出しと Read の行しか残らない。
``flow_text`` は Read の行の位置にそのファイルの本文を差し込むので、切り出しはそのまま動く
（phase ファイルの先頭の見出しは SKILL.md の見出しと同じなので、差し込むときに落とし、見出しが
2 回並ばないようにする）。分けた skill か・どれが Read の行か・どれが最初の見出しかは、検査と同じ
関数で決める（判定基準の持ち主を 1 つにする / GitHub issue #426・docs/rule-placement.md）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "validate_plugin_quality.py"
_spec = importlib.util.spec_from_file_location("_vpq_for_skill_flow", _SCRIPT)
_vpq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vpq)


def flow_text(skill_md: Path) -> str:
    """SKILL.md の各 Read の行の直後に参照先の本文を差し込んだ文字列（SPLIT_SKILLS に無い SKILL.md はそのまま）."""
    text = skill_md.read_text(encoding="utf-8")
    entry = _vpq.split_skill_entry(skill_md)
    if entry is None:
        return text
    rel, heading_re, label = entry
    plugin_dir = _vpq.split_skill_plugin_dir(rel)
    inserts: dict[int, str] = {}
    for _name, _heading, reads in _vpq.split_skill_phases(skill_md, heading_re, label):
        for i, path in reads:
            target = plugin_dir / path
            body = target.read_text(encoding="utf-8").splitlines(keepends=True)
            h = _vpq.first_heading_index(target)
            if h is not None:
                del body[h]
            inserts[i] = "\n" + "".join(body).rstrip("\n") + "\n"
    out: list[str] = []
    for i, line in enumerate(text.splitlines(keepends=True)):
        out.append(line)
        if i in inserts:
            out.append(inserts[i])
    return "".join(out)
