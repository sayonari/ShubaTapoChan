# HANDOFF - 2026-04-17 11:14

## 使用ツール
Claude Code Opus 4.7 (1M context)

## 現在のタスクと進捗
- [x] プロジェクト初期構築（make_projectスキル モードA） — 完了、GitHubへpush済み
  - リポジトリ: https://github.com/sayonari/ShubaTapoChan (public)
  - 初回コミット: `8734817` — first commit (15ファイル/247行)
- [x] PLAN.md ヒアリング、関連資産・TAPO C220調査 — 完了
- [x] SPEC.md / TODO.md / KNOWLEDGE.md 初稿作成 — 完了
- [ ] Phase 0: TAPO C220 物理セットアップ — **ユーザー作業待ち**
- [ ] Phase 1 以降: 次セッションで着手

## 試したこと・結果
- **成功**:
  - プロジェクトフォルダ構造の構築（`.agent/`, `.claude/commands`, `.spec/`, `.output/`, `.references/`）
  - GitHub public リポジトリ `sayonari/ShubaTapoChan` を `gh repo create` で作成
  - 既存資産の状態確認: `../Subaru_TTS` はPhase 1(データ収集)・まだ推論不可 / VAD_ASR_emoto はwav2vec2(`SiRoZaRuPa/wav2vec2-kanji-base-char-0916`)で動作中
  - TAPO C220 の音声双方向・PTZ制御は `pytapo` ライブラリで実装可能と確認
- **未試行（次回）**:
  - `.env` 内容の確認（GPU PCログイン情報・TAPO認証情報）
  - GPU PC実環境での接続・疎通確認

## ユーザー承認済みの設計判断（D1-D4）
- **D1 ASR**: VAD_ASR_emoto方式（wav2vec2 + 3s/200msスライディング窓 + dedup）を採用
- **D2 TTS**: Subaru_TTS完成を待つ。間に合わなければpyttsx3/VOICEVOXなど簡易TTSで仮実装
- **D3 音声出力**: TAPO C220スピーカー限定（GPU PCは物理的に別室でスピーカー無し）。`pytapo` のTwo-way audio使用
- **D4 開発環境**: Mac編集 / GPU PC SSH実行 / GitHub経由同期（AI判断）

## 次のセッションで最初にやること
1. **AGENTS.md のルールに従い、`.agent/memory/MEMORY.md` と本ファイルを読み込んで報告**
2. `.env` の中身を確認する（GPU PC接続情報、TAPO認証情報の有無・形式）
3. ユーザーに以下を確認：
   - **TAPO C220の物理セットアップ（Phase 0）が終わっているか**
     - Tapoアプリでのアカウント追加・Wi-Fi接続
     - Advanced Settings → Camera Account の作成
     - IPアドレスの固定
     - `ffprobe rtsp://<user>:<pass>@<ip>:554/stream1` 疎通確認
     - `.env` への情報記載
   - GPU PCとTAPOが同一LANか、VPNが必要か
   - 仮TTSは何を使うか（pyttsx3 / VOICEVOX など）— Subaru_TTS完成を待てる期間の見通し
4. 確認が取れたら **Phase 1: GPU PC環境構築** に着手
   - SSH接続確認 → venv作成 → 依存インストール → pytapo smoke test（`moveMotor` 1回呼ぶ）→ RTSP 10秒録音WAV

## 注意点・ブロッカー
- **Phase 0 はユーザー物理作業**。ユーザーがTAPO C220を開封した直後（2026-04-17時点で未設定・未通電）
- **TAPO C220 Two-way audio はFW依存**で動かない報告あり。初期検証は `pytapo/examples/send_audio.py` 相当で先に疎通確認する
- **Subaru_TTS は `../Subaru_TTS/` でまだ学習中**。MVP着手時点では推論API未提供。仮TTSで開発を進め `TTSClient` 抽象で差し替え可能に
- **自己発話フィードバック回避**: TAPOスピーカー→TAPOマイクの無限ループ防止のため、SPEAKING中のASRゲートは必須
- **GPU PCとTAPOの物理ネットワーク関係が未確認**。別ネットワークならTailscale等のVPNが必要
- ユーザーは会議参加のため10分後にPCを閉じる予定。今回のセッションはここで終了想定
