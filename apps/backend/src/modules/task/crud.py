from fastcrud import FastCRUD

from .models import Task

crud_task: FastCRUD = FastCRUD(Task)
