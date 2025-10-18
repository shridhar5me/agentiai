import streamlit as st
import tempfile
from pathlib import Path
import openai
from PyPDF2 import PdfReader
from fpdf import FPDF

st.set_page_config(page_title="Auto-Researcher Lite", layout="wide")

# --- Secrets and model config ---
try:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("OpenAI API key not found in Streamlit secrets. Go to your app's Settings → Secrets and add OPENAI_API_KEY.")
    st.stop()

openai.api_key = openai_api_key
MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4") if isinstance(st.secrets, dict) else "gpt-4"

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = []
    for page in reader.pages:
        text.append(page.extract_text() or "")
    return "\n".join(text)

def call_openai_summary(prompt, model=MODEL, max_tokens=800):
    # Uses ChatCompletion API for compatibility. Adjust if your key requires newer API.
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role":"system","content":"You are a helpful research assistant. Produce clear, concise summaries and bullet points."},
            {"role":"user","content": prompt}
        ],
        temperature=0.2,
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content.strip()

def generate_pdf(title, summary_text, filename="research_report.pdf"):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=16)
    pdf.multi_cell(0, 8, title, 0, 'L')
    pdf.ln(4)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 6, summary_text)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp.name)
    return tmp.name

st.title("Auto-Researcher Lite 🧠🔎")
st.markdown("Provide URLs, paste text, or upload PDFs/text files. The app will summarize and create a downloadable PDF report using OpenAI.")

with st.sidebar:
    st.header("How to use")
    st.write("""
    1. Enter a topic or paste text / upload a PDF.  
    2. Click **Summarize** to get a quick summary.  
    3. Optionally click **Generate PDF Report** to download a PDF.  

    **Important:** Add your OpenAI API key in Streamlit Secrets as `OPENAI_API_KEY`.
    """)

col1, col2 = st.columns([3,1])
with col1:
    topic = st.text_input("Enter a research topic (optional):", value="")
    urls = st.text_area("Paste URLs (one per line) (optional):", value="", height=100)
    uploaded_files = st.file_uploader("Upload PDF or text files (optional)", accept_multiple_files=True, type=['pdf','txt'])
    pasted_text = st.text_area("Or paste text here (optional):", height=200)
    prompt_additional = st.text_area("Additional instructions for the assistant (optional)", height=80)

with col2:
    st.write("Options")
    max_tokens = st.slider("Max tokens for summary", min_value=200, max_value=2000, value=800, step=100)
    gen_pdf = st.button("Generate PDF Report")
    summarize = st.button("Summarize")

# Collect content
collected = []
if topic:
    collected.append(f"Topic: {topic}\n")
if urls.strip():
    collected.append("URLs:\n" + urls.strip() + "\n")
if pasted_text.strip():
    collected.append("Pasted Text:\n" + pasted_text.strip() + "\n")
if uploaded_files:
    for f in uploaded_files:
        if f.type == "application/pdf" or f.name.lower().endswith(".pdf"):
            try:
                txt = extract_text_from_pdf(f)
                collected.append(f"Contents of {f.name}:\n{txt}\n")
            except Exception as e:
                collected.append(f"(Could not extract PDF {f.name}: {e})\n")
        else:
            try:
                content = f.getvalue().decode('utf-8', errors='ignore')
                collected.append(f"Contents of {f.name}:\n{content}\n")
            except Exception as e:
                collected.append(f"(Could not read {f.name}: {e})\n")

if not collected:
    st.info("Provide a topic, URLs, pasted text, or upload files to summarize.")
else:
    full_input = "\n\n".join(collected)
    if prompt_additional:
        full_input += "\n\nAdditional instructions: " + prompt_additional

    if summarize:
        with st.spinner("Calling OpenAI to generate summary..."):
            try:
                prompt = f"Please read the following content and provide:\n1) A concise summary (4-6 sentences).\n2) Key bullet points (5 bullets).\n3) Suggested next steps for deeper research.\n\nCONTENT:\n{full_input}\n\nBe concise and clear."
                summary = call_openai_summary(prompt, max_tokens=max_tokens)
                st.subheader("Summary")
                st.write(summary)
                st.session_state["latest_summary"] = summary
            except Exception as e:
                st.error(f"OpenAI call failed: {e}")

    if gen_pdf:
        summary_text = st.session_state.get("latest_summary", None)
        if not summary_text:
            st.warning("No summary found in session. Click 'Summarize' first or provide your own text to include in the PDF.")
        else:
            title = topic if topic else "Research Report"
            pdf_path = generate_pdf(title, summary_text)
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF Report", f, file_name=f"{title.replace(' ','_')}.pdf", mime="application/pdf")
