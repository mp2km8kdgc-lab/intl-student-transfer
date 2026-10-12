import os
import json
import datetime
import streamlit as st
from openai import OpenAI
import PyPDF2
import docx
import ai_team

JSON_HELP_CONTENT = {
    "zh": """如何导出 JSON 历史记录

第一步：找到按钮
在当前页面的同一个侧边栏（或历史记录区域），
寻找名字包含以下关键词的按钮：
  ○「导出历史记录」或「下载历史记录」
  ○「Export」或「Download」

第二步：点击下载
1. 直接点击该按钮。
2. 浏览器会自动开始下载（或弹出保存提示），
   下载下来的文件就是 .json 格式的历史记录。""",
    "en": """How to Export Your JSON History

Step 1: Find the button
In the sidebar (or history area) of the current page,
look for a button whose name contains one of these keywords:
  o "Export History" or "Download History"
  o "Export" or "Download"

Step 2: Click to download
1. Simply click the button.
2. Your browser will start the download automatically
   (or show a save prompt). The downloaded file is your
   history in .json format.""",
    "ja": """JSON履歴のエクスポート方法

ステップ1：ボタンを探す
現在のページのサイドバー（または履歴エリア）で、
以下のキーワードを含むボタンを探してください：
  ○「履歴をエクスポート」または「履歴をダウンロード」
  ○「Export」または「Download」

ステップ2：クリックしてダウンロード
1. そのボタンをクリックします。
2. ブラウザが自動的にダウンロードを開始します
  （または保存ダイアログが表示されます）。
   ダウンロードされたファイルが .json 形式の履歴データです。""",
    "ko": """JSON 기록 내보내기 방법

1단계: 버튼 찾기
현재 페이지의 사이드바(또는 기록 영역)에서
다음 키워드를 포함하는 버튼을 찾으세요:
  ○ "기록 내보내기" 또는 "기록 다운로드"
  ○ "Export" 또는 "Download"

2단계: 클릭하여 다운로드
1. 해당 버튼을 클릭하세요.
2. 브라우저가 자동으로 다운로드를 시작합니다
  (또는 저장 창이 표시됨).
   다운로드된 파일이 .json 형식의 기록 데이터입니다.""",
    "es": """Cómo exportar tu historial JSON

Paso 1: Encuentra el botón
En la barra lateral (o zona de historial) de la página actual,
busca un botón cuyo nombre contenga alguna de estas palabras clave:
  o "Exportar historial" o "Descargar historial"
  o "Export" o "Download"

Paso 2: Haz clic para descargar
1. Haz clic directamente en el botón.
2. El navegador iniciará la descarga automáticamente
   (o mostrará un cuadro de guardar).
   El archivo descargado es tu historial en formato .json."""
}

JSON_HELP_LANGS = {
    "中文": "zh",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Español": "es"
}

if 'history' not in st.session_state:
    st.session_state.history = []
if 'language' not in st.session_state:
    st.session_state.language = "English"
if 'show_json_help' not in st.session_state:
    st.session_state.show_json_help = False

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    try:
        OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    except Exception:
        pass

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

MODEL_NAME = os.environ.get("OPENROUTER_MODEL", "")
if not MODEL_NAME:
    try:
        MODEL_NAME = st.secrets.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    except Exception:
        MODEL_NAME = DEFAULT_MODEL

client = None
if OPENROUTER_API_KEY and OPENROUTER_API_KEY.startswith("sk-or-"):
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

st.set_page_config(
    page_title="International Student Academic Assistant",
    page_icon="🎓",
    layout="wide",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

st.markdown(
    """
    <style>
    footer {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    a[href*="github.com"] {display: none !important;}
    button[title*="GitHub"] {display: none !important;}
    button[aria-label*="GitHub"] {display: none !important;}
    [data-testid="stToolbar"] a[href*="github.com"] {display: none !important;}
    [data-testid="stToolbar"] button[title*="GitHub"] {display: none !important;}
    [data-testid="stToolbar"] button[aria-label*="GitHub"] {display: none !important;}
    [role="menu"] a[href*="github.com"] {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True
)

def record_history(page_name, user_input, ai_response):
    record = {
        "time": datetime.datetime.now().isoformat(),
        "page": page_name,
        "user_input": user_input[:300] + ("..." if len(user_input) > 300 else ""),
        "ai_response": ai_response,
        "language": st.session_state.language
    }
    st.session_state.history.append(record)

def ask_deepseek(prompt, system_prompt="You are a helpful assistant."):
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
        "5. Syllabus Analysis",
        *ai_team.PAGES.keys(),
    ]
)

language = st.sidebar.selectbox(
    "Language / 语言",
    ["English", "中文", "Español", "日本語", "한국어"],
    index=0
)
st.session_state.language = language

st.sidebar.markdown("---")
st.sidebar.subheader("📜 History")

col1, col2 = st.sidebar.columns([3, 1])
with col1:
    if st.session_state.history:
        json_str = json.dumps(st.session_state.history, ensure_ascii=False, indent=2)
        st.download_button(
            label="导出历史记录 (JSON)",
            data=json_str,
            file_name="history.json",
            mime="application/json"
        )
    else:
        st.caption("暂无历史记录")
with col2:
    if st.button("❓", key="json_help_btn", help="JSON 导出帮助"):
        st.session_state.show_json_help = not st.session_state.show_json_help

if st.session_state.show_json_help:
    with st.sidebar.expander("JSON 导出帮助", expanded=True):
        help_lang = st.radio(
            "选择语言",
            list(JSON_HELP_LANGS.keys()),
            index=0,
            key="json_help_lang"
        )
        lang_code = JSON_HELP_LANGS[help_lang]
        st.markdown(JSON_HELP_CONTENT[lang_code])

uploaded_history = st.sidebar.file_uploader(
    "导入历史记录 (JSON)",
    type=["json"],
    key="history_uploader"
)
if uploaded_history is not None:
    try:
        imported = json.load(uploaded_history)
        if isinstance(imported, list):
            st.session_state.history.extend(imported)
            st.sidebar.success(f"成功导入 {len(imported)} 条记录")
        else:
            st.sidebar.error("文件格式错误，应为 JSON 数组")
    except Exception as e:
        st.sidebar.error(f"导入失败: {e}")

if st.sidebar.button("清空历史记录"):
    st.session_state.history = []
    st.sidebar.success("已清空")

st.sidebar.caption(f"共 {len(st.session_state.history)} 条记录")

st.sidebar.markdown("---")
st.sidebar.caption("International Student Academic Assistant\n\nPrototype built with Python + Streamlit + OpenRouter by hx6@hawaii.edu")

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
            prompt = (
                f"You are a US community college transfer advisor. Student's completed courses:\n{completed}\n\n"
                f"Target University: {target_school}\nTarget Major: {target_major}\n\n"
                f"List remaining required courses and provide enrollment recommendations. "
                f"Answer in {st.session_state.language} with bullet points."
            )
            with st.spinner("Analyzing..."):
                result = ask_deepseek(prompt, "You are a professional academic advisor.")
            st.markdown("### AI Recommendations")
            st.markdown(result)
            record_history("Course Planner", f"Completed: {completed}\nTarget: {target_school} - {target_major}", result)

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
            prompt = (
                f"Analyze the following assignment instructions and output:\n"
                f"1. What do I need to do?\n2. What is graded?\n3. Deadline\n4. Rubric\n\n"
                f"Answer in {st.session_state.language} but keep English headings. "
                f"If no explicit deadline or rubric found, state \"Not found in original text, confirm with professor\".\n\n"
                f"Assignment:\n{content}"
            )
            with st.spinner("Analyzing..."):
                result = ask_deepseek(prompt, "You are an academic assistant.")
            st.markdown("### Analysis Result")
            st.markdown(result)
            record_history("Assignment Helper", content[:300], result)

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
            prompt = (
                f"As a senior US college advisor, provide two or more transfer plans based on the following information, "
                f"and explain how to adjust current weaknesses.\n\n"
                f"Current School: {current_school}\nTarget University: {target_school}\n"
                f"Target Major: {major}\nCompleted Courses: {completed}\n\n"
                f"Reference assist.org articulation logic, but remind user to confirm with schools.\n"
                f"Answer in {st.session_state.language} with bullet points."
            )
            with st.spinner("Planning..."):
                result = ask_deepseek(prompt, "You are a senior US college advisor.")
            st.markdown("### Transfer Plan & Advice")
            st.markdown(result)
            record_history("Transfer Information", f"{current_school} -> {target_school} ({major})\nCompleted: {completed}", result)

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
            prompt = (
                f"Answer the following international student question: {question}\n\n"
                f"Answer in {st.session_state.language} and remind student to verify with school official information."
            )
            with st.spinner("Answering..."):
                answer = ask_deepseek(prompt, "You are an international student advisor.")
            st.markdown("### Answer")
            st.markdown(answer)
            record_history("International Student FAQ", question, answer)
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
            prompt = (
                f"Extract key information, required tasks, and exams from the following syllabus. "
                f"Answer in {st.session_state.language} with bullet points.\n\nSyllabus:\n{content}"
            )
            with st.spinner("Analyzing Syllabus..."):
                result = ask_deepseek(prompt, "You are an academic assistant.")
            st.markdown("### Syllabus Analysis")
            st.markdown(result)
            record_history("Syllabus Analysis", content[:300], result)

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
                prompt = (
                    f"Based on the following syllabus, evaluate semester completion percentage and estimated score. "
                    f"Answer in {st.session_state.language} with bullet points.\n\n"
                    f"Syllabus:\n{st.session_state['syllabus_text']}\n\nCompleted Tasks:\n{completed_tasks}"
                )
                with st.spinner("Evaluating..."):
                    evaluation = ask_deepseek(prompt, "You are an academic assistant.")
                st.markdown("### Evaluation Result")
                st.markdown(evaluation)
                record_history("Syllabus Evaluation", f"Syllabus + Tasks: {completed_tasks[:200]}", evaluation)

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
else:
    ai_team.render_page(page, ask_deepseek, record_history, extract_text_from_upload)
