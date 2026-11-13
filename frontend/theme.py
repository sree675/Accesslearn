"""Accessibility-first styling.

Atkinson Hyperlegible was designed by the Braille Institute for low-vision readers, so it is the default.
Dyslexia-friendly mode switches to Lexend with wider letter, word and line spacing.
"""
import json

import streamlit as st
import streamlit.components.v1 as components

STANDARD = dict(bg="#F3F6F8", panel="#FFFFFF", side="#E4ECF1", ink="#14243B", muted="#42566B",
                accent="#0A6B6B", accent_ink="#FFFFFF", line="#B7C5D0", focus="#E39B00")
CONTRAST = dict(bg="#000000", panel="#000000", side="#000000", ink="#FFFFFF", muted="#FFFFFF",
                accent="#FFD400", accent_ink="#000000", line="#FFFFFF", focus="#00E5FF")


def inject(scale=100, high_contrast=False, dyslexia=False):
    c = CONTRAST if high_contrast else STANDARD
    if dyslexia:
        family = "'Lexend', 'Atkinson Hyperlegible', Verdana, sans-serif"
        spacing = "letter-spacing:0.05em; word-spacing:0.16em; line-height:1.85;"
    else:
        family = "'Atkinson Hyperlegible', 'Segoe UI', Verdana, sans-serif"
        spacing = "line-height:1.6;"
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Lexend:wght@400;600&display=swap');
    html {{ font-size: {scale}%; }}
    .stApp {{ background: {c['bg']}; color: {c['ink']}; }}
    .stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp div, .stApp input, .stApp textarea,
    .stApp button, .stApp select {{ font-family: {family}; {spacing} }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ color: {c['ink']}; font-weight: 700; letter-spacing: 0; }}
    .stApp p, .stApp li, .stApp label {{ color: {c['ink']}; max-width: 75ch; }}
    [data-testid="stCaptionContainer"], .stApp small {{ color: {c['muted']}; }}
    [data-testid="stSidebar"] {{ background: {c['side']}; border-right: 2px solid {c['line']}; }}
    [data-testid="stVerticalBlockBorderWrapper"] {{ background: {c['panel']}; border-color: {c['line']} !important; border-width: 2px !important; }}
    .stButton > button, .stLinkButton a, .stDownloadButton > button, .stFormSubmitButton > button {{
        min-height: 2.9rem; border: 2px solid {c['accent']}; border-radius: 6px; font-weight: 700;
        background: {c['accent']}; color: {c['accent_ink']}; }}
    .stButton > button:hover, .stLinkButton a:hover {{ filter: brightness(1.12); }}
    .stButton > button p, .stLinkButton a p {{ color: {c['accent_ink']}; }}
    *:focus-visible {{ outline: 3px solid {c['focus']} !important; outline-offset: 2px !important; }}
    a {{ color: {c['accent']}; text-decoration: underline; }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def speak_button(text, label="Read aloud"):
    """Browser text-to-speech so students who prefer listening can hear any description."""
    safe = json.dumps(text)
    components.html(
        f"""<button id="b" aria-label="{label}" style="font:700 16px system-ui;min-height:44px;padding:0 16px;
        border:2px solid #0A6B6B;border-radius:6px;background:#fff;color:#0A6B6B;cursor:pointer">{label}</button>
        <script>
        const t = {safe};
        document.getElementById('b').onclick = () => {{
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance(t); u.rate = 0.9; window.speechSynthesis.speak(u);
        }};
        </script>""",
        height=52,
    )
