def generate_grounded_answer(gem_client, question, context_block):
    prompt = f"""
    You are MenuBuddy. Use ONLY the context below. 
    Every claim MUST have a citation [ID].
    Context: {context_block}
    Question: {question}
    """
    resp = gem_client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=[prompt]
    )
    return resp.text.strip()
