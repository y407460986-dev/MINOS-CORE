import pdfplumber

files = [
    (
        r"C:\Users\fgtan\Desktop\A018 试验大纲_20260625\A018 试验大纲_20260625"
        r"\衬套\BZJ01004500_001_AB_BUSHING_DVPR.pdf",
        "衬套",
    ),
    (
        r"C:\Users\fgtan\Desktop\A018 试验大纲_20260625\A018 试验大纲_20260625"
        r"\镀锌机加件\宇通机加件镀锌_试验DVP&R.pdf",
        "镀锌机加件",
    ),
    (
        r"C:\Users\fgtan\Desktop\A018 试验大纲_20260625\A018 试验大纲_20260625"
        r"\销轴\BZJ01010100_HINGE_PIN_试验DVP&R.pdf",
        "销轴1",
    ),
    (
        r"C:\Users\fgtan\Desktop\A018 试验大纲_20260625\A018 试验大纲_20260625"
        r"\销轴\BZJ01010200_HINGE_PIN_试验DVP&R.pdf",
        "销轴2",
    ),
]

for fpath, label in files:
    print("=" * 80)
    print(f"[{label}] {fpath.split(chr(92))[-1]}")
    print("=" * 80)
    with pdfplumber.open(fpath) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                print(f"--- Page {i+1} ---")
                print(text)
    print()
