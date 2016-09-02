import requests
import json
from bson.objectid import ObjectId


class DatabaseServers():
    def __init__(self, db):
        self.collection = db["servers"]

    def get_all(self):
        db_servers = list(self.collection.find({}))
        for server in db_servers:
            server["_id"] = str(server["_id"])
        return db_servers

    def get(self, server_id):
        db_server = self.collection.find_one({"_id": ObjectId(server_id)})
        if db_server:
            db_server["_id"] = str(db_server["_id"])
        return db_server

    def get_host(self, server_host):
        db_server = self.collection.find_one({"host": server_host})
        if db_server:
            db_server["_id"] = str(db_server["_id"])
        return db_server

    def add(self, name, host, port):
        new_server = {
            "name": name,
            "host": host,
            "port": port
        }
        result = self.collection.insert(new_server)
        return result is not None

    def add_bot(self,  host, port, bot_json, token):
        post_data = bot_json
        post_data["token"] = token
        try:
            response = requests.post("http://%s:%s/bots/add" % (str(host), int(port)), data=post_data, timeout=120)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def toggle_bot(self,  host, port, bot_username, token):
        post_data = {"username": bot_username, "token": token}
        try:
            response = requests.post("http://%s:%s/bots/toggle" % (str(host), int(port)), data=post_data, timeout=20)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def remove_bot(self,  host, port, bot_username, token):
        post_data = {"username": bot_username, "token": token}
        try:
            response = requests.post("http://%s:%s/bots/remove" % (str(host), int(port)), data=post_data, timeout=20)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def ping(self, host, port, token):
        try:
            response = requests.get("http://%s:%s/ping?token=%s" % (str(host), int(port), token), timeout=20)
            if response.status_code == 200:
                return True
        except:
            pass
        return False

    def deposit(self, server_id, steam_id, trade_token, assets, report_url, additional, token):
        data = {"success": False}
        db_server = self.get(server_id)
        try:
            post_data = {
                "steam_id": steam_id,
                "trade_token": trade_token,
                "assets": json.dumps(assets),
                "data": json.dumps(additional),
                "report_url": report_url,
                "token": token
            }
            response = requests.post("http://%s:%s/deposit" % (str(db_server["host"]), int(db_server["port"])), data=post_data, timeout=20)
            if response.status_code == 200:
                response_json = response.json()
                data["success"] = True
                data["security_code"] = response_json["security_code"]
                data["task_id"] = response_json["task_id"]
                data["bot"] = response_json["bot"]
        except:
            pass
        return data

    def withdraw(self, server_id, steam_id, trade_token, assets, bot, report_url, additional, token):
        data = {"success": False}
        db_server = self.get(server_id)
        try:
            post_data = {
                "steam_id": steam_id,
                "trade_token": trade_token,
                "assets": json.dumps(assets),
                "data": json.dumps(additional),
                "report_url": report_url,
                "token": token
            }
            response = requests.post("http://%s:%s/%s/withdraw" % (str(db_server["host"]), int(db_server["port"]), str(bot)), data=post_data, timeout=20)
            if response.status_code == 200:
                response_json = response.json()
                data["success"] = True
                data["security_code"] = response_json["security_code"]
                data["task_id"] = response_json["task_id"]
                data["bot"] = response_json["bot"]
        except:
            pass
        return data

    def fetch_server_stats(self, host, port, token):
        data = {"success": False}
        try:
            response = requests.get("http://%s:%s/stats?token=%s" % (str(host), int(port), token), timeout=5)
            if response.status_code == 200:
                response_json = response.json()
                data["success"] = True
                data["load"] = float(response_json["load"])
                data["bots"] = response_json["bots"]
        except:
            pass
        return data

    def request_inventory(self, host, port, bot_username, app_id, token):
        data = {"success": False}
        try:
            response = requests.get("http://%s:%s/bots/%s/inventory/%s?token=%s" % (str(host), int(port), bot_username, app_id, token), timeout=300)
            if response.status_code == 200:
                response_json = response.json()
                data["success"] = True
                data["inventory"] = response_json["inventory"]
                data["descriptions"] = response_json["descriptions"]
        except:
            pass
        return data