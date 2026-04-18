# 🚀 TW.stock.app | 專屬台股與 ETF 投資管家

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/Built_with-Streamlit-FF4B4B.svg)
![Data](https://img.shields.io/badge/Data-Fugle%20%7C%20FinMind%20%7C%20Yahoo-success.svg)
![Database](https://img.shields.io/badge/Database-Google_Sheets-34A853.svg)

> **「從全球行情追蹤到精準現金流規劃，打造存股族的終極雲端儀表板。」**
> 
> [cite_start]**TW.stock.app** 是一個專為台股投資人設計的自動化決策系統。我們解決了資料更新不齊與計算不夠細膩的痛點，整合即時報價、多源配息數據與雲端存檔功能，讓您的投資組合不僅是數字，更是隨手可得的精準現金流預估。 [cite: 1, 8, 9, 10]

🔗 **線上系統連結：** [👉 點擊此處立即體驗 TW.stock.app](https://ez-stock-fhedmdgxgniyeyhfxexy3m.streamlit.app/)

---

## ✨ 核心亮點功能 (Core Features)

### 📊 1. 智慧型 ETF & 個股深度解析
* [cite_start]**🤖 健壯的配息演算法**：系統自動分析歷史除息日，精準判斷「月、季、半年或年配」 [cite: 53, 54, 55, 56][cite_start]。若遇配息停發，系統將自動補 0 校正，確保年化殖利率試算不失真 [cite: 58, 59]。
* [cite_start]**💰 多維度估值位階**：除了個股 EPS 合理價換算外 [cite: 72, 78, 79][cite_start]，ETF 模組更提供 5%、7%、10% 殖利率對應的「便宜、合理、昂貴」價格參考 [cite: 96, 98, 99]。

### 💼 2. 投資組合與「月月配」現金流管理
* [cite_start]**🔒 雲端隱私安全同步**：具備個人化帳號登入系統，結合 Google Sheets 資料庫實現資產雲端同步 [cite: 2, 11, 12, 16][cite_start]。更支援 **CSV 檔案一鍵匯入** [cite: 132, 133, 134]，快速建立個人化數位帳本。
* [cite_start]**📅 自動化領息排程月曆**：系統依據台股慣例自動推算發放日 [cite: 62, 63, 174][cite_start]，並根據持有張數**精準扣除 2.11% 二代健保補充保費** [cite: 101, 102]，呈現最真實的實領金額。
* [cite_start]**📈 資產配置視覺化**：自動化 Plotly 圓餅圖呈現各持股佔比 [cite: 170, 171][cite_start]，配合「圓環報酬率看板」直覺顯示總投資損益與平均殖利率 [cite: 147, 149, 151, 169]。

### ⚔️ 3. 全球戰情室與規劃工具
* [cite_start]**🌐 全球市場監控**：同步追蹤 S&P 500、費半、美 10 年債殖利率及台指期全等關鍵指標 [cite: 190, 204, 205, 206, 207]，全方位掌握大盤趨勢。
* [cite_start]**🔮 未來財富複利試算**：設定初始資金、每月投入與目標殖利率，模擬長期資產成長軌跡，並預估期滿後的「每月被動收入」 [cite: 106, 107, 110, 115, 120]。
* [cite_start]**🥊 ETF 終極 PK 擂台**：支援兩檔代碼並排對比價格、漲幅與實質殖利率，輔助最佳標的篩選 [cite: 121, 122, 131]。

---

## 🛠️ 技術架構與數據防禦 (Tech Stack)

本系統採用多源數據備援架構，確保數據穩定性：

| 模組分類 | 使用技術 / 服務 | 說明 |
| :--- | :--- | :--- |
| **前端與 UI** | `Streamlit` | [cite_start]快速建構互動式 Web 應用程式介面 [cite: 1]。 |
| **資料庫** | `Google Sheets` | [cite_start]透過 `gspread` 與 GCP Service Account 實現雲端數據讀寫 [cite: 1, 2]。 |
| **即時報價引擎** | `Fugle (富果) API` | [cite_start]提供台股盤中極低延遲的即時報價與總量數據 [cite: 42, 43, 44]。 |
| **歷史配息引擎**| `FinMind`, `Yahoo`, `HiStock` | [cite_start]**三引擎聯集備援**，確保債券 ETF 與各類標的配息資料完整性 [cite: 45, 47, 50, 52]。 |

---

## ⚠️ 免責聲明 (Disclaimer)
1. [cite_start]**僅供參考**：本系統所提供之所有報價、股息預估及合理價試算皆透過第三方開源 API 或網路爬蟲取得，僅供個人研究參考，絕不構成投資建議 [cite: 68]。
2. [cite_start]**資料風險**：受限於第三方資料來源穩定度，本系統不保證資訊之絕對即時性。如發現數據異常，請以交易所官方公告為準 [cite: 174]。
3. **自負盈虧**：投資必然伴隨風險，使用者基於本系統資訊所做出之決策與損益，本系統開發者概不負責。

---

## 👨‍💻 關於開發者
**Ez開發** 致力於將繁瑣的金融數據轉化為直覺的投資生產力。如果您覺得這個系統有幫助，歡迎分享給身邊的存股戰友！
