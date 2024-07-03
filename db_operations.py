from dotenv import load_dotenv
import os
from pymongo import MongoClient

# Load .env file
load_dotenv(override=True)


class DbOperations:
    def __init__(self, collection_name: str):
        CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING")
        client = MongoClient(CONNECTION_STRING)    
        db = client["fitness-plans"]
        self.collection = db[collection_name]

    def write_to_mongodb(self, json_input: dict):
        """
        Write something to a MongoDB database.
        """
        self.collection.insert_one(json_input)
        return {"status": "success", "message": "Uploaded to database"}

    def read_from_mongodb(self, query_param: str = None, sort_param: str = None, sort_order: int = None):
        """
        Read from a MongoDB database.
        """
        query = {"user_id": query_param}
        response = self.collection.find(query)

        if sort_param is not None and sort_order is not None:
            response = self.collection.find(query).sort(sort_param, sort_order)

        return list(response)

