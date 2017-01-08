from pymongo import MongoClient
from flask import Flask, render_template, request, redirect, jsonify, abort, session
from redis import StrictRedis

from simple_crypto import simple_encode, simple_decode
import sys
import os
import json

if sys.platform == 'win32':
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..\\cfg\\default.json')
else:
    CONFIG_PATH = '/usr/share/www/steam-trade-api/cfg/deploy.json'

from config.config import Configurator
from servers import DatabaseServers
from inventories import DatabaseInventories
from withdrawals import DatabaseWithdrawals
from deposits import DatabaseDeposits

CONFIG = Configurator(CONFIG_PATH)

mongodb = MongoClient(CONFIG.get("MONGODB_HOST", "localhost:27017"))["tradeapi"]
redis = StrictRedis(host=CONFIG["REDIS_HOST"], port=CONFIG["REDIS_PORT"], db=3, password=CONFIG["REDIS_PASSWORD"])

db_servers = DatabaseServers(mongodb)
db_inventories = DatabaseInventories(mongodb)
db_withdrawals = DatabaseWithdrawals(mongodb)
db_deposits = DatabaseDeposits(mongodb)


app = Flask(__name__)
app.debug = True
app.config.update(
    SECRET_KEY=CONFIG['APP_SECRET']
)


def logged_in():
    return session.get("authorized", False)


def in_allowed_ips(ip_address):
    if ip_address in CONFIG.get("ALLOW_IPS", []):
        return True
    return False


@app.before_request
def before_request():
    if not in_allowed_ips(request.remote_addr):
        return abort(404)

    if not logged_in():
        access_token = session.get("token", None) or request.args.get("token", False) or request.form.get("token", False)
        if access_token == CONFIG["ACCESS_TOKEN"]:
            session["authorized"] = True


@app.route("/", methods=["GET"])
def index():
    if logged_in():
        processing_deposits = db_deposits.get_processing()
        processing_withdrawals = db_withdrawals.get_processing()

        return render_template("index.jinja2", deposits=processing_deposits, withdrawals=processing_withdrawals)
    return abort(401)


@app.route("/servers", methods=["GET"])
def servers():
    if logged_in():
        servers = db_servers.get_all()
        return render_template("servers.jinja2", servers=servers)
    return abort(401)


@app.route("/settings", methods=["GET"])
def settings():
    if logged_in():
        return render_template("settings.jinja2")
    return abort(401)


@app.route("/servers/add", methods=["POST"])
def servers_add():
    if logged_in():
        name = request.form.get("name", None)
        host = request.form.get("host", None)
        port = request.form.get("port", 80)

        if db_servers.ping(host, port, CONFIG["ACCESS_TOKEN"]):
            db_servers.add(name, str(host), int(port))

        return redirect("/servers")
    return abort(401)


@app.route("/servers/<string:server_id>", methods=["GET"])
def servers_id(server_id):
    if logged_in():
        server = db_servers.get(server_id)
        server["status"] = None
        server["bots"] = None
        server["load"] = None

        if server:
            server["status"] = db_servers.ping(server["host"], server["port"], CONFIG["ACCESS_TOKEN"])
            server_stats = db_servers.fetch_server_stats(server["host"], server["port"], CONFIG["ACCESS_TOKEN"])
            server["load"] = server_stats["load"]
            server["bots"] = server_stats["bots"]
            return render_template("server.jinja2", server=server)
        return abort(404)
    return abort(401)


@app.route("/servers/<string:server_id>/bots/add", methods=["POST"])
def servers_id_bot_add(server_id):
    if logged_in():
        server = db_servers.get(server_id)
        if server:
            bot_data = {
                "nickname": request.form.get("nickname"),
                "username": request.form.get("username"),
                "password": request.form.get("password"),
                "device_id": request.form.get("device_id"),
                "shared_secret": request.form.get("shared_secret"),
                "identity_secret": request.form.get("identity_secret")
            }
            db_servers.add_bot(server["host"], server["port"], bot_data, CONFIG["ACCESS_TOKEN"])
            return redirect("/servers/%s" % server_id)
        return abort(404)
    return abort(401)


@app.route("/servers/<string:server_id>/bots/toggle", methods=["POST"])
def servers_id_bot_toggle(server_id):
    if logged_in():
        server = db_servers.get(server_id)
        if server:
            username = request.form.get("username")
            db_servers.toggle_bot(server["host"], server["port"], username, CONFIG["ACCESS_TOKEN"])
            return redirect("/servers/%s" % server_id)
        return abort(404)
    return abort(401)


@app.route("/servers/<string:server_id>/bots/remove", methods=["POST"])
def servers_id_bot_remove(server_id):
    if logged_in():
        server = db_servers.get(server_id)
        if server:
            username = request.form.get("username")
            db_servers.remove_bot(server["host"], server["port"], username, CONFIG["ACCESS_TOKEN"])
            return redirect("/servers/%s" % server_id)
        return abort(404)
    return abort(401)


@app.route("/trade/inventory/<int:app_id>", methods=["GET"])
def trade_inventory(app_id):
    if logged_in():
        global_inventory = {
            "inventory": {},
            "descriptions": {}
        }
        inventories = db_inventories.get_all_app_id(app_id)
        for inventory in inventories:
            _inventory = json.loads(inventory["inventory"])
            inventory["inventory"] = _inventory["inventory"]
            inventory["descriptions"] = _inventory["descriptions"]
            crypted_bot = simple_encode(CONFIG["CRYPTO_SALT"], str(inventory["bot"]))
            crypted_server = simple_encode(CONFIG["CRYPTO_SALT"], str(inventory["server_id"]))
            for key, item in inventory["inventory"].iteritems():
                item["bot"] = crypted_bot
                item["server"] = crypted_server
                global_inventory["inventory"]["%s_%s" % (key, crypted_bot)] = item
            for key, description in inventory["descriptions"].iteritems():
                global_inventory["descriptions"][key] = description

        is_empty = len(global_inventory["inventory"].keys()) == 0
        return jsonify(inventory=global_inventory["inventory"], descriptions=global_inventory["descriptions"], empty=is_empty), 200
    return abort(401)


@app.route("/trade/withdrawals/<string:steam_id>/active", methods=["GET"])
def trade_withdrawals_active(steam_id):
    if logged_in():
        withdrawals = db_withdrawals.get_steam_id(steam_id)
        return jsonify(withdrawals=withdrawals), 200
    return abort(401)


@app.route("/trade/deposits/<string:steam_id>/active", methods=["GET"])
def trade_deposits_active(steam_id):
    if logged_in():
        deposits = db_deposits.get_steam_id(steam_id)
        return jsonify(deposits=deposits), 200
    return abort(401)


@app.route("/trade/withdrawals/<string:steam_id>/add", methods=["POST"])
def trade_withdrawals_add(steam_id):
    if logged_in():
        trade_token = request.form.get("trade_token")
        report_url = request.form.get("report_url")

        additional = request.form.get("data")
        assets = request.form.get("assets")

        if not trade_token or not report_url or not assets:
            return abort(400)

        try:
            additional = json.loads(additional)
            assets = json.loads(assets)
        except:
            return abort(400)

        if len(assets) == 0:
            return abort(400)
        elif len(assets) > 50:
            return abort(400)

        # TODO: Check settings restrictions

        additional.pop("token", None)

        withdrawal_requests = {}
        withdrawal_points = {}
        keys_to_reserve = {}
        reserved_keys = redis.keys("reserved_*")

        for asset in assets:
            reserve_key = "reserved_%s_%s_%s_%s" % (asset["server"], asset["bot"], asset["app_id"], asset["assetid"])
            if reserve_key in reserved_keys:
                return abort(400)

            bot_username = simple_decode(CONFIG["CRYPTO_SALT"], asset["bot"])
            server_id = simple_decode(CONFIG["CRYPTO_SALT"], asset["server"])
            asset_key = "%s_%s" % (server_id, bot_username)
            asset.pop("bot", None)
            asset.pop("server", None)
            if asset_key not in withdrawal_requests:
                withdrawal_requests[asset_key] = [asset]
                withdrawal_points[asset_key] = int(asset["points"])
                keys_to_reserve[asset_key] = [reserve_key]
            else:
                withdrawal_requests[asset_key].append(asset)
                withdrawal_points[asset_key] += int(asset["points"])
                keys_to_reserve[asset_key].append(reserve_key)

        if len(withdrawal_requests.keys()) == 0:
            return abort(400)

        request_results = []
        points = 0

        for key, withdrawal_request in withdrawal_requests.iteritems():
            split_key = key.split("_")
            server_id = split_key[0]
            bot_username = split_key[1]
            additional["points"] = int(withdrawal_points[key])
            assets = withdrawal_request
            points += additional["points"]

            result = db_servers.withdraw(server_id, steam_id, trade_token, assets, bot_username, report_url, additional, CONFIG["ACCESS_TOKEN"])

            if result.get("success", False):
                for r_key in keys_to_reserve[key]:
                    redis.set(r_key, True, ex=320)

                security_code = result["security_code"]
                celery_task_id = result["task_id"]
                bot_nickname = result["bot"]

                new_withdraw_result = db_withdrawals.add(server_id, steam_id, trade_token, assets, report_url, security_code, celery_task_id, bot_nickname, bot_username, additional)
                if new_withdraw_result:
                    request_results.append({"security_code": security_code, "task_id": celery_task_id, "bot": bot_nickname})

        additional["points"] = points
        return jsonify(withdrawals=request_results, data=additional), 200
    return abort(401)


@app.route("/trade/deposits/<string:steam_id>/add", methods=["POST"])
def trade_deposits_add(steam_id):
    if logged_in():
        trade_token = request.form.get("trade_token")
        report_url = request.form.get("report_url")

        additional = request.form.get("data")
        assets = request.form.get("assets")

        if not trade_token or not report_url or not assets:
            return abort(400)

        try:
            additional = json.loads(additional)
            assets = json.loads(assets)
        except:
            return abort(400)

        if len(assets) == 0:
            return abort(400)

        # TODO: Check settings restrictions

        minimal_load = -1.0
        minimal_load_id = None
        server_load_keys = redis.keys("server_load_*")

        if len(server_load_keys) == 0:
            servers = db_servers.get_all()
            for server in servers:
                server_load = db_servers.fetch_server_stats(server["host"], server["port"], CONFIG["ACCESS_TOKEN"])
                if server_load.get("success", False):
                    redis.set("server_load_%s" % server["_id"], server_load["load"], ex=300)
                    server_load_keys.append("server_load_%s" % server["_id"])

        for server_load_key in server_load_keys:
            server_id = server_load_key.split("_load_")[1]
            server_load = float(redis.get(server_load_key))
            if server_load <= minimal_load or minimal_load == -1.0:
                minimal_load = server_load
                minimal_load_id = server_id

        if minimal_load > 0.9 or not minimal_load_id:
            return abort(503)

        additional.pop("token", None)
        result = db_servers.deposit(minimal_load_id, steam_id, trade_token, assets, report_url, additional, CONFIG["ACCESS_TOKEN"])

        if result.get("success", False):
            security_code = result["security_code"]
            celery_task_id = result["task_id"]
            deposit_data = {
                "bot": result["bot"]
            }
            new_deposit_result = db_deposits.add(minimal_load_id, steam_id, trade_token, assets, report_url, security_code, celery_task_id, result["bot"], additional)
            return jsonify(security_code=security_code, data=deposit_data), 200
        return abort(500)
    return abort(401)


@app.route("/trade/deposits/<string:steam_id>/report", methods=["POST"])
def trade_deposits_report(steam_id):
    if logged_in():
        error_message = request.form.get("error")
        celery_task_id = request.form.get("celery_task_id")
        tradeoffer_id = request.form.get("tradeoffer_id")
        status = int(request.form.get("status"))
        db_deposits.change_status_last(steam_id, status)

        if tradeoffer_id:
            db_deposits.set_data(steam_id, "tradeoffer_id", tradeoffer_id)

        if celery_task_id:
            db_deposits.change_celery_task_id_last(steam_id, celery_task_id)

        if error_message:
            db_deposits.change_message_last(steam_id, error_message)
        return "OK", 200
    return abort(401)


@app.route("/trade/withdrawals/<string:steam_id>/report", methods=["POST"])
def trade_withdrawals_report(steam_id):
    if logged_in():
        error_message = request.form.get("error")
        celery_task_id = request.form.get("celery_task_id")
        bot_username = request.form.get("bot")
        tradeoffer_id = request.form.get("tradeoffer_id")
        status = int(request.form.get("status"))
        db_withdrawals.change_status_last(steam_id, bot_username, status)

        if tradeoffer_id:
            db_withdrawals.set_data(steam_id, bot_username, "tradeoffer_id", tradeoffer_id)

        if celery_task_id:
            db_withdrawals.change_celery_task_id_last(steam_id, bot_username, celery_task_id)

        if error_message:
            db_withdrawals.change_message_last(steam_id, bot_username, error_message)
        return "OK", 200
    return abort(401)


@app.route("/trade/inventory/<int:app_id>/report", methods=["POST"])
def trade_inventory_report(app_id):
    if logged_in():
        server_host = request.remote_addr
        if server_host == "127.0.0.1" and CONFIG_PATH.endswith("deploy.json"):
            server_host = "185.46.10.189"
        server = db_servers.get_host(server_host)
        app_id = int(app_id)
        bot_username = request.form.get("bot", None)

		if bot_username:
			response = db_servers.request_inventory(server["host"], server["port"], bot_username, app_id, CONFIG["ACCESS_TOKEN"])
			if response.get("success", False):
				result = db_inventories.set_inventory(
					server["_id"],
					bot_username,
					app_id,
					{"inventory": response["inventory"], "descriptions": response["descriptions"]}
				)
				if result:
					return "OK", 200
				return "Database inventory update error", 500
  
        return abort(400)
    return abort(401)


@app.route("/logout", methods=["GET"])
def logout():
    if logged_in():
        session.pop("authorized", None)
        return redirect("/")
    return abort(401)
