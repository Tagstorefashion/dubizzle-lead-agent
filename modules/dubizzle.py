import os
import re
import time
from urllib.parse import quote, urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

# =========================================================
# إعدادات عامة
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}
SEARCH_TIMEOUT = 10

SERPER_SEARCH = "https://google.serper.dev/search"
SERPER_PLACES = "https://google.serper.dev/places"

# حالات التحقق: ٣ حالات بدل ٢، عشان "ماقدرناش نفحص" ما تتحولش لـ "مش موجود"
CONFIRMED = "موجود (مؤكد)"
NOT_FOUND = "لم يتم العثور"
UNKNOWN = "غير مؤكد"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _key():
    """مفتاح Serper (من متغير بيئة SERPER_API_KEY)."""
    return os.getenv("SERPER_API_KEY", "").strip()


# =========================================================
# أدوات النصوص والأرقام
# =========================================================

def clean_text(text):
    return " ".join(text.split()) if text else ""


def clean_digits(text):
    """يحوّل الأرقام العربية لإنجليزي ويشيل المسافات والشرط والأقواس."""
    text = (text or "").translate(AR_DIGITS)
    return re.sub(r"[\s\-\(\)\.]", "", text)


def _arnorm(text):
    text = (text or "").lower()
    for old, new in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s]", " ", text)
    return clean_text(text)


def normalize_name(name):
    return _arnorm(name)


_GENERIC = {
    _arnorm(w) for w in [
        "للسيارات", "سيارات", "للعربيات", "عربيات", "معرض", "معارض", "للتجارة",
        "تجارة", "موتورز", "موتور", "اوتو", "أوتو", "كار", "كارز", "cars", "car",
        "motors", "motor", "auto", "automotive", "egypt", "showroom", "trade",
        "trading", "الشركة", "شركة", "مصر",
    ]
}


def core_name(name):
    """الاسم المميز للمعرض بعد شيل الكلمات العامة (معرض، سيارات، auto...)."""
    words = [w for w in _arnorm(name).split() if w not in _GENERIC]
    return " ".join(words)


def _is_name_match(core, text):
    if len(core) < 4:
        return False
    return fuzz.partial_ratio(core, _arnorm(text)) >= 90


def extract_mobile_phone(text):
    """يطلّع رقم موبايل مصري (010/011/012/015)، وإلا رقم أرضي، وإلا 'غير متاح'."""
    if not text:
        return "غير متاح"
    t = clean_digits(text)

    m = re.search(r"(?<!\d)(?:\+20|0020|20|0)?(1[0125]\d{8})(?!\d)", t)
    if m:
        return "0" + m.group(1)

    m = re.search(r"(?<!\d)(?:\+20|0)([2-9]\d{7,8})(?!\d)", t)
    if m:
        return "0" + m.group(1)

    return "غير متاح"


def extract_phone(text):
    return extract_mobile_phone(text)


def is_mobile_number(value):
    return bool(re.fullmatch(r"01[0125]\d{8}", clean_digits(value)))


# =========================================================
# البحث: Serper (لو فيه مفتاح) أو DuckDuckGo (احتياطي)
# =========================================================

def _serper(endpoint, payload):
    key = _key()
    if not key:
        return None
    try:
        r = requests.post(
            endpoint,
            json=payload,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _real_url(href):
    """DuckDuckGo بيرجّع لينك تحويل، بنطلّع منه اللينك الحقيقي."""
    if "uddg=" in href:
        try:
            q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
            return unquote(q.get("uddg", [href])[0])
        except Exception:
            return href
    return href


def _ddg(query):
    """بيرجّع list، أو None لو DuckDuckGo حجب الطلب (عشان ما نعتبرهاش 'مش موجود')."""
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/?q=" + quote(query),
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for item in soup.select(".result"):
            a = item.select_one(".result__a")
            if not a:
                continue
            sn = item.select_one(".result__snippet")
            out.append({
                "url": _real_url(a.get("href", "").strip()),
                "title": a.get_text(" ", strip=True),
                "snippet": sn.get_text(" ", strip=True) if sn else "",
            })
        if not out and "No results" not in r.text:
            return None
        return out
    except Exception:
        return None


def _search_web(query, max_results=8):
    """list = نتائج (ممكن فاضية فعلاً) | None = فشل البحث نفسه."""
    if _key():
        data = _serper(SERPER_SEARCH, {"q": query, "gl": "eg", "hl": "ar", "num": max_results})
        if data is None:
            return None
        return [
            {"url": i.get("link", ""), "title": i.get("title", ""), "snippet": i.get("snippet", "")}
            for i in data.get("organic", [])
        ][:max_results]
    res = _ddg(query)
    return res[:max_results] if res is not None else None


def search_web(query, max_results=8):
    return _search_web(query, max_results) or []


def extract_dealer_name(title, snippet, url):
    clean = clean_text(title.split("-")[0].split("|")[0])
    return clean if len(clean) > 3 else ""


# =========================================================
# التحقق من المنصات
# =========================================================

def _check(domains, query, core, phone):
    """بيرجّع (الحالة, اللينك). مؤكد بس لو الاسم أو الرقم اتطابق فعلاً."""
    results = _search_web(query)
    if results is None:
        return UNKNOWN, ""
    last9 = clean_digits(phone)[-9:] if len(clean_digits(phone)) >= 9 else ""
    for r in results:
        if not any(d in r["url"] for d in domains):
            continue
        text = f'{r["title"]} {r["snippet"]}'
        if (last9 and last9 in clean_digits(text)) or _is_name_match(core, text):
            return CONFIRMED, r["url"]
    return NOT_FOUND, ""


def verify_all_platforms(dealer_name, district="", phone=""):
    core = core_name(dealer_name)
    ads_link = (
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=EG"
        f"&q={quote(dealer_name)}&search_type=keyword_unordered"
    )

    status = {
        "facebook": UNKNOWN,
        "facebook_url": "",
        "facebook_ads_link": ads_link,
        "dubizzle": UNKNOWN,
        "dubizzle_results": "يحتاج فحص يدوي",
        "contactcars": UNKNOWN,
        "contactcars_results": "يحتاج فحص يدوي",
    }

    if len(core) < 4:
        return status  # الاسم عام جداً، مفيش تحقق موثوق

    # فيسبوك / انستجرام (وجود صفحة، مش معناه إعلانات شغالة: استخدم لينك Ad Library)
    st, url = _check(
        ["facebook.com", "instagram.com"],
        f'(site:facebook.com OR site:instagram.com) "{dealer_name}"',
        core, phone,
    )
    status["facebook"] = "موجود (صفحة مؤكدة)" if st == CONFIRMED else st
    status["facebook_url"] = url
    time.sleep(0.1)

    # دوبيزل
    st, url = _check(
        ["dubizzle.com.eg"], f'site:dubizzle.com.eg "{dealer_name}"', core, phone
    )
    if st == CONFIRMED:
        status["dubizzle"], status["dubizzle_results"] = "مشترك (مؤكد)", url
    elif st == NOT_FOUND:
        status["dubizzle"], status["dubizzle_results"] = "لم يتم العثور", "فرصة استهداف"
    time.sleep(0.1)

    # كونتكت كارز
    st, url = _check(
        ["contactcars.com"], f'site:contactcars.com "{dealer_name}"', core, phone
    )
    if st == CONFIRMED:
        status["contactcars"], status["contactcars_results"] = "موجود (مؤكد)", url
    elif st == NOT_FOUND:
        status["contactcars"], status["contactcars_results"] = "لم يتم العثور", "فرصة استهداف"

    return status


# =========================================================
# الاكتشاف: Google Maps عن طريق Serper (الأدق)
# =========================================================

_BAD_CATEGORIES = [
    "ورشة", "صيانة", "repair", "parts", "قطع غيار", "tire", "اطارات", "إطارات",
    "wash", "غسيل", "rental", "تأجير", "insurance", "تأمين",
]


def _maps_link(place):
    cid = place.get("cid")
    if cid:
        return f"https://www.google.com/maps?cid={cid}"
    lat, lng = place.get("latitude"), place.get("longitude")
    if lat and lng:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return ""


def _discover_places(district, max_results):
    keywords = ["معرض سيارات", "معارض سيارات مستعملة", "تجارة سيارات", "car showroom"]
    seen, dealers = set(), []

    for kw in keywords:
        for page in range(1, 4):
            data = _serper(SERPER_PLACES, {
                "q": f"{kw} {district}", "gl": "eg", "hl": "ar", "page": page,
            })
            places = (data or {}).get("places", [])
            if not places:
                break

            for p in places:
                name = clean_text(p.get("title", ""))
                category = (p.get("category") or "").lower()
                if not name or any(b in category for b in _BAD_CATEGORIES):
                    continue
                uid = p.get("cid") or f'{name}|{p.get("address", "")}'
                if uid in seen:
                    continue
                seen.add(uid)

                phone = clean_text(p.get("phoneNumber", ""))
                address = clean_text(p.get("address", ""))
                dealers.append({
                    "اسم المعرض": name,
                    "المنطقة": district,
                    "الهاتف": phone or "غير متاح",
                    "رابط الخريطة": _maps_link(p),
                    "العنوان": address,
                    "الموقع": p.get("website", ""),
                    "مصدر الاكتشاف": "Google Maps",
                    "وصف المصدر": f"{address} {phone}",
                })
            time.sleep(0.2)

            if len(dealers) >= max_results:
                return dealers[:max_results]

    return dealers[:max_results]


def _enrich_mobile(dealer):
    """لو المعرض ملهوش موبايل، نبحث عن رقم ظاهر في نتائج جوجل بنفس الاسم."""
    core = core_name(dealer["اسم المعرض"])
    if len(core) < 4:
        return
    results = _search_web(f'"{dealer["اسم المعرض"]}" {dealer["المنطقة"]} موبايل واتساب') or []
    for r in results:
        text = f'{r["title"]} {r["snippet"]}'
        if _is_name_match(core, text):
            mobile = extract_mobile_phone(text)
            if is_mobile_number(mobile):
                dealer["الهاتف"] = mobile
                return


# =========================================================
# الاكتشاف الاحتياطي (من غير مفتاح): أدلة + DuckDuckGo
# =========================================================

def search_directory(url, district, max_results=10):
    try:
        response = requests.get(url, headers=HEADERS, timeout=SEARCH_TIMEOUT)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        for tag in soup.find_all(["h2", "h3", "h4"]):
            value = clean_text(tag.get_text(" ", strip=True))
            if value:
                candidates.append((tag, value))

        bad_words = [
            "map view", "filters", "locations", "letters", "categories", "brands",
            "car agents", "car showrooms", "car dealerships", "used cars",
            "new cars dealers", "car dealers", "معارض سيارات", "معارض بيع سيارات",
            "سيارات مستعملة", "سيارات جديدة", "more info", "phone number", "map",
            "website", "email us", "whatsapp", "search", "login", "register",
            "home", "contact us", "privacy", "terms", "facebook", "instagram", "youtube",
            "الرئيسية", "اتصل بنا", "بحث", "تسجيل الدخول", "عن الشركة", "عرض الخريطة",
        ]
        car_keywords = ["car", "cars", "motor", "motors", "auto", "automotive", "showroom",
                        "سيارات", "سياره", "سيارة", "معرض", "موتور", "أوتو"]

        results, seen = [], set()
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
            if not any(normalize_name(k) in normalize_name(combined) for k in car_keywords):
                continue

            seen.add(normalized)
            results.append({
                "اسم المعرض": name,
                "المنطقة": district,
                "الهاتف": extract_mobile_phone(combined),
                "رابط الخريطة": f"https://www.google.com/maps/search/{quote(name + ' ' + district)}",
                "مصدر الاكتشاف": url,
                "وصف المصدر": nearby,
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def _discover_free(district, max_results):
    all_dealers, directory_urls = [], []

    if district == "مدينة نصر":
        directory_urls = [
            "https://yellowpages.com.eg/en/category/nasr-city-new-cars-dealers/3256",
            "https://yellowpages.com.eg/en/category/nasr-city-car-dealerships/3256",
            "https://www.140online.com/Classes.aspx?Area=375&AreaName=Nasr+City&ClassId=140&Gov=2&GovName=Cairo&Lang=En",
        ]
    elif district == "مصر الجديدة":
        directory_urls = ["https://yellowpages.com.eg/en/category/heliopolis-new-cars-dealers"]
    elif district == "المعادي":
        directory_urls = ["https://yellowpages.com.eg/en/category/maadi-new-cars-dealers"]

    for url in directory_urls:
        remaining = max_results - len(all_dealers)
        if remaining <= 0:
            break
        all_dealers.extend(search_directory(url, district, remaining))
        time.sleep(0.3)

    if len(all_dealers) < max_results:
        bad_words = ["carfax", "denver", "texas", "california", "florida",
                     "new york", "los angeles", "filters", "map view"]
        for query in (f'"{district}" "معرض سيارات" مصر', f'"{district}" "معارض سيارات" مصر'):
            for result in search_web(query, max_results=8):
                title, snippet, url = result["title"], result["snippet"], result["url"]
                combined = normalize_name(f"{title} {snippet}")
                if any(normalize_name(w) in combined for w in bad_words):
                    continue
                name = extract_dealer_name(title, snippet, url)
                if not name:
                    continue
                all_dealers.append({
                    "اسم المعرض": name,
                    "المنطقة": district,
                    "الهاتف": extract_mobile_phone(f"{title} {snippet}"),
                    "رابط الخريطة": f"https://www.google.com/maps/search/{quote(name + ' ' + district)}",
                    "مصدر الاكتشاف": url,
                    "وصف المصدر": snippet,
                })
                if len(all_dealers) >= max_results:
                    break
            if len(all_dealers) >= max_results:
                break

    return all_dealers


# =========================================================
# الدالة الرئيسية
# =========================================================

def discover_dealers(district, max_results=10):
    dealers = []

    if _key():
        dealers = _discover_places(district, max_results)
    if not dealers:
        dealers = _discover_free(district, max_results)

    unique, seen = [], set()
    for dealer in dealers:
        key = normalize_name(dealer.get("اسم المعرض", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(dealer)
        if len(unique) >= max_results:
            break

    # محاولة إيجاد موبايل للمعارض اللي رقمها أرضي أو ناقص (بتستهلك بحث لكل معرض)
    if _key():
        for dealer in unique:
            if not is_mobile_number(dealer.get("الهاتف", "")):
                _enrich_mobile(dealer)
                time.sleep(0.1)

    return unique
