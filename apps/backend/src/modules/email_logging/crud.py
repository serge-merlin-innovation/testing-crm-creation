from fastcrud import FastCRUD

from .models import LoggedEmail, LoggingAddress, UnmatchedEmail

crud_logging_address: FastCRUD = FastCRUD(LoggingAddress)
crud_logged_email: FastCRUD = FastCRUD(LoggedEmail)
crud_unmatched_email: FastCRUD = FastCRUD(UnmatchedEmail)
