import re
import time
import urllib.parse
import io

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

from modules.dubizzle import get_dubizzle_status
from modules.contactcars import get_contactcars_status
from modules.deduplication import remove_duplicate_dealers


# =========================================================
# APP CONFIG
# =========================================================

st.set_page_config(
    page_title="Egypt Car Dealer Lead Intelligence",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Egypt Car Dealer Lead Intelligence")

st.caption(
    "اكتشاف معارض السيارات في مصر والتحقق من وجودها "
    "على Dubizzle و ContactCars وتجهيز بيانات التواصل"
)


# =========================================================
# AREAS
# =========================================================

DISTRICTS = [
    "مدينة نصر",
    "مصر الجديدة",
    "التجمع الخامس",
    "التجمع الأول",
    "التجمع الثالث",
    "المعادي",
    "زهراء المعادي",
    "المقطم",
    "6 أكتوبر",
    "الشيخ زايد",
    "المهندسين",
    "الدقي",
    "العجوزة",
    "الهرم",
    "فيصل",
    "شبرا",
    "وسط البلد",
    "العبور",
    "الشروق",
    "مدينتي",
    "العاشر من رمضان",
]


# =========================================================
# HTTP
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


# =========================================================
# HELPERS
# =========================================================

def clean_text(value):
    if not value:
        return ""

    value = BeautifulSoup(
        str(value),
        "html.parser"
    ).get_text(" ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_name(name):
    if not name:
        return ""

    name = clean_text(name).lower()

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(
        r"[^\w\s\u0600-\u06FF]",
        " ",
        name
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name.strip()


def extract_phone(text):
    if not text:
        return ""

    patterns = [
        r"01[0125]\d{8}",
        r"\+20\s*1[0125]\s*\d{8}",
        r"0020\s*1[0125]\s*\d{8}",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            str(text)
        )

        if not match:
            continue

        phone = re.sub(
            r"\D",
            "",
            match.group()
        )

        if phone.startswith("0020"):
            phone = phone[2:]

        if phone.startswith("20"):
            phone = phone[2:]

        if len(phone) == 11 and phone.startswith("01"):
            return phone

    return ""


def google_maps_link(name, area):

    query = urllib.parse.quote(
        f"{name} {area} Egypt"
    )

    return (
        "https://www.google.com/maps/search/"
        + query
    )


def whatsapp_link(phone, message):

    if not phone:
        return ""

    phone = re.sub(
        r"\D",
        "",
        str(phone)
    )

    if phone.startswith("0"):
        phone = "20" + phone[1:]

    encoded = urllib.parse.quote(
        message
    )

    return (
        f"https://wa.me/{phone}"
        f"?text={encoded}"
    )


# =========================================================
# SEARCH - DUCKDUCKGO
# =========================================================

def search_duckduckgo(query, max_results=15):

    try:

        url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote(query)
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(".result"):

            title_element = result.select_one(
                ".result__title"
            )

            link_element = result.select_one(
                ".result__a"
            )

            snippet_element = result.select_one(
                ".result__snippet"
            )

            if not title_element or not link_element:
                continue

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

            link = link_element.get(
                "href",
                ""
            )

            snippet = ""

            if snippet_element:
                snippet = clean_text(
                    snippet_element.get_text(
                        " ",
                        strip=True
                    )
                )

            if title and link:

                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                })

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


# =========================================================
# SEARCH - BING FALLBACK
# =========================================================

def search_bing(query, max_results=15):

    try:

        url = (
            "https://www.bing.com/search?q="
            + urllib.parse.quote(query)
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select("li.b_algo"):

            title_element = result.select_one("h2 a")

            if not title_element:
                continue

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

            link = title_element.get(
                "href",
                ""
            )

            snippet_element = result.select_one(
                ".b_caption p"
            )

            snippet = ""

            if snippet_element:
                snippet = clean_text(
                    snippet_element.get_text(
                        " ",
                        strip=True
                    )
                )

            if title and link:

                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                })

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


# =========================================================
# COMBINED SEARCH
# =========================================================

def search_web(query, max_results=15):

    results = search_duckduckgo(
        query,
        max_results
    )

    if results:
        return results

    # Fallback
    return search_bing(
        query,
        max_results
    )


# =========================================================
# EXTRACT DEALER NAME
# =========================================================

def extract_dealer_name(title, snippet=""):

    title = clean_text(title)

    if not title:
        return ""

    # Remove common suffixes
    patterns = [
        r"\s*[-|]\s*Facebook.*$",
        r"\s*[-|]\s*Instagram.*$",
        r"\s*[-|]\s*YouTube.*$",
        r"\s*[-|]\s*Dubizzle.*$",
        r"\s*[-|]\s*ContactCars.*$",
        r"\s*[-|]\s*Google.*$",
    ]

    name = title

    for pattern in patterns:

        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE
        )

    name = clean_text(name)

    # Reject pages that are clearly NOT dealership names
    rejected_exact = [
        "سيارات للبيع",
        "معارض سيارات",
        "معرض سيارات",
        "used cars",
        "cars for sale",
        "car dealers",
        "car dealer",
        "dubizzle",
        "contactcars",
    ]

    normalized = normalize_name(name)

    for bad_name in rejected_exact:

        if normalized == normalize_name(
            bad_name
        ):
            return ""

    # Avoid very generic search-result titles
    if len(name) < 3:
        return ""

    return name


# =========================================================
# DISCOVER DEALERS
# =========================================================

def discover_dealers(
    district,
    max_results
):

    dealers = []

    seen = set()

    queries = [

        f'"معرض سيارات" "{district}"',

        f'"معرض" "سيارات" "{district}"',

        f'"معارض سيارات" "{district}"',

        f'"تاجر سيارات" "{district}"',

        f'"car dealer" "{district}" Egypt',

        f'"used cars" "{district}" Egypt',

        f'"cars showroom" "{district}" Egypt',

    ]

    for query in queries:

        results = search_web(
            query,
            max_results=15
        )

        time.sleep(0.5)

        for result in results:

            title = result.get(
                "title",
                ""
            )

            snippet = result.get(
                "snippet",
                ""
            )

            url = result.get(
                "url",
                ""
            )

            combined = (
                f"{title} {snippet}"
            ).lower()

            # We want results that have some
            # indication of automotive activity.
            keywords = [
                "سيارات",
                "معرض",
                "cars",
                "motors",
                "auto",
                "dealer",
                "automotive",
                "showroom",
            ]

            if not any(
                word.lower() in combined
                for word in keywords
            ):
                continue

            dealer_name = extract_dealer_name(
                title,
                snippet
            )

            if not dealer_name:
                continue

            key = normalize_name(
                dealer_name
            )

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            phone = extract_phone(
                f"{title} {snippet}"
            )

            dealers.append({
                "اسم المعرض": dealer_name,
                "المنطقة": district,
                "الهاتف": phone,
                "مصدر الاكتشاف": url,
                "وصف المصدر": snippet,
            })

            if len(dealers) >= max_results:
                return dealers

    return dealers


# =========================================================
# PLATFORM VERIFICATION
# =========================================================

def verify_dealer(dealer_name):

    result = {

        "Dubizzle": "غير متحقق",
        "Dubizzle Results": 0,
        "Dubizzle URL": "",

        "ContactCars": "غير متحقق",
        "ContactCars Results": 0,
        "ContactCars URL": "",
    }

    # -----------------------------------------
    # Dubizzle
    # -----------------------------------------

    try:

        dubizzle = get_dubizzle_status(
            dealer_name
        )

        result["Dubizzle"] = dubizzle.get(
            "status",
            "غير متحقق"
        )

        result["Dubizzle Results"] = dubizzle.get(
            "listing_count",
            0
        )

        result["Dubizzle URL"] = dubizzle.get(
            "url",
            ""
        )

    except Exception:
        pass

    # -----------------------------------------
    # ContactCars
    # -----------------------------------------

    try:

        contactcars = get_contactcars_status(
            dealer_name
        )

        result["ContactCars"] = contactcars.get(
            "status",
            "غير متحقق"
        )

        result["ContactCars Results"] = contactcars.get(
            "listing_count",
            0
        )

        result["ContactCars URL"] = contactcars.get(
            "url",
            ""
        )

    except Exception:
        pass

    return result


# =========================================================
# SCORE
# =========================================================

def calculate_score(row):

    score = 0

    if row.get("الهاتف"):
        score += 20

    if row.get("Dubizzle") == "نعم":
        score += 25

    if row.get("ContactCars") == "نعم":
        score += 25

    try:

        if int(
            row.get(
                "Dubizzle Results",
                0
            )
        ) > 0:
            score += 10

    except Exception:
        pass

    try:

        if int(
            row.get(
                "ContactCars Results",
                0
            )
        ) > 0:
            score += 10

    except Exception:
        pass

    if row.get("مصدر الاكتشاف"):
        score += 5

    if row.get("المنطقة"):
        score += 5

    return min(
        score,
        100
    )


def score_label(score):

    if score >= 80:
        return "🔥 Hot Lead"

    if score >= 60:
        return "🟢 Good Lead"

    if score >= 40:
        return "🟡 Medium"

    return "⚪ Weak"


# =========================================================
# WHATSAPP
# =========================================================

def create_whatsapp_message(
    dealer_name
):

    return (
        f"السلام عليكم، مع حضرتك من فريق متخصص "
        f"في حلول التسويق وإدارة العملاء لمعارض السيارات.\n\n"
        f"لاحظنا نشاط {dealer_name} في سوق السيارات، "
        f"وحابين نتواصل مع حضرتك بخصوص فرصة تساعد "
        f"المعرض في زيادة العملاء المحتملين وتحسين "
        f"متابعة الـ leads.\n\n"
        f"لو مناسب، ممكن نتواصل مع حضرتك في الوقت المناسب؟"
    )


# =========================================================
# PIPELINE
# =========================================================

def run_pipeline(
    district,
    max_results
):

    dealers = discover_dealers(
        district,
        max_results
    )

    if not dealers:
        return pd.DataFrame()

    progress = st.progress(0)

    processed = []

    total = len(dealers)

    for index, dealer in enumerate(
        dealers
    ):

        name = dealer[
            "اسم المعرض"
        ]

        verification = verify_dealer(
            name
        )

        dealer.update(
            verification
        )

        dealer[
            "الإعلانات الشهرية"
        ] = "غير متاح"

        message = create_whatsapp_message(
            name
        )

        dealer[
            "رسالة واتساب"
        ] = message

        dealer[
            "Google Maps"
        ] = google_maps_link(
            name,
            district
        )

        dealer[
            "WhatsApp"
        ] = whatsapp_link(
            dealer.get(
                "الهاتف",
                ""
            ),
            message
        )

        dealer[
            "Score"
        ] = calculate_score(
            dealer
        )

        dealer[
            "Lead Quality"
        ] = score_label(
            dealer["Score"]
        )

        processed.append(
            dealer
        )

        progress.progress(
            (index + 1) / total
        )

    try:

        processed = remove_duplicate_dealers(
            processed
        )

    except Exception:
        pass

    return pd.DataFrame(
        processed
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header(
        "⚙️ Search Settings"
    )

    district = st.selectbox(
        "اختر المنطقة",
        DISTRICTS
    )

    max_results = st.slider(
        "عدد النتائج",
        min_value=5,
        max_value=50,
        value=20,
        step=5
    )

    st.divider()

    st.info(
        "سيتم البحث عن معارض حقيقية ومحاولة "
        "التحقق من وجودها على المنصات."
    )


# =========================================================
# SEARCH BUTTON
# =========================================================

if st.sidebar.button(
    "🚀 Start Lead Discovery",
    use_container_width=True
):

    with st.spinner(
        f"🔎 جاري البحث عن معارض سيارات في {district}..."
    ):

        df = run_pipeline(
            district,
            max_results
        )

    if df.empty:

        st.warning(
            "لم يتم العثور على نتائج مناسبة. "
            "جرب منطقة أخرى."
        )

    else:

        st.session_state[
            "dealer_results"
        ] = df

        st.success(
            f"✅ تم العثور على {len(df)} معرض."
        )


# =========================================================
# RESULTS
# =========================================================

if "dealer_results" in st.session_state:

    df = st.session_state[
        "dealer_results"
    ]

    st.subheader(
        "📊 Dealer Leads"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Leads",
        len(df)
    )

    col2.metric(
        "Hot Leads",
        len(
            df[
                df["Lead Quality"]
                == "🔥 Hot Lead"
            ]
        )
    )

    col3.metric(
        "Dubizzle Verified",
        int(
            (
                df["Dubizzle"]
                == "نعم"
            ).sum()
        )
    )

    col4.metric(
        "ContactCars Verified",
        int(
            (
                df["ContactCars"]
                == "نعم"
            ).sum()
        )
    )

    st.divider()

    st.warning(
        "⚠️ أرقام Results الحالية هي نتائج بحث مرتبطة "
        "بالاسم، وليست العدد الحقيقي المؤكد لإعلانات "
        "المعرض. سنطور العد المباشر للإعلانات لاحقًا."
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # DETAILS
    # =====================================================

    st.subheader(
        "📌 Lead Details"
    )

    selected = st.selectbox(
        "اختر معرض",
        df[
            "اسم المعرض"
        ].tolist()
    )

    row = df[
        df["اسم المعرض"]
        == selected
    ].iloc[0]

    col1, col2 = st.columns(2)

    with col1:

        st.markdown(
            f"### 🏢 {row['اسم المعرض']}"
        )

        st.write(
            f"📍 المنطقة: {row.get('المنطقة', '')}"
        )

        st.write(
            f"📞 الهاتف: "
            f"{row.get('الهاتف', '') or 'غير متاح'}"
        )

        st.write(
            f"⭐ Score: {row.get('Score', 0)}"
        )

        st.write(
            f"🎯 Quality: "
            f"{row.get('Lead Quality', '')}"
        )

    with col2:

        st.markdown(
            "### 🌐 Verification"
        )

        st.write(
            f"Dubizzle: "
            f"{row.get('Dubizzle', 'غير متحقق')}"
        )

        st.write(
            f"ContactCars: "
            f"{row.get('ContactCars', 'غير متحقق')}"
        )

        st.write(
            f"Dubizzle Results: "
            f"{row.get('Dubizzle Results', 0)}"
        )

        st.write(
            f"ContactCars Results: "
            f"{row.get('ContactCars Results', 0)}"
        )

    st.markdown(
        "### 💬 WhatsApp"
    )

    st.text_area(
        "الرسالة",
        value=row.get(
            "رسالة واتساب",
            ""
        ),
        height=160
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        if row.get("WhatsApp"):

            st.link_button(
                "💬 WhatsApp",
                row["WhatsApp"],
                use_container_width=True
            )

    with c2:

        if row.get("Google Maps"):

            st.link_button(
                "📍 Google Maps",
                row["Google Maps"],
                use_container_width=True
            )

    with c3:

        if row.get("مصدر الاكتشاف"):

            st.link_button(
                "🔎 Source",
                row["مصدر الاكتشاف"],
                use_container_width=True
            )

    # =====================================================
    # EXPORT
    # =====================================================

    st.divider()

    st.subheader(
        "📥 Export"
    )

    csv_data = df.to_csv(
        index=False,
        encoding="utf-8-sig"
    )

    st.download_button(
        "⬇️ Download CSV",
        data=csv_data,
        file_name="car_dealer_leads.csv",
        mime="text/csv",
        use_container_width=True
    )

    try:

        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(
            excel_buffer,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name="Dealer Leads"
            )

        excel_buffer.seek(0)

        st.download_button(
            "📊 Download Excel",
            data=excel_buffer,
            file_name="car_dealer_leads.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True
        )

    except Exception as e:

        st.error(
            f"Excel Error: {e}"
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Egypt Car Dealer Lead Intelligence • "
    "Discovery + Verification + Lead Scoring"
)
