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
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

# ==========================================
# 1. ページ基本設定 ＆ 濃紺シックデザインCSS
# ==========================================
st.set_page_config(page_title="受注一覧表・管理システム", layout="wide", initial_sidebar_state="collapsed")

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

st.title("📊 受注一覧表日付入力 ＆ 付物納期・納品書・請求書")

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
# 4. 便利関数（データクリーニング・日付パース・ファイル出力）
# ==========================================
def clean_val(val):
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

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    output.seek(0)
    return output

# --- 受注一覧表のPDF生成（出版社ごとに自動改ページ＆分類表示） ---
def generate_order_pdf(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Normal"], fontName=FONT_NAME, fontSize=14, leading=16, textColor=colors.HexColor("#1E3A8A"))
    pub_header_style = ParagraphStyle("PubHeader", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=12, textColor=colors.HexColor("#1E3A8A"), spaceBefore=4, spaceAfter=4)
    header_style = ParagraphStyle("Header", parent=styles["Normal"], fontName=FONT_NAME, fontSize=7.5, leading=9, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontName=FONT_NAME, fontSize=7, leading=8.5, textColor=colors.HexColor("#1E293B"))

    elements = [
        Paragraph("<b>受注一覧表 ＆ 工程・納品・請求管理（顧客別・判型別・納期順）</b>", title_style),
        Spacer(1, 4),
        Paragraph(f"<font size=8 color='#64748B'>発行日: {date.today().strftime('%Y年%m月%d日')}</font>", styles["Normal"]),
        Spacer(1, 8),
    ]

    exclude_cols = ["更新", "_record_idx", "_sub_idx", "詳細", "単価", "納品日", "PL数", "見本数量", "在庫出荷", "配車区分", "納品", "売上日", "請求数量", "請求単価", "内見本数量", "請求", "出版社名"]
    target_cols = [c for c in df.columns if c not in exclude_cols]

    publishers = df["出版社名"].unique() if "出版社名" in df.columns else [""]
    for idx, pub in enumerate(publishers):
        if idx > 0:
            elements.append(PageBreak())
        
        pub_name_display = pub if pub else "（出版社名未設定）"
        elements.append(Paragraph(f"<b>■ 出版社: {pub_name_display} 御中</b>", pub_header_style))
        
        sub_df = df[df["出版社名"] == pub] if pub else df

        table_data = [[Paragraph(c, header_style) for c in target_cols]]
        for _, row in sub_df.iterrows():
            table_data.append([Paragraph(str(row[c]) if pd.notna(row[c]) else "", cell_style) for c in target_cols])

        total_width = 812
        col_widths = []
        for c in target_cols:
            if c in ["受注日", "納期", "折本日", "無線日", "三方日", "仕上日", "見本納入日", "入品日"]:
                col_widths.append(55)
            elif c == "書名":
                col_widths.append(115)
            elif c == "判型" or c == "納期上/中/下" or c == "急ぎ":
                col_widths.append(42)
            elif c == "ISBN":
                col_widths.append(48)
            elif c == "受注番号":
                col_widths.append(50)
            else:
                col_widths.append(40)
                
        current_total = sum(col_widths)
        if current_total != total_width and len(col_widths) > 0:
            diff = (total_width - current_total) / len(col_widths)
            col_widths = [w + diff for w in col_widths]

        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 付物明細一覧表のPDF生成 ---
def generate_accessory_pdf(df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Normal"], fontName=FONT_NAME, fontSize=14, leading=16, textColor=colors.HexColor("#1E3A8A"))
    header_style = ParagraphStyle("Header", parent=styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=10, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontName=FONT_NAME, fontSize=7.5, leading=9, textColor=colors.HexColor("#1E293B"))

    elements = [
        Paragraph("<b>付物明細一覧表（表・カバー・帯・カード）</b>", title_style),
        Spacer(1, 6),
        Paragraph(f"<font size=8 color='#64748B'>発行日: {date.today().strftime('%Y年%m月%d日')}</font>", styles["Normal"]),
        Spacer(1, 10),
    ]

    exclude_cols = ["更新", "_record_idx", "_sub_idx", "詳細"]
    target_cols = [c for c in df.columns if c not in exclude_cols]

    table_data = [[Paragraph(c, header_style) for c in target_cols]]
    for _, row in df.iterrows():
        table_data.append([Paragraph(str(row[c]) if pd.notna(row[c]) else "", cell_style) for c in target_cols])

    col_w = 772 / len(target_cols)
    t = Table(table_data, colWidths=[col_w] * len(target_cols), repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]))

    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 納品書PDF生成 ---
def generate_delivery_pdf(grouped_deliv_dict):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle("Title", parent=styles["Normal"], fontName=FONT_NAME, fontSize=20, leading=22, alignment=1, textColor=colors.HexColor("#1E3A8A"))
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=14, textColor=colors.HexColor("#333333"))
    th_style = ParagraphStyle("TH", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle("TD", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#1E293B"))
    td_right = ParagraphStyle("TDR", parent=td_style, alignment=2)

    elements = []
    
    for idx, ((d_date, car_div, pub_name, deliv_no), items) in enumerate(grouped_deliv_dict.items()):
        if idx > 0:
            elements.append(PageBreak())
            
        elements.append(Paragraph("<b>納 品 書</b>", title_style))
        elements.append(Spacer(1, 10))
        
        meta_data = [
            [
                Paragraph(f"<b>{pub_name if pub_name else '（出版社名未設定）'} 御中</b>", ParagraphStyle("CName", parent=h_style, fontSize=14, leading=16)),
                Paragraph("<b>(株)中永製本所</b><br/>埼玉県さいたま市岩槻区真福寺1400<br/>TEL 048-798-7377", ParagraphStyle("SInfo", parent=h_style, alignment=2))
            ],
            [
                Paragraph(f"納品書番号: {deliv_no}<br/>納品日: {d_date if d_date else '（未設定）'}<br/>配車区分: {car_div if car_div else '（未設定）'}", h_style),
                Paragraph(f"発行日: {date.today().strftime('%Y年%m月%d日')}", ParagraphStyle("DateInfo", parent=h_style, alignment=2))
            ]
        ]
        meta_table = Table(meta_data, colWidths=[400, 372])
        meta_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
        elements.append(meta_table)
        elements.append(Spacer(1, 10))
        
        elements.append(Paragraph("下記のとおり納品いたしました。", h_style))
        elements.append(Spacer(1, 6))
        
        table_data = [[
            Paragraph("書名 （製本数）", th_style),
            Paragraph("数量", th_style),
            Paragraph("PL数", th_style),
            Paragraph("見本数", th_style),
            Paragraph("備考", th_style)
        ]]
        
        for item in items:
            title_display = f"{item['書名']} （{item['製本数']}部）" if item['書名'] else '（書名なし）'
            table_data.append([
                Paragraph(title_display, td_style),
                Paragraph(f"{item['数量']} 部", td_right),
                Paragraph(f"{item['PL数']} PL", td_right),
                Paragraph(f"{item['見本数']} 部", td_right),
                Paragraph(item['備考'], td_style)
            ])
            
        d_table = Table(table_data, colWidths=[312, 100, 80, 80, 200])
        d_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ]))
        elements.append(d_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 請求書PDF生成 ---
def generate_invoice_pdf(grouped_invoice_dict, bank_info):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=portrait(A4), leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle("Title", parent=styles["Normal"], fontName=FONT_NAME, fontSize=20, leading=22, alignment=1, textColor=colors.HexColor("#1E3A8A"))
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=14, textColor=colors.HexColor("#333333"))
    th_style = ParagraphStyle("TH", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle("TD", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#1E293B"))
    td_right = ParagraphStyle("TDR", parent=td_style, alignment=2)

    elements = []
    
    for idx, (pub_name, items) in enumerate(grouped_invoice_dict.items()):
        if idx > 0:
            elements.append(PageBreak())
            
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
            p_str = clean_val(item["請求単価"])
            q_num = int(q_str) if q_str.isdigit() else 0
            try:
                p_num = float(p_str) if p_str else 0.0
            except ValueError:
                p_num = 0.0
            subtotal += q_num * p_num
        
        tax_amount = round(subtotal * 0.10)
        grand_total = subtotal + tax_amount

        elements.append(Paragraph("<b>請 求 書</b>", title_style))
        elements.append(Spacer(1, 10))
        
        meta_data = [
            [
                Paragraph(f"<b>{pub_name if pub_name else '（出版社名未設定）'} 御中</b>", ParagraphStyle("CName", parent=h_style, fontSize=14, leading=16)),
                Paragraph("<b>(株)中永製本所</b><br/>埼玉県さいたま市岩槻区真福寺1400<br/>TEL 048-798-7377", ParagraphStyle("SInfo", parent=h_style, alignment=2))
            ],
            [
                Paragraph("下記のとおりご請求申し上げます。", h_style),
                Paragraph(f"発行日: {date.today().strftime('%Y年%m月%d日')}", ParagraphStyle("DateInfo", parent=h_style, alignment=2))
            ]
        ]
        meta_table = Table(meta_data, colWidths=[300, 245])
        meta_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
        elements.append(meta_table)
        elements.append(Spacer(1, 8))
        
        summary_text = f"<b>売上期間:</b> {period_str}<br/><b>ご請求金額合計（税込）: ￥{grand_total:,.0f}</b> （うち消費税額等: ￥{tax_amount:,.0f}）"
        summary_table = Table([[Paragraph(summary_text, h_style)]], colWidths=[545])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F8F9FA")),
            ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#CED4DA")),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 10))
        
        table_data = [[
            Paragraph("納品日", th_style),
            Paragraph("書名", th_style),
            Paragraph("請求数量", th_style),
            Paragraph("請求単価", th_style),
            Paragraph("内見本数", th_style),
            Paragraph("金額", th_style),
            Paragraph("備考", th_style)
        ]]
        
        for item in items:
            q_str = clean_val(item["請求数量"])
            p_str = clean_val(item["請求単価"])
            q_num = int(q_str) if q_str.isdigit() else 0
            try:
                p_num = float(p_str) if p_str else 0.0
            except ValueError:
                p_num = 0.0
            line_total = q_num * p_num
            
            table_data.append([
                Paragraph(clean_val(item["売上日"]), td_style),
                Paragraph(item["書名"], td_style),
                Paragraph(f"{q_num} 部", td_right),
                Paragraph(f"￥{p_num:,.2f}", td_right),
                Paragraph(f"{clean_val(item['内見本数量'])} 部", td_right),
                Paragraph(f"￥{line_total:,.2f}", td_right),
                Paragraph(item["備考"], td_style)
            ])
            
        inv_table = Table(table_data, colWidths=[60, 140, 50, 60, 50, 75, 110])
        inv_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1,-1), 5),
            ("TOPPADDING", (0, 0), (-1,-1), 5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ]))
        elements.append(inv_table)
        elements.append(Spacer(1, 10))
        
        bank_text = f"<b>【お振込先口座】</b><br/>{bank_info['bank_name']} {bank_info['bank_branch']} ({bank_info['bank_type']}) {bank_info['bank_account']}<br/>口座名義: {bank_info['bank_holder']}"
        bank_table = Table([[Paragraph(bank_text, td_style)]], colWidths=[280])
        bank_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F9F9F9")),
            ("BOX", (0,0), (-1,-1), 1, colors.HexColor("#333333")),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ]))
        elements.append(bank_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# ==========================================
# 5. URLパラメータのチェック ＆ データ取得関数
# ==========================================
query_params = st.query_params
url_order_no = query_params.get("ord", None)

def fetch_pocket_records(start_date=None, end_date=None, target_order_no=None, target_publisher=None, date_field="field-1"):
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
                merged_body["_recordId"] = str(
                    item.get("Id") or 
                    item.get("recordId") or 
                    rec_body.get("Id") or 
                    rec_body.get("recordId") or 
                    item.get("ResultId") or ""
                ).strip()
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
                    raw_date_str = str(r.get(date_field, ""))
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
        default_start = date.today()
        default_end = default_start + timedelta(days=14)
        st.session_state["api_records"] = fetch_pocket_records(start_date=default_start, end_date=default_end, date_field="field-1")

# ==========================================
# 6. タブ構成の定義
# ==========================================
tab1, tab_accessory, tab2, tab3 = st.tabs([
    "📋 タブ1: 受注一覧表", 
    "🏷️ 付物明細（表・カバー・帯・カード）",
    "📦 タブ2: 納品書発行", 
    "📄 タブ3: 請求書発行（口座指定可）"
])

# ==========================================
# タブ1：受注一覧表 ＆ 工程日・納品・請求明細エディタ
# ==========================================
with tab1:
    st.header("📋 受注一覧表 ＆ 工程・納品・請求管理")
    
    if url_order_no:
        st.success(f"🔗 DBから受注番号 **{url_order_no}** のデータを起動しました！")
    
    with st.expander("🔍 検索条件の変更・絞り込みはこちら", expanded=bool(not url_order_no)):
        search_date_type = st.radio("📅 期間検索の基準を選択", ["受注日（field-1）", "納期（field-52）"], horizontal=True)
        target_date_field = "field-1" if "受注日" in search_date_type else "field-52"

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            default_start = date.today()
            default_end = default_start + timedelta(days=14)
            t1_start = st.date_input("期間（開始）", value=default_start, key="t1_s")
        with col_s2:
            t1_end = st.date_input("期間（終了）", value=default_end, key="t1_e")
        
        publisher_input = st.text_input("📖 出版社名で絞り込み（空欄なら期間内すべて）", value="", key="pub_ord")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            search_clicked = st.button("🔄 指定期間 ＆ 出版社名で検索", type="primary", key="btn_s1")
        
        st.markdown("---")
        direct_order_input = st.text_input("🏷️ 受注番号で直接検索（1件指定）", value=url_order_no if url_order_no else "", key="direct_ord")
        direct_search_clicked = st.button("🔍 受注番号で検索実行", key="btn_direct_s")

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

    if direct_search_clicked and direct_order_input:
        st.query_params["ord"] = direct_order_input
        with st.spinner(f"受注番号 {direct_order_input} を検索中..."):
            st.session_state["api_records"] = fetch_pocket_records(target_order_no=direct_order_input)
        st.rerun()

    api_records = st.session_state.get("api_records", None)
    
    if api_records is not None:
        if api_records:
            st.success(f"✨ 対象レコード **{len(api_records)} 件** を取得しました。")
            
            if "df_flat_session" not in st.session_state or st.session_state.get("last_len") != len(api_records):
                flat_data = []
                for record_idx, r in enumerate(api_records):
                    h_ord_no = clean_val(r.get("field-2", ""))
                    h_ord_date = parse_date_safe(r.get("field-1"))
                    h_due = parse_date_safe(r.get("field-52"))
                    h_pub = clean_val(r.get("field-8", ""))
                    h_title = clean_val(r.get("field-13", ""))
                    h_format = clean_val(r.get("field-23", ""))  # 判型 (field-23)
                    
                    # 新規追加フィールドの取得
                    val_102 = clean_val(r.get("field-102", ""))
                    if val_102 not in ["", "確定", "上旬", "中旬", "下旬"]:
                        val_102 = ""
                    
                    val_103 = clean_val(r.get("field-103", ""))
                    if val_103 not in ["", "急"]:
                        val_103 = ""

                    h_isbn = clean_val(r.get("field-93", ""))
                    h_qty = clean_val(r.get("field-4", ""))
                    h_price = clean_val(r.get("field-5", ""))
                    
                    rec_id = clean_val(r.get("_recordId", ""))
                    detail_url = f"{POCKET_BASE_URL}/apps/{APP_ID}/records/{rec_id}/detail" if rec_id and rec_id.lower() != "none" else ""
                    
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
                        
                        val_88_13 = clean_val(rec_88.get("field-88_13", ""))
                        if val_88_13 != "在庫から":
                            val_88_13 = ""

                        val_88_10 = clean_val(rec_88.get("field-88_10", ""))

                        flat_data.append({
                            "更新": False,
                            "_record_idx": record_idx,
                            "_sub_idx": i,  # ★ サブテーブル上の行インデックスを保持
                            "詳細": detail_url,
                            "受注番号": h_ord_no,
                            "受注日": h_ord_date,
                            "納期": h_due,
                            "納期上/中/下": val_102,
                            "急ぎ": val_103,
                            "出版社名": h_pub,
                            "書名": h_title,
                            "判型": h_format,
                            "ISBN": h_isbn,
                            "製本数": h_qty,
                            "単価": h_price,
                            "折本日": parse_date_safe(rec_90.get("field-90_3")),
                            "無線日": parse_date_safe(rec_90.get("field-90_4")),
                            "三方日": parse_date_safe(rec_90.get("field-90_5")),
                            "仕上日": parse_date_safe(rec_90.get("field-90_6")),
                            "見本納入日": parse_date_safe(rec_90.get("field-90_1")),
                            "入品日": parse_date_safe(rec_90.get("field-90_10")),
                            "備考": clean_val(rec_90.get("field-90_9", "")),
                            "納品日": parse_date_safe(rec_88.get("field-88_2")),
                            "納品数": clean_val(rec_88.get("field-88_4", "")),
                            "PL数": clean_val(rec_88.get("field-88_7", "")),
                            "見本数量": clean_val(rec_88.get("field-88_8", "")),
                            "在庫出荷": val_88_13,
                            "配車区分": val_88_10,
                            "納品": False,
                            "売上日": parse_date_safe(rec_89.get("field-89_1")),
                            "請求数量": clean_val(rec_89.get("field-89_3", "")),
                            "請求単価": clean_val(rec_89.get("field-89_4", "")),
                            "内見本数量": clean_val(rec_89.get("field-89_12", "")),
                            "備考_請求": clean_val(rec_89.get("field-89_7", "")),
                            "請求": False
                        })
                
                df_temp = pd.DataFrame(flat_data)
                # ★ 顧客別（出版社名）→ 判型別 → 納期順 のマルチソート
                sort_keys = ["出版社名", "判型", "納期"]
                sort_ascending = [True, True, True]
                available_sort_keys = [k for k in sort_keys if k in df_temp.columns]
                if available_sort_keys:
                    df_temp = df_temp.sort_values(
                        by=available_sort_keys, 
                        ascending=sort_ascending[:len(available_sort_keys)], 
                        na_position="last"
                    ).reset_index(drop=True)
                
                st.session_state["df_flat_session"] = df_temp
                st.session_state["last_len"] = len(api_records)

            # --- 一括選択・解除・保存ボタン（1行横並び） ---
            st.markdown("##### ⚡ 一括チェック操作 ＆ 保存")
            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns([1, 1, 1, 1, 1.3])
            with col_b1:
                if st.button("☑️ 更新 全選択", key="all_update_on"):
                    st.session_state["df_flat_session"]["更新"] = True
                    st.rerun()
            with col_b2:
                if st.button("ロ 更新 全解除", key="all_update_off"):
                    st.session_state["df_flat_session"]["更新"] = False
                    st.rerun()
            with col_b3:
                if st.button("☑️ 請求 全選択", key="all_invoice_on"):
                    st.session_state["df_flat_session"]["請求"] = True
                    st.rerun()
            with col_b4:
                if st.button("ロ 請求 全解除", key="all_invoice_off"):
                    st.session_state["df_flat_session"]["請求"] = False
                    st.rerun()
            with col_b5:
                top_save_clicked = st.button("💾 上書き保存", type="primary", key="btn_save_top")

            edited_flat_df = st.data_editor(
                st.session_state["df_flat_session"],
                num_rows="fixed",
                key="grid_flat_main",
                use_container_width=True,
                column_config={
                    "更新": st.column_config.CheckboxColumn("更新チェック", required=True, help="チェックを入れた行のデータを@pocketに上書き保存します"),
                    "_record_idx": None,
                    "_sub_idx": None,
                    "詳細": st.column_config.LinkColumn(
                        "🔗 @pocket詳細",
                        help="@pocketの該当データ画面へジャンプします",
                        display_text="📝 詳細を開く"
                    ),
                    "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                    "受注日": st.column_config.DateColumn("受注日", format="YYYY-MM-DD", disabled=True),
                    "納期": st.column_config.DateColumn("納期", format="YYYY-MM-DD", disabled=True),
                    "納期上/中/下": st.column_config.SelectboxColumn(
                        "納期上/中/下",
                        options=["", "確定", "上旬", "中旬", "下旬"],
                        help="納期の上旬・中旬・下旬・確定を選択します (field-102)"
                    ),
                    "急ぎ": st.column_config.SelectboxColumn(
                        "急ぎ",
                        options=["", "急"],
                        help="急ぎ案件の場合は「急」を選択します (field-103)"
                    ),
                    "出版社名": st.column_config.TextColumn("出版社名", disabled=True),
                    "書名": st.column_config.TextColumn("書名", disabled=True),
                    "判型": st.column_config.TextColumn("判型", disabled=True, help="判型 (field-23)"),
                    "ISBN": st.column_config.TextColumn("ISBN", disabled=True, help="ISBN番号 (field-93)"),
                    "製本数": st.column_config.TextColumn("製本数", disabled=True),
                    "単価": st.column_config.TextColumn("単価", disabled=True),
                    "折本日": st.column_config.DateColumn("折本日", format="YYYY-MM-DD"),
                    "無線日": st.column_config.DateColumn("無線日", format="YYYY-MM-DD"),
                    "三方日": st.column_config.DateColumn("三方日", format="YYYY-MM-DD"),
                    "仕上日": st.column_config.DateColumn("仕上日", format="YYYY-MM-DD"),
                    "見本納入日": st.column_config.DateColumn("見本納入日", format="YYYY-MM-DD", help="見本納入日（field-90_1）"),
                    "入品日": st.column_config.DateColumn("入品日", format="YYYY-MM-DD", help="入品日（field-90_10）"),
                    "備考": st.column_config.TextColumn("備考"),
                    "納品日": st.column_config.DateColumn("納品日", format="YYYY-MM-DD", help="納品日（field-88_2）"),
                    "納品数": st.column_config.TextColumn("納品数", help="納品数（field-88_4）"),
                    "PL数": st.column_config.TextColumn("PL数", help="PL数（field-88_7）"),
                    "見本数量": st.column_config.TextColumn("見本数量", help="見本数量（field-88_8）"),
                    "在庫出荷": st.column_config.SelectboxColumn(
                        "在庫出荷",
                        options=["", "在庫から"],
                        help="「空欄」または「在庫から」を選択します（field-88_13）",
                        required=False
                    ),
                    "配車区分": st.column_config.TextColumn("配車区分", help="配車区分を入力します（field-88_10）"),
                    "納品": st.column_config.CheckboxColumn("納品", help="チェックすると納品書発行の対象になります"),
                    "売上日": st.column_config.DateColumn("売上日", format="YYYY-MM-DD"),
                    "請求数量": st.column_config.TextColumn("請求数量", help="請求数量（field-89_3）"),
                    "請求単価": st.column_config.TextColumn("請求単価", help="請求単価（field-89_4）"),
                    "内見本数量": st.column_config.TextColumn("内見本数量", help="内見本数量（field-89_12）"),
                    "備考_請求": st.column_config.TextColumn("備考（請求）"),
                    "請求": st.column_config.CheckboxColumn("請求", help="チェックすると請求書発行の対象になります"),
                }
            )
            
            st.session_state["df_flat_session"] = edited_flat_df

            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                exclude_for_dl = ["単価", "納品日", "PL数", "見本数量", "在庫出荷", "配車区分", "納品", "売上日", "請求数量", "請求単価", "内見本数量"]
                df_excel_export = edited_flat_df.drop(columns=[c for c in exclude_for_dl if c in edited_flat_df.columns])
                excel_bytes_ord = to_excel_bytes(df_excel_export)
                st.download_button(
                    label="📥 受注一覧表を Excel でダウンロード",
                    data=excel_bytes_ord,
                    file_name=f"受注一覧表_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_excel_order"
                )
            with col_dl2:
                pdf_bytes_ord = generate_order_pdf(edited_flat_df)
                st.download_button(
                    label="🖨️ 受注一覧表を PDF でダウンロード",
                    data=pdf_bytes_ord,
                    file_name=f"受注一覧表_{date.today().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    key="dl_pdf_order"
                )

            selected_rows = edited_flat_df[edited_flat_df["更新"] == True]
            if selected_rows.empty:
                selected_rows = edited_flat_df.iloc[[0]]
            
            target_record_idx = int(selected_rows.iloc[0]["_record_idx"])
            sample_rec = api_records[target_record_idx]
            field_2 = clean_val(selected_rows.iloc[0]["受注番号"])
            field_1 = clean_val(selected_rows.iloc[0]["受注日"])
            field_8 = clean_val(selected_rows.iloc[0]["出版社名"])
            field_13 = clean_val(selected_rows.iloc[0]["書名"])
            field_4 = clean_val(selected_rows.iloc[0]["製本数"])
            field_5 = clean_val(selected_rows.iloc[0]["単価"])
            
            st.info(f"📌 現在選択中のレコード: **受注番号 {field_2} ({field_13})** （納品書・請求書発行に連動しています）")
                
        else:
            st.warning("⚠️ 該当するレコードが見つかりませんでした。")
            sample_rec = {}
            top_save_clicked = False
            field_2, field_1, field_8, field_13, field_4, field_5 = "", "", "", "", "", ""
    else:
        st.info("ℹ️ 検索条件を指定するか、DBから受注番号を指定してアクセスしてください。")
        sample_rec = {}
        top_save_clicked = False
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
            h_ord_no = clean_val(r.get("field-2", ""))
            h_ord_date = parse_date_safe(r.get("field-1"))
            h_due = parse_date_safe(r.get("field-52"))
            h_pub = clean_val(r.get("field-8", ""))
            h_title = clean_val(r.get("field-13", ""))
            
            rec_id = clean_val(r.get("_recordId", ""))
            detail_url = f"{POCKET_BASE_URL}/apps/{APP_ID}/records/{rec_id}/detail" if rec_id and rec_id.lower() != "none" else ""
            
            sub_91 = r.get("field-91", [])
            max_len_91 = len(sub_91) if isinstance(sub_91, list) and len(sub_91) > 0 else 1
            
            for i in range(max_len_91):
                item_91 = sub_91[i] if isinstance(sub_91, list) and len(sub_91) > i else {}
                rec_91 = item_91.get("record", item_91) if isinstance(item_91, dict) else {}
                
                acc_flat_data.append({
                    "更新": False,
                    "_record_idx": record_idx,
                    "_sub_idx": i,  # ★ サブテーブル上の行インデックスを保持
                    "詳細": detail_url,
                    "受注番号": h_ord_no,
                    "受注日": h_ord_date,
                    "納期": h_due,
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
        if "納期" in df_acc.columns:
            df_acc = df_acc.sort_values(by="納期", ascending=True, na_position="last").reset_index(drop=True)
        
        edited_acc_df = st.data_editor(
            df_acc,
            num_rows="fixed",
            key="grid_accessory_main",
            use_container_width=True,
            column_config={
                "更新": st.column_config.CheckboxColumn("更新チェック", required=True, help="チェックを入れた行の付物データを@pocketに上書き保存します"),
                "_record_idx": None,
                "_sub_idx": None,
                "詳細": st.column_config.LinkColumn(
                    "🔗 @pocket詳細",
                    help="@pocketの該当データ画面へジャンプします",
                    display_text="📝 詳細を開く"
                ),
                "受注番号": st.column_config.TextColumn("受注番号", disabled=True),
                "受注日": st.column_config.DateColumn("受注日", format="YYYY-MM-DD", disabled=True),
                "納期": st.column_config.DateColumn("納期", format="YYYY-MM-DD", disabled=True),
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

        st.markdown("---")
        col_dl3, col_dl4 = st.columns(2)
        with col_dl3:
            excel_bytes_acc = to_excel_bytes(edited_acc_df)
            st.download_button(
                label="📥 付物明細一覧表を Excel でダウンロード",
                data=excel_bytes_acc,
                file_name=f"付物明細一覧表_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel_acc"
            )
        with col_dl4:
            pdf_bytes_acc = generate_accessory_pdf(edited_acc_df)
            st.download_button(
                label="🖨️ 付物明細一覧表を PDF でダウンロード",
                data=pdf_bytes_acc,
                file_name=f"付物明細一覧表_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key="dl_pdf_acc"
            )

    else:
        st.warning("⚠️ 表示対象の受注データがありません。タブ1で検索を行ってください。")

# ==========================================
# 共通の上書き保存処理（_sub_idx 完全対応版）
# ==========================================
st.divider()

bottom_save_clicked = st.button("💾 チェックを入れたデータを データベース に一括上書き保存する", type="primary", key="btn_save_checked_all")

if top_save_clicked or bottom_save_clicked:
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
            
            # 親レコードのペイロード（field-102, field-103 を含む）
            record_payload = {
                "field-2": clean_val(original_rec.get("field-2", "")),
                "field-1": clean_val(original_rec.get("field-1", "")),
                "field-4": clean_val(original_rec.get("field-4", "")),
                "field-5": clean_val(original_rec.get("field-5", "")),
            }
            
            if source_tab == "flat" and not group_df.empty:
                # 同じレコード内の最初の行から新規フィールドの値を採用
                first_row = group_df.iloc[0]
                record_payload["field-102"] = clean_val(first_row.get("納期上/中/下", ""))
                record_payload["field-103"] = clean_val(first_row.get("急ぎ", ""))
            else:
                record_payload["field-102"] = clean_val(original_rec.get("field-102", ""))
                record_payload["field-103"] = clean_val(original_rec.get("field-103", ""))
            
            # --- 1. field-90 (工程日等) の更新 (_sub_idx 対応) ---
            orig_sub_90 = original_rec.get("field-90", [])
            sub90_list = copy.deepcopy(orig_sub_90)
            if source_tab == "flat":
                def date_to_str(val):
                    if pd.isna(val) or not val:
                        return ""
                    if isinstance(val, (date, datetime)):
                        return val.strftime("%Y-%m-%d")
                    parsed = parse_date_safe(val)
                    return parsed.strftime("%Y-%m-%d") if parsed else ""

                for _, row in group_df.iterrows():
                    s_idx = int(row.get("_sub_idx", 0))
                    while len(sub90_list) <= s_idx:
                        sub90_list.append({"record": {}})
                    
                    rec_dict = sub90_list[s_idx].get("record", {})
                    rec_dict["field-90_3"] = date_to_str(row["折本日"])
                    rec_dict["field-90_4"] = date_to_str(row["無線日"])
                    rec_dict["field-90_5"] = date_to_str(row["三方日"])
                    rec_dict["field-90_6"] = date_to_str(row["仕上日"])
                    rec_dict["field-90_1"] = date_to_str(row["見本納入日"])
                    rec_dict["field-90_10"] = date_to_str(row["入品日"])
                    rec_dict["field-90_9"] = clean_val(row["備考"])
                    sub90_list[s_idx]["record"] = rec_dict
                    
                record_payload["field-90"] = sub90_list
            else:
                record_payload["field-90"] = orig_sub_90

            # --- 2. field-88 (納品データ) の更新 (_sub_idx 対応) ---
            orig_sub_88 = original_rec.get("field-88", [])
            sub88_list = copy.deepcopy(orig_sub_88)
            if source_tab == "flat":
                for _, row in group_df.iterrows():
                    s_idx = int(row.get("_sub_idx", 0))
                    while len(sub88_list) <= s_idx:
                        sub88_list.append({"record": {}})
                    
                    deliv_date_str = ""
                    deliv_date_val = row["納品日"]
                    if pd.notna(deliv_date_val):
                        if isinstance(deliv_date_val, (date, datetime)):
                            deliv_date_str = deliv_date_val.strftime("%Y-%m-%d")
                        else:
                            parsed_d = parse_date_safe(deliv_date_val)
                            if parsed_d:
                                deliv_date_str = parsed_d.strftime("%Y-%m-%d")

                    rec_dict_88 = sub88_list[s_idx].get("record", {})
                    rec_dict_88["field-88_2"] = deliv_date_str
                    rec_dict_88["field-88_4"] = clean_val(row["納品数"]) or "0"
                    rec_dict_88["field-88_7"] = clean_val(row["PL数"]) or "0"
                    rec_dict_88["field-88_8"] = clean_val(row["見本数量"]) or "0"
                    rec_dict_88["field-88_13"] = clean_val(row["在庫出荷"])
                    rec_dict_88["field-88_10"] = clean_val(row["配車区分"])
                    sub88_list[s_idx]["record"] = rec_dict_88
                    
                record_payload["field-88"] = sub88_list
            else:
                record_payload["field-88"] = orig_sub_88

            # --- 3. field-89 (請求データ) の更新 (_sub_idx 対応) ---
            orig_sub_89 = original_rec.get("field-89", [])
            sub89_list = copy.deepcopy(orig_sub_89)
            if source_tab == "flat":
                for _, row in group_df.iterrows():
                    s_idx = int(row.get("_sub_idx", 0))
                    while len(sub89_list) <= s_idx:
                        sub89_list.append({"record": {}})
                    
                    sale_date_str = ""
                    sale_date_val = row["売上日"]
                    if pd.notna(sale_date_val):
                        if isinstance(sale_date_val, (date, datetime)):
                            sale_date_str = sale_date_val.strftime("%Y-%m-%d")
                        else:
                            parsed_s = parse_date_safe(sale_date_val)
                            if parsed_s:
                                sale_date_str = parsed_s.strftime("%Y-%m-%d")

                    rec_dict_89 = sub89_list[s_idx].get("record", {})
                    rec_dict_89["field-89_1"] = sale_date_str
                    rec_dict_89["field-89_3"] = clean_val(row["請求数量"]) or "0"
                    rec_dict_89["field-89_4"] = clean_val(row["請求単価"]) or "0"
                    rec_dict_89["field-89_12"] = clean_val(row["内見本数量"]) or "0"
                    rec_dict_89["field-89_7"] = clean_val(row["備考_請求"])
                    for k in ["field-89_5", "field-89_6"]:
                        rec_dict_89.pop(k, None)
                    sub89_list[s_idx]["record"] = rec_dict_89
                    
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

            # --- 4. field-91 (付物データ) の更新 (_sub_idx 対応) ---
            orig_sub_91 = original_rec.get("field-91", [])
            sub91_list = copy.deepcopy(orig_sub_91)
            if source_tab == "acc":
                for _, row in group_df.iterrows():
                    s_idx = int(row.get("_sub_idx", 0))
                    while len(sub91_list) <= s_idx:
                        sub91_list.append({"record": {}})
                    
                    rec_dict_91 = sub91_list[s_idx].get("record", {})
                    rec_dict_91["field-91_1"] = clean_val(row["表 日付"])
                    rec_dict_91["field-91_5"] = clean_val(row["カバー 日付"])
                    rec_dict_91["field-91_9"] = clean_val(row["カード 日付"])
                    rec_dict_91["field-91_13"] = clean_val(row["帯 日付"])
                    for k in ["field-91_2", "field-91_6", "field-91_10", "field-91_14"]:
                        rec_dict_91.pop(k, None)
                    sub91_list[s_idx]["record"] = rec_dict_91
                    
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
                default_start = date.today()
                default_end = default_start + timedelta(days=14)
                st.session_state["api_records"] = fetch_pocket_records(start_date=default_start, end_date=default_end, date_field="field-1")
            st.rerun()
            
        if fail_count > 0:
            st.error(f"❌ {fail_count} 件の保存に失敗しました。")

# ==========================================
# タブ2：納品書発行
# ==========================================
with tab2:
    st.header("📦 納品書発行")
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
        
        from collections import defaultdict
        grouped_deliv = defaultdict(list)
        for r in delivery_rows:
            key = (r["納品日"], r["配車区分"], r["出版社名"], r["納品書番号"])
            grouped_deliv[key].append(r)
            
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            excel_bytes_deliv = to_excel_bytes(df_preview)
            st.download_button(
                label="📥 納品書データを Excel でダウンロード",
                data=excel_bytes_deliv,
                file_name=f"納品書データ_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel_deliv"
            )
        with col_d2:
            pdf_bytes_deliv = generate_delivery_pdf(grouped_deliv)
            st.download_button(
                label="🖨️ 納品書を PDF でダウンロード",
                data=pdf_bytes_deliv,
                file_name=f"納品書_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key="dl_pdf_deliv"
            )

# ==========================================
# タブ3：請求書発行
# ==========================================
with tab3:
    st.header("📄 請求書発行（出版社別・口座指定可）")
    st.info("💡 タブ1の明細行で**「請求」**のチェックボックスにチェックが入っているデータを、**出版社名ごと**にまとめて請求書を作成します。")
    
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
                    "請求単価": clean_val(row.get("請求単価", "0")),
                    "内見本数量": clean_val(row.get("内見本数量", "0")),
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
        
        from collections import defaultdict
        grouped_invoice = defaultdict(list)
        for r in invoice_rows:
            grouped_invoice[r["出版社名"]].append(r)
            
        bank_info_dict = {
            "bank_name": bank_name,
            "bank_branch": bank_branch,
            "bank_type": bank_type,
            "bank_account": bank_account,
            "bank_holder": bank_holder
        }
        
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            excel_bytes_inv = to_excel_bytes(df_inv_preview)
            st.download_button(
                label="📥 請求書データを Excel でダウンロード",
                data=excel_bytes_inv,
                file_name=f"請求書データ_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel_inv"
            )
        with col_i2:
            pdf_bytes_inv = generate_invoice_pdf(grouped_invoice, bank_info_dict)
            st.download_button(
                label="🖨️ 請求書を PDF でダウンロード",
                data=pdf_bytes_inv,
                file_name=f"請求書_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                key="dl_pdf_inv"
            )