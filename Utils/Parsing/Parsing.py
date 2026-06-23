import pdfplumber  # pip install pdfplumber

text = ""
with pdfplumber.open("resume.pdf") as pdf:
    for page in pdf.pages:
        text += page.extract_text() or ""
print(text)