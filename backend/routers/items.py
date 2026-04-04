from fastapi import APIRouter
from models.items import Item
from database import db
from bson import ObjectId

router = APIRouter()

items_collection = db["items"]

# CREATE
@router.post("/items")
def create_item(item: Item):
    data = item.dict()
    result = items_collection.insert_one(data)
    return {"id": str(result.inserted_id), "message": "Item added"}

# READ ALL
@router.get("/items")
def get_items():
    items = []
    for item in items_collection.find():
        item["id"] = str(item["_id"])
        del item["_id"]
        items.append(item)
    return items

# READ ONE
@router.get("/items/{item_id}")
def get_item(item_id: str):
    item = items_collection.find_one({"_id": ObjectId(item_id)})
    if not item:
        return {"error": "Item not found"}
    item["id"] = str(item["_id"])
    del item["_id"]
    return item

# UPDATE
@router.put("/items/{item_id}")
def update_item(item_id: str, item: Item):
    update = items_collection.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": item.dict()}
    )
    return {"message": "Item updated"}

# DELETE
@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    items_collection.delete_one({"_id": ObjectId(item_id)})
    return {"message": "Item deleted"}
