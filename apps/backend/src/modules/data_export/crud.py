from fastcrud import FastCRUD

from .models import ExportApproval

crud_export_approvals: FastCRUD = FastCRUD(ExportApproval)
