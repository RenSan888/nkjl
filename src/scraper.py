import requests
from bs4 import BeautifulSoup


def extract_menu_items_from_html(url, gem_client):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return []

        soup = BeautifulSoup(response.text, "html.parser")
        menu_items = []

        # Logic for 'chooseBar' and 'MenuWithPrice' tables goes here...
        # 1) Custom div structure
        blocks = soup.find_all("div", class_="chooseBar")
        for block in blocks:
            name = block.get("data-food")
            price = block.get("data-price")
            if name and price:
                clean_price = f"${price}" if "$" not in price else price
                menu_items.append({"item": name, "price": clean_price})

        # 2) Table structure used by MenuWithPrice
        if not menu_items:
            rows = soup.find_all(
                "tr",
                class_=lambda x: x and ("tr-0" in x or "tr-1" in x),
            )
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    name_tag = cols[0].find("span", class_="prc-food-new")
                    price_tag = cols[2]
                    if name_tag and price_tag:
                        name = name_tag.get_text(strip=True)
                        price = price_tag.get_text(strip=True)
                        if name and price:
                            menu_items.append({"item": name, "price": price})

        # Fallback to Gemini if list is empty
        if not menu_items:
            clean_text = soup.get_text(separator="\n", strip=True)[:12000]
            extraction = gem_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=[f"Extract menu items as 'Item: Price' from:\n{clean_text}"]
            )
            # Parse extraction.text into menu_items list...

        return menu_items
    except Exception as e:
        print(f"Scrape Error: {e}")
        return []
