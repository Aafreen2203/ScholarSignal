from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import current_user
from backend.app.db.session import get_db
from backend.app.models import (
    CollectionPublication,
    Publication,
    PublicationView,
    ResearchCollection,
    ResearchNote,
    SavedPublication,
    User,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


class PublicationSummary(BaseModel):
    id: int
    openalex_id: str
    title: str | None
    abstract: str | None
    authors: list[dict[str, Any]] | None
    publication_date: date | None
    doi: str | None
    cited_by_count: int | None


class SavedPaper(PublicationSummary):
    saved_at: datetime


class CollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Collection name cannot be blank")
        return value


class CollectionItem(BaseModel):
    id: int
    name: str
    description: str | None
    publication_count: int
    created_at: datetime
    updated_at: datetime


class PublicationInput(BaseModel):
    publication_id: int = Field(gt=0)


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=20000)
    publication_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "body")
    @classmethod
    def strip_required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Note fields cannot be blank")
        return value


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    publication_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "body")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Note fields cannot be blank")
        return value


class NoteItem(NoteInput):
    id: int
    created_at: datetime
    updated_at: datetime


def _publication(pub: Publication) -> PublicationSummary:
    return PublicationSummary(
        id=pub.id,
        openalex_id=pub.openalex_id,
        title=pub.title,
        abstract=pub.abstract,
        authors=pub.authors,
        publication_date=pub.publication_date,
        doi=pub.doi,
        cited_by_count=pub.cited_by_count,
    )


def _note_item(note: ResearchNote) -> NoteItem:
    return NoteItem(
        id=note.id,
        title=note.title,
        body=note.body,
        publication_id=note.publication_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _get_publication(db: Session, publication_id: int) -> Publication:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    return publication


def _owned_collection(db: Session, user_id: int, collection_id: int) -> ResearchCollection:
    collection = db.scalar(
        select(ResearchCollection).where(
            ResearchCollection.id == collection_id,
            ResearchCollection.owner_id == user_id,
        )
    )
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.get("/saved", response_model=list[SavedPaper])
def list_saved(
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Publication, SavedPublication.created_at)
        .join(SavedPublication, SavedPublication.publication_id == Publication.id)
        .where(SavedPublication.owner_id == user.id)
        .order_by(SavedPublication.created_at.desc(), SavedPublication.id.desc())
        .limit(limit)
    ).all()
    return [SavedPaper(**_publication(pub).model_dump(), saved_at=saved_at) for pub, saved_at in rows]


@router.post("/saved", status_code=status.HTTP_204_NO_CONTENT)
def save_publication(
    payload: PublicationInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    publication = _get_publication(db, payload.publication_id)
    saved = db.scalar(
        select(SavedPublication).where(
            SavedPublication.owner_id == user.id,
            SavedPublication.publication_id == publication.id,
        )
    )
    if saved is None:
        db.add(SavedPublication(owner_id=user.id, publication_id=publication.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.scalar(
                select(SavedPublication).where(
                    SavedPublication.owner_id == user.id,
                    SavedPublication.publication_id == publication.id,
                )
            ) is None:
                if db.get(Publication, publication.id) is None:
                    raise HTTPException(status_code=404, detail="Publication not found") from None
                raise HTTPException(status_code=409, detail="Could not save publication") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/saved/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_publication(
    publication_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    saved = db.scalar(
        select(SavedPublication).where(
            SavedPublication.owner_id == user.id,
            SavedPublication.publication_id == publication_id,
        )
    )
    if saved is not None:
        db.delete(saved)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections", response_model=list[CollectionItem])
def list_collections(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ResearchCollection, func.count(CollectionPublication.id))
        .outerjoin(CollectionPublication, CollectionPublication.collection_id == ResearchCollection.id)
        .where(ResearchCollection.owner_id == user.id)
        .group_by(ResearchCollection.id)
        .order_by(ResearchCollection.updated_at.desc(), ResearchCollection.id.desc())
        .limit(100)
    ).all()
    return [
        CollectionItem(
            id=item.id,
            name=item.name,
            description=item.description,
            publication_count=count,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item, count in rows
    ]


@router.post("/collections", response_model=CollectionItem, status_code=201)
def create_collection(
    payload: CollectionInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    collection = ResearchCollection(
        owner_id=user.id, name=payload.name.strip(), description=payload.description
    )
    if not collection.name:
        raise HTTPException(status_code=422, detail="Collection name cannot be blank")
    db.add(collection)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A collection with that name already exists") from None
    db.refresh(collection)
    return CollectionItem(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        publication_count=0,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    collection = _owned_collection(db, user.id, collection_id)
    db.delete(collection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections/{collection_id}/publications", response_model=list[PublicationSummary])
def list_collection_publications(
    collection_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _owned_collection(db, user.id, collection_id)
    publications = db.scalars(
        select(Publication)
        .join(CollectionPublication, CollectionPublication.publication_id == Publication.id)
        .where(CollectionPublication.collection_id == collection_id)
        .order_by(CollectionPublication.created_at.desc())
        .limit(200)
    ).all()
    return [_publication(pub) for pub in publications]


@router.post("/collections/{collection_id}/publications", status_code=204)
def add_collection_publication(
    collection_id: int,
    payload: PublicationInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _owned_collection(db, user.id, collection_id)
    publication = _get_publication(db, payload.publication_id)
    existing = db.scalar(
        select(CollectionPublication).where(
            CollectionPublication.collection_id == collection_id,
            CollectionPublication.publication_id == publication.id,
        )
    )
    if existing is None:
        db.add(CollectionPublication(collection_id=collection_id, publication_id=publication.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.scalar(
                select(CollectionPublication).where(
                    CollectionPublication.collection_id == collection_id,
                    CollectionPublication.publication_id == publication.id,
                )
            ) is None:
                if db.get(Publication, publication.id) is None:
                    raise HTTPException(status_code=404, detail="Publication not found") from None
                raise HTTPException(status_code=409, detail="Could not add publication") from None
    return Response(status_code=204)


@router.delete("/collections/{collection_id}/publications/{publication_id}", status_code=204)
def remove_collection_publication(
    collection_id: int,
    publication_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _owned_collection(db, user.id, collection_id)
    link = db.scalar(
        select(CollectionPublication).where(
            CollectionPublication.collection_id == collection_id,
            CollectionPublication.publication_id == publication_id,
        )
    )
    if link is not None:
        db.delete(link)
        db.commit()
    return Response(status_code=204)


@router.get("/notes", response_model=list[NoteItem])
def list_notes(
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ResearchNote)
        .where(ResearchNote.owner_id == user.id)
        .order_by(ResearchNote.updated_at.desc(), ResearchNote.id.desc())
        .limit(limit)
    ).all()
    return [_note_item(row) for row in rows]


@router.post("/notes", response_model=NoteItem, status_code=201)
def create_note(
    payload: NoteInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if payload.publication_id is not None:
        _get_publication(db, payload.publication_id)
    note = ResearchNote(owner_id=user.id, **payload.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_item(note)


@router.patch("/notes/{note_id}", response_model=NoteItem)
def update_note(
    note_id: int,
    payload: NotePatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    note = db.scalar(
        select(ResearchNote).where(ResearchNote.id == note_id, ResearchNote.owner_id == user.id)
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "publication_id" and value is not None:
            _get_publication(db, value)
        if key == "title" and value is not None:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="Note title cannot be blank")
        setattr(note, key, value)
    note.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(note)
    return _note_item(note)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    note = db.scalar(
        select(ResearchNote).where(ResearchNote.id == note_id, ResearchNote.owner_id == user.id)
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note)
    db.commit()
    return Response(status_code=204)


@router.get("/recent", response_model=list[PublicationSummary])
def recent_publications(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    pubs = db.scalars(
        select(Publication)
        .join(PublicationView, PublicationView.publication_id == Publication.id)
        .where(PublicationView.owner_id == user.id)
        .order_by(PublicationView.viewed_at.desc())
        .limit(limit)
    ).all()
    return [_publication(pub) for pub in pubs]
