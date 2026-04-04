from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://sachintrinityuse:sachinsaji2006@online.qhnk9zd.mongodb.net/?appName=Online"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["Foodcheck"]
items = db["items"]

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)