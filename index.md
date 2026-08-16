# RPI_BUTTON_TOUCH

智慧遠端電子鎖系列專案的終端控制系統

## 專案特點

* 專為 Raspberry Pi 與 Raspberry Pi OS 設計
* 使用 Python、FastAPI 與 Uvicorn 建立控制服務
* 透過 APScheduler 定期向遠端伺服器取得新任務
* 執行任務後會回報進度、執行結果與錯誤資訊
* 透過 GPIO 接腳與外接電路觸發公寓電鎖
* 可使用 JSON 自訂 GPIO、等待時間及多步驟動作流程
* 提供本機網頁介面，可查看裝置連線狀態及手動測試觸發

## 關聯專案

* [BTN_CTRL_CENTER](https://stdai0a10.github.io/btn_ctrl_center/) ([Github](https://github.com/stdai0a10/btn_ctrl_center))  
  一套整合網頁控制、多人空間管理與實體裝置執行的 IoT 控制中心
* [BTN_CTRL_OPS](https://stdai0a10.github.io/btn_ctrl_ops/) ([Github](https://github.com/stdai0a10/btn_ctrl_ops))  
  以 Docker Compose 整合核心專案、Cloudflare Tunnel 與 Traefik，打造易於部署與管理的容器化服務架構
* [RPI_BUTTON_TOUCH](https://stdai0a10.github.io/rpi_button_touch/) ([Github](https://github.com/stdai0a10/rpi_button_touch)) (當前專案)  
  Raspberry Pi 裝置端控制服務，整合遠端任務排程與 GPIO 硬體控制，負責接收遠端任務並透過 GPIO 驅動電子鎖
