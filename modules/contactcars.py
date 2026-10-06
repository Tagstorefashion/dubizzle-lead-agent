import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import quote


CONTACTCARS_BASE = "https://www.contactcars.com"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def search_contactcars_dealer(dealer_name, area=""):
    """
    البحث عن معرض معين على ContactCars.

    لا نعتبر المعرض موجوداً إلا إذا وجدنا
    نتائج مرتبطة بالاسم.
    """

    queries = [
        f'"{dealer_name}" site:contactcars.com',
        f'"{dealer_name}" ContactCars',
    ]

    results = []

    for query in queries:

        try:

            url = (
                "https://html.duckduckgo.com/html/?q="
                + quote(query)
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=15
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for result in soup.select(".result"):

                title_element = result.select_one(
                    ".result__title"
                )

                link_element = result.select_one(
                    ".result__a"
                )

                snippet_element = result.select_one(
                    ".result__snippet"
                )

                if not title_element or not link_element:
                    continue

                title = clean_text(
                    title_element.get_text(" ")
                )

                link = link_element.get(
                    "href",
                    ""
                )

                snippet = ""

                if snippet_element:
                    snippet = clean_text(
                        snippet_element.get_text(" ")
                    )

                combined_text = (
                    f"{title} {snippet}"
                ).lower()

                dealer_words = [
                    word.lower()
                    for word in dealer_name.split()
                    if len(word) >= 3
                ]

                matched_words = 0

                for word in dealer_words:

                    if word in combined_text:
                        matched_words += 1

                if dealer_words:

                    match_ratio = (
                        matched_words /
                        len(dealer_words)
                    )

                else:

                    match_ratio = 0

                # لازم يكون فيه تطابق واضح
                if match_ratio < 0.5:
                    continue

                results.append({
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                    "match_ratio": round(
                        match_ratio,
                        2
                    )
                })

        except Exception:
            continue

    # إزالة النتائج المكررة

    unique_results = {}

    for result in results:

        url = result["url"]

        if url and url not in unique_results:
            unique_results[url] = result

    return list(
        unique_results.values()
    )


def get_contactcars_status(
    dealer_name,
    area=""
):
    """
    التحقق من وجود المعرض على ContactCars.
    """

    results = search_contactcars_dealer(
        dealer_name,
        area
    )

    if not results:

        return {
            "exists": False,
            "listing_count": 0,
            "monthly_activity": None,
            "last_activity": None,
            "results": [],
            "status": "غير متحقق"
        }

    return {
        "exists": True,
        "listing_count": len(results),
        "monthly_activity": None,
        "last_activity": None,
        "results": results,
        "status": "تم العثور على نتائج"
    }
