import base64
import html
import io
import math
import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
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

WORKERS = 6       # عدد المعارض اللي بتتفحص في نفس الوقت
PAGE_SIZE = 20    # عدد البطاقات في الصفحة

TABLE_COLS = [
    "المعرض", "المحافظة", "المنطقة", "العنوان", "الموبايل", "واتساب", "الخريطة",
    "Facebook", "صفحة Facebook", "Ads Library",
    "Dubizzle", "رابط Dubizzle", "ContactCars", "رابط ContactCars",
]
LINK_COLS = [
    "الخريطة", "واتساب", "صفحة Facebook", "Ads Library",
    "رابط Dubizzle", "رابط ContactCars",
]

# =========================================================
# التصميم (CSS) - شبه صفحة دوبيزل: خلفية بيضا، نص كحلي، أحمر للتمييز
# =========================================================

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

:root {
  --accent: #E1252B;
  --ink: #002F34;
  --muted: #5C7276;
  --line: #DEE5E7;
  --soft: #F2F4F5;
}
html, body, .stApp, .stApp * { font-family: 'Cairo', 'Segoe UI', sans-serif; }
.stApp .material-icons, .stApp [data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded', 'Material Icons' !important; }
.stApp { background: #fff; color: var(--ink); }
.stApp p, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3 { color: var(--ink); }

.block-container { max-width: 1180px; padding-top: .6rem; direction: rtl; text-align: right; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 4px 0; margin-bottom: 18px; border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 12px; padding-bottom: 10px; }
.brand img { height: 42px; max-width: 190px; object-fit: contain; }
.brand .logo-fallback { font-size: 1.8rem; }
.brand .t { font-weight: 800; font-size: 1.2rem; line-height: 1.2; }
.brand .s { font-size: .8rem; color: var(--muted); }
.tabs { display: flex; gap: 22px; font-weight: 700; }
.tab { padding: 14px 2px 12px; color: var(--muted); border-bottom: 3px solid transparent; }
.tab.active { color: var(--ink); border-bottom-color: var(--accent); }

div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 10px; border-color: var(--line); background: #fff;
  box-shadow: 0 1px 6px rgba(0, 47, 52, .06);
}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
div[data-testid="stNumberInput"] input {
  background: #fff !important; color: var(--ink) !important;
  border-radius: 8px; border-color: var(--line);
}
.stApp label p { font-weight: 700; font-size: .86rem; color: var(--muted); }

.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
  background: var(--ink); border: none; color: #fff; font-weight: 800;
  font-size: 1.05rem; padding: .7rem 1rem; border-radius: 8px;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover { background: #014850; color: #fff; }

.section-title { font-size: 1.15rem; font-weight: 800; margin: 14px 0 6px; }
.small-note { font-size: .83rem; color: var(--muted); }
.footer-note { text-align: center; font-size: .78rem; color: var(--muted); margin-top: 26px; }

.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 8px 0 14px; }
.kpi { background: #fff; border: 1px solid var(--line); border-top: 3px solid var(--c); border-radius: 10px; padding: 10px 14px; }
.kpi .l { font-size: .82rem; color: var(--muted); font-weight: 600; }
.kpi .v { font-size: 1.7rem; font-weight: 800; line-height: 1.15; }

.card {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  padding: 14px 16px; margin: 10px 0; background: #fff;
  border: 1px solid var(--line); border-radius: 10px;
}
.card:hover { box-shadow: 0 2px 10px rgba(0, 47, 52, .12); }
.card .name { font-size: 1.08rem; font-weight: 800; }
.card .meta { color: var(--muted); font-size: .86rem; margin-top: 2px; }
.card .phone { font-weight: 800; font-size: 1.05rem; margin-top: 6px; unicode-bidi: plaintext; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip { font-size: .76rem; font-weight: 700; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--line); }
.chip.ok  { background: #E6F6EC; color: #12703A; border-color: #BFE6CD; }
.chip.dz  { background: #FDE8E9; color: #B81C22; border-color: #F6C3C5; }
.chip.opp { background: #FFF3D6; color: #8A5A00; border-color: #F3D793; }
.chip.cc  { background: #FFEBDD; color: #B5500F; border-color: #F6CBA9; }
.chip.no, .chip.mute { background: var(--soft); color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; max-width: 46%; }
.btn {
  display: inline-block; padding: 7px 12px; border: 1px solid var(--ink); border-radius: 8px;
  color: var(--ink) !important; font-weight: 700; font-size: .82rem;
  text-decoration: none !important; background: #fff;
}
.btn:hover { background: var(--ink); color: #fff !important; }
.btn.call { background: var(--accent); border-color: var(--accent); color: #fff !important; }
.btn.wa { background: #25D366; border-color: #25D366; color: #fff !important; }
@media (max-width: 800px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .card { flex-direction: column; align-items: flex-start; }
  .actions { max-width: 100%; }
}
</style>
"""


def load_logo_html():
    """بيدوّر على assets/logo.(png|svg|jpg|webp). لو مش موجود بيعرض أيقونة."""
    mimes = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml",
    }
    for ext, mime in mimes.items():
        p = BASE_DIR / "assets" / f"logo{ext}"
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            return f'<img src="data:{mime};base64,{b64}" alt="logo">', True
    return '<span class="logo-fallback">🚗</span>', False


# =========================================================
# منطق التشغيل
# =========================================================

def skipped_verification(name):
    return {
        "facebook": "لم يُفحص", "facebook_url": "",
        "facebook_ads_link": dz.ads_library_link(name),
        "facebook_ads_exact": False,
        "dubizzle": "لم يُفحص", "dubizzle_results": "", "dubizzle_link_kind": "",
        "contactcars": "لم يُفحص", "contactcars_results": "",
        "phone_found": "",
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


def estimate_credits(n, verify, n_districts):
    discovery = 12 * n_districts
    return (round(n * 4) if verify else round(n * 0.5)) + discovery


def credit_cap(n, verify, n_districts):
    """حد أقصى للاستهلاك: لو العملية عدّته بتقف لوحدها عشان رصيد Serper مايخلصش بالغلط."""
    return int(estimate_credits(n, verify, n_districts) * 1.3) + 20


def estimate_minutes(n, verify, n_districts):
    secs = n * (9 if verify else 2) / WORKERS + 20 * n_districts
    return max(1, math.ceil(secs / 60))


def dealer_keys(phone, fb_url):
    """مفاتيح تميّز المعرض: موبايله أو صفحة فيسبوك بتاعته (عشان نكشف التكرار)."""
    keys = []
    if dz.is_mobile_number(phone):
        keys.append("tel:" + dz.clean_digits(phone))
    if fb_url:
        keys.append("fb:" + fb_url.lower().rstrip("/"))
    return keys


def discover_pool(governorate, districts, target, on_progress, max_calls=None):
    """
    بيجمّع معارض من كل المناطق المختارة (بحصة متساوية لكل منطقة، وبعدين بيكمّل من
    المناطق اللي لسه فيها معارض). بيجيب أكتر من المطلوب شوية لتعويض المكرر.
    """
    pool_target = int(target * 1.25) + 3
    quota = max(10, math.ceil(pool_target / len(districts)))
    pool, seen, full = [], set(), set()

    def add(dealer, district):
        phone = best_phone(dealer)
        keys = ["name:" + dz.normalize_name(dealer.get("اسم المعرض", "")) + "|" + district]
        if dealer.get("رابط الخريطة"):
            keys.append("map:" + dealer["رابط الخريطة"])
        if dz.is_mobile_number(phone):
            keys.append("tel:" + dz.clean_digits(phone))
        if any(k in seen for k in keys):
            return
        seen.update(keys)
        dealer["المنطقة"] = district
        pool.append(dealer)

    for pass_no in (1, 2):
        for i, d in enumerate(districts):
            if len(pool) >= pool_target:
                break
            if max_calls and dz.USAGE["serper_calls"] >= max_calls:
                break
            if pass_no == 2 and d not in full:
                continue
            on_progress(0.02 + 0.18 * (i / len(districts)), f"جاري البحث عن معارض في {d}...")
            ask = quota if pass_no == 1 else quota * 3
            raw = dz.discover_dealers(d, ask, enrich=False, governorate=governorate)
            if pass_no == 1 and len(raw) >= ask:
                full.add(d)
            for dealer in raw:
                add(dealer, d)
        if len(pool) >= pool_target or not full:
            break
    return pool


def process_dealer(dealer, governorate, verify):
    """بيفحص معرض واحد (بيتشغل في thread). مفيش فيه أي استدعاء لـ streamlit."""
    district = dealer.get("المنطقة", "")
    name = dealer.get("اسم المعرض", "")

    phone = best_phone(dealer)
    v = dz.verify_all_platforms(name, district, phone) if verify else skipped_verification(name)

    # الرقم في الخرائط أرضي، بس صفحة الفيس عليها موبايل: نستخدمه (من غير أي credit)
    if not dz.is_mobile_number(phone) and v.get("phone_found"):
        phone = v["phone_found"]
    # لسه مفيش موبايل: بحث مدفوع (credit واحد) عن رقم ظاهر في جوجل
    if not dz.is_mobile_number(phone):
        dz.enrich_mobile(dealer)
        phone = best_phone(dealer)
    is_mob = dz.is_mobile_number(phone)

    maps_link = dealer.get("رابط الخريطة") or (
        f"https://www.google.com/maps/search/{urllib.parse.quote(name + ' ' + district)}"
    )
    fb_url = v.get("facebook_url") or ""
    dub_res = v.get("dubizzle_results", "")
    cc_res = v.get("contactcars_results", "")

    row = {
        "المعرض": name,
        "المحافظة": governorate,
        "المنطقة": district,
        "العنوان": dealer.get("العنوان", ""),
        "الموبايل": phone,
        "واتساب": f"https://wa.me/20{phone[1:]}" if is_mob else None,
        "الخريطة": maps_link,
        "Facebook": v["facebook"],
        "صفحة Facebook": fb_url or None,
        "Ads Library": v.get("facebook_ads_link") or None,
        "Dubizzle": v["dubizzle"],
        "رابط Dubizzle": dub_res if dub_res.startswith("http") else None,
        "ContactCars": v["contactcars"],
        "رابط ContactCars": cc_res if cc_res.startswith("http") else None,
    }
    return row, dealer_keys(phone, fb_url)


def run_prospector(governorate, districts, target, verify, on_progress, max_calls=None):
    """بيرجّع (DataFrame أو None, إحصائيات)."""
    dz.USAGE["serper_calls"] = 0
    on_progress(0.02, "جاري البحث عن المعارض في Google Maps...")
    pool = discover_pool(governorate, districts, target, on_progress, max_calls)
    if not pool:
        return None, {}

    rows, seen_run = [], set()
    stats = {"pool": len(pool), "duplicates": 0, "errors": 0, "capped": False}
    idx = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        # بنفحص على دفعات صغيرة عشان نوقف أول ما نوصل للعدد المطلوب من غير ما نصرف credits زيادة
        while len(rows) < target and idx < len(pool):
            if max_calls and dz.USAGE["serper_calls"] >= max_calls:
                stats["capped"] = True
                break
            batch = pool[idx: idx + WORKERS * 2]
            idx += len(batch)
            futures = [ex.submit(process_dealer, d, governorate, verify) for d in batch]
            for fut in futures:
                try:
                    row, keys = fut.result()
                except Exception:
                    stats["errors"] += 1
                    continue
                if len(rows) >= target:
                    continue
                if any(k in seen_run for k in keys):
                    stats["duplicates"] += 1  # نفس المعرض (نفس الموبايل أو صفحة الفيس)
                    continue
                seen_run.update(keys)
                rows.append(row)
                on_progress(0.2 + 0.8 * len(rows) / target, f"تم فحص {len(rows)} من {target} معرض")

    on_progress(1.0, "تم ✅")
    return (pd.DataFrame(rows, columns=TABLE_COLS) if rows else None), stats


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


# =========================================================
# عرض النتائج
# =========================================================

def kpi_card(label, value, color):
    return (
        f'<div class="kpi" style="--c:{color}">'
        f'<div class="l">{label}</div><div class="v">{value}</div></div>'
    )


def render_kpis(df):
    total = len(df)
    mobiles = int(df["الموبايل"].apply(dz.is_mobile_number).sum())
    fb = int(df["Facebook"].str.startswith("موجود").sum())
    dub = int(df["Dubizzle"].str.startswith("مشترك").sum())
    cc = int(df["ContactCars"].str.startswith("موجود").sum())
    html_kpis = '<div class="kpis">' + "".join([
        kpi_card("📊 إجمالي المعارض", total, "#002F34"),
        kpi_card("📞 أرقام موبايل", mobiles, "#16A34A"),
        kpi_card("🔵 صفحة Facebook", fb, "#2563EB"),
        kpi_card("🟥 مشترك في Dubizzle", dub, "#E1252B"),
        kpi_card("🟠 ContactCars", cc, "#F97316"),
    ]) + "</div>"
    st.markdown(html_kpis, unsafe_allow_html=True)


def _safe_url(u):
    u = u.strip() if isinstance(u, str) else ""
    return u if u.startswith(("http://", "https://")) else ""


def _btn(label, url, cls=""):
    url = _safe_url(url)
    if not url:
        return ""
    return (
        f'<a class="btn {cls}" href="{html.escape(url, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer">{label}</a>'
    )


def _chip(text, kind):
    return f'<span class="chip {kind}">{html.escape(text)}</span>'


def _status_chips(row):
    unchecked = (dz.UNKNOWN, "لم يُفحص")
    chips = []

    fb = row.get("Facebook", "")
    if str(fb).startswith("موجود"):
        chips.append(_chip("فيسبوك ✓", "ok"))
    elif fb in unchecked:
        chips.append(_chip("فيسبوك: غير مؤكد", "mute"))
    else:
        chips.append(_chip("مفيش صفحة فيسبوك", "no"))

    dub = row.get("Dubizzle", "")
    if str(dub).startswith("مشترك"):
        chips.append(_chip("مشترك في دوبيزل", "dz"))
    elif dub == dz.NOT_FOUND:
        chips.append(_chip("مش مشترك · فرصة استهداف", "opp"))
    else:
        chips.append(_chip("دوبيزل: غير مؤكد", "mute"))

    cc = row.get("ContactCars", "")
    if str(cc).startswith("موجود"):
        chips.append(_chip("ContactCars ✓", "cc"))
    elif cc == dz.NOT_FOUND:
        chips.append(_chip("مش على ContactCars", "no"))
    else:
        chips.append(_chip("ContactCars: غير مؤكد", "mute"))
    return "".join(chips)


def card_html(row):
    name = html.escape(str(row.get("المعرض", "")))
    area = html.escape(" · ".join(
        x for x in (str(row.get("المحافظة") or ""), str(row.get("المنطقة") or "")) if x
    ))
    address = str(row.get("العنوان") or "")
    meta = area + (" — " + html.escape(address) if address else "")

    phone = str(row.get("الموبايل") or "")
    digits = dz.clean_digits(phone)
    if dz.is_mobile_number(phone):
        phone_html = f'<div class="phone">📞 {html.escape(phone)}</div>'
        call = f'<a class="btn call" href="tel:{html.escape(digits)}">اتصل</a>'
    elif digits.isdigit():
        phone_html = f'<div class="phone">☎️ {html.escape(phone)} <span class="small-note">(رقم أرضي)</span></div>'
        call = f'<a class="btn call" href="tel:{html.escape(digits)}">اتصل</a>'
    else:
        phone_html = '<div class="phone small-note">رقم الموبايل غير متاح</div>'
        call = ""

    actions = "".join([
        call,
        _btn("واتساب", row.get("واتساب"), "wa"),
        _btn("📍 الخريطة", row.get("الخريطة")),
        _btn("صفحة فيسبوك", row.get("صفحة Facebook")),
        _btn("📢 إعلانات ميتا", row.get("Ads Library")),
        _btn("Dubizzle", row.get("رابط Dubizzle")),
        _btn("ContactCars", row.get("رابط ContactCars")),
    ])
    return (
        '<div class="card"><div>'
        f'<div class="name">{name}</div><div class="meta">{meta}</div>'
        f'{phone_html}<div class="chips">{_status_chips(row)}</div>'
        f'</div><div class="actions">{actions}</div></div>'
    )


# =========================================================
# الواجهة
# =========================================================

st.markdown(CSS, unsafe_allow_html=True)

logo_html, has_logo = load_logo_html()
st.markdown(
    f"""
    <div class="topbar">
      <div class="brand">{logo_html}
        <div><div class="t">Lead Prospector</div>
        <div class="s">اكتشف معارض السيارات وتحقق من نشاطها على المنصات</div></div>
      </div>
      <div class="tabs"><div class="tab active">معارض السيارات</div></div>
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
    c1, c2, c3 = st.columns([1.2, 2.6, 1])
    with c1:
        governorate = st.selectbox("🏙️ المحافظة", options=list(dz.REGIONS.keys()))
    with c2:
        chosen = st.multiselect(
            "📍 المناطق (سيبها فاضية = كل مناطق المحافظة)",
            options=dz.REGIONS[governorate],
            key=f"districts_{governorate}",
        )
    with c3:
        count = st.number_input("🔢 عدد المعارض", min_value=1, max_value=1000, value=20, step=10)

    districts = chosen or dz.REGIONS[governorate]
    verify = st.toggle("فحص المنصات (فيسبوك / دوبيزل / كونتكت كارز)", value=True)

    n = int(count)
    cap = credit_cap(n, verify, len(districts))
    st.markdown(
        f'<div class="small-note">💳 التكلفة التقريبية ≈ <b>{estimate_credits(n, verify, len(districts))}</b> '
        f'credit من Serper · ⏱️ الوقت التقريبي ≈ <b>{estimate_minutes(n, verify, len(districts))}</b> دقيقة · '
        f'بيتم البحث في {len(districts)} منطقة · بيقف تلقائياً عند {cap} credit. '
        f'{"العملية كبيرة: سيب الصفحة مفتوحة لحد ما تخلص." if n > 100 else "جرّب بعدد صغير الأول."}</div>',
        unsafe_allow_html=True,
    )
    run = st.button("🔍 ابدأ البحث والتأهيل", type="primary", use_container_width=True)

if run:
    bar = st.progress(0.0, text="جاري التجهيز...")
    try:
        df_new, run_stats = run_prospector(
            governorate, districts, n, verify,
            lambda p, t: bar.progress(min(max(p, 0.0), 1.0), text=t),
            max_calls=cap,
        )
    except Exception as e:  # عشان أي خطأ يظهر بوضوح بدل شاشة حمراء
        df_new, run_stats = None, {}
        bar.empty()
        st.error(f"حصل خطأ أثناء التشغيل: {e}")
    else:
        bar.empty()
        if df_new is None:
            st.error("⚠️ لم يتم العثور على معارض في المناطق المختارة حالياً.")
        else:
            st.session_state["leads"] = df_new
            st.session_state["meta"] = {
                "governorate": governorate,
                "calls": dz.USAGE["serper_calls"],
                "count": len(df_new),
                "requested": n,
                "duplicates": run_stats.get("duplicates", 0),
                "capped": run_stats.get("capped", False),
                "cap": cap,
            }

df = st.session_state.get("leads")

if df is not None:
    meta = st.session_state.get("meta", {})
    st.success(f"✅ تم استخراج وتأهيل {meta.get('count', len(df))} معرض في {meta.get('governorate', '')}")
    st.caption(f"🔎 استهلكت العملية {meta.get('calls', 0)} طلب على Serper (≈ {meta.get('calls', 0)} credit).")
    if meta.get("capped"):
        st.warning(
            f"العملية وقفت عند الحد الأقصى للاستهلاك ({meta.get('cap')} credit) بعد {meta.get('count', len(df))} معرض. "
            "ده حماية لرصيدك. لو عايز تكمّل، شغّلها تاني بمناطق تانية."
        )
    elif meta.get("count", len(df)) < meta.get("requested", 0):
        st.warning(
            f"طلبت {meta['requested']} معرض بس لقيت {meta['count']} معرض فعلاً. "
            "بنستبعد المعارض اللي خارج المناطق المختارة والمكررة "
            f"(اتشال {meta.get('duplicates', 0)} مكرر). اختار مناطق أكتر أو محافظة تانية."
        )

    render_kpis(df)

    st.markdown('<div class="section-title">النتائج</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns([1, 1, 1])
    only_mobile = f1.toggle("📞 اللي ليهم رقم موبايل فقط")
    only_opp = f2.toggle("🎯 فرص استهداف: مش مشتركين في Dubizzle")
    view_mode = f3.radio("طريقة العرض", ["بطاقات", "جدول"], horizontal=True)

    view = df
    if only_mobile:
        view = view[view["الموبايل"].apply(dz.is_mobile_number)]
    if only_opp:
        view = view[view["Dubizzle"] == dz.NOT_FOUND]

    if view.empty:
        st.info("مفيش نتائج بالفلاتر دي.")
    else:
        if view_mode == "بطاقات":
            pages = max(1, math.ceil(len(view) / PAGE_SIZE))
            page = 1
            if pages > 1:
                page = int(st.number_input(f"الصفحة (من {pages})", min_value=1, max_value=pages, value=1))
            chunk = view.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
            st.markdown(
                "".join(card_html(r) for r in chunk.to_dict("records")),
                unsafe_allow_html=True,
            )
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
            "- **غير مؤكد**: الفحص ما نجحش أو الدليل ضعيف، ومعناها مش إن المعرض مش موجود.\n"
            "- وجود صفحة فيسبوك **لا يعني** إن عنده إعلانات شغالة، فاضغط **إعلانات ميتا** "
            "(Meta Ads Library) وتأكد بنفسك قبل ما تتواصل. لو ظهرت \"No ads match\" فغالباً "
            "المعرض مش بيعلن حالياً."
        )

st.markdown(
    '<div class="footer-note"><bdi>Lead Prospector</bdi> · البيانات من <bdi>Google Maps</bdi> عبر <bdi>Serper</bdi> · راجع الأرقام قبل التواصل</div>',
    unsafe_allow_html=True,
)
