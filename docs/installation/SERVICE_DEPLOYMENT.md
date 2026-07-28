# PrintGuard Windows Service 部署

## 建議部署方式

正式部署改用單一 `PrintGuard-Setup.exe`。它會自動完成檔案安裝、服務建立、失敗復原設定、Domain 防火牆規則與解除安裝註冊，不需要使用者操作 CMD 或 PowerShell。詳細步驟請見 [INSTALLATION_AND_UNINSTALL_GUIDE.md](INSTALLATION_AND_UNINSTALL_GUIDE.md)。

原有 `deployment-service` PowerShell 腳本保留作為開發、疑難排解與相容性工具，不再是一般管理者的主要安裝方式。

## 架構

`PrintGuard.ServiceHost.exe` 是向 Windows Service Control Manager 註冊的原生服務程序。它負責啟動及監控：

- `PrintGuard.Server.exe`：Dashboard、API、SQLite、報表及設備CSV匯入。
- `PrintGuard.NativeAgent.exe`：Windows Print Spooler監控及測試佇列政策執行。

Service Host 接受停止與關機控制，在服務停止時終止子程序。任一子程序意外退出後5秒自動重啟。SCM另外設定服務程序失敗時的三階段恢復。

## Windows 設定

- 服務名稱：`PrintGuard`
- 顯示名稱：`PrintGuard 列印治理服務`（安裝腳本以 Unicode 字碼建立，避免 Windows PowerShell 5.1 在不同系統語系下產生亂碼）
- 啟動方式：延遲自動啟動
- 執行帳號：`LocalSystem`
- 依賴服務：`Spooler`
- r10 Dashboard：只監聽 `127.0.0.1:8080`，不建立 LAN 防火牆規則
- r11 Dashboard：監聽 `0.0.0.0:8080`；本機使用 `http://127.0.0.1:8080`，公司 Domain 網路使用 `http://PrintServer-IP:8080`
- r11 防火牆：只放行 Domain Profile 的 TCP 8080，Private／Public Profile 不放行

## 安裝

完整解壓縮 Service 安裝 ZIP，在 Print Server 執行：

`Install-PrintGuard-Service.cmd`

CMD會要求系統管理員權限，接著移除舊排程、複製程式、建立服務、設定恢復、啟動服務及檢查API。r11另外建立 Domain Profile 防火牆規則，解除安裝r11時一併移除。

目前版本選擇：

| 版本 | 使用情境 | 連線方式 |
|---|---|---|
| r10 本機限定版 | 只讓登入 Print Server 的管理者操作 | `http://127.0.0.1:8080` |
| r11 LAN版 | 讓公司 Domain 網路內的管理電腦操作 | `http://PrintServer-IP:8080` |

r10升級r11可直接覆蓋安裝。r11回復r10後，應依 [版本紀錄](../RELEASES.md) 移除 r11 建立的防火牆規則；兩者都保留相同資料庫與歷史資料。

## 資料保留

升級及預設解除安裝不刪除：

- `C:\ProgramData\PrintGuard\data\printguard.db`
- `C:\ProgramData\PrintGuard\logs`
- `C:\ProgramData\PrintGuard\imports`

CSV 自動匯入後會依結果移至 `imports\processed` 或 `imports\failed`；兩者皆保留30天後自動清除。

## 限制

正式印表機目前用於監控與報表。為避免未驗證規則影響正式環境，政策刪除仍只允許名稱包含 `_test` 的佇列。

v0.12.1 Dashboard 已提供管理者登入驗證，但目前沒有內建 HTTPS，僅供受信任公司網域網路使用；不可將 TCP 8080 直接公開到 Internet。
