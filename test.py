import socketio

# Define API and WebSocket URLs
API_URL = "http://ec2-18-139-217-2.ap-southeast-1.compute.amazonaws.com/plant_data"
WEBSOCKET_URL = "http://ec2-18-139-217-2.ap-southeast-1.compute.amazonaws.com"  # No need for /socket.io

# Initialize Socket.IO client
sio = socketio.Client()

@sio.event
def connect():
    print("Connected to WebSocket server!")

@sio.on('plant_data')
def on_message(data):
    print("Received real-time data:", data)

@sio.event
def disconnect():
    print("Disconnected from WebSocket server")

# Connect to the WebSocket server
sio.connect(WEBSOCKET_URL)

# Keep the connection open to listen for messages
sio.wait()
