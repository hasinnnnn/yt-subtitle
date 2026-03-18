import re
import json
import html
from urllib.parse import urlparse, parse_qs
from xml.etree.ElementTree import ParseError

import streamlit as st
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(page_title="YouTube Subtitle Grabber", page_icon="🎬", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1100px;
    }
    .app-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .app-subtitle {
        color: #9aa0a6;
        margin-bottom: 1.2rem;
    }
    .subtitle-card {
        border: 1px solid rgba(250, 250, 250, 0.08);
        background: rgba(255, 255, 255, 0.03);
        padding: 14px 16px;
        border-radius: 16px;
        margin-bottom: 12px;
    }
    .subtitle-time {
        display: inline-block;
        font-size: 0.82rem;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        margin-bottom: 8px;
    }
    .subtitle-text {
        font-size: 1rem;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .hint-box {
        border: 1px dashed rgba(255,255,255,0.18);
        padding: 16px;
        border-radius: 14px;
        margin-top: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def extract_video_id(url: str) -> str:
    url = url.strip()

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url):
        return url

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path

    if "youtu.be" in host:
        candidate = path.strip("/").split("/")[0]
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", candidate):
            return candidate

    if "youtube.com" in host or "m.youtube.com" in host:
        if path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
                return video_id

        match = re.search(r"/(shorts|embed|live)/([a-zA-Z0-9_-]{11})", path)
        if match:
            return match.group(2)

    raise ValueError("Link YouTube tidak valid.")


def format_seconds(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_plain_text_to_items(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    for i, line in enumerate(lines):
        items.append(
            {
                "text": line,
                "start": i * 3,
                "duration": 3,
            }
        )
    return items


def parse_srt(content: str):
    blocks = re.split(r"\n\s*\n", content.strip(), flags=re.MULTILINE)
    items = []

    def srt_time_to_seconds(t: str) -> float:
        h, m, s_ms = t.split(":")
        s, ms = s_ms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    for block in blocks:
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 2:
            continue

        if re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]

        if not lines:
            continue

        if "-->" in lines[0]:
            time_line = lines[0]
            text_lines = lines[1:]
            parts = [x.strip() for x in time_line.split("-->")]
            if len(parts) == 2:
                start = srt_time_to_seconds(parts[0])
                end = srt_time_to_seconds(parts[1])
                items.append(
                    {
                        "text": " ".join(text_lines).strip(),
                        "start": start,
                        "duration": max(0.1, end - start),
                    }
                )

    return items


def fetch_subtitles(video_id: str):
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["id", "id-ID", "en", "en-US", "en-GB"])
        items = fetched.to_raw_data()

        if not items:
            raise RuntimeError("Subtitle kosong atau tidak tersedia.")

        return items

    except ParseError:
        raise RuntimeError(
            "Request ke YouTube gagal diproses. Di Streamlit Cloud biasanya ini karena IP server diblok YouTube."
        )
    except Exception as e:
        msg = str(e).strip().lower()

        if "requestblocked" in msg or "ipblocked" in msg or "youtube is blocking requests" in msg:
            raise RuntimeError(
                "Request diblokir oleh YouTube. Di Streamlit Cloud ini biasanya karena IP cloud diblok."
            )
        if "no transcript found" in msg or "notranscriptfound" in msg:
            raise RuntimeError("Video ini tidak punya subtitle yang bisa diambil.")
        if "transcriptsdisabled" in msg or "subtitles are disabled" in msg:
            raise RuntimeError("Subtitle video ini dimatikan.")
        if "videounavailable" in msg:
            raise RuntimeError("Video tidak tersedia.")
        if "too many requests" in msg:
            raise RuntimeError("Terlalu banyak request. Coba lagi nanti.")

        raise RuntimeError(str(e))


def make_copy_button(text: str):
    safe_text = json.dumps(text)
    components.html(
        f"""
        <div style="display:flex;align-items:center;gap:10px;height:38px;">
            <button id="copy-btn" style="
                border:none;
                border-radius:10px;
                padding:10px 14px;
                font-weight:600;
                cursor:pointer;
                width:100%;
            ">📋 Copy Subtitle</button>
            <span id="copy-status" style="font-size:13px;"></span>
        </div>
        <script>
            const text = {safe_text};
            const btn = document.getElementById("copy-btn");
            const status = document.getElementById("copy-status");

            btn.addEventListener("click", async () => {{
                try {{
                    await navigator.clipboard.writeText(text);
                    status.textContent = "Tersalin";
                }} catch (err) {{
                    status.textContent = "Copy gagal";
                }}
            }});
        </script>
        """,
        height=50,
    )


if "subtitle_items" not in st.session_state:
    st.session_state.subtitle_items = []
if "full_text" not in st.session_state:
    st.session_state.full_text = ""
if "video_id" not in st.session_state:
    st.session_state.video_id = ""
if "error_msg" not in st.session_state:
    st.session_state.error_msg = ""

st.markdown('<div class="app-title">🎬 YouTube Subtitle Grabber</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Paste link YouTube, ambil subtitle, lalu copy atau download TXT.</div>',
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(["Dari Link YouTube", "Paste Manual", "Upload File"])

with tab1:
    with st.form("subtitle_form", clear_on_submit=False):
        url = st.text_input(
            "Link YouTube",
            placeholder="https://www.youtube.com/watch?v=...",
        )
        submitted = st.form_submit_button("Ambil Subtitle")

    if submitted:
        st.session_state.error_msg = ""
        st.session_state.subtitle_items = []
        st.session_state.full_text = ""
        st.session_state.video_id = ""

        try:
            video_id = extract_video_id(url)
            items = fetch_subtitles(video_id)

            full_text = "\n".join(
                item.get("text", "").replace("\n", " ").strip()
                for item in items
                if item.get("text", "").strip()
            ).strip()

            st.session_state.video_id = video_id
            st.session_state.subtitle_items = items
            st.session_state.full_text = full_text

        except Exception as e:
            st.session_state.error_msg = str(e)

with tab2:
    manual_text = st.text_area(
        "Paste subtitle di sini",
        height=220,
        placeholder="Tempel subtitle manual di sini...",
    )
    if st.button("Gunakan Subtitle Manual", use_container_width=True):
        clean = manual_text.strip()
        if clean:
            st.session_state.error_msg = ""
            st.session_state.video_id = "manual"
            st.session_state.full_text = clean
            st.session_state.subtitle_items = parse_plain_text_to_items(clean)
        else:
            st.session_state.error_msg = "Subtitle manual masih kosong."

with tab3:
    uploaded = st.file_uploader("Upload file .txt atau .srt", type=["txt", "srt"])
    if uploaded is not None:
        content = uploaded.read().decode("utf-8", errors="ignore")
        if uploaded.name.lower().endswith(".srt"):
            items = parse_srt(content)
            if items:
                full_text = "\n".join(
                    item.get("text", "").strip()
                    for item in items
                    if item.get("text", "").strip()
                ).strip()
            else:
                full_text = content.strip()
                items = parse_plain_text_to_items(full_text)
        else:
            full_text = content.strip()
            items = parse_plain_text_to_items(full_text)

        st.session_state.error_msg = ""
        st.session_state.video_id = uploaded.name.rsplit(".", 1)[0]
        st.session_state.full_text = full_text
        st.session_state.subtitle_items = items

if st.session_state.error_msg:
    st.error(st.session_state.error_msg)
    if "diblok" in st.session_state.error_msg.lower():
        st.info(
            "Mode link YouTube gagal di server ini. Pakai tab Paste Manual atau Upload File supaya app tetap bisa dipakai."
        )

if st.session_state.full_text:
    st.subheader("Opsi")
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="⬇️ Download TXT",
            data=st.session_state.full_text.encode("utf-8"),
            file_name=f"{st.session_state.video_id}_subtitle.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with col2:
        make_copy_button(st.session_state.full_text)

    st.caption(f"{len(st.session_state.subtitle_items)} baris subtitle.")
    st.subheader("Subtitle")

    for item in st.session_state.subtitle_items:
        text = html.escape(item.get("text", "")).replace("\n", "<br>")
        start = format_seconds(item.get("start", 0))
        duration = round(float(item.get("duration", 0)), 2)

        st.markdown(
            f"""
            <div class="subtitle-card">
                <div class="subtitle-time">⏱ {start} • {duration}s</div>
                <div class="subtitle-text">{text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        """
        <div class="hint-box">
            Coba ambil dari link YouTube. Kalau diblok, pakai tab <b>Paste Manual</b> atau <b>Upload File</b>.
        </div>
        """,
        unsafe_allow_html=True,
    )
