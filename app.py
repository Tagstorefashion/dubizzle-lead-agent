import base64
import io
import os
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl.utils import get_column_letter

from modules import dubizzle as dz

st.set_page_config(
    page_title="Dubizzle Lead Prospector",
    page_icon="🚗",
    layout="wide",
)

# مفتاح Serper من Streamlit Secrets (لو موجود)
try:
    if "SERPER_API_KEY" in st.secrets:
        os.environ["SERPER_API_KEY"] = st.secrets["SERPER_API_KEY"]
except Exception:
    pass

BASE_DIR = Path(__file__).parent

DISTRICT_OPTIONS = [
    "مدينة نصر", "مصر الجديدة", "المعادي", "التجمع الخامس", "المهندسين",
    "الدقي", "فيصل", "الهرم", "6 أكتوبر", "الشيخ زايد",
]

LINK_COLS = [
    "الخريطة", "واتساب", "صفحة Facebook", "Ads Library",
    "رابط Dubizzle", "رابط ContactCars",
]

# =========================================================
# التصميم (CSS) - شغال على الوضع الفاتح والداكن
# =========================================================

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

:root {
  --accent: #E1252B;
  --accent-dark: #B81C22;
  --card-bg: rgba(128,128,128,.08);
  --card-bd: rgba(128,128,128,.25);
}
html, body, .stApp, .stApp * { font-family: 'Cairo', 'Segoe UI', sans-serif; }
.stApp .material-icons, .stApp [data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded', 'Material Icons' !important; }

.block-container { max-width: 1280px; padding-top: 1.6rem; direction: rtl; text-align: right; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.hero {
  display: flex; align-items: center; gap: 20px;
  padding: 20px 26px; margin-bottom: 20px;
  border-radius: 18px; border: 1px solid var(--card-bd);
  background: linear-gradient(135deg, rgba(225,37,43,.16), rgba(225,37,43,.03) 60%);
  border-right: 6px solid var(--accent);
}
.hero img { height: 56px; max-width: 220px; object-fit: contain; }
.hero .logo-fallback {
  width: 56px; height: 56px; border-radius: 14px; display: flex;
  align-items: center; justify-content: center; font-size: 1.9rem;
  background: var(--card-bg); border: 1px dashed var(--card-bd);
}
.hero h1 { font-size: 1.75rem; margin: 0; font-weight: 800; line-height: 1.2; padding: 0; }
.hero p { margin: 4px 0 0; opacity: .75; font-size: .98rem; }

.kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 6px 0 18px; }
.kpi {
  background: var(--card-bg); border: 1px solid var(--card-bd);
  border-top: 4px solid var(--c); border-radius: 14px; padding: 14px 18px;
}
.kpi .l { font-size: .88rem; opacity: .8; font-weight: 600; }
.kpi .v { font-size: 2rem; font-weight: 800; line-height: 1.15; }
.kpi .s { font-size: .76rem; opacity: .6; }
@media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }

.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, var(--accent), var(--accent-dark));
  border: none; color: #fff; font-weight: 700; font-size: 1.05rem;
  padding: .7rem 1rem; border-radius: 12px;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.08); color: #fff; }

.section-title { font-size: 1.15rem; font-weight: 700; margin: 8px 0 6px; }
.small-note { font-size: .83rem; opacity: .7; }
.footer-note { text-align: center; font-size: .78rem; opacity: .55; margin-top: 26px; }
</style>
"""


def load_logo_html():
    """بيدوّر على assets/logo.(png|svg|jpg|webp). لو مش موجود بيعرض مكان فاضي."""
    mimes = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml",
    }
    for ext, mime in mimes.items():
        p = BASE_DIR / "assets" / f"logo{ext}"
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            return f'<img src="data:{mime};base64,{b64}" alt="logo">', True
    return '<div class="logo-fallback">🚗</div>', False


# =========================================================
# منطق التشغيل
# =========================================================

def ads_library_link(name):
    return (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=EG"
        f"&q={urllib.parse.quote(name)}&search_type=keyword_unordered"
    )


def skipped_verification(name):
    return {
        "facebook": "لم يُفحص", "facebook_url": "",
        "facebook_ads_link": ads_library_link(name),
        "dubizzle": "لم يُفحص", "dubizzle_results": "",
        "contactcars": "لم يُفحص", "contactcars_results": "",
    }


def best_phone(dealer):
    """أحسن رقم للمعرض: موبايل أولاً، وإلا أرضي، وإلا 'غير متاح'."""
    raw = dealer.get("الهاتف", "")
    mobile = dz.extract_mobile_phone(raw)
    if dz.is_mobile_number(mobile):
        return mobile
    # نقرأ وصف المصدر بس لو المعرض جاي من دليل (مش من Google Maps)
    if dealer.get("مصدر الاكتشاف") != "Google Maps":
        extra = dz.extract_mobile_phone(dealer.get("وصف المصدر", ""))
        if dz.is_mobile_number(extra):
            return extra
    return mobile  # أرضي أو "غير متاح"


def estimate_credits(n, verify):
    return round(n * 3.3) + 2 if verify else round(n * 0.3) + 2


def run_prospector(district, max_results, verify, on_progress):
    dz.USAGE["serper_calls"] = 0
    on_progress(0.03, "جاري البحث عن المعارض في Google Maps...")
    raw_dealers = dz.discover_dealers(district, max_results)
    if not raw_dealers:
        return None

    rows = []
    total = len(raw_dealers)
    for i, dealer in enumerate(raw_dealers, 1):
        name = dealer.get("اسم المعرض", "")
        on_progress(0.15 + 0.85 * (i - 1) / total, f"({i}/{total}) فحص: {name}")

        phone = best_phone(dealer)
        is_mob = dz.is_mobile_number(phone)
        maps_link = dealer.get("رابط الخريطة") or (
            f"https://www.google.com/maps/search/{urllib.parse.quote(name + ' ' + district)}"
        )

        v = dz.verify_all_platforms(name, district, phone) if verify else skipped_verification(name)

        dub_res = v.get("dubizzle_results", "")
        cc_res = v.get("contactcars_results", "")

        rows.append({
            "المعرض": name,
            "المنطقة": district,
            "العنوان": dealer.get("العنوان", ""),
            "الموبايل": phone,
            "واتساب": f"https://wa.me/20{phone[1:]}" if is_mob else None,
            "الخريطة": maps_link,
            "Facebook": v["facebook"],
            "صفحة Facebook": v.get("facebook_url") or None,
            "Ads Library": v.get("facebook_ads_link") or None,
            "Dubizzle": v["dubizzle"],
            "رابط Dubizzle": dub_res if dub_res.startswith("http") else None,
            "ContactCars": v["contactcars"],
            "رابط ContactCars": cc_res if cc_res.startswith("http") else None,
        })

    on_progress(1.0, "تم ✅")
    return pd.DataFrame(rows)


def to_excel_bytes(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
        ws = writer.sheets["Leads"]
        ws.sheet_view.rightToLeft = True
        ws.freeze_panes = "B2"
        for idx, col in enumerate(df.columns, 1):
            if col in LINK_COLS:
                width = 44
            elif col in ("المعرض", "العنوان"):
                width = 32
            else:
                width = 17
            ws.column_dimensions[get_column_letter(idx)].width = width
    return buf.getvalue()


def kpi_card(label, value, sub, color):
    return (
        f'<div class="kpi" style="--c:{color}">'
        f'<div class="l">{label}</div><div class="v">{value}</div>'
        f'<div class="s">{sub}</div></div>'
    )


def render_kpis(df):
    total = len(df)
    mobiles = int(df["الموبايل"].apply(dz.is_mobile_number).sum())
    fb = int(df["Facebook"].str.startswith("موجود").sum())
    dub = int(df["Dubizzle"].str.startswith("مشترك").sum())
    cc = int(df["ContactCars"].str.startswith("موجود").sum())
    unknown = lambda col: int(df[col].isin([dz.UNKNOWN, "لم يُفحص"]).sum())

    html = '<div class="kpi-grid">' + "".join([
        kpi_card("📊 إجمالي المعارض", total, "نتائج هذه العملية", "#64748B"),
        kpi_card("📞 أرقام موبايل", mobiles, f"من {total} معرض", "#16A34A"),
        kpi_card("🔵 صفحة Facebook", fb, f"غير مؤكد: {unknown('Facebook')}", "#2563EB"),
        kpi_card("🟥 مشترك في Dubizzle", dub, f"غير مؤكد: {unknown('Dubizzle')}", "#E1252B"),
        kpi_card("🟠 ContactCars", cc, f"غير مؤكد: {unknown('ContactCars')}", "#F97316"),
    ]) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


# =========================================================
# الواجهة
# =========================================================

st.markdown(CSS, unsafe_allow_html=True)

logo_html, has_logo = load_logo_html()
st.markdown(
    f"""
    <div class="hero">
      {logo_html}
      <div>
        <h1>Dubizzle Lead Prospector</h1>
        <p>اكتشف معارض السيارات، وتحقق من أرقامها ونشاطها على المنصات في دقائق</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not has_logo:
    with st.expander("🖼️ إزاي أضيف اللوجو؟"):
        st.write(
            "ارفع ملف اللوجو على GitHub داخل فولدر اسمه **assets** وسمّيه **logo.png** "
            "(أو logo.svg / logo.jpg / logo.webp)، وبعد ما التطبيق يتحدّث هيظهر هنا تلقائياً."
        )

if not os.getenv("SERPER_API_KEY"):
    st.warning(
        "⚠️ مفتاح SERPER_API_KEY غير مضاف. النتائج هتبقى ناقصة وغير مؤكدة. "
        "أضف المفتاح في Settings ← Secrets عشان تطلع بيانات Google Maps الحقيقية."
    )

with st.container(border=True):
    st.markdown('<div class="section-title">⚙️ إعدادات البحث</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1.6])
    with c1:
        district = st.selectbox("📍 المنطقة", options=DISTRICT_OPTIONS)
    with c2:
        count = st.number_input("🔢 عدد المعارض", min_value=1, max_value=200, value=10, step=5)
    with c3:
        st.write("")
        verify = st.toggle("فحص المنصات (فيسبوك / دوبيزل / كونتكت كارز)", value=True)

    est = estimate_credits(int(count), verify)
    st.markdown(
        f'<div class="small-note">💳 التكلفة التقريبية: حوالي <b>{est}</b> credit من رصيد Serper '
        f'({"≈ 3 credit لكل معرض مع الفحص الكامل" if verify else "من غير فحص المنصات الاستهلاك قليل جداً"}). '
        "جرّب بعدد صغير الأول.</div>",
        unsafe_allow_html=True,
    )
    run = st.button("🚀 ابدأ البحث والتأهيل", type="primary", use_container_width=True)

if run:
    bar = st.progress(0.0, text="جاري التجهيز...")
    try:
        df_new = run_prospector(
            district, int(count), verify,
            lambda p, t: bar.progress(min(max(p, 0.0), 1.0), text=t),
        )
    except Exception as e:  # عشان أي خطأ يظهر بوضوح بدل شاشة حمراء
        df_new = None
        bar.empty()
        st.error(f"حصل خطأ أثناء التشغيل: {e}")
    else:
        bar.empty()
        if df_new is None:
            st.error("⚠️ لم يتم العثور على معارض في هذه المنطقة حالياً.")
        else:
            st.session_state["leads"] = df_new
            st.session_state["meta"] = {
                "district": district,
                "calls": dz.USAGE["serper_calls"],
                "count": len(df_new),
            }

df = st.session_state.get("leads")

if df is not None:
    meta = st.session_state.get("meta", {})
    st.success(f"✅ تم استخراج وتأهيل {meta.get('count', len(df))} معرض في {meta.get('district', '')}")
    st.caption(f"🔎 استهلكت العملية {meta.get('calls', 0)} طلب على Serper (≈ {meta.get('calls', 0)} credit).")

    render_kpis(df)

    st.markdown('<div class="section-title">📋 النتائج</div>', unsafe_allow_html=True)
    f1, f2 = st.columns(2)
    only_mobile = f1.toggle("📞 اللي ليهم رقم موبايل فقط")
    only_opp = f2.toggle("🎯 فرص استهداف: مش مشتركين في Dubizzle")

    view = df
    if only_mobile:
        view = view[view["الموبايل"].apply(dz.is_mobile_number)]
    if only_opp:
        view = view[view["Dubizzle"] == dz.NOT_FOUND]

    if view.empty:
        st.info("مفيش نتائج بالفلاتر دي.")
    else:
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            height=min(38 * len(view) + 42, 640),
            column_config={
                "الخريطة": st.column_config.LinkColumn("الخريطة", display_text="📍 افتح"),
                "واتساب": st.column_config.LinkColumn("واتساب", display_text="💬 راسل"),
                "صفحة Facebook": st.column_config.LinkColumn("صفحة Facebook", display_text="🔵 افتح الصفحة"),
                "Ads Library": st.column_config.LinkColumn("Ads Library", display_text="📢 شوف الإعلانات"),
                "رابط Dubizzle": st.column_config.LinkColumn("رابط Dubizzle", display_text="🟥 افتح"),
                "رابط ContactCars": st.column_config.LinkColumn("رابط ContactCars", display_text="🟠 افتح"),
            },
        )

        d1, d2 = st.columns(2)
        d1.download_button(
            "📥 تحميل Excel",
            data=to_excel_bytes(view),
            file_name="car_dealers_leads.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        d2.download_button(
            "📄 تحميل CSV",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name="car_dealers_leads.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with st.expander("ℹ️ إزاي أقرأ النتائج؟"):
        st.markdown(
            "- **مؤكد**: لقينا صفحة أو إعلان باسم المعرض أو برقمه فعلاً.\n"
            "- **لم يتم العثور**: البحث اشتغل ومالقاش حاجة (غالباً فرصة استهداف).\n"
            "- **غير مؤكد**: الفحص ما نجحش، ومعناها مش إن المعرض مش موجود.\n"
            "- وجود صفحة فيسبوك **لا يعني** إن عنده إعلانات شغالة، فاضغط **شوف الإعلانات** "
            "(Meta Ads Library) وتأكد بنفسك قبل ما تتواصل."
        )

st.markdown(
    '<div class="footer-note">Dubizzle Lead Prospector · البيانات من Google Maps عبر Serper · راجع الأرقام قبل التواصل</div>',
    unsafe_allow_html=True,
)
