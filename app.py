from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

import psycopg2
from uuid import uuid4
import json  # For serializing payloads for MQTT

from src.config import get_dynamodb, get_sns
from src.services.database import get_plant_data_from_db, get_fish_data_from_db, insert_plant_data_into_db, insert_fish_data_into_db

import google.generativeai as genai

from dotenv import load_dotenv
import os
from datetime import datetime
import pytz

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

# Import the Paho MQTT client
import paho.mqtt.client as paho
from paho import mqtt

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", allow_upgrades=True, ping_timeout=10, ping_interval=5)

MQTT_TOPIC_CHANGE_WATER = "aquaponics/change_water"
MQTT_TOPIC_TURBIDITY = "aquaponics/turbidity"
MQTT_TOPIC_GROWLIGHT = "aquaponics/growlight"
MQTT_TOPIC_FEEDER = "aquaponics/feeder"

ldr_value_prev = 0


# Create and connect the MQTT client
mqtt_client = paho.Client(client_id="", userdata=None, protocol=paho.MQTTv5, callback_api_version=paho.CallbackAPIVersion.VERSION2)
mqtt_client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
mqtt_client.username_pw_set("hivemq.webclient.1744715705461", "6a45&NDq.1TJ!Cpd:syI")
mqtt_client.connect("7170b6ffae904900aeec54b1aeffca2c.s1.eu.hivemq.cloud", 8883)
mqtt_client.loop_start()

turbidity_history = []
turbidity_treshold = 250  # The threshold value for turbidity alerts

@app.route('/')
def home():
    return "Hello, World!"

# Set timezone for PH
ph_tz = pytz.timezone("Asia/Manila")

# ------------------------
# PLANT DATA ENDPOINTS
# ------------------------
@app.route('/plant_data', methods=['GET'])
def get_plant_data():
    try:
        limit = int(request.args.get('limit', 10))
        rows = get_plant_data_from_db(limit)
        formatted_data = []
        for row in rows:
            timestamp = row[5]
            # Localize timestamp if naive, then convert to PH timezone
            if timestamp.tzinfo is None:
                timestamp = ph_tz.localize(timestamp)
            else:
                timestamp = timestamp.astimezone(ph_tz)
            formatted_data.append({
                "ph": row[1],
                "tds": row[2],
                "temperature": row[3],
                "humidity": row[4],
                "created_at": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            })
        return jsonify(formatted_data), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/plant_data', methods=['POST'])
def receive_plant_data():
    try:
        data = request.json
        if (data.get('ph') is None or data.get('tds') is None or 
            data.get('temperature') is None or data.get('humidity') is None):
            return jsonify({"status": "error", "message": "Invalid data format"}), 400
        current_time = datetime.now(ph_tz)
        data["created_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")

        print("('/plant_data') Request received at:", current_time.strftime("%Y-%m-%d %H:%M:%S"))
        
        if not insert_plant_data_into_db(data):
            return jsonify({"status": "error", "message": "Error inserting data into database"}), 500
        
        sensor_data = {
            "ph": data.get("ph"),
            "tds": data.get("tds"),
            "temperature": data.get("temperature"),
            "humidity": data.get("humidity"),
            "created_at": data.get("created_at")
        }
        print("Sensor Data:", sensor_data)
        
        # Broadcast to all connected clients
        socketio.emit('plant_data', sensor_data)

        return jsonify({"status": "success", "data": sensor_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------------
# FISH DATA ENDPOINTS
# ------------------------
@app.route('/fish_data', methods=['GET'])
def get_fish_data():
    try:
        limit = int(request.args.get('limit', 10))
        rows = get_fish_data_from_db(limit)
        formatted_data = []
        for row in rows:
            # Process timestamp for fish data
            timestamp = row[4]
            if timestamp.tzinfo is None:
                timestamp = ph_tz.localize(timestamp)
            else:
                timestamp = timestamp.astimezone(ph_tz)
            formatted_data.append({
                "turbidity": row[1],
                "waterTemperature": row[2],
                "ph": row[3],
                "created_at": timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })
        return jsonify(formatted_data), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/fish_data', methods=['POST'])
def receive_fish_data():
    try:
        global turbidity_history
        data = request.json
        if (data.get('waterTemperature') is None or 
            data.get('ph') is None or data.get('turbidity') is None):
            return jsonify({"status": "error", "message": "Invalid data format"}), 400
        current_time = datetime.now(ph_tz)
        data['created_at'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"Received from ESP32: {data}")
        if not insert_fish_data_into_db(data):
            return jsonify({"status": "error", "message": "Error inserting data into database"})
        
        fish_data = {
            "turbidity": data.get("turbidity"),
            "waterTemperature": data.get("waterTemperature"),
            "ph": data.get("ph"),
            "created_at": data.get("created_at")
        }
        
        # Update turbidity history (capped at 50 records)
        if len(turbidity_history) == 0:
            rows = get_fish_data_from_db(50)
            turbidity_history = [float(row[1]) for row in rows]
        else:
            turbidity_history.append(float(data.get("turbidity")))
            if len(turbidity_history) > 50:
                turbidity_history = turbidity_history[1:]
        turbidity_average = sum(turbidity_history) / len(turbidity_history)

        # Send MQTT message based on turbidity threshold
        if turbidity_average > turbidity_treshold:
            mqtt_client.publish(MQTT_TOPIC_CHANGE_WATER, str(turbidity_average), qos=0)
            socketio.emit('change_water', turbidity_average)
        
        # Get 'ldr_value' from the request and trigger growlight if brightness is below acceptable threshold
        ldr_value = int(data.get("ldr_value"))
        isGrowlightTriggered = int(data.get("isGrowlightTriggered"))
        if ldr_value_prev != ldr_value:
            if ldr_value is not None and isGrowlightTriggered is not None: 
                try:
                    ldr_value = float(ldr_value)
                    if ldr_value == 0 and isGrowlightTriggered == 0:
                        current_time_str = datetime.now(ph_tz).strftime("%Y-%m-%d %H:%M:%S")
                        mqtt_client.publish(MQTT_TOPIC_GROWLIGHT, f'[{current_time_str}] Growlights Triggered due to low brightness: {ldr_value}')
                        socketio.emit('growlights', {"ldr_value": ldr_value, "triggered": True})
                    elif ldr_value == 1 and isGrowlightTriggered == 1:
                        current_time_str = datetime.now(ph_tz).strftime("%Y-%m-%d %H:%M:%S")
                        mqtt_client.publish(MQTT_TOPIC_GROWLIGHT, f'[{current_time_str}] Growlights Triggered due to low brightness: {ldr_value}')
                        socketio.emit('growlights', {"ldr_value": ldr_value, "triggered": True})
                except ValueError:
                    pass
            ldr_value_prev = ldr_value

        socketio.emit('fish_data', fish_data)
        return jsonify({"status": "success", "data": fish_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------------
# MQTT TRIGGER EVENTS
# ------------------------

@app.route('/growlights', methods=['POST'])
def trigger_growlights():
    current_time = datetime.now(ph_tz).strftime("%Y-%m-%d %H:%M:%S")
    mqtt_client.publish(MQTT_TOPIC_GROWLIGHT, f'[{current_time}] Growlights Triggered')
    return jsonify({"status": "success", "message": "Growlights triggered"}), 200

@app.route('/feeder', methods=['POST'])
def trigger_feeder():
    current_time = datetime.now(ph_tz).strftime("%Y-%m-%d %H:%M:%S")
    mqtt_client.publish(MQTT_TOPIC_FEEDER, f'[{current_time}] Feeder Triggered')
    return jsonify({"status": "success", "message": "Feeder triggered"}), 200

@app.route('/change_water', methods=['POST'])
def trigger_change_water():
    current_time = datetime.now(ph_tz).strftime("%Y-%m-%d %H:%M:%S")
    mqtt_client.publish(MQTT_TOPIC_CHANGE_WATER, f'[{current_time}] Change Water Triggered')
    return jsonify({"status": "success", "message": "Change water triggered"}), 200

# ------------------------
# SOCKETIO EVENTS
# ------------------------
@socketio.on('connect')
def handle_connect():
    print("A client connected")
    emit('message', {'data': 'connected successfully'})

@socketio.on('disconnect')
def handle_disconnect():
    print("A client disconnected")

# ------------------------
# GEMINI AI CONVERSATION API
# ------------------------
@app.route('/chat', methods=['POST'])
def chat():
    query = request.json.get('query')
    session_id = request.args.get('session_id')

    dynamodb = get_dynamodb()
    table = dynamodb.Table(os.getenv("DYNAMODB_TABLE"))
    
    if query is None:
        return jsonify({"status": "error", "message": "Invalid query"})
    
    if session_id is None or session_id == "":
        session_id = str(uuid4())
        table.put_item(Item={"session_id": session_id, "messages": []})
        messages = []
    else:
        current_session = table.get_item(Key={"session_id": session_id})
        messages = current_session.get("Item", {}).get("messages", [])

    messages = messages[-5:]  # Keep only the last 5 messages for context

    # Fetch raw plant data (last 10 records)
    plant_rows = get_plant_data_from_db(10)
    if plant_rows:
        plant_data_info = "\n".join(
            [f"ph: {row[1]}, tds: {row[2]}, temperature: {row[3]}, humidity: {row[4]}, created_at: {row[5].strftime('%Y-%m-%d %H:%M:%S')}" for row in plant_rows]
        )
    else:
        plant_data_info = "No plant data available."

    # Fetch raw fish data (last 10 records)
    fish_rows = get_fish_data_from_db(10)
    if fish_rows:
        fish_data_info = "\n".join(
            [f"turbidity: {row[1]}, waterTemperature: {row[2]}, ph: {row[3]}, created_at: {row[4].strftime('%Y-%m-%d %H:%M:%S')}" for row in fish_rows]
        )
    else:
        fish_data_info = "No fish data available."

    sensor_data_info = "Plant Data:\n" + plant_data_info + "\n\nFish Data:\n" + fish_data_info

    # Prompt Template for Gemini AI
    prompt_template = """You are an AI chatbot that provides helpful information about how to care for aquaponic systems.
You will provide information and suggestions to users about their aquaponic systems. Answer in a simple way and if the user is asking for
instructions, answer it in a clear and step by step manner. Make it as descriptive but as simple as possible.

Conversation History:
{history}

Sensor Data:
{sensor_data}

User: {query}
Bot:"""

    conversation_history = "\n".join([f"User: {m['query']}\nBot: {m['response']}" for m in messages])
    full_query = prompt_template.format(history=conversation_history, sensor_data=sensor_data_info, query=query)

    # Configure Gemini AI
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    generation_config = {
        "temperature": 0.5,
        "top_p": 0.9,
    }

    response = model.generate_content(full_query, generation_config=generation_config).to_dict()
    bot_reply = "I couldn't generate a response."

    try:
        bot_reply = response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass

    messages.append({"query": query, "response": bot_reply})
    table.put_item(Item={"session_id": session_id, "messages": messages})

    return jsonify({"status": "success", "session_id": session_id, "response": bot_reply})

@app.route('/chat', methods=['GET'])
def get_chat_by_session_id():
    session_id = request.args.get('session_id')
    if session_id is None:
        return jsonify({"status": "error", "message": "Invalid session_id"})
    dynamodb = get_dynamodb()
    table = dynamodb.Table(os.getenv("DYNAMODB_TABLE"))
    current_session = table.get_item(Key={"session_id": session_id})
    messages = current_session.get("Item", {}).get("messages", [])
    return jsonify({"status": "success", "session_id": session_id, "messages": messages})

@app.route('/chat', methods=['DELETE'])
def delete_chat_by_session_id():
    session_id = request.args.get('session_id')
    if session_id is None:
        return jsonify({"status": "error", "message": "Invalid session_id"})
    dynamodb = get_dynamodb()
    table = dynamodb.Table(os.getenv("DYNAMODB_TABLE"))
    table.delete_item(Key={"session_id": session_id})
    return jsonify({"status": "success", "message": "Session deleted"})

# ------------------------
# NOTIFICATION API
# ------------------------
def is_number_verified(number, sns_client):
    """Check if the phone number is already verified in SNS Sandbox."""
    print(number)
    try:
        response = sns_client.list_sms_sandbox_phone_numbers()
        print("Verified numbers:", response.get("PhoneNumbers", []))
        for numbernum in response.get("PhoneNumbers", []):
            print(numbernum["PhoneNumber"])
            if number == numbernum["PhoneNumber"]:
                return True
        return False
    except Exception as e:
        print("Error checking verification status:", e)
        return False

def request_verification(number, sns_client):
    """Request verification for an unverified phone number."""
    try:
        response = sns_client.create_sms_sandbox_phone_number(PhoneNumber=number)
        print("Verification request sent:", response)
        return True
    except Exception as e:
        print("Error requesting verification:", e)
        return False

@app.route('/notify', methods=['POST'])
def notify():
    try:
        number = "+" + request.args.get('number')
        body = request.json
        message = body.get("message")
        sns_client = get_sns()

        if not number:
            return jsonify({"status": "error", "message": "Phone number is required"}), 400

        response = sns_client.publish(
            PhoneNumber=number,
            Message=message
        )
        return jsonify({"status": "success", "data": {"number": number, "message": message, "message_id": response["MessageId"]}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Reset turbidity history and threshold values if needed
    ldr_value_prev = 0
    turbidity_history = []
    turbidity_treshold = 250
    server = pywsgi.WSGIServer(("0.0.0.0", 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
