import socket
import os
import logging
import hashlib
import threading
import json 
import time 


# Cấu hình client
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 65432
SERVER_PORTS = [54000, 55000, 56000, 57000]  # Danh sách các cổng
BUFFER_SIZE = 65535  # Giới hạn tối đa cho một gói UDP
DOWNLOAD_FOLDER = "downloads"
INPUT_FILE = "input.txt"
MAX_RETRIES = 2
TIMEOUT = 2

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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


def download_chunk(filename, chunk_id, offset, chunk_size, server_port):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT)
    server_address = (SERVER_HOST, server_port)
    seq_num = offset 
    conditionStop = offset + chunk_size #sửa chỗ này 
    try:
        with open(f"{DOWNLOAD_FOLDER}/{filename}_part_{chunk_id}", "wb") as file:
            while offset < conditionStop:
                part_size = min(1024, conditionStop  - offset)
                request = f"DOWNLOAD|{filename}|{offset}|{part_size}|{seq_num}|{chunk_id}".encode()
                client_socket.sendto(request, server_address)
                try:
                    response, _ = client_socket.recvfrom(BUFFER_SIZE)
                    packet = ReliablePacket.deserialize(response)
                    logging.info(f"Client received chunk_id={packet.chunk_id}, seq_num={packet.seq_num}")
                    if packet.chunk_id == chunk_id and packet.seq_num == seq_num:
                        if packet.checksum == generate_checksum(packet.data):
                            file.write(packet.data)
                            client_socket.sendto(f"ACK_{chunk_id}_{seq_num}".encode(), server_address)
                            seq_num += 1
                            offset += part_size
                        else:
                            logging.warning(f"Checksum mismatch for chunk {chunk_id}, seq_num {seq_num}")
                            client_socket.sendto(f"NACK_{chunk_id}_{seq_num}".encode(), server_address)
                except socket.timeout:
                    logging.warning(f"Timeout for chunk {chunk_id}, seq_num {seq_num}, size {part_size}")
    except Exception as e:
        logging.error(f"Error in download_chunk: {e}")
    finally:
        client_socket.close()

def download_file(file_list, filename):
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

#Hàm yêu cầu danh sách 
def request_file_list():
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

#Hàm đọc file input.txt
def read_input_file(input_file=INPUT_FILE):
    """Đọc các tên tệp từ file input.txt và trả về danh sách các tệp"""
    file_list = []
    try:
        with open(input_file, 'r') as f:
            for line in f:
                filename = line.strip()  # Lọc bỏ khoảng trắng thừa
                if filename:  # Nếu tên tệp không rỗng
                    file_list.append(filename)
        logging.info(f"Đã đọc {len(file_list)} tệp từ {input_file}.")
    except FileNotFoundError:
        logging.error(f"Không tìm thấy tệp {input_file}.")
    except Exception as e:
        logging.error(f"Lỗi khi đọc {input_file}: {e}")
    return file_list

def read_input_file():
    try:
        with open(INPUT_FILE, "r") as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        return []

def main():
    file_list = request_file_list()
    print("\nDanh sách file từ server:")
    for file_name, size in file_list .items():
        print(f" * {file_name} {size}B")
    print()
    files_to_download = read_input_file()

    for filename in files_to_download:
        if filename in file_list:
            download_file(file_list, filename)
        else:
            logging.warning(f"File {filename} not found on server.")
def main(): 
    # Tạo danh sách các tệp đã tải để kiểm tra trùng lặp
    downloaded_files = set()
    # Lấy danh sách file từ server
    file_list = request_file_list()
    print("\nDanh sách file từ server:")
    for file_name, size in file_list.items():
        print(f" * {file_name} {size}B")
    print()
    while True:
        try:
           
            # Đọc danh sách từ input.txt
            files_to_download = read_input_file()

            for filename in files_to_download:
                # Nếu tệp đã tải, bỏ qua
                if filename in downloaded_files:
                    logging.info(f"File {filename} đã được tải trước đó. Bỏ qua.")
                    continue
                
                # Nếu tệp có trong danh sách server, tiến hành tải
                if filename in file_list:
                    download_file(file_list, filename)
                    downloaded_files.add(filename)  # Đánh dấu tệp là đã tải
                else:
                    logging.warning(f"File {filename} không có trên server. Bỏ qua.")
            
            # Sau khi hoàn tất danh sách hiện tại, chờ 5 giây và kiểm tra lại
            logging.info("Hoàn tất danh sách hiện tại. Đợi 5 giây trước khi kiểm tra lại...")
            time.sleep(5)

        except KeyboardInterrupt:
            logging.info("Client đã dừng hoạt động.")
            break

if __name__ == "__main__":
    main()


 #Danh sách các biến
# seq_num: Số thứ tự của mỗi gói tin, giúp xác định vị trí của gói tin trong quá trình truyền tải.
# chunk_id: ID của mỗi chunk (phần lớn của tệp), được chia thành các phần nhỏ hơn.
# part_num: Số thứ tự của mỗi phần nhỏ trong chunk.
# offset: Vị trí bắt đầu của mỗi phần trong chunk.
# chunk_size: Kích thước mỗi chunk (tệp chia thành các chunk).
# total_data: Dữ liệu của một chunk, lưu trữ sau khi tất cả các phần của chunk được tải.
# retries: Số lần thử lại khi không nhận được dữ liệu.
# current_part_size: Kích thước phần dữ liệu hiện tại trong chunk.
# part_offset: Vị trí của phần trong chunk.
# chunk_parts: Dictionary lưu trữ các phần nhỏ của chunk, với seq_num làm key.
# lock: Đối tượng đồng bộ hóa để tránh truy cập đồng thời vào chunk_parts từ nhiều luồng.
# file_list: Danh sách các tệp từ server, bao gồm tên và kích thước tệp.
# filename: Tên tệp hiện tại đang được tải.
# server_address: Địa chỉ của server (IP và cổng).
# client_socket: Socket UDP để giao tiếp với server.
# input_file: Tệp chứa danh sách các tệp cần tải.
# part_size: Kích thước mỗi phần nhỏ trong chunk (ví dụ: 1KB hoặc 4KB).
# MAX_RETRIES: Số lần thử lại nếu có lỗi trong quá trình tải.
# TIMEOUT: Thời gian chờ tối đa trước khi thử lại hoặc báo lỗi.
# DOWNLOAD_FOLDER: Thư mục để lưu trữ các tệp đã tải.
# INPUT_FILE: Tệp chứa danh sách tệp cần tải từ server.
