from fastcrud import FastCRUD

from .models import Company

crud_company: FastCRUD = FastCRUD(Company)
