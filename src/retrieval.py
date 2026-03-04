from embedchain import App

def setup_rag_app():
    config = {
        "llm": {"provider": "openai", "config": {"model": "gpt-4o", "temperature": 0.1}},
        "embedder": {"provider": "google", "config": {"model": "models/gemini-embedding-001"}},
        "vectordb": {"provider": "chroma", "config": {"dir": "menubuddy_db", "allow_reset": True}},
    }
    return App.from_config(config=config)

def retrieve_menu_context(app, question, num_documents=5):
    results = app.search(question, num_documents=num_documents)
    contexts = []
    for idx, res in enumerate(results, start=1):
        contexts.append({
            "id": idx,
            "text": res.get("context", ""),
            "source": res.get("metadata", {}).get("source", "unknown")
        })
    return contexts
