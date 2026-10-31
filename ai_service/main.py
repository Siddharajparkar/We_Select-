from fastapi import FastAPI
from pydantic import BaseModel
from app.services.question_generator import generate_questions
from app.services.answer_evaluator import mark_answer

app = FastAPI(title="AI Assessment Service")


# --- Request models ---

class QuestionRequest(BaseModel):
    job_description: str
    question_type: str   # "mcq", "descriptive", "cognitive"
    domain: str
    difficulty: str      # "easy", "medium", "hard"
    count: int


class EvalRequest(BaseModel):
    question: str
    rubric: str
    max_score: int
    candidate_answer: str


# --- Endpoints ---

@app.post("/ai/generate-questions")
def generate(req: QuestionRequest):
    questions = generate_questions(
        job_description=req.job_description,
        q_type=req.question_type,
        domain=req.domain,
        difficulty=req.difficulty,
        count=req.count
    )
    return {"questions": questions}


@app.post("/ai/evaluate-answer")
def evaluate(req: EvalRequest):
    result = mark_answer(
        question=req.question,
        rubric=req.rubric,
        max_score=req.max_score,
        candidate_answer=req.candidate_answer
    )
    return result


@app.get("/health")
def health():
    return {"status": "ok"}