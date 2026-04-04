from fastapi import APIRouter
from models.users import User
from database import db
from bson import ObjectId
import hashlib

def hash_password(password: str) -> str:
    # simple SHA-256 hash for learning/demo purposes
    return hashlib.sha256(password.encode("utf-8")).hexdigest()



router = APIRouter()
users_collection = db["users"]

# CREATE USER
@router.post("/users")
def create_user(user: User):
    data = user.dict()
    data["password"] = hash_password(data["password"])
    result = users_collection.insert_one(data)
    return {"id": str(result.inserted_id), "message": "User created"}



# GET ALL USERS
@router.get("/users")
def get_users():
    users = []
    for u in users_collection.find():
        u["id"] = str(u["_id"])
        del u["_id"]
        if "password" in u:
            del u["password"]          # ✅ hide password
        users.append(u)
    return users

@router.get("/users/{user_id}")
def get_user(user_id: str):
    u = users_collection.find_one({"_id": ObjectId(user_id)})
    if not u:
        return {"error": "User not found"}
    u["id"] = str(u["_id"])
    del u["_id"]
    if "password" in u:
        del u["password"]              # ✅ hide password
    return u

