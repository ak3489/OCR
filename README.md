![OCR 界面预览](index.png)

# OCR 图片文字识别

批量识别图片中的文字（中文 / 英文），支持两种用法：

- **命令行版**：`ocr.py`，读取 `F:\OCR` 目录下的图片，结果写入 `全部结果.txt`。
- **网页版**：`ocr_web.py`，浏览器里拖拽上传图片即可识别、复制、导出（本 README 重点）。

识别引擎使用 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)（PP-OCRv6 模型）。

---

## 一、目录结构

```
F:\OCR\
├─ ocr.py              # 原命令行脚本
├─ ocr_web.py          # 网页版后端（FastAPI + PaddleOCR）
├─ requirements.txt    # Python 依赖
├─ static\
│   └─ index.html      # 网页前端（上传、结果展示、导出）
└─ node-version\       # Node 替代方案（Tesseract.js，可选）
    ├─ server.js
    └─ package.json
```

---

## 二、本地运行

### 0. 前置条件（重要）

从 git 克隆下来后，**必须先安装依赖**，否则 `python ocr.py` 会报 `ModuleNotFoundError: No module named 'paddleocr'`。

```powershell
# 在项目目录下执行，安装全部依赖
python -m pip install -r requirements.txt
```

依赖说明：

- `paddleocr` + `paddlepaddle`：OCR 识别引擎（命令行版和网页版都需要）。
- `fastapi`、`uvicorn`、`python-multipart`：仅网页版需要。
- 要求 Python 3.9 ~ 3.12。

> 如果只想跑命令行版，也可只装引擎：`python -m pip install paddleocr paddlepaddle`。

### 1. 命令行版

```powershell
python ocr.py
```

- 默认读取**脚本所在目录**下的图片（不再是写死的路径），识别后生成 `全部结果.txt`。
- 也可指定图片目录：`python ocr.py D:\我的图片`
- 若未安装依赖，脚本会直接提示：`缺少依赖，请先安装：python -m pip install -r requirements.txt`。

### 2. 网页版（推荐，中文准确率最高）

```powershell
# 安装依赖（首次）
python -m pip install -r requirements.txt

# 启动服务
python ocr_web.py
```

浏览器打开 <http://localhost:8000> ，拖入图片 → 点击「开始识别」→ 复制或「导出全部 txt」。

> 首次运行会自动下载 PP-OCR 模型（约几十 MB）到 `C:\Users\<你>\.paddlex\official_models\`，之后离线可用。

---

## 三、部署到服务器

网页版是一个标准的 FastAPI 服务，用**单进程**跑即可（PaddleOCR 实例不是线程安全的，代码里已用锁串行化请求，因此不要开多 worker）。

### 方案 A：Linux + systemd（最常用）

```bash
# 1. 拉代码 / 上传到服务器，例如 /opt/ocr
cd /opt/ocr

# 2. 建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 前台试跑
python ocr_web.py        # 监听 0.0.0.0:8000
```

创建 `/etc/systemd/system/ocr.service`：

```ini
[Unit]
Description=OCR Web Service
After=network.target

[Service]
WorkingDirectory=/opt/ocr
ExecStart=/opt/ocr/venv/bin/python ocr_web.py
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ocr
sudo systemctl status ocr
```

### 方案 B：Docker（环境最省心）

`Dockerfile`：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "ocr_web.py"]
```

```bash
docker build -t ocr-web .
docker run -d --name ocr -p 8000:8000 --restart unless-stopped ocr-web
```

### 方案 C：Nginx 反向代理 + HTTPS

外部访问用 Nginx 转发到本机 8000，顺便加域名和证书：

```nginx
server {
    listen 80;
    server_name ocr.example.com;

    client_max_body_size 20m;   # 允许大图上传

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;   # OCR 较慢，超时调大
    }
}
```

再用 certbot 申请免费证书：`sudo certbot --nginx -d ocr.example.com`。

### 服务器注意事项

- **只跑单 worker**：`uvicorn.run(app, ...)` 默认单进程即可；不要用 `--workers 4`，会各自加载一份模型并可能并发冲突。
- **内存**：模型常驻内存约 1~2 GB，服务器至少 2 GB 内存。
- **首次启动慢**：第一次要下载模型，可先在本地跑一次把 `.paddlex\official_models` 目录一起打包上传，实现离线部署。
- **并发**：当前实现是串行识别（加锁）。要高并发需要跑多个独立进程 + 队列（如 `redis` + `rq`/`celery`），成本更高，一般自用不需要。
- **安全**：对公网开放建议加登录鉴权，或在 Nginx 层用 `auth_basic` 限制访问。

---

## 四、可以用 Node 代替 Python 吗？

**可以，但不推荐用 Node 直接替代 PaddleOCR**，原因：

| 方案 | 引擎 | 中文准确率 | 依赖 |
|------|------|-----------|------|
| Python（本项目默认） | PaddleOCR PP-OCRv6 | 高（中文场景最佳） | paddlepaddle，较重 |
| **Node 替代** | Tesseract.js | 一般（中文明显弱于 Paddle） | 纯 npm，安装简单 |

- PaddleOCR 是 Python 库，Node 里没有等价的高精度实现。
- Node 里做 OCR 通常用 **Tesseract.js**（纯 JS/WASM）或 **onnxruntime-node + PP-OCR ONNX 模型**。前者简单但中文差，后者要自己拼装检测+识别+字典流程，工作量大。
- 如果你只是想**避免安装 Python / 部署更轻**，可以用 Node 版；如果在意中文识别质量，保留 Python。

### Node 替代方案（已提供）

```powershell
cd node-version
npm install
npm start
```

浏览器打开 <http://localhost:8000>，用的是同一套前端页面（`..\static\index.html`），后端换成 Tesseract.js。

> Node 版复用前端，接口同样是 `POST /api/ocr`（字段名 `file`），所以前端无需改动。
> 若中文效果不理想，建议继续用 Python 版。

---

## 五、常见问题

- **端口被占用**：改 `ocr_web.py` 里的 `port=8000`，或用 `uvicorn ocr_web:app --port 9000`。
- **识别慢**：CPU 识别单张约 1~3 秒，属正常；高并发请参考「服务器注意事项」。
- **模型下载失败**：手动下载模型放到 `C:\Users\<你>\.paddlex\official_models\` 对应目录即可离线。
- **换语言**：`ocr_web.py` 里 `PaddleOCR(lang='ch')` 可改成 `en`、`japan`、`korean` 等。
