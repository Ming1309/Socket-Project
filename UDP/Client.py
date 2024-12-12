# Client.py
import socket
import os
import threading
import logging
import hashlib

# Cấu hình client
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 65432
BUFFER_SIZE = 8192
DOWNLOAD_FOLDER = "downloads"
INPUT_FILE = "input.txt"
MAX_RETRIES = 15
TIMEOUT = 10

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def verify_chunk_integrity(received_data, expected_checksum):
    """Kiểm tra tính toàn vẹn của chunk."""
    actual_checksum = hashlib.md5(received_data).hexdigest()
    return actual_checksum == expected_checksum

def download_chunk(filename, part_num, offset, chunk_size):
    """Tải một phần dữ liệu của file."""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(TIMEOUT)

        request = f"DOWNLOAD:{filename}:{offset}:{chunk_size}:{part_num}"
        client_socket.sendto(request.encode(), (SERVER_HOST, SERVER_PORT))
        logging.info(f"Chunk {part_num}: Gửi yêu cầu tải: {request}")

        base_seq = part_num * 100
        max_seq = base_seq + 100

        received_data = bytearray()
        expected_seq = base_seq
        chunk_checksum = None
        total_packets = None
        retries = 0

        while True:
            try:
                packet, server_addr = client_socket.recvfrom(BUFFER_SIZE)
                try:
                    seq_str, total_packets_str, chunk_checksum, data = packet.split(b"|", 3)
                except ValueError:
                    logging.error(f"Packet không đúng định dạng: {packet}")
                    continue

                seq = int(seq_str)
                total_packets = int(total_packets_str)
                chunk_checksum = chunk_checksum.decode()

                if base_seq <= seq < max_seq and seq == expected_seq:
                    received_data.extend(data)
                    client_socket.sendto(f"ACK:{seq}".encode(), server_addr)
                    expected_seq += 1
                    retries = 0

                    if seq == base_seq + total_packets - 1:
                        break
                else:
                    client_socket.sendto(f"ACK:{expected_seq - 1}".encode(), server_addr)
                    retries += 1
                    if retries > MAX_RETRIES:
                        logging.error(f"Chunk {part_num}: Quá nhiều retries")
                        return False

            except socket.timeout:
                retries += 1
                logging.warning(f"Chunk {part_num}: Timeout tại sequence {expected_seq}, thử lại ({retries}/{MAX_RETRIES})")
                if retries > MAX_RETRIES:
                    logging.error(f"Chunk {part_num}: Timeout quá nhiều, tải thất bại")
                    return False

        if verify_chunk_integrity(received_data, chunk_checksum):
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{part_num}")
            with open(temp_file, "wb") as f:
                    f.write(received_data)
            logging.info(f"Chunk {part_num}: Lưu thành công.")
            return True
        else:
            logging.error(f"Chunk {part_num}: Lỗi toàn vẹn dữ liệu")
            return False

    except Exception as e:
        logging.error(f"Chunk {part_num}: Lỗi tải: {e}")
        return False
    finally:
        client_socket.close()

def download_file(filename, file_size, server_checksum):
    """Tải file từ server."""
    logging.info(f"Tải file {filename} ({file_size} bytes).")
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    chunk_size = (file_size + 3) // 4
    threads = []
    download_success = [False] * 4

    for i in range(4):
        offset = i * chunk_size
        size = chunk_size if i < 3 else (file_size - chunk_size * 3)
        thread = threading.Thread(
            target=lambda idx=i, off=offset, sz=size: download_success.__setitem__(
                idx, 
                download_chunk(filename, idx, off, sz)
            )
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    if all(download_success):
        output_file = os.path.join(DOWNLOAD_FOLDER, filename)
        with open(output_file, "wb") as outfile:
            for i in range(4):
                temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{i}")
                with open(temp_file, "rb") as infile:
                    outfile.write(infile.read())
                os.remove(temp_file)

        with open(output_file, 'rb') as f:
            downloaded_checksum = hashlib.md5(f.read()).hexdigest()
        
        if downloaded_checksum == server_checksum:
            logging.info(f"Tải file {filename} hoàn tất và đã xác thực.")
            return True
        else:
            logging.error(f"Lỗi toàn vẹn file {filename}.")
            os.remove(output_file)
            return False
    else:
        logging.error(f"Tải file {filename} thất bại.")
        return False

def process_input_file():
    """Đọc file input.txt và tải các file yêu cầu."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.sendto(b"LIST", (SERVER_HOST, SERVER_PORT))
    response, _ = client_socket.recvfrom(BUFFER_SIZE)
    client_socket.close()

    available_files = [line.split() for line in response.decode().split("\n")]
    available_files_dict = {name: {'size': int(size), 'checksum': checksum} 
                             for name, size, checksum in available_files}

    try:
        with open(INPUT_FILE, "r") as f:
            files_to_download = [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        logging.warning("Không tìm thấy file input.txt.")
        files_to_download = []

    for filename in files_to_download:
        if filename in available_files_dict:
            file_info = available_files_dict[filename]
            result = download_file(filename, file_info['size'], file_info['checksum'])
            if not result:
                logging.error(f"Tải file {filename} không thành công")
        else:
            logging.warning(f"File {filename} không tồn tại trên server.")

if __name__ == "__main__":
    logging.info("Client đang chạy...")
    process_input_file()
