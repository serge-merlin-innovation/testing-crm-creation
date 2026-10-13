from fastcrud import FastCRUD

from .models import AccountToken

crud_account_tokens: FastCRUD = FastCRUD(AccountToken)
