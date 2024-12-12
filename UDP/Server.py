# Server.py
import socket
import os
import logging
import hashlib
import time
import threading 
# Cấu hình server
HOST = "127.0.0.1"
PORT = 65432
SERVER_FILES_DIR = "files"
BUFFER_SIZE = 8192
MAX_RETRIES = 15
PACKET_SIZE = 1400

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_file_list():
    """Tải danh sách file từ thư mục files."""
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)
        logging.info(f"Thư mục {SERVER_FILES_DIR} đã được tạo.")

    file_list = {}
    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            file_list[file_name] = {
                'size': os.path.getsize(file_path),
                'checksum': file_hash
            }
            logging.info(f"Tìm thấy file: {file_name}, kích thước: {file_list[file_name]['size']} bytes")
    return file_list

def send_packet_with_ack(server_socket, packet, addr, seq):
    """Gửi một packet và đảm bảo nhận được ACK."""
    for attempt in range(MAX_RETRIES):
        try:
            server_socket.sendto(packet, addr)
            #logging.info(f"Sent packet {seq} to {addr}, waiting for ACK")
            #logging.info(f"Received ACK {ack.decode()} from {addr}")

            server_socket.settimeout(5)
            ack, _ = server_socket.recvfrom(BUFFER_SIZE)
            #logging.info(f"Sent packet {seq} to {addr}, waiting for ACK")
            #logging.info(f"Received ACK {ack.decode()} from {addr}")

            if ack.decode() == f"ACK:{seq}":
                return True
        except socket.timeout:
            logging.warning(f"Retry sending packet {seq}, attempt {attempt + 1}")
    return False

def handle_request(data, addr, server_socket, file_list):
    """Xử lý yêu cầu từ client."""
    try:
        message = data.decode()
        logging.info(f"Nhận yêu cầu từ {addr}: {message}")

        if message == "LIST":
            # Trả về danh sách file với thông tin chi tiết
            response = "\n".join([f"{name} {details['size']} {details['checksum']}" for name, details in file_list.items()])
            server_socket.sendto(response.encode(), addr)

        elif message.startswith("DOWNLOAD"):
            _, file_name, offset, chunk_size, part_num = message.split(":")
            offset = int(offset)
            chunk_size = int(chunk_size)
            part_num = int(part_num)

            if file_name in file_list:
                file_path = os.path.join(SERVER_FILES_DIR, file_name)
                with open(file_path, "rb") as f:
                    f.seek(offset)
                    chunk_data = f.read(chunk_size)

                chunk_checksum = hashlib.md5(chunk_data).hexdigest()
                total_packets = (len(chunk_data) + PACKET_SIZE - 1) // PACKET_SIZE
                base_seq = part_num * 100

                for seq in range(total_packets):
                    start = seq * PACKET_SIZE
                    end = min(start + PACKET_SIZE, len(chunk_data))
                    packet_data = chunk_data[start:end]
                    metadata = f"{base_seq + seq}|{total_packets}|{chunk_checksum}|".encode()
                    packet = metadata + packet_data

                    if not send_packet_with_ack(server_socket, packet, addr, base_seq + seq):
                        logging.error(f"Không thể gửi packet {seq} trong chunk {part_num}.")
                        return
            else:
                server_socket.sendto(b"ERROR: File not found", addr)

    except Exception as e:
        logging.exception("Lỗi xử lý yêu cầu")
        server_socket.sendto(f"ERROR: {str(e)}".encode(), addr)


def handle_client_request(data, addr, server_socket, file_list):
    thread = threading.Thread(target=handle_request, args=(data, addr, server_socket, file_list))
    thread.start()

def start_server():
    """Chạy server."""
    while True:
        file_list = load_file_list()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((HOST, PORT))
        logging.info(f"Server đang chạy tại {HOST}:{PORT}")

        try:
            while True:
                data, addr = server_socket.recvfrom(BUFFER_SIZE)
                handle_client_request(data, addr, server_socket, file_list)
        except KeyboardInterrupt:
            logging.info("Server đã đóng.")
            break
        except Exception as e:
            logging.exception("Lỗi trong server")
        finally:
            server_socket.close()

if __name__ == "__main__":
    start_server()
