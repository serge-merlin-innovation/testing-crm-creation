from fastcrud import FastCRUD

from .models import Opportunity

crud_opportunity: FastCRUD = FastCRUD(Opportunity)
