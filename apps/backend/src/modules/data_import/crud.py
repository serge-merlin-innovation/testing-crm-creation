from fastcrud import FastCRUD

from .models import DataImport

crud_data_import: FastCRUD = FastCRUD(DataImport)
