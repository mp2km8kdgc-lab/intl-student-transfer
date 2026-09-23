import os
import streamlit as st
from openai import OpenAI
import PyPDF2
import docx

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    try:
        OPENROUTER_API_KEY = st.secrets["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"]
    except Exception:
        pass
st.set_page_config(
    page_title="International Student Academic Assistant",
    page_icon="🎓",
    layout="wide"
)

client = None
if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-or-"):
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

def ask_deepseek(prompt, system_prompt="You are a helpful assistant."):
    if client is None:
        return "⚠️ 后端未配置 API Key，请联系管理员，抖音364611067。"
    try:
        response = client.chat.completions.create(
            model="openrouter/free",
            extra_headers={
                "HTTP-Referer": "https://localhost:8501",
                "X-OpenRouter-Title": "International Student Academic Assistant"
            },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

def extract_text_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith('.txt'):
            return uploaded_file.read().decode('utf-8', errors='ignore')
        elif filename.endswith('.pdf'):
            reader = PyPDF2.PdfReader(uploaded_file)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
            return text
        elif filename.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            return '\n'.join([p.text for p in doc.paragraphs])
        else:
            return uploaded_file.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return f"File read error: {str(e)}"

st.sidebar.title("🎓 Navigation")
page = st.sidebar.radio(
    "Select Page",
    [
        "1. Course Planner",
        "2. Assignment Helper",
        "3. Transfer Information",
        "4. International Student FAQ",
        "5. Syllabus Analysis"
    ]
)
st.sidebar.markdown("---")
st.sidebar.caption("International Student Academic Assistant\n\nPrototype built with Python + Streamlit + OpenRouter")

def course_planner():
    st.header("📚 Course Planner")
    st.write("Enter completed courses, target university and major to get course recommendations.")
    with st.form("course_planner_form"):
        completed = st.text_area("Completed Courses (one per line)", placeholder="e.g.:\nENG 100\nMATH 241\nPSY 100")
        target_school = st.text_input("Target University", placeholder="e.g.: University of California, Berkeley")
        target_major = st.text_input("Target Major", placeholder="e.g.: Computer Science")
        submitted = st.form_submit_button("Generate Recommendations")
    if submitted:
        if not completed or not target_school or not target_major:
            st.warning("Please fill in all fields.")
        else:
            prompt = f"You are a US community college transfer advisor. Student's completed courses:\n{completed}\n\nTarget University: {target_school}\nTarget Major: {target_major}\n\nList remaining required courses and provide enrollment recommendations. Answer in Chinese with bullet points."
            with st.spinner("Analyzing..."):
                result = ask_deepseek(prompt, "You are a professional academic advisor.")
            st.markdown("### AI Recommendations")
            st.markdown(result)

def assignment_helper():
    st.header("📝 Assignment Helper")
    st.write("Paste assignment text or upload a file to analyze requirements, grading criteria, deadlines, and rubric.")
    with st.form("assignment_form"):
        text = st.text_area("Paste assignment instructions", height=200)
        uploaded_file = st.file_uploader("Or upload file (.txt / .pdf / .docx)", type=["txt", "pdf", "docx"])
        submitted = st.form_submit_button("Analyze Assignment")
    if submitted:
        content = text.strip()
        if uploaded_file is not None:
            content = extract_text_from_upload(uploaded_file)
        if not content:
            st.warning("Please paste text or upload a file.")
        else:
            prompt = f"Analyze the following assignment instructions and output:\n1. What do I need to do?\n2. What is graded?\n3. Deadline\n4. Rubric\n\nAnswer in Chinese but keep English headings. If no explicit deadline or rubric found, state \"Not found in original text, confirm with professor\".\n\nAssignment:\n{content}"
            with st.spinner("Analyzing..."):
                result = ask_deepseek(prompt, "You are an academic assistant.")
            st.markdown("### Analysis Result")
            st.markdown(result)

def transfer_info():
    st.header("🔄 Transfer Information")
    st.write("Get transfer planning advice based on assist.org course articulation logic.")
    st.link_button("🌐 点击跳转到 assist.org 查询课程对应", "https://assist.org")
    st.info("Note: assist.org has no public API. Results are AI-generated based on general knowledge. **Always verify on assist.org and target school official website.**")
    with st.form("transfer_form"):
        current_school = st.text_input("Current School", placeholder="e.g.: Kapi'olani Community College")
        target_school = st.text_input("Target University", placeholder="e.g.: University of Hawaii at Manoa")
        major = st.text_input("Target Major", placeholder="e.g.: Business Administration")
        completed = st.text_area("Completed Courses", placeholder="One per line, e.g.:\nENG 100\nMATH 103\nECON 130")
        submitted = st.form_submit_button("Generate Transfer Plan")
    if submitted:
        if not current_school or not target_school or not major:
            st.warning("Please fill in current school, target university, and major.")
        else:
            prompt = f"As a senior US college advisor, provide two or more transfer plans based on the following information, and explain how to adjust current weaknesses.\n\nCurrent School: {current_school}\nTarget University: {target_school}\nTarget Major: {major}\nCompleted Courses: {completed}\n\nReference assist.org articulation logic, but remind user to confirm with schools.\nAnswer in Chinese with bullet points."
            with st.spinner("Planning..."):
                result = ask_deepseek(prompt, "You are a senior US college advisor.")
            st.markdown("### Transfer Plan & Advice")
            st.markdown(result)

def faq():
    st.header("❓ International Student FAQ")
    st.write("Common topics: I-20, SEVIS, transfer, employment, SSN, school resources.")
    faq_items = {
        "I-20": "I-20 is the Certificate of Eligibility for F-1 students, used for visa application, entry, and maintaining status. Transfer, extension, or major change usually requires updated I-20.",
        "SEVIS": "SEVIS is the system managed by DHS for student and exchange visitor information. F-1 students must maintain active SEVIS records and pay I-901 SEVIS Fee on time.",
        "Transfer": "For in-country transfer, obtain admission and I-20 from new school first, then request SEVIS record transfer from current school's international office. Maintain continuous status.",
        "Employment": "On-campus work usually requires no additional authorization; off-campus work generally requires CPT or OPT. Unauthorized employment seriously violates status.",
        "SSN": "SSN is US Social Security Number. F-1 students generally need on-campus job or approved CPT/OPT to apply. Do not give SSN to others casually.",
        "School Resources": "International student office, academic advisor, writing center, math tutoring, counseling, career center are important resources. Schedule appointments proactively."
    }
    with st.expander("📌 Quick Reference"):
        for key, value in faq_items.items():
            st.markdown(f"**{key}**: {value}")
    st.markdown("---")
    question = st.text_input("Enter your specific question")
    if st.button("Ask"):
        if question.strip():
            prompt = f"Answer the following international student question: {question}\n\nAnswer in Chinese and remind student to verify with school official information."
            with st.spinner("Answering..."):
                answer = ask_deepseek(prompt, "You are an international student advisor.")
            st.markdown("### Answer")
            st.markdown(answer)
        else:
            st.warning("Please enter a question.")

def syllabus():
    st.header("📖 Syllabus Analysis")
    st.write("Extract key information, required tasks, exams, and evaluate completion status and estimated score.")
    with st.form("syllabus_analyze_form"):
        syllabus_text = st.text_area("Paste Syllabus text", height=200)
        syllabus_file = st.file_uploader("Or upload Syllabus file (.txt / .pdf / .docx)", type=["txt", "pdf", "docx"])
        analyze_submitted = st.form_submit_button("Analyze Syllabus")
    if analyze_submitted:
        content = syllabus_text.strip()
        if syllabus_file is not None:
            content = extract_text_from_upload(syllabus_file)
        if not content:
            st.warning("Please paste text or upload a file.")
        else:
            st.session_state['syllabus_text'] = content
            prompt = f"Extract key information, required tasks, and exams from the following syllabus. Answer in Chinese with bullet points.\n\nSyllabus:\n{content}"
            with st.spinner("Analyzing Syllabus..."):
                result = ask_deepseek(prompt, "You are an academic assistant.")
            st.markdown("### Syllabus Analysis")
            st.markdown(result)
    if 'syllabus_text' in st.session_state:
        st.markdown("---")
        st.subheader("📊 Evaluate Completion & Score")
        with st.form("syllabus_evaluate_form"):
            completed_tasks = st.text_area("Enter completed tasks (one per line, may include status)", placeholder="e.g.:\nEssay 1 completed\nMidterm taken\nQuiz 1-3 completed")
            evaluate_submitted = st.form_submit_button("Evaluate Completion & Score")
        if evaluate_submitted:
            if not completed_tasks.strip():
                st.warning("Please enter completed tasks.")
            else:
                prompt = f"Based on the following syllabus, evaluate semester completion percentage and estimated score. Answer in Chinese with bullet points.\n\nSyllabus:\n{st.session_state['syllabus_text']}\n\nCompleted Tasks:\n{completed_tasks}"
                with st.spinner("Evaluating..."):
                    evaluation = ask_deepseek(prompt, "You are an academic assistant.")
                st.markdown("### Evaluation Result")
                st.markdown(evaluation)

if page == "1. Course Planner":
    course_planner()
elif page == "2. Assignment Helper":
    assignment_helper()
elif page == "3. Transfer Information":
    transfer_info()
elif page == "4. International Student FAQ":
    faq()
elif page == "5. Syllabus Analysis":
    syllabus()
