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
st.set_page_config(page_title="受注一覧表", layout="wide")
st.title("📊 受注一覧表 ＆ 付物・納品管理システム")

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
def fetch_pocket_records(start_date=None, end_date=None, target_order_no=None, target_publisher=None):
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    params = {}
    
    if target_order_no:
        params["query"] = f'field-2 = "{target_order_no}"'
    else:
        query_parts = []
        if start_date and end_date:
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            query_parts.append(f'field-1 >= "{start_str}" and field-1 <= "{end_str}"')
        
        if target_publisher:
            query_parts.append(f'field-8 like "{target_publisher}"')
        
        if query_parts:
            params["query"] = " and ".join(query_parts)
    
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
            
            if target_order_no and parsed_records:
                matched = [r for r in parsed_records if str(r.get("field-2", "")) == str(target_order_no)]
                if matched:
                    return matched
            
            filtered_records = []
            start_str = start_date.strftime("%Y-%m-%d") if start_date else None
            end_str = end_date.strftime("%Y-%m-%d") if end_date else None
            
            for r in parsed_records:
                if start_str and end_str:
                    raw_date_str = str(r.get("field-1", ""))
                    if not raw_date_str or raw_date_str.lower() in ["nan", "none"]:
                        continue
                    r_date = raw_date_str.replace("/", "-")[:10]
                    if len(r_date) != 10 or not (start_str <= r_date <= end_str):
                        continue
                
                if target_publisher:
                    r_pub = str(r.get("field-8", ""))
                    if target_publisher.lower() not in r_pub.lower():
                        continue
                
                filtered_records.append(r)
                
            return filtered_records if (start_date or target_publisher) else parsed_records
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
# 4. URLパラメータのチェック
# ==========================================
query_params = st.query_params
url_order_no = query_params.get("ord", None)

if "api_records" not in st.session_state or url_order_no:
    if url_order_no:
        with st.spinner(f"DBから受注番号: {url_order_no} のデータを取得中..."):
            st.session_state["api_records"] = fetch_pocket_records(target_order_no=url_order_no)
    else:
        default_end = date.today()
        default_start = default_end - timedelta(days=21)
        st.session_state["api_records"] = fetch_pocket_records(start_date=default_start, end_date=default_end)

# ==========================================
# 5. タブ構成の定義
# ==========================================
tab1, tab_accessory, tab2, tab3 = st.tabs([
    "📋 タブ1: 受注一覧表", 
    "🏷️ 付物明細（表・カバー・帯・カード）",
    "📦 タブ2: 納品書発行", 
    "📄 タブ3: 請求書発行（口座指定可）"
])

# ==========================================
# タブ1：受注一覧表 ＆ 工程日・製本情報エディタ
# ==========================================
with tab1:
    st.header("📋 受注一覧表")
    
    if url_order_no:
        st.success(f"🔗 DBから受注番号 **{url_order_no}** のデータを起動しました！")
    
    with st.expander("🔍 検索条件の変更・絞り込みはこちら", expanded=bool(not url_order_no)):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            default_end = date.today()
            default_start = default_end - timedelta(days=21)
            t1_start = st.date_input("受注日（開始）", value=default_start, key="t1_s")
        with col_s2:
            t1_end = st.date_input("受注日（終了）", value=default_end, key="t1_e")
        
        publisher_input = st.text_input("📖 出版社名で絞り込み（空欄なら期間内すべて）", value="", key="pub_ord")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            search_clicked = st.button("🔄 期間 ＆ 出版社名で検索", type="primary", key="btn_s1")
        
        st.markdown("---")
        direct_order_input = st.text_input("🏷️ 受注番号で直接検索（1件指定）", value=url_order_no if url_order_no else "", key="direct_ord")
        direct_search_clicked = st.button("🔍 受注番号で検索実行", key="btn_direct_s")

    if search_clicked:
        st.query_params.clear()
        with st.spinner("@ポケットからデータを取得中..."):
            st.session_state["api_records"] = fetch_pocket_records(
                start_date=t1_start, 
                end_date=t1_end, 
                target_publisher=publisher_input if publisher_input else None
            )
        st.rerun()

    if direct_search_clicked and direct_order_input:
        st.query_params["ord"] = direct_order_input
        with st.spinner(f"受注番号 {direct_order_input} を検索中..."):
            st.session_state["api_records"] = fetch_pocket_records(target_order_no=direct_order_input)
        st.rerun()

    api_records = st.session_state.get("api_records", None)
    
    if api_records is not None:
        if api_records:
            st.success(f"✨ 対象レコード **{len(api_records)} 件** を取得しました。")
            
            flat_data = []
            for record_idx, r in enumerate(api_records):
                h_ord_no = str(r.get("field-2", ""))
                h_ord_date = parse_date_safe(r.get("field-1"))
                h_pub = str(r.get("field-8", ""))
                h_title = str(r.get("field-13", ""))
                h_qty = str(r.get("field-4", ""))
                h_price = str(r.get("field-5", ""))
                
                sub_90 = r.get("field-90", [])
                sub_89 = r.get("field-89", [])
                
                max_len = max(len(sub_90) if isinstance(sub_90, list) else 0,
                              len(sub_89) if isinstance(sub_89, list) else 0, 1)
                
                for i in range(max_len):
                    item_90 = sub_90[i] if isinstance(sub_90, list) and len(sub_90) > i else {}
                    sub_id_90 = item_90.get("recordSubId", item_90.get("Id", ""))
                    rec_90 = item_90.get("record", item_90) if isinstance(item_90, dict) else {}
                    
                    item_89 = sub_89[i] if isinstance(sub_89, list) and len(sub_89) > i else {}
                    sub_id_89 = item_89.get("recordSubId", item_89.get("Id", ""))
                    rec_89 = item_89.get("record", item_89) if isinstance(item_89, dict) else {}
                    
                    flat_data.append({
                        "更新": False,
                        "_record_idx": record_idx,
                        "_id_90": sub_id_90,
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
            
            st.info(f"📌 現在選択中のレコード: **受注番号 {field_2} ({field_13})** （納品書・請求書発行に連動しています）")
                
        else:
            st.warning("⚠️ 該当するレコードが見つかりませんでした。")
            sample_rec = {}
            field_2, field_1, field_8, field_13, field_4, field_5 = "", "", "", "", "", ""
    else:
        st.info("ℹ️ 検索条件を指定するか、DBから受注番号を指定してアクセスしてください。")
        sample_rec = {}
        field_2, field_1, field_8, field_13, field_4, field_5 = "", "", "", "", "", ""

# ==========================================
# タブ1.5：付物明細（表、カバー、帯、カード）
# ==========================================
with tab_accessory:
    st.header("🏷️ 付物明細（表・カバー・帯・カード）管理")
    st.info("💡 各種付物の『日付』は変更・更新が可能ですが、『印刷所』は参照専用（更新不可）となります。")

    if api_records and len(api_records) > 0:
        acc_flat_data = []
        for record_idx, r in enumerate(api_records):
            h_ord_no = str(r.get("field-2", ""))
            h_pub = str(r.get("field-8", ""))
            h_title = str(r.get("field-13", ""))
            
            sub_91 = r.get("field-91", [])
            max_len_91 = len(sub_91) if isinstance(sub_91, list) and len(sub_91) > 0 else 1
            
            for i in range(max_len_91):
                item_91 = sub_91[i] if isinstance(sub_91, list) and len(sub_91) > i else {}
                rec_91 = item_91.get("record", item_91) if isinstance(item_91, dict) else {}
                
                acc_flat_data.append({
                    "更新": False,
                    "_record_idx": record_idx,
                    "受注番号": h_ord_no,
                    "出版社名": h_pub,
                    "書名": h_title,
                    "表 日付": parse_date_safe(rec_91.get("field-91_1")),
                    "表 印刷所": str(rec_91.get("field-91_2", "")),
                    "カバー 日付": parse_date_safe(rec_91.get("field-91_5")),
                    "カバー 印刷所": str(rec_91.get("field-91_6", "")),
                    "カード 日付": parse_date_safe(rec_91.get("field-91_9")),
                    "カード 印刷所": str(rec_91.get("field-91_10", "")),
                    "帯 日付": parse_date_safe(rec_91.get("field-91_13")),
                    "帯 印刷所": str(rec_91.get("field-91_14", ""))
                })
        
        df_acc = pd.DataFrame(acc_flat_data)
        
        edited_acc_df = st.data_editor(
            df_acc,
            num_rows="fixed",
            key="grid_accessory_main",
            use_container_width=True,
            column_config={
                "更新": st.column_config.CheckboxColumn("更新チェック", required=True, help="チェックを入れた行の付物データを@pocketに上書き保存します"),
                "_record_idx": None,
                "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                "出版社名": st.column_config.TextColumn("出版社名", disabled=True),
                "書名": st.column_config.TextColumn("書名", disabled=True),
                "表 日付": st.column_config.DateColumn("表 日付", format="YYYY-MM-DD"),
                "表 印刷所": st.column_config.TextColumn("表 印刷所", disabled=True),
                "カバー 日付": st.column_config.DateColumn("カバー 日付", format="YYYY-MM-DD"),
                "カバー 印刷所": st.column_config.TextColumn("カバー 印刷所", disabled=True),
                "カード 日付": st.column_config.DateColumn("カード 日付", format="YYYY-MM-DD"),
                "カード 印刷所": st.column_config.TextColumn("カード 印刷所", disabled=True),
                "帯 日付": st.column_config.DateColumn("帯 日付", format="YYYY-MM-DD"),
                "帯 印刷所": st.column_config.TextColumn("帯 印刷所", disabled=True),
            }
        )
    else:
        st.warning("⚠️ 表示対象の受注データがありません。タブ1で検索を行ってください。")

# ==========================================
# 共通の一括上書き保存ボタン
# ==========================================
st.divider()

if st.button("💾 チェックを入れたデータを データベース に一括上書き保存する", type="primary", key="btn_save_checked_all"):
    checked_rows = pd.DataFrame()
    source_tab = None
    
    if 'edited_flat_df' in locals() and not edited_flat_df[edited_flat_df["更新"] == True].empty:
        checked_rows = edited_flat_df[edited_flat_df["更新"] == True]
        source_tab = "flat"
    elif 'edited_acc_df' in locals() and not edited_acc_df[edited_acc_df["更新"] == True].empty:
        checked_rows = edited_acc_df[edited_acc_df["更新"] == True]
        source_tab = "acc"
        
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
                "field-2": str(original_rec.get("field-2", "")),
                "field-1": str(original_rec.get("field-1", "")),
                "field-4": str(original_rec.get("field-4", "")),
                "field-5": str(original_rec.get("field-5", "")),
            }
            
            import copy
            
            # 1. field-90 の構築
            orig_sub_90 = original_rec.get("field-90", [])
            sub90_list = []
            if source_tab == "flat":
                row_90 = first_row
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
                            "field-90_1": str(first_row["配本日"]) if pd.notna(first_row["配本日"]) else "",
                            "field-90_3": str(first_row["折本日"]) if pd.notna(first_row["折本日"]) else "",
                            "field-90_4": str(first_row["無線日"]) if pd.notna(first_row["無線日"]) else "",
                            "field-90_5": str(first_row["三方日"]) if pd.notna(first_row["三方日"]) else "",
                            "field-90_6": str(first_row["仕上日"]) if pd.notna(first_row["仕上日"]) else "",
                            "field-90_7": bool(first_row["チェック"]),
                            "field-90_9": str(first_row["備考"]) if pd.notna(first_row["備考"]) else "",
                            "field-90_2": ""
                        }
                    })
                record_payload["field-90"] = sub90_list
            else:
                record_payload["field-90"] = orig_sub_90

            # 2. field-89 (売上/仕入) の維持
            record_payload["field-89"] = original_rec.get("field-89", [])

            # 3. field-91 (付物明細) の構築
            orig_sub_91 = original_rec.get("field-91", [])
            sub91_list = []
            if source_tab == "acc":
                row_91 = first_row
                if isinstance(orig_sub_91, list) and len(orig_sub_91) > 0:
                    item_91 = copy.deepcopy(orig_sub_91[0])
                    rec_dict_91 = item_91.get("record", {})
                    
                    rec_dict_91["field-91_1"] = str(row_91["表 日付"]) if pd.notna(row_91["表 日付"]) else ""
                    rec_dict_91["field-91_5"] = str(row_91["カバー 日付"]) if pd.notna(row_91["カバー 日付"]) else ""
                    rec_dict_91["field-91_9"] = str(row_91["カード 日付"]) if pd.notna(row_91["カード 日付"]) else ""
                    rec_dict_91["field-91_13"] = str(row_91["帯 日付"]) if pd.notna(row_91["帯 日付"]) else ""
                    
                    for k in ["field-91_2", "field-91_6", "field-91_10", "field-91_14"]:
                        rec_dict_91.pop(k, None)
                        
                    item_91["record"] = rec_dict_91
                    sub91_list.append(item_91)
                else:
                    sub91_list.append({
                        "record": {
                            "field-91_1": str(first_row["表 日付"]) if pd.notna(first_row["表 日付"]) else "",
                            "field-91_5": str(first_row["カバー 日付"]) if pd.notna(first_row["カバー 日付"]) else "",
                            "field-91_9": str(first_row["カード 日付"]) if pd.notna(first_row["カード 日付"]) else "",
                            "field-91_13": str(first_row["帯 日付"]) if pd.notna(first_row["帯 日付"]) else ""
                        }
                    })
                record_payload["field-91"] = sub91_list
            else:
                record_payload["field-91"] = orig_sub_91

            payload = {
                "apiVersion": 1.1,
                "record": record_payload
            }

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
            st.success(f"✅ **{success_count} 件** のデータをデータベースに正常に一括上書き保存しました！")
            if url_order_no:
                st.session_state["api_records"] = fetch_pocket_records(target_order_no=url_order_no)
            else:
                default_end = date.today()
                default_start = default_end - timedelta(days=21)
                st.session_state["api_records"] = fetch_pocket_records(start_date=default_start, end_date=default_end)
            st.rerun()
            
        if fail_count > 0:
            st.error(f"❌ {fail_count} 件の保存に失敗しました。")

# ==========================================
# タブ2：納品書発行（売上/仕入明細 field-89 ベース ＆ 納品チェック絞り込み）
# ==========================================
with tab2:
    st.header("📦 納品書発行（売上/仕入明細連動）")
    st.info("💡 納請区分が**「納品」にチェックされている行のみ**が、自動的に納品書プレビューおよび印刷対象に絞り込まれます。")
    
    raw_sales_list = sample_rec.get("field-89", []) if 'sample_rec' in locals() else []
    deliv_table_data = []
    
    if raw_sales_list:
        for item in raw_sales_list:
            rec = item.get("record", item) if isinstance(item, dict) else {}
            deliv_table_data.append({
                "納品日": parse_date_safe(rec.get("field-89_9")),
                "納請区分": bool(rec.get("field-89_10", False)),
                "請求数量": str(rec.get("field-89_3", "0")),
                "売上日": parse_date_safe(rec.get("field-89_1"))
            })
    else:
        deliv_table_data = [{"納品日": None, "納請区分": False, "請求数量": "0", "売上日": None}]
    
    df_deliv = pd.DataFrame(deliv_table_data)
    edited_deliv = st.data_editor(
        df_deliv,
        num_rows="dynamic",
        key="editor_deliv_sales_base",
        use_container_width=True,
        column_config={
            "納品日": st.column_config.DateColumn("納品日", format="YYYY-MM-DD", help="納品日（field-89_9）"),
            "納請区分": st.column_config.CheckboxColumn("納請区分", help="チェック：納品 / 未チェック：請求 (field-89_10)"),
            "請求数量": st.column_config.TextColumn("数量 (請求数量)", disabled=True),
            "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD", disabled=True)
        }
    )
    
    if st.button("🚀 納品書プレビュー / 印刷（PDF）を作成", type="primary", key="btn_pdf_deliv_sales"):
        # 💡 納請区分が「納品（True）」にチェックされている行のみに絞り込む
        delivery_rows = [row for _, row in edited_deliv.iterrows() if row["納請区分"] == True]
        
        if not delivery_rows:
            st.warning("⚠️ 納請区分が「納品」にチェックされている行がありません。納品書を作成するには、対象行の「納請区分」にチェックを入れてください。")
        else:
            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; padding: 30px; color: #333; }}
                    h1 {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                    .meta {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                    th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    .right {{ text-align: right; }}
                    @media print {{
                        body {{ padding: 0; }}
                        .no-print {{ display: none; }}
                    }}
                </style>
            </head>
            <body>
                <h1>納 品 書</h1>
                <div class="meta">
                    <div>
                        <p><strong>宛先 (顧客名):</strong> {field_8 if 'field_8' in locals() else ''} 御中</p>
                        <p><strong>受注番号:</strong> {field_2 if 'field_2' in locals() else ''} / <strong>受注日:</strong> {field_1 if 'field_1' in locals() else ''}</p>
                        <p><strong>書名 (件名):</strong> {field_13 if 'field_13' in locals() else ''}</p>
                    </div>
                    <div>
                        <p><strong>発行日:</strong> {datetime.now().strftime('%Y-%m-%d')}</p>
                    </div>
                </div>
                <p>下記のとおり納品いたしました。</p>
                <table>
                    <tr>
                        <th>納品日</th>
                        <th>品名 (書名)</th>
                        <th class="right">納品数</th>
                    </tr>
            """
            for row in delivery_rows:
                d_date = str(row["納品日"]) if pd.notna(row["納品日"]) else ""
                d_name = f"{field_13}" if 'field_13' in locals() else "本書"
                d_qty = row["請求数量"]
                
                html_content += f"""
                    <tr>
                        <td>{d_date}</td>
                        <td>{d_name}</td>
                        <td class="right">{d_qty} 部</td>
                    </tr>
                """
            html_content += f"""
                </table>
                <br><br>
                <div class="no-print" style="text-align: center; margin-top: 30px;">
                    <button onclick="window.print();" style="padding: 10px 20px; font-size: 16px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ この納品書を印刷 / PDF保存する</button>
                </div>
            </body>
            </html>
            """
            st.success(f"納品書が生成されました！（対象件数: {len(delivery_rows)}件）")
            st.components.v1.html(html_content, height=500, scrolling=True)
            st.download_button("📥 納品書HTMLファイルをダウンロード", data=html_content.encode("utf-8"), file_name=f"納品書_{field_2 if 'field_2' in locals() else 'd'}.html", mime="text/html")

# ==========================================
# タブ3：請求書発行（口座UI付き）
# ==========================================
with tab3:
    st.header("📄 請求書発行（口座UI付き）")
    st.info("💡 振込先口座情報を入力し、請求明細を確認してプレビュー・印刷（PDF化）を行えます。")
    
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        bank_name = st.text_input("銀行名", value="三井住友銀行", key="b_name")
        bank_branch = st.text_input("支店名", value="岩槻支店", key="b_branch")
    with bc2:
        bank_type = st.selectbox("口座種別", options=["普通", "当座"], key="b_type")
        bank_account = st.text_input("口座番号", value="1234567", key="b_acc")
    with bc3:
        bank_holder = st.text_input("口座名義", value="カ）チュウエイセイホンジョ", key="b_holder")

    raw_sales_list = sample_rec.get("field-89", []) if 'sample_rec' in locals() else []
    sales_table_data = []
    
    if raw_sales_list:
        for item in raw_sales_list:
            rec = item.get("record", item) if isinstance(item, dict) else {}
            sales_table_data.append({
                "売上日": parse_date_safe(rec.get("field-89_1")),
                "請求数量": rec.get("field-89_3", "0")
            })
    else:
        sales_table_data = [{"売上日": None, "請求数量": "0"}]
        
    df_sales = pd.DataFrame(sales_table_data)
    edited_sales = st.data_editor(
        df_sales,
        num_rows="dynamic",
        key="editor_sales_clean",
        use_container_width=True,
        column_config={
            "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD"),
            "請求数量": st.column_config.TextColumn("請求数量")
        }
    )
    
    if st.button("🚀 請求書プレビュー / 印刷（PDF）を作成", type="primary", key="btn_pdf_invoice"):
        try:
            unit_price = float(field_5) if 'field_5' in locals() else 0
        except ValueError:
            unit_price = 0
            
        total_qty = 0
        for _, row in edited_sales.iterrows():
            q_str = str(row["請求数量"])
            if q_str.isdigit():
                total_qty += int(q_str)
                
        total_amount = total_qty * unit_price
            
        inv_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Helvetica Neue', Arial, sans-serif; padding: 30px; color: #333; }}
                h1 {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
                .meta {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .right {{ text-align: right; }}
                .box {{ border: 1px solid #333; padding: 15px; margin-top: 20px; background-color: #f9f9f9; width: 350px; }}
                @media print {{
                    body {{ padding: 0; }}
                    .no-print {{ display: none; }}
                }}
            </style>
        </head>
        <body>
            <h1>請 求 書</h1>
            <div class="meta">
                <div>
                    <p><strong>宛先:</strong> {field_8 if 'field_8' in locals() else ''} 御中</p>
                    <p><strong>件名 (書名):</strong> {field_13 if 'field_13' in locals() else ''}</p>
                    <p><strong>受注番号:</strong> {field_2 if 'field_2' in locals() else ''} / <strong>受注日:</strong> {field_1 if 'field_1' in locals() else ''}</p>
                </div>
                <div>
                    <p><strong>発行日:</strong> {datetime.now().strftime('%Y-%m-%d')}</p>
                </div>
            </div>
            
            <table>
                <tr>
                    <th>売上日 / 対象</th>
                    <th class="right">請求数量</th>
                    <th class="right">単価</th>
                    <th class="right">金額</th>
                </tr>
        """
        for _, row in edited_sales.iterrows():
            s_date = str(row["売上日"]) if pd.notna(row["売上日"]) else ""
            s_qty = row["請求数量"]
            try:
                q_num = int(s_qty) if str(s_qty).isdigit() else 0
            except ValueError:
                q_num = 0
            sub_total = q_num * unit_price
            inv_html += f"""
                <tr>
                    <td>{s_date} 分売上</td>
                    <td class="right">{q_num} 部</td>
                    <td class="right">¥{unit_price:,.2f}</td>
                    <td class="right">¥{sub_total:,.2f}</td>
                </tr>
            """
        inv_html += f"""
            </table>
            
            <h2 style="text-align: right; margin-top: 20px;">ご請求金額合計: ￥{total_amount:,.2f} (税込)</h2>
            
            <div class="box">
                <b>【お振込先口座】</b><br>
                {bank_name} {bank_branch} ({bank_type}) {bank_account}<br>
                口座名義: {bank_holder}
            </div>
            
            <br>
            <div class="no-print" style="text-align: center; margin-top: 20px;">
                <button onclick="window.print();" style="padding: 10px 20px; font-size: 16px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ この請求書を印刷 / PDF保存する</button>
            </div>
        </body>
        </html>
        """
        st.success("請求書が生成されました！画面上のプレビュー、または印刷ボタンからPDFとして保存できます。")
        st.components.v1.html(inv_html, height=600, scrolling=True, key="preview_invoice_html")
        st.download_button("📥 請求書HTMLファイルをダウンロード", data=inv_html.encode("utf-8"), file_name=f"請求書_{field_2 if 'field_2' in locals() else 'i'}.html", mime="text/html", key="download_invoice_html")