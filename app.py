import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DB_PATH = os.getenv("DB_PATH", "affiliate.db")
RAKUTEN_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"

st.set_page_config(page_title="楽天AIアフィリエイト運用システム", page_icon="🛒", layout="wide")


def secret_or_env(name, default=""):
    """Read Streamlit Community Cloud secrets first, then environment variables."""
    try:
        value = st.secrets.get(name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            item_code TEXT,
            item_name TEXT,
            affiliate_url TEXT,
            platform TEXT,
            caption TEXT,
            status TEXT DEFAULT 'draft'
        )"""
    )
    conn.commit()
    return conn


def as_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def as_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def item_score(item: dict) -> float:
    price = as_float(item.get("itemPrice"))
    review_avg = as_float(item.get("reviewAverage"))
    review_count = as_int(item.get("reviewCount"))
    affiliate_rate = as_float(item.get("affiliateRate"))
    postage_free = as_int(item.get("postageFlag")) == 1
    available = as_int(item.get("availability")) == 1

    score = 0.0
    # Explainable heuristic; not a promise of conversion performance.
    score += min(review_avg / 5 * 25, 25)
    score += min((review_count ** 0.5) / 20 * 25, 25)
    score += min(affiliate_rate / 10 * 25, 25)
    if 2000 <= price <= 15000:
        score += 10
    elif 1000 <= price <= 30000:
        score += 5
    if postage_free:
        score += 5
    if available:
        score += 5
    return round(min(score, 100), 1)


def search_rakuten(keyword, application_id, access_key, affiliate_id, hits=30,
                   min_price=None, max_price=None, min_affiliate_rate=None,
                   review_only=True, postage_free=False, sort="-reviewCount"):
    params = {
        "applicationId": application_id,
        "keyword": keyword,
        "affiliateId": affiliate_id,
        "format": "json",
        "formatVersion": 2,
        "hits": hits,
        "page": 1,
        "availability": 1,
        "hasReviewFlag": 1 if review_only else 0,
        "imageFlag": 1,
        "sort": sort,
    }
    if min_price:
        params["minPrice"] = int(min_price)
    if max_price:
        params["maxPrice"] = int(max_price)
    if min_affiliate_rate:
        params["minAffiliateRate"] = float(min_affiliate_rate)
    if postage_free:
        params["postageFlag"] = 1

    # Rakuten Web Service access control may require an HTTP Referer when
    # the app is registered as a web application. Streamlit server-to-server
    # requests do not automatically carry the browser's Referer header, so
    # we send the deployed app URL explicitly. It can be overridden via the
    # RAKUTEN_REFERER secret/environment variable if the app URL changes.
    referer = secret_or_env(
        "RAKUTEN_REFERER",
        "https://rakuten-ai-affiliate-h2lj9darp4kpoxfkanyqcg.streamlit.app/",
    )
    if referer and not referer.endswith("/"):
        referer += "/"

    headers = {
        "accessKey": access_key,
        "Referer": referer,
    }
    r = requests.get(RAKUTEN_ENDPOINT, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    return payload.get("Items", payload.get("items", []))


def normalize_items(raw_items):
    rows = []
    for item in raw_items:
        if "item" in item and isinstance(item["item"], dict):
            item = item["item"]
        rows.append({
            "商品名": item.get("itemName", ""),
            "価格": as_int(item.get("itemPrice")),
            "評価": as_float(item.get("reviewAverage")),
            "レビュー数": as_int(item.get("reviewCount")),
            "料率%": as_float(item.get("affiliateRate")),
            "送料無料": "○" if as_int(item.get("postageFlag")) == 1 else "",
            "在庫": "○" if as_int(item.get("availability")) == 1 else "",
            "選定スコア": item_score(item),
            "アフィリエイトURL": item.get("affiliateUrl") or item.get("itemUrl", ""),
            "商品コード": item.get("itemCode", ""),
            "画像": (item.get("mediumImageUrls") or item.get("smallImageUrls") or [""])[0] if isinstance(item.get("mediumImageUrls") or item.get("smallImageUrls"), list) else "",
            "説明": item.get("catchcopy", ""),
        })
    return rows


def ai_generate(product, platform, tone, extra_instruction=""):
    api_key = secret_or_env("OPENAI_API_KEY")
    model = secret_or_env("OPENAI_MODEL", "gpt-5.6")
    if not api_key:
        # Safe demo fallback so the app works without an OpenAI key.
        base = product["商品名"]
        lead = "楽天で見つけた、ちょっと気になるアイテム。"
        if tone == "短く":
            text = f"{lead}\n{base}\n\n気になったらチェックしてみてください。\n#楽天市場 #楽天ROOM"
        else:
            text = (f"{lead}\n\n【{base}】\n"
                    "価格・レビュー・使いやすさを見ながら選びやすい商品です。\n"
                    "気になったら詳細をチェックしてみてください。\n\n"
                    "※アフィリエイトリンクを含みます。\n"
                    "#楽天市場 #楽天アフィリエイト #買い物"
                    )
        return text

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    prompt = f"""
あなたは日本語SNSマーケティング担当です。楽天アフィリエイト用の投稿案を作成してください。
誇張・虚偽・根拠のない効果効能は書かず、商品データにない事実を断定しないでください。
平台: {platform}
トーン: {tone}
商品名: {product['商品名']}
価格: {product['価格']}円
評価: {product['評価']}
レビュー数: {product['レビュー数']}
アフィリエイト料率: {product['料率%']}%
商品説明: {product['説明']}
追加指示: {extra_instruction}
最後に「※アフィリエイトリンクを含みます。」を入れてください。
ハッシュタグを3〜6個付けてください。
"""
    response = client.responses.create(model=model, input=prompt)
    return response.output_text


def save_post(product, platform, caption, status="draft"):
    conn = db()
    conn.execute(
        "INSERT INTO posts(created_at,item_code,item_name,affiliate_url,platform,caption,status) VALUES(?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), product.get("商品コード", ""), product.get("商品名", ""), product.get("アフィリエイトURL", ""), platform, caption, status),
    )
    conn.commit()
    conn.close()


def extract_recent_posts(limit=50):
    conn = db()
    df = pd.read_sql_query("SELECT * FROM posts ORDER BY id DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df


st.title("🛒 楽天AIアフィリエイト運用システム")
st.caption("商品発掘 → AI選定 → SNS投稿文生成 → 投稿管理。まずは半自動MVPとして運用します。")

with st.sidebar:
    st.header("設定")
    app_id = st.text_input("楽天 Application ID", value=secret_or_env("RAKUTEN_APPLICATION_ID"), type="password")
    access_key = st.text_input("楽天 Access Key", value=secret_or_env("RAKUTEN_ACCESS_KEY"), type="password")
    affiliate_id = st.text_input("楽天 Affiliate ID", value=secret_or_env("RAKUTEN_AFFILIATE_ID"), type="password")
    st.divider()
    keyword = st.text_input("検索キーワード", "便利グッズ")
    min_price = st.number_input("最低価格", min_value=0, value=1000, step=500)
    max_price = st.number_input("最高価格", min_value=0, value=15000, step=500)
    min_rate = st.number_input("最低アフィリエイト料率(%)", min_value=0.0, max_value=99.9, value=2.0, step=0.5)
    hits = st.slider("取得件数", 5, 30, 20)
    review_only = st.checkbox("レビューあり", value=True)
    postage_free = st.checkbox("送料無料のみ", value=False)
    sort = st.selectbox("楽天側の並び", ["-reviewCount", "-reviewAverage", "-affiliateRate", "standard", "+itemPrice"])
    demo_mode = st.checkbox("デモモード（認証不要）", value=not bool(app_id and access_key and affiliate_id))
    search_clicked = st.button("🔎 商品候補を取得", type="primary", use_container_width=True)

if search_clicked:
    if demo_mode:
        rows = normalize_items([
            {"itemName": "折りたたみ電気ケトル 便利旅行用", "itemPrice": 3980, "reviewAverage": 4.5, "reviewCount": 842, "affiliateRate": 4.0, "postageFlag": 1, "availability": 1, "affiliateUrl": "https://example.com/rakuten-demo-1", "itemCode": "demo:001", "mediumImageUrls": ["https://placehold.co/300x300?text=Demo+1"], "catchcopy": "旅行や一人暮らしに便利なコンパクト設計"},
            {"itemName": "高反発まくら ホテル仕様", "itemPrice": 6980, "reviewAverage": 4.4, "reviewCount": 1201, "affiliateRate": 6.0, "postageFlag": 1, "availability": 1, "affiliateUrl": "https://example.com/rakuten-demo-2", "itemCode": "demo:002", "mediumImageUrls": ["https://placehold.co/300x300?text=Demo+2"], "catchcopy": "おうちでホテル気分を演出"},
            {"itemName": "スマホスタンド 木製 折りたたみ", "itemPrice": 2480, "reviewAverage": 4.6, "reviewCount": 517, "affiliateRate": 3.5, "postageFlag": 1, "availability": 1, "affiliateUrl": "https://example.com/rakuten-demo-3", "itemCode": "demo:003", "mediumImageUrls": ["https://placehold.co/300x300?text=Demo+3"], "catchcopy": "デスク周りをすっきり整える"},
            {"itemName": "大容量モバイルバッテリー 10000mAh", "itemPrice": 4980, "reviewAverage": 4.3, "reviewCount": 1900, "affiliateRate": 5.5, "postageFlag": 1, "availability": 1, "affiliateUrl": "https://example.com/rakuten-demo-4", "itemCode": "demo:004", "mediumImageUrls": ["https://placehold.co/300x300?text=Demo+4"], "catchcopy": "外出時の電池切れ対策に"},
        ])
        rows.sort(key=lambda x: x["選定スコア"], reverse=True)
        st.session_state["products"] = rows
        st.success("デモ商品を読み込みました。")
    elif not (app_id and access_key and affiliate_id):
        st.error("楽天APIの Application ID / Access Key / Affiliate ID を入力してください。")
    else:
        try:
            raw = search_rakuten(keyword, app_id, access_key, affiliate_id, hits, min_price or None, max_price or None, min_rate or None, review_only, postage_free, sort)
            rows = normalize_items(raw)
            rows.sort(key=lambda x: x["選定スコア"], reverse=True)
            st.session_state["products"] = rows
            st.success(f"{len(rows)}件取得しました。選定スコア順に並べています。")
        except requests.HTTPError as e:
            st.error(f"楽天APIエラー: {e.response.status_code} {e.response.text[:500]}")
        except Exception as e:
            st.error(f"取得エラー: {e}")

products = st.session_state.get("products", [])

if products:
    st.subheader("商品選定")
    df = pd.DataFrame(products)
    st.dataframe(df[["選定スコア", "商品名", "価格", "評価", "レビュー数", "料率%", "送料無料", "アフィリエイトURL"]], use_container_width=True, hide_index=True)

    names = [p["商品名"] for p in products]
    selected_name = st.selectbox("投稿を作る商品", names)
    selected = next(p for p in products if p["商品名"] == selected_name)

    c1, c2, c3 = st.columns(3)
    with c1:
        platform = st.selectbox("媒体", ["Instagram", "X", "TikTok台本"])
    with c2:
        tone = st.selectbox("トーン", ["標準", "短く", "親しみやすく", "高級感", "比較・レビュー型"])
    with c3:
        extra = st.text_input("追加指示", "")

    if st.button("🤖 AIで投稿案を生成", type="primary"):
        with st.spinner("投稿案を生成しています…"):
            try:
                caption = ai_generate(selected, platform, tone, extra)
                st.session_state["generated_caption"] = caption
            except Exception as e:
                st.error(f"AI生成エラー: {e}")

    caption = st.text_area("生成結果（編集可）", st.session_state.get("generated_caption", ""), height=260)
    if caption:
        if st.button("💾 下書きとして保存"):
            save_post(selected, platform, caption, "draft")
            st.success("下書きを保存しました。")

    st.info("SNSへの直接投稿は、X/Instagram/TikTokそれぞれのアプリ登録・OAuth・公開権限を設定してから接続する設計です。")

st.subheader("投稿管理")
posts = extract_recent_posts()
if posts.empty:
    st.write("まだ投稿データがありません。")
else:
    st.dataframe(posts, use_container_width=True, hide_index=True)

st.subheader("このMVPの次の拡張")
st.markdown(
    """
- 毎朝、自動で複数キーワードの商品候補を収集
- AIスコアの条件を曜日・季節・ジャンル別に変更
- 画像テンプレート生成／ショート動画台本生成
- SNS OAuth接続後の予約投稿
- クリック・成果を保存して、AIが翌日の商品候補へ反映
"""
)
