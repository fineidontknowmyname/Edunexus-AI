"""Educator-created categories and subjects.

Nothing here is pre-seeded: the platform ships with zero categories, zero
subjects, and zero topics. Any educator can create a category or a subject
through the app.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.db import Category, Subject


def create_category(db: Session, name: str, created_by: str) -> Category:
    existing = (
        db.query(Category)
        .filter(Category.name == name.strip(), Category.created_by == created_by)
        .first()
    )
    if existing is not None:
        return existing
    row = Category(name=name.strip(), created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    print(f"[SUBJECTS] Category created: {row.id} '{row.name}'")
    return row


def list_categories(db: Session) -> list[Category]:
    return db.query(Category).order_by(Category.name).all()


def create_subject(db: Session, name: str, category_id: str, created_by: str) -> Subject:
    category = db.get(Category, category_id)
    if category is None:
        raise ValueError(f"Category '{category_id}' not found.")

    existing = (
        db.query(Subject)
        .filter(Subject.category_id == category_id, Subject.name == name.strip())
        .first()
    )
    if existing is not None:
        raise ValueError(f"Subject '{name}' already exists in this category.")

    row = Subject(name=name.strip(), category_id=category_id, created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    print(f"[SUBJECTS] Subject created: {row.id} '{row.name}' (category {category_id})")
    return row


def list_subjects(db: Session) -> list[Subject]:
    return db.query(Subject).order_by(Subject.name).all()


def get_subject(db: Session, subject_id: str) -> Subject | None:
    return db.get(Subject, subject_id)
