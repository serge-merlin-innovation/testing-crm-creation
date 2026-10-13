from fastcrud import FastCRUD

from .models import FeeTerms, Invoice

crud_fee_terms: FastCRUD = FastCRUD(FeeTerms)
crud_invoice: FastCRUD = FastCRUD(Invoice)
