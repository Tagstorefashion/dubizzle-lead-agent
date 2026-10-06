import urllib.parse
import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


def search_contactcars(dealer_name, max_results=10):
    queries = [
        f'"{dealer_name}" site:contactcars.com',
        f'"{dealer_name}" ContactCars Egypt',
    ]

    all_results = []

    for query in queries:

        try:
            url = (
                "https://html.duckduckgo.com/html/?q="
                + urllib.parse.quote(query)
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

                title = title_element.get_text(
                    " ",
                    strip=True
                )

                link = link_element.get(
                    "href",
                    ""
                )

                snippet = ""

                if snippet_element:
                    snippet = snippet_element.get_text(
                        " ",
                        strip=True
                    )

                if link:
                    all_results.append({
                        "title": title,
                        "url": link,
                        "snippet": snippet,
                    })

                if len(all_results) >= max_results:
                    break

        except Exception:
            continue

        if len(all_results) >= max_results:
            break

    # Remove duplicate URLs
    unique_results = {}

    for result in all_results:
        url = result.get("url", "")

        if url:
            unique_results[url] = result

    return list(unique_results.values())


def get_contactcars_status(dealer_name):
    results = search_contactcars(
        dealer_name,
        max_results=10
    )

    if results:

        return {
            "status": "نعم",
            "listing_count": len(results),
            "url": results[0].get(
                "url",
                ""
            ),
            "results": results,
        }

    return {
        "status": "غير متحقق",
        "listing_count": 0,
        "url": "",
        "results": [],
    }
