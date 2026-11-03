"""app/main.py - FastAPI entry point. Run from the repo root: python -m uvicorn app.main:app --reload"""
import io
import re
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .feedback import SECTIONS, _jd_terms, _years_covered, generate_recommendations
from .resume_quality import analyze_resume_quality
from .job_safety import analyze_job_safety
from .interview import generate_interview_questions

app = FastAPI(title="Resume Analyzer")
INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

SKILLS = """python,java,javascript,typescript,c++,c#,golang,rust,sql,nosql,html,css,react,angular,vue,node.js,express,
django,flask,fastapi,spring boot,docker,kubernetes,aws,azure,gcp,terraform,jenkins,ci/cd,git,linux,mongodb,postgresql,
mysql,redis,kafka,spark,hadoop,pandas,numpy,scikit-learn,tensorflow,pytorch,machine learning,deep learning,nlp,
computer vision,data analysis,data visualization,statistics,tableau,power bi,excel,rest api,graphql,microservices,agile,
scrum,jira,figma,ui/ux,selenium,pytest,etl,airflow,llm,a/b testing,project management,communication,leadership,html5,bootstrap,tailwind,next.js,redux,jquery,php,laravel,ruby,rails,kotlin,swift,android,ios,flutter,oracle,dynamodb,elasticsearch,snowflake,bigquery,databricks,looker,sap,salesforce,seo,google analytics,photoshop,cybersecurity,networking,unit testing,oop,data structures,algorithms,problem solving,time series,regression,classification,opencv,hugging face,langchain,generative ai,prompt engineering,github,gitlab,postman,rabbitmq,nginx,ansible,prometheus,grafana,bash,matlab,scala,devops,cloud computing,business analysis,stakeholder management,teamwork,data structures""".replace("\n", "").split(",")


def find_skills(text):
    t = text.lower()
    return [s for s in SKILLS if re.search(rf"(?<![\w+#]){re.escape(s)}(?![\w+#])", t)]


def has_term(text, term):
    return bool(re.search(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])", text.lower()))


def jd_skill_list(jd):
    """Only assess recognized skills; arbitrary frequent JD words are not skills."""
    return list(dict.fromkeys(find_skills(jd)))


def validate_job_description(text: str):
    """Reject pasted fragments, gibberish, and non-job text before analysis."""
    words = re.findall(r"[A-Za-z][A-Za-z+#.\-/]*", text)
    lower = text.lower()
    if len(words) < 45:
        return "Paste a complete job description (at least 45 words), including responsibilities or requirements."
    if len(set(w.lower() for w in words)) < 18:
        return "This text has too little variety to identify a real job description. Paste the full posting."
    job_signals = ("responsibilit", "qualif", "require", "skill", "experience", "role", "candidate", "we are looking", "you will", "what you")
    if sum(signal in lower for signal in job_signals) < 2:
        return "I couldn't identify job responsibilities or qualifications. Paste a job posting, not general text."
    if len(jd_skill_list(text)) < 2:
        return "I couldn't identify enough role-specific skills. Include the job's tools, technologies, or core competencies."
    return None


def prioritize_skills(jd: str, skills: list[str]):
    """Rank skills using requirement language, sentence frequency, and emphasis."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", jd.lower())
    result = []
    for skill in skills:
        hits = [s for s in sentences if has_term(s, skill)]
        required = any(re.search(r"\b(required|must|essential|mandatory|proficien\w+|minimum)\b", s) for s in hits)
        preferred = any(re.search(r"\b(preferred|nice to have|bonus|desirable)\b", s) for s in hits)
        occurrences = jd.lower().count(skill)
        if required:
            level = "High"
        elif preferred:
            level = "Medium" if len(hits) > 1 or occurrences > 1 else "Low"
        elif len(hits) >= 3 or occurrences >= 3:
            level = "High"
        elif len(hits) >= 2 or occurrences >= 2:
            level = "Medium"
        else:
            level = "Low"
        result.append({"skill": skill, "priority": level, "reason": "Explicitly required" if required else "Preferred" if preferred else "Repeated in the posting" if len(hits) > 1 else "Mentioned once"})
    rank = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(result, key=lambda item: (rank[item["priority"]], -sum(1 for s in sentences if has_term(s, item["skill"]))))


def extract_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


@app.get("/")
def home():
    return FileResponse(INDEX)


@app.post("/analyze")
async def analyze(resume: UploadFile = File(...), job_description: str = Form(...), job_posting: str = Form(""), target_role: str = Form("")):
    data = await resume.read()
    if not (resume.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF resume.")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "PDF is larger than 5 MB.")
    jd_error = validate_job_description(job_description)
    if jd_error:
        raise HTTPException(422, jd_error)
    try:
        text = extract_text(data)
    except Exception:
        raise HTTPException(400, "Couldn't read that PDF. Is it corrupted or password-protected?")
    if len(text.strip()) < 100:
        raise HTTPException(422, "No readable text found. Scanned/image PDFs need OCR, which isn't supported yet.")

    rl = text.lower()
    jd_skills = jd_skill_list(job_description)
    skill_priorities = prioritize_skills(job_description, jd_skills)
    matched = [s for s in jd_skills if has_term(text, s)]
    missing = [s for s in jd_skills if s not in matched]
    extra = list(dict.fromkeys(s for s in find_skills(text) if s not in jd_skills))

    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    m = vec.fit_transform([text, job_description])
    sim = float(cosine_similarity(m[0], m[1])[0][0])

    jd_years = max([int(x) for x in re.findall(r"(\d+)\+?\s*(?:years|yrs)", job_description.lower())], default=0)
    have = _years_covered(text)
    lines = [l for l in text.splitlines() if 30 <= len(l.strip()) <= 260]
    quant = sum(bool(re.search(r"\d|%|\$|₹", l)) for l in lines)

    priority_weight = {"High": 3.0, "Medium": 1.7, "Low": 1.0}
    skill_weight_total = sum(priority_weight[item["priority"]] for item in skill_priorities)
    weighted_match = (sum(priority_weight[item["priority"]] for item in skill_priorities if item["skill"] in matched) / skill_weight_total) if skill_weight_total else 0
    parts = {
        "Priority-weighted skills": (weighted_match, 40),
        "Relevant experience": ((min(have / jd_years, 1) if have else 0.3) if jd_years
                                else (0.7 if re.search(SECTIONS["experience"], rl) else 0.3), 20),
        "Evidence of impact": (min(quant / len(lines) / 0.4, 1) if len(lines) >= 4 else 0.5, 15),
        "Resume structure": (sum(bool(re.search(p, rl)) for p in SECTIONS.values()) / len(SECTIONS), 10),
        "Bullet clarity": (
            min(
                sum(bool(re.match(r"(?:built|created|developed|designed|delivered|launched|led|managed|improved|reduced|increased|automated|implemented|analyzed|optimized)\b", line.strip(), re.I)) for line in lines)
                / max(1, min(5, len(lines))),
                1,
            ),
            10,
        ),
        "Language overlap (supporting)": (min(sim / 0.4, 1), 5),
    }
    breakdown = [{"name": k, "score": round(f * mx, 1), "max": mx} for k, (f, mx) in parts.items()]
    score = round(sum(b["score"] for b in breakdown))
    verdict = ("Excellent match" if score >= 80 else "Strong match" if score >= 65
               else "Moderate match" if score >= 45 else "Needs work")

    recommendation_jd = (f"Target role: {target_role.strip()}\n" if target_role.strip() else "") + job_description
    recs = generate_recommendations(text, recommendation_jd, matched_skills=matched or None,
                                    missing_skills=missing or None, similarity=sim)
    # Make skill-gap cards inherit the priority inferred from this job posting.
    priority_map = {item["skill"]: item for item in skill_priorities}
    for item in recs:
        if item.get("category") == "Missing skill":
            skill = item["title"].removeprefix("Add evidence of “").removesuffix("”")
            if skill in priority_map:
                item["priority"] = priority_map[skill]["priority"]
                item["job_priority_reason"] = priority_map[skill]["reason"]
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda item: priority_order.get(item.get("priority"), 3))
    focus_plan = [dict(item, rank=i + 1, start_here=(i == 0)) for i, item in enumerate(recs)]
    quality = analyze_resume_quality(text)
    safety = analyze_job_safety(job_posting or job_description)
    questions = generate_interview_questions(text, job_description, matched, missing)
    return {"score": score, "verdict": verdict, "breakdown": breakdown, "matched": matched,
            "missing": missing, "extra": extra[:12], "similarity": round(sim * 100),
            "skill_priorities": skill_priorities,
            "words": len(text.split()), "resume_quality": quality, "job_safety": safety,
            "interview_questions": questions, "focus_plan": focus_plan, "recommendations": recs,
            "target_role": target_role.strip(),
            "notice": "Coaching signals only. Review suggestions and only claim experience you can support."}
