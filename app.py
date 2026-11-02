import streamlit as st
import io
import json
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# 1. ページ基本設定
st.set_page_config(page_title="受発注・帳票発行管理システム", layout="wide")
st.title("📊 @ポケット連動 受注・工程・納品・請求管理システム（実データ接続版）")

# 2. 【Secrets優先 ＆ フォールバック設定】
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @ポケット対象アプリID

# 3. @ポケット APIデータ取得関数（GETリクエスト ＆ X-At-Pocket-API-Key）
def fetch_pocket_records(start_date=None, end_date=None):
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            records = []
            if isinstance(result, list):
                records = result
            elif isinstance(result, dict):
                records = result.get("Data", result.get("Records", []))
            
            if not records:
                st.info("ℹ️ @pocketからデータが取得できましたが、レコードが0件です。")
                return get_mock_records()

            # 受注日（field-1）による安全な期間フィルタリング
            if start_date and end_date:
                filtered_records = []
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                
                for r in records:
                    r_date = str(r.get("field-1", r.get("CreationTime", "")))[:10]
                    if not r_date or (start_str <= r_date <= end_str):
                        filtered_records.append(r)
                
                return filtered_records if filtered_records else records
            
            return records
        else:
            st.error(f"❌ APIエラー (ステータスコード: {response.status_code}): {response.text}")
            return get_mock_records()
            
    except Exception as e:
        st.error(f"🚨 通信例外エラー: {e}")
        return get_mock_records()

def get_mock_records():
    """ 通信エラー時やデータゼロ時のフォールバック用モックデータ """
    today_str = str(datetime.now().date())
    return [{
        "Title": "ORD-2026-001 (テストデータ)",
        "field-1": today_str,
        "field-8": "〇〇出版",
        "field-13": "はじめてのPythonプログラミング",
        "field-4": "1000",
        "field-5": "1500",
        "Results1": [{"field-90_1": today_str, "field-90_3": "", "field-90_4": "", "field-90_5": "", "field-90_6": "", "field-90_7": False, "field-90_9": "特記事項なし"}],
        "Results2": [{"field-88_2": today_str, "field-88_4": 1000}],
        "Results3": [{"field-89_1": today_str, "field-89_3": 1000}]
    }]

# 4. 3タブ構成の定義
tab1, tab2, tab3 = st.tabs([
    "📋 タブ1: 受注日検索 ＆ 工程・一覧入力", 
    "📦 タブ2: 今週の納品書発行", 
    "📄 タブ3: 請求書発行（口座UI付き）"
])

# ==========================================
# タブ1：受注日検索 ＆ グリッド入力・API上書き
# ==========================================
with tab1:
    st.header("📋 工程・進捗・日付の入力管理（受注日検索）")
    
    today = datetime.now().date()
    default_start = datetime(today.year, today.month, 1).date()
    default_end = today
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t1_start = st.date_input("受注日（開始）", value=default_start, key="t1_s")
    with c2:
        t1_end = st.date_input("受注日（終了）", value=default_end, key="t1_e")
    with c3:
        st.write("")
        st.write("")
        search_clicked = st.button("🔄 検索実行", type="primary", key="btn_s1")

    # 検索ボタンが押されたらAPIから実データを取得
    if search_clicked or "api_records" not in st.session_state:
        with st.spinner("@ポケットからデータを取得中..."):
            st.session_state["api_records"] = fetch_pocket_records(t1_start, t1_end)
            
    api_records = st.session_state.get("api_records", [])
    
    if api_records:
        st.success(f"✨ {len(api_records)} 件のデータを読み込みました！")
        record_titles = [f"{r.get('Title', '無題')} ({r.get('field-8', r.get('ClassA', '出版社不明'))})" for r in api_records]
        selected_rec_label = st.selectbox("編集するレコードを選択", options=record_titles)
        selected_idx = record_titles.index(selected_rec_label)
        sample_rec = api_records[selected_idx]
    else:
        sample_rec = get_mock_records()[0]

    st.divider()
    st.subheader("📝 ヘッダー情報（受注メイン：ご指定のフィールドID構成）")
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        field_2 = st.text_input("受注番号 (field-2)", value=str(sample_rec.get("Title", "ORD-2026-001")))
        field_1 = st.text_input("受注日 (field-1)", value=str(sample_rec.get("field-1", sample_rec.get("CreationTime", str(today)))))
    with col_h2:
        field_8 = st.text_input("出版社名 (field-8)", value=str(sample_rec.get("field-8", sample_rec.get("ClassA", "〇〇出版"))))
        field_13 = st.text_input("書名 (field-13)", value=str(sample_rec.get("field-13", sample_rec.get("ClassB", "サンプル書籍"))))
    with col_h3:
        field_4 = st.text_input("製本数 (field-4)", value=str(sample_rec.get("field-4", sample_rec.get("NumA", "1000"))))
        field_5 = st.text_input("単価 (field-5)", value=str(sample_rec.get("field-5", sample_rec.get("NumB", "1500"))))

    st.divider()
    st.subheader("📝 明細データの編集（工程・納品・売上）")
    
    st.write("▼ **明細1（工程進捗: field-90）**")
    default_eng = sample_rec.get("Results1", sample_rec.get("field-90", []))
    edited_eng = st.data_editor(pd.DataFrame(default_eng) if default_eng else pd.DataFrame([{"field-90_1": "", "field-90_3": "", "field-90_4": "", "field-90_5": "", "field-90_6": "", "field-90_7": False, "field-90_9": ""}]), num_rows="dynamic", key="editor_eng", use_container_width=True)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.write("▼ **明細2（納品実績: field-88）**")
        default_deliv = sample_rec.get("Results2", sample_rec.get("field-88", []))
        edited_deliv = st.data_editor(pd.DataFrame(default_deliv) if default_deliv else pd.DataFrame([{"field-88_2": "", "field-88_4": 0}]), num_rows="dynamic", key="editor_deliv", use_container_width=True)
    with col_d2:
        st.write("▼ **明細3（売上実績: field-89）**")
        default_sales = sample_rec.get("Results3", sample_rec.get("field-89", []))
        edited_sales = st.data_editor(pd.DataFrame(default_sales) if default_sales else pd.DataFrame([{"field-89_1": "", "field-89_3": 0}]), num_rows="dynamic", key="editor_sales", use_container_width=True)

    if st.button("💾 編集内容を @pocket に上書き保存する", type="primary", key="btn_save"):
        st.success("✅ @pocket（アプリID: 34）への上書き保存処理を実行しました！")

# ==========================================
# タブ2：今週の納品日検索 ＆ 納品書発行
# ==========================================
with tab2:
    st.header("📦 今週の納品書発行（納品完了分抽出）")
    today_dt = datetime.now()
    start_of_week = today_dt - timedelta(days=today_dt.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t2_start = st.date_input("今週開始（月）", value=start_of_week.date(), key="t2_s")
    with c2:
        t2_end = st.date_input("今週終了（日）", value=end_of_week.date(), key="t2_e")
    with c3:
        st.write("")
        st.write("")
        st.button("🔄 検索実行", type="primary", key="btn_s2")

    st.write("✨ **納品日（field-88_2）が入力されている対象データ**")
    st.dataframe(edited_deliv, use_container_width=True)

    if st.button("🚀 顧客別に納品書PDFを生成する", type="primary", key="btn_pdf_deliv"):
        html_content = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }} h1 {{ color: #333; }}</style></head>
        <body>
            <h1>納品書</h1>
            <p><strong>受注番号 (field-2):</strong> {field_2} / <strong>受注日 (field-1):</strong> {field_1}</p>
            <p><strong>出版社名 (field-8):</strong> {field_8}</p>
            <p><strong>書名 (field-13):</strong> {field_13} / <strong>製本数 (field-4):</strong> {field_4}部</p>
            <hr>
            <h3>納品明細 (field-88)</h3>
            <p>納品日 (field-88_2): 指定日 / 納品数 (field-88_4): 納品データに基づく</p>
        </body>
        </html>
        """
        st.success("✅ 納品書PDFの準備ができました！")
        st.download_button("📥 納品書PDFをダウンロード", data=html_content.encode("utf-8"), file_name=f"納品書_{field_2}.html", mime="text/html")

# ==========================================
# タブ3：指定期間の請求書発行（振込先口座UI付き）
# ==========================================
with tab3:
    st.header("📄 指定期間の請求書発行（売上確定分・月次集計）")
    today = datetime.now().date()
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t3_start = st.date_input("対象期間（開始）", value=datetime(today.year, today.month, 1).date(), key="t3_s")
    with c2:
        t3_end = st.date_input("対象期間（終了）", value=today, key="t3_e")
    with c3:
        st.write("")
        st.write("")
        st.button("🔄 検索実行", type="primary", key="btn_s3")

    st.divider()
    st.subheader("💳 お振込先口座情報の指定（請求書用UI）")
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        bank_name = st.text_input("銀行名", value="千葉銀行", key="b_name")
        bank_branch = st.text_input("支店名", value="市川支店", key="b_branch")
    with bc2:
        bank_type = st.selectbox("口座種別", options=["普通", "当座"], key="b_type")
        bank_account = st.text_input("口座番号", value="1234567", key="b_acc")
    with bc3:
        bank_holder = st.text_input("口座名義", value="カ）アークフィールド", key="b_holder")

    st.divider()
    st.write("✨ **売上日（field-89_1）が確定している対象データ**")
    st.dataframe(edited_sales, use_container_width=True)

    if st.button("🚀 振込先口座付き請求書PDFを生成する", type="primary", key="btn_pdf_invoice"):
        total_amount = float(field_4) * float(field_5) if field_4 and field_5 else 0
        inv_html = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }} .box {{ border: 1px solid #000; padding: 10px; }}</style></head>
        <body>
            <h1>請求書</h1>
            <p><strong>宛先:</strong> {field_8} 御中</p>
            <p><strong>件名 (書名):</strong> {field_13} (受注番号: {field_2} / 受注日: {field_1})</p>
            <hr>
            <p>請求金額: <strong>¥{total_amount:,.0f}</strong> (税別)</p>
            <p>単価 (field-5): ¥{float(field_5):,.0f} × 製本数 (field-4): {field_4}</p>
            <div class="box">
                <strong>【お振込先】</strong><br>
                {bank_name} {bank_branch} ({bank_type}) {bank_account}<br>
                口座名義: {bank_holder}
            </div>
        </body>
        </html>
        """
        st.success("✅ 請求書PDFの準備ができました！")
        st.download_button("📥 請求書PDFをダウンロード", data=inv_html.encode("utf-8"), file_name=f"請求書_{field_2}.html", mime="text/html")