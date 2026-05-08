# -*- coding: utf-8 -*-


import streamlit as st
import json, re, csv, io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types as gt

# ── Config ───────────────────────────────────────────────────
API_KEY = st.secrets["GEMINI_API_KEY"]
MODEL   = "gemini-flash-latest"

PROMPT_SINGLE = """Phan tich anh nay va:
1. Dem chinh xac tung loai vat the tren mat phang
2. Doc tat ca text/chu viet, ma barcode, QR code, so serial, ID, nhan mac tren vat the (neu co)

Chi tra ve JSON, KHONG them bat ky chu nao khac:
{
  "total": <so nguyen tong vat the>,
  "items": [{"name": "<ten tieng Viet>", "count": <so nguyen>}],
  "text_found": [{"label": "<ten vat the hoac vi tri>", "text": "<noi dung doc duoc>", "type": "<barcode|qr|serial|id|text|label>"}],
  "note": "<mo ta ngan canh>"
}
Neu khong tim thay text/barcode gi thi text_found = []"""

PROMPT_MULTI = """Toi se gui cho ban {n} anh chua cung mot nhom vat the chup tu nhieu goc do khac nhau.
Hay phan tich TAT CA anh va:
1. Dem tong so luong vat the (tranh dem trung neu cung 1 vat xuat hien o nhieu anh)
2. Doc tat ca text/chu viet, barcode, QR, serial, ID, nhan mac tren vat the

Chi tra ve JSON, KHONG them chu nao khac:
{
  "total": <so nguyen - uoc tinh tong vat the thuc te>,
  "items": [{"name": "<ten tieng Viet>", "count": <so nguyen>}],
  "text_found": [{"label": "<ten/vi tri vat>", "text": "<noi dung>", "type": "<barcode|qr|serial|id|text|label>"}],
  "note": "<tom tat: phan tich tu X anh, mo ta>"
}"""

# ── Page config ───────────────────────────────────────────────
st.set_page_config(page_title="Material Counter", page_icon="🔢", layout="wide")

st.markdown("""
<style>
  .stApp { background:#0F1923; color:#ECF0F1; }
  section[data-testid="stSidebar"] { background:#1A2535; }
  #MainMenu, footer, header { visibility:hidden; }

  .big-number {
    font-size:88px; font-weight:900; color:#FFB300;
    text-align:center; line-height:1; padding:8px 0;
  }
  .big-label { text-align:center; color:#7F8C8D; font-size:13px; margin-top:-6px; }

  .result-card {
    background:#1A2535; border:1px solid #00C896;
    border-radius:12px; padding:16px; margin-bottom:10px;
  }
  .item-row {
    display:flex; justify-content:space-between;
    padding:7px 0; border-bottom:1px solid #212F3D; font-size:15px;
  }
  .item-count { font-weight:700; color:#00C896; font-size:18px; }

  .text-card {
    background:#1A2535; border:1px solid #F39C12;
    border-radius:12px; padding:16px; margin-bottom:10px;
  }
  .text-row {
    padding:6px 0; border-bottom:1px solid #212F3D; font-size:14px;
  }
  .text-type {
    display:inline-block; background:#F39C12; color:#0F1923;
    border-radius:4px; padding:1px 7px; font-size:11px;
    font-weight:700; margin-right:8px;
  }
  .text-val { color:#ECF0F1; font-family:monospace; font-size:14px; }
  .text-lbl { color:#95A5A6; font-size:12px; margin-top:2px; }

  .note-text { color:#95A5A6; font-size:13px; font-style:italic; margin-top:8px; }

  div.stButton > button {
    background:#8E44AD; color:white; font-weight:700;
    border:none; border-radius:8px; padding:10px 24px;
    font-size:15px; width:100%; cursor:pointer;
  }
  div.stButton > button:hover { background:#7D3C98; border:none; }

  .img-thumb {
    border:2px solid #2C3E50; border-radius:8px;
    overflow:hidden; margin-bottom:4px;
  }
  .img-count-badge {
    background:#8E44AD; color:white; border-radius:20px;
    padding:2px 10px; font-size:12px; font-weight:700;
    display:inline-block; margin-bottom:8px;
  }

  div[data-testid="stTabs"] button { color:#95A5A6; font-size:14px; }
  div[data-testid="stTabs"] button[aria-selected="true"] {
    color:#00C896; border-bottom:2px solid #00C896;
  }

  .hist-row {
    background:#1A2535; border-radius:8px;
    padding:10px 14px; margin-bottom:6px;
  }
  .hist-total { color:#FFB300; font-weight:700; font-size:22px; float:right; }
  .hist-time  { color:#7F8C8D; font-size:11px; }
  .hist-items { color:#ECF0F1; font-size:13px; margin:4px 0; }
  .hist-texts { color:#F39C12; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
for k, v in [("history",[]), ("last_result",None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Gemini client ─────────────────────────────────────────────
@st.cache_resource
def get_client():
    return genai.Client(api_key=API_KEY)

# ── Gemini call ───────────────────────────────────────────────
def call_gemini(images: list[Image.Image], multi: bool = False) -> dict:
    client = get_client()
    contents = []

    for img in images:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        contents.append(gt.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))

    prompt = PROMPT_MULTI.format(n=len(images)) if multi else PROMPT_SINGLE
    contents.append(prompt)

    resp = client.models.generate_content(model=MODEL, contents=contents)
    raw  = resp.text.strip()
    # Strip markdown fences
    raw  = re.sub(r"^```(?:json)?\s*", "", raw)
    raw  = re.sub(r"\s*```$", "", raw.strip())
    # Lay phan JSON { ... } neu co text thua
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    return json.loads(raw)

# ── Annotate ──────────────────────────────────────────────────
def annotate(image: Image.Image, result: dict) -> Image.Image:
    img = image.copy().convert("RGBA")
    try:
        f_big = ImageFont.truetype("arialbd.ttf", 32)
        f_med = ImageFont.truetype("arial.ttf",   17)
        f_sm  = ImageFont.truetype("arial.ttf",   13)
    except:
        f_big = f_med = f_sm = ImageFont.load_default()

    total      = result.get("total", 0)
    items      = result.get("items", [])
    texts      = result.get("text_found", [])

    lines = [f"TONG: {total}"] + [f"  {it['name']}: {it['count']}" for it in items]
    if texts:
        lines.append("─" * 20)
        for t in texts[:4]:
            lines.append(f"  [{t.get('type','?').upper()}] {t.get('text','')[:30]}")

    ow = 360; oh = 16 + 30 * len(lines)
    ov = Image.new("RGBA", (ow, oh), (15, 25, 35, 215))
    img.paste(ov, (10, 10), ov)
    d = ImageDraw.Draw(img)
    d.text((18, 12), lines[0], font=f_big, fill=(255, 179, 0))
    for i, l in enumerate(lines[1:], 1):
        color = (243, 156, 18) if l.startswith("  [") else (210, 210, 210)
        d.text((18, 12 + 30*i), l, font=f_sm if l.startswith("  [") else f_med,
               fill=color)
    return img.convert("RGB")

# ── Render result panel ───────────────────────────────────────
def render_result(result: dict):
    total = result.get("total", 0)
    items = result.get("items", [])
    texts = result.get("text_found", [])
    note  = result.get("note", "")

    st.markdown(f'<div class="big-number">{total}</div>'
                f'<div class="big-label">vat the</div>', unsafe_allow_html=True)

    # Items
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown("**📦 Chi tiet vat the**")
    for it in items:
        st.markdown(
            f'<div class="item-row"><span>{it["name"]}</span>'
            f'<span class="item-count">{it["count"]}</span></div>',
            unsafe_allow_html=True)
    if note:
        st.markdown(f'<div class="note-text">💬 {note}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Text / Barcode
    if texts:
        st.markdown('<div class="text-card">', unsafe_allow_html=True)
        st.markdown("**🔍 Text / Barcode / ID doc duoc**")
        for t in texts:
            ttype = t.get("type", "text").upper()
            tval  = t.get("text", "")
            tlbl  = t.get("label", "")
            st.markdown(
                f'<div class="text-row">'
                f'<span class="text-type">{ttype}</span>'
                f'<span class="text-val">{tval}</span>'
                f'<div class="text-lbl">{tlbl}</div>'
                f'</div>',
                unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#7F8C8D;font-size:13px;padding:8px 0">'
            '🔍 Khong tim thay barcode/text tren vat the</div>',
            unsafe_allow_html=True)

# ── Export ────────────────────────────────────────────────────
def to_json(h):
    return json.dumps(h, ensure_ascii=False, indent=2).encode("utf-8")

def to_csv(h):
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["Thoi gian","Nguon","Vat the","So luong","Tong","Text doc duoc","Ghi chu"])
    for e in h:
        texts_str = " | ".join(
            f"[{t.get('type','')}] {t.get('text','')}"
            for t in e.get("text_found", []))
        for it in e.get("items", []):
            w.writerow([e["timestamp"], e.get("source",""),
                        it["name"], it["count"],
                        e["total"], texts_str, e.get("note","")])
    return buf.getvalue().encode("utf-8-sig")

# ════════════════════════════════════════════════════════════
# LAYOUT
# ════════════════════════════════════════════════════════════
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("## 🔢 Material Counter")
    st.markdown(f"<span style='color:#8E44AD;font-size:13px'>✦ {MODEL}</span>",
                unsafe_allow_html=True)
with c2:
    h = st.session_state.history
    if h:
        col_j, col_c = st.columns(2)
        with col_j:
            st.download_button("⬇ JSON", to_json(h), "kiem_dem.json",
                               "application/json", use_container_width=True)
        with col_c:
            st.download_button("⬇ CSV",  to_csv(h),  "kiem_dem.csv",
                               "text/csv", use_container_width=True)

st.divider()

tab_cam, tab_multi, tab_history = st.tabs([
    "  📷  Chup webcam  ",
    "  🖼  Upload nhieu anh  ",
    "  📋  Lich su  ",
])

# ──────────────────────────────────────────────────────────────
# TAB 1: Webcam
# ──────────────────────────────────────────────────────────────
with tab_cam:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Chup qua webcam / camera dien thoai")
        cam_img = st.camera_input("", label_visibility="collapsed")
        if cam_img:
            image = Image.open(cam_img).convert("RGB")
            if st.button("✦  AI Dem ngay", key="btn_cam"):
                with st.spinner("Dang phan tich..."):
                    try:
                        result = call_gemini([image])
                        st.session_state.last_result = {
                            "image": annotate(image, result),
                            "result": result, "source": "webcam",
                        }
                        st.session_state.history.append({
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "source": "webcam",
                            "total":  result.get("total", 0),
                            "items":  result.get("items", []),
                            "text_found": result.get("text_found", []),
                            "note":   result.get("note", ""),
                        })
                        st.rerun()
                    except Exception as e:
                        st.error(f"Loi Gemini: {e}")

    with right:
        r = st.session_state.last_result
        if r and r.get("source") == "webcam":
            st.image(r["image"], use_container_width=True)
            render_result(r["result"])
        else:
            st.markdown("""<div style='text-align:center;color:#7F8C8D;padding:80px 0'>
              <div style='font-size:56px'>📷</div>
              <div style='margin-top:10px'>Chup anh roi nhan AI Dem</div>
            </div>""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# TAB 2: Upload nhiều ảnh
# ──────────────────────────────────────────────────────────────
with tab_multi:
    st.markdown("#### Upload nhieu anh – phan tich tung anh")
    st.markdown(
        "<span style='color:#95A5A6;font-size:13px'>"
        "Moi anh se duoc Gemini phan tich rieng – ket qua hien thi tung cai"
        "</span>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "", type=["jpg","jpeg","png","webp"],
        accept_multiple_files=True,
        label_visibility="collapsed")

    if uploaded:
        images = [Image.open(f).convert("RGB") for f in uploaded]
        n = len(images)

        st.markdown(f'<div class="img-count-badge">✦ {n} anh da chon</div>',
                    unsafe_allow_html=True)

        # Thumbnails
        cols = st.columns(min(n, 4))
        for i, (col, img) in enumerate(zip(cols, images)):
            with col:
                st.image(img, caption=f"Anh {i+1}", use_container_width=True)
        if n > 4:
            cols2 = st.columns(min(n-4, 4))
            for i, (col, img) in enumerate(zip(cols2, images[4:])):
                with col:
                    st.image(img, caption=f"Anh {i+5}", use_container_width=True)

        st.markdown("")

        if st.button("✦  AI Dem tat ca", key="btn_multi"):
            all_results = []
            prog = st.progress(0, text="Dang phan tich...")
            for i, img in enumerate(images):
                prog.progress((i+1)/n, text=f"Phan tich anh {i+1}/{n}...")
                try:
                    r = call_gemini([img])
                    all_results.append({"img": img, "result": r, "idx": i+1})
                    # Luu history tung anh
                    st.session_state.history.append({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "source": f"upload_anh_{i+1}",
                        "total":  r.get("total", 0),
                        "items":  r.get("items", []),
                        "text_found": r.get("text_found", []),
                        "note":   r.get("note", ""),
                    })
                except Exception as e:
                    st.warning(f"Anh {i+1} loi: {e}")
            prog.empty()

            if all_results:
                total_all = sum(ar["result"].get("total", 0) for ar in all_results)
                st.success(f"Xong! Tong cong {total_all} vat the tu {len(all_results)} anh")
                st.markdown("---")
                for ar in all_results:
                    with st.expander(
                        f"📷 Anh {ar['idx']} — {ar['result'].get('total',0)} vat the",
                        expanded=True):
                        c1_, c2_ = st.columns([2, 1])
                        with c1_:
                            st.image(annotate(ar["img"], ar["result"]),
                                     use_container_width=True)
                        with c2_:
                            render_result(ar["result"])

    else:
        st.markdown("""<div style='text-align:center;color:#7F8C8D;padding:60px 0;
          border:2px dashed #2C3E50;border-radius:12px;margin-top:10px'>
          <div style='font-size:52px'>🖼</div>
          <div style='margin-top:10px;font-size:15px'>Keo tha hoac click de chon anh</div>
          <div style='font-size:12px;margin-top:6px'>JPG, PNG, WEBP – Co the chon nhieu anh</div>
        </div>""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# TAB 3: Lịch sử
# ──────────────────────────────────────────────────────────────
with tab_history:
    hist = st.session_state.history
    if not hist:
        st.markdown("""<div style='text-align:center;color:#7F8C8D;padding:60px 0'>
          <div style='font-size:48px'>📋</div>
          <div style='margin-top:10px'>Chua co lich su dem</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"**Tong {len(hist)} lan dem**")
        for e in reversed(hist):
            items_str = "  ·  ".join(
                f"{it['name']}: {it['count']}" for it in e.get("items",[]))
            texts_str = "  ·  ".join(
                f"[{t.get('type','?').upper()}] {t.get('text','')}"
                for t in e.get("text_found",[]))
            st.markdown(
                f'<div class="hist-row">'
                f'<span class="hist-total">{e["total"]}</span>'
                f'<div class="hist-time">⏱ {e["timestamp"]}  [{e.get("source","?")}]</div>'
                f'<div class="hist-items">{items_str or "—"}</div>'
                + (f'<div class="hist-texts">🔍 {texts_str}</div>' if texts_str else "")
                + f'</div>',
                unsafe_allow_html=True)

        if st.button("🗑  Xoa lich su"):
            st.session_state.history      = []
            st.session_state.last_result  = None
            st.rerun()
