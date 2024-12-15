import socket
import threading
import os
import hashlib
import logging

# Configurations
FILE_LIST_PATH = "file_list.txt"
SERVER_FILES_DIR = "server_files"
HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
BUFFER_SIZE = 4096

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load file list
def load_file_list():
    file_list = {}
    if os.path.exists(FILE_LIST_PATH):
        with open(FILE_LIST_PATH, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    file_name, file_size = parts
                    file_list[file_name] = int(file_size)
    logging.info("File list loaded.")
    return file_list

# Update file list
def update_file_list():
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)

    file_list = {}
    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            file_list[file_name] = os.path.getsize(file_path)

    with open(FILE_LIST_PATH, "w") as f:
        for file_name, file_size in file_list.items():
            f.write(f"{file_name} {file_size}\n")
    logging.info("File list updated.")

# Calculate file checksum
def calculate_file_checksum(file_path):
    try:
        with open(file_path, "rb") as f:
            checksum = hashlib.md5(f.read()).hexdigest()
        logging.info(f"Checksum calculated for {file_path}: {checksum}")
        return checksum
    except Exception as e:
        logging.error(f"Error calculating checksum: {e}")
        return None

# Send file chunk
def send_chunk(client_socket, file_path, offset, chunk_size):
    try:
        with open(file_path, "rb") as f:
            f.seek(offset)
            data = f.read(chunk_size)
        client_socket.sendall(data)
        logging.info(f"Sent chunk of size {len(data)} from {file_path} starting at offset {offset}")
    except Exception as e:
        logging.error(f"Error sending chunk: {e}")
        client_socket.sendall(b"ERROR: Unable to send chunk")

# Handle client requests
def handle_client(client_socket, address):
    logging.info(f"Connected to {address}")
    file_list = load_file_list()

    try:
        while True:
            request = client_socket.recv(BUFFER_SIZE).decode()
            if not request:
                break

            if request == "LIST":
                response = "\n".join([f"{name} {size}" for name, size in file_list.items()])
                client_socket.sendall(response.encode())
                logging.info(f"Sent file list to {address}")

            elif request.startswith("CHECKSUM"):
                _, file_name = request.split(":")
                file_path = os.path.join(SERVER_FILES_DIR, file_name)
                if os.path.exists(file_path):
                    checksum = calculate_file_checksum(file_path)
                    client_socket.sendall(checksum.encode())
                    logging.info(f"Sent checksum for {file_name} to {address}")
                else:
                    client_socket.sendall(b"ERROR: File not found")
                    logging.warning(f"File not found: {file_name} requested by {address}")

            elif request.startswith("DOWNLOAD"):
                try:
                    _, file_name, offset, chunk_size = request.split(":")
                    offset = int(offset)
                    chunk_size = int(chunk_size)

                    file_path = os.path.join(SERVER_FILES_DIR, file_name)
                    if not os.path.exists(file_path):
                        client_socket.sendall(b"ERROR: File not found")
                        logging.warning(f"File not found: {file_name} requested by {address}")
                        continue

                    send_chunk(client_socket, file_path, offset, chunk_size)
                    logging.info(f"Sent chunk of {file_name} to {address}")
                except Exception as e:
                    logging.error(f"Error processing download request: {e}")
                    client_socket.sendall(b"ERROR: Invalid request format")
            else:
                client_socket.sendall(b"ERROR: Unknown request")
                logging.warning(f"Unknown request received from {address}: {request}")

    except Exception as e:
        logging.error(f"Error handling client {address}: {e}")
    finally:
        client_socket.close()
        logging.info(f"Connection closed: {address}")

# Server program
def server_program():
    update_file_list()
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    logging.info(f"Server listening on {HOST}:{PORT}")

    try:
        while True:
            client_socket, address = server_socket.accept()
            threading.Thread(target=handle_client, args=(client_socket, address)).start()
    except KeyboardInterrupt:
        logging.info("Server shutting down...")
    finally:
        server_socket.close()

if __name__ == "__main__":
    server_program()
