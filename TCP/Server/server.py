import os
import socket
import threading
import logging
import json

# Setup basic logging
logging.basicConfig(level=logging.INFO)

HOST = socket.gethostbyname(socket.gethostname())
PORT = 8080

FILE_LIST_PATH = "file_list.json"
CHUNK_SIZE = 1024 * 1024  


def load_file_list():
    with open(FILE_LIST_PATH, 'r') as file:
        return json.load(file)

def send_file(client_socket, file_name, offset, chunk_size):
    try:
        file_path = os.path.join("file_list", file_name)  
        with open(file_path, 'rb') as file:
            file.seek(offset)
            while True:
                data = file.read(chunk_size)
                if not data:
                    break
                client_socket.sendall(data)
                logging.info(f"Sent {len(data)} bytes of {file_name} from offset {offset}")
                offset += len(data)
    except Exception as e:
        logging.error(f"Error sending file {file_name}: {e}")

def handle_client(client_socket, addr, file_list):
    try:
        request = client_socket.recv(1024).decode()
        request_data = json.loads(request)
        file_name = request_data['file_name']
        offset = request_data['offset']
        chunk_size = request_data.get('chunk_size', CHUNK_SIZE)

        if file_name in file_list:
            send_file(client_socket, file_name, offset, chunk_size)
        else:
            client_socket.sendall(b"File not found")
    except Exception as e:
        logging.error(f"Error handling client {addr}: {e}")
    finally:
        client_socket.close()

def start_server():
    file_list = load_file_list()
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