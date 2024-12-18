import socket 
import os
import hashlib
import json
import logging
import threading 
import signal
import sys

# Cấu hình cho server
HOST = "127.0.0.1"  # Địa chỉ IP của server
PORTS = [54000, 55000, 56000, 57000]  # Danh sách các cổng
BUFFER_SIZE = 65535  # Giới hạn tối đa cho một gói UDP
FILE_LIST_PATH = "file_list.txt"  # Đường dẫn tới file chứa danh sách tệp
FILES_DIR = "files"  # Thư mục chứa các tệp
MAX_RETRIES = 15  # Số lần thử lại tối đa
TIMEOUT = 2  # Thời gian chờ tối đa (giây)
stop_event = threading.Event()

# Cấu hình logging để ghi lại thông tin hoạt động của server
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Hàm tải danh sách tệp từ file "file_list.txt"
def load_file_list():
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

# Tải danh sách tệp khi server khởi động
file_list = load_file_list()

#Hàm tính checksum 
def generate_checksum(data):
    """Sinh checksum bằng SHA-256"""
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()

class ReliablePacket:
    def __init__(self, chunk_id, seq_num, data):
        """
        :param chunk_id: ID của chunk
        :param seq_num: Số thứ tự gói tin
        :param data: Dữ liệu của gói tin
        """
        if not isinstance(data, bytes):
            raise TypeError("data must be of type 'bytes'")
        
        self.chunk_id = chunk_id  # ID của chunk
        self.seq_num = seq_num  # Số thứ tự của gói tin
        self.data = data  # Dữ liệu của gói tin (bytes)
        self.checksum = generate_checksum(data)  # Tính checksum

    def serialize(self):
        """
        Chuyển đổi đối tượng ReliablePacket thành chuỗi JSON để gửi qua mạng.
        """
        return json.dumps({
            'chunk_id': self.chunk_id,
            'seq_num': self.seq_num,
            'data': self.data.decode('latin-1'),  # Dữ liệu (bytes) chuyển thành string
            'checksum': self.checksum
        }).encode('utf-8')  # Mã hóa JSON thành bytes

    @classmethod
    def deserialize(cls, packet_bytes):
        """
        Giải mã từ bytes thành đối tượng ReliablePacket.
        """
        packet_dict = json.loads(packet_bytes.decode('utf-8'))  # Giải mã JSON từ bytes
        return cls(
            chunk_id=packet_dict['chunk_id'],
            seq_num=packet_dict['seq_num'],
            data=packet_dict['data'].encode('latin-1')  # Chuyển string về bytes
        )

# Hàm xử lý yêu cầu danh sách tệp từ client
def handle_list_request(socket, addr):
    # Lấy danh sách tệp từ file_list.txt
    file_list_str = "\n".join([f"{name} {size}" for name, size in file_list.items()])  # Bao gồm cả kích thước
    socket.sendto(file_list_str.encode(), addr)  # Gửi danh sách tệp cho client
    logging.info(f"Sent file list to {addr}")


def handle_download_request(socket, addr, data):
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
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, port))

    logging.info(f"Server started on port {port}")

    try:
        while not stop_event.is_set():
            server_socket.settimeout(1)  # Set a timeout to avoid hanging
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
    logging.info("Interrupt received, shutting down...")
    stop_event.set()
    sys.exit(0)

# Khởi động server với nhiều cổng
def start_server():
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
    except KeyboardInterrupt:
        logging.info("Server interrupted by user.")
    finally:
        logging.info("Server shut down gracefully.")


if __name__ == "__main__":
    start_server()

    #Danh sách các biến 
# seq_num: Số thứ tự của mỗi gói tin (packet), giúp xác định vị trí của gói tin trong quá trình truyền tải dữ liệu.
# file_list: Dictionary lưu trữ danh sách các tệp có sẵn trên server, với tên tệp là key và kích thước (byte) là value.
# filename: Tên của tệp mà client yêu cầu tải.
# server_address: Địa chỉ và cổng của server mà client sẽ kết nối.
# file_path: Đường dẫn tuyệt đối đến tệp trên server mà client yêu cầu tải.
# chunk_size: Kích thước của mỗi chunk (phần lớn của tệp) mà server chia tệp thành để gửi.
# total_data: Dữ liệu của một chunk sau khi tất cả các phần của chunk được tải về từ tệp.
# retries: Số lần thử lại nếu không nhận được ACK từ client khi gửi một phần dữ liệu.
# current_part_size: Kích thước của phần dữ liệu hiện tại trong chunk, giúp chia nhỏ dữ liệu và gửi qua UDP.
# part_offset: Vị trí offset cho mỗi phần nhỏ trong chunk, dùng để tính toán vị trí của phần trong tệp.
# chunk_parts: Dictionary lưu trữ các phần nhỏ của chunk, với seq_num làm key và dữ liệu của phần đó làm value.
# lock: Đối tượng đồng bộ hóa để đảm bảo không có nhiều luồng truy cập đồng thời vào chunk_parts.
# request: Dữ liệu yêu cầu từ client, chứa thông tin về hành động mà client muốn thực hiện ("LIST" hoặc "DOWNLOAD").
# client_socket: Socket UDP được sử dụng để giao tiếp với client, gửi và nhận gói tin.
# part_size: Kích thước mỗi phần nhỏ trong chunk. Mỗi phần nhỏ sẽ được gửi qua UDP, đảm bảo không vượt quá giới hạn UDP.
# file_size: Kích thước tệp mà server sẽ gửi cho client, được tính từ kích thước của tệp trong thư mục server.
# is_last: Cờ để chỉ ra liệu đây có phải là phần cuối cùng của chunk hay không.
# start_time: Thời gian bắt đầu để tính toán thời gian chờ (timeout) khi chờ nhận ACK từ client.
# ack: Biến lưu trữ thông tin xác nhận (ACK) từ client, để xác nhận gói tin đã được nhận thành công.
# part_num: Số thứ tự của phần trong chunk, giúp xác định vị trí của phần trong chuỗi các phần của chunk.
# part_offset: Vị trí bắt đầu của phần trong chunk, giúp xác định chính xác vị trí phần dữ liệu trong tệp.
