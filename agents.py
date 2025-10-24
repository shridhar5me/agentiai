import io
import re
import json
from PyPDF2 import PdfReader
from openai import OpenAI

def extract_text_from_file(uploaded_file):
        if hasattr(uploaded_file, "read"):
            reader = PdfReader(uploaded_file)
        else:
            reader = PdfReader(io.BytesIO(uploaded_file))
        text_pages = []
        for page in reader.pages:
            text_pages.append(page.extract_text() or "")
        return "\n".join(text_pages)
    

def parse_resume_fields(text):
    out = {}
    if not text:
        return out
    m = re.search(r"Name[:\-\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    if m:
        out["name"] = m.group(1).strip()
    em = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if em:
        out["email"] = em.group(1)
    ph = re.search(r"(\+?\d[\d\-\s]{7,}\d)", text)
    if ph:
        out["phone"] = ph.group(1)
    skills = re.findall(r"(?:Skills|Technical Skills|Skillset)[:\-\s]*([\w\W]{0,200})", text, flags=re.IGNORECASE)
    if skills:
        s = skills[0]
        s = re.sub(r"\s+", " ", s)
        out["skills"] = [t.strip() for t in re.split(r"[,\n;]+", s) if t.strip()]
    exp = re.findall(r"(?:Experience|Work Experience|Professional Experience)[:\-\s]*([\w\W]{0,600})", text, flags=re.IGNORECASE)
    if exp:
        out["experience"] = exp[0].strip()
    return out

def safe_extract_json(text):
    if not text:
        return {}
    start = text.find("{")
    if start == -1:
        return {}
    end = text.rfind("}")
    if end == -1:
        return {}
    js = text[start:end+1]
    try:
        return json.loads(js)
    except Exception:
        js = js.replace("\n"," ")
        js = js.replace(",}", "}")
        js = js.replace(",]", "]")
        try:
            return json.loads(js)
        except Exception:
            return {}

def parse_openai_content(resp):
    try:
        first = resp.choices[0]
        if hasattr(first, "message"):
            msg = first.message
            if isinstance(msg, dict):
                return msg.get("content","").strip()
            return getattr(msg, "content","").strip() or ""
        if hasattr(first, "text"):
            return getattr(first, "text","").strip()
        return str(first)
    except Exception:
        try:
            return str(resp)
        except Exception:
            return ""

def call_openai_scorer(api_key, model, jd_text, resume_text, max_tokens=800):
    client = OpenAI(api_key=api_key)
    system = "You are an expert recruiter. Given a job description and a resume, return a JSON with fields candidate_name, match_score (0-100), years_experience_estimate, key_skills_matched, missing_skills, short_summary, fit_level. Return JSON only."
    user = f"JOB_DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}\n\nReturn the JSON."
    try:
        resp = client.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":user}], temperature=0.0, max_tokens=max_tokens)
        content = parse_openai_content(resp)
        parsed = safe_extract_json(content)
        if parsed:
            return parsed
        resp2 = client.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":user}], temperature=0.0, max_tokens=max_tokens)
        content2 = parse_openai_content(resp2)
        parsed2 = safe_extract_json(content2)
        if parsed2:
            return parsed2
        return {"match_score":0,"fit_level":"Low"}
    except Exception:
        return {"match_score":0,"fit_level":"Low"}

def call_openai_explainer(api_key, model, jd_text, resume_text, max_tokens=400):
    client = OpenAI(api_key=api_key)
    system = "You are an assistant that extracts highlights and a 1-2 sentence summary explaining fit. Return JSON with short_summary and highlights (array of strings). Return JSON only."
    user = f"JOB_DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}\n\nReturn the JSON."
    try:
        resp = client.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":user}], temperature=0.0, max_tokens=max_tokens)
        content = parse_openai_content(resp)
        parsed = safe_extract_json(content)
        if parsed:
            return parsed
        resp2 = client.chat.completions.create(model=model, messages=[{"role":"system","content":system},{"role":"user","content":user}], temperature=0.0, max_tokens=max_tokens)
        content2 = parse_openai_content(resp2)
        parsed2 = safe_extract_json(content2)
        if parsed2:
            return parsed2
        return {"short_summary":"","highlights":[]}
    except Exception:
        return {"short_summary":"","highlights":[]}
