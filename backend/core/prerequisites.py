import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def load_prerequisite_map(subject: str = "Operating Systems") -> dict[str, list[str]]:
    """
    Load and cache the concept prerequisite graph dictionary for a specified subject.

    :param subject: The subject name (defaults to "Operating Systems").
    :return: A dictionary mapping concept strings to lists of prerequisite topic strings.
    """
    # Normalize subject string to locate dataset file
    filename = f"prerequisites_{subject.lower().replace(' ', '_')}.json"
    data_dir = Path(__file__).resolve().parent.parent / "data"
    file_path = data_dir / filename

    if not file_path.exists():
        # Fallback to standard OS prerequisites file if specific subject file is not found
        file_path = data_dir / "prerequisites_os.json"

    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("prerequisite_map", {})


def get_prerequisites(topic: str, subject: str = "Operating Systems") -> list[str]:
    """
    Retrieve direct prerequisite concepts required for a given topic.

    :param topic: Target topic / concept name.
    :param subject: Academic subject context.
    :return: List of prerequisite topic strings.
    """
    prereq_map = load_prerequisite_map(subject)
    return prereq_map.get(topic, [])
