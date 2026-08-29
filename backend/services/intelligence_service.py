from typing import Any


def apply_rules(
    student_context: dict[str, Any],
    query_topic: str | None,
    top_similarity: float,
    session_mode: str,
    prerequisite_gaps: list[str],
) -> list[str]:
    rules: list[str] = []

    if top_similarity < 0.55:
        rules.append(
            "This question may not be covered in the uploaded curriculum. Answer from general knowledge "
            "and note in your own words that the student should verify it independently — the UI already "
            "shows a 'General knowledge' badge, so do not prefix your answer with a literal tag like "
            "'[General Knowledge]'."
        )

    if query_topic:
        mastery_entry = student_context["mastery"].get(query_topic)
        score = mastery_entry["score"] if mastery_entry else 0.0

        if query_topic in student_context["weak_topics"] or score < 0.60:
            rules.append("Start from fundamentals. Do not assume prior mastery.")

        for misconception in student_context["misconceptions"]:
            if misconception["topic"] == query_topic:
                rules.append(
                    f"Known misconception: {misconception['description']}. Address this distinction explicitly."
                )

        if prerequisite_gaps:
            rules.append(
                f"Verify prerequisite understanding of {', '.join(prerequisite_gaps)} before the main explanation."
            )

        pattern = student_context["interaction_patterns"].get(query_topic)
        if pattern and pattern["questions_asked"] >= 3:
            rules.append(
                "The student has asked about this topic multiple times. Use a worked example, not a definition."
            )

    if session_mode == "study":
        rules.append("Ask a guiding question first. Do not answer directly.")

    upcoming = student_context.get("upcoming_focus")
    if (
        upcoming
        and query_topic
        and query_topic in upcoming.get("topics_in_scope", [])
        and upcoming["days_remaining"] <= 5
    ):
        rules.append(
            f"Assessment in {upcoming['days_remaining']} days. Be thorough and exam-oriented."
        )

    if student_context["engagement"]["staleness_flag"]:
        rules.append("The student is returning after an absence. Give a brief re-orientation before the main response.")

    print(f"[INTELLIGENCE] {len(rules)} rule(s) triggered for topic={query_topic!r} mode={session_mode}: {rules}")
    return rules
