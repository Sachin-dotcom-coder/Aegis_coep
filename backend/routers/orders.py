from fastapi import APIRouter
from models.orders import OrderCreate
from database import db
from bson import ObjectId
from datetime import datetime

router = APIRouter()
orders_collection = db["orders"]
items_collection = db["items"]

@router.post("/orders")
def create_order(order: OrderCreate):
    # calculate total price from items
    total = 0
    for oi in order.items:
        item_doc = items_collection.find_one({"_id": ObjectId(oi.item_id)})
        if not item_doc:
            return {"error": f"Item {oi.item_id} not found"}
        total += item_doc["price"] * oi.quantity

    order_doc = {
        "user_id": ObjectId(order.user_id),
        "items": [
            {"item_id": ObjectId(oi.item_id), "quantity": oi.quantity}
            for oi in order.items
        ],
        "total_price": total,
        "status": "pending",
        "created_at": datetime.utcnow()
    }

    result = orders_collection.insert_one(order_doc)
    return {"id": str(result.inserted_id), "total_price": total}

@router.get("/orders")
def get_orders():
    orders = []
    for o in orders_collection.find():
        o["id"] = str(o["_id"])
        o["user_id"] = str(o["user_id"])
        for it in o["items"]:
            it["item_id"] = str(it["item_id"])
        del o["_id"]
        orders.append(o)
    return orders
