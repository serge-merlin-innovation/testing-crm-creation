from fastcrud import FastCRUD

from .models import KycRecord

crud_kyc: FastCRUD = FastCRUD(KycRecord)
