import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import (
    Class,
    CoverageStatus,
    LearningObjective,
    PrerequisiteMap,
    QuestionCurriculumMapping,
    Quiz,
    QuizCoverageReport,
    QuizQuestion,
    SyllabusSubtopic,
)


def analyze_quiz_coverage(db: Session, quiz: Quiz, persist: bool = True) -> dict[str, Any]:
    """Calculates deterministic, explainable curriculum coverage for a quiz.
    Coverage is advisory and represents the alignment of quiz questions
    to the syllabus topics, subtopics, and learning objectives.
    """
    # 1. Fetch questions for this quiz
    questions = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz.id)
        .order_by(QuizQuestion.question_order.asc())
        .all()
    )
    total_questions = len(questions)

    # 2. Collect mappings for each question
    question_ids = [q.id for q in questions]
    mappings: list[QuestionCurriculumMapping] = []
    if question_ids:
        mappings = (
            db.query(QuestionCurriculumMapping)
            .filter(QuestionCurriculumMapping.question_id.in_(question_ids))
            .all()
        )

    # Map question_id -> list of mappings
    q_mappings_map: dict[uuid.UUID, list[QuestionCurriculumMapping]] = {}
    for m in mappings:
        q_mappings_map.setdefault(m.question_id, []).append(m)

    mapped_question_ids = set()
    unmapped_questions = []

    for q in questions:
        q_maps = q_mappings_map.get(q.id, [])
        # Check if question has curriculum mapping or direct topic_id
        if q_maps or q.topic_id:
            mapped_question_ids.add(q.id)
        else:
            unmapped_questions.append({
                "question_id": str(q.id),
                "question_order": q.question_order,
                "question_text": q.question_text,
                "reason": "No approved curriculum topic or learning objective mapped to this question.",
            })

    # 3. Retrieve curriculum scope for the quiz
    class_row = db.get(Class, quiz.class_id)
    subject_id = class_row.subject_id if class_row else None

    topic_query = db.query(PrerequisiteMap)
    if subject_id:
        topic_query = topic_query.filter(PrerequisiteMap.subject_id == subject_id)
    elif class_row and class_row.subject:
        topic_query = topic_query.filter(PrerequisiteMap.subject == class_row.subject)

    # If quiz has a unit specified, prioritize topics for that unit
    if quiz.unit is not None:
        unit_topics = topic_query.filter(PrerequisiteMap.unit == quiz.unit).all()
        # If no topics are tagged with that unit, fall back to all topics for subject
        all_topics = unit_topics if unit_topics else topic_query.all()
    else:
        all_topics = topic_query.all()

    total_topics = len(all_topics)
    topic_matrix = []
    covered_count = 0
    partially_covered_count = 0
    missing_count = 0
    warnings = []

    # If unmapped questions exist, record advisory warning
    if unmapped_questions:
        warnings.append({
            "code": "UNMAPPED_QUESTIONS",
            "severity": "advisory",
            "message": f"{len(unmapped_questions)} of {total_questions} question(s) have no approved curriculum mappings.",
            "unmapped_question_ids": [uq["question_id"] for uq in unmapped_questions],
        })

    # 4. Analyze coverage per topic in scope
    mapped_objectives_count: dict[uuid.UUID, int] = {}
    
    for topic in all_topics:
        # Subtopics for this topic
        subtopics = (
            db.query(SyllabusSubtopic)
            .filter(SyllabusSubtopic.topic_id == topic.id)
            .order_by(SyllabusSubtopic.order_index.asc())
            .all()
        )
        subtopic_ids = [st.id for st in subtopics]

        # Objectives for this topic
        objectives = (
            db.query(LearningObjective)
            .filter(
                (LearningObjective.topic_id == topic.id)
                | (LearningObjective.subtopic_id.in_(subtopic_ids) if subtopic_ids else False)
            )
            .all()
        )
        objective_ids = [obj.id for obj in objectives]

        # Find questions mapped to this topic
        topic_question_ids = set()
        topic_subtopics_covered = set()
        topic_objectives_covered = set()

        for q in questions:
            q_maps = q_mappings_map.get(q.id, [])
            for m in q_maps:
                if m.topic_id == topic.id:
                    topic_question_ids.add(q.id)
                    if m.subtopic_id:
                        topic_subtopics_covered.add(m.subtopic_id)
                    if m.objective_id:
                        topic_objectives_covered.add(m.objective_id)
                        mapped_objectives_count[m.objective_id] = mapped_objectives_count.get(m.objective_id, 0) + 1
            # Also check direct topic_id or topic string on question
            if q.topic_id == topic.id or (q.topic and q.topic.strip().lower() == topic.topic.strip().lower()):
                topic_question_ids.add(q.id)

        q_count = len(topic_question_ids)

        # Determine topic coverage status
        if q_count == 0:
            status = CoverageStatus.not_covered
            missing_count += 1
            explanation = "No questions in this quiz assess this topic."
            warnings.append({
                "code": "TOPIC_NOT_COVERED",
                "severity": "advisory",
                "message": f"Topic '{topic.topic}' has no mapped questions in this quiz.",
                "topic_id": str(topic.id),
                "topic_name": topic.topic,
            })
        elif subtopics and len(topic_subtopics_covered) < len(subtopics):
            status = CoverageStatus.partially_covered
            partially_covered_count += 1
            missing_subtopics = [st.name for st in subtopics if st.id not in topic_subtopics_covered]
            explanation = f"Covers {len(topic_subtopics_covered)} of {len(subtopics)} subtopics. Missing: {', '.join(missing_subtopics[:3])}."
        elif not subtopics and objectives and len(topic_objectives_covered) < len(objectives):
            status = CoverageStatus.partially_covered
            partially_covered_count += 1
            explanation = f"Covers {len(topic_objectives_covered)} of {len(objectives)} learning objectives."
        else:
            status = CoverageStatus.covered
            covered_count += 1
            explanation = f"Topic is covered by {q_count} question(s)."

        topic_matrix.append({
            "topic_id": str(topic.id),
            "topic_name": topic.topic,
            "unit": topic.unit,
            "status": status.value,
            "question_count": q_count,
            "question_ids": [str(qid) for qid in topic_question_ids],
            "total_subtopics": len(subtopics),
            "covered_subtopics": len(topic_subtopics_covered),
            "total_objectives": len(objectives),
            "covered_objectives": len(topic_objectives_covered),
            "explanation": explanation,
        })

    # 5. Redundancy & Concentration Checks
    # If 3 or more questions assess the same single learning objective
    for obj_id, count in mapped_objectives_count.items():
        if count >= 3:
            obj_row = db.get(LearningObjective, obj_id)
            obj_text = obj_row.statement if obj_row else str(obj_id)
            warnings.append({
                "code": "HIGH_CONCENTRATION_OBJECTIVE",
                "severity": "advisory",
                "message": f"{count} questions are concentrated on learning objective: '{obj_text[:60]}...'",
                "objective_id": str(obj_id),
            })

    # 6. Overall coverage score
    if total_topics > 0:
        coverage_score = round(
            ((covered_count + (0.5 * partially_covered_count)) / total_topics) * 100.0,
            1,
        )
    else:
        coverage_score = 100.0 if total_questions > 0 and len(unmapped_questions) == 0 else 0.0

    report_payload = {
        "quiz_id": str(quiz.id),
        "total_questions": total_questions,
        "mapped_questions": len(mapped_question_ids),
        "unmapped_questions": unmapped_questions,
        "total_topics": total_topics,
        "covered_topics": covered_count,
        "partially_covered_topics": partially_covered_count,
        "missing_topics": missing_count,
        "coverage_score": coverage_score,
        "coverage_matrix": topic_matrix,
        "warnings": warnings,
        "advisory_notice": "Coverage analysis is advisory. Faculty may publish quizzes designed for partial or targeted curriculum scopes.",
    }

    # 7. Persist to QuizCoverageReport if requested
    if persist:
        import json
        matrix_json = json.dumps(topic_matrix)
        warnings_json = json.dumps(warnings)

        report = (
            db.query(QuizCoverageReport)
            .filter(QuizCoverageReport.quiz_id == quiz.id)
            .first()
        )
        if not report:
            report = QuizCoverageReport(
                id=uuid.uuid4(),
                quiz_id=quiz.id,
                total_topics=total_topics,
                covered_topics=covered_count,
                partially_covered_topics=partially_covered_count,
                missing_topics=missing_count,
                coverage_score=coverage_score,
                coverage_matrix=matrix_json,
                warnings=warnings_json,
                generated_at=datetime.now(timezone.utc),
            )
            db.add(report)
        else:
            report.total_topics = total_topics
            report.covered_topics = covered_count
            report.partially_covered_topics = partially_covered_count
            report.missing_topics = missing_count
            report.coverage_score = coverage_score
            report.coverage_matrix = matrix_json
            report.warnings = warnings_json
            report.generated_at = datetime.now(timezone.utc)
        db.commit()

    return report_payload


def acknowledge_coverage_warnings(
    db: Session,
    quiz_id: uuid.UUID,
    faculty_notes: str | None = None,
) -> dict[str, Any]:
    """Records faculty acknowledgment of advisory coverage warnings prior to publishing."""
    report = (
        db.query(QuizCoverageReport)
        .filter(QuizCoverageReport.quiz_id == quiz_id)
        .first()
    )
    if not report:
        raise ValueError("No coverage report found for this quiz. Run coverage analysis first.")

    report.faculty_acknowledged = True
    report.faculty_notes = faculty_notes
    db.commit()
    return {
        "quiz_id": str(quiz_id),
        "faculty_acknowledged": True,
        "faculty_notes": faculty_notes,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    }
