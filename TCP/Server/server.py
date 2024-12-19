import os
import socket
import logging
import threading
import signal

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Server configuration
HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345

FILE_LIST_PATH = "file_list.txt"
SERVER_FILES_DIR = "files"
BUFFER_SIZE = 4096

# To gracefully stop the server
server_running = True

def signal_handler(sig, frame):
    """Handle interrupt signal to shut down the server gracefully."""
    global server_running
    logging.info("Signal received. Shutting down the server...")
    server_running = False

def load_file_list():
    """Load the list of available files from a TXT file."""
    if not os.path.exists(FILE_LIST_PATH):
        logging.error(f"{FILE_LIST_PATH} not found. Exiting...")
        return {}
    file_list = {}
    with open(FILE_LIST_PATH, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 2:
                file_name, file_size = parts
                file_list[file_name] = int(file_size)
    return file_list

def update_file_list():
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)
    file_list = {}

    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            file_list[file_name] = os.path.getsize(file_path)
        else:
            logging.warning(f"Skipping non-file item: {file_name}")
    try:
        with open(FILE_LIST_PATH, "w") as f:
            for file_name, file_size in file_list.items():
                f.write(f"{file_name} {file_size}\n")
        logging.info(f"File list successfully updated in {FILE_LIST_PATH}")
    except Exception as e:
        logging.error(f"Error writing to {FILE_LIST_PATH}: {e}")
    return file_list

def send_chunk(client_socket, file_path, offset, chunk_size):
    """Send a chunk of data from a file to a client over a socket connection."""
    try:
        with open(file_path, "rb") as f:
            f.seek(offset)
            data = f.read(chunk_size)
        client_socket.sendall(data)
    except Exception as e:
        logging.error(f"Error sending chunk: {e}")
        try:
            client_socket.sendall(b"ERROR: Unable to send chunk")
        except Exception as send_error:
            logging.error(f"Error sending error message to client: {send_error}")

def handle_client(client_socket, address):
    """Handle requests from a client."""
    logging.info(f"Connected by {address}")
    try:
        while server_running:
            request = client_socket.recv(BUFFER_SIZE).decode()
            if not request:
                break
            logging.info(f"Received request from {address}: {request}")
            try:
                if request == "LIST":
                    file_list = load_file_list()
                    if file_list:
                        response = "\n".join([f"{name} {size}" for name, size in file_list.items()])
                    else:
                        response = "NO_FILES_AVAILABLE"
                    client_socket.sendall(response.encode())

                elif request.startswith("DOWNLOAD"):
                    _, file_name, offset, chunk_size = request.split(":")
                    offset = int(offset)
                    chunk_size = int(chunk_size)

                    file_path = os.path.join(SERVER_FILES_DIR, file_name)
                    if not os.path.exists(file_path):
                        client_socket.sendall(b"ERROR: File not found")
                        logging.warning(f"File not found: {file_path}")
                        continue

                    send_chunk(client_socket, file_path, offset, chunk_size)
                    logging.info(f"Sent chunk of file {file_name} to client")
                else:
                    client_socket.sendall(b"ERROR: Unknown request")
                    logging.error(f"Unknown request from {address}: {request}")
            except ValueError as ve:
                client_socket.sendall(b"ERROR: Invalid request format")
                logging.error(f"ValueError while handling request from {address}: {ve}")
            except Exception as e:
                client_socket.sendall(b"ERROR: Internal server error")
                logging.error(f"Exception while handling request from {address}: {e}")

    except socket.error as e:
        logging.error(f"Socket error from {address}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error from {address}: {e}")
    finally:
        try:
            client_socket.close()
            logging.info(f"Closed connection to client {address}")
        except Exception as close_error:
            logging.error(f"Error closing client socket for {address}: {close_error}")

def start_server():
    """Start the server to handle client connections."""
    global server_running
    logging.info("Server is starting.")
    update_file_list()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen()
            logging.info(f"Server listening on {HOST}:{PORT}")
            while server_running:
                try:
                    server_socket.settimeout(1.0)  # Prevent blocking during shutdown
                    client_socket, addr = server_socket.accept()
                    logging.info(f"Connection from {addr}")
                    threading.Thread(target=handle_client, args=(client_socket, addr)).start()
                except socket.timeout:
                    continue
        except Exception as e:
            logging.error(f"Error in server: {e}.")
        finally:
            server_socket.close()
            logging.info("Server socket closed.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    start_server()
