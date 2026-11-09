import io
import os
import json
import base64
import requests
import pandas as pd
from datetime import datetime, timedelta, date
import streamlit as st

# ==========================================
# 1. ページ基本設定（Streamlitヘッダー非表示）
# ==========================================
st.set_page_config(page_title="受注一覧表", layout="wide", initial_sidebar_state="collapsed")

# Streamlitのデフォルト上部タイトル/ヘッダーをCSSで完全に非表示にする
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📊 受注一覧表 ＆ 付物・納品・請求管理システム")

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
# 3. 便利関数（データクリーニング・日付パース）
# ==========================================
def clean_val(val):
    """None、NaN、文字列の 'none' や 'nan' を完全に空文字に変換する"""
    if val is None:
        return ""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.lower() in ["none", "nan", "nat", "null"]:
        return ""
    return s

def parse_date_safe(val):
    s = clean_val(val)
    if not s:
        return None
    try:
        if isinstance(val, (date, datetime)):
            return val.date() if isinstance(val, datetime) else val
        return datetime.strptime(s[:10].replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        return None

# ==========================================
# 4. URLパラメータのチェック
# ==========================================
query_params = st.query_params
url_order_no = query_params.get("ord", None)

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
# 保存処理の共通関数
# ==========================================
def execute_database_save(checked_rows, source_tab):
    headers = {
        "X-At-Pocket-API-Key": POCKET_API_KEY, 
        "Accept": "application/json", 
        "Content-Type": "application/json"
    }
    success_count = 0
    fail_count = 0
    
    grouped_records = checked_rows.groupby("_record_idx")
    import copy
    
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
            "field-2": clean_val(original_rec.get("field-2", "")),
            "field-1": clean_val(original_rec.get("field-1", "")),
            "field-4": clean_val(original_rec.get("field-4", "")),
            "field-5": clean_val(original_rec.get("field-5", "")),
        }
        
        # 1. field-90 (工程日) の構築
        orig_sub_90 = original_rec.get("field-90", [])
        sub90_list = []
        if source_tab == "flat":
            row_90 = first_row
            if isinstance(orig_sub_90, list) and len(orig_sub_90) > 0:
                item_90 = copy.deepcopy(orig_sub_90[0])
                rec_dict = item_90.get("record", {})
                rec_dict["field-90_1"] = clean_val(row_90["配本日"])
                rec_dict["field-90_3"] = clean_val(row_90["折本日"])
                rec_dict["field-90_4"] = clean_val(row_90["無線日"])
                rec_dict["field-90_5"] = clean_val(row_90["三方日"])
                rec_dict["field-90_6"] = clean_val(row_90["仕上日"])
                rec_dict["field-90_9"] = clean_val(row_90["備考"])
                item_90["record"] = rec_dict
                sub90_list.append(item_90)
            else:
                sub90_list.append({
                    "record": {
                        "field-90_1": clean_val(first_row["配本日"]),
                        "field-90_3": clean_val(first_row["折本日"]),
                        "field-90_4": clean_val(first_row["無線日"]),
                        "field-90_5": clean_val(first_row["三方日"]),
                        "field-90_6": clean_val(first_row["仕上日"]),
                        "field-90_9": clean_val(first_row["備考"]),
                        "field-90_2": ""
                    }
                })
            record_payload["field-90"] = sub90_list
        else:
            record_payload["field-90"] = orig_sub_90

        # 2. field-88 (納品明細) の構築
        orig_sub_88 = original_rec.get("field-88", [])
        sub88_list = []
        if source_tab == "flat":
            row_88 = first_row
            deliv_date_val = row_88["納品日"]
            deliv_date_str = ""
            if pd.notna(deliv_date_val):
                if isinstance(deliv_date_val, (date, datetime)):
                    deliv_date_str = deliv_date_val.strftime("%Y-%m-%d")
                else:
                    parsed_d = parse_date_safe(deliv_date_val)
                    if parsed_d:
                        deliv_date_str = parsed_d.strftime("%Y-%m-%d")

            if isinstance(orig_sub_88, list) and len(orig_sub_88) > 0:
                item_88 = copy.deepcopy(orig_sub_88[0])
                rec_dict_88 = item_88.get("record", {})
                rec_dict_88["field-88_2"] = deliv_date_str
                rec_dict_88["field-88_4"] = clean_val(row_88["納品数"]) or "0"
                rec_dict_88["field-88_7"] = clean_val(row_88["PL数"]) or "0"
                rec_dict_88["field-88_8"] = clean_val(row_88["見本数量"]) or "0"
                rec_dict_88["field-88_10"] = clean_val(row_88["配車区分"])
                
                item_88["record"] = rec_dict_88
                sub88_list.append(item_88)
            else:
                sub88_list.append({
                    "record": {
                        "field-88_2": deliv_date_str,
                        "field-88_4": clean_val(first_row["納品数"]) or "0",
                        "field-88_7": clean_val(first_row["PL数"]) or "0",
                        "field-88_8": clean_val(first_row["見本数量"]) or "0",
                        "field-88_10": clean_val(first_row["配車区分"])
                    }
                })
            record_payload["field-88"] = sub88_list
        else:
            record_payload["field-88"] = orig_sub_88

        # 3. field-89 (請求/売上明細) の構築
        orig_sub_89 = original_rec.get("field-89", [])
        sub89_list = []
        if source_tab == "flat":
            row_89 = first_row
            sale_date_val = row_89["売上日"]
            sale_date_str = ""
            if pd.notna(sale_date_val):
                if isinstance(sale_date_val, (date, datetime)):
                    sale_date_str = sale_date_val.strftime("%Y-%m-%d")
                else:
                    parsed_s = parse_date_safe(sale_date_val)
                    if parsed_s:
                        sale_date_str = parsed_s.strftime("%Y-%m-%d")

            if isinstance(orig_sub_89, list) and len(orig_sub_89) > 0:
                item_89 = copy.deepcopy(orig_sub_89[0])
                rec_dict_89 = item_89.get("record", {})
                rec_dict_89["field-89_1"] = sale_date_str
                rec_dict_89["field-89_3"] = clean_val(row_89["請求数量"]) or "0"
                rec_dict_89["field-89_4"] = clean_val(row_89["備考_請求"])
                for k in ["field-89_5", "field-89_6"]:
                    rec_dict_89.pop(k, None)
                item_89["record"] = rec_dict_89
                sub89_list.append(item_89)
            else:
                sub89_list.append({
                    "record": {
                        "field-89_1": sale_date_str,
                        "field-89_3": clean_val(first_row["請求数量"]) or "0",
                        "field-89_4": clean_val(first_row["備考_請求"])
                    }
                })
            record_payload["field-89"] = sub89_list
        else:
            cleaned_sub89 = []
            for item in orig_sub_89:
                item_cp = copy.deepcopy(item)
                rec = item_cp.get("record", item_cp)
                if isinstance(rec, dict):
                    for k in ["field-89_5", "field-89_6"]:
                        rec.pop(k, None)
                cleaned_sub89.append(item_cp)
            record_payload["field-89"] = cleaned_sub89

        # 4. field-91 (付物明細) の構築
        orig_sub_91 = original_rec.get("field-91", [])
        sub91_list = []
        if source_tab == "acc":
            row_91 = first_row
            if isinstance(orig_sub_91, list) and len(orig_sub_91) > 0:
                item_91 = copy.deepcopy(orig_sub_91[0])
                rec_dict_91 = item_91.get("record", {})
                
                rec_dict_91["field-91_1"] = clean_val(row_91["表 日付"])
                rec_dict_91["field-91_5"] = clean_val(row_91["カバー 日付"])
                rec_dict_91["field-91_9"] = clean_val(row_91["カード 日付"])
                rec_dict_91["field-91_13"] = clean_val(row_91["帯 日付"])
                
                for k in ["field-91_2", "field-91_6", "field-91_10", "field-91_14"]:
                    rec_dict_91.pop(k, None)
                    
                item_91["record"] = rec_dict_91
                sub91_list.append(item_91)
            else:
                sub91_list.append({
                    "record": {
                        "field-91_1": clean_val(first_row["表 日付"]),
                        "field-91_5": clean_val(first_row["カバー 日付"]),
                        "field-91_9": clean_val(first_row["カード 日付"]),
                        "field-91_13": clean_val(first_row["帯 日付"])
                    }
                })
            record_payload["field-91"] = sub91_list
        else:
            cleaned_sub91 = []
            for item in orig_sub_91:
                item_cp = copy.deepcopy(item)
                rec = item_cp.get("record", item_cp)
                if isinstance(rec, dict):
                    for k in ["field-91_2", "field-91_6", "field-91_10", "field-91_14"]:
                        rec.pop(k, None)
                cleaned_sub91.append(item_cp)
            record_payload["field-91"] = cleaned_sub91

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
# タブ1：受注一覧表 ＆ 工程日・納品・請求明細エディタ
# ==========================================
with tab1:
    st.header("📋 受注一覧表 ＆ 工程・納品・請求管理")
    
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
                h_ord_no = clean_val(r.get("field-2", ""))
                h_ord_date = parse_date_safe(r.get("field-1"))
                h_pub = clean_val(r.get("field-8", ""))
                h_title = clean_val(r.get("field-13", ""))
                h_qty = clean_val(r.get("field-4", ""))
                h_price = clean_val(r.get("field-5", ""))
                
                sub_90 = r.get("field-90", [])
                sub_88 = r.get("field-88", [])
                sub_89 = r.get("field-89", [])
                
                max_len = max(len(sub_90) if isinstance(sub_90, list) else 0,
                              len(sub_88) if isinstance(sub_88, list) else