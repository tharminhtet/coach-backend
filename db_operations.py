from dotenv import load_dotenv
import os
import uuid
from pymongo import MongoClient

# Load .env file
load_dotenv(override=True)


class DbOperations:
    def __init__(self, collection_name: str):
        CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING")
        client = MongoClient(CONNECTION_STRING)    
        db = client["fitness-plans"]
        self.collection = db[collection_name]

    def write_to_mongodb(self, document: dict):
        """
        Write something to a MongoDB database.
        """
        self.collection.insert_one(document)
        return {"status": "success", "message": "Uploaded to database"}

    def read_from_mongodb(self, query_param: str = None):
        """
        Read from a MongoDB database.
        """
        query = {"user_id": query_param}
        response = self.collection.find(query)
        return list(response)

    def read_one_from_mongodb(self, query: dict = None):
        response = self.collection.find_one(query)
        return response

    def aggregate_from_mongodb(self, pipeline):
        response = self.collection.aggregate(pipeline=pipeline)
        return list(response)

    def update_from_mongodb(self, query_param, new_value):
        self.collection.update_one(query_param, new_value)
        # if result.modified_count > 0:
        #     updated_doc = self.collection.find_one(query_param)
        #     updated_doc['_id'] = str(updated_doc['_id'])
        #     return updated_doc
        # return None

