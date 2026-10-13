from fastcrud import FastCRUD

from .models import Contact

crud_contact: FastCRUD = FastCRUD(Contact)
