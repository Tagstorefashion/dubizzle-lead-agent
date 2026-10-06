import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}


def _search_web(query):
    """
    Search DuckDuckGo HTML and return useful result URLs/titles/snippets.
    """
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=12,
        )

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
                    "snippet": snippet.get_text(" ", strip=True)
                    if snippet
                    else "",
                })

        return results

    except Exception:
        return []


def _is_dubizzle_company_url(url):
    """
    Accept only real Dubizzle company pages.
    """
    if not url:
        return False

    url = url.lower()

    return (
        "dubizzle.com.eg" in url
        and "/companies/" in url
    )


def _extract_active_ads(text):
    """
    Extract the real 'Active ads' count from a Dubizzle company page.
    """

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
    """
    Open Dubizzle company page and extract:
    - company name
    - active ads
    - verified status
    """

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

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

        verified = (
            "Verified Business" in text
            or "Verified business" in text
        )

        return {
            "name": title,
            "listing_count": active_ads,
            "verified": verified,
            "url": url,
        }

    except Exception:
        return None


def _find_company_page(dealer_name, district=""):
    """
    Find the actual Dubizzle company page.
    """

    searches = []

    clean_name = dealer_name.strip()

    if district:
        searches.append(
            f'site:dubizzle.com.eg/en/companies/ "{clean_name}" "{district}"'
        )

    searches.append(
        f'site:dubizzle.com.eg/en/companies/ "{clean_name}"'
    )

    searches.append(
        f'site:dubizzle.com.eg/en/companies/ {clean_name} Egypt'
    )

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


def get_dubizzle_status(dealer_name, district=""):
    """
    Return verified Dubizzle information for a dealer.

    Important:
    - listing_count is ONLY taken from the actual Dubizzle
      company page.
    - Search-engine result counts are never used.
    """

    empty_result = {
        "status": "غير متحقق",
        "listing_count": None,
        "url": "",
        "verified": False,
        "source": "Dubizzle",
    }

    if not dealer_name:
        return empty_result

    page = _find_company_page(
        dealer_name=dealer_name,
        district=district,
    )

    if not page:
        return empty_result

    listing_count = page.get("listing_count")

    return {
        "status": "موجود",
        "listing_count": listing_count,
        "url": page.get("url", ""),
        "verified": page.get("verified", False),
        "source": "Dubizzle",
    }
