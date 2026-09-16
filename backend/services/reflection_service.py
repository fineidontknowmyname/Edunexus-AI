from datetime import datetime
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sqlalchemy.orm import Session

from backend.models.db import Reflection, ReflectionCluster

MIN_REFLECTIONS_FOR_CLUSTERING = 3
MAX_CLUSTERS = 5


def submit_reflection(
    db: Session,
    student_id: str,
    class_id: str,
    subject_id: str | None,
    topic: str | None,
    text: str,
) -> Reflection:
    reflection = Reflection(
        student_id=student_id, class_id=class_id, subject_id=subject_id, topic=topic, text=text
    )
    db.add(reflection)
    db.commit()
    db.refresh(reflection)
    print(f"[REFLECTION] Recorded reflection {reflection.id} for student={student_id} class={class_id} topic={topic}")
    return reflection


def cluster_reflections(
    db: Session, class_id: str, subject_id: str, embedding_model: Any
) -> list[ReflectionCluster]:
    from backend.pipeline.embedder import embed_single

    rows = (
        db.query(Reflection)
        .filter(Reflection.class_id == class_id, Reflection.subject_id == subject_id)
        .order_by(Reflection.created_at.desc())
        .limit(200)
        .all()
    )
    if len(rows) < MIN_REFLECTIONS_FOR_CLUSTERING:
        print(
            f"[REFLECTION CLUSTER] Only {len(rows)} reflection(s) for class={class_id} "
            f"subject={subject_id} — need at least {MIN_REFLECTIONS_FOR_CLUSTERING}"
        )
        return []

    vectors = np.array([embed_single(row.text, model=embedding_model) for row in rows])
    n_clusters = min(MAX_CLUSTERS, len(rows))
    kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
    labels = kmeans.fit_predict(vectors)

    db.query(ReflectionCluster).filter(
        ReflectionCluster.class_id == class_id, ReflectionCluster.subject_id == subject_id
    ).delete()

    now = datetime.utcnow()
    clusters: list[ReflectionCluster] = []
    for cluster_id in range(n_clusters):
        member_indices = [i for i, label in enumerate(labels) if label == cluster_id]
        if not member_indices:
            continue
        centroid = kmeans.cluster_centers_[cluster_id]
        closest_index = min(member_indices, key=lambda i: np.linalg.norm(vectors[i] - centroid))
        cluster = ReflectionCluster(
            class_id=class_id,
            subject_id=subject_id,
            representative_text=rows[closest_index].text,
            cluster_size=len(member_indices),
            computed_at=now,
        )
        db.add(cluster)
        clusters.append(cluster)

    db.commit()
    for cluster in clusters:
        db.refresh(cluster)
    print(
        f"[REFLECTION CLUSTER] class={class_id} subject={subject_id}: "
        f"{len(rows)} reflections -> {len(clusters)} clusters"
    )
    return clusters


def get_latest_clusters(db: Session, class_id: str, subject_id: str) -> list[ReflectionCluster]:
    return (
        db.query(ReflectionCluster)
        .filter(ReflectionCluster.class_id == class_id, ReflectionCluster.subject_id == subject_id)
        .order_by(ReflectionCluster.cluster_size.desc())
        .all()
    )
