from pydantic import BaseModel
from typing import List

class OrderItem(BaseModel):
    item_id: str   # we'll convert to ObjectId in backend
    quantity: int

class OrderCreate(BaseModel):
    user_id: str
    items: List[OrderItem]
