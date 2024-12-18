import os
import sys
import json
import time
import signal
import socket 
import hashlib
import logging
import threading 

# Configuration
HOST = socket.gethostbyname(socket.gethostname())  
PORTS = [54000, 55000, 56000, 57000] 
BUFFER_SIZE = 65535  
FILE_LIST_PATH = "file_list.txt"  
FILES_DIR = "files"  
MAX_RETRIES = 15  
TIMEOUT = 2  
stop_event = threading.Event()

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_file_list():
    """Load the list of available files from a TXT file."""
    file_list = {}
    try:
        with open(FILE_LIST_PATH, "r") as f:
            for line in f.readlines():
                name, size = line.strip().split() 
                file_list[name] = int(size)
        logging.info(f"Loaded file list: {file_list}")
    except FileNotFoundError:
        logging.error("File list not found.")
    return file_list

def update_file_list():
    """Updates the list of available files on the server and writing the file names and their sizes to a file."""
    if not os.path.exists(FILES_DIR):
        os.makedirs(FILES_DIR)
    file_list = {}

    for file_name in os.listdir(FILES_DIR):
        file_path = os.path.join(FILES_DIR, file_name)
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

# Load the list of available files
file_list = load_file_list()

def generate_checksum(data):
    """Generate checksum using SHA-256"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()

class ReliablePacket:
    def __init__(self, chunk_id, seq_num, data):
        """
        Initializes a ReliablePacket instance.
        
        :param chunk_id: ID of the chunk
        :param seq_num: Sequence number of the packet
        :param data: Data of the packet (must be bytes)
        """
        if not isinstance(data, bytes):
            raise TypeError("Data must be of type 'bytes'")
        
        self.chunk_id = chunk_id  
        self.seq_num = seq_num  
        self.data = data  
        self.checksum = generate_checksum(data)  

    def serialize(self):
        """
        Serializes the ReliablePacket instance into a JSON string.
        
        :return: JSON string representation of the packet, encoded as bytes
        """
        return json.dumps({
            'chunk_id': self.chunk_id,
            'seq_num': self.seq_num,
            'data': self.data.decode('latin-1'),  
            'checksum': self.checksum
        }).encode('utf-8') 

    @classmethod
    def deserialize(cls, packet_bytes):
        """
        Deserializes bytes into a ReliablePacket instance.
        
        :param packet_bytes: Bytes representation of the packet
        :return: ReliablePacket instance
        """
        packet_dict = json.loads(packet_bytes.decode('utf-8'))  
        return cls(
            chunk_id=packet_dict['chunk_id'],
            seq_num=packet_dict['seq_num'],
            data=packet_dict['data'].encode('latin-1')  
        )

def handle_list_request(socket, addr):
    """Processes a client's request to list the available files on the server"""
    file_list_str = "\n".join([f"{name} {size}" for name, size in file_list.items()])  
    socket.sendto(file_list_str.encode(), addr)  
    logging.info(f"Sent file list to {addr}")


def handle_download_request(socket, addr, data):
    """Handles a client's request to download a file chunk."""
    try:
        request = data.decode().split("|")
        _, filename, offset, size, seq_num, chunk_id = request
        offset, size, seq_num, chunk_id = int(offset), int(size), int(seq_num), int(chunk_id)

        file_path = os.path.join(FILES_DIR, filename)
        if not os.path.exists(file_path):
            socket.sendto(b"ERR_FILE_NOT_FOUND", addr)
            return
        if size <= 0:
            raise ValueError(f"Invalid read size: {size}. Must be > 0 or -1.")
        with open(file_path, "rb") as f:
            f.seek(offset)
            part_data = f.read(size)
            if not part_data:
                logging.warning(f"Read empty data for chunk_id={chunk_id}, offset={offset}, size={size}")
                return 
        if not isinstance(part_data, bytes):
            raise TypeError("Data read from file is not in bytes format.")

        packet = ReliablePacket(chunk_id=chunk_id, seq_num=seq_num, data=part_data)

        retries = 0
        while retries < MAX_RETRIES:
            try:
                socket.sendto(packet.serialize(), addr)
                ack_data, _ = socket.recvfrom(BUFFER_SIZE)
                ack = ack_data.decode()
                if ack == f"ACK_{chunk_id}_{seq_num}":
                    logging.info(f"Successfully sent seq_num={seq_num} for chunk {chunk_id}")
                    return
                else:
                    logging.warning(f"Incorrect ACK received: {ack}")
                    retries += 1
            except socket.timeout:
                logging.warning(f"Timeout for seq_num={seq_num}, retrying...")
                retries += 1
    except Exception as e:
        logging.error(f"Error in handle_download_request: {e}")


def handle_client(port):
    """Handles client requests on a specific port."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, port))

    logging.info(f"Server started on port {port}")

    try:
        while not stop_event.is_set():
            server_socket.settimeout(1)  
            try:
                data, addr = server_socket.recvfrom(BUFFER_SIZE)
                request = data.decode().split("|")[0]

                if request == "LIST":
                    handle_list_request(server_socket, addr)
                elif request == "DOWNLOAD":
                    handle_download_request(server_socket, addr, data)
                else:
                    logging.warning(f"Invalid request from {addr}")
            except socket.timeout:
                continue
    except Exception as e:
        logging.error(f"Error handling client on port {port}: {e}")
    finally:
        server_socket.close()

def signal_handler(sig, frame):
    """Handles the interrupt signal to gracefully shut down the server."""
    logging.info("Interrupt received, shutting down...")
    stop_event.set()
    sys.exit(0)

def start_server():
    """Starts the server and handles multiple ports."""
    signal.signal(signal.SIGINT, signal_handler)
    update_file_list()
    threads = []
    try:
        for port in PORTS:
            thread = threading.Thread(target=handle_client, args=(port,))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Server interrupted by user.")
        stop_event.set() 
    finally:
        for thread in threads:
            thread.join()
        logging.info("Server shut down gracefully.")

if __name__ == "__main__":
    start_server()

