from typing import Annotated

from fastapi import Depends

from .service import ActivityService, NoteService


def get_activity_service() -> ActivityService:
    return ActivityService()


def get_note_service() -> NoteService:
    return NoteService()


ActivityServiceDep = Annotated[ActivityService, Depends(get_activity_service)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
