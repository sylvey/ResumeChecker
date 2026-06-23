import pdfplumber  # pip install pdfplumber

text = ""
with pdfplumber.open("../../Training_Data/Resume/Bharath_Ganesh_Lead.pdf") as pdf:
    for page in pdf.pages:
        text += page.extract_text() or ""
print(text)