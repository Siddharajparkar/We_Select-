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

SYSTEM_PROMPT = "You are a strict but fair assessment evaluator. Return ONLY a valid JSON object. No explanations, no markdown, no extra text."

EVAL_PROMPT = """Question: {question}
Rubric: {rubric}
Maximum score: {max_score}
Candidate's answer: {candidate_answer}
Return exactly this JSON format:
{{"score": 7, "justification": "The candidate correctly identified X and Y but missed Z which was worth 3 marks."}}"""


def mark_answer(question: str, rubric: str, max_score: int, candidate_answer: str):
    user_prompt = EVAL_PROMPT.format(
        question=question,
        rubric=rubric,
        max_score=max_score,
        candidate_answer=candidate_answer
    )

    for attempt in range(1, 4):  # max 3 retries
        try:
            response = client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                timeout=30
            )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)

            if "score" not in result or "justification" not in result:
                raise ValueError("Missing required fields in response")
            if not (0 <= result["score"] <= max_score):
                result["score"] = max(0, min(result["score"], max_score))  # clamp to valid range

            return result
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"AI_OUTPUT_INVALID after 3 attempts: {str(e)}")