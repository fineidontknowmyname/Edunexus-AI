import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def load_prerequisite_map(subject: str = "Operating Systems") -> dict[str, list[str]]:
    filename = f"prerequisites_{subject.lower().replace(' ', '_')}.json"
    data_dir = Path(__file__).resolve().parent.parent / "data"
    file_path = data_dir / filename

    if not file_path.exists():
        file_path = data_dir / "prerequisites_os.json"

    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("prerequisite_map", {})


def get_prerequisites(topic: str, subject: str = "Operating Systems") -> list[str]:
    prereq_map = load_prerequisite_map(subject)
    return prereq_map.get(topic, [])
