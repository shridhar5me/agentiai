import streamlit as st
import tempfile, csv, io, re, os, json
from pathlib import Path
import openai
from PyPDF2 import PdfReader

st.set_page_config(page_title="Smart Resume Screener", layout="wide")

# --- Secrets and model config ---
try:
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("OpenAI API key not found in Streamlit secrets. Add OPENAI_API_KEY in your app's Settings → Secrets.")
    st.stop()

openai.api_key = OPENAI_API_KEY
MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4") if isinstance(st.secrets, dict) else "gpt-4"

st.title("Smart Resume Screener Agent (HR Tech) 👩‍💼🤖")

st.markdown(
    """
Upload a Job Description (PDF or text) and multiple resumes (PDF or text). The app will extract text, call OpenAI to evaluate fit, and produce a ranked CSV report.
- Secrets: Add `OPENAI_API_KEY` in Streamlit Secrets.
- This is a demo; for production consider data privacy and compliance.
"""
)

with st.sidebar:
    st.header("Instructions")
    st.write("""
    1. Upload the Job Description (PDF or TXT).  
    2. Upload multiple resumes (PDF or TXT).  
    3. Click **Evaluate Resumes** to get ranked results.  
    4. Download the CSV report.
    """)
    st.markdown("**Note:** Sample resumes included for quick testing.")

col1, col2 = st.columns([3,1])

with col1:
    jd_file = st.file_uploader("Upload Job Description (PDF or TXT)", type=['pdf','txt'], key="jd")
    resumes = st.file_uploader("Upload Resumes (PDF or TXT) - multiple", type=['pdf','txt'], accept_multiple_files=True, key="resumes")
    use_samples = st.checkbox("Use sample resumes included in app", value=True)
    evaluate = st.button("Evaluate Resumes")

with col2:
    st.write("Options")
    max_tokens = st.slider("Max tokens for OpenAI eval", min_value=200, max_value=2000, value=800, step=100)

# Helper functions
def extract_text_from_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = []
        for page in reader.pages:
            text.append(page.extract_text() or "")
        return "\n".join(text)
    except Exception as e:
        return ""

def read_uploaded_file(f):
    if f is None:
        return ""
    if hasattr(f, "type") and f.type == "application/pdf" or (hasattr(f, "name") and f.name.lower().endswith(".pdf")):
        return extract_text_from_pdf(f)
    else:
        try:
            return f.getvalue().decode('utf-8', errors='ignore')
        except Exception:
            return ""

def simple_extract_name(text):
    # heuristic: find "Name:" or first line with two capitalized words
    m = re.search(r"Name[:\-\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    if m:
        return m.group(1)
    # fallback: first line
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line.strip()

def call_openai_evaluator(jd_text, resume_text, model=MODEL, max_tokens=800):
    system = "You are an expert technical recruiter and hiring manager. Given a job description and a resume, produce a JSON object with fields: candidate_name, match_score (0-100 integer), years_experience_estimate, key_skills_matched (array), missing_skills (array), short_summary (1-2 sentences), and fit_level (High/Medium/Low). Only return valid JSON."
    user_prompt = f"""JOB_DESCRIPTION:
{jd_text}

RESUME:
{resume_text}

Produce the JSON as instructed. Be concise.
"""
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[{"role":"system","content": system}, {"role":"user","content": user_prompt}],
        temperature=0.0,
        max_tokens=max_tokens
    )
    text = resp.choices[0].message.content.strip()
    # Try to extract JSON from the model output
    try:
        # find first { ... }
        start = text.find("{")
        end = text.rfind("}") + 1
        json_text = text[start:end]
        return json.loads(json_text)
    except Exception as e:
        return {"candidate_name": simple_extract_name(resume_text)[:50], "match_score": 0, "years_experience_estimate": 0, "key_skills_matched": [], "missing_skills": [], "short_summary": f"OpenAI response parse error: {str(e)}", "fit_level": "Low"}

# Load sample resumes if requested
sample_dir = Path(__file__).parent / "sample_resumes"
sample_files = []
if use_samples:
    if sample_dir.exists():
        for p in sample_dir.glob("*.txt"):
            sample_files.append(p)

if evaluate:
    # Get JD text
    jd_text = ""
    if jd_file:
        jd_text = read_uploaded_file(jd_file)
    else:
        st.warning("No JD uploaded. The evaluator will run but results may be generic. Consider uploading a job description.")
    # Collect resumes
    resumes_data = []
    if resumes:
        for r in resumes:
            txt = read_uploaded_file(r)
            resumes_data.append( (r.name, txt) )
    if use_samples and sample_files:
        for p in sample_files:
            with open(p, "r", encoding="utf-8") as f:
                resumes_data.append( (p.name, f.read()) )
    if not resumes_data:
        st.error("No resumes provided. Upload resume files or enable sample resumes.")
    else:
        results = []
        progress = st.progress(0)
        total = len(resumes_data)
        for idx, (name, txt) in enumerate(resumes_data, start=1):
            with st.spinner(f"Evaluating {name} ({idx}/{total})..."):
                try:
                    out = call_openai_evaluator(jd_text, txt, max_tokens=max_tokens)
                except Exception as e:
                    out = {"candidate_name": name, "match_score": 0, "years_experience_estimate": 0, "key_skills_matched": [], "missing_skills": [], "short_summary": f"OpenAI call failed: {e}", "fit_level": "Low"}
                out["source_file"] = name
                results.append(out)
            progress.progress(int(idx/total * 100))
        # Sort by match_score desc
        results_sorted = sorted(results, key=lambda x: x.get("match_score",0), reverse=True)
        st.subheader("Ranked Candidates")
        for r in results_sorted:
            st.markdown(f"**{r.get('candidate_name','Unknown')}** — Score: **{r.get('match_score',0)}** — Fit: **{r.get('fit_level','Unknown')}**")
            st.write(f"Estimated years experience: {r.get('years_experience_estimate',0)}")
            st.write("Key skills matched: " + ", ".join(r.get("key_skills_matched",[])))
            st.write("Missing skills: " + ", ".join(r.get("missing_skills",[])))
            st.write("Summary: " + r.get("short_summary",""))
            st.write("---")
        # CSV download
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
                ";".join(r.get("key_skills_matched",[])),
                ";".join(r.get("missing_skills",[])),
                r.get("short_summary","")
            ])
        st.download_button("Download CSV Report", data=csv_buffer.getvalue(), file_name="resume_ranking.csv", mime="text/csv")
