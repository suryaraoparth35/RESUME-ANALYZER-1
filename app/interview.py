"""Generate interview practice prompts from a specific job post and resume evidence."""
import re

def generate_interview_questions(resume_text: str, job_text: str, matched_skills: list[str], missing_skills: list[str], max_items: int = 7) -> list[dict]:
    resume_lines = [" ".join(line.strip(" •-*\t").split()) for line in resume_text.splitlines()]
    evidence_lines = [line for line in resume_lines if len(line) >= 35]
    questions = [{"question": "Which project or role best prepares you for this position? Walk me through your contribution and result.", "why": "Connects your own experience to the target job."},
                 {"question": "Tell me about a difficult problem you solved. What options did you consider, and what changed afterward?", "why": "Tests problem solving and ownership with a real example."},
                 {"question": "Describe a time you received critical feedback and what you changed because of it.", "why": "Prepares a behavioral example grounded in your own work."}]
    for skill in matched_skills[:3]:
        questions.append({"question": f"Your resume lists {skill}. Describe a specific time you used it, the decision you made, and the outcome.", "why": "The job asks for this skill and it appears in your resume."})
    if missing_skills:
        questions.append({"question": f"The job mentions {missing_skills[0]}, which I could not find in the resume. What experience, coursework, or project can you honestly describe related to it?", "why": "Helps you prepare a truthful answer for a likely gap; do not claim experience you do not have."})
    if evidence_lines:
        sample = evidence_lines[0][:150]
        questions.append({"question": f"You wrote: ‘{sample}’. How did you measure the result, and what would you improve next time?", "why": "Uses a line from your resume to help prepare for follow-up questions."})
    return questions[:max_items]
