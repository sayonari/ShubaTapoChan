# TODO - タスクリスト

## 🔥 急務（次セッション最優先）

### C220 スピーカ出力 (go2rtc) 実機検証
- [ ] GPU PC に `.env` の TAPO_CLOUD_PASSWORD を追加
- [ ] GPU PC で `./scripts/setup_go2rtc.sh` を実行して go2rtc コンテナ起動
- [ ] WebUI (`http://133.15.57.36:1984/`) で `tapo_c220` が両ソース緑になるか確認
- [ ] `SHUBATAPO_AUDIO_OUT=tapo` に切り替えて voice_loop 実機テスト
- [ ] 駄目な場合: パスワード認証形式 (plain/MD5/SHA256) を切替、FW ダウングレード検討

### 相槌／persona の実機確認
- [ ] `./scripts/mac_runner.sh --restart` で起動
- [ ] ASR 発話末で ack WAV が即再生 → main が続く流れを体感で確認
- [ ] persona (subaru) のトーンが応答に反映されているか確認

## 優先度：高

### ASR / TAPO 音声品質の根本改善
- [ ] TAPO アプリでノイズキャンセリング off / マイクボリューム最大を試す
- [ ] 50倍ゲインではなく、AGC (automatic gain control) を実装検討
- [ ] VAD しきい値チューニング（低音量でも取りこぼさないか）

### mac_runner 安定性改善
- [ ] SSH ポーリングが時々スタックする問題の調査
  - 候補: `rsync --partial --append`, `sshfs + fswatch`, `inotifywait` 経由
- [ ] プロセス重複起動防止（単一インスタンスロック）

### C220 統合運用
- [ ] C220 スピーカ運用時のマイク自己発話取り込み対策 (簡易 mute タイミング制御)
- [ ] バージイン実装: ユーザ発話開始検出 → `tapo_speaker.stop()`
- [ ] 応答と相槌の重複再生を避ける（main 送信前に ack 完了を待つか、固定 sleep を調整）

## 優先度：中

### 対話の自然さ
- [ ] 会話履歴の上限（現在6ターン）の最適化
- [ ] Claude Haiku → Sonnet に切り替えた場合の応答品質比較
- [ ] Max プラン経由と API 経由の体感差

### LLM のマルチモーダル化 (次の大きなマイルストーン)
- [ ] TAPO カメラから定期的にスナップショット取得 (pytapo or RTSP video フレーム)
- [ ] Claude のマルチモーダル API (image block) に画像＋partial テキストを渡す
- [ ] 画像が必要そうなクエリの自動判定 (例: 「これは何？」「スバル見える？」)
- [ ] 首振り (moveMotor) を LLM tool use で制御
- [ ] Persona に「目 (カメラ) から何が見える」という文脈を持たせる

### 応答音声のバージイン / 古い応答の破棄 (2026-04-21 追加)
- [x] Mac runner: 最新ターンより古い応答はスキップ
- [ ] ユーザ発話開始検出時に再生中の応答を afplay kill で中断 (真のバージイン)
- [ ] voice_loop 側でもスタック時に古い turn の TTS 合成をキャンセル

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
- [x] 相槌 (backchannel) 実装: prepare_fillers → turn_NNN_ack.wav → turn_NNN_main.wav
- [x] mac_runner の `.played` ベース未再生全ダウンロード方式（ack→main が名前順で再生）
- [x] キャラ設定様式 `personas/<name>.yaml` と Persona ローダ、大空スバル初期値
- [x] go2rtc サイドカー: `scripts/setup_go2rtc.sh`、`config/go2rtc.yaml.template`
- [x] TapoSpeakerClient (go2rtc HTTP API で C220 スピーカに push)
- [x] voice_loop に `SHUBATAPO_AUDIO_OUT=mac|tapo|both` 切替実装
- [x] `.env.example` 作成（TAPO_CLOUD_PASSWORD 等のキー一覧を明文化）
