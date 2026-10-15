import express from 'express';
import multer from 'multer';
import { createWorker } from 'tesseract.js';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 },
});

const PORT = process.env.PORT || 8000;

// Tesseract worker 初始化较慢，全局复用一个
let workerPromise;
function getWorker() {
  if (!workerPromise) {
    workerPromise = createWorker(['chi_sim', 'eng']);
  }
  return workerPromise;
}

app.get('/api/health', (req, res) => res.json({ status: 'ok' }));

app.post('/api/ocr', upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: '未收到文件' });
  try {
    const worker = await getWorker();
    const { data } = await worker.recognize(req.file.buffer);
    const text = (data.text || '').trim();
    res.json({
      filename: req.file.originalname,
      text: text || '未识别到文字',
      count: text ? text.split('\n').length : 0,
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// 复用同一套前端页面
app.use(express.static(path.join(__dirname, '..', 'static')));

app.listen(PORT, () => {
  console.log(`OCR (Node/Tesseract) 已启动: http://localhost:${PORT}`);
});
