# MEMORY

## プロジェクト概要
TAPO C220（首振り対応ネットワークカメラ）＋ 大空スバル声TTS（`../Subaru_TTS`）＋ GPU PC による音声対話エージェント。物理配置は、ユーザー近傍にTAPO、遠隔にGPU PC（別室、スピーカー無し）。

## 学習した知識・教訓

### 関連プロジェクトの位置関係
- `../Subaru_TTS/`：大空スバル声TTSの学習プロジェクト（GPT-SoVITS v4候補、Phase 1データ収集段階、推論未実装）
- `../BackChannel_sugimoto_model/`：相槌タイミングモデルの学習済み重み
- `../TurnTaking_sugiyama_model/`：話者交替モデルの学習済み重み
- `../VAD_ASR_emoto_model/emoto-wav2vec2/`：VAD+ASR用wav2vec2モデル
- `/Users/sayonari/GoogleDrive_MyDrive/nishimura/program/_research_lab/VAD_ASR_emoto/`：VAD_ASR_emotoの実装コード
- `/Users/sayonari/GoogleDrive_MyDrive/nishimura/program/_research_lab/BackChannel_sugimoto/`：相槌モデルのプログラム
- `/Users/sayonari/GoogleDrive_MyDrive/nishimura/program/_research_lab/TurnTaking_sugiyama/`：話者交替モデルのプログラム

### TAPO C220 の運用知識
- 双方向音声（スピーカー再生）は `pytapo` 独自プロトコル経由（RTSP back-channelは非対応）
- RTSPマイク音声は `rtsp://<user>:<pass>@<ip>:554/stream1`、AAC 16kHz
- 認証は「Camera Account」（Tapoクラウドアカウントとは別物）
- PTZは `pytapo.moveMotor(x, y)` でC200と共通

### VAD_ASR_emoto の重要な癖
- 3秒窓を200msシフトで毎回全体推論するため、**隣接窓の出力が重複する**
- LLMに渡す前に `difflib` 等でdedup必須（やらないとコンテキスト無駄遣い）

### 音声対話の設計原則（ユーザーからの教え）
- 発話末から1.5秒空くと対話破綻
- 対策：話者交替点検出 → 短い相槌を即座にTTS → 裏で本応答を生成
- LLMは軽量オンプレ優先、高度処理だけクラウド（Claude等）に逃がす

### make_project スキルの運用
- モードAの `mkdir [PROJECT_NAME]; cd` ステップは、既に空の目的フォルダ内で実行する場合はスキップしてよい（現在フォルダを直接プロジェクトルートとする）
- GitHub リポジトリ作成は `gh repo create <name> --public --description "..."` でも可
