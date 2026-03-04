def verify_answer_against_context(gem_client, answer, context_block):
    prompt = f"Verify if the Answer is supported by Context.\nContext: {context_block}\nAnswer: {answer}\nOutput VERDICT: OK or VERDICT: UNSUPPORTED"
    resp = gem_client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=[prompt]
    )
    verdict = "OK" if "VERDICT: OK" in resp.text.upper() else "UNSUPPORTED"
    return resp.text, verdict
