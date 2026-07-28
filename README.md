# PrintGuard

PrintGuard 是部署於 Windows Print Server 的列印監控與治理系統。它透過 Windows Print Spooler 原生 API 收集 Queue、AD／Windows 使用者、文件名稱、頁數、份數、彩色／黑白及單面／雙面資料，提供網頁查詢、政策稽核、CSV匯入與日／月報表。

公開總覽不需要登入，只顯示今日列印統計與設備狀態數量；列印工作、使用者、文件、報表與所有管理設定仍需管理員登入。

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
├─ deployment-service/          開發及相容性服務管理腳本
├─ installer/                   單一 PrintGuard-Setup.exe 建置設定
├─ tests/                       Python API與政策測試
├─ docs/                        架構、安裝、操作、開發及舊版文件
├─ README.md                    專案入口
└─ SECURITY.md                  資安政策
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

- [文件總覽](docs/README.md)
- [完整架構與程式碼責任](docs/architecture/SYSTEM_ARCHITECTURE_AND_CODE_GUIDE.md)
- [Windows Service部署](docs/installation/SERVICE_DEPLOYMENT.md)
- [安裝、升級與完整解除安裝](docs/installation/INSTALLATION_AND_UNINSTALL_GUIDE.md)
- [設備CSV匯入](docs/operations/DEVICE_CSV_IMPORT.md)
- [自動設備設定檔計畫](docs/development/AUTO_DEVICE_PROFILE_PLAN.md)
- [版本與切換紀錄](docs/RELEASES.md)
- [GitHub發佈與資料保護](docs/development/GITHUB_PUBLISHING.md)

## 資料與資安

正式執行資料位於 `C:\ProgramData\PrintGuard`，不應提交到GitHub。資料庫、Log、設備CSV、PaperCut報表、DEVMODE診斷檔、編譯輸出及安裝ZIP都已由 `.gitignore` 排除。

v0.13.0 提供免登入的唯讀公開總覽；使用者、文件、工作明細、報表及設定仍受管理者登入保護。目前尚未內建 HTTPS，只能放在受信任公司 Domain 網路，不得將 TCP 8080 直接公開到 Internet。

## 發行檔

目前測試版本：**v0.13.0**

- [下載 PrintGuard v0.13.0](https://github.com/aow00170mm-hub/PrintGuard/releases/tag/v0.13.0)
- 安裝檔：`PrintGuard-Setup-0.13.0.exe`
- SHA-256：`BDD5B5B23BF231297A20E85CA5A48BE0CD1FD8A3213FA49BF9A191C292A55CA7`
- v0.11.0 與 v0.12.1 仍保留於 GitHub Releases，可供測試或回復評估。

自包含 EXE 不存放在原始碼目錄，而是放在 GitHub Releases Assets。完整版本紀錄、私人備份位置及 SHA-256 請見 [版本紀錄](docs/RELEASES.md)。

