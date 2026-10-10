from fastcrud import FastCRUD

from .models import Offer

crud_offers: FastCRUD = FastCRUD(Offer)
