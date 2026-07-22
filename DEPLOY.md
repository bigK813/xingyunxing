# 幸运猩 · 上线部署指南

## 部署方式：Render（免费）

### 第一步：推送代码到 GitHub

```bash
cd "/Users/k/Documents/AI个人相关/幸运猩"
git add -A
git commit -m "v1.0: 幸运猩 彩票预测系统 - FastAPI + PWA"
git remote add origin https://github.com/bigK813/xingyunxing.git
git branch -M main
git push -u origin main
```

### 第二步：部署到 Render

1. 打开 render.com，用 GitHub 账号注册
2. 点击「New +」→「Web Service」
3. 连接你的 GitHub 仓库 `bigK813/xingyunxing`
4. 配置：
   - Name: `xingyunxing`
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
   - Free Instance Type: 勾选
5. 点击「Create Web Service」

部署后你会得到一个免费域名，如 `xingyunxing.onrender.com`

### 第三步：防止休眠（重要！）

Render 免费版 15 分钟无访问会自动休眠。

1. 去 uptimerobot.com 免费注册
2. 添加监控 → HTTP(s) → 输入你的 `.onrender.com` 地址
3. 监控间隔选 5 分钟

这样每 5 分钟自动 ping 一次，服务不会休眠。

### 第四步：数据初始化

首次访问时，服务会自动从体彩官网拉取历史数据（约 3 分钟）。
之后每天 21:35 和 22:00 自动增量更新。

也可手动访问 `/api/data/refresh` 触发刷新。

---

## 本地方案（开发用）

```bash
cd /Users/k/Documents/AI个人相关/幸运猩
python3 api_server.py
# 访问 http://localhost:8000
```

手机端（同一 WiFi）：`http://<电脑IP>:8000`
