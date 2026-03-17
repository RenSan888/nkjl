from flask import Flask, request, jsonify, render_template
import os
import PIL.Image
import google.genai as genai
from dotenv import load_dotenv

# Your modules (UNCHANGED)
from src.scraper import extract_menu_items_from_html
from src.retrieval import setup_rag_app, retrieve_menu_context
from src.citation_formatter import build_context_block
from src.generator import generate_grounded_answer
from src.validator import verify_answer_against_context

# INIT
load_dotenv()
app = Flask(__name__)

client = genai.Client(api_key=os.getenv("key"))
rag_app = setup_rag_app()

# -------------------- FRONTEND --------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------- IMPORT MENU (URL OR IMAGE) --------------------
@app.route("/import_menu", methods=["POST"])
def import_menu():
    try:
        # CASE 1: URL
        if request.is_json:
            data = request.get_json()
            url = data.get("url")

            menu_items = extract_menu_items_from_html(url, client)

            if not menu_items:
                return jsonify({"message": "No items found"}), 400

            formatted = "\n".join([f"{m['item']} - {m['price']}" for m in menu_items])
            rag_app.add(formatted, data_type="text", metadata={"source": url})

            return jsonify({
                "message": "Menu imported successfully",
                "items": len(menu_items)
            })

        # CASE 2: IMAGE
        if "image" in request.files:
            file = request.files["image"]
            img = PIL.Image.open(file)

            vision_resp = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=["Extract menu items and prices. Format: Item: Price.", img],
            )

            rag_app.add(vision_resp.text, data_type="text", metadata={"source": "image"})

            return jsonify({
                "message": "Image processed successfully"
            })

        return jsonify({"message": "Invalid input"}), 400

    except Exception as e:
        return jsonify({"message": str(e)}), 500


# -------------------- ASK QUESTION --------------------
@app.route("/ask_menu", methods=["POST"])
def ask_menu():
    try:
        data = request.get_json()
        query = data.get("question")

        contexts = retrieve_menu_context(rag_app, query)
        context_block = build_context_block(contexts)

        answer = generate_grounded_answer(client, query, context_block)
        _, verdict = verify_answer_against_context(client, answer, context_block)

        return jsonify({
            "answer": answer if verdict != "UNSUPPORTED" else "Could not verify answer.",
            "verification": verdict
        })

    except Exception as e:
        return jsonify({"message": str(e)}), 500


# RUN
if __name__ == "__main__":
    app.run(debug=True)
