import os
import requests
import PIL.Image
from bs4 import BeautifulSoup
import google.genai as genai
from embedchain import App
from flask import Flask, request, jsonify, render_template

# ---------------------------------------------------
# API KEYS
# ---------------------------------------------------
os.environ["OPENAI_API_KEY"] = "key"
os.environ["GOOGLE_API_KEY"] = "key"

# ---------------------------------------------------
# FLASK APP INIT
# ---------------------------------------------------
app_flask = Flask(__name__)


# ---------------------------------------------------
# HTML Extraction
# ---------------------------------------------------

def extract_menu_items_from_html(url, gem_client):
    """
    1) Try to parse menu/price directly from HTML
    2) If parsing fails, fall back to Gemini extraction
    """
    print(f"\n[PARSING] Accessing: {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[ERROR] Site returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        menu_items = []

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

        # 3) Fallback: Gemini text-based extraction
        if not menu_items:
            print("[INFO] Falling back to Gemini Intelligence...")
            for noise in soup(["script", "style", "nav", "footer", "header", "svg"]):
                noise.decompose()
            clean_text = soup.get_text(separator="\n", strip=True)

            extraction = gem_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=[
                    (
                        "You are extracting menu items from raw HTML text.\n"
                        "Return lines in the format 'Item: Price'.\n"
                        "Do NOT add descriptions.\n\n"
                        f"{clean_text[:12000]}"
                    )
                ],
            )

            if extraction and extraction.text:
                for line in extraction.text.split("\n"):
                    if ":" in line:
                        parts = line.split(":", 1)
                        item = parts[0].strip("- *")
                        price = parts[1].strip()
                        if item and price:
                            menu_items.append({"item": item, "price": price})

        return menu_items

    except Exception as e:
        print(f"[ERROR] Scraper failed: {e}")
        return []


# ---------------------------------------------------
# RETRIEVAL + CITATION
# ---------------------------------------------------

def retrieve_menu_context(app, question, num_documents=5):
    try:
        results = app.search(question, num_documents=num_documents)
    except Exception as e:
        print(f"[ERROR] Retrieval failed: {e}")
        return []

    contexts = []
    for idx, res in enumerate(results, start=1):
        text = res.get("context", "") or ""
        metadata = res.get("metadata", {}) or {}
        source = (
            metadata.get("source")
            or metadata.get("url")
            or metadata.get("data_value")
            or "menu_data"
        )
        if text.strip():
            contexts.append(
                {"id": idx, "text": text.strip(), "source": source}
            )
    return contexts


def build_context_block(contexts):
    lines = []
    for c in contexts:
        lines.append(f"[{c['id']}] {c['text']} (SOURCE: {c['source']})")
    return "\n".join(lines)


def generate_grounded_answer(gem_client, question, context_block):
    prompt = f"""
You are MenuBuddy, a menu question answering assistant.

You are given menu context, each line has an ID.

RULES:
- Use ONLY context to answer.
- If answer is not in context, say: "I don't know based on the menu data."
- Every factual claim must include a citation [ID].
- Do NOT invent menu items or prices.

Menu context:
{context_block}

User question:
{question}

Provide a concise answer with citations.
    """.strip()

    resp = gem_client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=[prompt],
    )
    return (resp.text or "").strip()


def verify_answer_against_context(gem_client, answer, context_block):
    prompt = f"""
You are a strict fact-checking assistant.

Context:
{context_block}

Answer:
{answer}

Tasks:
1. Identify unsupported claims.
2. If all claims are supported, say so.
3. Output exactly one final line:
   VERDICT: OK
   or
   VERDICT: UNSUPPORTED
    """

    resp = gem_client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=[prompt],
    )
    full_text = (resp.text or "").strip()

    verdict_line = "VERDICT: UNKNOWN"
    for line in reversed([l.strip() for l in full_text.splitlines() if l.strip()]):
        if line.upper().startswith("VERDICT:"):
            verdict_line = line.upper()
            break

    return full_text, verdict_line


# ---------------------------------------------------
# MAIN RAG FUNCTION
# ---------------------------------------------------

def menubuddy_basic_rag():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[ERROR] GOOGLE_API_KEY environment variable not set.")
        return

    gem_client = genai.Client(api_key=api_key)

    config = {
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-4o", "temperature": 0.1},
        },
        "embedder": {
            "provider": "google",
            "config": {"model": "models/gemini-embedding-001"},
        },
        "vectordb": {
            "provider": "chroma",
            "config": {"dir": "menubuddy_basic_db", "allow_reset": True},
        },
    }

    app = App.from_config(config=config)

    print("\n=== MenuBuddy Basic RAG (Grounded + Fact-Checked) ===")
    mode = input("Import menu (1=URL, 2=Image): ").strip()

    if mode == "1":
        url = input("Enter menu URL: ").strip()
        if not url:
            print("[ERROR] Empty URL.")
            return

        menu_items = extract_menu_items_from_html(url, gem_client)

        if menu_items:
            print(f"\n[OK] Extracted {len(menu_items)} items.")
            formatted = "\n".join([f"{m['item']} - {m['price']}" for m in menu_items])

            app.add(
                formatted,
                data_type="text",
                metadata={"source": url, "type": "menu_text"},
            )
            print("\n[SUCCESS] Menu added to vector DB.")
        else:
            print("\n[!] No menu items extracted.")
            return

    elif mode == "2":
        path = input("Enter image path: ").strip()
        try:
            img = PIL.Image.open(path)
            vision_resp = gem_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=[
                    "Extract menu items and prices. Format: Item: Price.",
                    img,
                ],
            )
            vision_text = (vision_resp.text or "").strip()
            if not vision_text:
                print("[ERROR] Empty vision output.")
                return

            app.add(
                vision_text,
                data_type="text",
                metadata={"source": path, "type": "menu_image_ocr"},
            )
            print("\n[OK] Image menu added to vector DB.")
        except Exception as e:
            print(f"[ERROR] Vision extraction failed: {e}")
            return

    else:
        print("[ERROR] Invalid mode.")
        return

    print("\nYou can now ask questions about the menu.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        q = input("Ask about the menu: ").strip()
        if q.lower() in ["exit", "quit"]:
            break
        if not q:
            continue

        contexts = retrieve_menu_context(app, q, num_documents=5)
        if not contexts:
            print("\n[INFO] No context found.")
            continue

        context_block = build_context_block(contexts)
        answer = generate_grounded_answer(gem_client, q, context_block)
        verification_text, verdict = verify_answer_against_context(
            gem_client, answer, context_block
        )

        print("\n---------------- MENU BUDDY ANSWER ----------------")
        print(answer)
        print("---------------------------------------------------")
        print(f"[Verification] {verdict}\n")


# ---------------------------------------------------
# FLASK API ENDPOINTS FOR WEB UI
# ---------------------------------------------------

# LINK http://127.0.0.1:5000/ui
@app_flask.route("/ui")
def ui():
    return render_template("index.html")

config = {
    "llm": {
        "provider": "openai",
        "config": {"model": "gpt-4o", "temperature": 0.1},
    },
    "embedder": {
        "provider": "google",
        "config": {"model": "models/gemini-embedding-001"},
    },
    "vectordb": {
        "provider": "chroma",
        "config": {"dir": "menubuddy_basic_db", "allow_reset": True},
    },
}

@app_flask.route("/import_menu", methods=["POST"])
def import_menu():
    gem_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    app = App.from_config(config=config)

    # JSON payload for URL
    if request.is_json:
        data = request.get_json()
        url = data.get("url")
        if url:
            menu_items = extract_menu_items_from_html(url, gem_client)
            if menu_items:
                formatted = "\n".join([f"{m['item']} - {m['price']}" for m in menu_items])
                app.add(formatted, data_type="text", metadata={"source": url, "type": "menu_text"})
                return jsonify({"status": "success", "items": len(menu_items)})
            return jsonify({"status": "error", "message": "No menu items found"}), 400

    # Multipart form for image
    if "image" in request.files:
        file = request.files["image"]
        try:
            img = PIL.Image.open(file)
            vision_resp = gem_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=["Extract menu items and prices. Format: Item: Price.", img],
            )
            vision_text = (vision_resp.text or "").strip()
            if vision_text:
                app.add(vision_text, data_type="text", metadata={"source": file.filename, "type": "menu_image_ocr"})
                return jsonify({"status": "success", "message": "Menu image added"})
            return jsonify({"status": "error", "message": "Failed to extract menu from image"}), 400
        except Exception as e:
            return jsonify({"status": "error", "message": f"Vision extraction failed: {e}"}), 500

    return jsonify({"status": "error", "message": "No valid input provided"}), 400


@app_flask.route("/ask_menu", methods=["POST"])
def ask_menu():
    gem_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    app = App.from_config(config=config)

    data = request.get_json()
    question = data.get("question")
    if not question:
        return jsonify({"status": "error", "message": "No question provided"}), 400

    contexts = retrieve_menu_context(app, question, num_documents=5)
    if not contexts:
        return jsonify({"status": "empty", "message": "No context found"}), 200

    context_block = build_context_block(contexts)
    answer = generate_grounded_answer(gem_client, question, context_block)
    _, verdict = verify_answer_against_context(gem_client, answer, context_block)

    return jsonify({"status": "success", "answer": answer, "verification": verdict})

# ---------------------------------------------------
# RUN FLASK
# ---------------------------------------------------

if __name__ == "__main__":
    app_flask.run(debug=True)
