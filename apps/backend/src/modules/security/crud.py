from fastcrud import FastCRUD

from .models import UserSecurity

crud_user_security: FastCRUD = FastCRUD(UserSecurity)
