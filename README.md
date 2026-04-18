# 🚀 TW.stock.app | 專屬台股與 ETF 投資管家

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/Built_with-Streamlit-FF4B4B.svg)
![Data](https://img.shields.io/badge/Data-Fugle%20%7C%20FinMind%20%7C%20Yahoo-success.svg)
![Database](https://img.shields.io/badge/Database-Google_Sheets-34A853.svg)

> **「從行情追蹤到現金流規劃，打造存股族的終極儀表板。」**
> 
> [cite_start]TW.stock.app 是一個基於 Python Streamlit 開發的個人化投資系統 [cite: 1][cite_start]。不僅提供即時的台股與 ETF 報價，更專注於**精準的配息預估**、**歷史回測**與**資產視覺化** [cite: 53, 171][cite_start]。透過雲端資料庫同步，讓你的投資策略與資產配置隨時跟著你走 [cite: 1, 4]。

🔗 **線上系統連結：** [👉 點擊此處立即體驗 TW.stock.app](https://ez-stock-fhedmdgxgniyeyhfxexy3m.streamlit.app/)

---

## ✨ 核心亮點功能 (Core Features)

### 📊 1. 智慧型 ETF & 個股深度解析
* [cite_start]**🤖 智慧配息頻率偵測**：系統自動分析歷史除息日，精準判斷標的為「月配、季配、半年配或年配」 [cite: 54, 55, 56]。
* [cite_start]**🛡️ 健壯的數據演算法**：針對配息停發或漏發的情況，系統會自動進行 0 填充校正，確保年化報酬率試算之精準度 [cite: 58, 59]。
* **💰 投資估值試算器**：
    * [cite_start]**個股**：輸入 EPS 與自訂本益比 (PE)，秒速換算參考價位 [cite: 72, 79]。
    * [cite_start]**ETF**：提供 5%、7%、10% 殖利率對應的「便宜、合理、昂貴」三段價格分析 [cite: 96, 98, 99]。

### 💼 2. 投資組合與「月月配」現金流管理
* [cite_start]**☁️ 雲端無縫同步**：結合 Google Sheets 資料庫與個人帳號登入系統，個人組合與關注清單自動雲端存檔 [cite: 1, 11, 16]。
* [cite_start]**📥 靈活資料匯入**：支援 CSV 檔案一鍵匯入投資清單，快速建立數位資產帳本 [cite: 133, 134]。
* [cite_start]**📅 自動化領息排程月曆**：系統依據台股慣例自動推算發放日 [cite: 62][cite_start]，並精準扣除 **2.11% 二代健保補充保費**（單筆股利 > 2 萬時），呈現最真實的實領金額 [cite: 101, 102]。
* [cite_start]**🥧 資產配置與報酬分析**：自動化圖表顯示各持股市值比重 [cite: 171][cite_start]，並實時計算投資組合的總報酬率與平均殖利率 [cite: 147, 169]。

### ⚔️ 3. 實戰策略與規劃工具
* [cite_start]**🌐 全球市場戰情室**：即時監控 S&P 500、費半、美 10 年債殖利率及台指期全等關鍵指標，掌握市場趨勢 [cite: 193, 204, 205, 206, 207]。
* [cite_start]**🔮 存股未來財富複利試算**：設定初始資金與月投入額，輕鬆模擬長期資產成長軌跡與未來的每月被動收入 [cite: 106, 107, 120]。
* [cite_start]**🥊 ETF 終極 PK 擂台**：支援兩檔標的並排對比價格、漲幅、配息頻率與實質殖利率 [cite: 121, 131]。
* [cite_start]**⭐ 即時行情關注清單**：打造專屬股票池，畫面自動刷新最新報價與日漲跌幅數據 [cite: 182, 186]。

---

## 🛠️ 系統技術架構 (Tech Stack)

[cite_start]本系統採用多源數據備援架構，確保數據的穩定性與正確性 [cite: 45]：

| 模組分類 | 使用技術 / 服務 | 說明 |
| :--- | :--- | :--- |
| **前端與 UI** | `Streamlit` | [cite_start]快速建構互動式 Web 應用程式介面 [cite: 1]。 |
| **資料庫** | `Google Sheets` | [cite_start]透過 `gspread` 實現輕量級雲端數據讀寫 [cite: 1, 2]。 |
| **即時報價引擎** | `Fugle API` | [cite_start]提供台股盤中極低延遲的即時報價與總量數據 [cite: 42]。 |
| **歷史配息引擎** | `FinMind`, `Yahoo`, `HiStock` | [cite_start]**三引擎聯集備援**。FinMind 為主，Yahoo 破除封鎖，HiStock 專解債券 ETF 爬蟲 [cite: 45, 47, 50]。 |
| **數據視覺化** | `Plotly Express` | [cite_start]負責高質感的互動式圓餅圖與趨勢圖渲染 [cite: 171]。 |

---

## ⚠️ 免責聲明 (Disclaimer)
1. **僅供參考**：本系統 (TW.stock.app) 所提供之所有數據皆透過第三方開源 API 或網路爬蟲取得，僅供**個人研究參考**，不構成任何形式之投資建議。
2. [cite_start]**資料風險**：受限於第三方資料來源穩定度，本系統**不保證**資訊的即時性。如發現數據異常，請以各金融機構或臺灣證券交易所官方公告為準 [cite: 68]。
3. **自負盈虧**：投資必然伴隨風險。使用者基於本系統資訊所做出之任何決策，開發者概不負任何法律責任。

---

## 👨‍💻 關於開發者
**Ez開發** 致力於將繁瑣的金融數據，轉化為簡單、直覺的投資輔助工具。如果你覺得這個系統對你有幫助，歡迎分享給身邊的存股族朋友！
