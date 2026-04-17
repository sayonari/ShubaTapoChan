# SPEC - 技術仕様・要件定義

## プロジェクト概要
TAPO C220（首振り対応ネットワークカメラ）をエージェントの「身体」として、大空スバル声質のTTS（`../Subaru_TTS`）で応答する音声対話エージェントを構築する。

- ユーザーはTAPO C220の近くで発話
- TAPOのマイクで音声を拾う → GPU PC上でASR → LLM応答生成 → TTS合成 → TAPOスピーカーから再生
- 将来的に首振り（PTZ）・相槌/話者交替モデル・起動ワード検出・カメラ画像理解などを拡張

## 機能要件

### FR-1: 最小MVP（First Walk）— 単純な一問一答ループ
ユーザー発話 → ASR → LLM → TTS → TAPOスピーカー再生 をノンストップで繰り返す。

### FR-2: 音声入力（TAPO C220 → GPU PC）
- TAPO C220のRTSP `/stream1` からAAC音声を取得
- ffmpeg / PyAVでデコードし 16kHz mono PCM に変換
- ストリーム上でVADにより発話区間を推定

### FR-3: ASR（逐次音声認識）
- 既存の`VAD_ASR_emoto`方式を踏襲：`SiRoZaRuPa/wav2vec2-kanji-base-char-0916`
- 窓幅 約3秒・シフト200ms のスライディング窓ASR
- 窓間で重複する冗長テキストを **dedup／マージ** して1発話の最終テキスト化
- dedupの方針：連続窓の出力同士の最長共通部分列 / difflibベースで重複区間を畳み込み、変化が止まったら発話終端とみなして確定テキストを出す（詳細はKNOWLEDGE.mdで詰める）

### FR-4: LLM応答生成（差し替え可能）
- 初期実装：Anthropic Claude API（`claude-haiku-4-5` で低遅延開始、必要に応じ Sonnet/Opus に昇格）
- 将来：オンプレ軽量LLM（Ollama / llama.cpp）、Gemma系マルチモーダル、ClaudeCode連携なども切り替えられる抽象インターフェイス（`LLMClient`）を設ける
- カメラ画像（TAPOからのフレーム）をマルチモーダルLLMに渡す経路を将来拡張として設計上想定

### FR-5: TTS合成（段階的進化）
- **Phase A（仮TTS）**：Subaru_TTS完成までのあいだ、Python単体で導入可能な簡易TTS（例：`pyttsx3` / VOICEVOXエンジン）で動作確認
- **Phase B（本命）**：`../Subaru_TTS` のGPT-SoVITS v4推論APIに差し替え（48kHz → 16kHzへリサンプルしてTAPOへ送る）
- 抽象インターフェイス `TTSClient` で Phase A/B を差し替え可能にする

### FR-6: 音声出力（GPU PC → TAPO C220 スピーカー）
- `pytapo` の Two-way audio 機能でTAPOスピーカーに送信
- 16kHz mono PCMで送信（pytapoの送信仕様に合わせる）
- 送信中はマイクASRを一時ゲート（自己発話の再取り込み回避）

### FR-7: 対話ループ制御
- 最小状態機械：`IDLE → LISTENING → PROCESSING → SPEAKING → IDLE`
- `SPEAKING` 中のマイク入力は無視（自己発話フィードバック防止）

## 非機能要件

### NFR-1: 実行環境
- GPU PC（RTX 3090 24GB / Ubuntu 24.04 / Python 3.12）ですべての重い処理を実行
- GPU PCとTAPO C220は**同一LAN上で通信可能**であることを前提（異なる場合はVPN/Tailscale等で橋渡しする）
- GPU PCにはスピーカー非接続のため、**音声再生はTAPO側のみ**

### NFR-2: レイテンシ目標
- 発話終了 → 相手発話開始まで **2秒以内**（MVP）、将来 1秒以内（相槌・話者交替モデル併用時）
- 相槌・話者交替モデル導入後、発話末から **1.5秒以内の応答再生開始** を目標

### NFR-3: 差し替え可能な設計
- `ASRClient` / `LLMClient` / `TTSClient` を抽象化し、実装を差し替えても他レイヤに影響を与えない

### NFR-4: 安全・運用
- `.env` にGPU PC / TAPO認証情報を格納（Git管理外、`.gitignore`済）
- ログは `journalctl --user` に集約

## 技術構成

### 全体アーキテクチャ（MVP）
```
[ユーザー発話]
  ↓
TAPO C220 マイク
  ↓ RTSP (/stream1, AAC 16kHz)
  ↓
GPU PC (Ubuntu 24.04 / RTX 3090)
  ├─ audio_in:   ffmpeg / PyAV → 16kHz PCM ストリーム
  ├─ vad:        webrtcvad または Silero VAD で発話区間判定
  ├─ asr:        wav2vec2 (SiRoZaRuPa/...-char-0916) を3s/200msスライディング
  ├─ dedup:      重複マージ → 確定テキスト
  ├─ llm:        LLMClient (default: Claude API / claude-haiku-4-5)
  ├─ tts:        TTSClient (Phase A: 仮TTS / Phase B: Subaru_TTS)
  └─ audio_out:  pytapo Two-way audio → TAPO C220 スピーカー
  ↓
[ユーザーの耳]
```

### 主要ライブラリ
| 用途 | ライブラリ |
|------|----------|
| RTSP/音声デコード | ffmpeg-python, av (PyAV) |
| VAD | webrtcvad-wheels, silero-vad |
| ASR (wav2vec2) | transformers, torch |
| dedup | difflib, 独自ロジック |
| LLM | anthropic |
| TTS(仮) | pyttsx3 or requests(VOICEVOX HTTP) |
| TTS(本命) | Subaru_TTS のGPT-SoVITS v4 HTTP API |
| TAPO制御・双方向音声 | pytapo |

### 開発・実行フロー（D4決定）
- **開発環境**：このMac（`/Users/sayonari/_data/program/ShubaTapoChan`）で編集
- **実行環境**：`.env` 記載のGPU PCへSSHで接続し、`rsync`または`git pull`で同期して実行
- **Git**：このMacのローカルをオリジンとし、`git push`でGitHub経由、GPU PC側で`git pull`して走らせる（またはVS Code Remote SSHで直接編集）

### TAPO C220 初期セットアップ（人間が行う前提作業）
1. Tapoアプリでカメラをアカウント追加、Wi-Fi接続
2. Advanced Settings → **Camera Account** を有効化、ユーザー名/パスワード設定
3. ルータでTAPOのIPをDHCP予約（固定IP化）
4. 別PCから `ffprobe rtsp://<user>:<pass>@<ip>:554/stream1` で疎通確認
5. TAPO認証情報・IPを`.env`へ記録

## フェーズ計画

### Phase 0: TAPO C220 物理セットアップ（人間作業）
TAPO C220をアプリで初期設定、IP固定、RTSP疎通確認、`.env`に情報記載。

### Phase 1: GPU PC環境構築
Python 3.12 venv、依存パッケージ、`pytapo`疎通、TAPO `moveMotor`/RTSP音声取得の動作確認スクリプト。

### Phase 2: 音声入力パイプライン
RTSP → 16kHz PCM → リングバッファ。VADを仮置き。

### Phase 3: ASR組み込み
`VAD_ASR_emoto` の `mod_record.py` をGPU対応＋RTSP入力対応にリファクタし、dedup付きで確定テキストを発行。

### Phase 4: LLM接続
`LLMClient` 抽象を実装、Claude APIで単発応答。

### Phase 5: 仮TTS + TAPOスピーカー出力
`TTSClient` 抽象を実装し、Phase A実装（仮TTS）。pytapoのTwo-way audioに送信。`send_audio.py`相当で疎通確認から。

### Phase 6: エンドツーエンド対話ループ
状態機械で一周させる。SPEAKING中のマイクゲート実装。

### Phase 7（後続）: Subaru_TTSに切替、PTZ・起動ワード・相槌/話者交替モデル統合、カメラ画像のマルチモーダル入力

## 未確定・要確認事項（次回セッションで詰める）
- GPU PCとTAPO C220が同一LANにあるか（物理配置）。異なる場合はTailscale等でVPN検討。
- `.env` に既に記載済みのGPU PCログイン情報の具体的な形式確認。
- TAPO C220のファームウェアバージョン（pytapo Two-way audio動作可否がFW依存）。
- 仮TTSに何を使うか（`pyttsx3` vs VOICEVOX vs 他）。初回動作確認優先なら`pyttsx3`。
