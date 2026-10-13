from fastcrud import FastCRUD

from .models import Notification

crud_notification: FastCRUD = FastCRUD(Notification)
