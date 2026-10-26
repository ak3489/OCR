import os
os.environ['FLAGS_enable_pir_api'] = '0'

import re
import statistics
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from paddleocr import PaddleOCR

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# ==================== 模型配置区 ====================
# 留空的项 = 用 paddleocr 当前版本的默认模型。想换模型时填模型名即可，例如：
# DET_MODEL = "PP-OCRv5_server_det"
# REC_MODEL = "PP-OCRv5_server_rec"
LANG = 'ch'          # 语言，见 README
OCR_VERSION = None   # None=默认(最新)，也可填 'PP-OCRv5' / 'PP-OCRv4' / 'PP-OCRv3'
DET_MODEL = ''       # 文字检测模型名，留空用默认
REC_MODEL = ''       # 文字识别模型名，留空用默认
ORIENT_MODEL = ''    # 文字方向分类模型名，留空用默认
# 也可用本地模型目录（离线/自制模型），填写后优先于上面的模型名
DET_MODEL_DIR = ''   # 例: r"D:\models\my_det"
REC_MODEL_DIR = ''   # 例: r"D:\models\my_rec"
ORIENT_MODEL_DIR = ''  # 例: r"D:\models\my_orient"
# ====================================================

app = FastAPI(title="OCR 网页版")

_ocr_kwargs = dict(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=True,
    lang=LANG,
    enable_mkldnn=False,
)
if OCR_VERSION:
    _ocr_kwargs['ocr_version'] = OCR_VERSION
if DET_MODEL:
    _ocr_kwargs['text_detection_model_name'] = DET_MODEL
if REC_MODEL:
    _ocr_kwargs['text_recognition_model_name'] = REC_MODEL
if ORIENT_MODEL:
    _ocr_kwargs['textline_orientation_model_name'] = ORIENT_MODEL
if DET_MODEL_DIR:
    _ocr_kwargs['text_detection_model_dir'] = DET_MODEL_DIR
if REC_MODEL_DIR:
    _ocr_kwargs['text_recognition_model_dir'] = REC_MODEL_DIR
if ORIENT_MODEL_DIR:
    _ocr_kwargs['textline_orientation_model_dir'] = ORIENT_MODEL_DIR

ocr = PaddleOCR(**_ocr_kwargs)


def resolve_model_info() -> dict:
    """返回当前实际使用的模型信息，用于网页展示。"""
    try:
        det, rec = ocr._get_ocr_model_names(LANG, OCR_VERSION)
    except Exception:
        det, rec = None, None
    det = DET_MODEL or det or '默认'
    rec = REC_MODEL or rec or '默认'
    info = {
        "lang": LANG,
        "ocr_version": OCR_VERSION or "默认(最新)",
        "det": det,
        "rec": rec,
    }
    if ORIENT_MODEL:
        info["orient"] = ORIENT_MODEL
    return info

img_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

# PaddleOCR 实例非线程安全，用锁串行化识别请求
ocr_lock = threading.Lock()


def cleanup_temp_files():
    """启动时清理上次进程异常退出可能残留的临时图片。"""
    tmp_dir = Path(tempfile.gettempdir())
    for p in tmp_dir.glob("ocr_*"):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


cleanup_temp_files()


def run_ocr(image_path: Path) -> list[tuple[str, list[float] | None]]:
    """识别图片，返回 (文本, 行框[x1,y1,x2,y2]) 列表，按阅读顺序。"""
    with ocr_lock:
        result = ocr.predict(str(image_path))
    lines = []
    for res in result:
        data = res.json if hasattr(res, 'json') else res
        if not isinstance(data, dict):
            continue
        res_data = data.get('res', {})
        texts = res_data.get('rec_texts', [])
        boxes = res_data.get('rec_boxes') or []
        for i, text in enumerate(texts):
            text = str(text).strip()
            if not text:
                continue
            box = boxes[i] if i < len(boxes) else None
            lines.append((text, [float(v) for v in box] if box is not None else None))
    return lines


_ASCII_TAIL = re.compile(r'[0-9A-Za-z]$')
_ASCII_HEAD = re.compile(r'^[0-9A-Za-z]')


def merge_paragraphs(lines: list[tuple[str, list[float]]]) -> str:
    """按行框位置把逐行结果接排成段落：段内不断行，段间换行。

    判为段落边界的依据：行首缩进、行距突增、上一行明显没写到右边距。
    """
    gaps = [max(0.0, b[1] - a[3]) for (_, a), (_, b) in zip(lines, lines[1:])]
    med_gap = statistics.median(gaps) if gaps else 0.0
    right = max(box[2] for _, box in lines)

    out = lines[0][0]
    prev = lines[0][1]
    for text, box in lines[1:]:
        h = max(1.0, min(prev[3] - prev[1], box[3] - box[1]))
        if abs(box[1] - prev[1]) < 0.5 * h:  # 同一行被切成多块
            out += (" " if box[0] - prev[2] > h else "") + text
        elif (box[0] - prev[0] > h                     # 行首缩进
              or box[1] - prev[3] > med_gap + 0.5 * h  # 行距突增
              or prev[2] < right - 2.5 * h):           # 上一行明显没写满
            out += "\n" + text
        else:
            sep = " " if _ASCII_TAIL.search(out) and _ASCII_HEAD.match(text) else ""
            out += sep + text
        prev = box
    return out


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/model")
def api_model():
    return resolve_model_info()


@app.post("/api/ocr")
async def api_ocr(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in img_exts:
        return {"filename": file.filename, "text": "", "error": "不支持的图片格式"}

    tmp_path = Path(tempfile.gettempdir()) / f"ocr_{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(await file.read())
    try:
        lines = run_ocr(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    raw = "\n".join(text for text, _ in lines)
    if lines and all(box for _, box in lines):
        reflow = merge_paragraphs(lines)
    else:
        reflow = raw

    return {
        "filename": file.filename,
        "text": raw or "未识别到文字",
        "text_reflow": reflow or "未识别到文字",
        "count": len(lines),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
