from fastcrud import FastCRUD

from .models import DealBuyer

crud_buyers: FastCRUD = FastCRUD(DealBuyer)
