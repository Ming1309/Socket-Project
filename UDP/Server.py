import socket
import os
import logging

# Cấu hình server
HOST = "127.0.0.1"
PORT = 65432
SERVER_FILES_DIR = "files"
BUFFER_SIZE = 4096

# Thiết lập logging
logging.basicConfig(level=logging.INFO)

def load_file_list():
    """Tải danh sách file từ thư mục files."""
    if not os.path.exists(SERVER_FILES_DIR):
        os.makedirs(SERVER_FILES_DIR)
    file_list = {}
    for file_name in os.listdir(SERVER_FILES_DIR):
        file_path = os.path.join(SERVER_FILES_DIR, file_name)
        if os.path.isfile(file_path):
            file_list[file_name] = os.path.getsize(file_path)
    return file_list

def handle_request(data, addr, server_socket, file_list):
    """Xử lý yêu cầu từ client."""
    message = data.decode()
    logging.info(f"Yêu cầu từ {addr}: {message}")

    if message == "LIST":
        # Gửi danh sách file
        response = "\n".join([f"{name} {size}" for name, size in file_list.items()])
        server_socket.sendto(response.encode(), addr)
    elif message.startswith("DOWNLOAD"):
        try:
            _, file_name, offset, chunk_size = message.split(":")
            offset = int(offset)
            chunk_size = int(chunk_size)

            if file_name in file_list:
                file_path = os.path.join(SERVER_FILES_DIR, file_name)
                with open(file_path, "rb") as f:
                    f.seek(offset)
                    data = f.read(chunk_size)

                # Chia nhỏ dữ liệu thành các gói UDP nhỏ hơn
                packet_size = 1024  # Kích thước mỗi gói (bytes)
                total_packets = (len(data) + packet_size - 1) // packet_size

                for i in range(total_packets):
                    start = i * packet_size
                    end = min(start + packet_size, len(data))
                    packet = data[start:end]
                    server_socket.sendto(packet, addr)
            else:
                server_socket.sendto(b"ERROR: File not found", addr)
        except Exception as e:
            logging.error(f"Lỗi xử lý yêu cầu tải: {e}")
            server_socket.sendto(b"ERROR: Invalid request format", addr)
    else:
        server_socket.sendto(b"ERROR: Unknown command", addr)

def start_server():
    """Chạy server."""
    file_list = load_file_list()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))
    logging.info(f"Server đang chạy tại {HOST}:{PORT}")

    while True:
        try:
            data, addr = server_socket.recvfrom(BUFFER_SIZE)
            handle_request(data, addr, server_socket, file_list)
        except KeyboardInterrupt:
            logging.info("Đóng server.")
            break
        except Exception as e:
            logging.error(f"Lỗi trong server: {e}")

if __name__ == "__main__":
    start_server()
