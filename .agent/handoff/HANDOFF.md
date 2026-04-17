# HANDOFF - 2026-04-17 19:22

## 使用ツール
Claude Code Opus 4.7 (1M context)

## 本日の到達点：音声対話エージェント MVP がエンドツーエンドで動作

### ✅ 動作確認済みパイプライン
```
ユーザ発話 → TAPO C220 マイク (RTSP)
         → GPU PC (Rasiel / RTX 3090 / Ubuntu 24.04)
           ├─ ffmpeg: RTSP 16kHz PCM変換
           ├─ 50倍ゲイン補正 (TAPO 音声が極端に低レベルのため)
           ├─ WhisperASR (faster-whisper large-v3 + webrtcvad)
           │   └─ ハルシネーション除外 (ご視聴ありがとうございました等)
           ├─ LLM (Claude API haiku-4-5 既定 / SHUBATAPO_LLM_BACKEND=code で Max プラン)
           └─ Subaru TTS (GPT-SoVITS v4 @ :8766, ref=seg_000143)
         → /tmp/shubatapo_replies/turn_NNN.wav
Mac側 mac_runner.sh → 新 WAV を scp → afplay で再生
```

### 検証ログ (19:16〜)
```
you> こんにちは
subaru> こんにちは！今日も元気だぜ～。なんか話したいことある？    (1.17s)
you> 聞こえますか?
subaru> あ、聞こえてるよ。ちゃんと聞こえてる！    (0.89s)
you> すごい!
subaru> ありがとう！嬉しい。    (0.91s)
...
```

## 現在のタスクと進捗
- [x] プロジェクト初期構築・GitHub リポジトリ作成
- [x] TAPO C220 物理セットアップ (AP mode + 専用WiFiルータでグローバルIP化)
- [x] GPU PC 環境構築 (Python 3.12 venv, PyTorch 2.6+cu124)
- [x] RTSP 音声入力パイプライン (ffmpeg + 50倍ゲイン)
- [x] WhisperASR (faster-whisper large-v3 + webrtcvad + ハルシネーション除外)
- [x] Subaru TTS HTTP クライアント
- [x] LLM バックエンド 2 種 (API / Max via Claude Agent SDK)
- [x] mac_runner.sh: Mac スピーカ出力対応、tmux常駐起動、起動プロンプトをSubaruボイス化
- [x] 参照音声を seg_000143 (家庭教師) に切替で合成品質改善
- [ ] **相槌 (backchannel) による体感遅延削減** ← 急務 TODO
- [ ] ASR精度・TAPO音声レベル改善 (マイク距離、ノイキャン off など)
- [ ] TAPOスピーカ出力 (go2rtc サイドカー, Phase 7)
- [ ] 話者交替モデル・起動ワード・カメラ画像入力

## 急務 TODO: 相槌実装（本日未完了）
**ユーザ要望 (19:18):**
> 応答を返すのが遅いので，こちらの入力の終了点が来たら，即，相槌的な短い応答を「おー」とか「うーん」とか「はいはい」とかそういうのを再生しつつ，その間に，LLM応答生成と音声合成を待っている　というシステム動作にして，遅延を感じさせない工夫をインプリしてほしい

### 実装方針（途中まで）
- [x] `src/shubatapo/dialog/fillers.py` 雛形作成済 (prepare_fillers で起動時に複数フレーズを TTS キャッシュ)
- [ ] `voice_loop.py` の改修
  - 起動時に prepare_fillers で `/tmp/shubatapo_fillers/` にキャッシュ作成
  - ASR 発話末確定時、**LLM呼び出しの直前**にランダム1つを `/tmp/shubatapo_replies/turn_NNN_ack.wav` にコピー
  - 続けて LLM → TTS → `/tmp/shubatapo_replies/turn_NNN_main.wav` に出力
- [ ] `mac_runner.sh` の改修
  - 現状 `ls -1t | head -1` で**最新1個**だけ拾うため、ack と main のどちらかが抜ける
  - 変更案: `played` ログを `$LOCAL_DIR/.played` に持ち、未再生ファイルを**名前順**で全部ダウンロード・再生
  - `turn_NNN_ack.wav` < `turn_NNN_main.wav` の名前順が afplay 再生順になる
- [ ] 起動時に `$LOCAL_DIR/.played` を現在リモートの全 WAV で初期化（古い応答の再生防止）

### 参考設計メモ
- 相槌フレーズ例: うーん、はいはい、おーっ、なるほどー、えっと、そっかー
- キャッシュは GPU PC 上: `/tmp/shubatapo_fillers/filler_*.wav`
- 再生順: ack (0.5-1.5秒) → main (2-8秒) のシーケンス
- Whisper+LLM+TTS 合計 3〜5秒のタイムラインで、ack が LLM 処理をマスクする

## 試したこと・結果
### 成功
- TAPO C220 双方向音声は go2rtc 以外に実装なし、との調査結果を得て Mac スピーカ出力に方針転換
- Subaru TTS 参照音声を seg_000001 (風呂) → seg_000143 (家庭教師) に変更で合成品質が明確に改善
- `tmux new-session -d -s voice_loop` で GPU PC 側を常駐化、Mac 側ランナー再起動でも voice_loop が死なない構成に
- 50倍ゲインで TAPO の極端な低音量 (RMS 8〜30) を補正、ASR が安定動作
- Claude Max プランの OAuth トークン連携 (claude-agent-sdk) も動作確認済

### 失敗・保留
- TAPO の `setAudioConfig`, `playAlarm`, `setSirenStatus` は全て METHOD_DO_NOT_EXIST でプログラム制御不可
- pytapo 3.4.13 に Two-way audio API は無し (Issue #41 で実験頓挫)。`playQuickResponse`/`testUsrDefAudio` は空データで使えず
- Whisper ハルシネーション「ご視聴ありがとうございました」が無音時に頻出 → ブラックリスト除外で対処
- 短いプロンプト「しゃべってー！」は GPT-SoVITS で合成品質が崩れる → 長めの文「準備できたよー！で、今日は何だっけ？」に変更

## 次のセッションで最初にやること
1. **AGENTS.md のルールに従い `.agent/memory/MEMORY.md` と本ファイルを読み込み報告**
2. **急務TODO: 相槌実装**
   - `src/shubatapo/dialog/fillers.py` を確認 (雛形作成済)
   - `src/shubatapo/dialog/voice_loop.py` に `prepare_fillers()` 呼び出し・ack WAV コピー処理追加
   - `scripts/mac_runner.sh` の再生ロジックを `.played` ベースに書き換え
   - 起動順序は `HANDOFF.md` の「実装方針」セクション参照
3. テスト: `./scripts/mac_runner.sh --restart` で起動 → 発話 → 「うーん」系が先行再生 → 応答がスムーズに続くことを確認

## 注意点・ブロッカー
- **TAPO 音声が異常に低レベル**（RMS 8-30、通常 1000-5000）。現状は 50 倍ゲインで誤魔化しているが、Tapo アプリでノイキャン off、音量 100 以上にできないか確認した方が根本的
- **SSH ポーリングが時々スタックする**（理由不明、mac_runner が応答しなくなる）。再起動で解決。将来的には inotify/sshfs+fswatch等に変更検討
- **ターン間の応答ファイル取りこぼし**が起きる（mac_runner が最新1個しか取らないため）。相槌実装時の再生ロジック改修で同時に解消される
- **Anthropic API クレジット**: $25 購入済。haiku-4-5 で 1 ターン ~$0.001 程度なので当面消費は軽い
- **Claude Max プラン経由**: `SHUBATAPO_LLM_BACKEND=code` で切替、OAuth トークンは .env の CLAUDE_CODE_OAUTH_TOKEN
- **`.env` は現在 OAUTH_TOKEN で設定（CLAUDE_CODE_OAUTH_TOKEN ではない）**。Max 経由を使う場合はキー名を `CLAUDE_CODE_OAUTH_TOKEN` に戻す or factory でフォールバックを追加する必要あり
- **voice_loop を止めるには**: `ssh nishimura@133.15.57.36 'tmux kill-session -t voice_loop'`

## 本日のコミット主要項目 (新しい順抜粋)
- `3416692` ゲイン 20→50 (TAPO 低音量対策)
- `a4019b7` 50倍ゲイン既定 (SHUBATAPO_AUDIO_GAIN)
- `04a93b2` プロンプト文言を長めに (GPT-SoVITS 品質改善)
- `24be775` mac_runner: tmux 常駐化で安定動作
- `ff0d908` scripts/mac_runner.sh: Mac スピーカ再生ランナー
- `8aaa585` TTS参照音声を seg_000143.wav に変更
- `e666817` mac_runner: Subaru TTS 合成プロンプト使用
- `bcb4b24` WhisperASR: ハルシネーション対策強化
- `a1f9f2e` ASR を faster-whisper + webrtcvad にリプレース
- `c20b6c2` LLM バックエンド API / Max 切替可能に
