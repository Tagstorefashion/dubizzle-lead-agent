import re
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import quote

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}
SEARCH_TIMEOUT = 10

def clean_text(text):
    return " ".join(text.split()) if text else ""

def normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    return clean_text(name)

def extract_mobile_phone(text):
    """استخراج رقم محمول مصري (01x) مفضل على الأرضي"""
    if not text:
        return "غير متاح"
    clean_text_str = text.replace(" ", "").replace("-", "")
    mobiles = re.findall(r'(?:01[0125][0-9]{8})', clean_text_str)
    if mobiles:
        return mobiles[0]
    landlines = re.findall(r'(?:02[0-9]{8})', clean_text_str)
    if landlines:
        return landlines[0]
    return "غير متاح"

def extract_phone(text):
    return extract_mobile_phone(text)

def _search_web(query):
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for item in soup.select(".result"):
            link = item.select_one(".result__a")
            snippet = item.select_one(".result__snippet")
            if not link:
                continue
            href = link.get("href", "").strip()
            title = link.get_text(" ", strip=True)
            if href:
                results.append({
                    "url": href,
                    "title": title,
                    "snippet": snippet.get_text(" ", strip=True) if snippet else ""
                })
        return results
    except Exception:
        return []

def search_web(query, max_results=8):
    return _search_web(query)[:max_results]

def extract_dealer_name(title, snippet, url):
    clean = clean_text(title.split("-")[0].split("|")[0])
    return clean if len(clean) > 3 else ""

def verify_all_platforms(dealer_name, district=""):
    """فحص المنصات باسم المعرض والمنطقة"""
    clean_dealer = re.sub(r'[^\w\s]', '', dealer_name).strip()
    search_term = f'"{clean_dealer}" {district}'.strip()

    status = {
        "facebook": "غير موجود",
        "dubizzle": "غير مشترك",
        "dubizzle_results": "فرصة استهداف ممتازة",
        "contactcars": "غير متاح",
        "contactcars_results": "غير موجود"
    }

    fb_results = _search_web(f'site:facebook.com {search_term}')
    if fb_results:
        status["facebook"] = "موجود (نشط)"

    dub_results = _search_web(f'site:dubizzle.com.eg {search_term}')
    if dub_results:
        status["dubizzle"] = "مشترك نشط"
        status["dubizzle_results"] = "إعلانات مسجلة"

    cc_results = _search_web(f'site:contactcars.com {search_term}')
    if cc_results:
        status["contactcars"] = "موجود"
        status["contactcars_results"] = "إعلانات مسجلة"

    return status

# =========================================================
# DIRECTORY DISCOVERY (كودك الأصلي تماماً مع إضافة الماب)
# =========================================================

def search_directory(url, district, max_results=10):
    try:
        response = requests.get(url, headers=HEADERS, timeout=SEARCH_TIMEOUT)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        candidates = []

        for tag in soup.find_all(["h2", "h3", "h4", "a"]):
            value = clean_text(tag.get_text(" ", strip=True))
            if value:
                candidates.append((tag, value))

        seen = set()

        for tag, name in candidates:
            normalized = normalize_name(name)

            ignored = [
                "car agents", "car showrooms", "car dealerships", "used cars",
                "new cars dealers", "car dealers", "معارض سيارات", "معارض بيع سيارات",
                "سيارات مستعملة", "سيارات جديدة", "more info", "phone number", "map",
                "website", "email us", "whatsapp",
            ]

            if normalized in [normalize_name(x) for x in ignored] or len(name) < 3 or len(name) > 100:
                continue

            bad_parts = ["search", "login", "register", "home", "contact us", "privacy", "terms", "facebook", "instagram", "youtube"]
            if any(normalize_name(x) in normalized for x in bad_parts):
                continue

            if normalized in seen:
                continue

            parent = tag.parent
            nearby = clean_text(parent.get_text(" ", strip=True)) if parent else ""
            if len(nearby) < 30:
                try:
                    nearby = clean_text(tag.parent.parent.get_text(" ", strip=True))
                except Exception:
                    pass

            combined = f"{name} {nearby}"

            district_normalized = normalize_name(district)
            combined_normalized = normalize_name(combined)

            if district_normalized not in combined_normalized:
                english_area = {
                    "مدينة نصر": "nasr city", "مصر الجديدة": "heliopolis", "التجمع الخامس": "new cairo",
                    "المعادي": "maadi", "المهندسين": "mohandessin", "الدقي": "dokki", "الهرم": "haram",
                    "فيصل": "faisal", "الشروق": "shorouk", "العبور": "obour", "الشيخ زايد": "sheikh zayed", "6 أكتوبر": "6 october"
                }.get(district, "")

                if english_area and normalize_name(english_area) not in combined_normalized:
                    continue

            car_keywords = ["car", "cars", "motor", "motors", "auto", "automotive", "showroom", "سيارات", "سياره", "سيارة", "معرض", "موتور"]
            if not any(normalize_name(keyword) in combined_normalized for keyword in car_keywords):
                continue

            phone = extract_mobile_phone(combined)
            source_url = url

            if tag.name == "a":
                href = tag.get("href", "")
                if href:
                    if href.startswith("/"):
                        source_url = requests.compat.urljoin(url, href)
                    elif href.startswith("http"):
                        source_url = href

            seen.add(normalized)
            maps_link = f"https://www.google.com/maps/search/{quote(name + ' ' + district)}"

            results.append({
                "اسم المعرض": name,
                "المنطقة": district,
                "الهاتف": phone,
                "رابط الخريطة": maps_link,
                "Facebook": "",
                "مصدر الاكتشاف": source_url,
                "وصف المصدر": nearby,
            })

            if len(results) >= max_results:
                break

        return results
    except Exception:
        return []

def discover_dealers(district, max_results=10):
    all_dealers = []
    directory_urls = []

    if district == "مدينة نصر":
        directory_urls = [
            "https://yellowpages.com.eg/en/category/nasr-city-new-cars-dealers/3256",
            "https://yellowpages.com.eg/en/category/nasr-city-car-dealerships/3256",
            "https://www.140online.com/Classes.aspx?Area=375&AreaName=Nasr+City&ClassId=140&Gov=2&GovName=Cairo&Lang=En"
        ]
    elif district == "مصر الجديدة":
        directory_urls = ["https://yellowpages.com.eg/en/category/heliopolis-new-cars-dealers"]
    elif district == "المعادي":
        directory_urls = ["https://yellowpages.com.eg/en/category/maadi-new-cars-dealers"]

    for url in directory_urls:
        remaining = max_results - len(all_dealers)
        if remaining <= 0:
            break
        results = search_directory(url, district, remaining)
        all_dealers.extend(results)
        time.sleep(0.3)

    if len(all_dealers) < max_results:
        fallback_queries = [f'"{district}" "معرض سيارات" مصر', f'"{district}" "معارض سيارات" مصر']
        for query in fallback_queries:
            results = search_web(query, max_results=8)
            for result in results:
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                url = result.get("url", "")

                bad_words = ["carfax", "denver", "texas", "california", "florida", "new york", "los angeles"]
                combined = normalize_name(f"{title} {snippet}")
                if any(normalize_name(word) in combined for word in bad_words):
                    continue

                name = extract_dealer_name(title, snippet, url)
                if not name:
                    continue

                phone = extract_mobile_phone(f"{title} {snippet}")
                maps_link = f"https://www.google.com/maps/search/{quote(name + ' ' + district)}"

                all_dealers.append({
                    "اسم المعرض": name,
                    "المنطقة": district,
                    "الهاتف": phone,
                    "رابط الخريطة": maps_link,
                    "Facebook": "",
                    "مصدر الاكتشاف": url,
                    "وصف المصدر": snippet,
                })

                if len(all_dealers) >= max_results:
                    break

            if len(all_dealers) >= max_results:
                break

    unique = []
    seen = set()

    for dealer in all_dealers:
        key = normalize_name(dealer.get("اسم المعرض", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(dealer)
        if len(unique) >= max_results:
            break

    return unique
