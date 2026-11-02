import streamlit as st
import io
import json
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# 1. ページ基本設定
st.set_page_config(page_title="受発注・帳票発行管理システム", layout="wide")
st.title("📊 @ポケット連動 受注・工程・納品・請求管理システム")

# 2. Secrets設定
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @ポケット対象アプリID

# 3. APIデータ取得関数（安全なフォールバック付き）
def fetch_pocket_records():
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        st.write(f"📡 APIステータスコード: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            st.write("▼ 受信データ内容:", result)
            
            records = []
            if isinstance(result, list):
                records = result
            elif isinstance(result, dict):
                records = result.get("Data", result.get("Records", []))
            
            if records:
                return records
        else:
            st.warning(f"⚠️ APIエラー: {response.text}")
    except Exception as e:
        st.info(f"ℹ️ 通信情報: {e}")
    
    # 接続できない場合やデータがない場合のモック
    today_str = str(datetime.now().date())
    return [{
        "Title": "ORD-2026-001 (テスト)",
        "field-1": today_str,
        "field-8": "〇〇出版",
        "field-13": "はじめてのPythonプログラミング",
        "field-4": "1000",
        "field-5": "1500",
        "Results1": [{"field-90_1": today_str, "field-90_3": "", "field-90_4": "", "field-90_5": "", "field-90_6": "", "field-90_7": False, "field-90_9": "特記事項なし"}],
        "Results2": [{"field-88_2": today_str, "field-88_4": 1000}],
        "Results3": [{"field-89_1": today_str, "field-89_3": 1000}]
    }]

# 4. タブ構成の定義
tab1, tab2, tab3 = st.tabs([
    "📋 タブ1: 受注日検索 ＆ 工程・一覧入力", 
    "📦 タブ2: 今週の納品書発行", 
    "📄 タブ3: 請求書発行（口座UI付き）"
])

# ==========================================
# タブ1
# ==========================================
with tab1:
    st.header("📋 工程・進捗・日付の入力管理（受注日検索）")
    
    today = datetime.now().date()
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t1_start = st.date_input("受注日（開始）", value=datetime(today.year, today.month, 1).date(), key="t1_s")
    with c2:
        t1_end = st.date_input("受注日（終了）", value=today, key="t1_e")
    with c3:
        st.write("")
        st.write("")
        search_clicked = st.button("🔄 検索実行", type="primary", key="btn_s1")

    if search_clicked or "api_records" not in st.session_state:
        st.session_state["api_records"] = fetch_pocket_records()

    api_records = st.session_state.get("api_records", [])
    sample_rec = api_records[0] if api_records else {}

    st.divider()
    st.subheader("📝 ヘッダー情報")
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        field_2 = st.text_input("受注番号 (field-2)", value=str(sample_rec.get("Title", "ORD-2026-001")))
        field_1 = st.text_input("受注日 (field-1)", value=str(sample_rec.get("field-1", str(today))))
    with col_h2:
        field_8 = st.text_input("出版社名 (field-8)", value=str(sample_rec.get("field-8", sample_rec.get("ClassA", "〇〇出版"))))
        field_13 = st.text_input("書名 (field-13)", value=str(sample_rec.get("field-13", sample_rec.get("ClassB", "サンプル書籍"))))
    with col_h3:
        field_4 = st.text_input("製本数 (field-4)", value=str(sample_rec.get("field-4", sample_rec.get("NumA", "1000"))))
        field_5 = st.text_input("単価 (field-5)", value=str(sample_rec.get("field-5", sample_rec.get("NumB", "1500"))))

    st.divider()
    st.subheader("📝 明細データの編集")
    
    default_eng = sample_rec.get("Results1", [])
    edited_eng = st.data_editor(pd.DataFrame(default_eng) if default_eng else pd.DataFrame([{"field-90_1": "", "field-90_3": "", "field-90_4": "", "field-90_5": "", "field-90_6": "", "field-90_7": False, "field-90_9": ""}]), num_rows="dynamic", key="editor_eng", use_container_width=True)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        default_deliv = sample_rec.get("Results2", [])
        edited_deliv = st.data_editor(pd.DataFrame(default_deliv) if default_deliv else pd.DataFrame([{"field-88_2": "", "field-88_4": 0}]), num_rows="dynamic", key="editor_deliv", use_container_width=True)
    with col_d2:
        default_sales = sample_rec.get("Results3", [])
        edited_sales = st.data_editor(pd.DataFrame(default_sales) if default_sales else pd.DataFrame([{"field-89_1": "", "field-89_3": 0}]), num_rows="dynamic", key="editor_sales", use_container_width=True)

    if st.button("💾 編集内容を @pocket に上書き保存する", type="primary", key="btn_save"):
        st.success("✅ 上書き保存をシミュレートしました！")

# ==========================================
# タブ2
# ==========================================
with tab2:
    st.header("📦 今週の納品書発行")
    st.dataframe(edited_deliv, use_container_width=True)
    if st.button("🚀 納品書PDF生成", type="primary", key="btn_pdf_deliv"):
        st.success("納品書PDFの準備ができました！")

# ==========================================
# タブ3
# ==========================================
with tab3:
    st.header("📄 請求書発行（口座UI付き）")
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        bank_name = st.text_input("銀行名", value="千葉銀行", key="b_name")
        bank_branch = st.text_input("支店名", value="市川支店", key="b_branch")
    with bc2:
        bank_type = st.selectbox("口座種別", options=["普通", "当座"], key="b_type")
        bank_account = st.text_input("口座番号", value="1234567", key="b_acc")
    with bc3:
        bank_holder = st.text_input("口座名義", value="カ）アークフィールド", key="b_holder")

    st.dataframe(edited_sales, use_container_width=True)
    if st.button("🚀 請求書PDF生成", type="primary", key="btn_pdf_invoice"):
        st.success("請求書PDFの準備ができました！")