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

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", allow_upgrades=True, ping_timeout=10, ping_interval=5)

# Replace with your RDS details
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("RDS_PSQL_HOST"), # anilytics-pgsql.c38ygweaynwh.ap-southeast-1.rds.amazonaws.com
        user=os.getenv("RDS_PSQL_USER"), # postgres
        password=os.getenv("RDS_PSQL_PASS"), # LuisMaverick2323_
        dbname=os.getenv("RDS_PSQL_DB"), # anilytics
        port=os.getenv("RDS_PSQL_PORT") # 5432
    )
    return conn

def close_db_connection(conn):
    if conn:
        conn.close()

@app.route('/')
def home():
    return "Hello, Krischan!"

# PLANT DATA ENDPOINTS
@app.route('/plant_data', methods=['GET'])
def get_plant_data():
    try:
        limit = int(request.args.get('limit', 10))
        rows = get_plant_data_from_db(limit)
        formatted_data = []
        for row in rows:
            formatted_data.append({
                "ph": row[1],
                "tds": row[2],
                "temperature": row[3],
                "humidity": row[4],
                "waterTemperature": row[5],
                "waterLevel": row[6],
                "temperatureStatus": row[7],
                "humidityStatus": row[8],
                "waterTemperatureStatus": row[9],
                "tdsStatus": row[10],
                "phStatus": row[11],
                "waterLevelStatus": row[12]
            })
        return jsonify(formatted_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/plant_data', methods=['POST'])
def receive_plant_data():
    try:
        data = request.json
        if (data.get('ph') is None or data.get('tds') is None or 
            data.get('temperature') is None or data.get('humidity') is None or
            data.get('waterTemperature') is None or data.get('waterLevel') is None or
            data.get('temperatureStatus') is None or data.get('humidityStatus') is None or
            data.get('waterTemperatureStatus') is None or data.get('tdsStatus') is None or
            data.get('phStatus') is None or data.get('waterLevelStatus') is None):
            return jsonify({"status": "error", "message": "Invalid data format"})
        
        print(f"Received from ESP32: {data}")
        if not insert_plant_data_into_db(data):
            return jsonify({"status": "error", "message": "Error inserting data into database"})
        
        sensor_data = {
            "ph": data.get("ph"),
            "tds": data.get("tds"),
            "temperature": data.get("temperature"),
            "humidity": data.get("humidity"),
            "waterTemperature": data.get("waterTemperature"),
            "waterLevel": data.get("waterLevel"),
            "temperatureStatus": data.get("temperatureStatus"),
            "humidityStatus": data.get("humidityStatus"),
            "waterTemperatureStatus": data.get("waterTemperatureStatus"),
            "tdsStatus": data.get("tdsStatus"),
            "phStatus": data.get("phStatus"),
            "waterLevelStatus": data.get("waterLevelStatus")
        }
        print("Sensor Data:", sensor_data)
        
        # Broadcast to all connected clients
        socketio.emit('plant_data', sensor_data)

        return jsonify({"status": "success", "data": sensor_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# FISH DATA ENDPOINTS
@app.route('/fish_data', methods=['GET'])
def get_fish_data():
    try:
        limit = int(request.args.get('limit', 10))
        rows = get_fish_data_from_db(limit)
        formatted_data = []
        for row in rows:
            formatted_data.append({
                "waterLevel": row[1],
                "ph": row[2],
                "turbidity": row[3],
                "waterLevelStatus": row[4],
                "phStatus": row[5],
                "turbidityStatus": row[6]
            })
        return jsonify(formatted_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/fish_data', methods=['POST'])
def receive_fish_data():
    try:
        data = request.json
        if (data.get('waterLevel') is None or 
            data.get('ph') is None or data.get('turbidity') is None or 
            data.get('waterLevelStatus') is None or 
            data.get('phStatus') is None or data.get('turbidityStatus') is None):
            return jsonify({"status": "error", "message": "Invalid data format"})
        
        
        print(f"Received from ESP32: {data}")
        if not insert_fish_data_into_db(data):
            return jsonify({"status": "error", "message": "Error inserting data into database"})
        
        fish_data = {
            "waterLevel": data.get("waterLevel"),
            "ph": data.get("ph"),
            "turbidity": data.get("turbidity"),
            "waterLevelStatus": data.get("waterLevelStatus"),
            "phStatus": data.get("phStatus"),
            "turbidityStatus": data.get("turbidityStatus")
        }
        
        socketio.emit('fish_data', fish_data)
        return jsonify({"status": "success", "data": fish_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

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
    message = "Hello, World!"
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
