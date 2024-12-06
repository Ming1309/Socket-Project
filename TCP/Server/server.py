import os
import socket
import threading
import logging
import json

# Setup basic logging
logging.basicConfig(level=logging.INFO)

HOST = socket.gethostbyname(socket.gethostname())
PORT = 65432

FILE_LIST = "file_list.json"
FILE_DIRECTORY = "files"
CHUNK_SIZE = 1024 * 1024  
MAX_CHUNK_SIZE = 4 * 1024 * 1024

def load_file_list():
    """Load the list of available files from a JSON file."""
    # Check if the file specified by FILE_LIST is exists. If it does not, logs an error message and return empty
    if not os.path.exists(FILE_LIST):
        logging.error(f"{FILE_LIST} not found. Exiting...")
        return {}
    # Open the file in read mode then tries to load the contents of the file
    try:
        with open(FILE_LIST, 'r') as file:
            return json.load(file)
    except json.JSONDecodeError:
        logging.error(f"Error decoding {FILE_LIST}. Exiting...")
        return {}

def send_file(client_socket, file_name, offset, chunk_size):
    """Send the requested file chunk to the client."""
    try:
        # Construct the file path
        file_path = os.path.join(FILE_DIRECTORY, file_name)

        # Validate file existence
        if not os.path.exists(file_path):
            client_socket.sendall(b"File not found")
            return
        
        # Validate offset
        file_size = os.path.getsize(file_path)
        if offset >= file_size:
            client_socket.sendall(b"Offset exceeds file size")
            return
        
        # Enforce maximum chunk size
        chunk_size = min(chunk_size, MAX_CHUNK_SIZE)

        # Send the file chunk
        with open(file_path, 'rb') as file:
            file.seek(offset)
            bytes_sent = 0
            while bytes_sent < chunk_size:
                data = file.read(min(chunk_size - bytes_sent, CHUNK_SIZE))
                if not data:
                    break
                client_socket.sendall(data)
                bytes_sent += len(data)
                logging.info(f"Sent {len(data)} bytes of {file_name} from offset {offset}")
                offset += len(data)
    except Exception as e:
        logging.error(f"Error sending file {file_name}: {e}")

def handle_client(client_socket, addr, file_list):
    """Handle individual client requests."""
    try:
        logging.info(f"Connection from {addr}")
        request = client_socket.recv(1024).decode()

        try:
            request_data = json.loads(request)
        except json.JSONDecodeError:
            client_socket.sendall(b"Invalid JSON format")
            return

        # Validate protocol fields
        if 'file_name' not in request_data:
            client_socket.sendall(b"Invalid request format")
            return

        file_name = request_data['file_name']

        if 'action' in request_data and request_data['action'] == 'size':
            # Handle file size request
            file_path = os.path.join(FILE_DIRECTORY, file_name)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                client_socket.sendall(str(file_size).encode())
            else:
                client_socket.sendall(b"File not found")
        else:
            # Handle file chunk request
            if 'offset' not in request_data:
                client_socket.sendall(b"Invalid request format")
                return

            offset = request_data['offset']
            chunk_size = request_data.get('chunk_size', CHUNK_SIZE)

            # Process file request
            if file_name in file_list:
                send_file(client_socket, file_name, offset, chunk_size)
            else:
                client_socket.sendall(b"File not found")
    except Exception as e:
        logging.error(f"Error handling client {addr}: {e}")
    finally:
        client_socket.close()
        logging.info(f"Connection to {addr} closed")

def start_server():
    """Start the file server."""
    file_list = load_file_list()
    if not file_list:
        logging.error("No files available to serve. Exiting...")
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, PORT))
            s.listen()
            logging.info(f"Server listening on {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr, file_list))
                client_thread.start()
        except socket.error as e:
            logging.error(f"Socket error: {e}")

if __name__ == "__main__":
    start_server()
