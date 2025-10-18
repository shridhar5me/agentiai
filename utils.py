import re
def extract_email(text):
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else ""

def extract_phone(text):
    m = re.search(r"(\+?\d[\d\-\s]{7,}\d)", text)
    return m.group(0) if m else ""
