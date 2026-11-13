import io
import os
import json
import base64
import requests
import pandas as pd
from datetime import datetime, timedelta, date
import streamlit as st

# ReportLab関連のインポート（PDF出力用）
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

# ==========================================
# 1. ページ基本設定 ＆ 濃紺シックデザインCSS
# ==========================================
st.set_page_config(page_title="納品・請求管理システム", layout="wide", initial_sidebar_state="collapsed")

dark_navy_theme_css = """
    <style>
    .stApp {
        background-color: #F8FAFC;
    }
    h1, h2, h3 {
        color: #0F172A !important;
        font-family: 'Helvetica Neue', Arial, sans-serif;
    }
    div.stButton > button:first-child {
        background-color: #1E3A8A;
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: bold;
        padding: 0.5rem 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: background-color 0.2s;
    }
    div.stButton > button:first-child:hover {
        background-color: #1E40AF;
        color: white;
    }
    div.stDownloadButton > button:first-child {
        background-color: #0F172A;
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: bold;
    }
    div.stDownloadButton > button:first-child:hover {
        background-color: #1E293B;
        color: white;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #E2E8F0;
        border-radius: 6px 6px 0px 0px;
        color: #334155;
        font-weight: bold;
        padding: 10px 18px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E3A8A !important;
        color: white !important;
    }
    .streamlit-expanderHeader {
        background-color: #F1F5F9;
        border-radius: 6px;
        color: #1E293B;
        font-weight: bold;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(dark_navy_theme_css, unsafe_allow_html=True)

st.title("📦 納品・請求管理システム（@pocket連動）")

# ==========================================
# 2. 日本語フォント登録処理（ReportLab用）
# ==========================================
def setup_japanese_font():
    local_font_path = "NotoSansJP-Regular.ttf"
    if os.path.exists(local_font_path):
        try:
            pdfmetrics.registerFont(TTFont("JPFont", local_font_path))
            return "JPFont"
        except Exception as e:
            print(f"同梱フォント登録エラー: {e}")

    win_font = os.path.join(
        os.environ.get("SystemRoot", "C:\\Windows"), "Fonts", "msgothic.ttc"
    )
    if os.path.exists(win_font):
        try:
            pdfmetrics.registerFont(TTFont("JPFont", win_font, subfontIndex=0))
            return "JPFont"
        except Exception as e:
            print(f"Windowsフォント登録エラー: {e}")

    return "Helvetica"

FONT_NAME = setup_japanese_font()

# ==========================================
# 3. Secrets設定
# ==========================================
if "pocket" in st.secrets:
    POCKET_API_KEY = st.secrets["pocket"].get("api_key", "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08")
    POCKET_BASE_URL = st.secrets["pocket"].get("base_url", "https://app070.at-pocket.com/arkf05_bb")
else:
    POCKET_API_KEY = "XZtsg3OrDFOh0VayOI83j84Oc3YIzm7oujbI0T08"
    POCKET_BASE_URL = "https://app070.at-pocket.com/arkf05_bb"

APP_ID = 34  # @pocket対象アプリID

# ==========================================
# 4. 便利関数
# ==========================================
def clean_val(val):
    if val is None:
        return ""
    if isinstance(val, (list, dict)):
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
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

def date_to_str(val):
    if pd.isna(val) or not val:
        return ""
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    parsed = parse_date_safe(val)
    return parsed.strftime("%Y-%m-%d") if parsed else ""

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    output.seek(0)
    return output

# --- @pocket データ更新用関数 ---
def update_pocket_record(record_id, update_data):
    if not record_id:
        return False, "レコードIDが不正です"
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records/{record_id}"
    headers = {
        "X-At-Pocket-API-Key": POCKET_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "apiVersion": 1.1,
        "record": update_data
    }
    try:
        response = requests.put(url, headers=headers, json=payload, timeout=20)
        if response.status_code in [200, 204]:
            return True, "成功"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)

# --- 納品書PDF生成関数 ---
def generate_delivery_pdf(grouped_deliv_dict):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle("Title", parent=styles["Normal"], fontName=FONT_NAME, fontSize=16, leading=18, alignment=1, textColor=colors.HexColor("#1E3A8A"))
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#333333"))
    company_style = ParagraphStyle("SInfo", parent=styles["Normal"], fontName=FONT_NAME, fontSize=11, leading=15, textColor=colors.HexColor("#0F172A"), alignment=2)
    
    th_style = ParagraphStyle("TH", parent=styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=10, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle("TD", parent=styles["Normal"], fontName=FONT_NAME, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#1E293B"))
    td_right = ParagraphStyle("TDR", parent=td_style, alignment=2)
    td_sub_style = ParagraphStyle("TDSub", parent=styles["Normal"], fontName=FONT_NAME, fontSize=7, leading=9, textColor=colors.HexColor("#475569"))

    elements = []
    
    for idx, ((cust_name, d_date, shipping_div), items) in enumerate(grouped_deliv_dict.items()):
        mmdd = d_date.replace("-", "")[2:6] if len(d_date) >= 10 else datetime.now().strftime("%m%d")
        base_ord = items[0]["受注番号"] if items else "000000"
        deliv_no = (base_ord + mmdd)[-10:].zfill(10)

        chunk_size = 8
        item_chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        
        for chunk_idx, chunk_items in enumerate(item_chunks):
            if idx > 0 or chunk_idx > 0:
                elements.append(PageBreak())
                
            elements.append(Paragraph("<b>納 品 書</b>", title_style))
            elements.append(Spacer(1, 6))
            
            shipping_label = f" (配送振分: {shipping_div})" if shipping_div else ""
            meta_data = [
                [
                    Paragraph(f"<b>{cust_name if cust_name else '（得意先名未設定）'} 御中</b>{shipping_label}", ParagraphStyle("CName", parent=h_style, fontSize=12, leading=14)),
                    Paragraph("<b>(株)中永製本所</b><br/>埼玉県さいたま市岩槻区真福寺1400<br/>TEL 048-798-7377", company_style)
                ],
                [
                    Paragraph(f"伝票番号: {deliv_no}<br/>納品日: {d_date if d_date else '（未設定）'}", h_style),
                    Paragraph(f"発行日: {date.today().strftime('%Y年%m月%d日')}", ParagraphStyle("DateInfo", parent=h_style, alignment=2))
                ]
            ]
            meta_table = Table(meta_data, colWidths=[400, 392])
            meta_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))
            elements.append(meta_table)
            elements.append(Spacer(1, 4))
            
            elements.append(Paragraph("下記のとおり納品いたしました。", h_style))
            elements.append(Spacer(1, 4))
            
            table_data = [[
                Paragraph("受注番号", th_style),
                Paragraph("書名", th_style),
                Paragraph("定価", th_style),
                Paragraph("判型", th_style),
                Paragraph("刷数", th_style),
                Paragraph("部数", th_style),
                Paragraph("パレット数", th_style),
                Paragraph("見本", th_style)
            ]]
            
            t_styles = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ]
            
            row_idx = 1
            for item in chunk_items:
                table_data.append([
                    Paragraph(item['受注番号'], td_style),
                    Paragraph(item['書名'], td_style),
                    Paragraph(item['定価'], td_right),
                    Paragraph(item['判型'], td_style),
                    Paragraph(item['刷数'], td_right),
                    Paragraph(f"{item['部数']} 部", td_right),
                    Paragraph(f"{item['パレット数']} PL", td_right),
                    Paragraph(f"{item['見本']} 部", td_right)
                ])
                table_data.append([
                    Paragraph(f"<b>ISBN:</b> {item['ISBN']}", td_sub_style),
                    Paragraph(f"<b>備考:</b> {item['備考']}", td_sub_style), "", "",
                    Paragraph(f"<b>印:</b> {item['印']}", td_sub_style),
                    Paragraph(f"<b>製品預:</b> {item['製品預かり']}", td_sub_style),
                    Paragraph(f"<b>預納品:</b> {item['預より納品']}", td_sub_style),
                    Paragraph(f"<b>納品日:</b> {item['納品日']}", td_sub_style)
                ])
                
                t_styles.append(("SPAN", (1, row_idx + 1), (3, row_idx + 1)))
                bg_color = colors.HexColor("#F8FAFC") if (row_idx // 2) % 2 == 1 else colors.white
                t_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx + 1), bg_color))
                
                row_idx += 2
                
            col_widths = [70, 272, 50, 45, 45, 55, 100, 55]
            d_table = Table(table_data, colWidths=col_widths)
            d_table.setStyle(TableStyle(t_styles))
            elements.append(d_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# ==========================================
# 5. データ取得関数
# ==========================================
query_params = st.query_params
url_order_no = query_params.get("ord", None)

def fetch_pocket_records(start_date=None, end_date=None, target_order_no=None, target_publisher=None, date_field="field-52"):
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
            query_parts.append(f'{date_field} >= "{start_str}" and {date_field} <= "{end_str}"')
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
                rec_id = (
                    item.get("Id") or 
                    item.get("id") or 
                    item.get("ID") or 
                    item.get("recordId") or 
                    rec_body.get("Id") or 
                    rec_body.get("id") or 
                    rec_body.get("recordId") or 
                    ""
                )
                merged_body["_recordId"] = str(rec_id).strip()
                parsed_records.append(merged_body)
            
            if start_date and end_date:
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")
                filtered = []
                for r in parsed_records:
                    raw_d = clean_val(r.get(date_field, ""))
                    if not raw_d:
                        continue
                    d_str = raw_d.replace("/", "-")[:10]
                    if len(d_str) == 10 and start_str <= d_str <= end_str:
                        filtered.append(r)
                parsed_records = filtered

            return parsed_records
        else:
            st.error(f"❌ APIエラー ({response.status_code}): {response.text}")
    except Exception as e:
        st.error(f"🚨 通信例外エラー: {e}")
    return []

if "api_records" not in st.session_state or url_order_no:
    if url_order_no:
        with st.spinner(f"DBから受注番号: {url_order_no} のデータを取得中..."):
            st.session_state["api_records"] = fetch_pocket_records(target_order_no=url_order_no)
    else:
        default_start = date.today()
        default_end = default_start + timedelta(days=14)
        st.session_state["api_records"] = fetch_pocket_records(start_date=default_start, end_date=default_end, date_field="field-52")

# ==========================================
# 6. 検索条件バー（共通）
# ==========================================
with st.expander("🔍 検索条件の設定はこちら", expanded=bool(not url_order_no)):
    search_date_type = st.radio("📅 期間検索の基準を選択", ["納期（field-52）", "受注日（field-1）"], horizontal=True)
    target_date_field = "field-52" if "納期" in search_date_type else "field-1"

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        t1_start = st.date_input("期間（開始）", value=date.today(), key="deliv_s")
    with col_s2:
        t1_end = st.date_input("期間（終了）", value=date.today() + timedelta(days=14), key="deliv_e")
    
    publisher_input = st.text_input("📖 得意先名（出版社名）で絞り込み", value="", key="deliv_pub")
    search_clicked = st.button("🔄 検索実行", type="primary", key="deliv_btn")

if search_clicked:
    st.query_params.clear()
    with st.spinner("@ポケットからデータを取得中..."):
        st.session_state["api_records"] = fetch_pocket_records(
            start_date=t1_start, 
            end_date=t1_end, 
            target_publisher=publisher_input if publisher_input else None,
            date_field=target_date_field
        )
    st.rerun()

api_records = st.session_state.get("api_records", None)

if api_records:
    # ==========================================
    # 7. タブ分割（納品書作成 ＆ 請求処理）
    # ==========================================
    tab_delivery, tab_billing = st.tabs(["📦 納品書作成タブ", "💰 請求処理タブ"])

    # ------------------------------------------
    # Tab 1: 納品書作成
    # ------------------------------------------
    with tab_delivery:
        st.subheader("📦 納品書作成・管理")
        
        flat_data = []
        for record_idx, r in enumerate(api_records):
            rec_id = r.get("_recordId", "")
            detail_url = f"{POCKET_BASE_URL}/apps/{APP_ID}/records/{rec_id}/detail" if rec_id and rec_id.lower() != "none" else ""

            h_ord_no = clean_val(r.get("field-2", ""))
            h_due = parse_date_safe(r.get("field-52"))
            h_pub = clean_val(r.get("field-8", ""))
            h_isbn = clean_val(r.get("field-93", ""))
            h_title = clean_val(r.get("field-13", ""))
            h_price = clean_val(r.get("field-20", ""))
            h_format = clean_val(r.get("field-23", ""))
            h_print_count = clean_val(r.get("field-28", ""))
            h_stamp = clean_val(r.get("field-4", ""))
            h_cust_keeping = clean_val(r.get("field-81", ""))
            
            sub_88 = r.get("field-88", [])
            item_88 = sub_88[0] if isinstance(sub_88, list) and len(sub_88) > 0 else {}
            rec_88 = item_88.get("record", item_88) if isinstance(item_88, dict) else {}
            sub_88_id = str(item_88.get("Id") or item_88.get("id") or item_88.get("recordId") or rec_88.get("Id") or "").strip()

            val_88_13 = clean_val(rec_88.get("field-88_13", ""))

            flat_data.append({
                "更新": False,
                "詳細": detail_url,
                "納期": h_due,
                "得意先名": h_pub,
                "受注番号": h_ord_no,
                "ISBN": h_isbn,
                "書名": h_title,
                "定価": h_price,
                "判型": h_format,
                "刷数": h_print_count,
                "部数": clean_val(rec_88.get("field-88_4", "")),
                "納品日": parse_date_safe(rec_88.get("field-88_2")),
                "印": h_stamp,
                "製品預かり": h_cust_keeping,
                "預より納品": val_88_13,
                "パレット数": clean_val(rec_88.get("field-88_7", "")),
                "配本日": parse_date_safe(rec_88.get("field-88_2")),
                "見本": clean_val(rec_88.get("field-88_8", "")),
                "備考": clean_val(rec_88.get("field-88_5", "")),
                "納品": False,
                "配送振分": clean_val(rec_88.get("field-88_10", "")),
                "_record_idx": record_idx,
                "_recordId": rec_id,
                "_sub_88_id": sub_88_id
            })

        df_deliv = pd.DataFrame(flat_data)
        display_cols = [
            "更新", "詳細", "納期", "得意先名", "受注番号", "ISBN", "書名", "定価", "判型", "刷数", 
            "部数", "納品日", "印", "製品預かり", "預より納品", "パレット数", "配本日", "見本", "備考", "納品", "配送振分"
        ]
        df_deliv_display = df_deliv[[c for c in display_cols if c in df_deliv.columns]]

        edited_deliv_df = st.data_editor(
            df_deliv_display,
            num_rows="fixed",
            key="grid_delivery_sys",
            use_container_width=True,
            column_config={
                "更新": st.column_config.CheckboxColumn("更新", required=True),
                "詳細": st.column_config.LinkColumn("🔗詳細", display_text="📝開く"),
                "納期": st.column_config.DateColumn("納期", format="YYYY-MM-DD", disabled=True),
                "得意先名": st.column_config.TextColumn("得意先名", disabled=True),
                "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                "ISBN": st.column_config.TextColumn("ISBN", disabled=True),
                "書名": st.column_config.TextColumn("書名", disabled=True),
                "定価": st.column_config.TextColumn("定価", disabled=True),
                "判型": st.column_config.TextColumn("判型", disabled=True),
                "刷数": st.column_config.TextColumn("刷数", disabled=True),
                "部数": st.column_config.TextColumn("部数"),
                "納品日": st.column_config.DateColumn("納品日", format="YYYY-MM-DD"),
                "印": st.column_config.TextColumn("印", disabled=True),
                "製品預かり": st.column_config.TextColumn("製品預かり", disabled=True),
                "預より納品": st.column_config.SelectboxColumn("預より納品", options=["", "在庫から"]),
                "パレット数": st.column_config.TextColumn("パレット数"),
                "配本日": st.column_config.DateColumn("配本日", format="YYYY-MM-DD"),
                "見本": st.column_config.TextColumn("見本"),
                "備考": st.column_config.TextColumn("備考"),
                "納品": st.column_config.CheckboxColumn("納品"),
                "配送振分": st.column_config.TextColumn("配送振分")
            }
        )

        st.markdown("---")
        col_save, col_pdf, col_excel = st.columns([1.5, 1.5, 1.5])
        
        with col_save:
            if st.button("💾 変更した行を @pocket に保存", type="primary", key="save_deliv_btn"):
                update_rows = edited_deliv_df[edited_deliv_df["更新"] == True]
                if len(update_rows) == 0:
                    st.warning("⚠️ 「更新」にチェックが入っている行がありません。")
                else:
                    success_count = 0
                    error_messages = []
                    with st.spinner("@pocketへデータを保存中..."):
                        for _, row in update_rows.iterrows():
                            r_id = clean_val(row.get("_recordId", ""))
                            ord_no = clean_val(row.get("受注番号", ""))
                            sub_88_id = clean_val(row.get("_sub_88_id", ""))
                            
                            if not r_id and ord_no:
                                search_url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
                                search_headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
                                search_params = {"query": f'field-2 = "{ord_no}"'}
                                try:
                                    s_res = requests.get(search_url, headers=search_headers, params=search_params, timeout=10)
                                    if s_res.status_code == 200:
                                        s_data = s_res.json()
                                        s_items = s_data.get("records", s_data.get("Data", s_data.get("Records", [])))
                                        if s_items and isinstance(s_items, list):
                                            first_item = s_items[0]
                                            rec_body_sub = first_item.get("record", {})
                                            r_id = str(first_item.get("Id") or first_item.get("id") or rec_body_sub.get("Id") or "").strip()
                                except Exception:
                                    pass

                            if not r_id:
                                error_messages.append(f"受注番号 {ord_no}: レコードIDが取得できませんでした")
                                continue

                            sub_88_item = {
                                "record": {
                                    "field-88_2": date_to_str(row.get("納品日")),
                                    "field-88_4": clean_val(row.get("部数", "")),
                                    "field-88_7": clean_val(row.get("パレット数", "")),
                                    "field-88_8": clean_val(row.get("見本", "")),
                                    "field-88_5": clean_val(row.get("備考", "")),
                                    "field-88_13": clean_val(row.get("預より納品", "")),
                                    "field-88_10": clean_val(row.get("配送振分", ""))
                                }
                            }
                            if sub_88_id:
                                sub_88_item["Id"] = sub_88_id

                            payload = {
                                "field-2": ord_no,
                                "field-88": [sub_88_item]
                            }
                            
                            ok, msg = update_pocket_record(r_id, payload)
                            if ok:
                                success_count += 1
                            else:
                                error_messages.append(f"受注番号 {ord_no}: {msg}")
                    
                    if success_count > 0:
                        st.success(f"✨ **{success_count} 件** のデータを @pocket へ正常に保存しました！（保存完了）")
                        st.toast("✨ 保存が完了しました！", icon="💾")
                    if error_messages:
                        for err in error_messages:
                            st.error(f"❌ 保存エラー: {err}")
                    if success_count > 0:
                        st.rerun()

        checked_deliv_rows = edited_deliv_df[edited_deliv_df["納品"] == True]

        with col_pdf:
            if len(checked_deliv_rows) > 0:
                from collections import defaultdict
                grouped_deliv = defaultdict(list)
                
                for _, row in checked_deliv_rows.iterrows():
                    cust_name = clean_val(row.get("得意先名", ""))
                    d_date_str = date_to_str(row.get("納品日"))
                    shipping_div = clean_val(row.get("配送振分", ""))
                    
                    key = (cust_name, d_date_str, shipping_div)
                    grouped_deliv[key].append({
                        "受注番号": clean_val(row.get("受注番号", "")) or "000000",
                        "ISBN": clean_val(row.get("ISBN", "")),
                        "書名": clean_val(row.get("書名", "")),
                        "定価": clean_val(row.get("定価", "")),
                        "判型": clean_val(row.get("判型", "")),
                        "刷数": clean_val(row.get("刷数", "")),
                        "部数": clean_val(row.get("部数", "0")),
                        "納品日": d_date_str,
                        "印": clean_val(row.get("印", "")),
                        "製品預かり": clean_val(row.get("製品預かり", "")),
                        "預より納品": clean_val(row.get("預より納品", "")),
                        "パレット数": clean_val(row.get("パレット数", "0")),
                        "見本": clean_val(row.get("見本", "0")),
                        "備考": clean_val(row.get("備考", "")),
                        "配送振分": shipping_div
                    })

                pdf_bytes = generate_delivery_pdf(grouped_deliv)
                st.download_button(
                    label="🖨️ 納品書 PDF ダウンロード",
                    data=pdf_bytes,
                    file_name=f"納品書_{date.today().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            else:
                st.button("🖨️ 納品書 PDF ダウンロード", disabled=True, help="「納品」チェックが1件も入っていません")

        with col_excel:
            if len(checked_deliv_rows) > 0:
                excel_bytes = to_excel_bytes(checked_deliv_rows.drop(columns=["更新", "詳細", "_record_idx", "_recordId", "_sub_88_id"], errors="ignore"))
                st.download_button(
                    label="📥 納品データ Excel ダウンロード",
                    data=excel_bytes,
                    file_name=f"納品データ_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.button("📥 納品データ Excel ダウンロード", disabled=True, help="「納品」チェックが1件も入っていません")

    # ------------------------------------------
    # Tab 2: 請求処理
    # ------------------------------------------
    with tab_billing:
        st.subheader("💰 請求処理・明細管理（field-89）")
        st.info("💡 納品完了したデータの売上日・数量・販売単価（field-5から流し込み・更新可能）・備考・見本（field-89_12）を編集し、@pocketの請求明細へ保存できます。")

        billing_flat_data = []
        for record_idx, r in enumerate(api_records):
            rec_id = r.get("_recordId", "")
            h_ord_no = clean_val(r.get("field-2", ""))
            h_pub = clean_val(r.get("field-8", ""))
            h_title = clean_val(r.get("field-13", "")) # メインの品名 (field-13)
            h_unit_price_default = clean_val(r.get("field-5", "")) # メインの販売単価 (field-5)

            # 納品サブテーブルからの見本取得 (field-88_8)
            sub_88 = r.get("field-88", [])
            item_88 = sub_88[0] if isinstance(sub_88, list) and len(sub_88) > 0 else {}
            rec_88 = item_88.get("record", item_88) if isinstance(item_88, dict) else {}
            default_mihon = clean_val(rec_88.get("field-88_8", ""))
            default_qty = clean_val(rec_88.get("field-88_4", ""))
            default_delivery_date = parse_date_safe(rec_88.get("field-88_2"))

            # 請求サブテーブル (field-89)
            sub_89 = r.get("field-89", [])
            item_89 = sub_89[0] if isinstance(sub_89, list) and len(sub_89) > 0 else {}
            rec_89 = item_89.get("record", item_89) if isinstance(item_89, dict) else {}
            sub_89_id = str(item_89.get("Id") or item_89.get("id") or rec_89.get("Id") or "").strip()

            # 各フィールドの値（@pocketのデータ優先、なければメインfield-5等のデフォルト）
            b_sales_date = parse_date_safe(rec_89.get("field-89_1")) or default_delivery_date or date.today()
            b_item_name = clean_val(rec_89.get("field-89_2")) or h_title
            b_qty = clean_val(rec_89.get("field-89_3")) or default_qty
            b_unit_price = clean_val(rec_89.get("field-89_4")) or h_unit_price_default # ★メインfield-5から流し込み
            b_memo = clean_val(rec_89.get("field-89_7"))
            b_mihon = clean_val(rec_89.get("field-89_12")) or default_mihon

            billing_flat_data.append({
                "更新": False,
                "得意先名": h_pub,
                "受注番号": h_ord_no,
                "売上日": b_sales_date,           # field-89_1
                "品名": b_item_name,             # field-89_2 (メインfield-13流し込み)
                "数量": b_qty,                   # field-89_3
                "販売単価": b_unit_price,        # field-89_4 (メインfield-5流し込み・更新可能)
                "備考": b_memo,                  # field-89_7
                "見本": b_mihon,                 # field-89_12 (明細field-88_8流し込み)
                "_recordId": rec_id,
                "_sub_89_id": sub_89_id
            })

        df_billing = pd.DataFrame(billing_flat_data)
        billing_display_cols = ["更新", "得意先名", "受注番号", "売上日", "品名", "数量", "販売単価", "備考", "見本"]
        df_billing_display = df_billing[[c for c in billing_display_cols if c in df_billing.columns]]

        edited_billing_df = st.data_editor(
            df_billing_display,
            num_rows="fixed",
            key="grid_billing_sys",
            use_container_width=True,
            column_config={
                "更新": st.column_config.CheckboxColumn("更新", required=True, help="チェックを入れた行の請求明細を@pocketに保存します"),
                "得意先名": st.column_config.TextColumn("得意先名", disabled=True),
                "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD", help="売上日（field-89_1）"),
                "品名": st.column_config.TextColumn("品名", help="品名（field-89_2）※メインfield-13から流し込み"),
                "数量": st.column_config.TextColumn("数量", help="数量（field-89_3）"),
                "販売単価": st.column_config.TextColumn("販売単価", help="販売単価（field-89_4）※メインfield-5から流し込み・更新可能"),
                "備考": st.column_config.TextColumn("備考", help="備考（field-89_7）"),
                "見本": st.column_config.TextColumn("見本", help="見本（field-89_12）※納品field-88_8から流し込み")
            }
        )

        st.markdown("---")
        if st.button("💾 変更した請求明細を @pocket に保存", type="primary", key="save_billing_btn"):
            update_b_rows = edited_billing_df[edited_billing_df["更新"] == True]
            if len(update_b_rows) == 0:
                st.warning("⚠️ 「更新」にチェックが入っている行がありません。")
            else:
                b_success_count = 0
                b_error_messages = []
                with st.spinner("@pocketへ請求明細を保存中..."):
                    for _, row in update_b_rows.iterrows():
                        r_id = clean_val(row.get("_recordId", ""))
                        ord_no = clean_val(row.get("受注番号", ""))
                        sub_89_id = clean_val(row.get("_sub_89_id", ""))
                        
                        if not r_id and ord_no:
                            search_url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
                            search_headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
                            search_params = {"query": f'field-2 = "{ord_no}"'}
                            try:
                                s_res = requests.get(search_url, headers=search_headers, params=search_params, timeout=10)
                                if s_res.status_code == 200:
                                    s_data = s_res.json()
                                    s_items = s_data.get("records", s_data.get("Data", s_data.get("Records", [])))
                                    if s_items and isinstance(s_items, list):
                                        first_item = s_items[0]
                                        rec_body_sub = first_item.get("record", {})
                                        r_id = str(first_item.get("Id") or first_item.get("id") or rec_body_sub.get("Id") or "").strip()
                            except Exception:
                                pass

                        if not r_id:
                            b_error_messages.append(f"受注番号 {ord_no}: レコードIDが取得できませんでした")
                            continue

                        sub_89_item = {
                            "record": {
                                "field-89_1": date_to_str(row.get("売上日")),
                                "field-89_2": clean_val(row.get("品名", "")),
                                "field-89_3": clean_val(row.get("数量", "")),
                                "field-89_4": clean_val(row.get("販売単価", "")), # ★ field-89_4へ保存
                                "field-89_7": clean_val(row.get("備考", "")),
                                "field-89_12": clean_val(row.get("見本", ""))
                            }
                        }
                        if sub_89_id:
                            sub_89_item["Id"] = sub_89_id

                        payload = {
                            "field-2": ord_no,
                            "field-89": [sub_89_item]
                        }
                        
                        ok, msg = update_pocket_record(r_id, payload)
                        if ok:
                            b_success_count += 1
                        else:
                            b_error_messages.append(f"受注番号 {ord_no}: {msg}")
                
                if b_success_count > 0:
                    st.success(f"✨ **{b_success_count} 件** の請求明細データを @pocket へ正常に保存しました！")
                    st.toast("✨ 請求明細の保存が完了しました！", icon="💰")
                if b_error_messages:
                    for err in b_error_messages:
                        st.error(f"❌ 保存エラー: {err}")
                if b_success_count > 0:
                    st.rerun()

else:
    st.warning("⚠️ 対象データが見つかりませんでした。上部の検索条件からデータを取得してください。")