"""Conservative intent hints; retain the original question for generation."""
import re
import unicodedata


def understand_query(question, previous_question="", previous_answer=""):
    original = question.strip()
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", original))
    lowered = normalized.casefold()
    if re.search(r"[\u0900-\u097f]", original):
        language = "Marathi" if re.search(r"मराठी|आहे|काय|मध्ये|सांगा|याचा|पान|करा", original) else "Hindi / Devanagari"
    elif re.search(r"\b(kya|hai|hain|bhai|iska|isme|samjha|batao|mein|likha|hindi|kaise|mujhe)\b", lowered):
        language = "Hinglish"
    else:
        language = "Auto / English"
    page_match = re.search(r"(?:\bpage\s*|पृष्ठ\s*|पान\s*)(\d{1,5})", lowered.translate(str.maketrans("०१२३४५६७८९", "0123456789")))
    page = int(page_match.group(1)) if page_match else None
    summary = bool(re.search(r"\b(summary|summarize|summarise|overview)\b|सारांश|संक्षेप|kya likha|main objective|main ideas|key points|primary topic|main purpose|मुख्य उद्देश|मुख्य उद्देश्य", lowered))
    variants = [normalized]
    # Response-language instructions can swamp short factual questions. Embed
    # the factual question as an additional variant, while keeping every original
    # word for the model. Never discard a second factual question.
    parts = re.split(r"(?<=[?।])\s+", normalized, maxsplit=1)
    if len(parts) == 2 and re.search(r"hinglish|hindi|english|marathi|हिंदी|हिन्दी|मराठी|मराठीत", parts[1], re.I) and re.search(r"answer|reply|respond|jawab|उत्तर|जवाब", parts[1], re.I):
        variants.insert(0, parts[0])
    if summary:
        variants.append("Main objective, purpose, overview and key findings of this document")
    elif re.search(r"easy language|simple|samjha|explain|समझा|समजाव", lowered):
        variants.append(normalized + " explanation definition")
    follow_up = bool(re.search(r"\b(it|that|this concept|its|they|these|iska|ye|uska|aur)\b|याचा|त्याचे|इसे|उसका", lowered))
    context = ""
    if follow_up and previous_question:
        context = f"{previous_question[:500]}\n{previous_answer[:700]}"
        variants.append(f"{context}\nFollow-up: {normalized}")
    return {"original": original, "normalized": normalized, "language_hint": language,
            "page": page, "summary": summary, "variants": list(dict.fromkeys(variants)), "followup_context": context}
