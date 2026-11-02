# 3. APIデータ取得関数（レスポンス構造の徹底デバッグ版）
def fetch_pocket_records():
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        st.write(f"📡 APIステータスコード: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # 💡 ルートのJSON構造をそのまま画面に表示してキーを確認します
            st.write("▼ 【超重要デバッグ】@pocketからの生JSONデータ（ルート構造）:", result)
            
            # 万が一、Response配下にデータがあるパターンなども全網羅して探索
            raw_items = []
            if isinstance(result, list):
                raw_items = result
            elif isinstance(result, dict):
                # 考えられるキーをすべてチェック
                for key in ["Data", "Records", "Response", "Values", "Items", "Rows"]:
                    if key in result:
                        val = result[key]
                        if isinstance(val, list):
                            raw_items = val
                            st.write(f"ℹ️ キー '{key}' の中にリストを発見しました（件数: {len(val)}件）")
                            break
                        elif isinstance(val, dict) and "Data" in val:
                            raw_items = val["Data"]
                            break
                # それでも見つからなければ、辞書のキー自体を表示
                if not raw_items:
                    st.write("⚠️ リストが見つかりませんでした。辞書のキー一覧:", list(result.keys()))
            
            parsed_records = []
            for item in raw_items:
                # "record" オブジェクトがある場合は中身を取り出す
                rec_body = item.get("record", {})
                if not rec_body and isinstance(item, dict):
                    rec_body = item
                
                rec_body["_recordId"] = item.get("recordId", item.get("Id", ""))
                rec_body["_accessEditUrl"] = item.get("accessEditUrl", "")
                parsed_records.append(rec_body)
            
            if parsed_records:
                st.success(f"✨ 有効なレコードを {len(parsed_records)} 件抽出しました！")
                return parsed_records
            else:
                st.warning("⚠️ パース後のレコードが0件です。上の「生JSONデータ」の中身を確認してください。")
        else:
            st.error(f"❌ APIエラー: {response.text}")
    except Exception as e:
        st.error(f"🚨 通信エラー: {e}")
    
    # フォールバック用モックデータ
    today_str = str(datetime.now().date())
    return [{
        "field-2": "200001",
        "field-1": "2020-01-06",
        "field-8": "株式会社 勁草書房",
        "field-13": "実務成年後見法",
        "field-4": "2000",
        "field-5": "59.39"
    }]