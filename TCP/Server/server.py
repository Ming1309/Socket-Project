import socket
import logging
import threading
import os

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Server configuration
HOST = socket.gethostbyname(socket.gethostname())
PORT = 65432

FILE_LIST_PATH = "file_list.txt"
SERVER_FILES_DIR = "files"
BUFFER_SIZE = 1024

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
                file_name, file_size_str = parts
                try:
                    if file_size_str.endswith("KB"):
                        file_size = float(file_size_str[:-2]) * 1024
                    elif file_size_str.endswith("MB"):
                        file_size = float(file_size_str[:-2]) * 1024 * 1024
                    elif file_size_str.endswith("GB"):
                        file_size = float(file_size_str[:-2]) * 1024 * 1024 * 1024
                    elif file_size_str.endswith("b"):
                        file_size = float(file_size_str[:-1])
                    else:
                        logging.warning(f"Skipping line due to invalid file size format: {line.strip()}")
                        continue
                    file_list[file_name] = int(file_size)
                except ValueError:
                    logging.warning(f"Skipping line due to invalid file size: {line.strip()}")
                    continue
    return file_list

def update_file_list():
    # Ensure the directory exists
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)
    file_list = {}

    # Iterate over files in the directory
    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            file_size_b = os.path.getsize(file_path)
            # Determine the most appropriate size unit
            if file_size_b >= 1024 * 1024 * 1024:  
                size = f"{round(file_size_b / (1024 * 1024 * 1024), 2)}GB"
            elif file_size_b >= 1024 * 1024:  
                size = f"{round(file_size_b / (1024 * 1024), 2)}MB"
            elif file_size_b >= 1024: 
                size = f"{round(file_size_b / 1024, 2)}KB"
            else: 
                size = f"{file_size_b}b"
            file_list[file_name] = size
        else:
            logging.warning(f"Skipping non-file item: {file_name}")

    try:
        # Write to the file
        with open(FILE_LIST_PATH, "w") as f:
            for file_name, file_size in file_list.items():
                f.write(f"{file_name} {file_size}\n")
        logging.info(f"File list successfully updated in {FILE_LIST_PATH}")
    except Exception as e:
        logging.error(f"Error writing to {FILE_LIST_PATH}: {e}")
    return file_list

def send_chunk(client_socket, file_name, offset, chunk_size):
    """Send a chunk of data from a file to a client over a socket connection."""
    try:
        with open(file_name, "rb") as f:
            f.seek(offset)
            data = f.read(chunk_size)
        header = f"{offset}:{len(data)}\n".encode()
        client_socket.sendall(header + data)
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
        while True:
            try:
                request = client_socket.recv(BUFFER_SIZE).decode()
                if not request:
                    break
                logging.info(f"Received request: {request}")
                if request == "LIST":
                    file_list = load_file_list()
                    response = "\n".join([f"{name} {size}" for name, size in file_list.items()])
                    logging.info(f"Sending file list: {response}")
                    client_socket.sendall(response.encode())
                elif request.startswith("DOWNLOAD"):
                    try:
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
                    except ValueError:
                        client_socket.sendall(b"ERROR: Invalid request format")
                        logging.error("Invalid request format")
                else:
                    client_socket.sendall(b"ERROR: Unknown request")
                    logging.error("Unknown request")
            except socket.error as e:
                if e.errno == 54:  # Connection reset by peer
                    logging.error(f"Connection reset by peer: {address}")
                    break
                else:
                    raise
    except Exception as e:
        logging.error(f"Error handling client {address}: {e}")
    finally:
        try:
            client_socket.close()
            logging.info(f"Closed connection to client {address}")
        except Exception as close_error:
            logging.error(f"Error closing client socket for {address}: {close_error}")

def start_server():
    """Start the server to handle client connections."""
    logging.info("[STARTING] Server is starting.")
    update_file_list()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        try:
            server_socket.bind((HOST, PORT))
            server_socket.listen()
            logging.info(f"Server listening on {HOST}:{PORT}")
            while True:
                conn, addr = server_socket.accept()
                logging.info(f"Connection from {addr}")
                threading.Thread(target=handle_client, args=(conn, addr)).start()
        except Exception as e:
            logging.error(f"Error in server: {e}.")
        except KeyboardInterrupt:
            logging.info("Server interrupted by user.")
        finally:
            server_socket.close()
            logging.info("Server socket closed.")

if __name__ == "__main__":
    start_server()
