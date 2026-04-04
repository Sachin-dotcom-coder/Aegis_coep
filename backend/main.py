from fastapi import FastAPI
from routers.items import router as items_router
from routers.users import router as users_router
from routers.orders import router as orders_router
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()   # ✅ app MUST be created first

@app.get("/")
def home():
    return {"message": "FoodBuy API is running!"}

# ✅ Include each router ONCE
app.include_router(items_router)
app.include_router(users_router)
app.include_router(orders_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)