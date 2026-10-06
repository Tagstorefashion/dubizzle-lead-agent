import streamlit as st
import pandas as pd
import requests
import urllib.parse
import re
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

# =========================================================
# APP CONFIG
# =========================================================

st.set_page_config(
    page_title="Egypt Car Dealer Lead Intelligence",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗 Egypt Car Dealer Lead Intelligence")
st.caption(
    "البحث عن معارض السيارات في مصر والتحقق من نشاطها على Dubizzle و ContactCars"
)

# =========================================================
# AREAS
# =========================================================

DISTRICT_OPTIONS = [
    "القاهرة - مدينة نصر",
    "القاهرة - التجمع الخامس والجديدة",
    "القاهرة - المعادي",
    "القاهرة - مصر الجديدة والنزهة",
    "القاهرة - شبرا ووسط البلد",
    "الجيزة - المهندسين والدقي",
    "الجيزة - فيصل والهرم",
    "الجيزة - 6 أكتوبر والشيخ زايد",
]

# =========================================================
# HTTP
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


# =========================================================
# HELPERS
# =========================================================

def clean_text(value):
    if not value:
        return ""

    value = BeautifulSoup(str(value), "html.parser").get_text(" ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_name(name):
    """
    توحيد اسم المعرض لمنع التكرار.
    """

    name = clean_text(name).lower()

    replacements = {
        "للسيارات": "",
        "للسيارات ": "",
        "سيارات": "",
        "كارز": "cars",
        "cars": "",
        "motors": "",
        "motor": "",
        "auto": "",
        "أوتو": "",
        "او تو": "",
        "العربية": "",
        "egypt": "",
        "مصر": "",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]+", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def is_similar_name(name1, name2, threshold=88):
    """
    مقارنة أسماء المعارض لمنع إدخال نفس المعرض أكثر من مرة.
    """

    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False

    return fuzz.token_set_ratio(n1, n2) >= threshold


def extract_phone(text):
    """
    استخراج أرقام المحمول المصرية فقط.
    """

    if not text:
        return ""

    patterns = [
        r"01[0125]\d{8}",
        r"\+20\s*1[0125]\s*\d{8}",
        r"0020\s*1[0125]\s*\d{8}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            phone = re.sub(r"\D", "", match.group())

            if phone.startswith("0020"):
                phone = phone[2:]

            if phone.startswith("20"):
                phone = phone[2:]

            if len(phone) == 11 and phone.startswith("01"):
                return phone

    return ""


def google_maps_link(name, area):
    query = urllib.parse.quote(f"{name} {area} Egypt")
    return f"https://www.google.com/maps/search/{query}"


def whatsapp_link(phone, message):
    if not phone:
        return ""

    if not phone.startswith("01") or len(phone) != 11:
        return ""

    encoded = urllib.parse.quote(message)

    return f"https://wa.me/2{phone}?text={encoded}"


# =========================================================
# SEARCH ENGINE
# =========================================================

def search_duckduckgo(query, max_results=20):

    url = (
        "https://html.duckduckgo.com/html/?q="
        + urllib.parse.quote(query)
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        results = []

        for result in soup.select(".result")[:max_results]:

            title_element = result.select_one(".result__title")

            link_element = result.select_one(".result__a")

            snippet_element = result.select_one(".result__snippet")

            if not title_element or not link_element:
                continue

            title = clean_text(title_element.get_text(" "))

            link = link_element.get("href", "")

            snippet = ""

            if snippet_element:
                snippet = clean_text(
                    snippet_element.get_text(" ")
                )

            results.append({
                "title": title,
                "link": link,
                "snippet": snippet
            })

        return results

    except Exception:
        return []


# =========================================================
# DEALER DISCOVERY
# =========================================================

def discover_dealers(selected_districts, max_results):

    dealers = []

    seen_names = []

    for district in selected_districts:

        parts = district.split(" - ", 1)

        city = parts[0]
        area = parts[1] if len(parts) > 1 else district

        queries = [
            f'"معرض سيارات" "{area}"',
            f'"معرض سيارات" "{area}" "{city}"',
            f'"معارض سيارات" "{area}"',
            f'"car dealer" "{area}" Egypt',
            f'"cars" "{area}" Egypt',
        ]

        for query in queries:

            results = search_duckduckgo(
                query,
                max_results=15
            )

            for result in results:

                title = result["title"]
                snippet = result["snippet"]
                link = result["link"]

                combined = f"{title} {snippet}".lower()

                dealer_keywords = [
                    "معرض",
                    "سيارات",
                    "cars",
                    "motors",
                    "auto",
                    "dealer",
                    "automotive",
                ]

                if not any(
                    keyword.lower() in combined
                    for keyword in dealer_keywords
                ):
                    continue

                # -------------------------------------------------
                # Prevent duplicates
                # -------------------------------------------------

                duplicate = False

                for old_name in seen_names:

                    if is_similar_name(
                        title,
                        old_name
                    ):
                        duplicate = True
                        break

                if duplicate:
                    continue

                seen_names.append(title)

                phone = extract_phone(
                    f"{title} {snippet}"
                )

                maps = google_maps_link(
                    title,
                    area
                )

                dealers.append({
                    "اسم المعرض": title,
                    "المدينة": city,
                    "المنطقة": area,
                    "الهاتف": phone,
                    "Google Maps": maps,
                    "مصدر الاكتشاف": link,
                    "Dubizzle": "سيتم التحقق",
                    "Dubizzle Ads": "سيتم التحقق",
                    "Dubizzle Ads / Month": "سيتم التحقق",
                    "ContactCars": "سيتم التحقق",
                    "ContactCars Ads": "سيتم التحقق",
                    "ContactCars Ads / Month": "سيتم التحقق",
                    "آخر نشاط": "سيتم التحقق",
                    "حالة التحقق": "يحتاج تحقق",
                })

                if len(dealers) >= max_results:
                    return dealers

    return dealers


# =========================================================
# PLATFORM VERIFICATION
# =========================================================

def verify_platform_presence(dealer_name, platform):

    if platform == "dubizzle":

        queries = [
            f'"{dealer_name}" site:dubizzle.com.eg',
            f'"{dealer_name}" dubizzle Egypt',
        ]

    elif platform == "contactcars":

        queries = [
            f'"{dealer_name}" site:contactcars.com',
            f'"{dealer_name}" ContactCars Egypt',
        ]

    else:
        return {
            "exists": False,
            "results": []
        }

    all_results = []

    for query in queries:

        results = search_duckduckgo(
            query,
            max_results=10
        )

        all_results.extend(results)

    # Remove duplicate URLs

    unique = {}

    for result in all_results:

        link = result.get("link", "")

        if link:
            unique[link] = result

    results = list(unique.values())

    if results:

        return {
            "exists": True,
            "results": results
        }

    return {
        "exists": False,
        "results": []
    }


# =========================================================
# MONTHLY ACTIVITY
# =========================================================

def estimate_monthly_activity(results):

    """
    لا نخترع رقم.

    لو لم نجد تواريخ فعلية للإعلانات:
    نرجع "غير متاح".

    لاحقاً سنستبدل هذا الجزء بجامع بيانات متخصص
    للـ listings والتواريخ.
    """

    if not results:
        return "غير متاح"

    return "يحتاج بيانات تواريخ الإعلانات"


# =========================================================
# LEAD SCORING
# =========================================================

def calculate_score(row):

    score = 0

    if row["الهاتف"]:
        score += 20

    if row["Dubizzle"] == "نعم":
        score += 30

    if row["ContactCars"] == "نعم":
        score += 25

    if row["Dubizzle Ads"] not in [
        "",
        "غير متاح",
        "سيتم التحقق"
    ]:
        score += 10

    if row["ContactCars Ads"] not in [
        "",
        "غير متاح",
        "سيتم التحقق"
    ]:
        score += 10

    if score > 100:
        score = 100

    return score


# =========================================================
# WHATSAPP
# =========================================================

def create_whatsapp_message(row):

    dealer = row["اسم المعرض"]

    message = (
        f"مساء الخير {dealer} 👋\n\n"
        "معاك فريق المبيعات، وحابين نتواصل مع حضرتكم "
        "بخصوص فرصة لزيادة ظهور مخزون السيارات بتاعكم "
        "والوصول لعملاء مهتمين بالشراء.\n\n"
        "لو مناسب لحضرتك ممكن نتواصل معاك في الوقت المناسب."
    )

    return message


# =========================================================
# MAIN PIPELINE
# =========================================================

def run_pipeline(selected_districts, max_results):

    dealers = discover_dealers(
        selected_districts,
        max_results
    )

    if not dealers:
        return pd.DataFrame()

    df = pd.DataFrame(dealers)

    for index, row in df.iterrows():

        dealer_name = row["اسم المعرض"]

        # -----------------------------------------------
        # Dubizzle
        # -----------------------------------------------

        dubizzle = verify_platform_presence(
            dealer_name,
            "dubizzle"
        )

        if dubizzle["exists"]:

            df.at[index, "Dubizzle"] = "نعم"

            df.at[index, "Dubizzle Ads"] = (
                "تم العثور على نتائج"
            )

            df.at[index, "Dubizzle Ads / Month"] = (
                estimate_monthly_activity(
                    dubizzle["results"]
                )
            )

        else:

            df.at[index, "Dubizzle"] = "غير متحقق"

            df.at[index, "Dubizzle Ads"] = "غير متاح"

            df.at[index, "Dubizzle Ads / Month"] = "غير متاح"

        # -----------------------------------------------
        # ContactCars
        # -----------------------------------------------

        contactcars = verify_platform_presence(
            dealer_name,
            "contactcars"
        )

        if contactcars["exists"]:

            df.at[index, "ContactCars"] = "نعم"

            df.at[index, "ContactCars Ads"] = (
                "تم العثور على نتائج"
            )

            df.at[index, "ContactCars Ads / Month"] = (
                estimate_monthly_activity(
                    contactcars["results"]
                )
            )

        else:

            df.at[index, "ContactCars"] = "غير متحقق"

            df.at[index, "ContactCars Ads"] = "غير متاح"

            df.at[index, "ContactCars Ads / Month"] = "غير متاح"

    # -----------------------------------------------
    # Score
    # -----------------------------------------------

    df["Lead Score"] = df.apply(
        calculate_score,
        axis=1
    )

    # -----------------------------------------------
    # WhatsApp
    # -----------------------------------------------

    df["رسالة WhatsApp"] = df.apply(
        create_whatsapp_message,
        axis=1
    )

    df["WhatsApp"] = df.apply(
        lambda row: whatsapp_link(
            row["الهاتف"],
            row["رسالة WhatsApp"]
        ),
        axis=1
    )

    return df


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("⚙️ إعدادات البحث")

    selected_districts = st.multiselect(
        "📍 المناطق",
        DISTRICT_OPTIONS,
        default=[
            "القاهرة - مصر الجديدة والنزهة"
        ]
    )

    max_results = st.slider(
        "🔎 عدد المعارض",
        min_value=5,
        max_value=100,
        value=20,
        step=5
    )

    st.divider()

    st.info(
        "البرنامج لا يفترض وجود بيانات غير متاحة. "
        "أي معلومة غير مؤكدة تظهر كـ غير متحقق."
    )


# =========================================================
# BUTTON
# =========================================================

if st.button(
    "🚀 ابدأ البحث والتحقق",
    type="primary",
    use_container_width=True
):

    if not selected_districts:

        st.warning(
            "اختر منطقة واحدة على الأقل."
        )

    else:

        with st.spinner(
            "🔎 جاري البحث عن المعارض والتحقق من المصادر..."
        ):

            df = run_pipeline(
                selected_districts,
                max_results
            )

        if df.empty:

            st.error(
                "لم يتم العثور على نتائج. "
                "جرب منطقة أخرى أو عدد نتائج أقل."
            )

        else:

            st.success(
                f"✅ تم العثور على {len(df)} معرض."
            )

            # -----------------------------------------
            # Dashboard
            # -----------------------------------------

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "المعارض",
                len(df)
            )

            col2.metric(
                "Dubizzle",
                int(
                    (df["Dubizzle"] == "نعم").sum()
                )
            )

            col3.metric(
                "ContactCars",
                int(
                    (df["ContactCars"] == "نعم").sum()
                )
            )

            col4.metric(
                "لديها هاتف",
                int(
                    (df["الهاتف"] != "").sum()
                )
            )

            st.divider()

            # -----------------------------------------
            # Table
            # -----------------------------------------

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            # -----------------------------------------
            # Excel
            # -----------------------------------------

            excel_file = "car_dealer_leads.xlsx"

            df.to_excel(
                excel_file,
                index=False
            )

            with open(
                excel_file,
                "rb"
            ) as file:

                st.download_button(
                    "📥 تحميل Excel",
                    data=file,
                    file_name=excel_file,
                    mime=(
                        "application/vnd."
                        "openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True
                )
