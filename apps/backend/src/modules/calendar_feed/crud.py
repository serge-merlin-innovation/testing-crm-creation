from fastcrud import FastCRUD

from .models import CalendarFeed

crud_calendar_feed: FastCRUD = FastCRUD(CalendarFeed)
