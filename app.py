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
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Egypt Car Dealer Lead Intelligence",
    page_icon="🚗",
    layout="wide",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}

SEARCH_TIMEOUT = 8


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
# TEXT
# =========================================================

def clean_text(value):
    if not value:
        return ""

    text = BeautifulSoup(
        str(value),
        "html.parser"
    ).get_text(" ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


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


# =========================================================
# PHONE
# =========================================================

def extract_phone(text):

    if not text:
        return ""

    text = str(text)

    patterns = [
        r"01[0125]\d{8}",
        r"01[0125][\s\-]?\d{3}[\s\-]?\d{4}",
        r"\+20[\s\-]?1[0125][\s\-]?\d{8}",
        r"0020[\s\-]?1[0125][\s\-]?\d{8}",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
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


# =========================================================
# LINKS
# =========================================================

def google_maps_link(name, district):

    query = urllib.parse.quote(
        f"{name} {district} Egypt"
    )

    return (
        "https://www.google.com/maps/search/?api=1&query="
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

    return (
        "https://wa.me/"
        + phone
        + "?text="
        + urllib.parse.quote(message)
    )


# =========================================================
# SEARCH ENGINE
# =========================================================

def search_duckduckgo(
    query,
    max_results=10
):

    try:

        url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote(query)
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT
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

            url = link_element.get(
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

            if title and url:

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


def search_bing(
    query,
    max_results=10
):

    try:

        url = (
            "https://www.bing.com/search?q="
            + urllib.parse.quote(query)
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(
            "li.b_algo"
        ):

            title_element = result.select_one(
                "h2 a"
            )

            if not title_element:
                continue

            title = clean_text(
                title_element.get_text(
                    " ",
                    strip=True
                )
            )

            url = title_element.get(
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

            if title and url:

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                })

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


def search_web(
    query,
    max_results=10
):

    results = search_duckduckgo(
        query,
        max_results
    )

    if results:
        return results

    return search_bing(
        query,
        max_results
    )


# =========================================================
# VALIDATION
# =========================================================

EGYPT_WORDS = [
    "مصر",
    "القاهرة",
    "الجيزة",
    "مدينة نصر",
    "مصر الجديدة",
    "التجمع",
    "المعادي",
    "المقطم",
    "المهندسين",
    "الدقي",
    "العجوزة",
    "الهرم",
    "فيصل",
    "شبرا",
    "العبور",
    "الشروق",
    "مدينتي",
    "زايد",
    "أكتوبر",
    "egypt",
    "cairo",
    "giza",
]


CAR_WORDS = [
    "سيارات",
    "سياره",
    "سيارة",
    "معرض",
    "معارض",
    "تاجر",
    "تجار",
    "كار",
    "cars",
    "car",
    "dealer",
    "dealers",
    "motors",
    "motor",
    "auto",
    "automotive",
    "showroom",
]


BAD_WORDS = [
    "carfax",
    "denver",
    "texas",
    "california",
    "florida",
    "new york",
    "los angeles",
    "used cars for sale",
    "cars for sale",
    "wikipedia",
    "pinterest",
    "amazon",
    "ebay",
]


def is_egyptian_result(
    title,
    snippet,
    district
):

    text = normalize_name(
        f"{title} {snippet}"
    )

    # ممنوع نتائج أجنبية واضحة
    for bad in BAD_WORDS:

        if normalize_name(bad) in text:
            return False

    # لازم يكون فيه نشاط سيارات
    has_car_word = any(
        normalize_name(word) in text
        for word in CAR_WORDS
    )

    if not has_car_word:
        return False

    # لازم يكون فيه إشارة لمصر/القاهرة
    has_egypt_word = any(
        normalize_name(word) in text
        for word in EGYPT_WORDS
    )

    # أو يكون اسم المنطقة نفسه ظاهر
    district_normalized = normalize_name(
        district
    )

    if district_normalized in text:
        has_egypt_word = True

    return has_egypt_word


# =========================================================
# EXTRACT REAL DEALER NAME
# =========================================================

def extract_dealer_name(
    title,
    snippet="",
    source_url=""
):

    title = clean_text(title)
    snippet = clean_text(snippet)

    if not title:
        return ""

    name = title

    # Facebook / Instagram / Google suffixes
    suffixes = [
        r"\s*[-|]\s*Facebook.*$",
        r"\s*[-|]\s*Instagram.*$",
        r"\s*[-|]\s*Google.*$",
        r"\s*[-|]\s*YouTube.*$",
        r"\s*[-|]\s*Dubizzle.*$",
        r"\s*[-|]\s*ContactCars.*$",
    ]

    for pattern in suffixes:

        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE
        )

    name = clean_text(name)

    # أسماء عامة لا تعتبر معرض
    generic_names = [
        "معرض سيارات",
        "معارض سيارات",
        "سيارات للبيع",
        "سيارات مستعملة",
        "سيارات جديدة",
        "used cars",
        "used cars for sale",
        "cars for sale",
        "car dealer",
        "car dealers",
        "car dealership",
        "cars showroom",
        "dealership",
        "dubizzle",
        "contactcars",
        "facebook",
    ]

    normalized = normalize_name(
        name
    )

    for generic in generic_names:

        if normalized == normalize_name(
            generic
        ):
            return ""

    # عناوين CARFAX وأشباهها
    bad_name_parts = [
        "carfax",
        "cars for sale in",
        "used cars for sale in",
        "new cars for sale in",
        "wikipedia",
    ]

    for bad in bad_name_parts:

        if normalize_name(bad) in normalized:
            return ""

    # لا نقبل عنوانًا طويلًا جدًا
    if len(name) > 100:
        return ""

    return name


# =========================================================
# FACEBOOK SEARCH
# =========================================================

def search_facebook(
    dealer_name,
    district
):

    queries = [
        f'"{dealer_name}" Facebook Egypt',
        f'"{dealer_name}" "{district}" Facebook',
    ]

    for query in queries:

        results = search_web(
            query,
            max_results=5
        )

        for result in results:

            url = result.get(
                "url",
                ""
            ).lower()

            title = result.get(
                "title",
                ""
            )

            snippet = result.get(
                "snippet",
                ""
            )

            if (
                "facebook.com" in url
                or "facebook" in title.lower()
                or "facebook" in snippet.lower()
            ):

                return {
                    "url": result.get(
                        "url",
                        ""
                    ),
                    "phone": extract_phone(
                        f"{title} {snippet}"
                    ),
                }

    return {
        "url": "",
        "phone": "",
    }


# =========================================================
# DISCOVERY
# =========================================================

def discover_dealers(
    district,
    max_results
):

    dealers = []
    seen_names = set()

    # عدد قليل من البحثات حتى يكون سريع
    queries = [

        f'"معرض سيارات" "{district}" مصر',

        f'"معارض سيارات" "{district}"',

        f'"car dealer" "{district}" Egypt',

    ]

    for query in queries:

        results = search_web(
            query,
            max_results=10
        )

        time.sleep(0.3)

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

            # ---------------------------------------------
            # MUST LOOK EGYPTIAN
            # ---------------------------------------------

            if not is_egyptian_result(
                title,
                snippet,
                district
            ):
                continue

            # ---------------------------------------------
            # EXTRACT NAME
            # ---------------------------------------------

            dealer_name = extract_dealer_name(
                title,
                snippet,
                url
            )

            if not dealer_name:
                continue

            normalized = normalize_name(
                dealer_name
            )

            if not normalized:
                continue

            if normalized in seen_names:
                continue

            # ---------------------------------------------
            # PHONE
            # ---------------------------------------------

            phone = extract_phone(
                f"{title} {snippet}"
            )

            # ---------------------------------------------
            # FACEBOOK
            # ---------------------------------------------

            facebook = search_facebook(
                dealer_name,
                district
            )

            if not phone:
                phone = facebook.get(
                    "phone",
                    ""
                )

            # ---------------------------------------------
            # ADD
            # ---------------------------------------------

            seen_names.add(
                normalized
            )

            dealers.append({
                "اسم المعرض": dealer_name,
                "المنطقة": district,
                "الهاتف": phone,
                "Facebook": facebook.get(
                    "url",
                    ""
                ),
                "مصدر الاكتشاف": url,
                "وصف المصدر": snippet,
            })

            if len(dealers) >= max_results:
                return dealers

    return dealers


# =========================================================
# PLATFORM VERIFICATION
# =========================================================

def verify_dealer(
    dealer_name
):

    result = {
        "Dubizzle": "غير متحقق",
        "Dubizzle Results": 0,
        "Dubizzle URL": "",

        "ContactCars": "غير متحقق",
        "ContactCars Results": 0,
        "ContactCars URL": "",
    }

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
        score += 25

    if row.get("Facebook"):
        score += 15

    if row.get("Dubizzle") == "نعم":
        score += 20

    if row.get("ContactCars") == "نعم":
        score += 20

    if row.get("المنطقة"):
        score += 10

    if row.get("مصدر الاكتشاف"):
        score += 10

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

        verification = verify_dealer(
            dealer["اسم المعرض"]
        )

        dealer.update(
            verification
        )

        dealer[
            "الإعلانات الشهرية"
        ] = "غير متاح"

        message = create_whatsapp_message(
            dealer["اسم المعرض"]
        )

        dealer[
            "رسالة واتساب"
        ] = message

        dealer[
            "Google Maps"
        ] = google_maps_link(
            dealer["اسم المعرض"],
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
# UI
# =========================================================

st.title(
    "🚗 Egypt Car Dealer Lead Intelligence"
)

st.markdown(
    "اكتشاف معارض السيارات المصرية والتحقق من بياناتها."
)

with st.sidebar:

    st.header(
        "⚙️ Search Settings"
    )

    district = st.selectbox(
        "اختر المنطقة",
        DISTRICTS
    )

    max_results = st.slider(
        "عدد المعارض",
        5,
        20,
        10
    )

    st.caption(
        "النسخة الحالية تركز على جودة الاكتشاف "
        "قبل زيادة عدد النتائج."
    )


if st.sidebar.button(
    "🚀 Start Lead Discovery",
    use_container_width=True
):

    with st.spinner(
        f"🔎 جاري البحث عن معارض حقيقية في {district}..."
    ):

        df = run_pipeline(
            district,
            max_results
        )

    if df.empty:

        st.warning(
            "لم يتم العثور على معارض موثوقة. "
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

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "المعارض",
        len(df)
    )

    c2.metric(
        "Hot Leads",
        int(
            (
                df["Lead Quality"]
                == "🔥 Hot Lead"
            ).sum()
        )
    )

    c3.metric(
        "معها هاتف",
        int(
            df["الهاتف"]
            .fillna("")
            .astype(str)
            .ne("")
            .sum()
        )
    )

    c4.metric(
        "Facebook",
        int(
            df["Facebook"]
            .fillna("")
            .astype(str)
            .ne("")
            .sum()
        )
    )

    st.divider()

    st.dataframe(
        df[
            [
                "اسم المعرض",
                "المنطقة",
                "الهاتف",
                "Facebook",
                "Dubizzle",
                "ContactCars",
                "Score",
                "Lead Quality",
            ]
        ],
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
        df["اسم المعرض"].tolist()
    )

    row = df[
        df["اسم المعرض"]
        == selected
    ].iloc[0]

    c1, c2 = st.columns(2)

    with c1:

        st.markdown(
            f"### 🏢 {row['اسم المعرض']}"
        )

        st.write(
            f"📍 المنطقة: {row['المنطقة']}"
        )

        st.write(
            f"📞 الهاتف: "
            f"{row['الهاتف'] or 'غير متاح'}"
        )

        st.write(
            f"⭐ Score: {row['Score']}"
        )

        st.write(
            f"🎯 {row['Lead Quality']}"
        )

    with c2:

        st.markdown(
            "### 🌐 Verification"
        )

        st.write(
            f"Dubizzle: {row['Dubizzle']}"
        )

        st.write(
            f"ContactCars: {row['ContactCars']}"
        )

    st.markdown(
        "### 🔗 Sources"
    )

    l1, l2, l3 = st.columns(3)

    with l1:

        if row.get("Facebook"):

            st.link_button(
                "📘 Facebook",
                row["Facebook"],
                use_container_width=True
            )

    with l2:

        if row.get("Google Maps"):

            st.link_button(
                "📍 Google Maps",
                row["Google Maps"],
                use_container_width=True
            )

    with l3:

        if row.get("WhatsApp"):

            st.link_button(
                "💬 WhatsApp",
                row["WhatsApp"],
                use_container_width=True
            )

    st.markdown(
        "### 💬 WhatsApp Message"
    )

    st.text_area(
        "الرسالة",
        value=row.get(
            "رسالة واتساب",
            ""
        ),
        height=160
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
        file_name="egypt_car_dealer_leads.csv",
        mime="text/csv",
        use_container_width=True
    )

    try:

        buffer = io.BytesIO()

        with pd.ExcelWriter(
            buffer,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name="Dealer Leads"
            )

        buffer.seek(0)

        st.download_button(
            "📊 Download Excel",
            data=buffer,
            file_name="egypt_car_dealer_leads.xlsx",
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
    "Egyptian Dealer Discovery + Verification"
)
