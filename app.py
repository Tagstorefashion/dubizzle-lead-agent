import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import quote, urljoin

from modules.dubizzle import get_dubizzle_status
from modules.contactcars import get_contactcars_status
from modules.deduplication import remove_duplicates


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Egypt Car Dealer Lead Intelligence",
    page_icon="🚗",
    layout="wide"
)


# =========================================================
# CONFIG
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

SEARCH_TIMEOUT = 10

DISTRICTS = [
    "مدينة نصر",
    "مصر الجديدة",
    "المعادي",
    "التجمع الخامس",
    "الهرم",
    "فيصل",
    "6 أكتوبر",
    "الشيخ زايد",
    "المهندسين",
    "الدقي",
    "وسط البلد",
    "العبور",
    "الشروق",
]


# =========================================================
# GENERAL HELPERS
# =========================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_name(name):
    name = clean_text(name).lower()

    replacements = [
        "cars",
        "car",
        "auto",
        "automotive",
        "motors",
        "motor",
        "showroom",
        "showrooms",
        "للسيارات",
        "للسيارات",
        "سيارات",
        "معرض",
        "معارض",
        "شركة",
        "شركه",
    ]

    for word in replacements:
        name = name.replace(word, " ")

    name = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]+", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def extract_phone(text):
    if not text:
        return ""

    text = str(text)

    patterns = [
        r"(?:\+20|0020)[\s\-()]?1[0125]\d[\s\-]?\d{3}[\s\-]?\d{4}",
        r"01[0125][\s\-]?\d{3}[\s\-]?\d{4}",
        r"\+20[\s\-]?(?:2|0?2)[\s\-]?\d{7,8}",
        r"0?2[\s\-]?\d{7,8}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            phone = match.group(0)
            phone = re.sub(r"[^\d+]", "", phone)

            if phone.startswith("0020"):
                phone = "+" + phone[2:]

            if phone.startswith("01"):
                phone = "+20" + phone[1:]

            return phone

    return ""


def extract_all_phones(text):
    if not text:
        return []

    phones = []

    patterns = [
        r"(?:\+20|0020)[\s\-()]?1[0125]\d[\s\-]?\d{3}[\s\-]?\d{4}",
        r"01[0125][\s\-]?\d{3}[\s\-]?\d{4}",
        r"\+20[\s\-]?(?:2|0?2)[\s\-]?\d{7,8}",
        r"0?2[\s\-]?\d{7,8}",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)

        for match in matches:
            phone = re.sub(r"[^\d+]", "", match)

            if phone.startswith("0020"):
                phone = "+" + phone[2:]

            if phone.startswith("01"):
                phone = "+20" + phone[1:]

            if phone not in phones:
                phones.append(phone)

    return phones


def google_maps_link(name, address=""):
    query = f"{name} {address} Egypt"
    return "https://www.google.com/maps/search/?api=1&query=" + quote(query)


def whatsapp_link(phone):
    if not phone:
        return ""

    phone = re.sub(r"\D", "", phone)

    if phone.startswith("0"):
        phone = "20" + phone[1:]

    if not phone.startswith("20"):
        phone = "20" + phone

    return f"https://wa.me/{phone}"


# =========================================================
# SEARCH ENGINES
# =========================================================

def search_duckduckgo(query, max_results=10):
    results = []

    try:
        url = "https://html.duckduckgo.com/html/"

        response = requests.get(
            url,
            params={"q": query},
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__a")
            snippet_el = result.select_one(".result__snippet")

            if not title_el:
                continue

            title = clean_text(title_el.get_text(" ", strip=True))
            link = title_el.get("href", "")
            snippet = clean_text(
                snippet_el.get_text(" ", strip=True)
                if snippet_el
                else ""
            )

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                })

    except Exception:
        pass

    return results


def search_bing(query, max_results=10):
    results = []

    try:
        url = "https://www.bing.com/search"

        response = requests.get(
            url,
            params={"q": query},
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        for result in soup.select("li.b_algo")[:max_results]:
            title_el = result.select_one("h2 a")
            snippet_el = result.select_one(".b_caption p")

            if not title_el:
                continue

            title = clean_text(title_el.get_text(" ", strip=True))
            link = title_el.get("href", "")
            snippet = clean_text(
                snippet_el.get_text(" ", strip=True)
                if snippet_el
                else ""
            )

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                })

    except Exception:
        pass

    return results


def search_web(query, max_results=10):
    results = search_duckduckgo(query, max_results)

    if results:
        return results

    return search_bing(query, max_results)


# =========================================================
# DIRECTORY DISCOVERY
# =========================================================

GENERIC_NAMES = {
    "more info",
    "see all branches",
    "map",
    "photos",
    "videos",
    "search",
    "home",
    "next",
    "previous",
    "read more",
}


CAR_KEYWORDS = [
    "car",
    "cars",
    "auto",
    "automotive",
    "motor",
    "motors",
    "vehicle",
    "vehicles",
    "سيارات",
    "سياره",
    "سيارات",
    "أوتو",
    "موتور",
    "للسيارات",
]


def is_car_name(name):
    name_lower = name.lower()

    for keyword in CAR_KEYWORDS:
        if keyword.lower() in name_lower:
            return True

    return True


def find_detail_links(soup, base_url):
    links = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))

        if not href:
            continue

        full_url = urljoin(base_url, href)

        if (
            "company.aspx" in full_url.lower()
            or "/company/" in full_url.lower()
            or "more-info" in full_url.lower()
        ):
            links.append({
                "text": text,
                "url": full_url,
            })

    return links


def parse_directory_page(url, district):
    dealers = []

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        detail_links = find_detail_links(soup, url)

        # -------------------------------------------------
        # 1. Try extracting actual company cards
        # -------------------------------------------------

        possible_cards = soup.select(
            ".company-listing, "
            ".listing, "
            ".result, "
            ".company, "
            ".business, "
            "article"
        )

        for card in possible_cards:
            text = clean_text(card.get_text(" ", strip=True))

            if not text:
                continue

            phone = extract_phone(text)

            links = card.find_all("a", href=True)

            company_name = ""

            detail_url = ""

            for a in links:
                anchor_text = clean_text(
                    a.get_text(" ", strip=True)
                )

                href = urljoin(url, a.get("href", ""))

                if not anchor_text:
                    continue

                if anchor_text.lower() in GENERIC_NAMES:
                    continue

                if len(anchor_text) < 3:
                    continue

                if len(anchor_text) > 100:
                    continue

                if (
                    "company.aspx" in href.lower()
                    or "/company/" in href.lower()
                ):
                    company_name = anchor_text
                    detail_url = href
                    break

            if not company_name:
                continue

            dealers.append({
                "name": company_name,
                "district": district,
                "address": text[:500],
                "phone": phone,
                "source": url,
                "detail_url": detail_url,
            })

        # -------------------------------------------------
        # 2. Fallback: parse headings
        # -------------------------------------------------

        headings = soup.find_all(
            ["h2", "h3", "h4"]
        )

        for heading in headings:
            name = clean_text(
                heading.get_text(" ", strip=True)
            )

            if not name:
                continue

            if name.lower() in GENERIC_NAMES:
                continue

            if len(name) < 3:
                continue

            if len(name) > 100:
                continue

            parent = heading.parent

            nearby_text = ""

            if parent:
                nearby_text = clean_text(
                    parent.get_text(" ", strip=True)
                )

            # Expand one level when necessary
            if len(nearby_text) < 50 and parent:
                grandparent = parent.parent

                if grandparent:
                    nearby_text = clean_text(
                        grandparent.get_text(" ", strip=True)
                    )

            phone = extract_phone(nearby_text)

            detail_url = ""

            for a in heading.find_all_next(
                "a",
                href=True,
                limit=5
            ):
                href = urljoin(
                    url,
                    a.get("href", "")
                )

                if (
                    "company.aspx" in href.lower()
                    or "/company/" in href.lower()
                ):
                    detail_url = href
                    break

            dealers.append({
                "name": name,
                "district": district,
                "address": nearby_text[:500],
                "phone": phone,
                "source": url,
                "detail_url": detail_url,
            })

    except Exception:
        return []

    return dealers


# =========================================================
# DETAIL PAGE ENRICHMENT
# =========================================================

def enrich_from_detail_page(dealer):
    detail_url = dealer.get("detail_url", "")

    if not detail_url:
        return dealer

    try:
        response = requests.get(
            detail_url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        if response.status_code != 200:
            return dealer

        soup = BeautifulSoup(response.text, "html.parser")

        page_text = clean_text(
            soup.get_text(" ", strip=True)
        )

        # -------------------------------------------------
        # Phone
        # -------------------------------------------------

        phones = extract_all_phones(page_text)

        if phones:
            dealer["phone"] = phones[0]

            if len(phones) > 1:
                dealer["phones"] = " | ".join(phones)

        # -------------------------------------------------
        # Email
        # -------------------------------------------------

        emails = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            page_text
        )

        if emails:
            dealer["email"] = emails[0]

        # -------------------------------------------------
        # Website / Facebook
        # -------------------------------------------------

        facebook = ""
        website = ""

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")

            if not href:
                continue

            lower = href.lower()

            if "facebook.com" in lower and not facebook:
                facebook = href

            elif (
                href.startswith("http")
                and "140online.com" not in lower
                and "yellowpages.com.eg" not in lower
                and not website
            ):
                website = href

        if facebook:
            dealer["facebook"] = facebook

        if website:
            dealer["website"] = website

        # -------------------------------------------------
        # Better address
        # -------------------------------------------------

        district_words = [
            "Nasr City",
            "Misr El Gedeida",
            "Heliopolis",
            "Maadi",
            "Cairo",
            "مدينة نصر",
            "مصر الجديدة",
            "المعادي",
            "القاهرة",
        ]

        address_candidates = []

        for line in soup.stripped_strings:
            line = clean_text(line)

            if len(line) < 15:
                continue

            if any(
                word.lower() in line.lower()
                for word in district_words
            ):
                address_candidates.append(line)

        if address_candidates:
            dealer["address"] = address_candidates[0]

    except Exception:
        pass

    return dealer


# =========================================================
# DIRECTORY URLS
# =========================================================

DIRECTORY_URLS = {
    "مدينة نصر": [
        "https://www.140online.com/Classes.aspx?"
        "Area=375&AreaName=Nasr+City&ClassId=140&Gov=2"
        "&GovName=Cairo&Lang=En",

        "https://www.140online.com/UsedCars.aspx",

        "https://yellowpages.com.eg/en/category/"
        "nasr-city-car-dealerships/3256",

        "https://yellowpages.com.eg/en/category/"
        "مدينة-نصر-سيارات-جديدة-وكلاء-حصريون/3256",
    ],

    "مصر الجديدة": [
        "https://yellowpages.com.eg/en/category/"
        "heliopolis-car-dealerships/3256",
    ],

    "المعادي": [
        "https://yellowpages.com.eg/en/category/"
        "maadi-car-dealerships/3256",
    ],
}


# =========================================================
# SEARCH FALLBACK
# =========================================================

def fallback_discovery(district, limit):
    dealers = []

    queries = [
        f"car showroom {district} Cairo Egypt",
        f"car dealer {district} Cairo Egypt",
        f"used cars showroom {district} Cairo",
        f"معارض سيارات {district}",
        f"معرض سيارات {district}",
    ]

    for query in queries:
        results = search_web(
            query,
            max_results=10
        )

        for result in results:
            title = clean_text(result.get("title", ""))
            snippet = clean_text(result.get("snippet", ""))
            url = result.get("url", "")

            combined = f"{title} {snippet}"

            if not any(
                word.lower() in combined.lower()
                for word in CAR_KEYWORDS
            ):
                continue

            phone = extract_phone(combined)

            dealers.append({
                "name": title,
                "district": district,
                "address": snippet,
                "phone": phone,
                "source": url,
                "detail_url": "",
            })

            if len(dealers) >= limit:
                return dealers

        time.sleep(0.3)

    return dealers


# =========================================================
# MAIN DISCOVERY
# =========================================================

def discover_dealers(district, limit=10):
    dealers = []

    urls = DIRECTORY_URLS.get(
        district,
        []
    )

    # -----------------------------------------------------
    # Primary: Egyptian directories
    # -----------------------------------------------------

    for url in urls:
        if len(dealers) >= limit * 2:
            break

        found = parse_directory_page(
            url,
            district
        )

        dealers.extend(found)

        time.sleep(0.3)

    # -----------------------------------------------------
    # Fallback search
    # -----------------------------------------------------

    if len(dealers) < 3:
        fallback = fallback_discovery(
            district,
            limit * 2
        )

        dealers.extend(fallback)

    # -----------------------------------------------------
    # Normalize / deduplicate
    # -----------------------------------------------------

    unique = {}

    for dealer in dealers:
        name = clean_text(
            dealer.get("name", "")
        )

        if not name:
            continue

        normalized = normalize_name(name)

        if len(normalized) < 2:
            continue

        if normalized not in unique:
            dealer["name"] = name
            unique[normalized] = dealer
        else:
            existing = unique[normalized]

            # Keep better phone
            if (
                not existing.get("phone")
                and dealer.get("phone")
            ):
                existing["phone"] = dealer["phone"]

            # Keep detail URL
            if (
                not existing.get("detail_url")
                and dealer.get("detail_url")
            ):
                existing["detail_url"] = dealer[
                    "detail_url"
                ]

    dealers = list(unique.values())

    # -----------------------------------------------------
    # Enrich details
    # -----------------------------------------------------

    enriched = []

    progress = st.progress(
        0,
        text="جاري جلب بيانات المعارض..."
    )

    total = min(
        len(dealers),
        limit
    )

    for index, dealer in enumerate(
        dealers[:limit]
    ):
        dealer = enrich_from_detail_page(
            dealer
        )

        enriched.append(dealer)

        progress.progress(
            (index + 1) / max(total, 1),
            text=(
                f"جاري تجهيز المعرض "
                f"{index + 1} من {total}"
            )
        )

        time.sleep(0.15)

    progress.empty()

    return enriched


# =========================================================
# FACEBOOK SEARCH
# =========================================================

def search_facebook(dealer_name, district):
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
            url = result.get("url", "")
            title = clean_text(
                result.get("title", "")
            )
            snippet = clean_text(
                result.get("snippet", "")
            )

            combined = (
                f"{title} {snippet} {url}"
            ).lower()

            if "facebook.com" in combined:
                return url

    return ""


# =========================================================
# PLATFORM VERIFICATION
# =========================================================

def verify_dealer(dealer):
    name = dealer.get("name", "")
    district = dealer.get("district", "")

    # -----------------------------------------------------
    # Dubizzle
    # -----------------------------------------------------

    try:
        dubizzle = get_dubizzle_status(
            name,
            district
        )
    except Exception:
        dubizzle = {
            "status": "غير متاح",
            "listing_count": 0,
            "url": "",
        }

    # -----------------------------------------------------
    # ContactCars
    # -----------------------------------------------------

    try:
        contactcars = get_contactcars_status(
            name,
            district
        )
    except Exception:
        contactcars = {
            "status": "غير متاح",
            "listing_count": 0,
            "url": "",
        }

    # -----------------------------------------------------
    # Facebook
    # -----------------------------------------------------

    facebook = dealer.get(
        "facebook",
        ""
    )

    if not facebook:
        facebook = search_facebook(
            name,
            district
        )

    dealer["facebook"] = facebook

    dealer["dubizzle_status"] = dubizzle.get(
        "status",
        "غير متاح"
    )

    dealer["dubizzle_results"] = dubizzle.get(
        "listing_count",
        0
    )

    dealer["dubizzle_url"] = dubizzle.get(
        "url",
        ""
    )

    dealer["contactcars_status"] = contactcars.get(
        "status",
        "غير متاح"
    )

    dealer["contactcars_results"] = contactcars.get(
        "listing_count",
        0
    )

    dealer["contactcars_url"] = contactcars.get(
        "url",
        ""
    )

    return dealer


# =========================================================
# SCORING
# =========================================================

def calculate_score(dealer):
    score = 0

    if dealer.get("phone"):
        score += 25

    if dealer.get("facebook"):
        score += 15

    if dealer.get("website"):
        score += 10

    if dealer.get("address"):
        score += 10

    if dealer.get("dubizzle_status") == "موجود":
        score += 20

    if dealer.get("contactcars_status") == "موجود":
        score += 20

    return min(score, 100)


def score_label(score):
    if score >= 80:
        return "🔥 قوي"

    if score >= 60:
        return "🟢 جيد"

    if score >= 40:
        return "🟡 متوسط"

    return "🔴 ضعيف"


# =========================================================
# WHATSAPP
# =========================================================

def create_whatsapp_message(dealer):
    name = dealer.get("name", "")

    return (
        f"أهلاً {name} 👋\n\n"
        "معاكم خدمة متخصصة في التسويق الرقمي "
        "لمعارض السيارات.\n\n"
        "بنساعد المعرض في زيادة الـ leads "
        "والعملاء المحتملين من خلال WhatsApp "
        "والمنصات الرقمية.\n\n"
        "حابين نبعث لحضرتك تفاصيل سريعة؟"
    )


# =========================================================
# PIPELINE
# =========================================================

def run_pipeline(district, limit):
    st.info(
        f"🔎 جاري البحث عن معارض حقيقية في {district}..."
    )

    dealers = discover_dealers(
        district,
        limit
    )

    if not dealers:
        return []

    st.success(
        f"تم العثور على {len(dealers)} معرض مبدئي."
    )

    # -----------------------------------------------------
    # Verification progress
    # -----------------------------------------------------

    verified = []

    progress = st.progress(
        0,
        text="جاري التحقق من المنصات..."
    )

    total = len(dealers)

    for index, dealer in enumerate(dealers):

        dealer = verify_dealer(
            dealer
        )

        dealer["score"] = calculate_score(
            dealer
        )

        dealer["score_label"] = score_label(
            dealer["score"]
        )

        dealer["maps_url"] = google_maps_link(
            dealer.get("name", ""),
            dealer.get("address", "")
        )

        dealer["whatsapp_url"] = whatsapp_link(
            dealer.get("phone", "")
        )

        dealer["whatsapp_message"] = (
            create_whatsapp_message(
                dealer
            )
        )

        verified.append(dealer)

        progress.progress(
            (index + 1) / max(total, 1),
            text=(
                f"التحقق من "
                f"{index + 1} من {total}"
            )
        )

    progress.empty()

    return verified


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("🚗 Lead Prospector")

district = st.sidebar.selectbox(
    "المنطقة",
    DISTRICTS
)

limit = st.sidebar.slider(
    "عدد النتائج",
    min_value=5,
    max_value=30,
    value=10,
    step=5
)

run_search = st.sidebar.button(
    "🔎 ابدأ البحث",
    use_container_width=True
)

st.sidebar.markdown("---")

st.sidebar.caption(
    "المصادر الأساسية:\n"
    "• 140online\n"
    "• Egypt Yellow Pages\n"
    "• Dubizzle\n"
    "• ContactCars\n"
    "• Facebook"
)


# =========================================================
# HEADER
# =========================================================

st.title(
    "🚗 Egypt Car Dealer Lead Intelligence"
)

st.write(
    "اكتشاف معارض السيارات المصرية "
    "ثم إثراء بياناتها والتحقق من وجودها "
    "على المنصات المختلفة."
)

st.warning(
    "⚠️ ملاحظة: أرقام Results الخاصة بـ Dubizzle "
    "وContactCars في النسخة الحالية هي نتائج بحث "
    "وليست بالضرورة العدد الحقيقي للإعلانات. "
    "سنفصل حساب الـ listing count الحقيقي في خطوة لاحقة."
)


# =========================================================
# RUN
# =========================================================

if run_search:

    with st.spinner(
        "جاري تشغيل البحث..."
    ):
        results = run_pipeline(
            district,
            limit
        )

    if not results:
        st.error(
            "لم يتم العثور على معارض موثوقة. "
            "جرب منطقة أخرى."
        )

    else:

        st.session_state[
            "dealer_results"
        ] = results


# =========================================================
# DISPLAY
# =========================================================

if "dealer_results" in st.session_state:

    results = st.session_state[
        "dealer_results"
    ]

    st.subheader(
        f"📊 النتائج — {len(results)} معرض"
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    phones_count = sum(
        bool(x.get("phone"))
        for x in results
    )

    facebook_count = sum(
        bool(x.get("facebook"))
        for x in results
    )

    dubizzle_count = sum(
        x.get("dubizzle_status") == "موجود"
        for x in results
    )

    contactcars_count = sum(
        x.get("contactcars_status") == "موجود"
        for x in results
    )

    col1.metric(
        "📞 أرقام",
        phones_count
    )

    col2.metric(
        "📘 Facebook",
        facebook_count
    )

    col3.metric(
        "🟣 Dubizzle",
        dubizzle_count
    )

    col4.metric(
        "🔵 ContactCars",
        contactcars_count
    )

    st.markdown("---")

    # -----------------------------------------------------
    # Table
    # -----------------------------------------------------

    table_data = []

    for dealer in results:

        table_data.append({
            "المعرض": dealer.get(
                "name",
                ""
            ),

            "المنطقة": dealer.get(
                "district",
                ""
            ),

            "الموبايل": dealer.get(
                "phone",
                ""
            ),

            "Facebook": (
                "موجود"
                if dealer.get("facebook")
                else "غير موجود"
            ),

            "Dubizzle": dealer.get(
                "dubizzle_status",
                "غير متاح"
            ),

            "Dubizzle Results": dealer.get(
                "dubizzle_results",
                0
            ),

            "ContactCars": dealer.get(
                "contactcars_status",
                "غير متاح"
            ),

            "ContactCars Results": dealer.get(
                "contactcars_results",
                0
            ),

            "Score": dealer.get(
                "score",
                0
            ),

            "التقييم": dealer.get(
                "score_label",
                ""
            ),
        })

    df = pd.DataFrame(
        table_data
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    # -----------------------------------------------------
    # Details
    # -----------------------------------------------------

    st.markdown("---")

    st.subheader(
        "🔍 تفاصيل المعارض"
    )

    for index, dealer in enumerate(results):

        name = dealer.get(
            "name",
            "معرض"
        )

        score = dealer.get(
            "score",
            0
        )

        with st.expander(
            f"{score_label(score)} — {name}"
        ):

            col1, col2 = st.columns(2)

            with col1:

                st.write(
                    "**📍 المنطقة:**",
                    dealer.get(
                        "district",
                        ""
                    )
                )

                st.write(
                    "**🏠 العنوان:**",
                    dealer.get(
                        "address",
                        ""
                    )
                )

                st.write(
                    "**📞 الموبايل:**",
                    dealer.get(
                        "phone",
                        "غير متوفر"
                    )
                )

                if dealer.get("phones"):
                    st.write(
                        "**📞 أرقام إضافية:**",
                        dealer.get("phones")
                    )

                st.write(
                    "**📧 Email:**",
                    dealer.get(
                        "email",
                        "غير متوفر"
                    )
                )

            with col2:

                st.write(
                    "**📘 Facebook:**",
                    dealer.get(
                        "facebook",
                        "غير متوفر"
                    )
                )

                st.write(
                    "**🌐 Website:**",
                    dealer.get(
                        "website",
                        "غير متوفر"
                    )
                )

                st.write(
                    "**🟣 Dubizzle:**",
                    dealer.get(
                        "dubizzle_status",
                        "غير متاح"
                    )
                )

                st.write(
                    "**🔵 ContactCars:**",
                    dealer.get(
                        "contactcars_status",
                        "غير متاح"
                    )
                )

                st.write(
                    "**⭐ Score:**",
                    f"{score}/100"
                )

            st.markdown("---")

            links = []

            if dealer.get("whatsapp_url"):
                links.append(
                    f"[💬 WhatsApp]("
                    f"{dealer['whatsapp_url']})"
                )

            if dealer.get("facebook"):
                links.append(
                    f"[📘 Facebook]("
                    f"{dealer['facebook']})"
                )

            if dealer.get("maps_url"):
                links.append(
                    f"[📍 Google Maps]("
                    f"{dealer['maps_url']})"
                )

            if dealer.get("dubizzle_url"):
                links.append(
                    f"[🟣 Dubizzle]("
                    f"{dealer['dubizzle_url']})"
                )

            if dealer.get("contactcars_url"):
                links.append(
                    f"[🔵 ContactCars]("
                    f"{dealer['contactcars_url']})"
                )

            if links:
                st.markdown(
                    " | ".join(links)
                )

            st.markdown(
                "**💬 رسالة WhatsApp جاهزة:**"
            )

            st.code(
                dealer.get(
                    "whatsapp_message",
                    ""
                ),
                language=None
            )


    # -----------------------------------------------------
    # EXPORT
    # -----------------------------------------------------

    st.markdown("---")

    st.subheader(
        "📥 تصدير البيانات"
    )

    export_rows = []

    for dealer in results:

        export_rows.append({
            "Dealer Name": dealer.get(
                "name",
                ""
            ),

            "District": dealer.get(
                "district",
                ""
            ),

            "Address": dealer.get(
                "address",
                ""
            ),

            "Phone": dealer.get(
                "phone",
                ""
            ),

            "Additional Phones": dealer.get(
                "phones",
                ""
            ),

            "Email": dealer.get(
                "email",
                ""
            ),

            "Facebook": dealer.get(
                "facebook",
                ""
            ),

            "Website": dealer.get(
                "website",
                ""
            ),

            "Dubizzle Status": dealer.get(
                "dubizzle_status",
                ""
            ),

            "Dubizzle Search Results": dealer.get(
                "dubizzle_results",
                0
            ),

            "ContactCars Status": dealer.get(
                "contactcars_status",
                ""
            ),

            "ContactCars Search Results": dealer.get(
                "contactcars_results",
                0
            ),

            "Score": dealer.get(
                "score",
                0
            ),

            "Google Maps": dealer.get(
                "maps_url",
                ""
            ),

            "WhatsApp": dealer.get(
                "whatsapp_url",
                ""
            ),

            "WhatsApp Message": dealer.get(
                "whatsapp_message",
                ""
            ),

            "Source": dealer.get(
                "source",
                ""
            ),

            "Detail Page": dealer.get(
                "detail_url",
                ""
            ),
        })

    export_df = pd.DataFrame(
        export_rows
    )

    csv_data = export_df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "📄 تحميل CSV",
        data=csv_data,
        file_name="egypt_car_dealers.csv",
        mime="text/csv",
        use_container_width=True
    )

    # -----------------------------------------------------
    # Excel
    # -----------------------------------------------------

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
                sheet_name="Dealers"
            )

        st.download_button(
            "📊 تحميل Excel",
            data=excel_buffer.getvalue(),
            file_name="egypt_car_dealers.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True
        )

    except Exception as e:

        st.warning(
            f"تعذر إنشاء ملف Excel: {e}"
        )
