import io
import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, date
import streamlit as st

# ==========================================
# 1. ページ基本設定
# ==========================================
st.set_page_config(page_title="受注・進捗・帳票管理システム", layout="wide")
st.title("📊 @pocket連動 受注進捗・日付更新管理システム")

# ==========================================
# 2. Secrets設定
# ==========================================
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @pocket対象アプリID

# ==========================================
# 3. APIデータ取得関数
# ==========================================
def fetch_pocket_records(start_date=None, end_date=None):
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    params = {}
    if start_date and end_date:
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        params["query"] = f'field-1 >= "{start_str}" and field-1 <= "{end_str}"'
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code != 200 and "query" in params:
            response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            raw_items = result.get("records", result.get("Data", result.get("Records", [])))
            
            parsed_records = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                rec_body = item.get("record", {})
                if not isinstance(rec_body, dict):
                    rec_body = {}
                
                merged_body = {**item, **rec_body}
                merged_body["_recordId"] = item.get("Id", item.get("recordId", item.get("ResultId", rec_body.get("Id", ""))))
                parsed_records.append(merged_body)
            
            if start_date and end_date and parsed_records:
                filtered_records = []
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                
                for r in parsed_records:
                    raw_date_str = str(r.get("field-1", ""))
                    if not raw_date_str or raw_date_str.lower() in ["nan", "none"]:
                        continue
                    r_date = raw_date_str.replace("/", "-")[:10]
                    if len(r_date) == 10 and (start_str <= r_date <= end_str):
                        filtered_records.append(r)
                return filtered_records
            
            return parsed_records
        else:
            st.error(f"❌ APIエラー (ステータスコード {response.status_code}): {response.text}")
    except Exception as e:
        st.error(f"🚨 通信例外エラー: {e}")
    
    return []

def parse_date_safe(val):
    if not val or str(val).lower() in ["nan", "none", ""]:
        return None
    try:
        return datetime.strptime(str(val)[:10].replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        return None

# ==========================================
# 4. タブ構成の定義
# ==========================================
tab1, tab2, tab3 = st.tabs([
    "📋 タブ1: 進捗・日付更新エディタ", 
    "📦 タブ2: 納品書発行", 
    "📄 タブ3: 請求書発行（口座UI付き）"
])

# ==========================================
# タブ1：進捗・日付更新エディタ
# ==========================================
with tab1:
    st.header("📋 受注進捗・日付更新管理エディタ")
    st.info("💡 既存の受注データに対して、**配本日・折本日・無線日・仕上日・納品日・売上日**などの進捗日付を安全に入力・更新する専用画面です。")
    
    default_start = datetime(2026, 10, 1).date()
    default_end = datetime(2026, 10, 31).date()
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        t1_start = st.date_input("受注日（開始）", value=default_start, key="t1_s")
    with c2:
        t1_end = st.date_input("受注日（終了）", value=default_end, key="t1_e")
    with c3:
        st.write("")
        st.write("")
        search_clicked = st.button("🔄 検索実行", type="primary", key="btn_s1")

    if search_clicked:
        with st.spinner("@ポケットからデータを取得中..."):
            st.session_state["api_records"] = fetch_pocket_records(t1_start, t1_end)

    api_records = st.session_state.get("api_records", None)
    
    if api_records is not None:
        if api_records:
            st.success(f"✨ 親レコード **{len(api_records)} 件** を取得しました。")
            
            flat_data = []
            for record_idx, r in enumerate(api_records):
                h_ord_no = str(r.get("field-2", ""))
                h_ord_date = parse_date_safe(r.get("field-1"))
                h_pub = str(r.get("field-8", ""))
                h_title = str(r.get("field-13", ""))
                h_qty = str(r.get("field-4", ""))
                h_price = str(r.get("field-5", ""))
                
                sub_90 = r.get("field-90", [])
                sub_88 = r.get("field-88", [])
                sub_89 = r.get("field-89", [])
                
                max_len = max(len(sub_90) if isinstance(sub_90, list) else 0,
                              len(sub_88) if isinstance(sub_88, list) else 0,
                              len(sub_89) if isinstance(sub_89, list) else 0, 1)
                
                for i in range(max_len):
                    item_90 = sub_90[i] if isinstance(sub_90, list) and len(sub_90) > i else {}
                    sub_id_90 = item_90.get("recordSubId", item_90.get("Id", ""))
                    rec_90 = item_90.get("record", item_90) if isinstance(item_90, dict) else {}
                    
                    item_88 = sub_88[i] if isinstance(sub_88, list) and len(sub_88) > i else {}
                    sub_id_88 = item_88.get("recordSubId", item_88.get("Id", ""))
                    rec_88 = item_88.get("record", item_88) if isinstance(item_88, dict) else {}
                    
                    item_89 = sub_89[i] if isinstance(sub_89, list) and len(sub_89) > i else {}
                    sub_id_89 = item_89.get("recordSubId", item_89.get("Id", ""))
                    rec_89 = item_89.get("record", item_89) if isinstance(item_89, dict) else {}
                    
                    flat_data.append({
                        "更新": False,
                        "_record_idx": record_idx,
                        "_id_90": sub_id_90,
                        "_id_88": sub_id_88,
                        "_id_89": sub_id_89,
                        "受注番号": h_ord_no,
                        "受注日": h_ord_date,
                        "出版社名": h_pub,
                        "書名": h_title,
                        "製本数": h_qty,
                        "単価": h_price,
                        "配本日": parse_date_safe(rec_90.get("field-90_1")),
                        "折本日": parse_date_safe(rec_90.get("field-90_3")),
                        "無線日": parse_date_safe(rec_90.get("field-90_4")),
                        "三方日": parse_date_safe(rec_90.get("field-90_5")),
                        "仕上日": parse_date_safe(rec_90.get("field-90_6")),
                        "チェック": bool(rec_90.get("field-90_7", False)),
                        "備考": str(rec_90.get("field-90_9", "")),
                        "納品日": parse_date_safe(rec_88.get("field-88_2")),
                        "納品数": str(rec_88.get("field-88_4", "")),
                        "売上日": parse_date_safe(rec_89.get("field-89_1")),
                        "請求数量": str(rec_89.get("field-89_3", ""))
                    })
            
            df_flat = pd.DataFrame(flat_data)
            
            edited_flat_df = st.data_editor(
                df_flat,
                num_rows="fixed",
                key="grid_flat_main",
                use_container_width=True,
                column_config={
                    "更新": st.column_config.CheckboxColumn("更新チェック", required=True, help="チェックを入れた行の受注データを@pocketに上書き保存します"),
                    "_record_idx": None,
                    "_id_90": None,
                    "_id_88": None,
                    "_id_89": None,
                    "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                    "受注日": st.column_config.DateColumn("受注日", format="YYYY-MM-DD", disabled=True),
                    "出版社名": st.column_config.TextColumn("出版社名", disabled=True),
                    "書名": st.column_config.TextColumn("書名", disabled=True),
                    "製本数": st.column_config.TextColumn("製本数", disabled=True),
                    "単価": st.column_config.TextColumn("単価", disabled=True),
                    "配本日": st.column_config.DateColumn("配本日", format="YYYY-MM-DD"),
                    "折本日": st.column_config.DateColumn("折本日", format="YYYY-MM-DD"),
                    "無線日": st.column_config.DateColumn("無線日", format="YYYY-MM-DD"),
                    "三方日": st.column_config.DateColumn("三方日", format="YYYY-MM-DD"),
                    "仕上日": st.column_config.DateColumn("仕上日", format="YYYY-MM-DD"),
                    "チェック": st.column_config.CheckboxColumn("チェック"),
                    "備考": st.column_config.TextColumn("備考"),
                    "納品日": st.column_config.DateColumn("納品日", format="YYYY-MM-DD"),
                    "納品数": st.column_config.TextColumn("納品数"),
                    "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD"),
                    "請求数量": st.column_config.TextColumn("請求数量"),
                }
            )
            
            selected_rows = edited_flat_df[edited_flat_df["更新"] == True]
            if selected_rows.empty:
                selected_rows = edited_flat_df.iloc[[0]]
            
            target_record_idx = int(selected_rows.iloc[0]["_record_idx"])
            sample_rec = api_records[target_record_idx]
            field_2 = str(selected_rows.iloc[0]["受注番号"])
            field_1 = str(selected_rows.iloc[0]["受注日"])
            field_8 = str(selected_rows.iloc[0]["出版社名"])
            field_13 = str(selected_rows.iloc[0]["書名"])
            field_4 = str(selected_rows.iloc[0]["製本数"])
            field_5 = str(selected_rows.iloc[0]["単価"])
            
            st.info(f"📌 現在選択中のレコード: **受注番号 {field_2} ({field_13})** （下のタブ2・3のPDF発行に連動しています）")
                
        else:
            st.warning("⚠️ 指定した受注日の範囲に該当するレコードがありませんでした。")
            sample_rec = {}
            field_2, field_1, field_8, field_13, field_4, field_5 = "", "", "", "", "", ""
    else:
        st.info("ℹ️ 上の検索条件を指定し「検索実行」ボタンを押すとデータが読み込まれます。")
        sample_rec = {}
        field_2, field_1, field_8, field_13, field_4, field_5 = "", "", "", "", "", ""

    st.divider()
    
    checked_rows_count = len(edited_flat_df[edited_flat_df["更新"] == True]) if 'edited_flat_df' in locals() else 0
    if st.button(f"💾 チェックを入れた受注データ（{checked_rows_count}件）を @pocket に一括上書き保存する", type="primary", key="btn_save_checked"):
        checked_rows = edited_flat_df[edited_flat_df["更新"] == True]
        if checked_rows.empty:
            st.warning("⚠️ 上書き保存する行の「更新チェック」ボックスにチェックを入れてください。")
        else:
            headers = {
                "X-At-Pocket-API-Key": POCKET_API_KEY, 
                "Accept": "application/json", 
                "Content-Type": "application/json"
            }
            success_count = 0
            fail_count = 0
            
            grouped_records = checked_rows.groupby("_record_idx")
            
            for r_idx, group_df in grouped_records:
                r_idx = int(r_idx)
                original_rec = api_records[r_idx]
                record_id = original_rec.get("_recordId")
                
                if not record_id:
                    st.error("❌ レコードIDが見つかりませんでした。")
                    fail_count += 1
                    continue
                
                update_url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records/{record_id}"
                
                first_row = group_df.iloc[0]
                record_payload = {
                    "field-2": str(first_row["受注番号"]),
                    "field-1": str(first_row["受注日"]) if pd.notna(first_row["受注日"]) else "",
                    "field-4": str(first_row["製本数"]),
                    "field-5": str(first_row["単価"]),
                }
                
                import copy
                
                # 1. field-90 の構築
                orig_sub_90 = original_rec.get("field-90", [])
                sub90_list = []
                row_90 = group_df.iloc[0]
                
                if isinstance(orig_sub_90, list) and len(orig_sub_90) > 0:
                    item_90 = copy.deepcopy(orig_sub_90[0])
                    rec_dict = item_90.get("record", {})
                    
                    rec_dict["field-90_1"] = str(row_90["配本日"]) if pd.notna(row_90["配本日"]) else ""
                    rec_dict["field-90_3"] = str(row_90["折本日"]) if pd.notna(row_90["折本日"]) else ""
                    rec_dict["field-90_4"] = str(row_90["無線日"]) if pd.notna(row_90["無線日"]) else ""
                    rec_dict["field-90_5"] = str(row_90["三方日"]) if pd.notna(row_90["三方日"]) else ""
                    rec_dict["field-90_6"] = str(row_90["仕上日"]) if pd.notna(row_90["仕上日"]) else ""
                    rec_dict["field-90_7"] = bool(row_90["チェック"])
                    rec_dict["field-90_9"] = str(row_90["備考"]) if pd.notna(row_90["備考"]) else ""
                    
                    item_90["record"] = rec_dict
                    sub90_list.append(item_90)
                else:
                    sub90_list.append({
                        "record": {
                            "field-90_1": str(row_90["配本日"]) if pd.notna(row_90["配本日"]) else "",
                            "field-90_3": str(row_90["折本日"]) if pd.notna(row_90["折本日"]) else "",
                            "field-90_4": str(row_90["無線日"]) if pd.notna(row["無線日"]) else "",
                            "field-90_5": str(row_90["三方日"]) if pd.notna(row["三方日"]) else "",
                            "field-90_6": str(row_90["仕上日"]) if pd.notna(row["仕上日"]) else "",
                            "field-90_7": bool(row_90["チェック"]),
                            "field-90_9": str(row_90["備考"]) if pd.notna(row["備考"]) else "",
                            "field-90_2": ""
                        }
                    })

                # 2. field-88 の構築
                orig_sub_88 = original_rec.get("field-88", [])
                sub88_list = []
                if isinstance(orig_sub_88, list) and len(orig_sub_88) > 0:
                    item_88 = copy.deepcopy(orig_sub_88[0])
                    rec_dict = item_88.get("record", {})
                    
                    rec_dict["field-88_2"] = str(row_90["納品日"]) if pd.notna(row_90["納品日"]) else ""
                    rec_dict["field-88_4"] = str(int(row_90["納品数"])) if str(row_90["納品数"]).isdigit() else "0"
                    
                    item_88["record"] = rec_dict
                    sub88_list.append(item_88)
                else:
                    sub88_list.append({
                        "record": {
                            "field-88_1": "1",
                            "field-88_2": str(row_90["納品日"]) if pd.notna(row_90["納品日"]) else "",
                            "field-88_3": "本書",
                            "field-88_4": str(int(row_90["納品数"])) if str(row_90["納品数"]).isdigit() else "0",
                            "field-88_5": "",
                            "field-88_6": []
                        }
                    })

                # 3. field-89 の構築
                orig_sub_89 = original_rec.get("field-89", [])
                sub89_list = []
                if isinstance(orig_sub_89, list) and len(orig_sub_89) > 0:
                    item_89 = copy.deepcopy(orig_sub_89[0])
                    rec_dict = item_89.get("record", {})
                    
                    rec_dict["field-89_1"] = str(row_90["売上日"]) if pd.notna(row_90["売上日"]) else ""
                    rec_dict["field-89_3"] = str(int(row_90["請求数量"])) if str(row_90["請求数量"]).isdigit() else "0"
                    
                    item_89["record"] = rec_dict
                    sub89_list.append(item_89)
                else:
                    sub89_list.append({
                        "record": {
                            "field-89_1": str(row_90["売上日"]) if pd.notna(row_90["売上日"]) else "",
                            "field-89_2": "",
                            "field-89_3": str(int(row_90["請求数量"])) if str(row_90["請求数量"]).isdigit() else "0",
                            "field-89_4": "",
                            "field-89_5": "0",
                            "field-89_6": "0",
                            "field-89_7": ""
                        }
                    })

                record_payload["field-90"] = sub90_list
                record_payload["field-88"] = sub88_list
                record_payload["field-89"] = sub89_list

                payload = {
                    "apiVersion": 1.1,
                    "record": record_payload
                }
                
                with st.expander(f"📤 【確認】レコードID {record_id} の送信ペイロード"):
                    st.json(payload)

                try:
                    res = requests.put(update_url, headers=headers, json=payload, timeout=15)
                    if res.status_code in [200, 204]:
                        success_count += 1
                    else:
                        st.error(f"❌ レコードID {record_id} の保存失敗 (ステータス {res.status_code}): {res.text}")
                        fail_count += 1
                except Exception as e:
                    st.error(f"🚨 例外発生: {e}")
                    fail_count += 1
            
            if success_count > 0:
                st.success(f"✅ **{success_count} 件** のレコードデータを @pocket に正常に一括上書き保存しました！")
            if fail_count > 0:
                st.error(f"❌ {fail_count} 件の保存に失敗しました。")

# ==========================================
# タブ2：納品書発行
# ==========================================
with tab2:
    st.header("📦 納品書発行")
    default_deliv = sample_rec.get("field-88", [{"納品日": "", "納品数": 0}]) if 'sample_rec' in locals() else [{"納品日": "", "納品数": 0}]
    edited_deliv = st.data_editor(pd.DataFrame(default_deliv) if default_deliv else pd.DataFrame([{"納品日": "", "納品数": 0}]), num_rows="dynamic", key="editor_deliv", use_container_width=True)
    
    if st.button("🚀 選択中レコードの納品書PDFを生成する", type="primary", key="btn_pdf_deliv"):
        html_content = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }}</style></head>
        <body>
            <h1>納品書</h1>
            <p><strong>受注番号:</strong> {field_2 if 'field_2' in locals() else ''} / <strong>受注日:</strong> {field_1 if 'field_1' in locals() else ''}</p>
            <p><strong>発行先:</strong> {field_8 if 'field_8' in locals() else ''} 御中</p>
            <p><strong>書名:</strong> {field_13 if 'field_13' in locals() else ''} / <strong>製本数:</strong> {field_4 if 'field_4' in locals() else ''}部</p>
        </body>
        </html>
        """
        st.success("納品書PDFの準備ができました！")
        st.download_button("📥 納品書PDFをダウンロード", data=html_content.encode("utf-8"), file_name=f"納品書_{field_2 if 'field_2' in locals() else 'd'}.html", mime="text/html")

# ==========================================
# タブ3：請求書発行（口座UI付き）
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

    default_sales = sample_rec.get("field-89", [{"売上日": "", "請求数量": 0}]) if 'sample_rec' in locals() else [{"売上日": "", "請求数量": 0}]
    edited_sales = st.data_editor(pd.DataFrame(default_sales) if default_sales else pd.DataFrame([{"売上日": "", "請求数量": 0}]), num_rows="dynamic", key="editor_sales", use_container_width=True)
    
    if st.button("🚀 振込先口座付き請求書PDFを生成する", type="primary", key="btn_pdf_invoice"):
        try:
            total_amount = float(field_4) * float(field_5) if 'field_4' in locals() and 'field_5' in locals() and field_4 and field_5 else 0
        except ValueError:
            total_amount = 0
            
        inv_html = f"""
        <html>
        <head><meta charset="utf-8"><style>body {{ font-family: sans-serif; }} .box {{ border: 1px solid #000; padding: 10px; }}</style></head>
        <body>
            <h1>請求書</h1>
            <p><strong>宛先:</strong> {field_8 if 'field_8' in locals() else ''} 御中</p>
            <p><strong>件名 (書名):</strong> {field_13 if 'field_13' in locals() else ''} (受注番号: {field_2 if 'field_2' in locals() else ''} / 受注日: {field_1 if 'field_1' in locals() else ''})</p>
            <hr>
            <p>請求金額: <strong>¥{total_amount:,.2f}</strong> (税込)</p>
            <p>単価: ¥{field_5 if 'field_5' in locals() else ''} × 製本数: {field_4 if 'field_4' in locals() else ''}</p>
            <div class="box">
                <strong>【お振込先】</strong><br>
                {bank_name} {bank_branch} ({bank_type}) {bank_account}<br>
                口座名義: {bank_holder}
            </div>
        </body>
        </html>
        """
        st.success("請求書PDFの準備ができました！")
        st.download_button("📥 請求書PDFをダウンロード", data=inv_html.encode("utf-8"), file_name=f"請求書_{field_2 if 'field_2' in locals() else 'i'}.html", mime="text/html")