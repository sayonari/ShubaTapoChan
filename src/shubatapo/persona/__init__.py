"""キャラクター設定（ペルソナ）ローダ。

プロジェクトルート `personas/<name>.yaml` を読み込み、LLM の system プロンプトに
変換する。voice_loop / text_loop はこれをそのまま LLMClient.respond(system=...) に渡す。

使い方:
    from shubatapo.persona import load_persona
    persona = load_persona()            # SHUBATAPO_PERSONA 環境変数 or "subaru"
    system_prompt = persona.to_system_prompt()
"""
from shubatapo.persona.loader import Persona, load_persona

__all__ = ["Persona", "load_persona"]
