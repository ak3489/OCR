import os
os.environ['FLAGS_enable_pir_api'] = '0'

import sys
from pathlib import Path
import re

try:
    from paddleocr import PaddleOCR
except ImportError:
    print('缺少依赖，请先安装：python -m pip install -r requirements.txt')
    sys.exit(1)

# ==================== 配置区 ====================
# 如果想把所有结果写到同一个文件，请填写文件名，例如：
# OUTPUT_TXT = "全部结果.txt"
# 如果不填写（保持 None），就会按图片名称分别生成 txt
OUTPUT_TXT = "全部结果.txt"
# ================================================

def natural_key(path):
    """实现数字自然排序，让 1.jpg、2.jpg、10.jpg 按正确顺序排列"""
    name = path.stem
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', name)]

ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=True,
    lang='ch',
    enable_mkldnn=False
)

work_dir = Path(__file__).resolve().parent
if len(sys.argv) > 1:
    work_dir = Path(sys.argv[1]).resolve()
img_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

# 先收集所有图片，再按数字顺序排序
img_files = [p for p in work_dir.iterdir() if p.suffix.lower() in img_exts]
img_files.sort(key=natural_key)

print('开始识别...\n')

all_results = []

for img_path in img_files:
    print(f'正在识别: {img_path.name}')
    
    result = ocr.predict(str(img_path))
    
    texts = []
    for res in result:
        data = res.json if hasattr(res, 'json') else res
        if isinstance(data, dict):
            rec_texts = data.get('res', {}).get('rec_texts', [])
            for text in rec_texts:
                if text and str(text).strip():
                    texts.append(str(text).strip())
    
    content = '\n'.join(texts) if texts else '未识别到文字'
    
    if OUTPUT_TXT:
        all_results.append(f'===== {img_path.name} =====\n{content}\n')
    else:
        txt_path = img_path.with_suffix('.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'已保存 → {txt_path.name}\n')

if OUTPUT_TXT:
    output_path = work_dir / OUTPUT_TXT
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_results))
    print(f'全部结果已保存到 → {output_path.name}')

print('全部完成！')