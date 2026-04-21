"""Persona (キャラ設定) の YAML ロードと system プロンプト整形。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PERSONA_DIR = PROJECT_ROOT / "personas"


@dataclass(frozen=True)
class Persona:
    """キャラ設定の構造。personas/*.yaml の内容を保持する。

    全フィールドは必須ではない。YAML に書かれていなければ system プロンプトには含めない。
    """
    name: str                              # 表示名 (例: "大空スバル")
    reading: str = ""                      # ふりがな (例: "おおぞらすばる")
    affiliation: str = ""                  # 所属 (例: "ホロライブ2期生")
    summary: str = ""                      # 一行プロフィール
    first_person: str = ""                 # 一人称 (例: "スバル")
    tone: str = ""                         # 口調の指示
    signature_phrases: list[str] = field(default_factory=list)  # 口癖・決め台詞
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)         # 背景設定の箇条書き
    response_style: list[str] = field(default_factory=list)     # 応答スタイル指示
    dos: list[str] = field(default_factory=list)                # してほしいこと
    donts: list[str] = field(default_factory=list)              # してほしくないこと
    extra: str = ""                                             # 追加の自由記述

    def to_system_prompt(self) -> str:
        """Claude 等の system メッセージに渡す文字列に整形。"""
        lines: list[str] = []
        header = f"あなたは「{self.name}」"
        if self.reading:
            header += f"（{self.reading}）"
        if self.affiliation:
            header += f"／{self.affiliation}"
        header += " として応答してください。"
        lines.append(header)

        if self.summary:
            lines.append(f"プロフィール: {self.summary}")
        if self.first_person:
            lines.append(f"一人称: {self.first_person}")
        if self.tone:
            lines.append(f"口調: {self.tone}")
        if self.signature_phrases:
            lines.append("口癖・決め台詞: " + " / ".join(self.signature_phrases))
        if self.likes:
            lines.append("好きなもの: " + "、".join(self.likes))
        if self.dislikes:
            lines.append("苦手なもの: " + "、".join(self.dislikes))
        if self.background:
            lines.append("背景設定:\n" + "\n".join(f"- {b}" for b in self.background))
        if self.response_style:
            lines.append("応答スタイル:\n" + "\n".join(f"- {s}" for s in self.response_style))
        if self.dos:
            lines.append("してほしいこと:\n" + "\n".join(f"- {d}" for d in self.dos))
        if self.donts:
            lines.append("してほしくないこと:\n" + "\n".join(f"- {d}" for d in self.donts))
        if self.extra:
            lines.append(self.extra)

        return "\n\n".join(lines)


def load_persona(name: str | None = None, persona_dir: Path | None = None) -> Persona:
    """persona YAML を読み込む。name 未指定なら SHUBATAPO_PERSONA 環境変数、なければ "subaru"。"""
    if name is None:
        name = os.getenv("SHUBATAPO_PERSONA", "subaru")
    base = persona_dir or PERSONA_DIR
    path = base / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"persona YAML が見つかりません: {path}")
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "name" not in data:
        raise ValueError(f"persona YAML に name が必須です: {path}")
    # dataclass のフィールド名に一致するキーだけ拾う（typo で知らないキーが来ても落とさない）
    allowed = {f for f in Persona.__dataclass_fields__}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    return Persona(**kwargs)
