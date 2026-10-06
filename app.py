import re
import time
import urllib.parse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

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

REQUEST_DELAY = 0.7

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}


# =========================================================
# DISTRICTS
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
    "العجوزة",
    "المهندسين",
    "الدقي",
    "الهرم",
    "فيصل",
    "وسط البلد",
    "شبرا",
    "حلوان",
    "العبور",
    "الشروق",
    "مدينتي",
    "العاشر من رمضان",
]


# =========================================================
# TEXT HELPERS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_name(name):
    if not name:
        return ""

    name = str(name).lower()

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"[^\w\s\u0600-\u06FF]", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def is_similar_name(name1, name2, threshold=82):
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False

    if n1 == n2:
        return True

    return fuzz.token_set_ratio(n1, n2) >= threshold


# =========================================================
# PHONE
# =========================================================

def extract_phone(text):
    if not text:
        return ""

    text = str(text)

    patterns = [
        r"(?:\+20|0020)?\s*01[0125]\s*[-\s]?\d{3}\s*[-\s]?\d{4}",
        r"01[0125]\d{8}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            phone = re.sub(r"[^\d+]", "", match.group(0))

            if phone.startswith("0020"):
                phone = "+" + phone[2:]

            elif phone.startswith("01"):
                phone = "+20" + phone[1:]

            return phone

    return ""


# =========================================================
# LINKS
# =========================================================

def google_maps_link(dealer_name, district):
    query = urllib.parse.quote(
        f"{dealer_name} {district} Egypt"
    )

    return f"https://www.google.com/maps/search/?api=1&query={query}"


def whatsapp_link(phone, message):
    if not phone:
        return ""

    phone = re.sub(r"[^\d]", "", str(phone))

    if phone.startswith("0"):
        phone = "20" + phone[1:]

    encoded_message = urllib.parse.quote(message)

    return (
        f"https://wa.me/{phone}"
        f"?text={encoded_message}"
    )


# =========================================================
# DUCKDUCKGO SEARCH
# =========================================================

def search_duckduckgo(query, max_results=10):
    """
    Search DuckDuckGo HTML results.

    This is used for dealer discovery only.
    Platform verification is handled by the dedicated modules.
    """

    try:
        url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote(query)
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for result in soup.select(".result"):
            title_element = result.select_one(".result__title")

            if not title_element:
                continue

            link_element = title_element.find("a")

            if not link_element:
                continue

            title = clean_text(
                link_element.get_text(" ", strip=True)
            )

            href = link_element.get("href", "")

            snippet_element = result.select_one(
                ".result__snippet"
            )

            snippet = ""

            if snippet_element:
                snippet = clean_text(
                    snippet_element.get_text(
                        " ",
                        strip=True
                    )
                )

            if title and href:
                results.append(
                    {
                        "title": title,
                        "url": href,
                        "snippet": snippet,
                    }
                )

            if len(results) >= max_results:
                break

        return results

    except Exception:
        return []


# =========================================================
# DEALER NAME EXTRACTION
# =========================================================

def extract_dealer_name(title, snippet=""):
    """
    Try to get a cleaner dealer name from a search result.

    This is intentionally conservative so the app doesn't
    automatically invent a dealership name.
    """

    title = clean_text(title)
    snippet = clean_text(snippet)

    if not title:
        return ""

    # Remove common search-result suffixes
    patterns = [
        r"\s*[-|]\s*Dubizzle.*$",
        r"\s*[-|]\s*ContactCars.*$",
        r"\s*[-|]\s*Facebook.*$",
        r"\s*[-|]\s*Instagram.*$",
        r"\s*[-|]\s*Google.*$",
        r"\s*[-|]\s*YouTube.*$",
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

    # Reject obvious non-dealer pages
    rejected_words = [
        "سيارة للبيع",
        "سيارات للبيع",
        "سيارات مستعملة",
        "سيارات جديدة",
        "cars for sale",
        "used cars",
        "new cars",
        "dealer near me",
        "dealers near me",
        "dubizzle",
        "contactcars",
    ]

    lowered = name.lower()

    for word in rejected_words:
        if word.lower() in lowered:
            return ""

    # If title is too short, use it only if it looks meaningful
    if len(name) < 3:
        return ""

    return name


# =========================================================
# DEALER DISCOVERY
# =========================================================

def discover_dealers(district, max_dealers=20):
    """
    Discover possible dealerships in a selected Egyptian district.

    Discovery is separated from verification.
    A discovered name is NOT automatically considered verified.
    """

    queries = [
        f"معارض سيارات {district} مصر",
        f"معرض سيارات {district}",
        f"تجار سيارات {district}",
        f"car dealer {district} Egypt",
        f"used car dealer {district} Egypt",
    ]

    discovered = []

    for query in queries:

        results = search_duckduckgo(
            query,
            max_results=10
        )

        time.sleep(REQUEST_DELAY)

        for result in results:

            dealer_name = extract_dealer_name(
                result["title"],
                result.get("snippet", "")
            )

            if not dealer_name:
                continue

            # Avoid obvious duplicate names
            already_exists = False

            for dealer in discovered:
                if is_similar_name(
                    dealer["اسم المعرض"],
                    dealer_name
                ):
                    already_exists = True
                    break

            if already_exists:
                continue

            phone = extract_phone(
                result.get("title", "")
                + " "
                + result.get("snippet", "")
            )

            discovered.append(
                {
                    "اسم المعرض": dealer_name,
                    "المنطقة": district,
                    "الهاتف": phone,
                    "مصدر الاكتشاف": result["url"],
                    "وصف المصدر": result.get(
                        "snippet",
                        ""
                    ),
                }
            )

            if len(discovered) >= max_dealers:
                break

        if len(discovered) >= max_dealers:
            break

    return discovered


# =========================================================
# PLATFORM VERIFICATION
# =========================================================

def verify_dealer(dealer_name):
    """
    Verify dealership presence on Dubizzle and ContactCars
    using the dedicated modules.
    """

    result = {
        "Dubizzle": "غير متحقق",
        "Dubizzle Results": 0,
        "Dubizzle URL": "",
        "ContactCars": "غير متحقق",
        "ContactCars Results": 0,
        "ContactCars URL": "",
    }

    # -------------------------
    # DUBIZZLE
    # -------------------------

    try:
        dubizzle = get_dubizzle_status(
            dealer_name
        )

        if dubizzle:
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

    # -------------------------
    # CONTACTCARS
    # -------------------------

    try:
        contactcars = get_contactcars_status(
            dealer_name
        )

        if contactcars:
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

    # Phone
    if row.get("الهاتف"):
        score += 20

    # Dubizzle
    if row.get("Dubizzle") == "نعم":
        score += 25

    # ContactCars
    if row.get("ContactCars") == "نعم":
        score += 25

    # Results
    try:
        dubizzle_results = int(
            row.get("Dubizzle Results", 0)
        )
    except Exception:
        dubizzle_results = 0

    try:
        contactcars_results = int(
            row.get("ContactCars Results", 0)
        )
    except Exception:
        contactcars_results = 0

    if dubizzle_results > 0:
        score += 10

    if contactcars_results > 0:
        score += 10

    # Discovery source
    if row.get("مصدر الاكتشاف"):
        score += 5

    # District
    if row.get("المنطقة"):
        score += 5

    return min(score, 100)


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

def create_whatsapp_message(dealer_name):
    return (
        f"السلام عليكم، مع حضرتك من فريق متخصص في حلول "
        f"التسويق وإدارة العملاء لمعارض السيارات.\n\n"
        f"لاحظنا نشاط {dealer_name} في سوق السيارات، "
        f"وحابين نتواصل مع حضرتك بخصوص فرصة تساعد المعرض "
        f"في زيادة العملاء المحتملين وتحسين متابعة الـ leads.\n\n"
        f"لو مناسب، ممكن نتواصل مع حضرتك في الوقت المناسب؟"
    )


# =========================================================
# PIPELINE
# =========================================================

def run_pipeline(district, max_dealers):
    st.info(
        f"🔎 جاري البحث عن معارض سيارات في {district}..."
    )

    dealers = discover_dealers(
        district,
        max_dealers
    )

    if not dealers:
        return pd.DataFrame()

    st.info(
        f"تم اكتشاف {len(dealers)} نتيجة مبدئية. "
        f"جاري التحقق من المنصات..."
    )

    progress = st.progress(0)

    verified_dealers = []

    total = len(dealers)

    for index, dealer in enumerate(dealers):

        dealer_name = dealer["اسم المعرض"]

        verification = verify_dealer(
            dealer_name
        )

        dealer.update(
            verification
        )

        # ---------------------------------------------
        # IMPORTANT:
        # Current platform modules return search-result
        # counts, not guaranteed real ad counts.
        # ---------------------------------------------

        dealer["الإعلانات الشهرية"] = "غير متاح"

        message = create_whatsapp_message(
            dealer_name
        )

        dealer["رسالة واتساب"] = message

        dealer["Google Maps"] = google_maps_link(
            dealer_name,
            district
        )

        dealer["WhatsApp"] = whatsapp_link(
            dealer.get("الهاتف", ""),
            message
        )

        dealer["Score"] = calculate_score(
            dealer
        )

        dealer["Lead Quality"] = score_label(
            dealer["Score"]
        )

        verified_dealers.append(
            dealer
        )

        progress.progress(
            (index + 1) / total
        )

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    try:
        final_dealers = remove_duplicate_dealers(
            verified_dealers
        )
    except Exception:
        final_dealers = verified_dealers

    return pd.DataFrame(final_dealers)


# =========================================================
# UI
# =========================================================

st.title(
    "🚗 Egypt Car Dealer Lead Intelligence"
)

st.markdown(
    """
    اكتشاف وتحليل معارض السيارات في مصر،
    مع محاولة التحقق من وجودها على Dubizzle و ContactCars
    وتجهيز بيانات التواصل والـ WhatsApp.
    """
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Search Settings")

district = st.sidebar.selectbox(
    "اختر المنطقة",
    DISTRICTS
)

max_dealers = st.sidebar.slider(
    "عدد النتائج",
    min_value=5,
    max_value=50,
    value=20,
    step=5
)


# =========================================================
# SEARCH BUTTON
# =========================================================

if st.sidebar.button(
    "🚀 Start Lead Discovery",
    use_container_width=True
):

    with st.spinner(
        "جاري اكتشاف وتحليل المعارض..."
    ):

        df = run_pipeline(
            district,
            max_dealers
        )

    if df.empty:

        st.warning(
            "لم يتم العثور على نتائج مناسبة. "
            "جرب منطقة أخرى."
        )

    else:

        st.session_state["dealer_results"] = df

        st.success(
            f"تم تجهيز {len(df)} lead."
        )


# =========================================================
# RESULTS
# =========================================================

if "dealer_results" in st.session_state:

    df = st.session_state["dealer_results"]

    st.subheader(
        "📊 Dealer Leads"
    )

    # -----------------------------------------------------
    # METRICS
    # -----------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Leads",
            len(df)
        )

    with col2:
        hot_leads = len(
            df[
                df["Lead Quality"]
                == "🔥 Hot Lead"
            ]
        )

        st.metric(
            "Hot Leads",
            hot_leads
        )

    with col3:
        dubizzle_count = len(
            df[
                df["Dubizzle"]
                == "نعم"
            ]
        )

        st.metric(
            "Dubizzle Verified",
            dubizzle_count
        )

    with col4:
        contactcars_count = len(
            df[
                df["ContactCars"]
                == "نعم"
            ]
        )

        st.metric(
            "ContactCars Verified",
            contactcars_count
        )

    st.divider()

    # -----------------------------------------------------
    # NOTICE
    # -----------------------------------------------------

    st.warning(
        "⚠️ ملاحظة: أرقام Dubizzle Results و "
        "ContactCars Results في النسخة الحالية تمثل "
        "نتائج البحث التي تم العثور عليها، وليست بالضرورة "
        "العدد الحقيقي لإعلانات المعرض على المنصة. "
        "سيتم تطوير العدّ المباشر للإعلانات في خطوة لاحقة."
    )

    # -----------------------------------------------------
    # FILTER
    # -----------------------------------------------------

    search_text = st.text_input(
        "🔎 ابحث داخل النتائج",
        placeholder="اسم المعرض أو المنطقة أو الهاتف..."
    )

    filtered_df = df.copy()

    if search_text:

        mask = (
            filtered_df.astype(str)
            .apply(
                lambda row: row.str.contains(
                    search_text,
                    case=False,
                    na=False
                ).any(),
                axis=1
            )
        )

        filtered_df = filtered_df[mask]

    # -----------------------------------------------------
    # TABLE
    # -----------------------------------------------------

    display_columns = [
        "اسم المعرض",
        "المنطقة",
        "الهاتف",
        "Dubizzle",
        "Dubizzle Results",
        "ContactCars",
        "ContactCars Results",
        "Score",
        "Lead Quality",
        "الإعلانات الشهرية",
    ]

    available_columns = [
        col
        for col in display_columns
        if col in filtered_df.columns
    ]

    st.dataframe(
        filtered_df[available_columns],
        use_container_width=True,
        hide_index=True
    )

    # -----------------------------------------------------
    # DETAILS
    # -----------------------------------------------------

    st.subheader(
        "📌 Lead Details"
    )

    selected_dealer = st.selectbox(
        "اختر معرض",
        filtered_df["اسم المعرض"].tolist()
    )

    selected_rows = filtered_df[
        filtered_df["اسم المعرض"]
        == selected_dealer
    ]

    if not selected_rows.empty:

        row = selected_rows.iloc[0]

        c1, c2 = st.columns(2)

        with c1:

            st.markdown(
                f"### 🏢 {row['اسم المعرض']}"
            )

            st.write(
                f"📍 المنطقة: {row.get('المنطقة', '')}"
            )

            st.write(
                f"📞 الهاتف: {row.get('الهاتف', '') or 'غير متاح'}"
            )

            st.write(
                f"⭐ Score: {row.get('Score', 0)}"
            )

            st.write(
                f"🎯 Quality: {row.get('Lead Quality', '')}"
            )

        with c2:

            st.markdown(
                "### 🌐 Platform Verification"
            )

            st.write(
                f"Dubizzle: {row.get('Dubizzle', 'غير متحقق')}"
            )

            st.write(
                f"Dubizzle Results: "
                f"{row.get('Dubizzle Results', 0)}"
            )

            st.write(
                f"ContactCars: "
                f"{row.get('ContactCars', 'غير متحقق')}"
            )

            st.write(
                f"ContactCars Results: "
                f"{row.get('ContactCars Results', 0)}"
            )

        st.markdown(
            "### 💬 WhatsApp Message"
        )

        message = row.get(
            "رسالة واتساب",
            ""
        )

        st.text_area(
            "الرسالة",
            value=message,
            height=180
        )

        # -------------------------------------------------
        # LINKS
        # -------------------------------------------------

        link_col1, link_col2, link_col3 = st.columns(3)

        with link_col1:

            maps_url = row.get(
                "Google Maps",
                ""
            )

            if maps_url:
                st.link_button(
                    "📍 Google Maps",
                    maps_url,
                    use_container_width=True
                )

        with link_col2:

            whatsapp_url = row.get(
                "WhatsApp",
                ""
            )

            if whatsapp_url:
                st.link_button(
                    "💬 WhatsApp",
                    whatsapp_url,
                    use_container_width=True
                )
            else:
                st.caption(
                    "لا يوجد رقم هاتف متاح"
                )

        with link_col3:

            source_url = row.get(
                "مصدر الاكتشاف",
                ""
            )

            if source_url:
                st.link_button(
                    "🔎 Source",
                    source_url,
                    use_container_width=True
                )


    # =====================================================
    # EXPORT
    # =====================================================

    st.divider()

    st.subheader(
        "📥 Export"
    )

    export_columns = [
        "اسم المعرض",
        "المنطقة",
        "الهاتف",
        "Dubizzle",
        "Dubizzle Results",
        "Dubizzle URL",
        "ContactCars",
        "ContactCars Results",
        "ContactCars URL",
        "الإعلانات الشهرية",
        "Score",
        "Lead Quality",
        "Google Maps",
        "WhatsApp",
        "رسالة واتساب",
        "مصدر الاكتشاف",
    ]

    export_columns = [
        col
        for col in export_columns
        if col in df.columns
    ]

    export_df = df[export_columns].copy()

    csv_data = export_df.to_csv(
        index=False,
        encoding="utf-8-sig"
    )

    st.download_button(
        "⬇️ Download CSV",
        data=csv_data,
        file_name=(
            f"car_dealer_leads_"
            f"{district}.csv"
        ),
        mime="text/csv",
        use_container_width=True
    )

    # Excel
    try:

        import io

        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(
            excel_buffer,
            engine="openpyxl"
        ) as writer:

            export_df.to_excel(
                writer,
                index=False,
                sheet_name="Dealer Leads"
            )

        excel_buffer.seek(0)

        st.download_button(
            "📊 Download Excel",
            data=excel_buffer,
            file_name=(
                f"car_dealer_leads_"
                f"{district}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True
        )

    except Exception as e:

        st.error(
            f"تعذر إنشاء ملف Excel: {e}"
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Egypt Car Dealer Lead Intelligence • "
    "Discovery + Platform Verification + Lead Scoring"
)
