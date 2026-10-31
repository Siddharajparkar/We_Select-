import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://assessment-portal-resource.services.ai.azure.com/openai/v1/",
    api_key=os.getenv("AZURE_FOUNDRY_KEY")
)

DEPLOYMENT = os.getenv("AZURE_FOUNDRY_DEPLOYMENT")

MCQ_PROMPT = """Generate {count} multiple choice questions for a {domain} role at {difficulty} difficulty level.
Job Description: {job_description}
Return exactly this JSON format:
[{{"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct": "A", "explanation": "..."}}]"""

DESCRIPTIVE_PROMPT = """Generate {count} descriptive questions for a {domain} role at {difficulty} difficulty level.
Job Description: {job_description}
Return exactly this JSON format:
[{{"question": "...", "rubric": "Award full marks for...", "max_score": 10, "word_limit": 200}}]"""

COGNITIVE_PROMPT = """Generate {count} cognitive reasoning questions suitable for a {domain} role. Types should include logical, numerical, and verbal reasoning.
Return exactly this JSON format:
[{{"question": "...", "type": "logical", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct": "B", "explanation": "..."}}]"""

SYSTEM_PROMPT = "You are an expert technical assessment question writer. Return ONLY a valid JSON array. No explanations, no markdown, no extra text."


def generate_questions(job_description: str, q_type: str, domain: str, difficulty: str, count: int):
    if q_type == "mcq":
        user_prompt = MCQ_PROMPT.format(count=count, domain=domain, difficulty=difficulty, job_description=job_description)
    elif q_type == "descriptive":
        user_prompt = DESCRIPTIVE_PROMPT.format(count=count, domain=domain, difficulty=difficulty, job_description=job_description)
    elif q_type == "cognitive":
        user_prompt = COGNITIVE_PROMPT.format(count=count, domain=domain)
    else:
        raise ValueError(f"Unknown question type: {q_type}")

    for attempt in range(1, 4):  # max 3 retries
        try:
            response = client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                timeout=30
            )
            raw = response.choices[0].message.content.strip()
            questions = json.loads(raw)
            if not isinstance(questions, list) or len(questions) == 0:
                raise ValueError("Empty or invalid response")
            return questions
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"AI_OUTPUT_INVALID after 3 attempts: {str(e)}")