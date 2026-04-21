# MEMORY

## プロジェクト概要
TAPO C220（首振り対応ネットワークカメラ）＋ 大空スバル声TTS（`../Subaru_TTS`）＋ GPU PC による音声対話エージェント。

現状構成（2026-04-21時点）:
- **入力**: TAPO RTSP → ffmpeg 16kHz PCM → 50倍ゲイン → webrtcvad → faster-whisper large-v3
- **LLM**: Anthropic API (haiku-4-5 既定) または Claude Agent SDK (Max プラン枠, Sonnet/Opus)
- **キャラ設定**: `personas/<name>.yaml` → system プロンプトに注入（既定 subaru）
- **相槌**: 起動時に 6 種を TTS キャッシュ、ASR 確定時に ack→main 順で出力
- **TTS**: Subaru_TTS GPT-SoVITS v4 HTTP サーバー (port 8766, 48kHz mono WAV)
- **出力**:
  - `SHUBATAPO_AUDIO_OUT=mac` (既定): Mac 側 mac_runner.sh が scp + afplay（Subaru 声質◎）
  - `SHUBATAPO_AUDIO_OUT=tapo`: go2rtc 経由で C220 スピーカ push（PCMA/8kHz 電話品質）
  - `SHUBATAPO_AUDIO_OUT=both`: 両方

## 学習した知識・教訓

### 関連プロジェクト／モデルの位置関係
- `../Subaru_TTS/`：GPT-SoVITS v4 学習プロジェクト。TTSサーバは `http://133.15.57.36:8766` で稼働中（tmux セッション `tts_server`）、並行で長時間学習 `long_train` セッション（50 epoch 版）
- `../Subaru_TTS/.output/TTS_API_SPEC.md` にAPI仕様あり
- GPU PC (Rasiel): 133.15.57.36, RTX 3090, Ubuntu 24.04, Python 3.12 venv at `~/ShubaTapoChan/.venv`
- TAPO C220 (グローバルIP 133.15.57.84, FW 1.2.2 Build 260311)
- 参照音声のオススメ: `seg_000143.wav`（「フーボはあの...家庭教師みたいですよね」）。短いフレーズや `seg_000001.wav` は合成品質が崩れる

### TAPO C220 の制約と運用
- **RTSP 音声は PCM A-law 8kHz mono**（事前調査の16kHz AACと違う、モデル/FW依存）
- **音声レベルが低い**が、**ゲインでブーストしてはいけない**。ノイズも同時に増幅され
  webrtcvad が常時 speech と誤判定 → 発話末が 20 秒以上検出されない事故が発生 (2026-04-21)。
  SN 比優先で既定 `SHUBATAPO_AUDIO_GAIN=1.0`、ユーザは大きな声で話す運用
- **Two-way audio (スピーカ出力) はpytapoに未実装**。go2rtcのみ現実解。FW 1.2.2 は動作未検証
- `playAlarm`, `startManualAlarm`, `setAudioConfig` などプログラム制御系APIは METHOD_DO_NOT_EXIST で使えない
- `playQuickResponse`, `testUsrDefAudio` はスロット空で使えない（Tapo アプリでの事前登録が必要）
- 首振り (`moveMotor`) は正常動作

### ネットワーク構成の教訓
- GPU PC とTAPOは**同一ネットワーク網にある必要**。家庭用ルータ配下の NAT だと GPU PC から TAPO (192.168.x.x) に到達できない
- 解決策: ルータを AP (ブリッジ) モード化 + 上位でグローバル IP を取る構成で TAPO も `133.15.57.x` のグローバル帯に乗せた（大学内ネットのためファイアウォールで保護）

### Whisper の癖と対策
- **ハルシネーション**: 無音/ノイズ入力に「ご視聴ありがとうございました」「ありがとうございました」等を頻発する
- 対策: ブラックリスト除外 + `no_speech_threshold=0.6` + webrtcvad で非発話区間をゲート
- `vad_filter=False` を指定（前段で webrtcvad 済のため内蔵VAD不要）
- `condition_on_previous_text=False` で前発話の影響を断つ

### LLM 切替機構
- `SHUBATAPO_LLM_BACKEND=api` (既定): ClaudeClient (haiku-4-5、低レイテンシ、従量課金)
- `SHUBATAPO_LLM_BACKEND=code`: ClaudeCodeClient (Max プラン枠、Sonnet/Opus、追加課金なし)
- Max プラン用 OAuth トークン取得: Mac で `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` 環境変数
- `ANTHROPIC_API_KEY` を設定すると SDK がAPI課金に切替わるので注意

### 音声対話の設計原則（ユーザからの教え）
- 発話末から 1.5秒 空くと対話破綻
- 対策: 話者交替点検出 → 短い相槌を即座にTTS → 裏で本応答を生成
- LLM は軽量優先。高度処理だけクラウドに逃がす

### 運用コマンド集（よく使う）
```
# voice_loop を GPU PC で tmux 起動
ssh nishimura@133.15.57.36 "tmux new-session -d -s voice_loop 'cd ~/ShubaTapoChan && source .venv/bin/activate && python -u -m shubatapo.dialog.voice_loop 2>&1 | tee /tmp/voice_loop.log'"

# voice_loop 停止
ssh nishimura@133.15.57.36 'tmux kill-session -t voice_loop'

# Mac ランナー
./scripts/mac_runner.sh            # 普段使い（tmux 既存セッションを使う）
./scripts/mac_runner.sh --restart  # 強制再起動

# ASR の窓ごと partial 表示 (デバッグ用)
SHUBATAPO_ASR_DEBUG=1 python scripts/smoke_asr.py /tmp/sample.wav

# ゲイン上書き
SHUBATAPO_AUDIO_GAIN=30 python -m shubatapo.dialog.voice_loop
```

### C220 スピーカ出力 (go2rtc)
- `tapo://` は TP-Link 独自プロトコル。RTSP とは**別パスワード**（TP-Link クラウドアカウント、ユーザ名なし）
- Docker: `scripts/setup_go2rtc.sh` → `shubatapo-go2rtc` コンテナ (host network, :1984/:8554)
- `/tmp/shubatapo_replies` と `/tmp/shubatapo_fillers` を bind mount して絶対パスを一致させる
- HTTP API: `POST /api/streams?dst=tapo_c220&src=file:<abs>#input=file`、`src=""` で停止
- 音質上限は PCMA/8000 (電話品質)。Subaru 声質評価は Mac 経路で行う

### Git 運用
- コミット時は `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` フッタ
- .env は `.gitignore` 済、rsync で Mac → GPU PC 同期する
- `.env` のキー名は `CLAUDE_CODE_OAUTH_TOKEN` が正式（Agent SDK の規約）。`OAUTH_TOKEN` だとSDKが拾わないので注意
- `.env.example` にキー一覧を記載。新規キーを追加する時はここも更新する
