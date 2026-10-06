import io
import re
import time
from urllib.parse import quote, urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

from modules.dubizzle import get_dubizzle_status
from modules.contactcars import get_contactcars_status


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
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

TIMEOUT = 10

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

DIRECTORIES = {
    "مدينة نصر": [
        "https://www.140online.com/Classes.aspx?"
        "Area=375&AreaName=Nasr+City&ClassId=140"
        "&Gov=2&GovName=Cairo&Lang=En",
        "https://yellowpages.com.eg/en/category/"
        "nasr-city-car-dealerships/3256",
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
# HELPERS
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

    words = [
        "cars",
        "car",
        "auto",
        "automotive",
        "motors",
        "motor",
        "showroom",
        "showrooms",
        "سيارات",
        "سياره",
        "معرض",
        "معارض",
        "شركة",
        "شركه",
        "للسيارات",
    ]

    for word in words:
        name = name.replace(word, " ")

    name = re.sub(
        r"[^a-zA-Z0-9\u0600-\u06FF]+",
        " ",
        name,
    )

    name = re.sub(r"\s+", " ", name)

    return name.strip()


def extract_phones(text):
    if not text:
        return []

    patterns = [
        r"(?:\+20|0020)[\s\-()]?1[0125]\d[\s\-]?\d{3}[\s\-]?\d{4}",
        r"01[0125][\s\-]?\d{3}[\s\-]?\d{4}",
        r"0?2[\s\-]?\d{7,8}",
    ]

    phones = []

    for pattern in patterns:
        for match in re.findall(pattern, text):
            phone = re.sub(r"[^\d+]", "", match)

            if phone.startswith("0020"):
                phone = "+" + phone[2:]

            if phone.startswith("01"):
                phone = "+20" + phone[1:]

            if phone not in phones:
                phones.append(phone)

    return phones


def extract_phone(text):
    phones = extract_phones(text)

    if phones:
        return phones[0]

    return ""


def whatsapp_url(phone):
    if not phone:
        return ""

    phone = re.sub(r"\D", "", phone)

    if phone.startswith("0"):
        phone = "20" + phone[1:]

    if not phone.startswith("20"):
        phone = "20" + phone

    return "https://wa.me/" + phone


def maps_url(name, address):
    query = quote(
        f"{name} {address} Egypt"
    )

    return (
        "https://www.google.com/maps/search/"
        "?api=1&query=" + query
    )


# =========================================================
# WEB SEARCH
# =========================================================

def duckduckgo_search(query, limit=10):
    results = []

    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for item in soup.select(".result")[:limit]:
            title_el = item.select_one(".result__a")
            snippet_el = item.select_one(
                ".result__snippet"
            )

            if not title_el:
                continue

            results.append(
                {
                    "title": clean_text(
                        title_el.get_text(
                            " ",
                            strip=True,
                        )
                    ),
                    "url": title_el.get(
                        "href",
                        "",
                    ),
                    "snippet": clean_text(
                        snippet_el.get_text(
                            " ",
                            strip=True,
                        )
                        if snippet_el
                        else ""
                    ),
                }
            )

    except Exception:
        return []

    return results


def bing_search(query, limit=10):
    results = []

    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for item in soup.select("li.b_algo")[:limit]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(
                ".b_caption p"
            )

            if not title_el:
                continue

            results.append(
                {
                    "title": clean_text(
                        title_el.get_text(
                            " ",
                            strip=True,
                        )
                    ),
                    "url": title_el.get(
                        "href",
                        "",
                    ),
                    "snippet": clean_text(
                        snippet_el.get_text(
                            " ",
                            strip=True,
                        )
                        if snippet_el
                        else ""
                    ),
                }
            )

    except Exception:
        return []

    return results


def web_search(query, limit=10):
    results = duckduckgo_search(
        query,
        limit,
    )

    if results:
        return results

    return bing_search(
        query,
        limit,
    )


# =========================================================
# DIRECTORY PARSER
# =========================================================

BAD_NAMES = {
    "more info",
    "read more",
    "see all",
    "map",
    "photos",
    "videos",
    "search",
    "home",
    "next",
    "previous",
}


def get_card_text(element):
    if not element:
        return ""

    return clean_text(
        element.get_text(
            " ",
            strip=True,
        )
    )


def find_detail_url(element, base_url):
    if not element:
        return ""

    for link in element.find_all(
        "a",
        href=True,
    ):
        href = urljoin(
            base_url,
            link.get("href", ""),
        )

        low = href.lower()

        if (
            "company.aspx" in low
            or "/company/" in low
        ):
            return href

    return ""


def parse_directory(url, district):
    dealers = []

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        # First try common business/listing blocks.
        selectors = [
            ".company-listing",
            ".listing",
            ".company",
            ".business",
            ".result",
            "article",
        ]

        cards = []

        for selector in selectors:
            found = soup.select(selector)

            if found:
                cards.extend(found)

        for card in cards:
            text = get_card_text(card)

            if len(text) < 10:
                continue

            links = card.find_all(
                "a",
                href=True,
            )

            name = ""
            detail = ""

            for link in links:
                link_text = clean_text(
                    link.get_text(
                        " ",
                        strip=True,
                    )
                )

                href = urljoin(
                    url,
                    link.get("href", ""),
                )

                if not link_text:
                    continue

                if link_text.lower() in BAD_NAMES:
                    continue

                if len(link_text) < 3:
                    continue

                if len(link_text) > 100:
                    continue

                if (
                    "company.aspx" in href.lower()
                    or "/company/" in href.lower()
                ):
                    name = link_text
                    detail = href
                    break

            if not name:
                continue

            phones = extract_phones(text)

            dealers.append(
                {
                    "name": name,
                    "district": district,
                    "address": text[:600],
                    "phone": (
                        phones[0]
                        if phones
                        else ""
                    ),
                    "phones": (
                        " | ".join(phones)
                        if phones
                        else ""
                    ),
                    "detail_url": detail,
                    "source": url,
                }
            )

        # Fallback: headings
        if len(dealers) < 3:
            for heading in soup.find_all(
                ["h2", "h3", "h4"]
            ):
                name = clean_text(
                    heading.get_text(
                        " ",
                        strip=True,
                    )
                )

                if not name:
                    continue

                if name.lower() in BAD_NAMES:
                    continue

                if len(name) < 3:
                    continue

                if len(name) > 100:
                    continue

                parent = heading.parent

                text = get_card_text(
                    parent
                )

                if len(text) < 20:
                    grand = (
                        parent.parent
                        if parent
                        else None
                    )

                    text = get_card_text(
                        grand
                    )

                phones = extract_phones(text)

                detail = find_detail_url(
                    parent,
                    url,
                )

                dealers.append(
                    {
                        "name": name,
                        "district": district,
                        "address": text[:600],
                        "phone": (
                            phones[0]
                            if phones
                            else ""
                        ),
                        "phones": (
                            " | ".join(phones)
                            if phones
                            else ""
                        ),
                        "detail_url": detail,
                        "source": url,
                    }
                )

    except Exception:
        return []

    return dealers


# =========================================================
# DETAIL PAGE
# =========================================================

def enrich_dealer(dealer):
    url = dealer.get(
        "detail_url",
        "",
    )

    if not url:
        return dealer

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return dealer

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        text = clean_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        phones = extract_phones(text)

        if phones:
            dealer["phone"] = phones[0]
            dealer["phones"] = (
                " | ".join(phones)
            )

        emails = re.findall(
            r"[A-Za-z0-9._%+-]+"
            r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            text,
        )

        if emails:
            dealer["email"] = emails[0]

        facebook = ""
        website = ""

        for link in soup.find_all(
            "a",
            href=True,
        ):
            href = link.get(
                "href",
                "",
            )

            low = href.lower()

            if (
                "facebook.com" in low
                and not facebook
            ):
                facebook = href

            elif (
                href.startswith("http")
                and "140online.com" not in low
                and "yellowpages.com.eg" not in low
                and not website
            ):
                website = href

        if facebook:
            dealer["facebook"] = facebook

        if website:
            dealer["website"] = website

    except Exception:
        pass

    return dealer


# =========================================================
# FALLBACK DISCOVERY
# =========================================================

def fallback_discovery(
    district,
    limit,
):
    dealers = []

    queries = [
        f"car dealer {district} Cairo Egypt",
        f"car showroom {district} Cairo Egypt",
        f"معرض سيارات {district}",
    ]

    for query in queries:
        results = web_search(
            query,
            10,
        )

        for result in results:
            title = clean_text(
                result.get(
                    "title",
                    "",
                )
            )

            snippet = clean_text(
                result.get(
                    "snippet",
                    "",
                )
            )

            url = result.get(
                "url",
                "",
            )

            if not title:
                continue

            combined = (
                title + " " + snippet
            ).lower()

            car_words = [
                "car",
                "cars",
                "auto",
                "motor",
                "motors",
                "سيارات",
                "سيارة",
                "معرض",
            ]

            if not any(
                word in combined
                for word in car_words
            ):
                continue

            phones = extract_phones(
                combined
            )

            dealers.append(
                {
                    "name": title,
                    "district": district,
                    "address": snippet,
                    "phone": (
                        phones[0]
                        if phones
                        else ""
                    ),
                    "phones": (
                        " | ".join(phones)
                        if phones
                        else ""
                    ),
                    "detail_url": "",
                    "source": url,
                }
            )

            if len(dealers) >= limit:
                return dealers

    return dealers


# =========================================================
# DISCOVERY
# =========================================================

def discover_dealers(
    district,
    limit,
):
    all_dealers = []

    urls = DIRECTORIES.get(
        district,
        [],
    )

    for url in urls:
        found = parse_directory(
            url,
            district,
        )

        all_dealers.extend(
            found
        )

        if len(all_dealers) >= limit * 2:
            break

        time.sleep(0.3)

    if len(all_dealers) < 3:
        fallback = fallback_discovery(
            district,
            limit * 2,
        )

        all_dealers.extend(
            fallback
        )

    # Deduplicate
    unique = {}

    for dealer in all_dealers:
        name = clean_text(
            dealer.get(
                "name",
                "",
            )
        )

        if not name:
            continue

        key = normalize_name(
            name
        )

        if not key:
            continue

        if key not in unique:
            dealer["name"] = name
            unique[key] = dealer

        else:
            old = unique[key]

            if (
                not old.get("phone")
                and dealer.get("phone")
            ):
                old["phone"] = dealer[
                    "phone"
                ]

            if (
                not old.get("detail_url")
                and dealer.get(
                    "detail_url"
                )
            ):
                old["detail_url"] = dealer[
                    "detail_url"
                ]

    dealers = list(
        unique.values()
    )

    dealers = dealers[:limit]

    # Enrichment
    if dealers:
        progress = st.progress(
            0,
            text="جاري تجهيز بيانات المعارض...",
        )

        for index, dealer in enumerate(
            dealers
        ):
            dealers[index] = enrich_dealer(
                dealer
            )

            progress.progress(
                (index + 1) / len(dealers),
                text=(
                    f"المعرض {index + 1} "
                    f"من {len(dealers)}"
                ),
            )

        progress.empty()

    return dealers


# =========================================================
# FACEBOOK
# =========================================================

def find_facebook(
    dealer_name,
    district,
):
    queries = [
        f'"{dealer_name}" Facebook Egypt',
        f'"{dealer_name}" "{district}" Facebook',
    ]

    for query in queries:
        results = web_search(
            query,
            5,
        )

        for result in results:
            url = result.get(
                "url",
                "",
            )

            title = clean_text(
                result.get(
                    "title",
                    "",
                )
            )

            snippet = clean_text(
                result.get(
                    "snippet",
                    "",
                )
            )

            combined = (
                url
                + " "
                + title
                + " "
                + snippet
            ).lower()

            if "facebook.com" in combined:
                return url

    return ""


# =========================================================
# VERIFY
# =========================================================

def verify_dealer(dealer):
    name = dealer.get(
        "name",
        "",
    )

    district = dealer.get(
        "district",
        "",
    )

    # Facebook
    if not dealer.get("facebook"):
        dealer["facebook"] = find_facebook(
            name,
            district,
        )

    # Dubizzle
    try:
        dubizzle = get_dubizzle_status(
            name,
            district,
        )
    except Exception:
        dubizzle = {}

    # ContactCars
    try:
        contactcars = get_contactcars_status(
            name,
            district,
        )
    except Exception:
        contactcars = {}

    dealer["dubizzle_status"] = dubizzle.get(
        "status",
        "غير متاح",
    )

    dealer["dubizzle_results"] = dubizzle.get(
        "listing_count",
        0,
    )

    dealer["dubizzle_url"] = dubizzle.get(
        "url",
        "",
    )

    dealer["contactcars_status"] = (
        contactcars.get(
            "status",
            "غير متاح",
        )
    )

    dealer["contactcars_results"] = (
        contactcars.get(
            "listing_count",
            0,
        )
    )

    dealer["contactcars_url"] = (
        contactcars.get(
            "url",
            "",
        )
    )

    return dealer


# =========================================================
# SCORE
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

    if dealer.get(
        "dubizzle_status"
    ) == "موجود":
        score += 20

    if dealer.get(
        "contactcars_status"
    ) == "موجود":
        score += 20

    return min(
        score,
        100,
    )


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

def whatsapp_message(dealer):
    name = dealer.get(
        "name",
        "حضرتك",
    )

    return (
        f"أهلاً {name} 👋\n\n"
        "معاكم خدمة متخصصة في التسويق "
        "لمعارض السيارات.\n\n"
        "بنساعد المعارض في زيادة العملاء "
        "والـ leads من خلال التسويق الرقمي "
        "وWhatsApp.\n\n"
        "حابين نبعث لحضرتك تفاصيل سريعة؟"
    )


# =========================================================
# PIPELINE
# =========================================================

def run_pipeline(
    district,
    limit,
):
    st.info(
        f"🔎 البحث في {district}..."
    )

    dealers = discover_dealers(
        district,
        limit,
    )

    if not dealers:
        return []

    st.success(
        f"تم العثور على {len(dealers)} معرض."
    )

    progress = st.progress(
        0,
        text="جاري التحقق من البيانات...",
    )

    verified = []

    for index, dealer in enumerate(
        dealers
    ):
        dealer = verify_dealer(
            dealer
        )

        dealer["score"] = calculate_score(
            dealer
        )

        dealer["score_label"] = score_label(
            dealer["score"]
        )

        dealer["maps_url"] = maps_url(
            dealer.get(
                "name",
                "",
            ),
            dealer.get(
                "address",
                "",
            ),
        )

        dealer["whatsapp_url"] = (
            whatsapp_url(
                dealer.get(
                    "phone",
                    "",
                )
            )
        )

        dealer["whatsapp_message"] = (
            whatsapp_message(
                dealer
            )
        )

        verified.append(
            dealer
        )

        progress.progress(
            (index + 1) / len(dealers),
            text=(
                f"التحقق {index + 1} "
                f"من {len(dealers)}"
            ),
        )

    progress.empty()

    return verified


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title(
    "🚗 Lead Prospector"
)

district = st.sidebar.selectbox(
    "اختر المنطقة",
    DISTRICTS,
)

limit = st.sidebar.slider(
    "عدد النتائج",
    5,
    30,
    10,
    5,
)

start = st.sidebar.button(
    "🔎 ابدأ البحث",
    use_container_width=True,
)


# =========================================================
# HEADER
# =========================================================

st.title(
    "🚗 Egypt Car Dealer Lead Intelligence"
)

st.write(
    "اكتشاف معارض السيارات في مصر "
    "وتجميع بيانات التواصل والتحقق من "
    "وجودها على المنصات المختلفة."
)

st.warning(
    "تنبيه: Dubizzle Results وContactCars "
    "حاليًا هي نتائج بحث وليست عدد الإعلانات "
    "الحقيقي. سنطور حساب الـ listings الحقيقي "
    "بعد التأكد أن مرحلة اكتشاف المعارض تعمل."
)


# =========================================================
# SEARCH
# =========================================================

if start:
    results = run_pipeline(
        district,
        limit,
    )

    st.session_state[
        "results"
    ] = results


# =========================================================
# RESULTS
# =========================================================

if "results" in st.session_state:

    results = st.session_state[
        "results"
    ]

    if not results:
        st.error(
            "لم يتم العثور على معارض. "
            "جرب منطقة أخرى."
        )

    else:

        st.subheader(
            f"📊 النتائج: {len(results)}"
        )

        phone_count = sum(
            bool(x.get("phone"))
            for x in results
        )

        facebook_count = sum(
            bool(x.get("facebook"))
            for x in results
        )

        dubizzle_count = sum(
            x.get(
                "dubizzle_status"
            ) == "موجود"
            for x in results
        )

        contactcars_count = sum(
            x.get(
                "contactcars_status"
            ) == "موجود"
            for x in results
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "📞 أرقام",
            phone_count,
        )

        c2.metric(
            "📘 Facebook",
            facebook_count,
        )

        c3.metric(
            "🟣 Dubizzle",
            dubizzle_count,
        )

        c4.metric(
            "🔵 ContactCars",
            contactcars_count,
        )

        st.markdown("---")

        # Table
        rows = []

        for dealer in results:
            rows.append(
                {
                    "المعرض": dealer.get(
                        "name",
                        "",
                    ),
                    "المنطقة": dealer.get(
                        "district",
                        "",
                    ),
                    "الموبايل": dealer.get(
                        "phone",
                        "",
                    ),
                    "Facebook": (
                        "موجود"
                        if dealer.get(
                            "facebook"
                        )
                        else "غير موجود"
                    ),
                    "Dubizzle": dealer.get(
                        "dubizzle_status",
                        "غير متاح",
                    ),
                    "Dubizzle Results": dealer.get(
                        "dubizzle_results",
                        0,
                    ),
                    "ContactCars": dealer.get(
                        "contactcars_status",
                        "غير متاح",
                    ),
                    "ContactCars Results": dealer.get(
                        "contactcars_results",
                        0,
                    ),
                    "Score": dealer.get(
                        "score",
                        0,
                    ),
                }
            )

        df = pd.DataFrame(rows)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")

        st.subheader(
            "🔍 تفاصيل المعارض"
        )

        for dealer in results:

            name = dealer.get(
                "name",
                "معرض",
            )

            score = dealer.get(
                "score",
                0,
            )

            with st.expander(
                f"{score_label(score)} — {name}"
            ):

                left, right = st.columns(2)

                with left:
                    st.write(
                        "**📍 المنطقة:**",
                        dealer.get(
                            "district",
                            "",
                        ),
                    )

                    st.write(
                        "**🏠 العنوان:**",
                        dealer.get(
                            "address",
                            "",
                        ),
                    )

                    st.write(
                        "**📞 الموبايل:**",
                        dealer.get(
                            "phone",
                            "غير متوفر",
                        ),
                    )

                    st.write(
                        "**📞 أرقام إضافية:**",
                        dealer.get(
                            "phones",
                            "",
                        ),
                    )

                    st.write(
                        "**📧 Email:**",
                        dealer.get(
                            "email",
                            "غير متوفر",
                        ),
                    )

                with right:
                    facebook = dealer.get(
                        "facebook",
                        "",
                    )

                    website = dealer.get(
                        "website",
                        "",
                    )

                    st.write(
                        "**📘 Facebook:**",
                        facebook
                        if facebook
                        else "غير متوفر",
                    )

                    st.write(
                        "**🌐 Website:**",
                        website
                        if website
                        else "غير متوفر",
                    )

                    st.write(
                        "**🟣 Dubizzle:**",
                        dealer.get(
                            "dubizzle_status",
                            "غير متاح",
                        ),
                    )

                    st.write(
                        "**🔵 ContactCars:**",
                        dealer.get(
                            "contactcars_status",
                            "غير متاح",
                        ),
                    )

                    st.write(
                        "**⭐ Score:**",
                        f"{score}/100",
                    )

                st.markdown("---")

                links = []

                if dealer.get(
                    "whatsapp_url"
                ):
                    links.append(
                        "[💬 WhatsApp]("
                        + dealer[
                            "whatsapp_url"
                        ]
                        + ")"
                    )

                if facebook:
                    links.append(
                        "[📘 Facebook]("
                        + facebook
                        + ")"
                    )

                links.append(
                    "[📍 Google Maps]("
                    + dealer[
                        "maps_url"
                    ]
                    + ")"
                )

                if dealer.get(
                    "dubizzle_url"
                ):
                    links.append(
                        "[🟣 Dubizzle]("
                        + dealer[
                            "dubizzle_url"
                        ]
                        + ")"
                    )

                if dealer.get(
                    "contactcars_url"
                ):
                    links.append(
                        "[🔵 ContactCars]("
                        + dealer[
                            "contactcars_url"
                        ]
                        + ")"
                    )

                st.markdown(
                    " | ".join(links)
                )

                st.write(
                    "**💬 رسالة WhatsApp:**"
                )

                st.code(
                    dealer.get(
                        "whatsapp_message",
                        "",
                    )
                )

        # =================================================
        # EXPORT
        # =================================================

        st.markdown("---")

        st.subheader(
            "📥 تصدير النتائج"
        )

        export_rows = []

        for dealer in results:
            export_rows.append(
                {
                    "Dealer Name": dealer.get(
                        "name",
                        "",
                    ),
                    "District": dealer.get(
                        "district",
                        "",
                    ),
                    "Address": dealer.get(
                        "address",
                        "",
                    ),
                    "Phone": dealer.get(
                        "phone",
                        "",
                    ),
                    "Additional Phones": dealer.get(
                        "phones",
                        "",
                    ),
                    "Email": dealer.get(
                        "email",
                        "",
                    ),
                    "Facebook": dealer.get(
                        "facebook",
                        "",
                    ),
                    "Website": dealer.get(
                        "website",
                        "",
                    ),
                    "Dubizzle": dealer.get(
                        "dubizzle_status",
                        "",
                    ),
                    "Dubizzle Results": dealer.get(
                        "dubizzle_results",
                        0,
                    ),
                    "ContactCars": dealer.get(
                        "contactcars_status",
                        "",
                    ),
                    "ContactCars Results": dealer.get(
                        "contactcars_results",
                        0,
                    ),
                    "Score": dealer.get(
                        "score",
                        0,
                    ),
                    "Google Maps": dealer.get(
                        "maps_url",
                        "",
                    ),
                    "WhatsApp": dealer.get(
                        "whatsapp_url",
                        "",
                    ),
                    "WhatsApp Message": dealer.get(
                        "whatsapp_message",
                        "",
                    ),
                    "Source": dealer.get(
                        "source",
                        "",
                    ),
                }
            )

        export_df = pd.DataFrame(
            export_rows
        )

        csv_data = export_df.to_csv(
            index=False
        ).encode(
            "utf-8-sig"
        )

        st.download_button(
            "📄 تحميل CSV",
            data=csv_data,
            file_name="egypt_car_dealers.csv",
            mime="text/csv",
            use_container_width=True,
        )

        try:
            excel_buffer = io.BytesIO()

            with pd.ExcelWriter(
                excel_buffer,
                engine="openpyxl",
            ) as writer:

                export_df.to_excel(
                    writer,
                    index=False,
                    sheet_name="Dealers",
                )

            st.download_button(
                "📊 تحميل Excel",
                data=excel_buffer.getvalue(),
                file_name="egypt_car_dealers.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

        except Exception as error:
            st.warning(
                "تعذر إنشاء ملف Excel: "
                + str(error)
            )
