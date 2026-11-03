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


_MOBILE_RE = re.compile(
    r"(?<!\d)(?:\+?20|0020|0)?[\s\-\.]?(1[0125])((?:[\s\-\.]?\d){8})(?!\d)"
)
_LANDLINE_RE = re.compile(
    r"(?<!\d)(?:\+?20|0020|0)[\s\-\.]?([2-9](?:[\s\-\.]?\d){7,8})(?!\d)"
)


def extract_mobile_phone(text):
    """يطلّع رقم موبايل مصري (010/011/012/015)، وإلا رقم أرضي، وإلا 'غير متاح'.
    بيقرأ النص زي ما هو (من غير ما يلزق الأرقام ببعض)، فالعنوان اللي جنب الرقم مايبوّظوش."""
    if not text:
        return "غير متاح"
    t = str(text).translate(AR_DIGITS)

    m = _MOBILE_RE.search(t)
    if m:
        return "0" + m.group(1) + re.sub(r"\D", "", m.group(2))

    m = _LANDLINE_RE.search(t)
    if m:
        return "0" + re.sub(r"\D", "", m.group(1))

    return "غير متاح"


def extract_phone(text):
    return extract_mobile_phone(text)


def is_mobile_number(value):
    return bool(re.fullmatch(r"01[0125]\d{8}", clean_digits(value)))


# =========================================================
# البحث: Serper (لو فيه مفتاح) أو DuckDuckGo (احتياطي)
# =========================================================

# عدّاد طلبات Serper (كل طلب = credit واحد تقريباً). التطبيق بيصفّره في أول كل عملية.
USAGE = {"serper_calls": 0}


def _serper(endpoint, payload):
    key = _key()
    if not key:
        return None
    USAGE["serper_calls"] += 1
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
# روابط فيسبوك / انستجرام / Ads Library
# =========================================================

# أول جزء في المسار اللي مش اسم صفحة (بوستات، جروبات، صور...)
_FB_SKIP = {
    "groups", "events", "marketplace", "watch", "reel", "reels", "share", "sharer",
    "photo", "photos", "photo.php", "video", "videos", "hashtag", "login", "public",
    "story.php", "permalink.php", "people", "l.php", "dialog", "policies", "help",
    "ads", "business", "gaming", "stories", "posts", "media", "plugins", "tr",
}
_IG_SKIP = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "directory"}

_FB_ID_PATTERNS = [
    r'"pageID"\s*:\s*"(\d{8,20})"',
    r'"page_id"\s*:\s*"(\d{8,20})"',
    r'fb://page/\?id=(\d{8,20})',
    r'fb://profile/(\d{8,20})',
    r'"entity_id"\s*:\s*"(\d{8,20})"',
]


def normalize_facebook_url(url):
    """يرجّع رابط الصفحة نفسها (مش بوست ولا صورة)، أو None لو الرابط مش صفحة."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    if not p.netloc.lower().endswith("facebook.com"):
        return None
    path = [s for s in p.path.split("/") if s]
    if path and re.fullmatch(r"[a-z]{2}-[a-z]{2}", path[0].lower()):
        path = path[1:]
    if not path:
        return None

    first = path[0].lower()
    if first == "profile.php":
        pid = parse_qs(p.query).get("id", [""])[0]
        return f"https://www.facebook.com/profile.php?id={pid}" if pid.isdigit() else None
    if first == "pages":
        if len(path) >= 4 and path[1].lower() == "category":
            return "https://www.facebook.com/" + "/".join(path[:4])
        if len(path) >= 3:
            return "https://www.facebook.com/" + "/".join(path[:3])
        return None
    if first in _FB_SKIP:
        return None
    return f"https://www.facebook.com/{path[0]}"


def normalize_instagram_url(url):
    try:
        p = urlparse(url)
    except Exception:
        return None
    if not p.netloc.lower().endswith("instagram.com"):
        return None
    path = [s for s in p.path.split("/") if s]
    if not path or path[0].lower() in _IG_SKIP:
        return None
    return f"https://www.instagram.com/{path[0]}/"


def extract_fb_page_id(url):
    """بيطلّع الـ page ID من شكل الرابط نفسه (من غير أي طلب إنترنت). أو None."""
    if not url:
        return None
    try:
        p = urlparse(url)
    except Exception:
        return None
    path = [s for s in p.path.split("/") if s]

    if path and path[0].lower() == "profile.php":
        pid = parse_qs(p.query).get("id", [""])[0]
        return pid if pid.isdigit() else None
    if path and path[0].lower() == "pages":
        for seg in reversed(path):
            if seg.isdigit() and len(seg) >= 8:
                return seg
        m = re.search(r"-(\d{10,20})$", path[-1])
        return m.group(1) if m else None
    if path:
        if path[0].isdigit() and len(path[0]) >= 8:
            return path[0]
        m = re.search(r"-(\d{10,20})$", path[0])  # زي Name-100064123456789
        if m:
            return m.group(1)
    return None


def fetch_fb_page_id(url, timeout=6):
    """محاولة أخيرة: نقرأ صفحة فيسبوك ونطلّع الـ ID منها. ممكن تفشل لو فيسبوك حجب الطلب."""
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
                "Accept-Language": "ar,en;q=0.8",
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        for pat in _FB_ID_PATTERNS:
            m = re.search(pat, r.text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


_BRANCH_MARKERS = [
    "branch", "فرع", "nasr city", "مدينة نصر", "maadi", "المعادي", "heliopolis",
    "مصر الجديدة", "new cairo", "التجمع", "mohandessin", "المهندسين", "dokki", "الدقي",
    "faisal", "فيصل", "haram", "الهرم", "october", "أكتوبر", "اكتوبر", "zayed", "زايد",
    "cairo", "القاهرة", "giza", "الجيزة",
]


def clean_dealer_name(name):
    """
    بيشيل اسم الفرع/المنطقة من اسم Google Maps:
    "Auto Samir Rayan - Nasr City Branch" -> "Auto Samir Rayan"
    لأن صفحة المعرض على فيسبوك ودوبيزل نادراً بيبقى اسمها فيه الفرع.
    """
    n = clean_text(re.sub(r"\(.*?\)", " ", name or ""))
    parts = [p for p in re.split(r"\s+[-–—|]\s+|\s*\|\s*", n) if p.strip()]
    if not parts:
        return clean_text(name)
    kept = [parts[0]] + [
        p for p in parts[1:] if not any(m in p.lower() for m in _BRANCH_MARKERS)
    ]
    out = clean_text(" - ".join(kept))
    out = re.sub(r"\s+(?:branch|فرع)\b.*$", "", out, flags=re.I)
    return clean_text(out) or clean_text(name)


def ads_library_link(name, page_id=None):
    """
    لو معانا page ID: بيفتح إعلانات صفحة المعرض نفسها (فيسبوك + انستجرام مع بعض).
    لو لأ: بحث بالكلمات باسم المعرض بعد شيل اسم الفرع (أقل دقة، ممكن يطلّع صفحات تانية).
    بنعرض كل الإعلانات (شغالة ومنتهية) عشان الفلتر مايخفّيش حاجة.
    """
    base = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=EG"
    if page_id:
        return f"{base}&view_all_page_id={page_id}&search_type=page&media_type=all"
    return f"{base}&q={quote(clean_dealer_name(name))}&search_type=keyword_unordered&media_type=all"


# =========================================================
# التحقق من المنصات
# =========================================================

def _match_results(domains, query, core, phone):
    """
    بيرجّع None لو البحث فشل، وإلا list بكل النتايج اللي اتطابقت (بالاسم أو الرقم).
    كل عنصر: {"url","title","snippet","by_phone"}.
    """
    results = _search_web(query, max_results=10)
    if results is None:
        return None
    last9 = clean_digits(phone)[-9:] if len(clean_digits(phone)) >= 9 else ""
    matched = []
    for r in results:
        if not any(d in r["url"] for d in domains):
            continue
        text = f'{r["title"]} {r["snippet"]}'
        by_phone = bool(last9 and last9 in clean_digits(text))
        if by_phone or _is_name_match(core, text):
            matched.append({**r, "by_phone": by_phone})
    return matched


def _check(domains, query, core, phone):
    """بيرجّع (الحالة, اللينك). مؤكد بس لو الاسم أو الرقم اتطابق فعلاً."""
    matched = _match_results(domains, query, core, phone)
    if matched is None:
        return UNKNOWN, ""
    if matched:
        best = sorted(matched, key=lambda m: not m["by_phone"])[0]
        return CONFIRMED, best["url"]
    return NOT_FOUND, ""


# كلمات في عنوان إعلان دوبيزل معناها إنه مش إعلان عربيات (عقار، قطع غيار، موتوسيكل...)
_DZ_NON_VEHICLE = [_arnorm(w) for w in [
    "commercial", "properties", "property", "for rent", "عقار", "للايجار", "للإيجار",
    "قطع غيار", "spare parts", "موتوسيكل", "motorcycle", "اكسسوار", "accessories",
    "شقق", "apartment", "فيلا", "villa", "اراضي", "أراضي", "land", "وظائف", "jobs",
    "services", "خدمات",
]]

# صفحة إعلان حقيقية: .../ad/<عنوان>-ID123456.html (مش صفحة بحث ولا تصنيف)
_DZ_AD_URL = re.compile(r"dubizzle\.com\.eg/(?:[a-z]{2}/)?ad/.+-ID\d+\.html", re.I)

# علامات إن الإعلان انتهى/اتشال
_DZ_EXPIRED_MARKERS = [
    "هذا الإعلان غير متاح", "هذا الاعلان غير متاح",
    "this ad is no longer available", "this ad is not available",
]


def _dz_is_ad_url(url):
    return bool(_DZ_AD_URL.search(url or ""))


def _dz_is_vehicle_ad(title):
    """إعلان عربيات للبيع (مش عقار/قطع غيار/خدمات)، من عنوان النتيجة."""
    t = _arnorm(title)
    if any(w in t for w in _DZ_NON_VEHICLE):
        return False
    return "سيارات للبيع" in t or "cars for sale" in t


def _dz_inspect_ad(ad_url, timeout=5):
    """
    بيفتح صفحة الإعلان (لو دوبيزل سمح) ويرجّع (منتهي؟, لينك صفحة البائع).
    منتهي = True/False، أو None لو معرفناش نقرأ الصفحة. الأخطاء مش بتوقف البرنامج.
    """
    try:
        r = requests.get(ad_url, headers=HEADERS, timeout=timeout)
        if r.status_code in (404, 410):
            return True, None
        if r.status_code != 200:
            return None, None
        html = r.text
        low = html.lower()
        expired = any(m.lower() in low for m in _DZ_EXPIRED_MARKERS)
        m = re.search(
            r'href="((?:https://www\.dubizzle\.com\.eg)?/(?:en/|ar/)?profile/[\w\-]+/?)"', html
        )
        profile = urljoin("https://www.dubizzle.com.eg", m.group(1)) if m else None
        return expired, profile
    except Exception:
        return None, None


DZ_KIND_PROFILE = "صفحة البائع"
DZ_KIND_VEHICLE_AD = "إعلان سيارة للمعرض"
DZ_KIND_OTHER_AD = "إعلان (مش سيارات)"
DZ_KIND_EXPIRED = "إعلان قديم/منتهي"


def check_dubizzle(dealer_name, core, phone):
    """
    بيرجّع (الحالة, اللينك, نوع اللينك). حالة المنصة نفسها زي ما كانت.
    اللينك: بنستبعد أي صفحة مش إعلان (بحث/تصنيف)، ونقدّم إعلانات العربيات، وبنفتح أول
    ٣ مرشحين نشوف مين لسه شغال. لو كلهم منتهيين بنرجّع أحسنهم ونوضّح إنه قديم.
    """
    matched = _match_results(
        ["dubizzle.com.eg"], f'site:dubizzle.com.eg "{dealer_name}"', core, phone
    )
    if matched is None:
        return UNKNOWN, "", ""
    if not matched:
        return NOT_FOUND, "", ""

    ads = [m for m in matched if _dz_is_ad_url(m["url"])]
    if not ads:
        # اتطابق على صفحات مش إعلانات (بحث/تصنيف): نأكد الحالة من غير ما نقدّم لينك مضلل
        return CONFIRMED, "", ""

    ranked = sorted(ads, key=lambda m: (not _dz_is_vehicle_ad(m["title"]), not m["by_phone"]))
    first_expired = None
    for m in ranked[:3]:
        expired, profile = _dz_inspect_ad(m["url"])
        if profile:
            return CONFIRMED, profile, DZ_KIND_PROFILE
        if expired:
            first_expired = first_expired or m
            continue
        kind = DZ_KIND_VEHICLE_AD if _dz_is_vehicle_ad(m["title"]) else DZ_KIND_OTHER_AD
        return CONFIRMED, m["url"], kind
    return CONFIRMED, first_expired["url"], DZ_KIND_EXPIRED


def check_facebook(dealer_name, core, phone):
    """
    بيرجّع (الحالة, رابط الصفحة, page_id).
    الرابط دايماً صفحة المعرض نفسها (مش بوست)، وفيسبوك مقدَّم على انستجرام.
    """
    matched = _match_results(
        ["facebook.com", "instagram.com"],
        f'(site:facebook.com OR site:instagram.com) "{dealer_name}"',
        core, phone,
    )
    if matched is None:
        return UNKNOWN, "", None
    if not matched:
        return NOT_FOUND, "", None

    candidates = []  # (is_instagram, not_by_phone, order, url, is_fb)
    for i, m in enumerate(matched):
        fb = normalize_facebook_url(m["url"])
        if fb:
            candidates.append((0, not m["by_phone"], i, fb))
            continue
        ig = normalize_instagram_url(m["url"])
        if ig:
            candidates.append((1, not m["by_phone"], i, ig))

    if not candidates:
        # اتلاقى تطابق بس الروابط كلها بوستات/جروبات: مؤكد بس من غير لينك صفحة
        return CONFIRMED, "", None

    url = sorted(candidates)[0][3]
    page_id = extract_fb_page_id(url)
    if not page_id and "facebook.com" in url:
        page_id = fetch_fb_page_id(url)
    return CONFIRMED, url, page_id


def verify_all_platforms(dealer_name, district="", phone=""):
    dealer_name = clean_dealer_name(dealer_name)  # بدون اسم الفرع/المنطقة
    core = core_name(dealer_name)

    status = {
        "facebook": UNKNOWN,
        "facebook_url": "",
        "facebook_page_id": None,
        "facebook_ads_link": ads_library_link(dealer_name),
        "facebook_ads_exact": False,
        "dubizzle": UNKNOWN,
        "dubizzle_results": "يحتاج فحص يدوي",
        "dubizzle_link_kind": "",
        "contactcars": UNKNOWN,
        "contactcars_results": "يحتاج فحص يدوي",
    }

    if len(core) < 4:
        return status  # الاسم عام جداً، مفيش تحقق موثوق

    # فيسبوك / انستجرام (وجود صفحة، مش معناه إعلانات شغالة: استخدم لينك Ad Library)
    st, url, page_id = check_facebook(dealer_name, core, phone)
    status["facebook"] = "موجود (صفحة مؤكدة)" if st == CONFIRMED else st
    status["facebook_url"] = url
    status["facebook_page_id"] = page_id
    if page_id:
        status["facebook_ads_link"] = ads_library_link(dealer_name, page_id)
        status["facebook_ads_exact"] = True
    time.sleep(0.1)

    # دوبيزل
    st, url, kind = check_dubizzle(dealer_name, core, phone)
    if st == CONFIRMED:
        status["dubizzle"], status["dubizzle_results"] = "مشترك (مؤكد)", url
        status["dubizzle_link_kind"] = kind
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
