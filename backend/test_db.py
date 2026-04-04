from pymongo import MongoClient
import os

client = MongoClient("mongodb+srv://user123:user1232006@coep.jugovtr.mongodb.net/?appName=COEP")
dbs = client.list_database_names()
print("DATABASES:", dbs)
for db_name in dbs:
    if "aegis" in db_name.lower():
        db = client[db_name]
        print(f"DB: {db_name}")
        for coll in db.list_collection_names():
            print(f"  Coll: {coll} | Count: {db[coll].count_documents({})}")
client.close()
