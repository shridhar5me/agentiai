import streamlit as st
from pathlib import Path
import io
import csv
import re
from typing import List, Tuple, Dict, Any
from openai import OpenAI
from PyPDF2 import PdfReader
from agents import extract_text_from_file, parse_resume_fields, call_openai_scorer, call_openai_explainer
from utils import sanitize_text, chunk_text

st.set_page_config(page_title="Smart Resume Screener - MultiAgent", layout="wide")

if "OPENAI_API_KEY" not in st.secrets:
    st.error("Add OPENAI_API_KEY in Streamlit Secrets.")
    st.stop()

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4")
client = OpenAI(api_key=OPENAI_API_KEY)

st.title("Smart Resume Screener - MultiAgent")
col1, col2 = st.columns([3,1])
with col1:
    jd_file = st.file_uploader("Upload Job Description (PDF/TXT)", type=["pdf","txt"], key="jd")
    resumes = st.file_uploader("Upload Resumes (PDF/TXT)", type=["pdf","txt"], accept_multiple_files=True, key="resumes")
    evaluate = st.button("Evaluate Resumes")
with col2:
    st.write("Options")
    max_tokens = st.slider("Max tokens", 200, 2000, 800, 100)
    st.write("Model: " + OPENAI_MODEL)

inbox_dir = Path(__file__).parent / "inbox_resumes"
inbox_dir.mkdir(exist_ok=True)

def read_uploaded(f):
    if f is None:
        return ""
    name = getattr(f, "name", "")
    ctype = getattr(f, "type", "")
    if "pdf" in ctype.lower() or name.lower().endswith(".pdf"):
        try:
            f.seek(0)
        except Exception:
            pass
        return extract_text_from_file(f)
    else:
        try:
            b = f.getvalue()
            if isinstance(b, bytes):
                return b.decode("utf-8", errors="ignore")
            return str(b)
        except Exception:
            return ""

def run_evaluation(jd_text, resumes_data):
    results = []
    total = len(resumes_data)
    progress = st.progress(0)
    for idx, (name, txt) in enumerate(resumes_data, start=1):
        with st.spinner(f"Extractor Agent parsing {name} ({idx}/{total})"):
            parsed = parse_resume_fields(txt)
        with st.spinner(f"Scorer Agent evaluating {name} ({idx}/{total})"):
            score = call_openai_scorer(OPENAI_API_KEY, OPENAI_MODEL, jd_text, txt, max_tokens)
        with st.spinner(f"Explainer Agent summarizing {name} ({idx}/{total})"):
            explanation = call_openai_explainer(OPENAI_API_KEY, OPENAI_MODEL, jd_text, txt, max_tokens)
        out = {
            "candidate_name": parsed.get("name") or parsed.get("email") or name,
            "source_file": name,
            "match_score": score.get("match_score", 0),
            "fit_level": score.get("fit_level", "Low"),
            "years_experience_estimate": score.get("years_experience_estimate", 0),
            "key_skills_matched": score.get("key_skills_matched", []),
            "missing_skills": score.get("missing_skills", []),
            "short_summary": explanation.get("short_summary", ""),
            "highlights": explanation.get("highlights", [])
        }
        results.append(out)
        progress.progress(int(idx/total*100))
    return sorted(results, key=lambda x: int(x.get("match_score",0)), reverse=True)

if evaluate:
    jd_text = read_uploaded(jd_file) if jd_file else ""
    resumes_data = []
    if resumes:
        for r in resumes:
            resumes_data.append((r.name, read_uploaded(r)))

    for p in inbox_dir.glob("*.txt"):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            resumes_data.append((p.name, f.read()))
    if not resumes_data:
        st.error("No resumes to evaluate.")
    else:
        results_sorted = run_evaluation(jd_text, resumes_data)
        st.subheader("Ranked Candidates")
        for r in results_sorted:
            st.markdown(f"**{r.get('candidate_name','Unknown')}** — Score: **{r.get('match_score',0)}** — Fit: **{r.get('fit_level','Unknown')}**")
            st.write(f"Experience: {r.get('years_experience_estimate',0)} years")
            st.write("Key skills: " + (", ".join(r.get("key_skills_matched", [])) or "None"))
            st.write("Missing skills: " + (", ".join(r.get("missing_skills", [])) or "None"))
            st.write("Summary: " + (r.get("short_summary", "") or ""))
            if r.get("highlights"):
                st.write("Highlights:")
                for h in r.get("highlights", []):
                    st.markdown(f"- {h}")

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["candidate_name","source_file","match_score","fit_level","years_experience_estimate","key_skills_matched","missing_skills","short_summary"])
        for r in results_sorted:
            writer.writerow([
                r.get("candidate_name",""),
                r.get("source_file",""),
                r.get("match_score",""),
                r.get("fit_level",""),
                r.get("years_experience_estimate",""),
                ";".join(r.get("key_skills_matched", [])),
                ";".join(r.get("missing_skills", [])),
                r.get("short_summary","")
            ])
        st.download_button("Download CSV Report", data=csv_buffer.getvalue(), file_name="resume_ranking.csv", mime="text/csv")
