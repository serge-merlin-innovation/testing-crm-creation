from fastcrud import FastCRUD

from .models import MaintenanceWindow, RecoveryDrill, SecurityFinding

crud_recovery_drills: FastCRUD = FastCRUD(RecoveryDrill)
crud_security_findings: FastCRUD = FastCRUD(SecurityFinding)
crud_maintenance_windows: FastCRUD = FastCRUD(MaintenanceWindow)
