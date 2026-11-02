# 3. @ポケット APIデータ取得関数（レスポンス確認用デバッグ版）
def fetch_pocket_records(start_date=None, end_date=None):
    url = f"{POCKET_BASE_URL}/api/apps/{APP_ID}/records"
    headers = {"X-At-Pocket-API-Key": POCKET_API_KEY, "Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            # 💡 ここで@pocketから返ってきた生のデータ構造を画面に表示して確認します
            st.write("▼ 【デバッグ】@pocketからの生レスポンス:", result)
            
            records = []
            if isinstance(result, list):
                records = result
            elif isinstance(result, dict):
                # 様々な可能性のあるキーを総当たりで探す
                records = result.get("Data", result.get("Records", result.get("Response", {}).get("Data", [])))
            
            if not records:
                st.warning("⚠️ レスポンスは200ですが、レコードの抽出ができませんでした。上の生レスポンスの中身を確認してみてください。")
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