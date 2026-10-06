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

def _search_web(query):
    """البحث عبر DuckDuckGo HTML وجلب النتائج"""
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

def _is_dubizzle_company_url(url):
    if not url:
        return False
    url = url.lower()
    return "dubizzle.com.eg" in url and "/companies/" in url

def _extract_active_ads(text):
    if not text:
        return None
    patterns = [
        r"Active\s+ads\s+([\d,]+)",
        r"active\s+ads\s*[:\-]?\s*([\d,]+)",
        r"([\d,]+)\s+Active\s+ads",
        r"إعلانات\s+نشطة\s*[:\-]?\s*([\d,]+)",
        r"([\d,]+)\s+إعلانات\s+نشطة",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except Exception:
                pass
    return None

def _fetch_company_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        if not text:
            return None

        active_ads = _extract_active_ads(text)
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)
        if not title:
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(" ", strip=True)

        verified = "Verified Business" in text or "Verified business" in text or "متجر موثوق" in text

        return {
            "name": title,
            "listing_count": active_ads,
            "verified": verified,
            "url": url,
        }
    except Exception:
        return None

def _find_company_page(dealer_name, district=""):
    clean_name = re.sub(r'[^\w\s]', '', dealer_name).strip()
    searches = []

    if district:
        searches.append(f'site:dubizzle.com.eg/en/companies/ "{clean_name}" "{district}"')
    searches.append(f'site:dubizzle.com.eg/en/companies/ "{clean_name}"')
    searches.append(f'site:dubizzle.com.eg/en/companies/ {clean_name}')

    for query in searches:
        results = _search_web(query)
        for result in results:
            url = result.get("url", "")
            if not _is_dubizzle_company_url(url):
                continue
            page = _fetch_company_page(url)
            if page:
                return page
    return None

def verify_all_platforms(dealer_name, district=""):
    """
    التحقق المباشر والكامل من المنصات (Facebook, Dubizzle, ContactCars) 
    باستخدام اسم المعرض والمنطقة لضمان أقصى دقة.
    """
    clean_dealer = re.sub(r'[^\w\s]', '', dealer_name).strip()
    search_term = f'"{clean_dealer}" {district}'.strip()

    status = {
        "facebook": "غير موجود",
        "dubizzle": "غير مشترك",
        "dubizzle_results": "فرصة استهداف ممتازة",
        "contactcars": "غير متاح",
        "contactcars_results": "غير موجود"
    }

    # 1. فحص Dubizzle المباشر وتحديد عدد الإعلانات
    dub_page = _find_company_page(dealer_name=dealer_name, district=district)
    if dub_page:
        count = dub_page.get("listing_count")
        status["dubizzle"] = "مشترك نشط"
        status["dubizzle_results"] = f"{count} إعلانات نشطة" if count is not None else "متجر مسجل"

    # 2. فحص Facebook
    fb_results = _search_web(f'site:facebook.com {search_term}')
    if fb_results:
        status["facebook"] = "موجود (نشط)"

    # 3. فحص ContactCars
    cc_results = _search_web(f'site:contactcars.com {search_term}')
    if cc_results:
        status["contactcars"] = "موجود"
        status["contactcars_results"] = "إعلانات مسجلة"

    return status

def get_dubizzle_status(dealer_name, district=""):
    empty_result = {
        "status": "غير متحقق",
        "listing_count": None,
        "url": "",
        "verified": False,
        "source": "Dubizzle",
    }

    if not dealer_name:
        return empty_result

    page = _find_company_page(dealer_name=dealer_name, district=district)
    if not page:
        return empty_result

    return {
        "status": "موجود",
        "listing_count": page.get("listing_count"),
        "url": page.get("url", ""),
        "verified": page.get("verified", False),
        "source": "Dubizzle",
    }

def process_discovered_dealer(dealer_name, district, raw_text=""):
    """
    دالة شاملة تأخذ بيانات المعرض وتخرج الصف كاملاً جاهزاً للجدول:
    - اسم المعرض
    - الرقم
    - الخريطة
    - التحقق من المنصات باسم المعرض
    """
    phone = extract_mobile_phone(raw_text)
    maps_link = f"https://www.google.com/maps/search/{quote(dealer_name + ' ' + district)}"
    platforms = verify_all_platforms(dealer_name, district)

    return {
        "اسم المعرض": dealer_name,
        "المنطقة": district,
        "الموبايل": phone,
        "رابط الخريطة": maps_link,
        "Facebook": platforms["facebook"],
        "Dubizzle": platforms["dubizzle"],
        "Dubizzle Results": platforms["dubizzle_results"],
        "ContactCars": platforms["contactcars"],
        "ContactCars Results": platforms["contactcars_results"]
    }
