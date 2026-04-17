# KNOWLEDGE - ドメイン知識・調査結果

## 業務・ドメイン知識

### 音声対話の遅延設計（PLAN.mdより）
- 対話は発話末から **1.5秒** 空くと破綻しやすい
- 対策：話者交替点検出 → 短い相槌をTTS再生しながら、裏でASR→LLM→TTS本応答を走らせる
- LLMが重いと間に合わない。軽量LLMが望ましい（MVP後の課題）

## 調査・リサーチ結果

### Subaru_TTS（`../Subaru_TTS`）の状態
- Phase 1（データ収集・前処理）段階、推論はまだ未実装
- 第一候補: **GPT-SoVITS v4**（日本語VTuber音声クローンで実績、RTF 0.028、48kHz出力、少量データ5〜20分でFT可）
- 第二候補: Fish Speech v1.5
- 実行環境: RTX 3090 24GB / Ubuntu 24.04 / Python 3.12（ShubaTapoChanと同一GPU PC想定）
- 完成後はHTTP API経由で呼ぶ想定（MVPでは仮TTSで開発を進める）

### VAD_ASR_emoto の仕組み
- 場所（プログラム）: `/Users/sayonari/GoogleDrive_MyDrive/nishimura/program/_research_lab/VAD_ASR_emoto/`
- 場所（モデル）: `/Users/sayonari/_data/program/VAD_ASR_emoto_model/emoto-wav2vec2/`
- 使用モデル（`mod_record.py`より）: `SiRoZaRuPa/wav2vec2-kanji-base-char-0916`
- 音声仕様: 16kHz mono PCM, CHUNK=1024
- 推論窓: RATE*3 = 3秒（`input_len = int(RATE*3)`）
- 挙動: CPUでも動作（`USE_GPU=False`が既定）。GPUで更に高速化可能
- **課題**: スライディング窓（200msシフト）で毎回3秒全体を推論するため、隣接窓で重複テキストが出力される。LLMへ渡す前に **dedupマージ処理が必要**
- dedup案: `difflib.SequenceMatcher` で連続窓の最長共通部分を検出→畳み込み、変化が止まった時点を発話末と判定

### TAPO C220 の制御
- **RTSP URL**: `rtsp://<user>:<pass>@<ip>:554/stream1` （高画質） or `/stream2` （低画質）
- **音声コーデック**: AAC 16kHz mono
- **認証**: Tapoアプリの Advanced Settings → **Camera Account** で作成する専用アカウント（Tapoクラウドアカウントではない）
- **双方向音声**: RTSP/ONVIFでは公式非対応。`pytapo` が独自プロトコル（HTTPS 443/8800経由、暗号化マルチパート）で実装
- **双方向音声 遅延**: 500ms〜1.5s（ネットワーク・カメラ処理依存）
- **双方向音声 注意**: TAPO C220のファームウェアによって挙動が変わるとの報告あり。初期検証は`pytapo/examples/send_audio.py`で疎通確認を優先
- **PTZ**: `pytapo.Tapo.moveMotor(x, y)`、`moveMotorStep(angle)`、`calibrateMotor()`、`setPrivacyMode()` で制御可。C220/C200互換

### 既存実装の参考
- `JurajNyiri/pytapo` — 中核ライブラリ
- `JurajNyiri/HomeAssistant-Tapo-Control` — Two-way audio / PTZ のリファレンス実装
- 日本のZenn/Qiitaで「Tapo C200/C220 × ChatGPT Realtime API」系の実装記事が2025年前半に複数公開
- アーキテクチャ共通パターン: RTSP音声入力 → VAD → STT → LLM → TTS → pytapo Two-way audio、PTZはLLM tool useで`moveMotor`

## 技術的な知見

### GPU PC（Ubuntu 24.04）推奨スタック
- venv直（Dockerよりネットワーク挙動が素直）
- `systemd --user` でエージェント常駐、ログは`journalctl`
- 主要パッケージ: `pytapo>=3.3`, `av` (PyAV), `transformers`, `torch` (CUDA), `webrtcvad-wheels`, `silero-vad`, `anthropic`, `pyttsx3` or VOICEVOX Python client

### 自己発話フィードバック回避
- TAPOのスピーカーから出た音声をTAPOのマイクが拾って無限ループになるのを防ぐため、**SPEAKING状態中はASRゲートを閉じる**
- AEC（エコーキャンセル）は将来課題

## 決定事項と理由

| 項目 | 決定 | 理由 |
|------|------|------|
| ASR方式 | VAD_ASR_emoto方式 (wav2vec2 + sliding window + dedup) | D1=(a)。「全部GPU PC」方針と両立、既存資産の再利用、低遅延 |
| TTS（MVP） | Subaru_TTS完成を待つ。間に合わなければ pyttsx3/VOICEVOX 等で仮実装 | D2。本命まで開発を止めないために抽象化して差し替え可に |
| 音声出力先 | TAPO C220 スピーカー（pytapo Two-way audio） | D3。GPU PCは物理的に別室でスピーカー無し |
| 開発環境 | Mac 編集 / GPU PC SSH 実行 / GitHub経由同期 | D4=(a)。一般的で可搬性あり |
| LLM初期実装 | Claude API（`claude-haiku-4-5` 既定、切替可） | 低遅延、抽象`LLMClient`で後から差し替え自由 |

## 要確認（次セッション冒頭で確認）
- GPU PCとTAPO C220の物理ネットワーク関係（同一LANか、VPNが必要か）
- `.env` の具体内容（GPU PCログイン情報・TAPO情報）
- TAPO C220 開封直後なので、まずPhase 0（物理セットアップ）をユーザーが実施する必要あり
