# PrintGuard

PrintGuard 是部署於 Windows Print Server 的列印監控與治理系統。它透過 Windows Print Spooler 原生 API 收集 Queue、AD／Windows 使用者、文件名稱、頁數、份數、彩色／黑白及單面／雙面資料，提供網頁查詢、政策稽核、CSV匯入與日／月報表。

## 目前功能

- 自動發現 Print Server 可見的所有列印佇列。
- 以 Windows Service 自動啟動並監督 Server與Native Agent。
- 保存成功、進行中與遭阻擋的列印工作至SQLite。
- 報表可切換使用者彙總、使用者／印表機明細及印表機彙總。
- 匯出使用者彙總與使用者／印表機明細CSV。
- 匯入SHARP設備工作CSV，支援檔案與工作層去重。
- 匯入成功／失敗原始檔分類保存30天。
- 每日集中Log並保留30天。
- 網頁設定黑白／彩色政策及設備判讀設定檔。

> 政策強制刪除目前有安全護欄，只允許名稱包含 `_test` 的測試Queue。正式Queue目前用於監控、報表與政策稽核。

## 專案結構

```text
PrintGuard
├─ server.py                    Dashboard、API、SQLite、報表、CSV匯入
├─ web/                         管理網頁
├─ native-agent/                Windows Print Spooler原生Agent（.NET）
├─ service-host/                Windows Service宿主與程序監督（.NET）
├─ deployment-service/          正式服務安裝、狀態與解除安裝腳本
├─ tests/                       Python API與政策測試
├─ SYSTEM_ARCHITECTURE_AND_CODE_GUIDE.md
├─ SERVICE_DEPLOYMENT.md
├─ DEVICE_CSV_IMPORT.md
├─ AUTO_DEVICE_PROFILE_PLAN.md
├─ RELEASES.md
└─ GITHUB_PUBLISHING.md
```

## 開發與測試

需求：

- Windows 10／11或Windows Server
- Python 3.10以上
- .NET SDK 10

啟動開發Server：

```powershell
python .\server.py
```

執行測試：

```powershell
python -m unittest discover -s tests -v
dotnet build .\native-agent\PrintGuard.NativeAgent.csproj -c Release
dotnet build .\service-host\PrintGuard.ServiceHost.csproj -c Release
```

## 文件

- [完整架構與程式碼責任](SYSTEM_ARCHITECTURE_AND_CODE_GUIDE.md)
- [Windows Service部署](SERVICE_DEPLOYMENT.md)
- [設備CSV匯入](DEVICE_CSV_IMPORT.md)
- [自動設備設定檔計畫](AUTO_DEVICE_PROFILE_PLAN.md)
- [r10／r11版本與切換](RELEASES.md)
- [GitHub發佈與資料保護](GITHUB_PUBLISHING.md)

## 資料與資安

正式執行資料位於 `C:\ProgramData\PrintGuard`，不應提交到GitHub。資料庫、Log、設備CSV、PaperCut報表、DEVMODE診斷檔、編譯輸出及安裝ZIP都已由 `.gitignore` 排除。

r11 LAN版沒有登入驗證或HTTPS，只能放在受信任公司Domain網路，不得將TCP 8080直接公開到Internet。

## 發行檔

自包含EXE與安裝ZIP不存放在原始碼儲存庫。內部備份位置及目前版本SHA-256記錄於 [RELEASES.md](RELEASES.md)；若透過GitHub發佈，請使用GitHub Releases Assets。

