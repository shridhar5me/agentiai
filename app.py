import streamlit as st
from pathlib import Path
import io
import csv
import json
import re
from typing import Tuple, List, Dict, Any
from openai import OpenAI
from PyPDF2 import PdfReader

st.set_page_config(page_title="Smart Resume Screener", layout="wide")

if "OPENAI_API_KEY" not in st.secrets:
    st.error("Add OPENAI_API_KEY in Streamlit Secrets.")
    st.stop()

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4")
client = OpenAI(api_key=OPENAI_API_KEY)

def extract_text_from_pdf(uploaded_file):
    try:
        if hasattr(uploaded_file, "read"):
            reader = PdfReader(uploaded_file)
        else:
            reader = PdfReader(io.BytesIO(uploaded_file))
        text_pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_pages.append(page_text)
        return "\n".join(text_pages)
    except Exception:
        try:
            raw = uploaded_file.getvalue()
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

def read_uploaded_file(f):
    if f is None:
        return ""
    name = getattr(f, "name", "")
    try:
        content_type = getattr(f, "type", "")
    except Exception:
        content_type = ""
    if "pdf" in content_type.lower() or name.lower().endswith(".pdf"):
        try:
            f.seek(0)
        except Exception:
            pass
        return extract_text_from_pdf(f)
    else:
        try:
            b = f.getvalue()
            if isinstance(b, bytes):
                return b.decode("utf-8", errors="ignore")
            return str(b)
        except Exception:
            return ""

def simple_extract_name(text):
    if not text:
        return "Unknown"
    m = re.search(r"Name[:\-\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    if m:
        return m.group(1).strip()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.search(r"[@\d]", line):
            continue
        if re.match(r"^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$", line):
            return line.strip()
        return line.strip()
    return "Unknown"

def safe_extract_json_from_text(text):
    if not text:
        return {}
    start = text.find("{")
    if start == -1:
        return {}
    end = text.rfind("}")
    if end == -1 or end <= start:
        return {}
    json_text = text[start:end + 1]
    try:
        return json.loads(json_text)
    except Exception:
        cleaned = re.sub(r",\s*}", "}", json_text)
        cleaned = re.sub(r",\s*\]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            return {}

def parse_openai_response_content(resp):
    try:
        first_choice = resp.choices[0]
        if hasattr(first_choice, "message"):
            msg = first_choice.message
            if isinstance(msg, dict):
                return msg.get("content", "").strip()
            return getattr(msg, "content", "").strip() or ""
        if hasattr(first_choice, "text"):
            return getattr(first_choice, "text", "").strip()
        return str(first_choice)
    except Exception:
        try:
            return str(resp)
        except Exception:
            return ""

def call_openai_evaluator(jd_text, resume_text, model=OPENAI_MODEL, max_tokens=800):
    system = (
        "You are an expert recruiter/hiring manager. Given a job description and a resume, "
        "produce a compact JSON object with fields: candidate_name, match_score (0-100), "
        "years_experience_estimate, key_skills_matched (array), missing_skills (array), "
        "short_summary (1-2 sentences), and fit_level (High/Medium/Low). Return JSON only."
    )
    user_prompt = f"""JOB_DESCRIPTION:\n{jd_text}\n\nRESUME:\n{resume_text}\n\nRespond with the JSON as specified."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        content = parse_openai_response_content(resp)
        parsed = safe_extract_json_from_text(content)
        if not parsed:
            resp2 = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            content2 = parse_openai_response_content(resp2)
            parsed = safe_extract_json_from_text(content2)
        if not parsed:
            return {
                "candidate_name": simple_extract_name(resume_text)[:60],
                "match_score": 0,
                "years_experience_estimate": 0,
                "key_skills_matched": [],
                "missing_skills": [],
                "short_summary": "Could not parse response.",
                "fit_level": "Low",
            }
        try:
            ms = int(parsed.get("match_score", 0))
            ms = max(0, min(100, ms))
        except Exception:
            ms = 0
        try:
            years = parsed.get("years_experience_estimate", 0)
            if isinstance(years, str) and years.isdigit():
                years = int(years)
            else:
                years = float(years) if str(years).replace(".", "", 1).isdigit() else 0
        except Exception:
            years = 0
        parsed["match_score"] = ms
        parsed["years_experience_estimate"] = years
        parsed["key_skills_matched"] = parsed.get("key_skills_matched") or []
        parsed["missing_skills"] = parsed.get("missing_skills") or []
        parsed["candidate_name"] = parsed.get("candidate_name") or simple_extract_name(resume_text)[:60]
        parsed["short_summary"] = parsed.get("short_summary", "") or ""
        parsed["fit_level"] = parsed.get("fit_level", "Low")
        return parsed
    except Exception as e:
        return {
            "candidate_name": simple_extract_name(resume_text)[:60],
            "match_score": 0,
            "years_experience_estimate": 0,
            "key_skills_matched": [],
            "missing_skills": [],
            "short_summary": f"OpenAI call failed: {str(e)}",
            "fit_level": "Low",
        }

st.title("Smart Resume Screener Agent (HR Tech) 👩‍💼🤖")
st.markdown("Upload a Job Description (PDF/TXT) and multiple resumes. App evaluates and ranks candidates using OpenAI.")

with st.sidebar:
    st.header("Instructions")
    st.write("1. Upload Job Description\n2. Upload resumes\n3. Click Evaluate\n4. Download report")

col1, col2 = st.columns([3, 1])
with col1:
    jd_file = st.file_uploader("Upload Job Description (PDF/TXT)", type=["pdf", "txt"], key="jd")
    resumes = st.file_uploader("Upload Resumes (PDF/TXT)", type=["pdf", "txt"], accept_multiple_files=True, key="resumes")
    use_samples = st.checkbox("Use sample resumes (if present)", value=True)
    evaluate = st.button("Evaluate Resumes")
with col2:
    max_tokens = st.slider("Max tokens", 200, 2000, 800, 100)
    st.write("Model: " + OPENAI_MODEL)

sample_dir = Path(__file__).parent / "sample_resumes"
sample_files = []
if sample_dir.exists() and use_samples:
    for p in sample_dir.glob("*.txt"):
        sample_files.append(p)

if evaluate:
    st.info("Starting evaluation...")
    jd_text = read_uploaded_file(jd_file) if jd_file else ""
    resumes_data = []
    if resumes:
        for r in resumes:
            txt = read_uploaded_file(r)
            resumes_data.append((r.name, txt))
    if use_samples and sample_files:
        for p in sample_files:
            with open(p, "r", encoding="utf-8") as f:
                resumes_data.append((p.name, f.read()))
    if not resumes_data:
        st.error("No resumes to evaluate.")
    else:
        progress_bar = st.progress(0)
        results = []
        total = len(resumes_data)
        for idx, (name, txt) in enumerate(resumes_data, start=1):
            with st.spinner(f"Evaluating {name} ({idx}/{total})..."):
                out = call_openai_evaluator(jd_text, txt, model=OPENAI_MODEL, max_tokens=max_tokens)
                out["source_file"] = name
                if not out.get("candidate_name"):
                    out["candidate_name"] = simple_extract_name(txt)
                results.append(out)
            progress_bar.progress(int((idx / total) * 100))
        results_sorted = sorted(results, key=lambda x: int(x.get("match_score", 0)), reverse=True)
        st.subheader("Ranked Candidates")
        for r in results_sorted:
            st.markdown(f"**{r.get('candidate_name','Unknown')}** — Score: **{r.get('match_score',0)}** — Fit: **{r.get('fit_level','Unknown')}**")
            st.write(f"Experience: {r.get('years_experience_estimate',0)} years")
            st.write("Key skills: " + (", ".join(r.get("key_skills_matched", [])) or "None"))
            st.write("Missing skills: " + (", ".join(r.get("missing_skills", [])) or "None"))
            st.write("Summary: " + (r.get("short_summary", "") or ""))
            st.write("---")
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["candidate_name", "source_file", "match_score", "fit_level", "years_experience_estimate", "key_skills_matched", "missing_skills", "short_summary"])
        for r in results_sorted:
            writer.writerow([
                r.get("candidate_name", ""),
                r.get("source_file", ""),
                r.get("match_score", ""),
                r.get("fit_level", ""),
                r.get("years_experience_estimate", ""),
                ";".join(r.get("key_skills_matched", [])),
                ";".join(r.get("missing_skills", [])),
                r.get("short_summary", "")
            ])
        st.download_button("Download CSV Report", data=csv_buffer.getvalue(), file_name="resume_ranking.csv", mime="text/csv")
