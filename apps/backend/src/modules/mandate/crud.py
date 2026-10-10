from fastcrud import FastCRUD

from .models import Mandate

crud_mandate: FastCRUD = FastCRUD(Mandate)
