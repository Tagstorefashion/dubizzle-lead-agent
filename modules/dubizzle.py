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
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
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
        response = requests.get(url, headers=HEADERS, timeout=8)
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
    """فحص المنصات باسم المعرض والمنطقة باستعلام مرن وفعال"""
    clean_dealer = re.sub(r'[^\w\s]', ' ', dealer_name).strip()
    # استخراج أول كلمتين أساسيتين من اسم المعرض لضمان دقة البحث
    core_words = " ".join(clean_dealer.split()[:3])
    
    status = {
        "facebook": "غير موجود",
        "dubizzle": "غير مشترك",
        "dubizzle_results": "فرصة استهداف ممتازة",
        "contactcars": "غير متاح",
        "contactcars_results": "غير موجود"
    }

    if not core_words or len(core_words) < 3:
        return status

    # 1. فحص فيسبوك
    fb_query = f'site:facebook.com "{core_words}" {district}'
    fb_res = _search_web(fb_query)
    if fb_res:
        status["facebook"] = "موجود (نشط)"
    else:
        # محاولة بحث أوسع
        if _search_web(f'site:facebook.com {core_words} مصر'):
            status["facebook"] = "موجود (نشط)"

    time.sleep(0.1)

    # 2. فحص دوبيزل
    dub_query = f'site:dubizzle.com.eg {core_words}'
    dub_res = _search_web(dub_query)
    if dub_res:
        status["dubizzle"] = "مشترك نشط"
        status["dubizzle_results"] = "إعلانات/متجر مسجل"

    time.sleep(0.1)

    # 3. فحص كونتكت كارز
    cc_query = f'site:contactcars.com {core_words}'
    cc_res = _search_web(cc_query)
    if cc_res:
        status["contactcars"] = "موجود"
        status["contactcars_results"] = "إعلانات مسجلة"

    return status

# =========================================================
# DIRECTORY DISCOVERY
# =========================================================

def search_directory(url, district, max_results=10):
    try:
        response = requests.get(url, headers=HEADERS, timeout=SEARCH_TIMEOUT)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        candidates = []

        # سحب العناوين المباشرة فقط
        for tag in soup.find_all(["h2", "h3", "h4"]):
            value = clean_text(tag.get_text(" ", strip=True))
            if value:
                candidates.append((tag, value))

        seen = set()

        # استبعاد عناصر الملاحة والروابط الهيكلية كلياً
        bad_words = [
            "map view", "filters", "locations", "letters", "categories", "brands",
            "car agents", "car showrooms", "car dealerships", "used cars",
            "new cars dealers", "car dealers", "معارض سيارات", "معارض بيع سيارات",
            "سيارات مستعملة", "سيارات جديدة", "more info", "phone number", "map",
            "website", "email us", "whatsapp", "search", "login", "register",
            "home", "contact us", "privacy", "terms", "facebook", "instagram", "youtube",
            "الرئيسية", "اتصل بنا", "بحث", "تسجيل الدخول", "عن الشركة", "عرض الخريطة"
        ]

        for tag, name in candidates:
            normalized = normalize_name(name)

            if any(bad in normalized for bad in bad_words) or len(name) < 3 or len(name) > 80:
                continue

            if normalized in seen:
                continue

            parent = tag.parent
            nearby = clean_text(parent.get_text(" ", strip=True)) if parent else ""
            if len(nearby) < 20:
                try:
                    nearby = clean_text(tag.parent.parent.get_text(" ", strip=True))
                except Exception:
                    pass

            combined = f"{name} {nearby}"

            car_keywords = ["car", "cars", "motor", "motors", "auto", "automotive", "showroom", "سيارات", "سياره", "سيارة", "معرض", "موتور", "أوتو"]
            if not any(normalize_name(keyword) in normalize_name(combined) for keyword in car_keywords):
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

    # البحث الاحتياطي في حال عدم كفاية النتائج
    if len(all_dealers) < max_results:
        fallback_queries = [f'"{district}" "معرض سيارات" مصر', f'"{district}" "معارض سيارات" مصر']
        for query in fallback_queries:
            results = search_web(query, max_results=8)
            for result in results:
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                url = result.get("url", "")

                bad_words = ["carfax", "denver", "texas", "california", "florida", "new york", "los angeles", "filters", "map view"]
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
