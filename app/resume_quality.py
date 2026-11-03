"""Resume-quality checks based on document evidence, separate from job similarity."""
import re
from collections import Counter

ACTION_VERBS = {
    "built", "created", "developed", "designed", "delivered", "launched", "led", "managed",
    "improved", "reduced", "increased", "automated", "implemented", "analyzed", "owned",
    "coordinated", "negotiated", "resolved", "trained", "optimized", "wrote", "published",
}
VAGUE_PHRASES = ("responsible for", "worked on", "helped with", "duties included", "involved in", "assisted with")
SECTION_PATTERNS = {
    "Summary": r"\b(summary|profile|objective)\b",
    "Experience": r"\b(experience|employment|internship)\b",
    "Projects": r"\bprojects?\b",
    "Education": r"\beducation\b",
    "Skills": r"\bskills\b",
    "Certifications": r"\b(certifications?|certificates?)\b",
}

def analyze_resume_quality(text: str) -> dict:
    lines = [" ".join(line.strip(" •-*\t").split()) for line in text.splitlines()]
    bullets = [line for line in lines if len(line) >= 30 and not re.match(r"^(summary|experience|education|skills|projects|certifications?)\b", line, re.I)]
    action_bullets = [line for line in bullets if re.match(r"(?:" + "|".join(sorted(ACTION_VERBS, key=len, reverse=True)) + r")\b", line, re.I)]
    vague_bullets = [line for line in bullets if any(phrase in line.lower() for phrase in VAGUE_PHRASES)]
    measurable = [line for line in bullets if re.search(r"\b\d+(?:\.\d+)?\s?(?:%|percent|users?\b|clients?\b|customers?\b|projects?\b|members?\b|requests?\b|hours?\b|days?\b|weeks?\b|months?\b|years?\b)|\$\s?\d+|₹\s?\d+", line, re.I)]
    sections = {name: bool(re.search(pattern, text, re.I)) for name, pattern in SECTION_PATTERNS.items()}
    email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
    phone = bool(re.search(r"(?:\+?\d[\d ().-]{7,}\d)", text))
    dates = re.findall(r"\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}\b", text, re.I)
    section_score = sum(sections.values()) / len(sections) * 100
    impact_score = min(100, len(measurable) / max(2, min(6, len(bullets) or 2)) * 100)
    action_score = min(100, len(action_bullets) / max(2, min(6, len(bullets) or 2)) * 100)
    contact_score = (email + phone) * 50
    timeline_score = min(100, len(dates) * 20)
    duplicate_count = sum(n - 1 for n in Counter(line.lower() for line in bullets).values() if n > 1)
    metrics = [
        {"label": "Section coverage", "score": round(section_score), "explanation": "Checks for clear resume sections."},
        {"label": "Evidence of impact", "score": round(impact_score), "explanation": "Looks for measurable outcomes in experience or project bullets."},
        {"label": "Specific action verbs", "score": round(action_score), "explanation": "Checks whether bullets describe concrete actions."},
        {"label": "Timeline clarity", "score": round(timeline_score), "explanation": "Looks for dates that help a reader follow your history."},
        {"label": "Contact details", "score": round(contact_score), "explanation": "Checks whether an email address and phone number are selectable in the PDF."},
    ]
    quality = round(section_score * .20 + impact_score * .25 + action_score * .20 + timeline_score * .15 + contact_score * .10 + max(0, 100 - duplicate_count * 30) * .10)
    strengths, improvements = [], []
    if measurable: strengths.append(f"Found measurable outcomes in {len(measurable)} bullet(s).")
    else: improvements.append("No measurable outcomes were detected in the bullets.")
    if vague_bullets: improvements.append(f"Found {len(vague_bullets)} vague bullet(s), such as ‘worked on’ or ‘responsible for’.")
    if duplicate_count: improvements.append(f"Found {duplicate_count} repeated experience or project bullet(s).")
    missing_sections = [name for name, found in sections.items() if not found]
    if missing_sections: improvements.append("No clear heading detected for: " + ", ".join(missing_sections) + ".")
    if not email or not phone: improvements.append("Check that both an email address and a phone number are visible in the PDF.")
    if not dates: improvements.append("No dates were detected in the selectable PDF text.")
    return {"score": quality, "breakdown": metrics, "sections": sections,
            "evidence": {"bullet_count": len(bullets), "action_bullets": len(action_bullets), "measurable_bullets": len(measurable), "vague_bullets": len(vague_bullets), "duplicate_bullets": duplicate_count, "dates_found": len(dates), "email_found": email, "phone_found": phone},
            "strengths": strengths, "improvements": improvements}
