# TODO - タスクリスト

## 🔥 急務（次セッション最優先）

### 相槌 (backchannel) による体感遅延削減
ユーザ発話末検出時、LLM 処理を待たずに短い相槌を先行再生して遅延をマスクする。
- [x] `src/shubatapo/dialog/fillers.py` : 相槌フレーズのTTSキャッシュモジュール (雛形)
- [ ] `src/shubatapo/dialog/voice_loop.py` 改修:
  - 起動時に `prepare_fillers()` で `/tmp/shubatapo_fillers/` にキャッシュ作成
  - ASR 発話末確定時、LLM 呼び出しの**直前**にランダム1つを `turn_NNN_ack.wav` としてコピー
  - 続けて LLM → TTS → `turn_NNN_main.wav` に出力
- [ ] `scripts/mac_runner.sh` の再生ロジック改修:
  - `.played` 履歴ファイルで未再生分を全て名前順ダウンロード・afplay
  - 起動時に現在リモートの全 WAV を `.played` で初期化（古い応答の再生防止）
  - 同時に「ターン取りこぼし」問題も解消される
- [ ] 動作確認: 発話 → 相槌即時再生 → 応答がスムーズに続く

## 優先度：高

### ASR / TAPO 音声品質の根本改善
- [ ] TAPO アプリでノイズキャンセリング off / マイクボリューム最大を試す
- [ ] 50倍ゲインではなく、AGC (automatic gain control) を実装検討
- [ ] VAD しきい値チューニング（低音量でも取りこぼさないか）

### mac_runner 安定性改善
- [ ] SSH ポーリングが時々スタックする問題の調査
  - 候補: `rsync --partial --append`, `sshfs + fswatch`, `inotifywait` 経由
- [ ] プロセス重複起動防止（単一インスタンスロック）

## 優先度：中

### TAPO スピーカ出力 (Phase 7)
- [ ] go2rtc サイドカー構成の検証
- [ ] C220 FW 1.2.2 Build 260311 で go2rtc tapo backchannel が動くか検証
- [ ] 動かない場合の FW ダウングレード手順

### 対話の自然さ
- [ ] 会話履歴の上限（現在6ターン）の最適化
- [ ] Claude Haiku → Sonnet に切り替えた場合の応答品質比較
- [ ] Max プラン経由と API 経由の体感差

### LLM のマルチモーダル化
- [ ] TAPO カメラ画像を Claude に渡す経路
- [ ] 首振り (moveMotor) を LLM tool use で制御
- [ ] 画像が必要そうなクエリの自動判定

## 優先度：低（後続フェーズ）

- [ ] Subaru_TTS の長期学習完了モデル(50 epoch)への切替
- [ ] 起動ワード「おーいスバルさん」検出 → 待機モード / 詳細対話モード切替
- [ ] 相槌タイミングモデル (BackChannel_sugimoto) との統合 (ML 相槌)
- [ ] 話者交替モデル (TurnTaking_sugiyama) との統合
- [ ] エコーキャンセル (TAPO スピーカ出力復活時の自己発話再取り込み防止)
- [ ] 複数ユーザ対応（話者分離）

## 完了済み
- [x] プロジェクト初期構築（ShubaTapoChan、GitHub push）
- [x] PLAN / SPEC 初稿確定
- [x] 関連資産調査（Subaru_TTS, VAD_ASR_emoto, TAPO C220/pytapo）
- [x] TAPO C220 物理セットアップ（AP mode + 専用WiFiルータでグローバルIP化）
- [x] GPU PC SSH 疎通、Python venv、PyTorch 2.6+cu124、CUDA 確認
- [x] pytapo smoke test（moveMotor、getBasicInfo）
- [x] RTSP 16kHz PCM ストリーム取得（ffmpeg subprocess）
- [x] ASR: SlidingWindowASR (wav2vec2) → WhisperASR (faster-whisper + webrtcvad) にリプレース
- [x] Whisper ハルシネーション対策（ブラックリスト + no_speech_threshold）
- [x] 50倍ゲインでTAPO低音量対策
- [x] LLM: Claude API (Haiku 4.5) 実装、smoke 確認
- [x] LLM: Claude Agent SDK 経由 (Max プラン) 実装、smoke 確認
- [x] LLM バックエンド切替 (SHUBATAPO_LLM_BACKEND=api|code)
- [x] Subaru TTS HTTP クライアント、参照音声 seg_000143.wav で品質改善
- [x] テキスト対話ループ (text_loop)
- [x] 音声対話ループ (voice_loop) — エンドツーエンド動作確認
- [x] Mac ランナー (mac_runner.sh) — GPU PC tmux 常駐 + Mac scp + afplay
- [x] 起動時 Subaru ボイスで挨拶プロンプト
