from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

import psycopg2
from uuid import uuid4

from src.config import get_dynamodb, get_sns
from src.services.database import get_plant_data_from_db, get_fish_data_from_db, insert_plant_data_into_db, insert_fish_data_into_db

import google.generativeai as genai

from dotenv import load_dotenv
import os
from datetime import datetime
        

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
import pytz



load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", allow_upgrades=True, ping_timeout=10, ping_interval=5)

@app.route('/')
def home():
    return "Hello, World" \
    "" \
    "!"

# PLANT DATA ENDPOINTS
ph_tz = pytz.timezone("Asia/Manila")

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

# FISH DATA ENDPOINTS
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
        
        socketio.emit('fish_data', fish_data)
        return jsonify({"status": "success", "data": fish_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@socketio.on('connect')
def handle_connect():
    print("A client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("A client disconnected")


# GEMINI AI CONVERSATION API
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

    # **Prompt Template**
    prompt_template = """You are an AI chatbot that provides helpful information about how to care for aquaponic systems.
    You will provide information and suggestions to users about their aquaponic systems.
    
    Conversation History:
    {history}

    User: {query}
    Bot:"""

    conversation_history = "\n".join([f"User: {m['query']}\nBot: {m['response']}" for m in messages])

    # **Formatted Prompt for AI**
    full_query = prompt_template.format(history=conversation_history, query=query)

    # **Configure Gemini AI**
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    generation_config = {
        "max_output_tokens": 100,  # Limit response to 50 tokens
        "temperature": 0.5,  # Medium randomness
        "top_p": 0.9,  # High diversity
    }

    response = model.generate_content(full_query, generation_config=generation_config).to_dict()
    bot_reply = "I couldn't generate a response."

    try:
        bot_reply = response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass

    # **Store the new message in the session**
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

# NOTIFICATION API
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
        response = sns_client.create_sms_sandbox_phone_number(
            PhoneNumber=number
        )
        print("Verification request sent:", response)
        return True
    except Exception as e:
        print("Error requesting verification:", e)
        return False

@app.route('/notify', methods=['POST'])
def notify():
    number = "+" + request.args.get('number')
    body = request.json
    message = body.get("message")
    sns_client = get_sns()

    if not number:
        return jsonify({"status": "error", "message": "Phone number is required"}), 400

    if not is_number_verified(number = number, sns_client = sns_client):
        success = request_verification(number = number, sns_client = sns_client)
        if success:
            return jsonify({"status": "pending_verification", "message": "Verification code sent. Approve in AWS Console."}), 202
        else:
            return jsonify({"status": "error", "message": "Failed to request verification"}), 500

    try:
        response = sns_client.publish(
            PhoneNumber=number,
            Message=message
        )
        return jsonify({"status": "success", "data": {"number": number, "message": message, "message_id": response["MessageId"]}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
if __name__ == "__main__":
    server = pywsgi.WSGIServer(("0.0.0.0", 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
