import os
import requests
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
import PIL.Image
import google.genai as genai
from embedchain import App

# ---------------------------------------------------
# API
# ---------------------------------------------------
os.environ["OPENAI_API_KEY"] = "KEY"
# os.environ["GOOGLE_API_KEY"] = "KEY"

# ---------------------------------------------------
# FLASK SETUP
# ---------------------------------------------------
app_flask = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------
# INIT GEMINI + RAG
# ---------------------------------------------------
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

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
        "config": {"dir": "menubuddy_basic_db"},
    },
}

rag_app = App.from_config(config=config)

# ---------------------------------------------------
# HTML MENU SCRAPER
# ---------------------------------------------------
def extract_menu_items_from_html(url, gem_client):

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
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        menu_items = []

        # Method 1
        blocks = soup.find_all("div", class_="chooseBar")
        for block in blocks:
            name = block.get("data-food")
            price = block.get("data-price")
            if name and price:
                clean_price = f"${price}" if "$" not in price else price
                menu_items.append({"item": name, "price": clean_price})

        # Method 2
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

        # Gemini fallback
        if not menu_items:

            for noise in soup(["script", "style", "nav", "footer"]):
                noise.decompose()

            clean_text = soup.get_text(separator="\n", strip=True)

            extraction = gem_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "Extract menu items. Return format 'Item: Price'.\n\n"
                    + clean_text[:12000]
                ],
            )

            if extraction and extraction.text:
                for line in extraction.text.split("\n"):
                    if ":" in line:
                        item, price = line.split(":", 1)
                        menu_items.append({
                            "item": item.strip(),
                            "price": price.strip()
                        })

        return menu_items

    except Exception:
        return []

# ---------------------------------------------------
# RETRIEVAL
# ---------------------------------------------------
def retrieve_menu_context(app, question, num_documents=5):

    try:
        results = app.search(question, num_documents=num_documents)
    except Exception:
        return []

    contexts = []

    for idx, res in enumerate(results, start=1):
        text = res.get("context", "") or ""
        metadata = res.get("metadata", {}) or {}

        source = (
            metadata.get("source")
            or metadata.get("url")
            or "menu_data"
        )

        if text.strip():
            contexts.append({
                "id": idx,
                "text": text.strip(),
                "source": source
            })

    return contexts

# ---------------------------------------------------
# CONTEXT BUILDER
# ---------------------------------------------------
def build_context_block(contexts):
    return "\n".join(
        [f"[{c['id']}] {c['text']} (SOURCE: {c['source']})" for c in contexts]
    )

# ---------------------------------------------------
# GENERATION
# ---------------------------------------------------
def generate_grounded_answer(gem_client, question, context_block):

    prompt = f"""
You are MenuBuddy.

Use ONLY the context below.

Context:
{context_block}

Question:
{question}

Cite sources like [1].
"""

    resp = gem_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return (resp.text or "").strip()

# ---------------------------------------------------
# VERIFICATION
# ---------------------------------------------------
def verify_answer_against_context(gem_client, answer, context_block):

    prompt = f"""
You are a strict fact-checking assistant.

Context:
{context_block}

Answer:
{answer}

Check if every claim is supported.

Output:
VERDICT: OK
or
VERDICT: UNSUPPORTED
"""

    resp = gem_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return (resp.text or "").strip()

# ---------------------------------------------------
# ROUTES
# ---------------------------------------------------
@app_flask.route("/")
def index():
    return render_template("index.html")

# ---------------- IMPORT MENU ----------------
@app_flask.route("/import_menu", methods=["POST"])
def import_menu():

    # URL INPUT
    if request.is_json:
        data = request.get_json()
        url = data.get("url")

        if not url:
            return jsonify({"message": "No URL provided"}), 400

        menu_items = extract_menu_items_from_html(url, client)

        if not menu_items:
            return jsonify({"message": "No menu items found"}), 400

        formatted = "\n".join(
            [f"{m['item']} - {m['price']}" for m in menu_items]
        )

        rag_app.add(
            formatted,
            data_type="text",
            metadata={"source": url},
        )

        return jsonify({
            "message": "Menu added",
            "items": len(menu_items)
        })

    # IMAGE INPUT
    if "image" in request.files:

        file = request.files["image"]

        if file.filename == "":
            return jsonify({"message": "No file"}), 400

        filename = secure_filename(file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)

        try:
            img = PIL.Image.open(path)

            vision_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "Extract menu items and prices. Format: Item: Price.",
                    img
                ]
            )

            vision_text = (vision_resp.text or "").strip()

            if not vision_text:
                return jsonify({"message": "Extraction failed"}), 400

            rag_app.add(
                vision_text,
                data_type="text",
                metadata={"source": path},
            )

            return jsonify({"message": "Image menu added"})

        except Exception as e:
            return jsonify({"message": str(e)}), 500

    return jsonify({"message": "Invalid request"}), 400

# ---------------- ASK QUESTION ----------------
@app_flask.route("/ask_menu", methods=["POST"])
def ask_menu():

    data = request.get_json()
    question = data.get("question")

    if not question:
        return jsonify({"message": "No question"}), 400

    contexts = retrieve_menu_context(rag_app, question)

    if not contexts:
        return jsonify({"message": "No context found"}), 404

    context_block = build_context_block(contexts)

    answer = generate_grounded_answer(client, question, context_block)

    verification = verify_answer_against_context(
        client,
        answer,
        context_block
    )

    return jsonify({
        "answer": answer,
        "verification": verification
    })

# ---------------------------------------------------
# RUN
# ---------------------------------------------------
if __name__ == "__main__":
    app_flask.run(debug=True)
