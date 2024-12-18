import os
import json 
import time 
import socket
import logging
import hashlib
import threading
from tqdm import tqdm  

# Configuration
SERVER_HOST = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 65432
SERVER_PORTS = [54000, 55000, 56000, 57000]
BUFFER_SIZE = 65535 
DOWNLOAD_FOLDER = "downloads"
INPUT_FILE = "input.txt"
TIMEOUT = 2

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_checksum(data):
    """Generate checksum using SHA-256"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()

class ReliablePacket:
    def __init__(self, chunk_id, seq_num, data):
        """
        Initializes a ReliablePacket instance.
        :param chunk_id: ID of chunk
        :param seq_num: Sequence number of the packet
        :param data: Data of the packet
        """
        if not isinstance(data, bytes):
            raise TypeError("data must be of type 'bytes'")
        
        self.chunk_id = chunk_id  
        self.seq_num = seq_num 
        self.data = data 
        self.checksum = generate_checksum(data)

    def serialize(self):
        """Serializes the ReliablePacket instance into a JSON string.
        
        :return: JSON string representation of the packet, encoded as bytes"""
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


def download_chunk(filename, chunk_id, offset, chunk_size, server_port):
    """Downloads a chunk of a file."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT)
    server_address = (SERVER_HOST, server_port)
    seq_num = offset
    conditionStop = offset + chunk_size 
    progress_bar = tqdm(total=chunk_size, desc=f"Chunk {chunk_id}", unit="B", unit_scale=True, leave=False)

    try:
        with open(f"{DOWNLOAD_FOLDER}/{filename}_part_{chunk_id}", "wb") as file:
            while offset < conditionStop:
                part_size = min(1024, conditionStop - offset)
                request = f"DOWNLOAD|{filename}|{offset}|{part_size}|{seq_num}|{chunk_id}".encode()
                client_socket.sendto(request, server_address)

                try:
                    response, _ = client_socket.recvfrom(BUFFER_SIZE)
                    packet = ReliablePacket.deserialize(response)
                    if packet.chunk_id == chunk_id and packet.seq_num == seq_num:
                        if packet.checksum == generate_checksum(packet.data):
                            file.write(packet.data)
                            client_socket.sendto(f"ACK_{chunk_id}_{seq_num}".encode(), server_address)
                            seq_num += 1
                            offset += part_size
                            progress_bar.update(part_size) 
                        else:
                            logging.warning(f"Checksum mismatch for chunk {chunk_id}, seq_num {seq_num}")
                            client_socket.sendto(f"NACK_{chunk_id}_{seq_num}".encode(), server_address)
                except socket.timeout:
                    logging.warning(f"Timeout for chunk {chunk_id}, seq_num {seq_num}, size {part_size}")
    except Exception as e:
        logging.error(f"Error in download_chunk: {e}")
    finally:
        progress_bar.close()  
        client_socket.close()

def download_file(file_list, filename):
    """Manages the file download."""
    file_size = file_list[filename]
    chunk_size = file_size // 4
    threads = []
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    for chunk_id in range(4):
        offset = chunk_id * chunk_size
        chunk_size = chunk_size if chunk_id != 3 else file_size - offset
        server_port = SERVER_PORTS[chunk_id]
        thread = threading.Thread(target=download_chunk, args=(filename, chunk_id, offset, chunk_size, server_port))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
    
    time.sleep(1)
    
    try:
        with open(f"{DOWNLOAD_FOLDER}/{filename}", "wb") as final_file:
            for chunk_id in range(4):
                with open(f"{DOWNLOAD_FOLDER}/{filename}_part_{chunk_id}", "rb") as part_file:
                    final_file.write(part_file.read())
                os.remove(f"{DOWNLOAD_FOLDER}/{filename}_part_{chunk_id}")
    except Exception as e:
        print(f'Lỗi không thể gộp được file {filename}')
    finally:
        print()
        print(f" Tải file {filename} thành công!\n")
        print()

def request_file_list():
    """Retrieve the list of available files from the server and display this information."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (SERVER_HOST, SERVER_PORTS[0])
    client_socket.settimeout(TIMEOUT)

    try:
        client_socket.sendto("LIST".encode(), server_address)
        response, _ = client_socket.recvfrom(BUFFER_SIZE)
        file_list_str = response.decode()
        file_list = {line.split()[0]: int(line.split()[1]) for line in file_list_str.split("\n") if line.strip()}
        return file_list
    except Exception as e:
        logging.error(f"Error requesting file list: {e}")
        return {}
    finally:
        client_socket.close()

def read_input_file():
    try:
        with open(INPUT_FILE, "r") as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        return []

def main(): 
    downloaded_files = set()
    file_list = request_file_list()
    print("\nDanh sách file từ server:")
    for file_name, size in file_list.items():
        print(f" * {file_name} {size}B")
    print()
    while True:
        try:
            files_to_download = read_input_file()

            for filename in files_to_download:
                if filename in downloaded_files:
                    continue
                
                if filename in file_list:
                    download_file(file_list, filename)
                    downloaded_files.add(filename)  
                else:
                    logging.warning(f"File {filename} is not on the server. Skipping...")
            
            logging.info("Complete the current list. Wait 5 seconds before checking again...")
            time.sleep(5)

        except KeyboardInterrupt:
            logging.info("Client shut down gracefully.")
            break

if __name__ == "__main__":
    main()
