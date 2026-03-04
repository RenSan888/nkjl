import os
import PIL.Image
from flask import Flask, render_template, request, jsonify
import google.genai as genai
from dotenv import load_dotenv
from src.scraper import extract_menu_items_from_html
from src.retrieval import setup_rag_app, retrieve_menu_context
from src.citation_formatter import build_context_block
from src.generator import generate_grounded_answer
from src.validator import verify_answer_against_context

load_dotenv()

app = Flask(__name__)
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
app_rag = setup_rag_app()

# -------------------- ROUTES --------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/import_menu", methods=["POST"])
def import_menu():
    try:
        if "url" in request.json:
            url = request.json["url"]
            menu_items = extract_menu_items_from_html(url, client)
            if not menu_items:
                return jsonify({"message": "No items found at that URL."}), 400

            formatted = "\n".join([f"{m['item']} - {m['price']}" for m in menu_items])
            app_rag.add(formatted, data_type="text", metadata={"source": url})

            return jsonify({"message": "Menu added successfully.", "items": len(menu_items)})

        elif "image" in request.files or request.files.get("image"):
            img_file = request.files.get("image")
            img = PIL.Image.open(img_file)

            vision_resp = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=["Extract menu items and prices. Format: Item: Price.", img],
            )
            app_rag.add(vision_resp.text, data_type="text", metadata={"source": img_file.filename})

            return jsonify({"message": "Image menu added successfully."})

        else:
            return jsonify({"message": "No URL or image provided."}), 400

    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500


@app.route("/ask_menu", methods=["POST"])
def ask_menu():
    try:
        question = request.json.get("question", "").strip()
        if not question:
            return jsonify({"message": "No question provided."}), 400

        # --- RETRIEVE CONTEXT ---
        contexts = retrieve_menu_context(app_rag, question)
        context_block = build_context_block(contexts)

        # --- GENERATE ANSWER ---
        answer = generate_grounded_answer(client, question, context_block)

        # --- VALIDATE ANSWER ---
        _, verdict = verify_answer_against_context(client, answer, context_block)

        response = {
            "answer": answer,
            "verification": verdict
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
