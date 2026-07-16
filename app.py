import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Neural Forge",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap');

/* ── Canvas — Aurora Mesh with grain texture ──────────────────────────── */
.stApp {
    font-family: 'Inter', sans-serif;
    background-color: #0d1121;
    background-image:
        /* grain noise for texture depth — makes it feel like a real image */
        url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.045'/%3E%3C/svg%3E"),
        /* vivid aurora gradient orbs */
        radial-gradient(ellipse at 5%   5%,  rgba(124, 58,237,0.60) 0%, transparent 50%),
        radial-gradient(ellipse at 95%  5%,  rgba( 14,165,233,0.50) 0%, transparent 50%),
        radial-gradient(ellipse at 95% 95%,  rgba(236, 72,153,0.38) 0%, transparent 50%),
        radial-gradient(ellipse at  5% 95%,  rgba( 79, 70,229,0.45) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 48%,  rgba(139, 92,246,0.18) 0%, transparent 55%);
    background-size: 256px 256px, 100%, 100%, 100%, 100%, 100%;
    background-attachment: fixed;
}
/* ── Hide Streamlit chrome ────────────────────────────────────────────── */
header[data-testid="stHeader"] { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="stSidebarHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
}

/* ── Main content panel — floats over background ─────────────────────── */
/* NOTE: no backdrop-filter here — it would create a new containing block  */
/* for position:fixed children, clipping the neural canvas to half-page.  */
[data-testid="stMainBlockContainer"] > div:first-child,
section[data-testid="stMain"] > div:first-child {
    background: rgba(255,255,255,0.025);
    border-left: 1px solid rgba(255,255,255,0.06);
    border-right: 1px solid rgba(255,255,255,0.06);
}

/* ── Sidebar shell ────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: rgba(11,14,27,0.94) !important;
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(139,92,246,0.20);
    box-shadow: 4px 0 32px rgba(0,0,0,0.45);
}
[data-testid="stSidebar"] * { font-family: 'Inter', sans-serif !important; }

/* Nav item base */
[data-testid="stSidebarNav"] a {
    border-radius: 8px !important;
    margin: 2px 8px !important;
    padding: 9px 12px !important;
    transition: all 0.25s ease, box-shadow 0.25s ease !important;
    color: #475569 !important;
    border-left: 3px solid transparent !important;
}

/* ── Per-page hover glows ─────────────────────────────────────────────── */
/* 1 Monitor Pipelines — emerald */
[data-testid="stSidebarNav"] li:nth-child(1) a:not([aria-current="page"]):hover {
    background: rgba(52,211,153,0.09) !important;
    color: #6ee7b7 !important;
    border-left-color: rgba(52,211,153,0.45) !important;
    box-shadow: inset 0 0 22px rgba(52,211,153,0.05) !important;
    transform: translateX(3px);
}
/* 2 Data Explorer — violet */
[data-testid="stSidebarNav"] li:nth-child(2) a:not([aria-current="page"]):hover {
    background: rgba(139,92,246,0.10) !important;
    color: #c4b5fd !important;
    border-left-color: rgba(139,92,246,0.50) !important;
    box-shadow: inset 0 0 22px rgba(139,92,246,0.07) !important;
    transform: translateX(3px);
}
/* 3 Bronze & Silver — slate/silver */
[data-testid="stSidebarNav"] li:nth-child(3) a:not([aria-current="page"]):hover {
    background: rgba(148,163,184,0.09) !important;
    color: #e2e8f0 !important;
    border-left-color: rgba(148,163,184,0.45) !important;
    box-shadow: inset 0 0 22px rgba(148,163,184,0.05) !important;
    transform: translateX(3px);
}
/* 4 Gold Builder — amber/gold */
[data-testid="stSidebarNav"] li:nth-child(4) a:not([aria-current="page"]):hover {
    background: rgba(251,191,36,0.09) !important;
    color: #fde68a !important;
    border-left-color: rgba(251,191,36,0.50) !important;
    box-shadow: inset 0 0 22px rgba(251,191,36,0.06) !important;
    transform: translateX(3px);
}
/* 5 Gold Agent — cyan */
[data-testid="stSidebarNav"] li:nth-child(5) a:not([aria-current="page"]):hover {
    background: rgba(34,211,238,0.09) !important;
    color: #a5f3fc !important;
    border-left-color: rgba(34,211,238,0.50) !important;
    box-shadow: inset 0 0 22px rgba(34,211,238,0.06) !important;
    transform: translateX(3px);
}

/* ── Per-page active states ───────────────────────────────────────────── */
/* 1 Monitor Pipelines */
[data-testid="stSidebarNav"] li:nth-child(1) a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(52,211,153,0.14) 0%, rgba(52,211,153,0.02) 100%) !important;
    border-left: 3px solid #34d399 !important;
    color: #6ee7b7 !important; font-weight: 600;
    box-shadow: inset 0 0 24px rgba(52,211,153,0.08), 0 2px 14px rgba(0,0,0,0.14) !important;
}
/* 2 Data Explorer */
[data-testid="stSidebarNav"] li:nth-child(2) a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(139,92,246,0.16) 0%, rgba(139,92,246,0.02) 100%) !important;
    border-left: 3px solid #a78bfa !important;
    color: #c4b5fd !important; font-weight: 600;
    box-shadow: inset 0 0 24px rgba(139,92,246,0.09), 0 2px 14px rgba(0,0,0,0.14) !important;
}
/* 3 Bronze & Silver */
[data-testid="stSidebarNav"] li:nth-child(3) a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(148,163,184,0.14) 0%, rgba(148,163,184,0.02) 100%) !important;
    border-left: 3px solid #94a3b8 !important;
    color: #e2e8f0 !important; font-weight: 600;
    box-shadow: inset 0 0 24px rgba(148,163,184,0.07), 0 2px 14px rgba(0,0,0,0.14) !important;
}
/* 4 Gold Builder */
[data-testid="stSidebarNav"] li:nth-child(4) a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(212,163,89,0.16) 0%, rgba(212,163,89,0.02) 100%) !important;
    border-left: 3px solid #f59e0b !important;
    color: #fbbf24 !important; font-weight: 600;
    box-shadow: inset 0 0 24px rgba(212,163,89,0.09), 0 2px 14px rgba(0,0,0,0.14) !important;
}
/* 5 Gold Agent */
[data-testid="stSidebarNav"] li:nth-child(5) a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(34,211,238,0.12) 0%, rgba(34,211,238,0.02) 100%) !important;
    border-left: 3px solid #22d3ee !important;
    color: #a5f3fc !important; font-weight: 600;
    box-shadow: inset 0 0 24px rgba(34,211,238,0.07), 0 2px 14px rgba(0,0,0,0.14) !important;
}

/* ── Typography ───────────────────────────────────────────────────────── */
h1, h2, h3, h4 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #f1f5f9 !important;
    letter-spacing: -0.02em;
}
h1 { font-size: 1.9rem !important; font-weight: 700 !important; }
h2 { font-size: 1.4rem !important; font-weight: 600 !important; }
h3 { font-size: 1.1rem !important; font-weight: 600 !important; }
p, li, span, label, div {
    color: #94a3b8;
    font-family: 'Inter', sans-serif;
}
.stMarkdown p { color: #94a3b8; }
strong { color: #c4b5fd !important; }
code {
    font-family: 'JetBrains Mono', monospace !important;
    background: rgba(139,92,246,0.12) !important;
    color: #86efac !important;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 0.85em;
}
pre {
    background: rgba(11,14,28,0.92) !important;
    border: 1px solid rgba(139,92,246,0.18) !important;
    border-radius: 10px !important;
}

/* ── Glass Cards / Containers ─────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.055) !important;
    backdrop-filter: blur(18px);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    padding: 1rem 1.25rem !important;
    transition: all 0.25s ease;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(167,139,250,0.40);
    box-shadow: 0 0 24px rgba(139,92,246,0.15);
    transform: translateY(-1px);
}
[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 0.78rem !important; text-transform: uppercase; letter-spacing: 0.06em; }
[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #c4b5fd !important;
}
[data-testid="stMetricDelta"] { font-family: 'JetBrains Mono', monospace !important; font-size: 0.8rem !important; }

[data-testid="stExpander"] {
    background: rgba(255,255,255,0.03) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.18) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
[data-testid="stExpander"]:hover {
    border-color: rgba(167,139,250,0.22) !important;
    box-shadow: 0 4px 28px rgba(0,0,0,0.22) !important;
}
[data-testid="stExpander"] summary {
    color: #c4b5fd !important;
    font-weight: 500;
}

/* ── Buttons ──────────────────────────────────────────────────────────── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    border: 1px solid rgba(139,92,246,0.30) !important;
    background: rgba(139,92,246,0.08) !important;
    color: #c4b5fd !important;
}
.stButton > button:hover {
    border-color: #a78bfa !important;
    background: rgba(139,92,246,0.16) !important;
    color: #ddd6fe !important;
    box-shadow: 0 0 18px rgba(139,92,246,0.28) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(124,58,237,0.28), rgba(14,165,233,0.18)) !important;
    border: 1px solid #a78bfa !important;
    color: #ddd6fe !important;
    font-weight: 600 !important;
    box-shadow: 0 0 14px rgba(139,92,246,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 0 30px rgba(139,92,246,0.50) !important;
    transform: translateY(-2px) !important;
}

/* ── Inputs ───────────────────────────────────────────────────────────── */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background: rgba(255,255,255,0.09) !important;
    border: 1.5px solid rgba(139,92,246,0.50) !important;
    border-radius: 8px !important;
    color: #f1f5f9 !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    transition: all 0.25s ease !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder,
.stNumberInput input::placeholder {
    color: #64748b !important;
    font-weight: 400 !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    background: rgba(255,255,255,0.13) !important;
    border-color: transparent !important;
    box-shadow:
        0 0 0 1.5px #a78bfa,
        0 0 0 4px rgba(139,92,246,0.18),
        0 0 20px rgba(139,92,246,0.20) !important;
    outline: none !important;
}
.stTextArea textarea {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    line-height: 1.6 !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background: rgba(255,255,255,0.09) !important;
    border: 1.5px solid rgba(139,92,246,0.50) !important;
    border-radius: 8px !important;
    color: #f1f5f9 !important;
}
.stSelectbox > div > div:focus-within {
    border-color: transparent !important;
    box-shadow:
        0 0 0 1.5px #a78bfa,
        0 0 0 4px rgba(139,92,246,0.18) !important;
}
/* Bold selected value text */
.stSelectbox [data-baseweb="select"] *:not(svg):not(path),
[data-testid="stSidebar"] [data-baseweb="select"] *:not(svg):not(path) {
    font-weight: 700 !important;
}
/* Sidebar selectbox box styling */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.09) !important;
    border: 1.5px solid rgba(139,92,246,0.50) !important;
    border-radius: 8px !important;
}
/* Placeholder text */
.stSelectbox [data-baseweb="select"] input::placeholder {
    font-weight: 400 !important;
}
/* Dropdown menu list */
[data-baseweb="popover"] li,
[data-baseweb="menu"] li,
[role="option"] {
    background: rgba(18,18,32,0.97) !important;
    color: #e2e8f0 !important;
    font-weight: 500 !important;
}
[role="option"]:hover,
[data-baseweb="menu"] li:hover {
    background: rgba(139,92,246,0.20) !important;
    color: #ddd6fe !important;
}

/* Slider */
.stSlider [data-testid="stSlider"] > div {
    color: #94a3b8 !important;
}
.stSlider [role="slider"] {
    background: #a78bfa !important;
    box-shadow: 0 0 8px rgba(167,139,250,0.55) !important;
}
.stSlider [data-baseweb="slider"] div[role="progressbar"] {
    background: linear-gradient(90deg, #a78bfa, #38bdf8) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid rgba(139,92,246,0.16) !important;
    gap: 4px;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    color: #64748b !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 8px 16px !important;
    transition: all 0.2s ease !important;
    background: transparent !important;
    border: none !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
    color: #c4b5fd !important;
    background: rgba(139,92,246,0.06) !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #c4b5fd !important;
    font-weight: 600 !important;
    border-bottom: 2px solid #a78bfa !important;
    background: rgba(139,92,246,0.08) !important;
}

/* ── Dataframe / Tables ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(139,92,246,0.15) !important;
    border-radius: 10px !important;
    overflow: hidden;
}
[data-testid="stDataFrame"] iframe {
    border-radius: 10px !important;
}

/* ── Alerts / Info boxes ──────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 3px !important;
    backdrop-filter: blur(8px) !important;
}
[data-testid="stAlert"][data-baseweb="notification"] {
    background: rgba(255,255,255,0.05) !important;
}
.stInfo {
    background: rgba(56,189,248,0.07) !important;
    border-left-color: #38bdf8 !important;
    color: #bae6fd !important;
}
.stSuccess {
    background: rgba(52,211,153,0.07) !important;
    border-left-color: #34d399 !important;
    color: #a7f3d0 !important;
}
.stWarning {
    background: rgba(251,191,36,0.07) !important;
    border-left-color: #fbbf24 !important;
    color: #fde68a !important;
}
.stError {
    background: rgba(248,113,113,0.07) !important;
    border-left-color: #f87171 !important;
    color: #fecaca !important;
}

/* ── Chat messages (Gold Agent) ───────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 12px !important;
    margin-bottom: 6px !important;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    border-left: 3px solid #f472b6 !important;
}
[data-testid="stChatMessage"][data-testid*="assistant"] {
    border-left: 3px solid #a78bfa !important;
}

/* ── Dividers ─────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid rgba(139,92,246,0.14) !important;
    margin: 1rem 0 !important;
}

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(13,17,33,0.60); }
::-webkit-scrollbar-thumb { background: rgba(139,92,246,0.30); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(139,92,246,0.55); }

/* ── Caption / small text ─────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #475569 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
}

/* ── JSON display ─────────────────────────────────────────────────────── */
[data-testid="stJson"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(139,92,246,0.14) !important;
    border-radius: 10px !important;
}

/* ── Forms ────────────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: rgba(255,255,255,0.03) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.16) !important;
}

/* ── Checkboxes ───────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] input[type="checkbox"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 17px !important;
    height: 17px !important;
    border-radius: 5px !important;
    border: 1.5px solid rgba(139,92,246,0.38) !important;
    background: rgba(15,12,30,0.60) !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    position: relative !important;
    flex-shrink: 0 !important;
}
[data-testid="stCheckbox"] input[type="checkbox"]:hover {
    border-color: rgba(167,139,250,0.65) !important;
    box-shadow: 0 0 8px rgba(139,92,246,0.25) !important;
}
[data-testid="stCheckbox"] input[type="checkbox"]:checked {
    background: linear-gradient(135deg, #7c3aed, #38bdf8) !important;
    border-color: transparent !important;
    box-shadow: 0 0 14px rgba(139,92,246,0.55), 0 0 4px rgba(56,189,248,0.30) !important;
    background-image:
        linear-gradient(135deg, #7c3aed, #38bdf8),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2 6.5l3 3 5-5.5' stroke='white' stroke-width='1.8' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") !important;
    background-size: cover, 10px !important;
    background-repeat: no-repeat, no-repeat !important;
    background-position: center, center !important;
}

/* ── Table headers (markdown tables in pipeline docs / plan summary) ─── */
table {
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    width: 100% !important;
    background: rgba(255,255,255,0.02) !important;
    border-collapse: separate !important;
    border-spacing: 0 !important;
}
table th {
    color: #e2e8f0 !important;
    font-size: 0.71rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    padding: 10px 14px !important;
    background: rgba(139,92,246,0.10) !important;
    border-bottom: 1px solid rgba(139,92,246,0.22) !important;
    white-space: nowrap !important;
}
table td {
    color: #94a3b8 !important;
    padding: 8px 14px !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
    font-size: 0.88rem !important;
}
table tr:last-child td {
    border-bottom: none !important;
}
table tr:hover td {
    background: rgba(139,92,246,0.05) !important;
    color: #cbd5e1 !important;
}

/* ── Spinner ──────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
    border-color: #a78bfa transparent transparent transparent !important;
}

/* ── Layer color helpers ──────────────────────────────────────────────── */
.badge-bronze { color: #fb923c; font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; background: rgba(251,146,60,0.14); padding: 2px 8px; border-radius: 4px; }
.badge-silver { color: #c4b5fd; font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; background: rgba(196,181,253,0.12); padding: 2px 8px; border-radius: 4px; }
.badge-gold   { color: #fbbf24; font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; background: rgba(251,191,36,0.12); padding: 2px 8px; border-radius: 4px; }

/* ── Hide Streamlit's auto-generated nav (we build our own below) ─────── */
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Page link nav items ──────────────────────────────────────────────── */
[data-testid="stPageLink"] a {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    border-radius: 8px !important;
    margin: 2px 0 !important;
    padding: 9px 12px !important;
    text-decoration: none !important;
    color: #64748b !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    border-left: 3px solid transparent !important;
    transition: all 0.2s ease !important;
}
[data-testid="stPageLink"] a:hover {
    background: rgba(139,92,246,0.09) !important;
    color: #c4b5fd !important;
    border-left-color: rgba(139,92,246,0.45) !important;
    transform: translateX(3px) !important;
}
[data-testid="stPageLink"] a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(139,92,246,0.16) 0%, rgba(139,92,246,0.02) 100%) !important;
    border-left: 3px solid #a78bfa !important;
    color: #c4b5fd !important;
    font-weight: 600 !important;
}
/* Remove default margins around page link containers */
[data-testid="stSidebarContent"] [data-testid="stPageLink"] {
    margin: 0 !important;
    padding: 0 !important;
}

/* ── Sidebar brand block ──────────────────────────────────────────────── */
.nb-brand {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 14px 16px 12px;
    margin: 12px 12px 6px;
    background: linear-gradient(135deg, rgba(124,58,237,0.10), rgba(14,165,233,0.04));
    border: 1px solid rgba(139,92,246,0.16);
    border-radius: 10px;
}
.nb-brand-icon {
    font-size: 1.6rem;
    background: linear-gradient(135deg, #a78bfa, #38bdf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 6px rgba(139,92,246,0.50));
    line-height: 1;
    flex-shrink: 0;
}
.nb-brand-name {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.14em !important;
    color: #e2e8f0 !important;
    line-height: 1;
}
.nb-brand-tag {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.60rem !important;
    color: #34d399 !important;
    letter-spacing: 0.08em !important;
    margin-top: 4px;
}

/* ── Sidebar status widget ────────────────────────────────────────────── */
.nb-status-widget {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 14px;
    margin: 20px 12px 10px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(52,211,153,0.18);
    border-radius: 10px;
    backdrop-filter: blur(8px);
}
.nb-status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #34d399;
    flex-shrink: 0;
    animation: nb-dot-pulse 2.5s ease-in-out infinite;
}
.nb-status-title {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.62rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.11em !important;
    color: #34d399 !important;
    text-transform: uppercase;
}
.nb-status-text {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.70rem !important;
    color: #475569 !important;
    margin-top: 2px;
}

/* ── Animations ───────────────────────────────────────────────────────── */
@keyframes nb-dot-pulse {
    0%, 100% { box-shadow: 0 0 5px #34d399, 0 0 10px rgba(52,211,153,0.35); opacity: 1; }
    50%       { box-shadow: 0 0 9px #34d399, 0 0 20px rgba(52,211,153,0.55); opacity: 0.75; }
}
@keyframes glow-pulse {
    0%, 100% { box-shadow: 0 0 8px rgba(139,92,246,0.22); }
    50%       { box-shadow: 0 0 24px rgba(139,92,246,0.55); }
}
@keyframes sweep-right {
    0%   { background-position: -200% center; }
    100% { background-position: 200% center; }
}
@keyframes fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
.stApp [data-testid="stVerticalBlock"] {
    animation: fade-up 0.3s ease-out;
}

/* ── Neural canvas (global — all pages including login) ──────────────── */
.nf-neural-canvas {
    position: fixed; inset: 0;
    z-index: 1; pointer-events: none; overflow: hidden;
}
.nf-neural-canvas svg { width: 100%; height: 100%; }
.nf-edge { stroke-width: 1; fill: none; stroke-dasharray: 6 6; }
.nf-edge-v { stroke: rgba(139,92,246,0.22); animation: flow-edge 4s linear infinite; }
.nf-edge-c { stroke: rgba(14,165,233,0.18);  animation: flow-edge 5s linear infinite; }
.nf-edge-p { stroke: rgba(236,72,153,0.14);  animation: flow-edge 6s linear infinite; }
@keyframes flow-edge { to { stroke-dashoffset: -24; } }
.nf-node-ring-v, .nf-node-ring-c, .nf-node-ring-p { fill: none; }
.nf-node-ring-v { stroke: rgba(167,139,250,0.40); stroke-width: 1; animation: ring-fade 3.0s ease-in-out infinite alternate; }
.nf-node-ring-c { stroke: rgba(56,189,248,0.35);  stroke-width: 1; animation: ring-fade 3.5s ease-in-out infinite alternate; }
.nf-node-ring-p { stroke: rgba(244,114,182,0.30); stroke-width: 1; animation: ring-fade 4.0s ease-in-out infinite alternate; }
@keyframes ring-fade { from { opacity: 0.7; } to { opacity: 0.1; } }
.nf-node-core-v { fill: rgba(139,92,246,0.55); animation: core-glow-v 3.0s ease-in-out infinite alternate; }
.nf-node-core-c { fill: rgba(14,165,233,0.55);  animation: core-glow-c 3.5s ease-in-out infinite alternate; }
.nf-node-core-p { fill: rgba(236,72,153,0.50);  animation: core-glow-p 4.0s ease-in-out infinite alternate; }
@keyframes core-glow-v {
    from { opacity: 0.5; filter: drop-shadow(0 0 3px rgba(139,92,246,0.60)); }
    to   { opacity: 1.0; filter: drop-shadow(0 0 9px rgba(167,139,250,1.00)); }
}
@keyframes core-glow-c {
    from { opacity: 0.5; filter: drop-shadow(0 0 3px rgba(14,165,233,0.60)); }
    to   { opacity: 1.0; filter: drop-shadow(0 0 9px rgba(56,189,248,1.00)); }
}
@keyframes core-glow-p {
    from { opacity: 0.5; filter: drop-shadow(0 0 3px rgba(236,72,153,0.55)); }
    to   { opacity: 1.0; filter: drop-shadow(0 0 9px rgba(244,114,182,0.95)); }
}

/* ── Logout button — fixed top-right ─────────────────────────────────── */
.st-key-nf_logout {
    position: fixed !important;
    top: 14px !important;
    right: 24px !important;
    z-index: 9999 !important;
    width: auto !important;
}
.st-key-nf_logout > div { width: auto !important; }
.st-key-nf_logout button {
    background: rgba(239,68,68,0.10) !important;
    border: 1px solid rgba(239,68,68,0.28) !important;
    color: #fca5a5 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.07em !important;
    padding: 5px 13px !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    transform: none !important;
}
.st-key-nf_logout button:hover {
    background: rgba(239,68,68,0.22) !important;
    border-color: rgba(239,68,68,0.55) !important;
    box-shadow: 0 0 14px rgba(239,68,68,0.28) !important;
    color: #fecaca !important;
    transform: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── Neural canvas (injected once — visible on every page) ────────────────────
st.markdown("""
<div class="nf-neural-canvas">
<svg viewBox="0 0 1400 800" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <g class="nf-edges">
    <line class="nf-edge nf-edge-v" x1="60" y1="180" x2="240" y2="110" style="animation-delay:0.0s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="180" x2="240" y2="260" style="animation-delay:0.5s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="350" x2="240" y2="260" style="animation-delay:0.3s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="350" x2="240" y2="420" style="animation-delay:0.8s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="350" x2="240" y2="570" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="530" x2="240" y2="420" style="animation-delay:0.6s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="530" x2="240" y2="570" style="animation-delay:1.0s"/>
    <line class="nf-edge nf-edge-v" x1="60" y1="530" x2="240" y2="700" style="animation-delay:0.4s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="110" x2="450" y2="140" style="animation-delay:0.1s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="110" x2="450" y2="290" style="animation-delay:0.7s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="260" x2="450" y2="140" style="animation-delay:0.9s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="260" x2="450" y2="290" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="260" x2="450" y2="440" style="animation-delay:0.5s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="420" x2="450" y2="290" style="animation-delay:0.8s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="420" x2="450" y2="440" style="animation-delay:0.3s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="420" x2="450" y2="590" style="animation-delay:0.6s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="570" x2="450" y2="440" style="animation-delay:1.1s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="570" x2="450" y2="590" style="animation-delay:0.4s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="570" x2="450" y2="700" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="700" x2="450" y2="590" style="animation-delay:0.9s"/>
    <line class="nf-edge nf-edge-c" x1="240" y1="700" x2="450" y2="700" style="animation-delay:0.1s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="140" x2="660" y2="190" style="animation-delay:0.3s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="140" x2="660" y2="360" style="animation-delay:0.7s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="290" x2="660" y2="190" style="animation-delay:0.5s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="290" x2="660" y2="360" style="animation-delay:0.1s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="290" x2="660" y2="530" style="animation-delay:0.9s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="440" x2="660" y2="360" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="440" x2="660" y2="530" style="animation-delay:0.6s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="590" x2="660" y2="530" style="animation-delay:0.4s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="590" x2="660" y2="680" style="animation-delay:0.8s"/>
    <line class="nf-edge nf-edge-v" x1="450" y1="700" x2="660" y2="680" style="animation-delay:0.3s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="190" x2="880" y2="260" style="animation-delay:0.6s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="360" x2="880" y2="260" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="360" x2="880" y2="440" style="animation-delay:0.9s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="530" x2="880" y2="440" style="animation-delay:0.4s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="530" x2="880" y2="590" style="animation-delay:0.1s"/>
    <line class="nf-edge nf-edge-p" x1="660" y1="680" x2="880" y2="590" style="animation-delay:0.7s"/>
    <line class="nf-edge nf-edge-c" x1="880" y1="260" x2="1080" y2="320" style="animation-delay:0.5s"/>
    <line class="nf-edge nf-edge-c" x1="880" y1="440" x2="1080" y2="320" style="animation-delay:0.3s"/>
    <line class="nf-edge nf-edge-c" x1="880" y1="440" x2="1080" y2="510" style="animation-delay:0.8s"/>
    <line class="nf-edge nf-edge-c" x1="880" y1="590" x2="1080" y2="510" style="animation-delay:0.2s"/>
    <line class="nf-edge nf-edge-v" x1="1080" y1="320" x2="1300" y2="390" style="animation-delay:0.4s"/>
    <line class="nf-edge nf-edge-v" x1="1080" y1="510" x2="1300" y2="390" style="animation-delay:0.6s"/>
  </g>
  <g class="nf-nodes">
    <circle class="nf-node-ring-v" cx="60" cy="180" r="13"/><circle class="nf-node-core-v" cx="60" cy="180" r="5" style="animation-delay:0.1s"/>
    <circle class="nf-node-ring-v" cx="60" cy="350" r="13" style="animation-delay:0.4s"/><circle class="nf-node-core-v" cx="60" cy="350" r="5" style="animation-delay:0.4s"/>
    <circle class="nf-node-ring-v" cx="60" cy="530" r="13" style="animation-delay:0.7s"/><circle class="nf-node-core-v" cx="60" cy="530" r="5" style="animation-delay:0.7s"/>
    <circle class="nf-node-ring-c" cx="240" cy="110" r="13"/><circle class="nf-node-core-c" cx="240" cy="110" r="5" style="animation-delay:0.2s"/>
    <circle class="nf-node-ring-c" cx="240" cy="260" r="13" style="animation-delay:0.5s"/><circle class="nf-node-core-c" cx="240" cy="260" r="5" style="animation-delay:0.5s"/>
    <circle class="nf-node-ring-c" cx="240" cy="420" r="13" style="animation-delay:0.8s"/><circle class="nf-node-core-c" cx="240" cy="420" r="5" style="animation-delay:0.8s"/>
    <circle class="nf-node-ring-c" cx="240" cy="570" r="13" style="animation-delay:0.3s"/><circle class="nf-node-core-c" cx="240" cy="570" r="5" style="animation-delay:0.3s"/>
    <circle class="nf-node-ring-c" cx="240" cy="700" r="10" style="animation-delay:0.9s"/><circle class="nf-node-core-c" cx="240" cy="700" r="4" style="animation-delay:0.9s"/>
    <circle class="nf-node-ring-v" cx="450" cy="140" r="13" style="animation-delay:0.6s"/><circle class="nf-node-core-v" cx="450" cy="140" r="5" style="animation-delay:0.6s"/>
    <circle class="nf-node-ring-v" cx="450" cy="290" r="13" style="animation-delay:0.1s"/><circle class="nf-node-core-v" cx="450" cy="290" r="5" style="animation-delay:0.1s"/>
    <circle class="nf-node-ring-v" cx="450" cy="440" r="13" style="animation-delay:0.4s"/><circle class="nf-node-core-v" cx="450" cy="440" r="5" style="animation-delay:0.4s"/>
    <circle class="nf-node-ring-v" cx="450" cy="590" r="13" style="animation-delay:0.7s"/><circle class="nf-node-core-v" cx="450" cy="590" r="5" style="animation-delay:0.7s"/>
    <circle class="nf-node-ring-v" cx="450" cy="700" r="10" style="animation-delay:0.2s"/><circle class="nf-node-core-v" cx="450" cy="700" r="4" style="animation-delay:0.2s"/>
    <circle class="nf-node-ring-p" cx="660" cy="190" r="13" style="animation-delay:0.5s"/><circle class="nf-node-core-p" cx="660" cy="190" r="5" style="animation-delay:0.5s"/>
    <circle class="nf-node-ring-p" cx="660" cy="360" r="13" style="animation-delay:0.8s"/><circle class="nf-node-core-p" cx="660" cy="360" r="5" style="animation-delay:0.8s"/>
    <circle class="nf-node-ring-p" cx="660" cy="530" r="13" style="animation-delay:0.3s"/><circle class="nf-node-core-p" cx="660" cy="530" r="5" style="animation-delay:0.3s"/>
    <circle class="nf-node-ring-p" cx="660" cy="680" r="10" style="animation-delay:0.6s"/><circle class="nf-node-core-p" cx="660" cy="680" r="4" style="animation-delay:0.6s"/>
    <circle class="nf-node-ring-c" cx="880" cy="260" r="13" style="animation-delay:0.2s"/><circle class="nf-node-core-c" cx="880" cy="260" r="5" style="animation-delay:0.2s"/>
    <circle class="nf-node-ring-c" cx="880" cy="440" r="13" style="animation-delay:0.5s"/><circle class="nf-node-core-c" cx="880" cy="440" r="5" style="animation-delay:0.5s"/>
    <circle class="nf-node-ring-c" cx="880" cy="590" r="10" style="animation-delay:0.8s"/><circle class="nf-node-core-c" cx="880" cy="590" r="4" style="animation-delay:0.8s"/>
    <circle class="nf-node-ring-v" cx="1080" cy="320" r="16" style="animation-delay:0.3s"/><circle class="nf-node-core-v" cx="1080" cy="320" r="7" style="animation-delay:0.3s"/>
    <circle class="nf-node-ring-v" cx="1080" cy="510" r="16" style="animation-delay:0.6s"/><circle class="nf-node-core-v" cx="1080" cy="510" r="7" style="animation-delay:0.6s"/>
    <circle class="nf-node-ring-c" cx="1300" cy="390" r="18" style="animation-delay:0.4s"/><circle class="nf-node-core-c" cx="1300" cy="390" r="9" style="animation-delay:0.4s"/>
  </g>
</svg>
</div>
""", unsafe_allow_html=True)

# ── Auth ─────────────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def _check_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("NF_USERNAME", "")
    expected_pass = os.environ.get("NF_PASSWORD", "")
    if not expected_user or not expected_pass:
        return False
    return username.strip() == expected_user and password == expected_pass


def _show_login():
    st.markdown("""
    <style>
    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"] { display: none !important; }
    .block-container {
        padding-top: 0 !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        max-width: 100% !important;
    }
    .nf-login-brand {
        display: flex; align-items: center; justify-content: center;
        gap: 14px; padding-top: 10vh; margin-bottom: 20px;
    }
    .nf-login-icon {
        font-size: 2.6rem;
        background: linear-gradient(135deg, #a78bfa, #38bdf8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        filter: drop-shadow(0 0 14px rgba(139,92,246,0.75)); line-height: 1;
    }
    .nf-login-title-text {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 1.9rem !important; font-weight: 700 !important;
        letter-spacing: 0.16em !important;
        background: linear-gradient(135deg, #e2e8f0 0%, #c4b5fd 55%, #38bdf8 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text; line-height: 1; display: block;
    }
    .nf-login-tagline {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.62rem !important; color: #34d399 !important;
        letter-spacing: 0.10em !important; margin-top: 5px; display: block;
    }
    [data-testid="stForm"] {
        background: rgba(11,14,27,0.84) !important;
        backdrop-filter: blur(28px) !important; -webkit-backdrop-filter: blur(28px) !important;
        border: 1px solid rgba(139,92,246,0.30) !important; border-radius: 16px !important;
        padding: 28px 32px 22px !important;
        box-shadow: 0 0 0 1px rgba(255,255,255,0.04), 0 12px 50px rgba(0,0,0,0.60),
                    0 0 70px rgba(139,92,246,0.12), inset 0 1px 0 rgba(255,255,255,0.06) !important;
    }
    .nf-login-field-label {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.65rem !important; font-weight: 600 !important;
        letter-spacing: 0.12em !important; color: #64748b !important;
        text-transform: uppercase; margin-bottom: 4px; display: block;
    }
    .nf-login-footer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.58rem; color: #1e293b;
        text-align: center; letter-spacing: 0.07em; margin-top: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

    _, mid, _ = st.columns([1.4, 1, 1.4])
    with mid:
        st.markdown("""
        <div class="nf-login-brand">
          <span class="nf-login-icon">⬡</span>
          <div>
            <span class="nf-login-title-text">NEURAL FORGE</span>
            <span class="nf-login-tagline">Pipeline Engine &nbsp;·&nbsp; v1.0</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("nf_login_form", clear_on_submit=False):
            st.markdown('<span class="nf-login-field-label">Username</span>', unsafe_allow_html=True)
            username = st.text_input("u", placeholder="Enter username",
                                     label_visibility="collapsed", key="login_username")
            st.markdown('<span class="nf-login-field-label">Password</span>', unsafe_allow_html=True)
            password = st.text_input("p", placeholder="••••••••", type="password",
                                     label_visibility="collapsed", key="login_password")
            st.markdown("<div style='height:6px'/>", unsafe_allow_html=True)
            submitted = st.form_submit_button("▶  ACCESS SYSTEM",
                                              use_container_width=True, type="primary")

        if submitted:
            if _check_credentials(username, password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid credentials.")

        st.markdown("""
        <p class="nf-login-footer">NEURAL FORGE &nbsp;·&nbsp; DATA PIPELINE ENGINE &nbsp;·&nbsp; v1.0</p>
        """, unsafe_allow_html=True)


if not st.session_state.authenticated:
    _show_login()
    st.stop()

# ── Logout button — fixed top-right (CSS in global stylesheet) ───────────────
if st.button("⏻  Logout", key="nf_logout"):
    st.session_state.authenticated = False
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="nb-brand">
        <span class="nb-brand-icon">⬡</span>
        <div>
            <div class="nb-brand-name">NEURAL FORGE</div>
            <div class="nb-brand-tag">v1.0 &nbsp;·&nbsp; ACTIVE</div>
        </div>
    </div>
""", unsafe_allow_html=True)
    st.divider()
    st.page_link("pages/4_Monitor_Pipelines.py", label="Monitor Pipelines", icon="📊")
    st.page_link("pages/6_Data_Explorer.py",     label="Data Explorer",     icon="🔍")
    st.page_link("pages/2_Bronze_Silver.py",     label="Bronze & Silver",   icon="🔄")
    st.page_link("pages/3_Gold_Builder.py",      label="Gold Builder",      icon="🏆")
    st.page_link("pages/5_Gold_Agent.py",        label="Gold Agent",        icon="🤖")
    st.divider()

pg = st.navigation([
    st.Page("pages/4_Monitor_Pipelines.py", title="Monitor Pipelines", icon="📊"),
    st.Page("pages/6_Data_Explorer.py",     title="Data Explorer",     icon="🔍"),
    st.Page("pages/2_Bronze_Silver.py",     title="Bronze & Silver",   icon="🔄"),
    st.Page("pages/3_Gold_Builder.py",      title="Gold Builder",      icon="🏆"),
    st.Page("pages/5_Gold_Agent.py",        title="Gold Agent",        icon="🤖"),
])
pg.run()
