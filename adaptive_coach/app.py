import streamlit as st
import google.generativeai as genai
import os
import re
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv
from datetime import date
import database as db

load_dotenv()

# ─────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Adaptive Learning Companion",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# Global CSS (dark premium theme)
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0e1117;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(160deg, #12151f 0%, #0d1117 100%);
    border-right: 1px solid #1e2535;
}

/* Cards */
.metric-card {
    background: linear-gradient(135deg, #1a1f2e, #141929);
    border: 1px solid #2a3150;
    border-radius: 14px;
    padding: 18px 22px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}
.metric-label { color: #8892b0; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.metric-value { font-size: 28px; font-weight: 700; }

/* Status colors */
.status-Normal       { color: #64ffda; }
.status-High-Performance { color: #00e676; }
.status-Burnout      { color: #ff5370; }
.status-Inconsistent { color: #ffcb6b; }
.status-Recovery     { color: #82aaff; }

/* AI Decision box */
.ai-box {
    border-radius: 14px;
    padding: 22px 26px;
    margin-bottom: 20px;
    transition: all 0.4s ease;
}

/* Task card */
.task-card {
    background: #161b27;
    border: 1px solid #252d45;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
}

/* Auth container */
.auth-wrap {
    max-width: 420px;
    margin: 60px auto;
    background: linear-gradient(135deg, #12151f, #1a1f2e);
    border: 1px solid #2a3150;
    border-radius: 18px;
    padding: 40px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}

/* Buttons */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover { transform: translateY(-1px); }

/* Progress bar */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #64ffda, #7c4dff);
    border-radius: 4px;
}

/* Divider */
hr { border-color: #1e2535 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DB Init
# ─────────────────────────────────────────────
db.init_db()

# ─────────────────────────────────────────────
# Authentication Layer
# ─────────────────────────────────────────────
def render_auth():
    st.markdown("""
    <div style='text-align:center; margin-bottom:10px;'>
        <span style='font-size:48px;'>🧠</span>
        <h1 style='font-size:28px; font-weight:800; margin:8px 0 4px; color:#cdd9ff;'>
            Adaptive Learning Companion
        </h1>
        <p style='color:#8892b0; font-size:14px;'>Your AI coach that adapts to your pace & prevents burnout</p>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔐 Login", "📝 Create Account"])

    with tab_login:
        with st.form("login_form"):
            uname = st.text_input("Username", placeholder="your_username")
            pwd   = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Login →", use_container_width=True, type="primary")
        if submitted:
            result = db.login_user(uname, pwd)
            if result['ok']:
                st.session_state.user_id   = result['user_id']
                st.session_state.user_name = result['name']
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error(result['error'])

    with tab_register:
        with st.form("register_form"):
            r_name  = st.text_input("Full Name", placeholder="Navin R")
            r_uname = st.text_input("Username",  placeholder="navin_r")
            r_pwd   = st.text_input("Password",  type="password", placeholder="••••••••")
            r_pwd2  = st.text_input("Confirm Password", type="password", placeholder="••••••••")
            reg_btn = st.form_submit_button("Create Account →", use_container_width=True, type="primary")
        if reg_btn:
            if r_pwd != r_pwd2:
                st.error("Passwords do not match.")
            elif len(r_pwd) < 6:
                st.error("Password must be at least 6 characters.")
            elif not r_uname.strip():
                st.error("Username cannot be empty.")
            else:
                result = db.register_user(r_uname, r_pwd, r_name)
                if result['ok']:
                    st.success("Account created! Please log in.")
                else:
                    st.error(result['error'])


# ─────────────────────────────────────────────
# Session State Bootstrap from DB
# ─────────────────────────────────────────────
def bootstrap_state():
    uid = st.session_state.user_id
    state = db.get_user_state(uid)
    for k, v in state.items():
        if k != 'user_id':
            key = f"db_{k}"
            if key not in st.session_state:
                st.session_state[key] = v

    # Subjects
    if 'subjects' not in st.session_state:
        st.session_state.subjects = db.get_subjects(uid)

    # Today's plan_id
    if 'plan_id' not in st.session_state:
        st.session_state.plan_id = db.get_current_plan(uid)

    # Cached tasks list
    if 'tasks_cache' not in st.session_state:
        st.session_state.tasks_cache = db.get_plan_tasks(st.session_state.plan_id)

    # Raw plan text (for display fallback)
    if 'raw_plan_text' not in st.session_state:
        st.session_state.raw_plan_text = db.get_plan_text(st.session_state.plan_id)


def ss(key):
    """Shorthand to read DB-backed session state key."""
    return st.session_state.get(f"db_{key}")


def ss_set(key, value):
    """Write to session cache + persist to DB."""
    st.session_state[f"db_{key}"] = value
    db.update_user_state(st.session_state.user_id, {key: value})


# ─────────────────────────────────────────────
# Gemini Plan Generation
# ─────────────────────────────────────────────
def parse_tasks_from_response(text: str) -> list:
    """
    Parses Gemini output searching for lines like:
      TASK: Do something advanced | RESOURCE: https://...
    Falls back to treating every non-empty line beginning with '-' or a digit as a task.
    """
    tasks = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("TASK:"):
            parts = line[5:].split("|", 1)
            task_text = parts[0].strip()
            resource  = parts[1].replace("RESOURCE:", "").strip() if len(parts) > 1 else ""
            tasks.append({"task_text": task_text, "resource_link": resource})
        elif re.match(r'^[-*•\d]', line) and len(line) > 5:
            # Fallback: plain bullet/numbered list
            clean = re.sub(r'^[-*•\d+\.\)]+\s*', '', line)
            tasks.append({"task_text": clean, "resource_link": ""})

    # De-duplicate, limit to 5
    seen = set()
    unique = []
    for t in tasks:
        if t["task_text"] not in seen:
            seen.add(t["task_text"])
            unique.append(t)
    return unique[:5]


def generate_daily_plan():
    uid = st.session_state.user_id
    api_key = os.getenv("GEMINI_API_KEY") or st.session_state.get('api_key', '')
    if not api_key:
        return None, "Please provide a **GEMINI_API_KEY** in the sidebar to generate a plan."

    status      = ss('status')
    multiplier  = ss('difficulty_multiplier')
    goal        = ss('goal')
    avail_time  = ss('available_time')
    subjects    = st.session_state.subjects

    # ── Status-specific instruction ──
    if status == 'Burnout':
        dynamic_instruction = (
            "MINIMAL PLAN: Select ONLY 1-2 very light topics. Focus on simple revision or "
            "easy 10-min videos. Do NOT introduce anything new."
        )
        task_count = "2"
    elif status == 'Inconsistent':
        dynamic_instruction = (
            "REDUCED PLAN: Pick fewer topics. Replace hard concepts with shorter, easier tasks to rebuild momentum."
        )
        task_count = "3"
    elif status == 'High-Performance':
        dynamic_instruction = (
            "ADVANCED PLAN: Increase difficulty significantly. Add real projects, problem sets, or deep dives."
        )
        task_count = "4"
    elif status == 'Recovery':
        dynamic_instruction = (
            "RECOVERY PLAN: Gradually reintroduce normal content. Mix easy revision with one moderate new concept."
        )
        task_count = "3"
    else:
        dynamic_instruction = "NORMAL PLAN: Balance reading, revision, and hands-on practice."
        task_count = "3"

    # ── Contextual Memory: past 3 days ──
    past = db.get_past_completed_tasks(uid, limit=3)
    history_block = ""
    if past:
        lines = []
        for day in past:
            done_list = ", ".join(day['tasks']) if day['tasks'] else "none"
            lines.append(f"  • {day['date']} ({day['status']}): Completed — {done_list}")
        history_block = (
            "\nRECENT LEARNING HISTORY (do NOT repeat these; build upon them):\n"
            + "\n".join(lines)
            + "\n"
        )

    prompt = f"""You are an Adaptive AI Tutor generating a personalized daily study plan.

Student Profile:
- Goal: {goal}
- Time available today: {avail_time:.1f} hours
- Current status: {status} (difficulty multiplier: {multiplier}x)
- Study subjects: {', '.join(subjects)}
{history_block}
Today's Instruction: {dynamic_instruction}

Generate EXACTLY {task_count} specific, actionable study tasks.

STRICT OUTPUT FORMAT — each task on its own line:
TASK: [specific task description with estimated time in brackets, e.g., "Build a Python REST API (advanced) [45 min]"] | RESOURCE: [A real, relevant URL — official docs, YouTube search, or tutorial]

Rules:
1. Every line MUST start with "TASK:" and contain exactly one " | RESOURCE:" separator.
2. Time estimates must total approximately {avail_time:.1f} hours.
3. Tasks must be specific, not generic. Mention exact topics/concepts.
4. Resource links must be real URLs (docs, YouTube searches, tutorials).
5. Do NOT add any introductory or closing text — output only the TASK lines."""

    try:
        genai.configure(api_key=api_key)
        
        # Dynamically find an available model for this API key
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if not available_models:
            return None, "⚠️ API Error: Your API key does not have access to ANY text generation models. Please verify you are using a valid Google AI Studio key with the Generative Language API enabled."
            
        # Prefer flash, else fallback to whatever is first
        target_model = 'models/gemini-1.5-flash'
        if target_model not in available_models:
            target_model = available_models[0]
            
        model = genai.GenerativeModel(target_model)
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        tasks = parse_tasks_from_response(raw_text)
        if not tasks:
            # If parsing fails, fall back to raw text
            return None, raw_text
        return tasks, raw_text
    except Exception as e:
        return None, f"⚠️ API Error: {str(e)}"


# ─────────────────────────────────────────────
# Behavioral Logic Engine
# ─────────────────────────────────────────────
def evaluate_behavior(completion_pct: float):
    """Update state based on completion percentage (0.0 – 1.0)."""
    uid = st.session_state.user_id
    plan_id = st.session_state.plan_id
    status = ss('status')
    streak = ss('streak')
    missed = ss('missed_counts')
    progress = ss('progress')
    avail = ss('available_time')

    if completion_pct >= 0.7:
        # ── Treat as COMPLETED ──
        new_streak = streak + 1
        new_missed = 0
        new_progress = min(100.0, progress + 10 * completion_pct)
        db.update_plan_status(plan_id, 'completed')

        if new_streak >= 3:
            new_status = 'High-Performance'
            new_mult   = 1.2
            new_avail  = min(8.0, avail * 1.1)
            msg = f"🔥 High consistency! Streak: {new_streak}. Challenge level increased."
        elif status == 'Recovery':
            new_status = 'Normal'
            new_mult   = 1.0
            new_avail  = avail
            msg = "✅ Well done! Recovered. Back to normal pace."
        else:
            new_status = 'Normal'
            new_mult   = 1.0
            new_avail  = avail
            msg = f"✅ Great work! Streak: {new_streak}. Keep pushing!"
    else:
        # ── Treat as MISSED ──
        new_streak  = 0
        new_missed  = missed + 1
        new_progress = max(0.0, progress - 5.0 * (1 - completion_pct))
        db.update_plan_status(plan_id, 'missed')

        if new_missed >= 4:
            new_status = 'Burnout'
            new_mult   = 0.5
            new_avail  = max(0.5, avail * 0.5)
            msg = "🆘 Burnout detected! Switching to a minimal light-revision plan."
        elif new_missed >= 2:
            new_status = 'Inconsistent'
            new_mult   = 0.8
            new_avail  = max(0.5, avail * 0.8)
            msg = f"⚠️ Inconsistency detected ({new_missed} misses). Reducing load by 20%."
        else:
            new_status = 'Normal'
            new_mult   = 1.0
            new_avail  = avail
            msg = "📉 Minor setback. Let's recover tomorrow."

    # Persist all state changes
    ss_set('streak', new_streak)
    ss_set('missed_counts', new_missed)
    ss_set('progress', new_progress)
    ss_set('status', new_status)
    ss_set('difficulty_multiplier', new_mult)
    ss_set('available_time', new_avail)
    ss_set('current_logic_msg', msg)

    plan_date = db.get_plan_date(plan_id)
    db.record_progress(uid, new_progress, new_status, plan_date)


def simulate_state(target: str):
    uid = st.session_state.user_id
    if target == 'burnout':
        ss_set('streak', 0)
        ss_set('missed_counts', 4)
        ss_set('status', 'Burnout')
        ss_set('difficulty_multiplier', 0.5)
        ss_set('available_time', max(0.5, ss('available_time') * 0.5))
        ss_set('progress', max(0, ss('progress') - 15))
        ss_set('current_logic_msg', "🆘 Burnout Demo: Minimal plan with light revision only.")
    else:
        ss_set('streak', 1)
        ss_set('missed_counts', 0)
        ss_set('status', 'Recovery')
        ss_set('difficulty_multiplier', 0.8)
        ss_set('available_time', min(8.0, ss('available_time') * 1.2))
        ss_set('progress', min(100, ss('progress') + 15))
        ss_set('current_logic_msg', "🔄 Recovery Demo: Gradually reintroducing normal topics.")
        
    plan_date = db.get_plan_date(st.session_state.plan_id)
    db.record_progress(uid, ss('progress'), ss('status'), plan_date)


# ─────────────────────────────────────────────
# Glowing Status Box
# ─────────────────────────────────────────────
STATUS_META = {
    'Normal':           {'color': '#64ffda', 'icon': '🧠'},
    'High-Performance': {'color': '#00e676', 'icon': '🔥'},
    'Burnout':          {'color': '#ff5370', 'icon': '🆘'},
    'Inconsistent':     {'color': '#ffcb6b', 'icon': '⚠️'},
    'Recovery':         {'color': '#82aaff', 'icon': '🔄'},
}

def render_status_box():
    status = ss('status') or 'Normal'
    meta   = STATUS_META.get(status, STATUS_META['Normal'])
    color  = meta['color']
    icon   = meta['icon']
    msg    = ss('current_logic_msg') or '—'

    st.markdown(f"""
    <div class="ai-box" style="
        border: 1.5px solid {color};
        box-shadow: 0 0 28px {color}40;
        background: {color}0d;
    ">
        <h4 style="margin:0 0 6px; color:{color}; font-weight:700; font-size:15px;">
            {icon} AI Decision
        </h4>
        <p style="margin:0; color:#cdd9ff; font-size:14px;">{msg}</p>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Main Dashboard  
# ─────────────────────────────────────────────
def render_dashboard():
    uid = st.session_state.user_id

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(f"### 👋 Hey, **{st.session_state.user_name}**!")

        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        st.divider()
        st.markdown("### ⚙️ Configuration")
        api_key_input = st.text_input("Gemini API Key", type="password",
                                       value=st.session_state.get('api_key', ''))
        if api_key_input:
            st.session_state.api_key = api_key_input

        st.divider()
        st.markdown("### 📝 Learning Profile")

        # Goal
        new_goal = st.text_input("Learning Goal", value=ss('goal'))
        if new_goal != ss('goal'):
            ss_set('goal', new_goal)

        # Available time
        new_time = st.slider("Time Available Today (hrs)", 0.5, 8.0,
                             float(ss('available_time') or 2.0), step=0.5)
        if abs(new_time - (ss('available_time') or 2.0)) > 0.01:
            ss_set('available_time', new_time)

        st.divider()
        st.markdown("### 📚 Subjects")
        SUBJECT_POOL = [
            "Python", "AWS", "SQL", "Machine Learning", "Deep Learning",
            "React", "JavaScript", "TypeScript", "Docker", "Kubernetes",
            "Data Structures", "Algorithms", "System Design",
            "FastAPI", "Django", "Statistics", "Linear Algebra",
        ]
        all_opts = list(set(SUBJECT_POOL + (st.session_state.subjects or [])))
        new_subjects = st.multiselect(
            "Select your subjects",
            options=sorted(all_opts),
            default=st.session_state.subjects,
        )
        custom = st.text_input("➕ Add custom subject", placeholder="e.g. Rust")
        if custom and custom not in new_subjects:
            new_subjects.append(custom)

        if set(new_subjects) != set(st.session_state.subjects):
            st.session_state.subjects = new_subjects
            db.set_subjects(uid, new_subjects)

        st.divider()
        st.markdown("### 🛠️ Demo Tools")
        st.button("🆘 Simulate Burnout", on_click=simulate_state, args=('burnout',), use_container_width=True)
        st.button("🔄 Simulate Recovery", on_click=simulate_state, args=('recovery',), use_container_width=True)

    # ── Header ──
    col_h, col_logout = st.columns([5, 1])
    with col_h:
        st.markdown("""
        <h1 style='font-size:30px; font-weight:800; color:#cdd9ff; margin-bottom:4px;'>
            🧠 Adaptive Learning Companion
        </h1>
        <p style='color:#8892b0; font-size:14px; margin:0;'>
            Your AI coach that adapts to your pace, detects burnout, and builds you a smarter plan every day.
        </p>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Metric Cards ──
    status  = ss('status') or 'Normal'
    meta    = STATUS_META.get(status, STATUS_META['Normal'])
    col1, col2, col3, col4 = st.columns(4)

    cards = [
        ("🔥 Streak", f"{ss('streak') or 0} days", meta['color']),
        ("❌ Misses",  f"{ss('missed_counts') or 0}",          "#ff5370"),
        (f"{meta['icon']} Status",  status,               meta['color']),
        ("⚡ Difficulty", f"{ss('difficulty_multiplier') or 1.0}x", "#ffcb6b"),
    ]
    for col, (label, value, color) in zip([col1, col2, col3, col4], cards):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value" style="color:{color};">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Progress Bar ──
    prog = ss('progress') or 0.0
    st.markdown("**📊 Overall Progress Journey**")
    st.progress(int(min(100, max(0, prog))),
                text=f"{prog:.1f}% complete")

    st.divider()

    # ── AI Intelligence Layer ──
    st.markdown("## 🤖 Intelligence Layer")
    render_status_box()

    # Re-generate plan button
    c1, c2 = st.columns([4, 1])
    with c2:
        regen = st.button("🔄 New Plan", use_container_width=True, type="primary")

    # Generate plan if none exists or user clicked regen
    if regen or (not st.session_state.tasks_cache and not st.session_state.raw_plan_text):
        api_key = os.getenv("GEMINI_API_KEY") or st.session_state.get('api_key', '')
        if not api_key:
            st.info("👋 Please add your Gemini API key in the sidebar to generate a plan.")
        else:
            with st.spinner("✨ Generating your personalised plan..."):
                tasks, raw_text = generate_daily_plan()
            if tasks:
                plan_id = st.session_state.plan_id
                db.save_plan_tasks(plan_id, tasks)
                db.update_plan_text(plan_id, raw_text)
                st.session_state.tasks_cache  = db.get_plan_tasks(plan_id)
                st.session_state.raw_plan_text = raw_text
                st.rerun()
            else:
                st.session_state.raw_plan_text = raw_text  # store error / raw fallback
                st.rerun()

    # ── Render Tasks as Checkboxes ──
    st.markdown("### 📋 Today's Action Plan")
    tasks_cache = st.session_state.tasks_cache

    if tasks_cache:
        completed_count = 0
        for task in tasks_cache:
            t_id       = task['id']
            t_text     = task['task_text']
            t_link     = task['resource_link']
            t_done     = bool(task['is_completed'])

            col_chk, col_task = st.columns([0.05, 0.95])
            with col_chk:
                checked = st.checkbox("", value=t_done, key=f"task_{t_id}", label_visibility="collapsed")
                if checked != t_done:
                    db.update_task_completion(t_id, checked)
                    # Update local cache
                    for i, t in enumerate(st.session_state.tasks_cache):
                        if t['id'] == t_id:
                            st.session_state.tasks_cache[i]['is_completed'] = 1 if checked else 0
                    st.rerun()

            with col_task:
                link_part = ""
                if t_link:
                    link_part = f" &nbsp;→&nbsp; <a href='{t_link}' target='_blank' style='color:#64ffda; font-size:12px;'>📎 Resource</a>"
                if checked:
                    st.markdown(
                        f"<p style='margin:6px 0; text-decoration:line-through; color:#4a5568;'>"
                        f"~~{t_text}~~{link_part}</p>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<p style='margin:6px 0; color:#cdd9ff;'>{t_text}{link_part}</p>",
                        unsafe_allow_html=True
                    )

            if checked:
                completed_count += 1

        # ── Completion Summary ──
        total = len(tasks_cache)
        pct   = completed_count / total if total > 0 else 0
        pct_label = f"{completed_count}/{total} tasks ({int(pct*100)}%)"

        bar_col = "#00e676" if pct >= 0.7 else ("#ffcb6b" if pct >= 0.4 else "#ff5370")
        st.markdown(f"""
        <div style='margin:15px 0 5px; font-size:13px; color:#8892b0;'>
            Daily completion: <strong style='color:{bar_col};'>{pct_label}</strong>
        </div>
        """, unsafe_allow_html=True)

    elif st.session_state.raw_plan_text:
        # Fallback raw text display (if Gemini didn't follow strict format)
        st.markdown(st.session_state.raw_plan_text)
    else:
        st.info("👋 Add your Gemini API Key in the sidebar and click **New Plan** to get started!")

    st.divider()

    # ── Daily Check-in ──
    st.markdown("## 🎯 Daily Check-in")
    st.markdown("<p style='color:#8892b0; font-size:13px;'>Mark your day once you're done. "
                "≥70% tasks = Completed. &lt;70% = Missed.</p>", unsafe_allow_html=True)

    tasks_now = st.session_state.tasks_cache
    total_tasks = len(tasks_now)
    done_count  = sum(1 for t in tasks_now if t.get('is_completed'))
    current_pct = (done_count / total_tasks) if total_tasks > 0 else 0.0

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("✅ Submit Day as Completed", use_container_width=True, type="primary"):
            evaluate_behavior(max(current_pct, 0.7))
            st.session_state.plan_id     = db.get_current_plan(uid)
            st.session_state.tasks_cache = []
            st.session_state.raw_plan_text = ''
            st.success("🎉 Day logged as completed! Generating tomorrow's plan...")
            st.rerun()
    with col_b2:
        if st.button("❌ Submit Day as Missed", use_container_width=True):
            evaluate_behavior(min(current_pct, 0.3))
            st.session_state.plan_id     = db.get_current_plan(uid)
            st.session_state.tasks_cache = []
            st.session_state.raw_plan_text = ''
            st.warning("📉 Day logged as missed. Adjusting tomorrow's plan...")
            st.rerun()

    st.divider()

    # ── Analytics Dashboard ──
    st.markdown("## 📈 Analytics Dashboard")
    history = db.get_progress_history(uid, limit=30)

    if history:
        df = pd.DataFrame(history)
        df['record_date'] = pd.to_datetime(df['record_date'])

        tab_progress, tab_status, tab_streak = st.tabs(
            ["📊 Progress Journey", "🏷️ Status Distribution", "🔥 Streak Timeline"]
        )

        with tab_progress:
            fig = px.area(
                df, x='record_date', y='progress_value',
                color_discrete_sequence=['#64ffda'],
                labels={'record_date': 'Date', 'progress_value': 'Progress (%)'},
                title='Your Progress Over Time'
            )
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(20,25,40,0.6)',
                font_color='#cdd9ff',
                title_font_size=15,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(range=[0, 105], gridcolor='#1e2535'),
                xaxis=dict(gridcolor='#1e2535'),
            )
            fig.update_traces(line_color='#64ffda', fillcolor='rgba(100,255,218,0.1)')
            st.plotly_chart(fig, use_container_width=True)

        with tab_status:
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Days']
            STATUS_COLORS = {
                'Normal': '#64ffda', 'High-Performance': '#00e676',
                'Burnout': '#ff5370', 'Inconsistent': '#ffcb6b', 'Recovery': '#82aaff'
            }
            colors = [STATUS_COLORS.get(s, '#8892b0') for s in status_counts['Status']]
            fig2 = go.Figure(go.Pie(
                labels=status_counts['Status'],
                values=status_counts['Days'],
                hole=0.5,
                marker_colors=colors,
                textfont_size=13,
            ))
            fig2.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='#cdd9ff',
                title='Days in Each Status',
                title_font_size=15,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

        with tab_streak:
            fig3 = px.bar(
                df, x='record_date', y='progress_value',
                color='status',
                color_discrete_map=STATUS_COLORS,
                labels={'record_date': 'Date', 'progress_value': 'Progress', 'status': 'Status'},
                title='Daily Progress by Status'
            )
            fig3.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(20,25,40,0.6)',
                font_color='#cdd9ff',
                title_font_size=15,
                margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(gridcolor='#1e2535'),
                xaxis=dict(gridcolor='#1e2535'),
            )
            st.plotly_chart(fig3, use_container_width=True)

    else:
        st.info("📊 Submit a few days to unlock your analytics dashboard!")


# ─────────────────────────────────────────────
# App Entry Point
# ─────────────────────────────────────────────
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    render_auth()
else:
    bootstrap_state()
    render_dashboard()
