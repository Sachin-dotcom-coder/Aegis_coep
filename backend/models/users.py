from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str
    password: str          
    address: str | None = None
    phone: str | None = None
