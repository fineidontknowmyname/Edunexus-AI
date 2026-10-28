import pytest
from backend.services.quiz_service import _normalize_answer, _validate_generated_question


def test_validate_valid_item():
    item = {
        "question": "What is the primary function of an OS?",
        "options": [
            "Manage hardware resources",
            "Compile source code",
            "Format word documents",
            "Browse websites",
        ],
        "correct_answer": "Manage hardware resources",
        "difficulty": "easy",
    }
    cleaned = _validate_generated_question(item)
    assert cleaned == {
        "question": "What is the primary function of an OS?",
        "options": [
            "Manage hardware resources",
            "Compile source code",
            "Format word documents",
            "Browse websites",
        ],
        "correct_answer": "Manage hardware resources",
        "difficulty": "easy",
    }


def test_validate_missing_keys():
    # Not a dict
    assert _validate_generated_question("not a dict") is None
    assert _validate_generated_question(None) is None
    assert _validate_generated_question([1, 2, 3]) is None

    # Missing question
    assert _validate_generated_question({
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
    }) is None

    # Missing options
    assert _validate_generated_question({
        "question": "Q?",
        "correct_answer": "A",
    }) is None

    # Missing correct_answer
    assert _validate_generated_question({
        "question": "Q?",
        "options": ["A", "B", "C", "D"],
    }) is None


def test_validate_empty_question():
    base = {
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "difficulty": "medium",
    }
    assert _validate_generated_question({**base, "question": ""}) is None
    assert _validate_generated_question({**base, "question": "   \n\t  "}) is None
    assert _validate_generated_question({**base, "question": 123}) is None
    assert _validate_generated_question({**base, "question": None}) is None


def test_validate_options_structure_and_types():
    base = {
        "question": "Valid Question?",
        "correct_answer": "Option A",
    }
    # Not a list
    assert _validate_generated_question({**base, "options": "A, B, C, D"}) is None
    assert _validate_generated_question({**base, "options": {"A": 1, "B": 2, "C": 3, "D": 4}}) is None

    # Length not 4
    assert _validate_generated_question({**base, "options": ["A", "B", "C"]}) is None
    assert _validate_generated_question({**base, "options": ["A", "B", "C", "D", "E"]}) is None

    # Non-string element
    assert _validate_generated_question({**base, "options": ["A", "B", "C", 4]}) is None
    assert _validate_generated_question({**base, "options": ["A", None, "C", "D"]}) is None

    # Empty or whitespace element
    assert _validate_generated_question({**base, "options": ["A", "", "C", "D"]}) is None
    assert _validate_generated_question({**base, "options": ["A", "   ", "C", "D"]}) is None


def test_validate_options_duplicates_and_normalization_collision():
    base = {
        "question": "Valid Question?",
        "correct_answer": "Option A",
    }
    # Exact duplicate
    assert _validate_generated_question({
        **base,
        "options": ["Option A", "Option A", "Option C", "Option D"],
    }) is None

    # Collision after normalization (different case / whitespace)
    assert _validate_generated_question({
        **base,
        "options": ["Option A", "option   a", "Option C", "Option D"],
    }) is None

    assert _validate_generated_question({
        **base,
        "options": ["CPU", "cpu", "Disk", "Memory"],
    }) is None


def test_validate_correct_answer_checks():
    base = {
        "question": "Valid Question?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
    }
    # Not in options
    assert _validate_generated_question({**base, "correct_answer": "Option E"}) is None

    # Empty or whitespace
    assert _validate_generated_question({**base, "correct_answer": ""}) is None
    assert _validate_generated_question({**base, "correct_answer": "   "}) is None

    # Non-string
    assert _validate_generated_question({**base, "correct_answer": None}) is None
    assert _validate_generated_question({**base, "correct_answer": 1}) is None


def test_validate_difficulty_fallback_and_parsing():
    base = {
        "question": "Valid Question?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option A",
    }
    # Valid difficulties (case-insensitive and trimmed)
    res_easy = _validate_generated_question({**base, "difficulty": "easy"})
    assert res_easy["difficulty"] == "easy"

    res_med = _validate_generated_question({**base, "difficulty": "  MEDIUM  "})
    assert res_med["difficulty"] == "medium"

    res_hard = _validate_generated_question({**base, "difficulty": "Hard"})
    assert res_hard["difficulty"] == "hard"

    # Missing difficulty defaults to medium
    res_missing = _validate_generated_question(base)
    assert res_missing["difficulty"] == "medium"

    # Invalid / unrecognized difficulties default to medium
    res_invalid_str = _validate_generated_question({**base, "difficulty": "super_hard"})
    assert res_invalid_str["difficulty"] == "medium"

    res_none = _validate_generated_question({**base, "difficulty": None})
    assert res_none["difficulty"] == "medium"

    res_num = _validate_generated_question({**base, "difficulty": 5})
    assert res_num["difficulty"] == "medium"


def test_normalize_answer_characterization():
    # None returns None
    assert _normalize_answer(None) is None

    # Whitespace collapsing
    assert _normalize_answer("  hello   world  \t\n") == "hello world"

    # Unicode casefolding
    assert _normalize_answer("Python") == "python"
    assert _normalize_answer("STRAßE") == "strasse"

    # Punctuation is PRESERVED (current behavior: does NOT strip punctuation)
    assert _normalize_answer("Newton's law") == "newton's law"
    assert _normalize_answer("Wait, really?!") == "wait, really?!"
    assert _normalize_answer("e.g.") == "e.g."
