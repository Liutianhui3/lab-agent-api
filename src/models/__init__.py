"""注册所有 ORM 模型，确保双向关联可以解析。"""

from models.conversation import Conversation
from models.equipment import Equipment
from models.lab import Lab
from models.message import Message
from models.reservation import Reservation
from models.user import User

__all__ = ["Conversation", "Equipment", "Lab", "Message", "Reservation", "User"]
