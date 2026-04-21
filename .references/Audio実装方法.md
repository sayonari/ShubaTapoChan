# Tapo C220 への音声流し込み：開発AI向け技術ブリーフ

## 1. 目的 / Context

TP-Link Tapo C220（PTZ機能付きWi-Fiカメラ）を、音声対話システムの
**出力スピーカー**として使いたい。外部PCで合成したTTS音声を、ネットワーク経由で
C220の内蔵スピーカーから再生したい。

- カメラ → PC 方向：RTSPで映像・音声取得（これは簡単、既にできる）
- PC → カメラ 方向：**これが本件の課題**
- PTZ（首振り）制御も将来的には同じフレームワーク上で扱いたい

## 2. 技術背景 / なぜ素直にできないのか

- C220は仕様上 two-way audio 対応（Tapoアプリの「トーク」機能）
- しかし TP-Link は **ONVIF Profile T の backchannel を出していない**
- RTSP で出てくる音声トラックは `recvonly`（PCMA/8000）で、
  書き戻しチャンネルが SDP に存在しない
- **プロプライエタリな独自プロトコル**で喋る必要があり、
  Tapoクラウドアカウントの資格情報を使う

参考（C220のRTSP SDP実例、m=audio が recvonly である様子）:
- https://github.com/AlexxIT/go2rtc/issues/1272

## 3. 実装選択肢

### ★ Option 1: go2rtc（最有力）

**Repository:** https://github.com/AlexxIT/go2rtc
**Tapoソースの仕様:** https://github.com/AlexxIT/go2rtc#source-tapo

- `tapo://` という独自スキームでTP-Linkプロプライエタリ音声をラップ
- Two-way audio 対応ソース: doorbird, dvrip, exec, ring, rtsp, **tapo**,
  tuya, webrtc, wyze, xiaomi
- **HTTP APIで任意のオーディオファイル／ストリームをカメラへpush可能**
  - ファイル再生は `#input=file` を付ける（リアルタイム変換）
  - ライブストリームは `#input` を付けない（そのままリアルタイム）
  - `src=""` をAPIに送れば再生停止 → **バージイン実装が楽**

**go2rtc 設定例（C220で動作報告あり）:**

```yaml
streams:
  tapo_c220:
    - rtsp://<rtsp_user>:<rtsp_pass>@192.168.xxx.xxx:554/stream1
    - tapo://<cloud_password>@192.168.xxx.xxx
```

- `rtsp://` はTapoアプリの「詳細設定 → カメラアカウント」で作ったユーザ
- `tapo://` の方は **TP-Linkクラウドアカウントのパスワード**
  （ユーザ名は書かない書式が安定）

**認証のバリエーション（モデル/ファームで変わる）:**
- プレーンテキスト
- MD5ハッシュ（大文字）
- **SHA256**（新しめのC220ファームではこれが通ったという報告）

動作報告（C220）:
- https://community.home-assistant.io/t/tapo-cameras-with-frigate/618520?page=2
- https://github.com/AlexxIT/go2rtc/issues/1835

つまずき事例（C220 2-way audio が通らない）:
- https://github.com/AlexxIT/go2rtc/issues/1272

---

### Option 2: pytapo（Pythonから直接叩きたい場合）

**Repository:** https://github.com/JurajNyiri/pytapo
**PyPI:** https://pypi.org/project/pytapo/
**最新版:** 3.3.51（2025-10-22時点）

- Home AssistantのTapo統合の中核ライブラリ
- 音声**送信**機能は experimental 扱い
- 作者本人による実験ブランチ `talk_experiments` に送信実装あり
- コード例・API呼び出し（getMediaSession → talk payload を
  mode="aec" で送信）は Issue #41 にサンプルコードあり：
  - https://github.com/JurajNyiri/pytapo/issues/41
- 古い要望 Issue #14（スピーカーでファイル再生したい）:
  - https://github.com/JurajNyiri/pytapo/issues/14

**用途:** go2rtcをHTTP越しに呼ぶのではなく、Pythonプロセスから直接
カメラを制御したい研究用コードを書きたい場合。対話管理やレイテンシ計測を
Python内で完結させたいならこちら。

---

### Option 3: Scrypted（参考）

**Repository:** https://github.com/koush/scrypted
- HomeKit経由でC220を扱いたい場合の選択肢
- ただしモデル依存が激しく、C220での動作報告は少ない
- 参考: https://github.com/koush/scrypted/discussions/1363

---

## 4. 推奨アーキテクチャ

音声対話システム用途では **go2rtc を中継サーバとして立てる** のが最短:

```
[TTS エンジン (PC)]
        │
        │ 生成音声 (wav/opus など)
        ▼
[HTTPで expose or 直接POST]
        │
        ▼
[go2rtc (同一PC or Docker)]
        │  tapo:// (独自プロトコル)
        ▼
[Tapo C220 スピーカー]
```

- go2rtc の HTTP API: `/api/streams?src=<url>&dst=tapo_c220`
  で任意ストリームをカメラに流せる
- バージイン（ユーザが話し始めたら再生中止）は
  `src=""` で即停止

## 5. 重要な注意事項 / 地雷

### 5.1 音質の上限
- 再生経路は **PCMA/8000 または PCMU/8000**（電話品質）
- go2rtc docs曰く「PCMA/PCMUは256段階しか表現できないVERY low-quality codec」
- **合成音声の品質評価実験には向かない**
- 対話のやり取りを成立させる用途では十分

### 5.2 ファームウェア依存
- Tapoの新しいファームでtapo://プロトコルが壊れるケースあり
- 「C220をファームウェアダウングレードしたら動いた。ただし一度下げると
  最新に戻せなくなった」という報告あり
- **自動更新は真っ先に切る**
- 購入時のファームウェア・ロットは記録しておく
- 参考: https://github.com/blakeblackshear/frigate/discussions/8963

### 5.3 認証情報の使い分け
- **RTSP接続用**: Tapoアプリ → 詳細設定 → カメラアカウント で設定したユーザ/パス
- **tapo:// 接続用**: TP-Linkクラウドアカウントのパスワード（ユーザ名は不要）
- 記号を含む複雑なクラウドパスワードだと失敗するケースあり（シンプル推奨）
- 2025年時点のC220ではSHA256ハッシュ化が必要なケースも

### 5.4 ローカル化
- tapo:// は初期化時にクラウド認証するが、以降はLAN内で完結可能
- プライバシー重視ならVLAN分離＋インターネット遮断の構成を推奨
- 参考: https://github.com/AlexxIT/go2rtc/issues/1494

## 6. 参考URL まとめ

### 主要リポジトリ
- go2rtc: https://github.com/AlexxIT/go2rtc
- go2rtc Tapoソース仕様: https://github.com/AlexxIT/go2rtc#source-tapo
- pytapo: https://github.com/JurajNyiri/pytapo
- HomeAssistant-Tapo-Control: https://github.com/JurajNyiri/HomeAssistant-Tapo-Control

### 公式
- Tapo C220 製品ページ: https://www.tapo.com/en/product/smart-camera/tapo-c220/

### コミュニティ / 動作報告
- HA Community（Tapo+Frigate, C220動作例あり）:
  https://community.home-assistant.io/t/tapo-cameras-with-frigate/618520?page=2
- HA Community（C100/C210でTTS再生ガイド、C220にも流用可）:
  https://community.home-assistant.io/t/guide-tapo-camera-c100-c210-tts-on-camera-speaker/889744
- HA Community（Frigate+C320wsで双方向音声）:
  https://community.home-assistant.io/t/solved-2-way-audio-with-frigate-tapo-cameras-c320ws/793219

### 関連Issue
- TP-Link Tapo C220 2-Way Audio Issue:
  https://github.com/AlexxIT/go2rtc/issues/1272
- Does Two way audio still work with new Tapo cameras?:
  https://github.com/AlexxIT/go2rtc/issues/1494
- How to achieve two-way voice:
  https://github.com/AlexxIT/go2rtc/issues/1460
- Tapo 2-way audio button appears but loading（C220, 2025-08）:
  https://github.com/AlexxIT/go2rtc/issues/1835
- pytapo: Add ability to send audio to camera:
  https://github.com/JurajNyiri/pytapo/issues/41

## 7. 開発AIへの依頼ポイント（サジェスチョン）

1. **最初のマイルストーン**: go2rtc を Docker で立てて、
   C220に対して `tapo://` ソースが load できるか確認する
   - `http://localhost:1984/` のWebUIで2-way audioアイコンが出ればOK
2. **2つ目**: WebUI からマイク入力が C220 スピーカーから出るか検証
   （認証情報の形式を確定させるため）
3. **3つ目**: HTTP API 経由で事前録音した wav をpushして鳴らす
4. **4つ目**: TTS出力を streaming で go2rtc に流す
   （ファイル化せずに）
5. **5つ目**: バージイン（`src=""`で即停止）のレイテンシ実測
6. **研究用計測**: end-to-endレイテンシ（TTS生成開始→カメラ発音開始）と、
   停止コマンドからの発音停止までのレイテンシを測定