# Streamlit Community Cloudへの公開手順

1. GitHubで新しいPublic repositoryを作成します。例: `rakuten-ai-affiliate`
2. このフォルダのファイルをrepositoryのルートへアップロードします。
3. https://share.streamlit.io/ にログインし、GitHubを接続します。
4. `Create app` → `Yup, I have an app.` を選び、repository・branch・`app.py` を指定してDeployします。
5. `Advanced settings` → `Secrets` に `.streamlit/secrets.toml.example` の内容を貼り付け、実際の楽天APIキーとOpenAI APIキーを入力してSaveします。
6. 公開された `https://<subdomain>.streamlit.app` を楽天のアプリケーションURLに設定します。
7. 楽天の「許可されたウェブサイト」には同じ公開ドメインを入力します。

注意: `secrets.toml` 本体やAPIキーをGitHubにコミットしないでください。
