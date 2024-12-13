import socket
import logging
import threading
import os

# Setup basic logging
logging.basicConfig(level=logging.INFO)

HOST = socket.gethostbyname(socket.gethostname())
PORT = 65432

FILE_LIST_PATH = "file_list.txt"
SERVER_FILES_DIR = "files"

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
                try:
                    file_list[file_name] = int(file_size)
                except ValueError:
                    logging.warning(f"Skipping line due to invalid file size: {line.strip()}")
                    continue
    return file_list


def send_chunk(client_socket, file_path, offset, chunk_size):
    """Send a chunk of data from a file to a client over a socket connection."""
    try:
        with open(file_path, "rb") as f:
            f.seek(offset)
            data = f.read(chunk_size)

        # Prepare and send header and data
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
    logging.info(f"Handling client {address}")
    file_list = load_file_list()
    try:
        while True:
            try:
                request = client_socket.recv(1024).decode()
                if not request:
                    break

                logging.info(f"Received request: {request}")

                if request == "LIST":
                    response = "\n".join([f"{name} {size}" for name, size in file_list.items()])
                    client_socket.sendall(response.encode())
                    logging.info("Sent file list to client")

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
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)

    file_list = {}
    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            file_list[file_name] = os.path.getsize(file_path)

    # Update the file list in the text file
    with open(FILE_LIST_PATH, "w") as f:
        for file_name, file_size in file_list.items():
            f.write(f"{file_name} {file_size}\n")

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        logging.info(f"Server listening on {HOST}:{PORT}")

        while True:
            client_socket, address = server_socket.accept()
            logging.info(f"Connection from {address}")
            threading.Thread(target=handle_client, args=(client_socket, address)).start()
    except KeyboardInterrupt:
        logging.info("Server interrupted by user")
    except Exception as e:
        logging.error(f"Error in server: {e}")
    finally:
        server_socket.close()
        logging.info("Server socket closed")

if __name__ == "__main__":
    start_server()
