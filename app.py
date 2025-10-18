"""
)

with st.sidebar:
    st.header("Instructions")
    st.write(
        """
1. Upload the Job Description (PDF or TXT).
2. Upload multiple resumes (PDF or TXT).
3. Click **Evaluate Resumes** to get ranked results.
4. Download the CSV report.
"""
    )
    st.markdown("**Note:** Sample resumes can be bundled into the app directory for quick testing.")

col1, col2 = st.columns([3, 1])

with col1:
    jd_file = st.file_uploader("Upload Job Description (PDF or TXT)", type=["pdf", "txt"], key="jd")
    resumes = st.file_uploader(
        "Upload Resumes (PDF or TXT) - you can upload multiple", type=["pdf", "txt"], accept_multiple_files=True, key="resumes"
    )
    use_samples = st.checkbox("Use sample resumes included in app folder (if present)", value=True)
    evaluate = st.button("Evaluate Resumes")
with col2:
    st.write("Options")
    max_tokens = st.slider("Max tokens for OpenAI eval", min_value=200, max_value=2000, value=800, step=100)
    st.write("Model: " + OPENAI_MODEL)

# Load sample resumes if present in a 'sample_resumes' folder sitting next to app.py
sample_dir = Path(__file__).parent / "sample_resumes"
sample_files = []
if sample_dir.exists() and use_samples:
    for p in sample_dir.glob("*.txt"):
        sample_files.append(p)

if evaluate:
    st.info("Starting evaluation. This will call OpenAI for each resume uploaded/selected.")
    # read JD
    jd_text = ""
    if jd_file:
        jd_text = read_uploaded_file(jd_file)
    else:
        st.warning("No JD uploaded. The evaluation will continue but results may be generic.")
    # collect resumes (uploaded)
    resumes_data: List[Tuple[str, str]] = []
    if resumes:
        for r in resumes:
            txt = read_uploaded_file(r)
            resumes_data.append((r.name, txt))
    # add sample resumes from folder if available
    if use_samples and sample_files:
        for p in sample_files:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    resumes_data.append((p.name, f.read()))
            except Exception:
                pass

    if not resumes_data:
        st.error("No resumes to evaluate. Upload resume files or put sample resumes in the 'sample_resumes' folder.")
    else:
        progress_bar = st.progress(0)
        results = []
        total = len(resumes_data)
        for idx, (name, txt) in enumerate(resumes_data, start=1):
            with st.spinner(f"Evaluating {name} ({idx}/{total})..."):
                out = call_openai_evaluator(jd_text, txt, model=OPENAI_MODEL, max_tokens=max_tokens)
                out["source_file"] = name
                # Ensure candidate_name exists
                if not out.get("candidate_name"):
                    out["candidate_name"] = simple_extract_name(txt)
                results.append(out)
            progress_bar.progress(int((idx / total) * 100))

        # Sort results by match_score desc
        results_sorted = sorted(results, key=lambda x: int(x.get("match_score", 0)), reverse=True)

        # Display results
        st.subheader("Ranked Candidates")
        for r in results_sorted:
            st.markdown(f"**{r.get('candidate_name','Unknown')}** — Score: **{r.get('match_score',0)}** — Fit: **{r.get('fit_level','Unknown')}**")
            st.write(f"Estimated years experience: {r.get('years_experience_estimate',0)}")
            st.write("Key skills matched: " + (", ".join(r.get("key_skills_matched", [])) or "None"))
            st.write("Missing skills: " + (", ".join(r.get("missing_skills", [])) or "None"))
            st.write("Summary: " + (r.get("short_summary", "") or ""))
            st.write("---")

        # Prepare CSV for download
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["candidate_name", "source_file", "match_score", "fit_level", "years_experience_estimate", "key_skills_matched", "missing_skills", "short_summary"])
        for r in results_sorted:
            writer.writerow(
                [
                    r.get("candidate_name", ""),
                    r.get("source_file", ""),
                    r.get("match_score", ""),
                    r.get("fit_level", ""),
                    r.get("years_experience_estimate", ""),
                    ";".join(r.get("key_skills_matched", [])),
                    ";".join(r.get("missing_skills", [])),
                    r.get("short_summary", ""),
                ]
            )
        st.download_button("Download CSV Report", data=csv_buffer.getvalue(), file_name="resume_ranking.csv", mime="text/csv")

