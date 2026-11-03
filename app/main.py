"""FastAPI service for private, in-memory resume analysis."""
from __future__ import annotations

import io
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from wordfreq import zipf_frequency

from .feedback import generate_recommendations, _years_covered
from .interview import generate_interview_questions
from .job_safety import analyze_job_safety

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = json.loads((ROOT / "app" / "skills_taxonomy.json").read_text(encoding="utf-8"))
SKILL_MAP: dict[str, dict[str, str]] = {}
for category, names in TAXONOMY["categories"].items():
    if isinstance(names, str):
        names = [name.strip() for name in names.split(",")]
    for name in names:
        SKILL_MAP[name.lower()] = {"name": name, "category": category}
for canonical, aliases in TAXONOMY.get("aliases", {}).items():
    if canonical.lower() in SKILL_MAP:
        for alias in aliases:
            SKILL_MAP[alias.lower()] = SKILL_MAP[canonical.lower()]

# spaCy's current dependency chain does not build cleanly on Python 3.15.
# Resume section and skill extraction use explicit rules, so NER stays optional.
NLP = None
SPACY_MODEL_LOADED = False

load_dotenv(ROOT / ".env")
app = FastAPI(title="AI Resume Analyzer", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_BYTES = 5 * 1024 * 1024
STOP_WORDS = set("a an the and or of to in for with on at by from as is are be this that will you your we our their it its i they them who what when where which while how work working team teams ability strong skills skill years year etc including preferred required plus role job candidate must have has can able good great new using use based across within into such other more also any all not looking join company position responsibilities requirements qualifications hiring manage seeking opportunity knowledge understanding familiarity well need needs ensure support help make develop".split())
LOREM = {"lorem", "ipsum", "dolor", "consectetur", "adipiscing", "elit"}
SIGNAL_WORDS = {
    "responsibility": ("responsibilit", "duties", "accountabilities"),
    "qualification": ("qualifications", "qualification", "requirements", "required", "must have"),
    "experience": ("experience", "years", "background", "proven track record"),
    "role": ("role", "position", "candidate", "job title"),
    "action": ("develop", "build", "design", "manage", "lead", "analyze", "implement", "maintain", "deliver", "collaborate", "create", "support", "own", "drive"),
}
ACTION_VERBS = {"achieved", "analyzed", "automated", "built", "created", "delivered", "designed", "developed", "drove", "generated", "improved", "implemented", "increased", "launched", "led", "managed", "optimized", "owned", "reduced", "resolved", "scaled", "shipped", "streamlined", "trained", "wrote"}
SECTION_PATTERNS = {
    "Summary / Objective": r"\b(summary|professional profile|objective|profile)\b",
    "Experience": r"\b(experience|employment|work history|internship)\b",
    "Education": r"\beducation\b",
    "Skills": r"\b(technical skills|core competencies|skills)\b",
    "Projects": r"\bprojects?\b",
    "Certifications": r"\b(certifications?|certificates?)\b",
}
SECTION_NAMES = {
    "Summary / Objective": "summary", "Experience": "experience", "Education": "education",
    "Skills": "skills", "Projects": "projects", "Certifications": "certifications",
}
HEADING_RE = re.compile(r"(?im)^\s*(summary|professional profile|objective|profile|experience|employment|work history|internship|education|technical skills|core competencies|skills|projects?|certifications?|certificates?)\s*:?[ \t]*$")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z+#./'-]*", text)


def extract_skill_hits(text: str) -> list[dict[str, str]]:
    hits: dict[str, dict[str, str]] = {}
    low = text.lower()
    for alias, info in SKILL_MAP.items():
        if re.search(rf"(?<![\w+#]){re.escape(alias)}(?![\w+#])", low):
            hits[info["name"]] = {"name": info["name"], "category": info["category"]}
    return sorted(hits.values(), key=lambda x: x["name"].lower())


def validate_job_description(text: str) -> None:
    words = tokenize(text)
    if len(words) < 80:
        raise HTTPException(422, f"Your job description has {len(words)} words. Paste at least 80 words, including responsibilities and qualifications.")
    lower = text.lower()
    lorem_hits = sorted(LOREM.intersection(re.findall(r"[a-z]+", lower)))
    if lorem_hits:
        raise HTTPException(422, "This looks like placeholder text (Lorem ipsum). Paste the actual job posting instead.")
    if re.search(r"(.)\1{5,}", text, re.I):
        raise HTTPException(422, "Some text contains repeated characters (for example, 'aaaaaa'). Replace it with readable job-posting text.")

    normalized = [w.lower().strip("'./-") for w in words]
    content_words = [w for w in normalized if w not in STOP_WORDS and len(w) > 2]
    if content_words:
        counts = Counter(content_words)
        if counts.most_common(1)[0][1] / len(content_words) > 0.12 or sum(n for _, n in counts.most_common(3)) / len(content_words) > 0.30:
            raise HTTPException(422, "This text repeats the same words too often. Paste a complete, readable job description.")

    # Dictionary quality check, with exemptions for acronyms and curated technical terms.
    valid = 0
    for original, word in zip(words, normalized):
        technical = word in SKILL_MAP or any(alias in SKILL_MAP for alias in (word,))
        acronym = original.isupper() and 2 <= len(original) <= 8
        compound = any(ch.isdigit() for ch in word) or "-" in word or "/" in word
        dictionary_word = zipf_frequency(word.replace("'", ""), "en") >= 2.0
        valid += bool(technical or acronym or compound or dictionary_word)
    valid_ratio = valid / max(len(words), 1)
    if valid_ratio < 0.60:
        raise HTTPException(422, f"Only {valid_ratio:.0%} of the words look like readable English or recognized technical terms. Check for typos or gibberish, then paste the job posting again.")

    signal_count = sum(any(term in lower for term in variants) for variants in SIGNAL_WORDS.values())
    skill_count = len(extract_skill_hits(text))
    if signal_count + min(skill_count, 2) < 3:
        raise HTTPException(422, "I couldn't find enough job-related information. Include responsibilities, qualifications, experience, and role-specific tools or skills.")
    if skill_count < 2:
        raise HTTPException(422, "I couldn't identify at least two role-specific skills or technologies. Include the tools, methods, or core competencies the role asks for.")


def extract_resume(file_bytes: bytes, extension: str) -> tuple[str, int | None]:
    if extension == ".pdf":
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages), len(pdf.pages)
    document = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        paragraphs.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
    return "\n".join(paragraphs), None


def detect_sections(text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    sections: dict[str, str] = {}
    matches = list(HEADING_RE.finditer(text))
    for i, match in enumerate(matches):
        raw = match.group(1).lower()
        key = next((label for label, pattern in SECTION_PATTERNS.items() if re.search(pattern, raw, re.I)), None)
        if key:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections[key] = text[match.end():end].strip()
    email = next(iter(re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)), None)
    phone_text = re.sub(r"\b(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\b", " ", text)
    phone_candidates = re.findall(r"(?<!\d)\+?\d[\d\s().-]{7,}\d(?!\d)", phone_text)
    phone = next((candidate.strip() for candidate in phone_candidates if 8 <= len(re.sub(r"\D", "", candidate)) <= 15), None)
    links = list(dict.fromkeys(re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com)/[\w./-]+", text, re.I)))
    name = None
    if NLP is not None and NLP.has_pipe("ner"):
        doc = NLP(text[:5000])
        name = next((ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON" and len(ent.text.split()) <= 4), None)
    contact = {"name": name, "email": email, "phone": phone, "links": links}
    sections_present = [{"name": name, "present": name in sections} for name in SECTION_PATTERNS]
    sections_present.insert(0, {"name": "Contact Info", "present": bool(name or email or phone or links)})
    return {"content": sections, "contact": contact}, sections_present


def skill_priority(jd: str, skill: str) -> tuple[str, str, float]:
    sentences = re.split(r"(?<=[.!?])\s+|\n", jd.lower())
    hits = [s for s in sentences if re.search(rf"(?<![\w+#]){re.escape(skill.lower())}(?![\w+#])", s)]
    required = any(re.search(r"\b(required|must|essential|mandatory|proficien\w+|minimum)\b", s) for s in hits)
    preferred = any(re.search(r"\b(preferred|nice to have|bonus|desirable)\b", s) for s in hits)
    occurrences = jd.lower().count(skill.lower())
    priority = "High" if required or (not preferred and (len(hits) >= 3 or occurrences >= 3)) else "Medium" if preferred and (len(hits) > 1 or occurrences > 1) or len(hits) >= 2 or occurrences >= 2 else "Low"
    weight = {"High": 3.0, "Medium": 1.7, "Low": 1.0}[priority]
    reason = "Explicitly required" if required else "Preferred" if preferred else "Repeated in the posting" if len(hits) > 1 else "Mentioned once"
    return priority, reason, weight


def similarity(left: str, right: str) -> float:
    if not left.strip() or not right.strip():
        return 0.0
    try:
        vectors = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit_transform([left, right])
        return float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0])
    except ValueError:
        return 0.0


def action_quality(text: str) -> float:
    lines = [line.strip(" •-*\t") for line in text.splitlines() if 25 <= len(line.strip()) <= 280]
    if not lines:
        return 0.0
    action_count = sum(bool(re.match(r"(?:" + "|".join(ACTION_VERBS) + r")\b", line, re.I)) for line in lines)
    passive_count = sum(bool(re.search(r"\b(responsible for|worked on|helped|assisted with|duties included)\b", line, re.I)) for line in lines)
    return min(1.0, max(0.0, 0.55 * min(action_count / max(3, len(lines) * 0.4), 1) + 0.45 * (1 - passive_count / len(lines))))


def analyze_resume(text: str, jd: str, pages: int | None) -> dict[str, Any]:
    normalized = text.lower()
    parsed, section_status = detect_sections(text)
    resume_skills = extract_skill_hits(text)
    jd_skills = extract_skill_hits(jd)
    priorities = []
    priority_weight = 0.0
    matched_weight = 0.0
    for skill in jd_skills:
        priority, reason, weight = skill_priority(jd, skill["name"])
        present = any(s["name"] == skill["name"] for s in resume_skills)
        priorities.append({**skill, "priority": priority, "reason": reason, "matched": present})
        priority_weight += weight
        if present:
            matched_weight += weight
    priorities.sort(key=lambda x: ({"High": 0, "Medium": 1, "Low": 2}[x["priority"]], x["name"].lower()))
    matched = [item["name"] for item in priorities if item["matched"]]
    missing = [item["name"] for item in priorities if not item["matched"]]

    exp_text = parsed["content"].get("Experience", "") or "\n".join(
        line for line in text.splitlines() if re.search(r"\b(19|20)\d{2}\b", line)
    )
    exp_similarity = similarity(exp_text, jd)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    quantified_lines = sum(bool(re.search(r"\d|%|\$|₹", line)) for line in lines)
    quantified_score = min(1.0, quantified_lines / max(3, len([line for line in lines if len(line) > 30]) * 0.35))
    section_ratio = sum(1 for item in section_status if item["present"]) / len(section_status)
    words = len(tokenize(text))
    if pages is None:
        estimated_pages = max(1, round(words / 500))
        page_label = f"About {estimated_pages} page(s), estimated from word count"
    else:
        estimated_pages = pages
        page_label = f"{pages} page(s) detected"
    length_score = 1.0 if 300 <= words <= 800 else 0.65 if 220 <= words <= 950 else 0.3
    page_score = 1.0 if 1 <= estimated_pages <= 2 else 0.4
    contact_score = 1.0 if any(parsed["contact"].values()) else 0.0
    paragraphs = [line for line in text.splitlines() if len(line.split()) > 80]
    paragraph_score = 0.5 if paragraphs else 1.0
    format_signal = length_score * 4 + page_score * 3 + contact_score * 2 + paragraph_score

    breakdown = [
        {"name": "Structure & sections", "score": round(20 * section_ratio, 1), "max": 20, "explanation": "Coverage of contact details, summary, experience, education, skills, projects, and certifications."},
        {"name": "Priority skill match", "score": round(30 * (matched_weight / priority_weight if priority_weight else 0), 1), "max": 30, "explanation": "Required and repeated skills contribute more than nice-to-have skills."},
        {"name": "Experience relevance", "score": round(20 * exp_similarity, 1), "max": 20, "explanation": "TF-IDF cosine similarity between experience evidence and the job description."},
        {"name": "Quantified achievements", "score": round(10 * quantified_score, 1), "max": 10, "explanation": "Checks how often experience lines show measurable scale or outcomes."},
        {"name": "Action verbs & writing", "score": round(10 * action_quality(text), 1), "max": 10, "explanation": "Rewards clear action-led lines and reduces passive phrasing."},
        {"name": "Formatting & length", "score": round(10 * format_signal / 10, 1), "max": 10, "explanation": f"{words} words · {page_label} · contact details and paragraph length checked."},
    ]
    total = round(sum(item["score"] for item in breakdown))
    verdict = "Excellent alignment" if total >= 80 else "Strong alignment" if total >= 65 else "Developing alignment" if total >= 45 else "More tailoring needed"

    recs = generate_recommendations(text, jd, matched_skills=matched, missing_skills=missing, max_items=7)
    priority_by_skill = {item["name"]: item for item in priorities}
    for rec in recs:
        if rec.get("category") == "Missing skill":
            skill = rec["title"].removeprefix("Add evidence of “").removesuffix("”")
            if skill in priority_by_skill:
                rec["priority"] = priority_by_skill[skill]["priority"]
                rec["job_priority_reason"] = priority_by_skill[skill]["reason"]
    recs.sort(key=lambda rec: {"High": 0, "Medium": 1, "Low": 2}.get(rec["priority"], 3))

    if not re.search(r"\b(summary|objective|profile)\b", normalized):
        recs.append({"priority": "Medium", "category": "Resume structure", "title": "Add a targeted opening summary", "detail": "Add two or three lines that connect your strongest existing experience to this job's top requirements.", "evidence": "No summary or objective section was detected."})
    if not parsed["contact"]["email"]:
        recs.append({"priority": "High", "category": "Contact details", "title": "Add a professional email address", "detail": "Recruiters need a clear way to reach you. Add a professional email near your name at the top of the resume."})
    focus_plan = [dict(item, rank=i + 1, start_here=(i == 0)) for i, item in enumerate(recs[:8])]

    return {
        "score": total, "verdict": verdict, "breakdown": breakdown,
        "skills": {"matched": matched, "missing": missing, "resume_only": [s["name"] for s in resume_skills if s["name"] not in {x["name"] for x in jd_skills}], "priorities": priorities},
        "parsed_resume": {"sections": section_status, "contact": parsed["contact"], "word_count": words, "pages": page_label},
        "experience_similarity": round(exp_similarity * 100), "recommendations": focus_plan,
        "resume_quality": {"score": round(100 * (section_ratio * .45 + action_quality(text) * .25 + quantified_score * .2 + contact_score * .1)), "strengths": [], "improvements": []},
        "job_safety": analyze_job_safety(jd),
        "interview_questions": generate_interview_questions(text, jd, matched, missing),
        "notice": "This is a coaching estimate, not an ATS score or hiring prediction. Only include experience you can verify.",
    }


def claude_recommendations(result: dict[str, Any], jd: str) -> list[dict[str, Any]] | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        prompt = {
            "role": "Give concise, evidence-based resume coaching. Never invent experience or tell the user to claim a missing skill.",
            "job_title_or_description": jd[:8000],
            "score": result["score"],
            "matched_skills": result["skills"]["matched"],
            "missing_prioritized_skills": result["skills"]["priorities"],
            "resume_quality": result["resume_quality"],
            "current_recommendations": result["recommendations"],
            "output": "Return only a JSON array of up to 7 objects with priority, category, title, detail, evidence."
        }
        response = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"), max_tokens=1200, messages=[{"role": "user", "content": json.dumps(prompt)}])
        content = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        parsed = json.loads(re.search(r"\[.*\]", content, re.S).group(0))
        return parsed if isinstance(parsed, list) else None
    except Exception:
        return None


@app.get("/api/health")
def health():
    return {"ok": True, "llm_available": bool(os.getenv("ANTHROPIC_API_KEY")), "spacy_model": "en_core_web_sm" if SPACY_MODEL_LOADED else "optional-disabled"}


@app.post("/api/validate-jd")
def validate_jd_live(job_description: str = Form(...)):
    try:
        validate_job_description(job_description)
        return {"valid": True, "message": "Looks like a complete job description."}
    except HTTPException as exc:
        return {"valid": False, "message": exc.detail}


@app.post("/api/analyze")
async def analyze(resume: UploadFile = File(...), job_description: str = Form(...), use_llm: bool = Form(False)):
    filename = resume.filename or "resume"
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(415, "Upload a PDF or DOCX resume. Other file types are not supported.")
    data = await resume.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "This file is larger than 5 MB. Upload a smaller resume.")
    validate_job_description(job_description)
    try:
        text, pages = extract_resume(data, extension)
    except Exception as exc:
        raise HTTPException(400, "I couldn't read this file. Check that it is a valid, unlocked PDF or DOCX.") from exc
    if len(text.strip()) < 80:
        raise HTTPException(422, "I couldn't find readable resume text. If this is a scanned PDF, OCR is not enabled yet.")
    result = analyze_resume(text, job_description, pages)
    result["llm_used"] = False
    result["recommendation_mode"] = "Rule-based personalized coaching"
    if use_llm:
        improved = claude_recommendations(result, job_description)
        if improved:
            result["recommendations"] = improved[:8]
            result["llm_used"] = True
            result["recommendation_mode"] = "Claude-assisted coaching"
    return result


@app.get("/{path:path}")
def frontend(path: str):
    dist = ROOT / "frontend" / "dist"
    index = dist / "index.html"
    target = (dist / path).resolve()
    if target.is_file() and target.is_relative_to(dist.resolve()):
        return FileResponse(target)
    if index.exists():
        return FileResponse(index)
    raise HTTPException(503, "Frontend assets are not built. Run the Vite development server or build frontend/dist.")
