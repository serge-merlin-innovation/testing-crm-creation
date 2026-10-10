from fastcrud import FastCRUD

from .models import AuditEntry

crud_audit: FastCRUD = FastCRUD(AuditEntry)
