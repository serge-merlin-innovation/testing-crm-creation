from fastcrud import FastCRUD

from .models import ApiClient, ApiToken

crud_api_token: FastCRUD = FastCRUD(ApiToken)
crud_api_client: FastCRUD = FastCRUD(ApiClient)
