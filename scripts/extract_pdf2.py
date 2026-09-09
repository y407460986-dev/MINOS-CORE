import os

import fitz

base = r"C:\Users\fgtan\Desktop\A018 试验大纲_20260625\A018 试验大纲_20260625"
folders = ["衬套", "镀锌机加件", "锻件", "销轴"]

for folder in folders:
    folder_path = os.path.join(base, folder)
    for fname in os.listdir(folder_path):
        if not fname.endswith(".pdf"):
            continue
        fpath = os.path.join(folder_path, fname)
        print("=" * 80)
        print(f"[{folder}] {fname}")
        print("=" * 80)
        doc = fitz.open(fpath)
        for i, page in enumerate(doc):
            text = page.get_text("text")
            if text.strip():
                print(f"--- Page {i+1} ---")
                print(text)
        doc.close()
        print()
