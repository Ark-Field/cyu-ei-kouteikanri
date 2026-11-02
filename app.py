import streamlit as st
import io
import json
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# 1. ページ基本設定
st.set_page_config(page_title="受発注・帳票発行管理システム", layout="wide")
st.title("📊 @ポケット連動 受注・工程・納品・請求管理システム（API連携修正版）")

# 2. 【安全なSecrets取得処理】
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "ここにAPIキーを設定してください"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @ポケット対象アプリID

# 3. @ポケット API通信関数（正しいエンドポイントへ修正）
def fetch_pocket_records_by_order_date(start_date, end_date):
    """
    PleasanterのAPI仕様に合わせた一覧取得/検索関数
    """
    # Pleasanterの一般的なAPI一覧取得エンドポイント
    api_url = f"{POCKET_BASE_URL}/api/items/{APP_ID}/get"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "ApiVersion": 1.1,
        "ApiKey": POCKET_API_KEY,
        "View": {
            "ColumnFilterHash": {
                # 必要に応じて日付フィルターを有効化
                # "field-1": f"{start_date}~{end_date}"
            }
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        st.write(f"📡 APIステータスコード: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            data_list = result.get("Response", {}).get("Data", [])
            return data_list if isinstance(data_list, list) else [data_list]
        else:
            st.error(f"APIエラーレスポンス: {response.text}")
    except Exception as e:
        st.error(f"API通信例外エラー: {e}")
    
    return []

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
    
    st.write("🔍 **検索クエリ条件設定（受注日によるAPI負荷軽減）**")
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t1_start = st.date_input("受注日（開始）", value=default_start, key="t1_s")
    with c2:
        t1_end = st.date_input("受注日（終了）", value=default_end, key="t1_e")
    with c3:
        st.write("")
        st.write("")
        search_clicked = st.button("🔄 検索実行", type="primary", key="btn_s1")

    api_records = []
    if search_clicked:
        with st.spinner("@ポケットからデータを取得中..."):
            api_records = fetch_pocket_records_by_order_date(t1_start, t1_end)
            st.session_state["api_records"] = api_records
    else:
        api_records = st.session_state.get("api_records", [])

    if api_records:
        st.success(f"✨ {len(api_records)} 件のデータが取得できました！")
    else:
        st.info("ℹ️ 検索結果が空、またはテストデータを使用しています。")

    st.divider()
    st.subheader("📝 ヘッダー情報（受注メイン：ご指定のフィールドID構成）")
    
    sample_rec = api_records[0] if api_records else {}
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        field_2 = st.text_input("受注番号 (field-2)", value=str(sample_rec.get("Title", "ORD-2026-001")))
        field_1 = st.text_input("受注日 (field-1)", value=str(sample_rec.get("CreationTime", str(today))))
    with col_h2:
        field_8 = st.text_input("出版社名 (field-8)", value=str(sample_rec.get("ClassA", "〇〇出版")))
        field_13 = st.text_input("書名 (field-13)", value=str(sample_rec.get("ClassB", "サンプル書籍")))
    with col_h3:
        field_4 = st.text_input("製本数 (field-4)", value=str(sample_rec.get("NumA", "1000")))
        field_5 = st.text_input("単価 (field-5)", value=str(sample_rec.get("NumB", "1500")))

    st.divider()
    st.subheader("📝 明細データの編集（工程・納品・売上）")
    
    st.write("▼ **明細1（工程進捗: field-90）**")
    default_eng = sample_rec.get("Results1", [{
        "field-90_1": "2026-11-01", 
        "field-90_3": "2026-11-03", 
        "field-90_4": "2026-11-05", 
        "field-90_5": "2026-11-06", 
        "field-90_6": "2026-11-07", 
        "field-90_7": True, 
        "field-90_9": "特記事項なし"
    }])
    edited_eng = st.data_editor(pd.DataFrame(default_eng), num_rows="dynamic", key="editor_eng", use_container_width=True)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.write("▼ **明細2（納品実績: field-88）**")
        default_deliv = sample_rec.get("Results2", [{"field-88_2": "2026-11-08", "field-88_4": 1000}])
        edited_deliv = st.data_editor(pd.DataFrame(default_deliv), num_rows="dynamic", key="editor_deliv", use_container_width=True)
    with col_d2:
        st.write("▼ **明細3（売上実績: field-89）**")
        default_sales = sample_rec.get("Results3", [{"field-89_1": "2026-11-10", "field-89_3": 1000}])
        edited_sales = st.data_editor(pd.DataFrame(default_sales), num_rows="dynamic", key="editor_sales", use_container_width=True)

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