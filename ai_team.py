"""
ai_team.py - AI 转学助手团队（Research / Content / Support / Analytics）

接入方式（见 aapp.py 里的 4 处改动）：
    import ai_team
    ai_team.render_page(page, ask_fn=ask_deepseek, record_fn=record_history)

设计原则
1. 这个模块不碰 API Key。AI 调用全部通过 aapp.py 传进来的 ask_fn（OpenRouter），
   Key 仍然只存在于服务器端的环境变量 / st.secrets。
2. 不编造招生信息：Research 只从“官网页面文字”里抽取，并且每个字段必须带原文引用；
   引用在原文里找不到的字段会被丢弃，显示“未找到”。
3. 保底 / 匹配 / 冲刺由代码按 Research 里的 GPA 数据计算，AI 只负责解释和给下一步。
4. Analytics 只统计主题和次数，不显示学生原话。
"""
import csv
import datetime
import io
import ipaddress
import json
import re
import socket
from collections import Counter
from urllib.parse import urljoin, urlparse

import streamlit as st

try:  # 自动读取网页是可选功能；没装 requests / bs4 时退回到粘贴文字
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    requests = None
    BeautifulSoup = None

DISCLAIMER = "⚠️ 本页内容不是法律或移民建议。招生政策、截止日期和录取要求随时可能变化，请以学校官网为准。"
NF = "未找到"
STALE_DAYS = 90

EMPLOYEES = {
    "research": {"emoji": "🔎", "no": "AI #1", "name": "Research 研究员工", "duty": "从学校官网页面文字里抽取转学要求；每个字段都要有原文引用，查不到就写“未找到”。"},
    "content": {"emoji": "📝", "no": "AI #2", "name": "Content 内容员工", "duty": "把 Research 记录改写成短视频脚本、博客和 FAQ，不歪曲来源。"},
    "support": {"emoji": "💬", "no": "AI #3", "name": "Customer Support 客服员工", "duty": "收集学生背景，按保底 / 匹配 / 冲刺给出选校建议和下一步。"},
    "analytics": {"emoji": "📊", "no": "AI #4", "name": "Analytics 分析员工", "duty": "汇总高频问题和热门学校，建议下周内容，并指出需要更新的 Research。"},
}

# Research 记录里要抽取的字段（key, 中文名）
FIELDS = [
    ("gpa_min", "GPA最低"),
    ("gpa_rec", "GPA建议"),
    ("prereqs", "先修课"),
    ("requirements", "转学要求"),
    ("credits", "学分要求"),
    ("deadline", "截止日期"),
    ("intl", "国际生要求"),
    ("english", "英语要求"),
]
FIELD_LABEL = dict(FIELDS)

PLATFORMS = {
    "TikTok 脚本": "tiktok",
    "Instagram Reel 脚本": "reel",
    "YouTube Shorts 脚本": "shorts",
    "Blog": "blog",
    "FAQ": "faq",
}

PROFILE_FIELDS = [
    ("term", "学制"),
    ("credits", "累计学分"),
    ("major", "专业"),
    ("gpa", "GPA"),
    ("courses", "已完成课程"),
    ("season", "目标入学季"),
    ("intl", "是否国际生"),
    ("targets", "目标学校"),
]

# Analytics 用关键词把问题归类（只保留主题，不展示原话）
TOPICS = [
    ("学分够不够、能转多少学分", ["学分", "credit"], "做一期“转学前需要修满多少学分”的短视频 + FAQ"),
    ("GPA 要求与竞争力", ["gpa", "绩点"], "用 Research 数据整理“各校 GPA 参考区间”博客"),
    ("先修课清单", ["先修", "prereq", "course", "课程"], "按专业做先修课对照表，附官方来源"),
    ("转学截止日期", ["截止", "deadline", "什么时候"], "做一条“本季转学截止日期”图文"),
    ("国际生申请流程", ["国际生", "international", "i-20", "sevis", "f-1"], "写国际生转学材料清单 FAQ（注明不是移民建议）"),
    ("英语成绩要求", ["英语", "toefl", "ielts", "托福", "雅思", "duolingo"], "整理各校英语成绩要求并标注来源"),
    ("选校：保底 / 匹配 / 冲刺", ["选校", "保底", "匹配", "冲刺", "申请什么", "哪些学校"], "做一期“怎么给转学选校分层”脚本"),
    ("文书与个人陈述", ["文书", "essay", "piq", "个人陈述", "statement"], "写一篇转学文书结构指南"),
    ("学费与奖学金", ["学费", "奖学金", "financial aid", "tuition", "scholarship"], "先让 Research 补充学费与资助信息，再出内容"),
]


# ============================================================ 通用小工具
def _state():
    ss = st.session_state
    ss.setdefault("ai_research", [])        # Research 记录列表
    ss.setdefault("ai_content_saved", [])   # 已保存的内容
    ss.setdefault("ai_support_chat", [])    # [{role, content, recs?}]
    ss.setdefault("ai_support_profile", {})
    ss.setdefault("ai_status", {})          # {employee: idle/working/review}
    ss.setdefault("ai_content_current", {})  # {(record_id, platform): text}


def _header(key):
    e = EMPLOYEES[key]
    status = st.session_state.ai_status.get(key, "idle")
    label = {"idle": "🟢 空闲", "working": "🟡 工作中", "review": "🟠 待审核"}[status]
    c1, c2 = st.columns([1, 8])
    c1.markdown(f"<div style='font-size:42px;line-height:1.1'>{e['emoji']}</div>", unsafe_allow_html=True)
    c2.markdown(f"**{e['no']} · {e['name']}**　{label}")
    c2.caption(e["duty"])
    st.warning(DISCLAIMER)


def _set_status(key, value):
    st.session_state.ai_status[key] = value


def _today():
    return datetime.date.today().isoformat()


def _missing(v):
    return v is None or v == "" or v == [] or v == NF


def _show(v):
    if _missing(v):
        return NF
    return "；".join(map(str, v)) if isinstance(v, list) else str(v)


def _safe_url(u):
    try:
        p = urlparse((u or "").strip())
    except ValueError:
        return ""
    return p.geturl() if p.scheme in ("http", "https") and p.netloc else ""


def _norm(s):
    """比较引用用：转小写、合并空白、统一引号和破折号。"""
    s = (s or "").lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", s).strip()


def parse_json(text):
    """从模型输出里取出 JSON 对象（兼容 ```json 代码块和前后废话）。失败返回 None。"""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# ============================================================ 读取官网页面（带 SSRF 防护）
def _is_public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
        except ValueError:
            return False
    return bool(infos)


def fetch_page_text(url, max_bytes=2_000_000, max_hops=3):
    """只允许 https、公网地址；手动跟随重定向并逐跳检查。返回 (text, error)。"""
    if requests is None:
        return "", "服务器没有安装 requests / beautifulsoup4，请改用“粘贴文字”。"
    cur = _safe_url(url)
    if not cur or not cur.startswith("https://"):
        return "", "只支持 https:// 开头的网址。"
    try:
        for _ in range(max_hops + 1):
            host = urlparse(cur).hostname or ""
            if not _is_public_host(host):
                return "", "这个网址不是公网地址，已拒绝读取。"
            r = requests.get(cur, timeout=10, allow_redirects=False, stream=True,
                             headers={"User-Agent": "Mozilla/5.0 (intl-student-transfer research bot)"})
            if r.is_redirect or r.is_permanent_redirect:
                nxt = _safe_url(urljoin(cur, r.headers.get("Location", "")))
                if not nxt.startswith("https://"):
                    return "", "重定向到了非 https 地址，已拒绝。"
                cur = nxt
                continue
            r.raise_for_status()
            raw = r.raw.read(max_bytes + 1, decode_content=True)
            if len(raw) > max_bytes:
                return "", "页面太大（超过 2MB），请改用“粘贴文字”。"
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return "", f"暂不支持读取 {ctype or '未知类型'}，PDF 请用“上传文件”。"
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "footer"]):
                tag.decompose()
            text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
            if len(text.strip()) < 200:
                return "", "页面几乎没有文字（可能是动态加载的页面，例如 assist.org）。请复制页面文字后粘贴。"
            return text, ""
        return "", "重定向次数过多。"
    except Exception as e:  # noqa: BLE001
        return "", f"读取失败：{e}"


# ============================================================ Research：抽取 + 引用校验
EXTRACT_SYSTEM = "You extract facts from a university web page. You never guess and never use outside knowledge."


def build_extract_prompt(school, major, term, page_text):
    keys = ", ".join(k for k, _ in FIELDS)
    return (
        f"Below is text copied from an official page of {school or 'a US university'}"
        f"{' for the major ' + major if major else ''} ({term}).\n"
        f"Extract ONLY these fields: {keys}.\n"
        "Rules:\n"
        "- Use ONLY the page text. If a field is not stated, set value to null and quote to null.\n"
        "- Every non-null field MUST include a `quote`: an exact, contiguous snippet (max 200 chars) copied from the page text.\n"
        "- `prereqs` is a list of course names; other values are short strings; gpa_min and gpa_rec are numbers.\n"
        "- Do not infer, average, or round. Do not use knowledge outside the text.\n"
        "Return ONLY one JSON object shaped like:\n"
        '{"gpa_min": {"value": 2.8, "quote": "..."}, "prereqs": {"value": ["Calculus I"], "quote": "..."}, ...}\n\n'
        f"PAGE TEXT:\n{page_text[:12000]}"
    )


def verify_extraction(obj, page_text):
    """丢掉引用在原文里找不到的字段。返回 (values, verified_keys, dropped_keys)。"""
    hay = _norm(page_text)
    values, ok, dropped = {}, [], []
    for key, _ in FIELDS:
        item = (obj or {}).get(key)
        if not isinstance(item, dict) or _missing(item.get("value")):
            values[key] = None
            continue
        quote = _norm(str(item.get("quote") or ""))
        if len(quote) >= 8 and quote in hay:
            val = item["value"]
            if key in ("gpa_min", "gpa_rec"):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    values[key] = None
                    dropped.append(key)
                    continue
            values[key] = val
            ok.append(key)
        else:
            values[key] = None
            dropped.append(key)
    return values, ok, dropped


def confidence_of(ok_keys, source_url):
    host = (urlparse(source_url).hostname or "").lower()
    official = host.endswith(".edu")
    if len(ok_keys) >= 4 and official:
        return "高"
    if len(ok_keys) >= 2:
        return "中"
    return "低" if ok_keys else "无"


def is_stale(iso):
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(iso)).days > STALE_DAYS
    except (TypeError, ValueError):
        return False


def records_to_rows(records):
    rows = []
    for r in records:
        rows.append({
            "学校": r.get("school", ""),
            "专业": r.get("major", ""),
            "GPA最低": _show(r.get("gpa_min")),
            "GPA建议": _show(r.get("gpa_rec")),
            "先修课": _show(r.get("prereqs")),
            "转学要求": _show(r.get("requirements")),
            "学分要求": _show(r.get("credits")),
            "截止日期": _show(r.get("deadline")),
            "国际生要求": _show(r.get("intl")),
            "英语要求": _show(r.get("english")),
            "来源": r.get("source") or NF,
            "录入日期": (r.get("updated_at") or NF) + ("（可能已过期）" if is_stale(r.get("updated_at")) else ""),
            "置信度": r.get("confidence", "无"),
        })
    return rows


def rows_to_csv(rows):
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(rows)
    return "\ufeff" + buf.getvalue()  # BOM：Excel 打开中文不乱码


def page_research(ask_fn, record_fn, extract_text_fn=None):
    _header("research")
    recs = st.session_state.ai_research

    with st.form("ai_research_form"):
        c1, c2 = st.columns(2)
        school = c1.text_input("学校", placeholder="如 UCLA")
        major = c2.text_input("专业", placeholder="如 Computer Science")
        c3, c4, c5 = st.columns(3)
        state = c3.text_input("州", placeholder="如 CA", max_chars=2)
        degree = c4.selectbox("学位类型", ["本科", "副学士", "硕士"])
        term = c5.selectbox("学制", ["两年制社区学院转四年制", "四年制转四年制"])
        source_url = st.text_input("官方页面网址（必填，作为来源）", placeholder="https://admission.ucla.edu/...")
        page_text = st.text_area("官网页面文字（可粘贴；留空则自动读取上面的网址）", height=140)
        upload = st.file_uploader("或上传官网 PDF / docx / txt", type=["pdf", "docx", "txt"])
        submitted = st.form_submit_button("开始研究")

    if submitted:
        url = _safe_url(source_url)
        if not school.strip() or not url:
            st.warning("请填写学校和有效的官方页面网址（http/https），没有来源的信息不会被记录。")
        else:
            _set_status("research", "working")
            text = page_text.strip()
            if upload is not None and extract_text_fn:
                text = extract_text_fn(upload)
            err = "文件读取失败，请换一个文件或改用粘贴文字。" if text.startswith("File read error") else ""
            with st.status("研究中…", expanded=False) as status:
                if not text and not err:
                    status.update(label="正在读取官网页面…")
                    text, err = fetch_page_text(url)
                obj, ok, dropped = None, [], []
                if text and not err:
                    status.update(label="正在抽取并校验引用…")
                    raw = ask_fn(build_extract_prompt(school, major, term, text), EXTRACT_SYSTEM)
                    obj = parse_json(raw)
                    if raw.startswith(("⚠️", "AI Error")):
                        err = raw
                    elif obj is None:
                        err = "模型没有返回可解析的 JSON（免费模型偶尔会这样），请重试。"
                    else:
                        values, ok, dropped = verify_extraction(obj, text)
                status.update(label="完成" if not err else "失败", state="complete" if not err else "error")
            if err:
                st.error(err)
                _set_status("research", "idle")
            else:
                rec = {
                    "id": f"{int(datetime.datetime.now().timestamp() * 1000)}",
                    "school": school.strip(), "major": major.strip(), "state": state.strip().upper(),
                    "degree": degree, "term": term, **values,
                    "source": url, "updated_at": _today(),
                    "confidence": confidence_of(ok, url), "verified_fields": ok, "manual": False,
                }
                key = (rec["school"].lower(), rec["major"].lower(), rec["term"])
                idx = next((i for i, r in enumerate(recs) if (r["school"].lower(), r["major"].lower(), r["term"]) == key), None)
                if idx is None:
                    recs.insert(0, rec)
                elif recs[idx].get("manual"):
                    st.info("已存在你手动编辑过的同名记录，没有覆盖。")
                else:
                    recs[idx] = rec
                msg = f"已记录。校验通过 {len(ok)} 项" + (f"，丢弃 {len(dropped)} 项（原文里找不到引用）" if dropped else "") + "。"
                st.success(msg)
                record_fn("AI Research", f"{school} / {major}", msg)
                _set_status("research", "review")

    st.markdown("### 研究结果")
    if not recs:
        st.info("还没有记录。填写上面的表单并提供官网页面文字或网址。")
    else:
        st.caption("“未找到”表示官网文字里没有明确写，不是 0 或没有要求。表格可直接编辑；编辑后的记录会标记为手动。")
        rows = records_to_rows(recs)
        st.dataframe(rows, use_container_width=True, hide_index=True)

        c1, c2, c3 = st.columns(3)
        c1.download_button("导出 JSON", json.dumps(recs, ensure_ascii=False, indent=2), "research.json", "application/json")
        c2.download_button("导出 CSV", rows_to_csv(rows), "research.csv", "text/csv")
        c3.download_button("复制用文本（TSV）", "\n".join("\t".join(map(str, r.values())) for r in rows), "research.tsv", "text/tab-separated-values")

        with st.expander("编辑 / 删除某条记录"):
            labels = [f"{r['school']} - {r['major']}（{r['term']}）" for r in recs]
            i = st.selectbox("选择记录", range(len(recs)), format_func=lambda n: labels[n])
            r = recs[i]
            with st.form(f"ai_edit_{r['id']}"):
                e1, e2 = st.columns(2)
                vals = {}
                for n, (k, lab) in enumerate(FIELDS):
                    col = e1 if n % 2 == 0 else e2
                    cur = r.get(k)
                    shown = "" if _missing(cur) else ("，".join(cur) if isinstance(cur, list) else str(cur))
                    vals[k] = col.text_input(lab + ("（多项用逗号分隔）" if k == "prereqs" else ""), value=shown, key=f"e_{r['id']}_{k}")
                new_src = st.text_input("来源网址", value=r.get("source", ""))
                save = st.form_submit_button("保存修改")
            if save:
                if not _safe_url(new_src):
                    st.error("来源网址必须以 http:// 或 https:// 开头。")
                else:
                    for k, _ in FIELDS:
                        v = vals[k].strip()
                        if v == "":
                            r[k] = None
                        elif k in ("gpa_min", "gpa_rec"):
                            try:
                                r[k] = float(v)
                            except ValueError:
                                st.error(f"{FIELD_LABEL[k]} 需要是数字")
                                break
                        elif k == "prereqs":
                            r[k] = [x.strip() for x in re.split(r"[,，、;；\n]+", v) if x.strip()]
                        else:
                            r[k] = v
                    else:
                        r["source"], r["updated_at"], r["manual"] = _safe_url(new_src), _today(), True
                        st.success("已保存")
                        st.rerun()
            if st.button("删除这条记录", key=f"del_{r['id']}"):
                recs.pop(i)
                st.rerun()


# ============================================================ Content
CONTENT_SYSTEM = "You are a content writer. You only use the facts in the provided JSON record and never add facts."


def _record_facts(r):
    return {
        "school": r.get("school"), "major": r.get("major"), "term": r.get("term"),
        **{label: (None if _missing(r.get(k)) else r.get(k)) for k, label in FIELDS},
        "source": r.get("source"), "recorded_on": r.get("updated_at"),
    }


def build_content_prompt(platform, record, language):
    facts = json.dumps(_record_facts(record), ensure_ascii=False)
    base = (
        f"Write in {language}. Use ONLY the facts in this JSON record; any null field must be written as \"{NF}，发布前请核实\" "
        "and must not be guessed. Do not claim certainty beyond the record, do not invent statistics, and mention that policies "
        f"should be verified on the official website. Record:\n{facts}\n\n"
    )
    spec = {
        "tiktok": "Create a TikTok script with sections: 0-3 second hook; 15-30 second key points; CTA; on-screen captions; hashtags.",
        "reel": "Create an Instagram Reel script with sections: hook; key points; CTA; captions; hashtags.",
        "shorts": "Create a YouTube Shorts script with sections: title; hook; key points; CTA; captions; hashtags.",
        "blog": "Create a blog plan with: SEO title; meta description (under 160 characters); H2/H3 outline with the facts under each heading; 3 FAQ items.",
        "faq": "Create exactly 5 FAQ question-and-answer pairs.",
    }[platform]
    return base + spec


def page_content(ask_fn, record_fn):
    _header("content")
    st.info("内容基于 Research 数据，不能歪曲来源。数据里没有的信息会标注“未找到”，发布前请人工核实。")
    recs = st.session_state.ai_research
    if not recs:
        st.warning("还没有 Research 记录。请先到 “AI Research” 页面研究一所学校。")
        return

    labels = [f"{r['school']} - {r['major']}（录入 {r.get('updated_at', NF)}）" for r in recs]
    i = st.selectbox("选择 Research 记录", range(len(recs)), format_func=lambda n: labels[n])
    rec = recs[i]
    platform_label = st.selectbox("平台", list(PLATFORMS.keys()))
    platform = PLATFORMS[platform_label]
    cache_key = f"{rec['id']}::{platform}"

    if st.button("点击生成", type="primary"):
        _set_status("content", "working")
        with st.spinner("生成中…"):
            text = ask_fn(build_content_prompt(platform, rec, st.session_state.language), CONTENT_SYSTEM)
        st.session_state.ai_content_current[cache_key] = text
        record_fn("AI Content", f"{rec['school']} / {rec['major']} / {platform_label}", text)
        _set_status("content", "review")

    tabs = st.tabs(list(PLATFORMS.keys()))
    for tab, (lab, pid) in zip(tabs, PLATFORMS.items()):
        with tab:
            text = st.session_state.ai_content_current.get(f"{rec['id']}::{pid}")
            if not text:
                st.caption(f"还没有生成 {lab}。")
                continue
            st.markdown(text)
            src = rec.get("source") or NF
            st.caption(f"来源：{src}　录入日期：{rec.get('updated_at', NF)}")
            full = f"{text}\n\n来源：{src}（录入日期 {rec.get('updated_at', NF)}）\n提示：内容基于 Research 数据，发布前请核对官网。"
            c1, c2 = st.columns(2)
            c1.download_button("下载文本", full, f"{rec['school']}-{pid}.txt", "text/plain", key=f"dl_{rec['id']}_{pid}")
            if c2.button("保存到我的内容", key=f"sv_{rec['id']}_{pid}"):
                st.session_state.ai_content_saved.insert(0, {"label": f"{rec['school']} {rec['major']}", "platform": lab, "text": full, "saved_at": _today()})
                st.success("已保存")

    saved = st.session_state.ai_content_saved
    if saved:
        st.markdown("### 已保存的内容")
        for n, it in enumerate(saved):
            with st.expander(f"{it['label']} · {it['platform']} · {it['saved_at']}"):
                st.text(it["text"])
                if st.button("删除", key=f"sdel_{n}"):
                    saved.pop(n)
                    st.rerun()


# ============================================================ Support
INITIAL_MSG = "为了给你准确建议，我需要确认你的学制、累计学分、专业、GPA、已完成课程、目标入学季、是否国际生、目标学校。"
QUICK_QUESTIONS = [
    "我现在22 credits，应该申请什么？",
    "我是国际生，需要准备英语成绩吗？",
    "转学截止日期是什么时候？",
]


def profile_missing(profile):
    return [label for k, label in PROFILE_FIELDS if _missing(profile.get(k)) and profile.get(k) != 0]


def classify(profile, records):
    """按 GPA 与 Research 里的建议 GPA 的差距分组：>=+0.2 保底；>=-0.1 匹配；否则冲刺。"""
    groups = {"保底": [], "匹配": [], "冲刺": []}
    unclassified = []
    try:
        gpa = float(profile.get("gpa"))
    except (TypeError, ValueError):
        return groups, unclassified
    major = _norm(profile.get("major"))
    targets = [t.strip().lower() for t in re.split(r"[、,，;；\n]+", str(profile.get("targets") or "")) if t.strip()]
    for r in records:
        if major and major not in _norm(r.get("major")) and _norm(r.get("major")) not in major:
            continue
        name = f"{r.get('school')} {r.get('major')}"
        if _missing(r.get("gpa_rec")):
            unclassified.append(name)
            continue
        gap = gpa - float(r["gpa_rec"])
        bucket = "保底" if gap >= 0.2 else "匹配" if gap >= -0.1 else "冲刺"
        groups[bucket].append({
            "school": r.get("school"), "major": r.get("major"), "gap": round(gap, 2),
            "is_target": any(t in str(r.get("school")).lower() for t in targets),
            "prereqs": r.get("prereqs"), "deadline": r.get("deadline"),
            "intl": r.get("intl"), "english": r.get("english"),
            "source": r.get("source"), "updated_at": r.get("updated_at"),
        })
    return groups, unclassified


SUPPORT_SYSTEM = (
    "You are a customer-support advisor for US college transfer students. Be warm, concise, and honest. "
    "You may only state school-specific facts that appear in the provided RECORDS; otherwise say they were not found and "
    "tell the student to check the official website. Never give legal or immigration advice; for visa/status questions, "
    "tell the student to ask their school's international student office (DSO)."
)


def build_support_prompt(question, profile, missing, groups, unclassified, language):
    return (
        f"Answer in {language}.\n"
        f"STUDENT PROFILE (may be incomplete): {json.dumps(profile, ensure_ascii=False)}\n"
        f"MISSING INFO: {json.dumps(missing, ensure_ascii=False)}\n"
        f"RECORDS grouped by code-computed fit (保底=safety, 匹配=match, 冲刺=reach): {json.dumps(groups, ensure_ascii=False)}\n"
        f"SCHOOLS WITHOUT A RECOMMENDED GPA (cannot be classified): {json.dumps(unclassified, ensure_ascii=False)}\n\n"
        f"STUDENT QUESTION: {question}\n\n"
        "Instructions:\n"
        "- If MISSING INFO is not empty: give only temporary advice, say clearly it is temporary, and ask for the missing items (max 3 at a time). Do not present a final school list.\n"
        "- If MISSING INFO is empty: present 保底 / 匹配 / 冲刺 using the groups exactly as given; for each school give the reason (GPA gap), the next step, and the source URL with its recorded date.\n"
        "- If a group is empty, say so. Never invent schools, numbers, or deadlines. End with a one-line reminder to verify on the official website."
    )


def page_support(ask_fn, record_fn):
    _header("support")
    ss = st.session_state
    if not ss.ai_support_chat:
        ss.ai_support_chat = [{"role": "assistant", "content": INITIAL_MSG}]

    with st.expander("我的信息（8 项，越完整建议越准）", expanded=len(ss.ai_support_chat) <= 1):
        p = ss.ai_support_profile
        c1, c2 = st.columns(2)
        p["term"] = c1.selectbox("学制", ["", "两年制社区学院转四年制", "四年制转四年制"], index=["", "两年制社区学院转四年制", "四年制转四年制"].index(p.get("term", "")))
        p["credits"] = c2.number_input("累计学分", min_value=0, max_value=300, value=int(p.get("credits") or 0))
        p["major"] = c1.text_input("专业", value=p.get("major", ""))
        p["gpa"] = c2.number_input("GPA", min_value=0.0, max_value=4.5, step=0.01, value=float(p.get("gpa") or 0.0))
        p["courses"] = st.text_area("已完成课程", value=p.get("courses", ""), height=70)
        p["season"] = c1.text_input("目标入学季", value=p.get("season", ""), placeholder="如 2027 年秋季")
        p["intl"] = c2.selectbox("是否国际生", ["", "是", "否"], index=["", "是", "否"].index(p.get("intl", "")))
        p["targets"] = st.text_input("目标学校（多个用顿号分隔）", value=p.get("targets", ""))
        # 数字 0 视为“未填写”（GPA 0.0 和 学分 0 在表单里是默认值）
        for k in ("credits", "gpa"):
            if not p.get(k):
                p[k] = None
        st.caption(f"已收集 {len(PROFILE_FIELDS) - len(profile_missing(p))} / {len(PROFILE_FIELDS)} 项。信息不足时只给临时建议。")

    for m in ss.ai_support_chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    quick = st.columns(len(QUICK_QUESTIONS))
    clicked = next((q for col, q in zip(quick, QUICK_QUESTIONS) if col.button(q, key=f"q_{q}")), None)
    question = st.chat_input("输入你的问题") or clicked
    if question:
        ss.ai_support_chat.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        missing = profile_missing(ss.ai_support_profile)
        groups, unclassified = ({"保底": [], "匹配": [], "冲刺": []}, [])
        if not missing:
            groups, unclassified = classify(ss.ai_support_profile, ss.ai_research)
        with st.chat_message("assistant"):
            _set_status("support", "working")
            with st.spinner("整理建议中…"):
                reply = ask_fn(build_support_prompt(question, ss.ai_support_profile, missing, groups, unclassified, ss.language), SUPPORT_SYSTEM)
            st.markdown(reply)
        ss.ai_support_chat.append({"role": "assistant", "content": reply})
        record_fn("AI Support", question, reply)
        _set_status("support", "review" if not missing else "idle")

    if st.button("新对话（清空对话和我的信息）"):
        ss.ai_support_chat, ss.ai_support_profile = [], {}
        st.rerun()


# ============================================================ Analytics
def topic_of(text):
    t = (text or "").lower()
    return [name for name, kws, _ in TOPICS if any(k in t for k in kws)]


def compute_stats(history, records, today=None):
    """只返回聚合数据，不返回任何用户原话。"""
    today = today or datetime.date.today()
    topic_count, school_count, per_day = Counter(), Counter(), Counter()
    support_total = unresolved = 0
    known_schools = {r.get("school") for r in records if r.get("school")}
    for h in history:
        text = h.get("user_input", "")
        day = str(h.get("time", ""))[:10]
        per_day[day] += 1
        for t in topic_of(text):
            topic_count[t] += 1
        for s in known_schools:
            if s and s.lower() in text.lower():
                school_count[s] += 1
        if h.get("page") == "AI Support":
            support_total += 1
            if "未找到" in str(h.get("ai_response", "")) or "temporary" in str(h.get("ai_response", "")).lower() or "临时" in str(h.get("ai_response", "")):
                unresolved += 1
    days = [(today - datetime.timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    total_q = sum(topic_count.values()) or 1
    top = [{"问题": t, "次数": c, "占比": round(c / total_q * 100, 1), "建议内容": next(s for n, _, s in TOPICS if n == t)}
           for t, c in topic_count.most_common(10)]
    needs_update = []
    for r in records:
        reasons = []
        if is_stale(r.get("updated_at")):
            reasons.append(f"超过 {STALE_DAYS} 天未更新")
        if not r.get("source"):
            reasons.append("没有来源")
        miss = sum(1 for k, _ in FIELDS if _missing(r.get(k)))
        if miss >= 4:
            reasons.append(f"{miss} 项关键信息未找到")
        if reasons:
            needs_update.append({"学校/专业": f"{r.get('school')} {r.get('major')}", "原因": "；".join(reasons)})
    return {
        "total": len(history),
        "support_total": support_total,
        "unresolved": unresolved,
        "top_questions": top,
        "top_schools": school_count.most_common(5),
        "trend": {d[5:]: per_day.get(d, 0) for d in days},
        "by_page": dict(Counter(h.get("page", "?") for h in history)),
        "needs_update": needs_update,
    }


def page_analytics(ask_fn, record_fn):
    _header("analytics")
    st.caption("不显示学生隐私信息：只统计问题主题和次数，不展示学生原话。统计范围是当前会话的历史记录（可在侧边栏导入之前导出的 JSON）。")
    s = compute_stats(st.session_state.history, st.session_state.ai_research)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("总对话数", s["total"])
    k2.metric("高频问题数", len(s["top_questions"]))
    k3.metric("未解决问题数", s["unresolved"], help="客服回答里出现“临时建议 / 未找到”的次数，是粗略估计")
    k4.metric("热门学校", s["top_schools"][0][0] if s["top_schools"] else "暂无")

    if not s["total"]:
        st.info("还没有历史记录。先去其他页面用一用，或在侧边栏导入历史 JSON。")
    else:
        st.markdown("#### Top 10 高频问题")
        if s["top_questions"]:
            st.bar_chart({r["问题"]: r["次数"] for r in s["top_questions"]})
        else:
            st.caption("暂时没有匹配到主题。")
        st.markdown("#### 最近 7 天问题趋势")
        st.line_chart(s["trend"])
        st.markdown("#### 各页面使用次数")
        st.bar_chart(s["by_page"])
        if s["top_questions"]:
            st.markdown("#### 高频问题明细")
            st.dataframe(s["top_questions"], use_container_width=True, hide_index=True)
            st.download_button("导出 CSV", rows_to_csv(s["top_questions"]), "analytics.csv", "text/csv")

    st.markdown("#### 需要更新 Research 的学校/专业")
    if s["needs_update"]:
        st.dataframe(s["needs_update"], use_container_width=True, hide_index=True)
    else:
        st.caption("暂时没有需要更新的记录。")

    st.markdown("#### 下周内容建议")
    if s["top_questions"]:
        for n, q in enumerate(s["top_questions"][:3]):
            st.markdown(f"- **{['TikTok', 'Blog', 'FAQ'][n]}：{q['问题']}**（被问 {q['次数']} 次，占 {q['占比']}%）— {q['建议内容']}")
    else:
        st.caption("有足够的问题记录后才会给出建议。")


# ============================================================ 入口
PAGES = {
    "6. AI Research 研究员": page_research,
    "7. AI Content 内容员": page_content,
    "8. AI Support 客服员": page_support,
    "9. AI Analytics 分析员": page_analytics,
}


def render_page(page, ask_fn, record_fn, extract_text_fn=None):
    """aapp.py 的路由里调用。返回 True 表示这个页面由本模块处理。"""
    if page not in PAGES:
        return False
    _state()
    if page == "6. AI Research 研究员":
        page_research(ask_fn, record_fn, extract_text_fn)
    else:
        PAGES[page](ask_fn, record_fn)
    return True
