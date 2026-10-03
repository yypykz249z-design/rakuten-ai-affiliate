# 楽天AIアフィリエイト運用システム MVP

楽天市場の商品検索APIを使って商品候補を収集し、説明可能なヒューリスティックでAIスコアを付け、SNS投稿文のたたき台を生成・保存するローカルWebアプリです。

## 1. 準備

Python 3.11+ を推奨。

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

`.env.example` を `.env` にコピーして認証情報を設定します。

必要な楽天側情報:
- Application ID
- Access Key
- Affiliate ID

楽天市場商品検索APIの現行エンドポイントは 2026-07-01 版です。

## 2. 起動

```bash
streamlit run app.py
```

## 3. AIについて

`OPENAI_API_KEY` を設定すると投稿文生成に OpenAI Responses API を使います。
キーが無い場合もアプリ自体はデモ用の簡易テンプレートで動きます。

## 4. SNSについて

このMVPは誤投稿を避けるため、まず「商品選定→投稿案生成→下書き保存」までです。
本番版ではSNSごとの公式API/OAuthに接続し、予約投稿を追加します。

## 5. 注意

楽天アフィリエイトの規約・ガイドラインに従って運用してください。大量の機械的投稿や禁止されているメッセージツールでのリンク送信などを自動化しない設計にしてください。
