from fastcrud import FastCRUD

from .models import Activity, Note

crud_activity: FastCRUD = FastCRUD(Activity)
crud_note: FastCRUD = FastCRUD(Note)
