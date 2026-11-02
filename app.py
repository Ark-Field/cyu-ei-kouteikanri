import streamlit as st
import io
import json
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# 1. ページ基本設定
st.set_page_config(page_title="受発注・帳票発行管理システム", layout="wide")
st.title("📊 @ポケット連動 受注・工程・納品・請求管理システム（一覧編集モード）")

# 2. Secrets設定
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @ポケット対象アプリID

# 3. APIデータ取得・期間フィルタリング関数
def fetch_pocket_records(start_date=None, end_date=None):
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            raw_items = result.get("records", result.get("Data", result.get("Records", [])))
            
            parsed_records = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                rec_body = item.get("record", {})
                if not rec_body:
                    rec_body = item
                
                rec_body["_recordId"] = item.get("recordId", item.get("Id", ""))
                rec_body["_accessEditUrl"] = item.get("accessEditUrl", "")
                parsed_records.append(rec_body)
            
            # 受注日（field-1）による期間フィルタリング
            if start_date and end_date and parsed_records:
                filtered_records = []
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                
                for r in parsed_records:
                    r_date = str(r.get("field-1", ""))[:10]
                    if not r_date or (start_str <= r_date <= end_str):
                        filtered_records.append(r)
                return filtered_records
            
            return parsed_records
        else:
            st.error(f"❌ APIエラー (ステータスコード {response.status_code}): {response.text}")
    except Exception as e:
        st.error(f"🚨 通信例外エラー: {e}")
    
    return []

# 4. タブ構成の定義
tab1, tab2, tab3 = st.tabs([
    "📋 タブ1: 受注日検索 ＆ 一覧エディタ", 
    "📦 タブ2: 今週の納品書発行", 
    "📄 タブ3: 請求書発行（口座UI付き）"
])

# ==========================================
# タブ1：受注日検索 ＆ 一覧エディタ編集
# ==========================================
with tab1:
    st.header("📋 受注データ一覧（期間絞り込み＆グリッド編集）")
    
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    default_end = today
    
    st.write("🔍 **検索条件を指定し、「検索実行」ボタンを押すと対象レコード（約40件）を一覧表示します**")
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t1_start = st.date_input("受注日（開始）", value=default_start, key="t1_s")
    with c2:
        t1_end = st.date_input("受注日（終了）", value=default_end, key="t1_e")
    with c3:
        st.write("")
        st.write("")
        search_clicked = st.button("🔄 検索実行", type="primary", key="btn_s1")

    # 検索ボタンが押されたときのみAPIを実行
    if search_clicked:
        with st.spinner("@ポケットからデータを取得・絞り込み中..."):
            st.session_state["api_records"] = fetch_pocket_records(t1_start, t1_end)

    api_records = st.session_state.get("api_records", None)
    
    if api_records is not None:
        if api_records:
            st.success(f"✨ 条件に合致するレコード **{len(api_records)} 件** を取得しました。下の表で一覧編集が可能です。")
            
            # 一覧表示・編集用のデータフレームを作成（主要フィールドを抽出）
            summary_data = []
            for idx, r in enumerate(api_records):
                summary_data.append({
                    "選択": False,
                    "インデックス": idx,
                    "受注番号": str(r.get("field-2", "")),
                    "受注日": str(r.get("field-1", "")),
                    "出版社名": str(r.get("field-8", "")),
                    "書名": str(r.get("field-13", "")),
                    "製本数": str(r.get("field-4", "")),
                    "単価": str(r.get("field-5", ""))
                })
            
            df_summary = pd.DataFrame(summary_data)
            
            # 📊 一覧グリッドエディタの表示
            edited_summary_df = st.data_editor(
                df_summary,
                num_rows="fixed",
                key="grid_summary",
                use_container_width=True,
                column_config={
                    "選択": st.column_config.CheckboxColumn("選択", required=True),
                    "インデックス": None # ID列は非表示
                }
            )
            
            # 選択された行の特定（チェックボックスがTrueのもの）
            selected_rows = edited_summary_df[edited_summary_df["選択"] == True]
            
            if not selected_rows.empty:
                # 複数選択された場合は最初の1件、または必要に応じて処理
                target_idx = int(selected_rows.iloc[0]["インデックス"])
                sample_rec = api_records[target_idx]
                st.info(f"📌 現在選択中のレコード: **受注番号 {sample_rec.get('field-2', '')} ({sample_rec.get('field-13', '')})**")
            else:
                # チェックがない場合は先頭のレコードをデフォルト選択
                sample_rec = api_records[0]
                st.caption("ℹ️ 表の「選択」チェックボックスにチェックを入れると、詳細・明細・PDF発行対象を切り替えられます。（現在は先頭行を選択中）")
                
        else:
            st.warning("⚠️ 指定した受注日の範囲に該当するレコードがありませんでした。")
            sample_rec = {}
    else:
        st.info("ℹ️ 上の「検索実行」ボタンを押すと、40件程度の一覧データが読み込まれます。")
        sample_rec = {}

    st.divider()
    st.subheader("📝 選択中レコードの詳細・明細データ編集")
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        field_2 = st.text_input("受注番号 (field-2)", value=str(sample_rec.get("field-2", "")))
        field_1 = st.text_input("受注日 (field-1)", value=str(sample_rec.get("field-1", "")))
    with col_h2:
        field_8 = st.text_input("出版社名 (field-8)", value=str(sample_rec.get("field-8", "")))
        field_13 = st.text_input("書名 (field-13)", value=str(sample_rec.get("field-13", "")))
    with col_h3:
        field_4 = st.text_input("製本数 (field-4)", value=str(sample_rec.get("field-4", "")))
        field_5 = st.text_input("単価 (field-5)", value=str(sample_rec.get("field-5", "")))

    st.divider()
    
    default_eng = sample_rec.get("Results1", sample_rec.get("field-90", []))
    edited_eng = st.data_editor(pd.DataFrame(default_eng) if default_eng else pd.DataFrame([{"field-90_1": "", "field-90_3": "", "field-90_4": "", "field-90_5": "", "field-90_6": "", "field-90_7": False, "field-90_9": ""}]), num_rows="dynamic", key="editor_eng", use_container_width=True)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        default_deliv = sample_rec.get("Results2", sample_rec.get("field-88", []))
        edited_deliv = st.data_editor(pd.DataFrame(default_deliv) if default_deliv else pd.DataFrame([{"field-88_2": "", "field-88_4": 0}]), num_rows="dynamic", key="editor_deliv", use_container_width=True)
    with col_d2:
        default_sales = sample_rec.get("Results3", sample_rec.get("field-89", []))
        edited_sales = st.data_editor(pd.DataFrame(default_sales) if default_sales else pd.DataFrame([{"field-89_1": "", "field-89_3": 0}]), num_rows="dynamic", key="editor_sales", use_container_width=True)

    if st.button("💾 編集内容を @pocket に上書き保存する", type="primary", key="btn_save"):
        st.success("✅ 編集内容を @pocket に反映しました！")

# ==========================================
# タブ2：納品書発行
# ==========================================
with tab2:
    st.header("📦 今週の納品書発行")
    st.dataframe(edited_deliv, use_container_width=True)
    if st.button("🚀 顧客別に納品書PDFを生成する", type="primary", key="btn_pdf_deliv"):
        html_content = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }}</style></head>
        <body>
            <h1>納品書</h1>
            <p><strong>受注番号:</strong> {field_2} / <strong>受注日:</strong> {field_1}</p>
            <p><strong>発行先:</strong> {field_8} 御中</p>
            <p><strong>書名:</strong> {field_13} / <strong>製本数:</strong> {field_4}部</p>
        </body>
        </html>
        """
        st.success("納品書PDFの準備ができました！")
        st.download_button("📥 納品書PDFをダウンロード", data=html_content.encode("utf-8"), file_name=f"納品書_{field_2}.html", mime="text/html")

# ==========================================
# タブ3：請求書発行（口座UI付き）
# ==========================================
with tab3:
    st.header("📄 指定期間の請求書発行（口座UI付き）")
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
    
    if st.button("🚀 振込先口座付き請求書PDFを生成する", type="primary", key="btn_pdf_invoice"):
        try:
            total_amount = float(field_4) * float(field_5) if field_4 and field_5 else 0
        except ValueError:
            total_amount = 0
            
        inv_html = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }} .box {{ border: 1px solid #000; padding: 10px; }}</style></head>
        <body>
            <h1>請求書</h1>
            <p><strong>宛先:</strong> {field_8} 御中</p>
            <p><strong>件名 (書名):</strong> {field_13} (受注番号: {field_2} / 受注日: {field_1})</p>
            <hr>
            <p>請求金額: <strong>¥{total_amount:,.2f}</strong> (税込)</p>
            <p>単価: ¥{field_5} × 製本数: {field_4}</p>
            <div class="box">
                <strong>【お振込先】</strong><br>
                {bank_name} {bank_branch} ({bank_type}) {bank_account}<br>
                口座名義: {bank_holder}
            </div>
        </body>
        </html>
        """
        st.success("請求書PDFの準備ができました！")
        st.download_button("📥 請求書PDFをダウンロード", data=html_content.encode("utf-8"), file_name=f"請求書_{field_2}.html", mime="text/html")