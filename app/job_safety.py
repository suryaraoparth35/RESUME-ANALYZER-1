"""Heuristic risk signals for pasted job posts; not employer verification."""
import re

CHECKS = [
    ("Upfront fee or purchase", r"(?:pay|payment|fee|purchase|buy).{0,45}(?:training|equipment|application|processing|starter kit)|(?:application|training) fee", "Requests to pay to apply or to receive equipment deserve independent verification."),
    ("Sensitive information requested early", r"(?:send|provide|upload|share).{0,55}(?:social security|ssn|passport|bank account|credit card|one.time password|\botp\b)", "Identity, banking, or one-time-code information should not be shared before verified onboarding."),
    ("Unusually high pay with little screening", r"\$\s?\d{3,}\s?(?:per|/)\s?(?:hour|hr).{0,70}(?:no experience|no interview|easy work)", "Very high pay paired with little screening can be a lure."),
    ("Urgency or secrecy", r"(?:act|apply|respond|accept).{0,30}(?:immediately|today|within \d+ hours)|keep this (?:confidential|secret)|do not contact", "Artificial deadlines or instructions to avoid verification deserve a closer look."),
    ("Recruiting only through messaging apps", r"(?:telegram|whatsapp|signal).{0,60}(?:interview|recruit|hr)|(?:interview|recruit).{0,60}(?:telegram|whatsapp|signal)", "A messaging app alone does not verify who is recruiting."),
    ("Check deposit or money transfer", r"(?:deposit|cash|mobile).{0,45}check|receive.{0,35}money.{0,35}(?:transfer|forward|send)", "Requests to deposit checks or move money can expose applicants to fraud."),
]

def analyze_job_safety(text: str) -> dict:
    if not text.strip():
        return {"provided": False, "score": None, "level": "Not checked", "flags": [], "next_steps": []}
    flags = [{"label": name, "explanation": explanation} for name, pattern, explanation in CHECKS if re.search(pattern, text, re.I | re.S)]
    score = min(96, 8 + len(flags) * 22)
    return {"provided": True, "score": score, "level": "High" if score >= 55 else "Review" if flags else "No major flags detected", "flags": flags,
            "next_steps": ["Verify the role on the employer’s official careers site.", "Find a company contact independently and confirm the recruiter and opening.", "Do not pay to apply or share banking, identity, or one-time-code details before verified onboarding."],
            "disclaimer": "This text-only scan can miss scams and can flag legitimate posts. It does not verify an employer."}
