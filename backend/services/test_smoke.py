import asyncio
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.core.database import SessionLocal
from backend.models.db import Class, User, Quiz, QuizQuestion
from backend.services.quiz_service import generate_topic_quiz
from backend.api.quizzes import _question_out

async def test_smoke():
    db = SessionLocal()
    try:
        class_id = "5942c0fb-a47c-4549-aeba-f2691a2cffa1"
        topic = "One-Time Pad"
        topic_id = "8d34c080-1c5f-487f-86e7-9f2cadd91152"
        
        student = db.query(User).filter(User.email == "student@edunexus.edu").first()
        if not student:
            student = db.query(User).first()
        
        print(f"Starting diagnostic quiz generation for {topic}...")
        quiz = await generate_topic_quiz(
            db=db,
            class_id=class_id,
            topic=topic,
            topic_id=topic_id,
            student_user=student,
            embedding_model=None,
            num_questions=5
        )
        print(f"SUCCESS! Quiz ID: {quiz.id}")
        print(f"Quiz Title: {quiz.title}")
        
        questions = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.question_order).all()
        print(f"Questions count: {len(questions)}")
        assert len(questions) == 5, f"Expected 5 questions, got {len(questions)}"
        for idx, q in enumerate(questions, 1):
            q_out = _question_out(q, include_answer=False)
            print(f"Q{idx}: {q.question_text[:70]}...")
            print(f"   Type: {q.question_type} | Diff: {q.difficulty.value}")
            print(f"   Source doc: {q_out.get('document_name')} | Page: {q_out.get('page')} | Section: {q_out.get('section_heading')}")
            snippet = q_out.get('snippet')
            print(f"   Snippet: {snippet[:100] if snippet else None}...")
            assert q_out.get('document_name') is not None, "Missing document_name"
            assert q_out.get('page') is not None, "Missing page"
            assert snippet is not None, "Missing snippet"
            # Ensure correct answer is hidden for students
            assert "correct_answer" not in q_out, "Security leak: correct_answer exposed to student!"
            assert "explanation" not in q_out, "Security leak: explanation exposed to student!"
        print("ALL 5 QUESTIONS GROUNDED AND CITATIONS VERIFIED!")
    finally:
        db.rollback()
        db.close()

asyncio.run(test_smoke())
