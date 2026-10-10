from fastcrud import FastCRUD

from .models import AccessRequest

crud_access_requests: FastCRUD = FastCRUD(AccessRequest)
