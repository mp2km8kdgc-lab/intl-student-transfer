import os
import json
from datetime import datetime
import streamlit as st
from openai import OpenAI
import PyPDF2
import docx

# ================== 隐藏 GitHub 链接和默认菜单 ==================
hide_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stAppDeployButton {display: none;}
a[href*="github.com"] {display: none;}
</style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ================== 读取密钥和模型 ==================
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    try:
        OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    except Exception:
        pass

MODEL_NAME = os.environ.get("OPENROUTER_MODEL", "")
if not MODEL_NAME:
    try:
        MODEL_NAME = st.secrets.get("OPENROUTER_MODEL", "openrouter/free")
    except Exception:
        MODEL_NAME = "openrouter/free"

client = None
if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-or-"):
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

# ================== 页面配置 ==================
st.set_page_config(
    page_title="International Student Academic Assistant",
    page_icon="🎓",
    layout="wide"
)

# ================== 初始化 session_state ==================
if "history" not in st.session_state:
    st.session_state.history = []
if "language" not in st.session_state:
    st.session_state.language = "English"

# ================== 侧边栏：语言选择 ==================
st.sidebar.title("🌐 Language / 语言")
language_options = ["English", "中文", "日本語", "한국어", "Español"]
st.session_state.language = st.sidebar.selectbox(
    "Select AI response language",
    language_options,
    index=language_options.index(st.session_state.language)
)

st.sidebar.markdown("---")
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

# ================== 侧边栏：历史记录管理 ==================
st.sidebar.markdown("---")
st.sidebar.title("📜 History")

with st.sidebar.expander("导出 / 导入 / 清空", expanded=False):
    # 导出
    if st.session_state.history:
        json_str = json.dumps(st.session_state.history, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ 导出历史记录 (JSON)",
            data=json_str,
            file_name=f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    else:
        st.caption("暂无历史记录")

    # 导入
    uploaded_history = st.file_uploader("⬆️ 导入历史记录 (JSON)", type=["json"], key="history_upload")
    if uploaded_history is not None:
        try:
            imported = json.load(uploaded_history)
            if isinstance(imported, list):
                st.session_state.history.extend(imported)
                st.success(f"成功导入 {len(imported)} 条记录")
            else:
                st.error("JSON 格式错误：根元素必须是数组")
        except Exception as e:
            st.error(f"导入失败：{str(e)}")

    # 清空
    if st.button("🗑️ 清空所有历史记录"):
        st.session_state.history = []
        st.success("历史记录已清空")

# 显示历史记录条数
st.sidebar.caption(f"当前共 {len(st.session_state.history)} 条记录")

# ================== 核心 AI 调用（自动记录历史） ==================
def run_ai(prompt, system_prompt, page_name, user_summary):
    """调用 AI，并自动将结果记录到历史"""
    if client is None:
        return "⚠️ 后端未配置 API Key，请联系管理员。"
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
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
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"AI Error: {str(e)}"

    # 记录到历史
    st.session_state.history.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "page": page_name,
        "user_summary": user_summary,
        "language": st.session_state.language,
        "ai_answer": answer
    })
    return answer

# ================== 文件读取工具 ==================
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

# ================== 各页面函数 ==================
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
            lang = st.session_state.language
            prompt = f"You are a US community college transfer advisor. Student's completed courses:\n{completed}\n\nTarget University: {target_school}\nTarget Major: {target_major}\n\nList remaining required courses and provide enrollment recommendations. Please answer in {lang} with bullet points."
            with st.spinner("Analyzing..."):
                result = run_ai(prompt, "You are a professional academic advisor.", "Course Planner", f"{target_school} / {target_major}")
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
            lang = st.session_state.language
            prompt = f"Analyze the following assignment instructions and output:\n1. What do I need to do?\n2. What is graded?\n3. Deadline\n4. Rubric\n\nPlease answer in {lang} but keep English headings. If no explicit deadline or rubric found, state \"Not found in original text, confirm with professor\".\n\nAssignment:\n{content}"
            with st.spinner("Analyzing..."):
                result = run_ai(prompt, "You are an academic assistant.", "Assignment Helper", content[:100] + "...")
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
            lang = st.session_state.language
            prompt = f"As a senior US college advisor, provide two or more transfer plans based on the following information, and explain how to adjust current weaknesses.\n\nCurrent School: {current_school}\nTarget University: {target_school}\nTarget Major: {major}\nCompleted Courses: {completed}\n\nReference assist.org articulation logic, but remind user to confirm with schools.\nPlease answer in {lang} with bullet points."
            with st.spinner("Planning..."):
                result = run_ai(prompt, "You are a senior US college advisor.", "Transfer Information", f"{current_school} → {target_school}")
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
            lang = st.session_state.language
            prompt = f"Answer the following international student question: {question}\n\nPlease answer in {lang} and remind student to verify with school official information."
            with st.spinner("Answering..."):
                answer = run_ai(prompt, "You are an international student advisor.", "FAQ", question[:100])
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
            lang = st.session_state.language
            prompt = f"Extract key information, required tasks, and exams from the following syllabus. Please answer in {lang} with bullet points.\n\nSyllabus:\n{content}"
            with st.spinner("Analyzing Syllabus..."):
                result = run_ai(prompt, "You are an academic assistant.", "Syllabus Analysis", "Syllabus analysis")
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
                lang = st.session_state.language
                prompt = f"Based on the following syllabus, evaluate semester completion percentage and estimated score. Please answer in {lang} with bullet points.\n\nSyllabus:\n{st.session_state['syllabus_text']}\n\nCompleted Tasks:\n{completed_tasks}"
                with st.spinner("Evaluating..."):
                    evaluation = run_ai(prompt, "You are an academic assistant.", "Syllabus Evaluation", completed_tasks[:100])
                st.markdown("### Evaluation Result")
                st.markdown(evaluation)

# ================== 路由 ==================
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
