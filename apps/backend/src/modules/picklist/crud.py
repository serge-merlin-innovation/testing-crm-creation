from fastcrud import FastCRUD

from .models import PicklistValue

crud_picklist: FastCRUD = FastCRUD(PicklistValue)
