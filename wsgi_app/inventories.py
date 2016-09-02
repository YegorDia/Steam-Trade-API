from bson.objectid import ObjectId
import datetime
import json


class DatabaseInventories():
    def __init__(self, db):
        self.collection = db["inventories"]

    def set_inventory(self, server_id, bot_username, app_id, inventory_json):
        inventory = self.get(server_id, bot_username, app_id)
        datetime_now = datetime.datetime.utcnow()
        if inventory:
            result = self.collection.update(
                {"server_id": ObjectId(server_id), "bot": bot_username},
                {"$set": {"updated": datetime_now, "inventory": json.dumps(inventory_json)}}
            )
        else:
            result = {"ok": 1}
            self.collection.insert({
                "server_id": ObjectId(server_id),
                "bot": str(bot_username),
                "app_id": int(app_id),
                "updated": datetime_now,
                "inventory": json.dumps(inventory_json)
            })
        return result["ok"] == 1

    def get(self, server_id, bot_username, app_id):
        inventory_json = self.collection.find_one({"server_id": ObjectId(server_id), "bot": bot_username, "app_id": int(app_id)})
        return inventory_json

    def get_all_app_id(self, app_id):
        inventories = list(self.collection.find({"app_id": int(app_id)}, {"_id": 0}))
        return inventories