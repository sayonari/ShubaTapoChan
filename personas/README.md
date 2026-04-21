# personas/

キャラクター設定（ペルソナ）を YAML で定義するディレクトリ。
LLM の system プロンプトに注入され、応答のトーン・口調・背景を決める。

## ファイル
- `subaru.yaml` — 大空スバル（本プロジェクトの既定ペルソナ）

## 使い方
- 既定: `SHUBATAPO_PERSONA=subaru`（指定なしでも subaru）
- 別キャラ: `SHUBATAPO_PERSONA=<stem>` で `personas/<stem>.yaml` を読む
- Python: `from shubatapo.persona import load_persona; p = load_persona()`

## スキーマ（すべて任意、name のみ必須）
| フィールド | 型 | 用途 |
|---|---|---|
| `name` | str | 表示名 |
| `reading` | str | ふりがな |
| `affiliation` | str | 所属（例: ホロライブ2期生） |
| `summary` | str | 一行プロフィール |
| `first_person` | str | 一人称 |
| `tone` | str | 口調・語尾の指示 |
| `signature_phrases` | list[str] | 口癖・決め台詞 |
| `likes` / `dislikes` | list[str] | 好き嫌い |
| `background` | list[str] | 背景設定の箇条書き |
| `response_style` | list[str] | 応答形式の指示（長さ、絵文字禁止など） |
| `dos` / `donts` | list[str] | してほしい/してほしくないこと |
| `extra` | str | 追加の自由記述 |

未定義フィールドは system プロンプトに含まれない。新キャラは
既存の `subaru.yaml` をコピーして書き換えれば良い。
