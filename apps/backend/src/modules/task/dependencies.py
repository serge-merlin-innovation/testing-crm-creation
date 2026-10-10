from typing import Annotated

from fastapi import Depends

from ..notification.dependencies import NotificationServiceDep
from .service import TaskService


def get_task_service(notifications: NotificationServiceDep) -> TaskService:
    return TaskService(notifications)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
