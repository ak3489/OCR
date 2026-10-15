import os
os.environ['FLAGS_enable_pir_api'] = '0'

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

app = FastAPI(title="OCR 网页版")

ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=True,
    lang='ch',
    enable_mkldnn=False,
)

img_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

# PaddleOCR 实例非线程安全，用锁串行化识别请求
ocr_lock = threading.Lock()


def run_ocr(image_path: Path) -> list[str]:
    with ocr_lock:
        result = ocr.predict(str(image_path))
    texts = []
    for res in result:
        data = res.json if hasattr(res, 'json') else res
        if isinstance(data, dict):
            for text in data.get('res', {}).get('rec_texts', []):
                if text and str(text).strip():
                    texts.append(str(text).strip())
    return texts


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ocr")
async def api_ocr(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in img_exts:
        return {"filename": file.filename, "text": "", "error": "不支持的图片格式"}

    tmp_path = Path(tempfile.gettempdir()) / f"ocr_{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(await file.read())
    try:
        texts = run_ocr(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "filename": file.filename,
        "text": "\n".join(texts) if texts else "未识别到文字",
        "count": len(texts),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
