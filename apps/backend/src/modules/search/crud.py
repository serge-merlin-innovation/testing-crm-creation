from fastcrud import FastCRUD

from .models import SavedFilter

crud_saved_filter: FastCRUD = FastCRUD(SavedFilter)
