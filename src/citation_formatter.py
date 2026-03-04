def build_context_block(contexts):
    """Formats retrieved documents into a numbered list for the LLM."""
    lines = [f"[{c['id']}] {c['text']} (SOURCE: {c['source']})" for c in contexts]
    return "\n".join(lines)
