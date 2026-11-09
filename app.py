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
                              len(sub_88) if isinstance(sub_88, list) else 0,
                              len(sub_89) if isinstance(sub_89, list) else 0, 1)
                
                for i in range(max_len):
                    item_90 = sub_90[i] if isinstance(sub_90, list) and len(sub_90) > i else {}
                    rec_90 = item_90.get("record", item_90) if isinstance(item_90, dict) else {}
                    
                    item_88 = sub_88[i] if isinstance(sub_88, list) and len(sub_88) > i else {}
                    rec_88 = item_88.get("record", item_88) if isinstance(item_88, dict) else {}
                    
                    item_89 = sub_89[i] if isinstance(sub_89, list) and len(sub_89) > i else {}
                    rec_89 = item_89.get("record", item_89) if isinstance(item_89, dict) else {}
                    
                    val_88_10 = clean_val(rec_88.get("field-88_10", ""))

                    flat_data.append({
                        "更新": False,
                        "_record_idx": record_idx,
                        "受注番号": h_ord_no,
                        "受注日": h_ord_date,
                        "出版社名": h_pub,
                        "書名": h_title,
                        "製本数": h_qty,
                        "単価": h_price,
                        # 工程日 (field-90)
                        "配本日": parse_date_safe(rec_90.get("field-90_1")),
                        "折本日": parse_date_safe(rec_90.get("field-90_3")),
                        "無線日": parse_date_safe(rec_90.get("field-90_4")),
                        "三方日": parse_date_safe(rec_90.get("field-90_5")),
                        "仕上日": parse_date_safe(rec_90.get("field-90_6")),
                        "備考": clean_val(rec_90.get("field-90_9", "")),
                        # 納品関連 (field-88)
                        "納品日": parse_date_safe(rec_88.get("field-88_2")),
                        "納品数": clean_val(rec_88.get("field-88_4", "")),
                        "PL数": clean_val(rec_88.get("field-88_7", "")),
                        "見本数量": clean_val(rec_88.get("field-88_8", "")),
                        "配車区分": val_88_10,
                        "納品": False,
                        "在庫出荷": False,
                        # 請求関連 (field-89)
                        "売上日": parse_date_safe(rec_89.get("field-89_1")),
                        "請求数量": clean_val(rec_89.get("field-89_3", "")),
                        "備考_請求": clean_val(rec_89.get("field-89_4", "")),
                        "請求": False
                    })
            
            df_flat = pd.DataFrame(flat_data)
            
            # 【API更新ボタン】をデータ表示領域の上部に配置
            st.markdown("### 💾 データ更新・保存")
            if st.button("💾 チェックを入れたデータを データベース に一括上書き保存する（受注一覧）", type="primary", key="btn_save_checked_flat"):
                edited_temp = st.session_state.get("grid_flat_main", None)
                # セッションステートから現在編集中のデータを取得して保存処理を実行
                if edited_temp is not None and "edited_rows" in edited_temp:
                    # edited_tempを反映したDataFrameを構築して保存
                    pass # 下記の保存ロジックへ
                # 簡易的に現在作成した edited_flat_df を参照して処理
            
            # 💡 データ表示領域の高さ(height=600)を指定して下へ広く表示
            edited_flat_df = st.data_editor(
                df_flat,
                num_rows="fixed",
                key="grid_flat_main",
                use_container_width=True,
                height=600,
                column_config={
                    "更新": st.column_config.CheckboxColumn("更新チェック", required=True, help="チェックを入れた行のデータを@pocketに上書き保存します"),
                    "_record_idx": None,
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
                    "備考": st.column_config.TextColumn("備考"),
                    "納品日": st.column_config.DateColumn("納品日", format="YYYY-MM-DD", help="納品日（field-88_2）"),
                    "納品数": st.column_config.TextColumn("納品数", help="納品数（field-88_4）"),
                    "PL数": st.column_config.TextColumn("PL数", help="PL数（field-88_7）"),
                    "見本数量": st.column_config.TextColumn("見本数量", help="見本数量（field-88_8）"),
                    "配車区分": st.column_config.TextColumn("配車区分", help="配車区分（field-88_10）"),
                    "納品": st.column_config.CheckboxColumn("納品", help="チェックすると納品書発行の対象になります"),
                    "在庫出荷": st.column_config.CheckboxColumn("在庫出荷", help="チェックすると在庫出荷扱いになります"),
                    "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD"),
                    "請求数量": st.column_config.TextColumn("請求数量"),
                    "備考_請求": st.column_config.TextColumn("備考（請求）"),
                    "請求": st.column_config.CheckboxColumn("請求", help="チェックすると請求書発行の対象になります"),
                }
            )
            
            # データエディター直上のボタン押下時の実際の保存処理
            if st.session_state.get("btn_save_checked_flat_clicked", False) or st.button("💾 チェックを入れた行をデータベースに保存", type="primary", key="save_top_flat"):
                checked_rows = edited_flat_df[edited_flat_df["更新"] == True]
                if checked_rows.empty:
                    st.warning("⚠️ 上書き保存する行の「更新チェック」ボックスにチェックを入れてください。")
                else:
                    execute_database_save(checked_rows, "flat")

            selected_rows = edited_flat_df[edited_flat_df["更新"] == True]
            if selected_rows.empty:
                selected_rows = edited_flat_df.iloc[[0]]
            
            target_record_idx = int(selected_rows.iloc[0]["_record_idx"])
            sample_rec = api_records[target_record_idx]
            field_2 = clean_val(selected_rows.iloc[0]["受注番号"])
            field_13 = clean_val(selected_rows.iloc[0]["書名"])
            
            st.info(f"📌 現在選択中のレコード: **受注番号 {field_2} ({field_13})** （納品書・請求書発行に連動しています）")
            
            # A4横 受注一覧表の印刷プレビュー生成ボタン
            if st.button("🚀 A4横 受注一覧表 プレビュー / 印刷を作成", type="primary", key="btn_pdf_ord_list"):
                ord_list_html = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        @page {{
                            size: A4 landscape;
                            margin: 10mm;
                        }}
                        body {{
                            font-family: 'Helvetica Neue', Arial, sans-serif;
                            color: #333;
                            margin: 0;
                            padding: 0;
                            background: #fff;
                        }}
                        .page {{
                            width: 277mm;
                            margin: 0 auto;
                            box-sizing: border-box;
                        }}
                        h1 {{
                            text-align: center;
                            border-bottom: 2px solid #333;
                            padding-bottom: 8px;
                            margin-bottom: 15px;
                            font-size: 22px;
                            letter-spacing: 2px;
                        }}
                        .meta {{
                            display: flex;
                            justify-content: space-between;
                            margin-bottom: 15px;
                            font-size: 13px;
                        }}
                        table {{
                            width: 100%;
                            border-collapse: collapse;
                            margin-top: 5px;
                            font-size: 11px;
                        }}
                        th, td {{
                            border: 1px solid #ccc;
                            padding: 6px 8px;
                            text-align: left;
                        }}
                        th {{
                            background-color: #e9ecef;
                            font-weight: bold;
                        }}
                        .right {{
                            text-align: right;
                        }}
                        @media print {{
                            body {{ padding: 0; }}
                            .no-print {{ display: none; }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="page">
                        <h1>受 注 一 覧 表</h1>
                        <div class="meta">
                            <div><strong>集計期間 / 対象:</strong> 指定期間の受注データ一覧</div>
                            <div><strong>発行日:</strong> {datetime.now().strftime('%Y-%m-%d')}</div>
                        </div>
                        <table>
                            <tr>
                                <th>受注番号</th>
                                <th>受注日</th>
                                <th>出版社名</th>
                                <th>書名</th>
                                <th class="right">製本数</th>
                                <th>配本日</th>
                                <th>仕上日</th>
                                <th>納品日</th>
                                <th class="right">納品数</th>
                                <th>配車区分</th>
                                <th>備考</th>
                            </tr>
                """
                for _, r in edited_flat_df.iterrows():
                    ord_list_html += f"""
                            <tr>
                                <td>{clean_val(r["受注番号"])}</td>
                                <td>{str(r["受注日"]) if pd.notna(r["受注日"]) else ""}</td>
                                <td>{clean_val(r["出版社名"])}</td>
                                <td>{clean_val(r["書名"])}</td>
                                <td class="right">{clean_val(r["製本数"])}</td>
                                <td>{str(r["配本日"]) if pd.notna(r["配本日"]) else ""}</td>
                                <td>{str(r["仕上日"]) if pd.notna(r["仕上日"]) else ""}</td>
                                <td>{str(r["納品日"]) if pd.notna(r["納品日"]) else ""}</td>
                                <td class="right">{clean_val(r["納品数"])}</td>
                                <td>{clean_val(r["配車区分"])}</td>
                                <td>{clean_val(r["備考"])}</td>
                            </tr>
                    """
                ord_list_html += f"""
                        </table>
                        <div class="no-print" style="text-align: center; margin-top: 25px;">
                            <button onclick="window.print();" style="padding: 10px 20px; font-size: 15px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ 受注一覧表を印刷 / PDF保存する</button>
                        </div>
                    </div>
                </body>
                </html>
                """
                st.success("A4横 受注一覧表プレビューが生成されました！")
                b64_ord_html = base64.b64encode(ord_list_html.encode("utf-8")).decode("utf-8")
                st.components.v1.iframe(f"data:text/html;base64,{b64_ord_html}", height=600, scrolling=True)
                
        else:
            st.warning("⚠️ 該当するレコードが見つかりませんでした。")
    else:
        st.info("ℹ️ 検索条件を指定するか、DBから受注番号を指定してアクセスしてください。")

# ==========================================
# タブ1.5：付物明細（表・カバー・帯・カード）
# ==========================================
with tab_accessory:
    st.header("🏷️ 付物明細（表・カバー・帯・カード）管理")
    st.info("💡 各種付物の『日付』は変更・更新が可能ですが、『印刷所』は参照専用（更新不可）となります。")

    if api_records and len(api_records) > 0:
        acc_flat_data = []
        for record_idx, r in enumerate(api_records):
            h_ord_no = clean_val(r.get("field-2", ""))
            h_pub = clean_val(r.get("field-8", ""))
            h_title = clean_val(r.get("field-13", ""))
            
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
                    "表 印刷所": clean_val(rec_91.get("field-91_2", "")),
                    "カバー 日付": parse_date_safe(rec_91.get("field-91_5")),
                    "カバー 印刷所": clean_val(rec_91.get("field-91_6", "")),
                    "カード 日付": parse_date_safe(rec_91.get("field-91_9")),
                    "カード 印刷所": clean_val(rec_91.get("field-91_10", "")),
                    "帯 日付": parse_date_safe(rec_91.get("field-91_13")),
                    "帯 印刷所": clean_val(rec_91.get("field-91_14", ""))
                })
        
        df_acc = pd.DataFrame(acc_flat_data)
        
        # 【API更新ボタン】を付物明細の上部に配置
        if st.button("💾 チェックを入れた付物データを データベース に一括上書き保存する", type="primary", key="save_top_acc"):
            checked_acc = edited_acc_df[edited_acc_df["更新"] == True]
            if checked_acc.empty:
                st.warning("⚠️ 上書き保存する行の「更新チェック」ボックスにチェックを入れてください。")
            else:
                execute_database_save(checked_acc, "acc")

        # 💡 付物明細のエディターも高さ(height=600)を指定して下へ広く表示
        edited_acc_df = st.data_editor(
            df_acc,
            num_rows="fixed",
            key="grid_accessory_main",
            use_container_width=True,
            height=600,
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
# タブ2：納品書発行（A4横）
# ==========================================
with tab2:
    st.header("📦 納品書発行（A4横）")
    st.info("💡 タブ1の明細行で**「納品」**にチェックが入っているデータを、**[納品日] [配車区分] [出版社名]** ごとの納品ヘッダーでまとめて納品書を作成します。")
    
    if 'edited_flat_df' in locals() and edited_flat_df is not None:
        delivery_rows = []
        for _, row in edited_flat_df.iterrows():
            if row.get("納品", False):
                ord_no_raw = clean_val(row.get("受注番号", ""))
                d_date_val = row.get("納品日", "")
                
                mmdd = ""
                if pd.notna(d_date_val):
                    if isinstance(d_date_val, (date, datetime)):
                        mmdd = d_date_val.strftime("%m%d")
                    else:
                        parsed_d = parse_date_safe(d_date_val)
                        if parsed_d:
                            mmdd = parsed_d.strftime("%m%d")
                if not mmdd:
                    mmdd = datetime.now().strftime("%m%d")
                
                base_ord = ord_no_raw if ord_no_raw else "000000"
                delivery_no = (base_ord + mmdd)[-10:]
                if len(delivery_no) < 10:
                    delivery_no = delivery_no.zfill(10)

                delivery_rows.append({
                    "納品書番号": delivery_no,
                    "納品日": clean_val(row.get("納品日", "")),
                    "配車区分": clean_val(row.get("配車区分", "")),
                    "出版社名": clean_val(row.get("出版社名", "")),
                    "書名": clean_val(row.get("書名", "")),
                    "製本数": clean_val(row.get("製本数", "0")),
                    "数量": clean_val(row.get("納品数", "0")),
                    "PL数": clean_val(row.get("PL数", "0")),
                    "見本数": clean_val(row.get("見本数量", "0")),
                    "備考": clean_val(row.get("備考", ""))
                })
    else:
        delivery_rows = []
    
    if not delivery_rows:
        st.warning("⚠️ 「納品」にチェックが入っている明細がありません。\nタブ1の明細一覧で「納品」チェックを入れてください。")
    else:
        st.success(f"✨ 納品対象の明細が **{len(delivery_rows)} 件** 選択されています。")
        
        df_preview = pd.DataFrame(delivery_rows)
        st.dataframe(df_preview, use_container_width=True)
        
        if st.button("🚀 グループ別 A4横 納品書プレビュー / 印刷を作成", type="primary", key="btn_pdf_deliv_grouped"):
            from collections import defaultdict
            grouped_deliv = defaultdict(list)
            for r in delivery_rows:
                key = (r["納品日"], r["配車区分"], r["出版社名"], r["納品書番号"])
                grouped_deliv[key].append(r)
                
            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    @page {{
                        size: A4 landscape;
                        margin: 10mm;
                    }}
                    body {{
                        font-family: 'Helvetica Neue', Arial, sans-serif;
                        color: #333;
                        margin: 0;
                        padding: 0;
                        background: #fff;
                    }}
                    .invoice-page {{
                        width: 277mm;
                        min-height: 180mm;
                        page-break-after: always;
                        margin-bottom: 20px;
                        padding-bottom: 20px;
                        border-bottom: 2px dashed #ccc;
                        box-sizing: border-box;
                    }}
                    h1 {{
                        text-align: center;
                        border-bottom: 2px solid #333;
                        padding-bottom: 8px;
                        margin-bottom: 10px;
                        font-size: 24px;
                        letter-spacing: 4px;
                    }}
                    .meta {{
                        display: flex;
                        justify-content: space-between;
                        align-items: flex-start;
                        margin-bottom: 15px;
                        font-size: 14px;
                    }}
                    .customer-name {{
                        font-size: 26px;
                        font-weight: bold;
                        border-bottom: 2px solid #333;
                        padding-bottom: 4px;
                        display: inline-block;
                        margin-bottom: 5px;
                    }}
                    .supplier-info {{
                        text-align: right;
                        font-size: 13px;
                        line-height: 1.4;
                    }}
                    .group-header {{
                        background-color: #f1f3f5;
                        padding: 8px 12px;
                        margin-bottom: 15px;
                        font-weight: bold;
                        border-left: 5px solid #007bff;
                        font-size: 14px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                        margin-bottom: 20px;
                        font-size: 14px;
                    }}
                    th, td {{
                        border: 1px solid #ccc;
                        padding: 10px;
                        text-align: left;
                    }}
                    th {{
                        background-color: #e9ecef;
                        font-weight: bold;
                    }}
                    .right {{
                        text-align: right;
                    }}
                    @media print {{
                        body {{ padding: 0; }}
                        .no-print {{ display: none; }}
                        .invoice-page {{ border-bottom: none; }}
                    }}
                </style>
            </head>
            <body>
            """
            
            for (d_date, car_div, pub_name, deliv_no), items in grouped_deliv.items():
                html_content += f"""
                <div class="invoice-page">
                    <h1>納 品 書</h1>
                    <div class="meta">
                        <div>
                            <span class="customer-name">{pub_name if pub_name else '（出版社名未設定）'} 御中</span><br>
                            <p style="margin: 5px 0 0 0;"><strong>納品書番号:</strong> {deliv_no}</p>
                        </div>
                        <div class="supplier-info">
                            <strong>(株)中永製本所</strong><br>
                            埼玉県さいたま市岩槻区真福寺1400<br>
                            TEL 048-798-7377<br>
                            <strong>発行日:</strong> {datetime.now().strftime('%Y-%m-%d')}
                        </div>
                    </div>
                    
                    <div class="group-header">
                        納品日: {d_date if d_date else '（未設定）'} &nbsp;&nbsp;|&nbsp;&nbsp; 配車区分: {car_div if car_div else '（未設定）'}
                    </div>
                    
                    <p>下記のとおり納品いたしました。</p>
                    <table>
                        <tr>
                            <th>書名 （製本数）</th>
                            <th class="right" style="width: 100px;">数量</th>
                            <th class="right" style="width: 100px;">PL数</th>
                            <th class="right" style="width: 100px;">見本数</th>
                            <th style="width: 250px;">備考</th>
                        </tr>
                """
                for item in items:
                    title_display = f"{item['書名']} （{item['製本数']}部）" if item['書名'] else '（書名なし）'
                    html_content += f"""
                        <tr>
                            <td>{title_display}</td>
                            <td class="right">{item['数量']} 部</td>
                            <td class="right">{item['PL数']} PL</td>
                            <td class="right">{item['見本数']} 部</td>
                            <td>{item['備考']}</td>
                        </tr>
                    """
                html_content += f"""
                    </table>
                </div>
                """
                
            html_content += f"""
                <div class="no-print" style="text-align: center; margin-top: 30px;">
                    <button onclick="window.print();" style="padding: 12px 24px; font-size: 16px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ A4横で一括印刷 / PDF保存する</button>
                </div>
            </body>
            </html>
            """
            st.success("A4横対応・納品元情報付きの納品書が生成されました！")
            
            b64_html = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
            st.components.v1.iframe(f"data:text/html;base64,{b64_html}", height=600, scrolling=True)

# ==========================================
# タブ3：請求書発行（A4横）
# ==========================================
with tab3:
    st.header("📄 請求書発行（出版社別・口座指定可 / A4横）")
    st.info("💡 タブ1の明細行で**「請求」**のチェックボックスにチェックが入っているデータを、**出版社名ごと**にまとめて **A4横** の請求書を作成します。")
    
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        bank_name = st.text_input("銀行名", value="三井住友銀行", key="b_name")
        bank_branch = st.text_input("支店名", value="岩槻支店", key="b_branch")
    with bc2:
        bank_type = st.selectbox("口座種別", options=["普通", "当座"], key="b_type")
        bank_account = st.text_input("口座番号", value="1234567", key="b_acc")
    with bc3:
        bank_holder = st.text_input("口座名義", value="カ）チュウエイセイホンジョ", key="b_holder")

    if 'edited_flat_df' in locals() and edited_flat_df is not None:
        invoice_rows = []
        for _, row in edited_flat_df.iterrows():
            if row.get("請求", False):
                invoice_rows.append({
                    "出版社名": clean_val(row.get("出版社名", "")),
                    "書名": clean_val(row.get("書名", "")),
                    "売上日": row.get("売上日"),
                    "請求数量": clean_val(row.get("請求数量", "0")),
                    "単価": clean_val(row.get("単価", "0")),
                    "備考": clean_val(row.get("備考_請求", ""))
                })
    else:
        invoice_rows = []
    
    if not invoice_rows:
        st.warning("⚠️ 「請求」にチェックが入っている明細がありません。\nタブ1の明細一覧で「請求」チェックを入れてください。")
    else:
        st.success(f"✨ 請求対象の明細が **{len(invoice_rows)} 件** 選択されています。")
        
        df_inv_preview = pd.DataFrame(invoice_rows)
        st.dataframe(df_inv_preview, use_container_width=True)
        
        if st.button("🚀 出版社別 A4横 請求書プレビュー / 印刷を作成", type="primary", key="btn_pdf_invoice"):
            from collections import defaultdict
            grouped_invoice = defaultdict(list)
            for r in invoice_rows:
                grouped_invoice[r["出版社名"]].append(r)
                
            inv_html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    @page {{
                        size: A4 landscape;
                        margin: 10mm;
                    }}
                    body {{
                        font-family: 'Helvetica Neue', Arial, sans-serif;
                        color: #333;
                        margin: 0;
                        padding: 0;
                        background: #fff;
                    }}
                    .invoice-page {{
                        width: 277mm;
                        min-height: 180mm;
                        page-break-after: always;
                        margin-bottom: 20px;
                        padding-bottom: 20px;
                        border-bottom: 2px dashed #ccc;
                        box-sizing: border-box;
                    }}
                    h1 {{
                        text-align: center;
                        border-bottom: 2px solid #333;
                        padding-bottom: 8px;
                        margin-bottom: 15px;
                        font-size: 24px;
                        letter-spacing: 4px;
                    }}
                    .meta {{
                        display: flex;
                        justify-content: space-between;
                        align-items: flex-start;
                        margin-bottom: 20px;
                        font-size: 14px;
                    }}
                    .customer-name {{
                        font-size: 26px;
                        font-weight: bold;
                        border-bottom: 2px solid #333;
                        padding-bottom: 4px;
                        display: inline-block;
                        margin-bottom: 10px;
                    }}
                    .supplier-info {{
                        text-align: right;
                        font-size: 13px;
                        line-height: 1.4;
                    }}
                    .summary-box {{
                        background-color: #f8f9fa;
                        border: 1px solid #ced4da;
                        padding: 12px 15px;
                        margin-bottom: 20px;
                        font-size: 15px;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                        margin-bottom: 20px;
                        font-size: 14px;
                    }}
                    th, td {{
                        border: 1px solid #ccc;
                        padding: 10px;
                        text-align: left;
                    }}
                    th {{
                        background-color: #e9ecef;
                        font-weight: bold;
                    }}
                    .right {{
                        text-align: right;
                    }}
                    .bank-box {{
                        border: 1px solid #333;
                        padding: 12px;
                        margin-top: 15px;
                        background-color: #f9f9f9;
                        width: 320px;
                        font-size: 13px;
                        line-height: 1.4;
                    }}
                    @media print {{
                        body {{ padding: 0; }}
                        .no-print {{ display: none; }}
                        .invoice-page {{ border-bottom: none; }}
                    }}
                </style>
            </head>
            <body>
            """
            
            for pub_name, items in grouped_invoice.items():
                sale_dates = [parse_date_safe(i["売上日"]) for i in items if parse_date_safe(i["売上日"])]
                if sale_dates:
                    min_d = min(sale_dates).strftime('%Y年%m月%d日')
                    max_d = max(sale_dates).strftime('%Y年%m月%d日')
                    period_str = f"{min_d} ～ {max_d}" if min_d != max_d else min_d
                else:
                    period_str = datetime.now().strftime('%Y年%m月度')

                subtotal = 0
                for item in items:
                    q_str = clean_val(item["請求数量"])
                    p_str = clean_val(item["単価"])
                    q_num = int(q_str) if q_str.isdigit() else 0
                    try:
                        p_num = float(p_str) if p_str else 0.0
                    except ValueError:
                        p_num = 0.0
                    subtotal += q_num * p_num
                
                tax_amount = round(subtotal * 0.10)
                grand_total = subtotal + tax_amount

                inv_html += f"""
                <div class="invoice-page">
                    <h1>請 求 書</h1>
                    <div class="meta">
                        <div>
                            <span class="customer-name">{pub_name if pub_name else '（出版社名未設定）'} 御中</span><br>
                            <p style="margin: 5px 0 0 0;">下記のとおりご請求申し上げます。</p>
                        </div>
                        <div class="supplier-info">
                            <strong>(株)中永製本所</strong><br>
                            埼玉県さいたま市岩槻区真福寺1400<br>
                            TEL 048-798-7377<br>
                            <strong>発行日:</strong> {datetime.now().strftime('%Y-%m-%d')}
                        </div>
                    </div>
                    
                    <div class="summary-box">
                        <table style="width: 100%; border: none; margin: 0;">
                            <tr style="border: none;">
                                <td style="border: none; padding: 2px 0;"><strong>売上期間:</strong> {period_str}</td>
                                <td style="border: none; padding: 2px 0; text-align: right; font-size: 16px;"><strong>ご請求金額合計（税込）: ￥{grand_total:,.0f}</strong></td>
                            </tr>
                            <tr style="border: none;">
                                <td style="border: none; padding: 2px 0;"></td>
                                <td style="border: none; padding: 2px 0; text-align: right; color: #555;">（うち消費税額等: ￥{tax_amount:,.0f}）</td>
                            </tr>
                        </table>
                    </div>
                    
                    <table>
                        <tr>
                            <th style="width: 110px;">納品日</th>
                            <th>書名</th>
                            <th class="right" style="width: 90px;">請求数量</th>
                            <th class="right" style="width: 110px;">単価</th>
                            <th class="right" style="width: 130px;">金額</th>
                            <th style="width: 180px;">備考</th>
                        </tr>
                """
                
                for item in items:
                    q_str = clean_val(item["請求数量"])
                    p_str = clean_val(item["単価"])
                    q_num = int(q_str) if q_str.isdigit() else 0
                    try:
                        p_num = float(p_str) if p_str else 0.0
                    except ValueError:
                        p_num = 0.0
                    line_total = q_num * p_num
                    
                    inv_html += f"""
                        <tr>
                            <td>{str(item["売上日"]) if pd.notna(item["売上日"]) else ""}</td>
                            <td>{item["書名"]}</td>
                            <td class="right">{q_num} 部</td>
                            <td class="right">￥{p_num:,.2f}</td>
                            <td class="right">￥{line_total:,.2f}</td>
                            <td>{item["備考"]}</td>
                        </tr>
                    """
                
                inv_html += f"""
                    </table>
                    
                    <div class="bank-box">
                        <b>【お振込先口座】</b><br>
                        {bank_name} {bank_branch} ({bank_type}) {bank_account}<br>
                        口座名義: {bank_holder}
                    </div>
                </div>
                """
                
            inv_html += f"""
                <div class="no-print" style="text-align: center; margin-top: 30px;">
                    <button onclick="window.print();" style="padding: 12px 24px; font-size: 16px; background-color: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer;">🖨️ A4横 請求書を一括印刷 / PDF保存する</button>
                </div>
            </body>
            </html>
            """
            
            st.success("出版社別のA4横請求書が生成されました！")
            b64_inv_html = base64.b64encode(inv_html.encode("utf-8")).decode("utf-8")
            st.components.v1.iframe(f"data:text/html;base64,{b64_inv_html}", height=600, scrolling=True)