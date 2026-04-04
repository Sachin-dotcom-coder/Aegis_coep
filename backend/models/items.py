from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    description: str | None = None
    image_url: str | None = None
    category: str | None = None


