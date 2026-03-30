def calculate_stock_value(stock_name, current_price, eps, avg_pe_low, avg_pe_mid, avg_pe_high):
    """
    計算股票的估價區間
    :param stock_name: 股票名稱
    :param current_price: 目前股價
    :param eps: 最近四季累積 EPS 或 預估 EPS
    :param avg_pe_low: 歷年低點本益比 (便宜價參考)
    :param avg_pe_mid: 歷年中位本益比 (合理價參考)
    :param avg_pe_high: 歷年高點本益比 (昂貴價參考)
    """
    
    cheap_price = eps * avg_pe_low
    fair_price = eps * avg_pe_mid
    expensive_price = eps * avg_pe_high
    
    print(f"--- {stock_name} 估價報告 ---")
    print(f"目前股價: {current_price}")
    print(f"最近 EPS: {eps}")
    print("-" * 25)
    print(f"便宜價 (PE {avg_pe_low}): {cheap_price:.2f}")
    print(f"合理價 (PE {avg_pe_mid}): {fair_price:.2f}")
    print(f"昂貴價 (PE {avg_pe_high}): {expensive_price:.2f}")
    print("-" * 25)
    
    # 判斷邏輯
    if current_price <= cheap_price:
        return "👉 結論：目前處於【便宜區間】，具備安全邊際。"
    elif current_price <= fair_price:
        return "👉 結論：目前處於【合理區間】，可分批佈局。"
    elif current_price <= expensive_price:
        return "👉 結論：目前處於【昂貴區間】，建議觀望或減碼。"
    else:
        return "👉 結論：【極度高估】，泡沫風險大！"

# --- 使用範例 ---
# 假設某股票目前 100 元，EPS 為 5 元
# 歷史便宜 PE 是 12 倍，合理 15 倍，昂貴 20 倍
result = calculate_stock_value(
    stock_name="範例股票", 
    current_price=100, 
    eps=5.0, 
    avg_pe_low=12, 
    avg_pe_mid=15, 
    avg_pe_high=20
)

print(result)
