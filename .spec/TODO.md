# TODO - タスクリスト

## 優先度：高（次回セッションで着手）

### Phase 0: TAPO C220 物理セットアップ（人間作業）
- [ ] Tapoアプリでカメラを初期設定し、Wi-Fi接続
- [ ] Advanced Settings → Camera Account を作成（RTSP/pytapo用）
- [ ] ルーターでTAPOのIPをDHCP予約（固定IP化）
- [ ] 別PCから `ffprobe rtsp://<user>:<pass>@<ip>:554/stream1` で疎通確認
- [ ] TAPO認証情報・IP・ファームウェアバージョンを `.env` に記載
- [ ] GPU PCとTAPOが同一LANにあるか確認（異なればTailscale等の検討）

### Phase 1: GPU PC環境構築
- [ ] `.env` の内容確認（GPU PCログイン情報、TAPO認証情報）
- [ ] GPU PCへSSH接続確認スクリプト作成
- [ ] Python 3.12 venv 作成、主要依存のインストール（pytapo, av, transformers, torch, anthropic, webrtcvad-wheels, silero-vad, pyttsx3 or VOICEVOX client）
- [ ] pytapoでTAPOへ接続し `moveMotor(0, 0)` 動作確認する smoke test
- [ ] RTSPから10秒だけ録音しWAV保存するスクリプト（疎通確認）

### Phase 2: 音声入力パイプライン
- [ ] RTSP → ffmpeg/PyAV → 16kHz mono PCM のストリーム実装
- [ ] リングバッファ（3〜5秒）とVAD（webrtcvad）のゲート
- [ ] 発話開始/終了イベントをコールバックで発火

### Phase 3: ASR組み込み
- [ ] VAD_ASR_emoto の `mod_record.py` を参照しながら、ASRコアを切り出し（GPU対応）
- [ ] スライディング窓（3s/200ms）でwav2vec2推論
- [ ] 窓間出力の dedup ロジック実装（difflibベース）
- [ ] 発話終了時に確定テキスト1本を発行するAPI

## 優先度：中

### Phase 4: LLM接続
- [ ] `LLMClient` 抽象インターフェイス定義
- [ ] Claude API 実装（`claude-haiku-4-5` 既定、`messages.create` でストリーミング対応）
- [ ] 会話履歴の保持（直近N往復）

### Phase 5: 仮TTS + TAPOスピーカー出力
- [ ] `TTSClient` 抽象インターフェイス定義
- [ ] Phase A実装：pyttsx3 または VOICEVOX HTTP クライアント
- [ ] pytapo Two-way audio 送信のラッパー実装
- [ ] `send_audio.py` 相当でWAV1本の疎通確認
- [ ] SPEAKING中のマイクゲート実装

### Phase 6: エンドツーエンド対話ループ
- [ ] 状態機械 `IDLE/LISTENING/PROCESSING/SPEAKING` 実装
- [ ] エンドツーエンド手動テスト（「こんにちは」→応答が聞こえるか）
- [ ] 遅延計測（各ステージのタイムスタンプ記録）

## 優先度：低（後続フェーズ、SPEC Phase 7）

- [ ] Subaru_TTS 完成後、`TTSClient` Phase B 実装に差し替え
- [ ] PTZ制御（pytapo moveMotor）を LLM tool use として公開
- [ ] 起動ワード「おーいスバルさん」検出
- [ ] 相槌タイミングモデル（BackChannel_sugimoto）統合
- [ ] 話者交替モデル（TurnTaking_sugiyama）統合
- [ ] TAPOのカメラ画像をマルチモーダルLLMに渡す経路
- [ ] 待機モード / 詳細音声対話モードの切替

## 完了済み
- [x] 初期セットアップ（ShubaTapoChan プロジェクト構築、GitHub push）
- [x] PLAN / SPEC 初稿確定
- [x] 関連資産の調査（Subaru_TTS、VAD_ASR_emoto、TAPO C220/pytapo）
