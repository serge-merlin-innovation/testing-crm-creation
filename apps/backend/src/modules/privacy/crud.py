from fastcrud import FastCRUD

from .models import LegalHold, RetentionReview

crud_legal_holds: FastCRUD = FastCRUD(LegalHold)
crud_retention_reviews: FastCRUD = FastCRUD(RetentionReview)
