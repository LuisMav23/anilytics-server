import socketio

# Create a Socket.IO client instance
sio = socketio.Client()

@sio.event
def connect():
    print("Connected to the Socket.IO server.")

@sio.event
def disconnect():
    print("Disconnected from the Socket.IO server.")

@sio.event
def message(data):
    print("Message received:", data)

@sio.event
def turbidity(data):
    print("Turbidity event received:", data)

@sio.event
def change_water(data):
    print("Change water event received:", data)

def main():
    url = "http://ec2-18-139-217-2.ap-southeast-1.compute.amazonaws.com"
    try:
        sio.connect(url)
        sio.wait()  # Keep the client running to listen for events
    except Exception as e:
        print("Connection error:", e)

if __name__ == "__main__":
    main()