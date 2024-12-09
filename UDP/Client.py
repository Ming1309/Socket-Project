import socket
import os
import threading

# Cấu hình client
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 65432
BUFFER_SIZE = 4096
DOWNLOAD_FOLDER = "downloads"
INPUT_FILE = "input.txt"

def download_chunk(filename, part_num, offset, chunk_size):
    """Tải một phần dữ liệu của file."""
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        request = f"DOWNLOAD:{filename}:{offset}:{chunk_size}"
        client_socket.sendto(request.encode(), (SERVER_HOST, SERVER_PORT))

        # Nhận dữ liệu từ server
        received_data = bytearray()
        while len(received_data) < chunk_size:
            packet, _ = client_socket.recvfrom(BUFFER_SIZE)
            received_data.extend(packet)

        # Lưu dữ liệu vào file tạm
        temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{part_num}")
        with open(temp_file, "wb") as f:
            f.write(received_data)
    except Exception as e:
        print(f"Lỗi tải phần {part_num} của file {filename}: {e}")
    finally:
        client_socket.close()


def download_file(filename, file_size):
    """Tải file từ server."""
    print(f"Đang tải: {filename} ({file_size} bytes)")

    # Tạo thư mục tải xuống nếu chưa tồn tại
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    # Chia file thành 4 phần
    chunk_size = file_size // 4
    threads = []

    for i in range(4):
        offset = i * chunk_size
        size = chunk_size if i < 3 else file_size - offset  # Phần cuối nhận số byte còn lại
        thread = threading.Thread(target=download_chunk, args=(filename, i, offset, size))
        threads.append(thread)
        thread.start()

    # Chờ tất cả các phần tải xong
    for thread in threads:
        thread.join()

    # Ghép các phần lại thành file hoàn chỉnh
    output_file = os.path.join(DOWNLOAD_FOLDER, filename)
    with open(output_file, "wb") as outfile:
        for i in range(4):
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{i}")
            with open(temp_file, "rb") as infile:
                outfile.write(infile.read())
            os.remove(temp_file)

    print(f"Tải xong: {filename}")

def process_input_file():
    """Đọc file input.txt và tải các file yêu cầu."""
    while True:
        try:
            with open(INPUT_FILE, "r") as f:
                files_to_download = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            files_to_download = []

        for filename in files_to_download:
            # Gửi yêu cầu danh sách file
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.sendto(b"LIST", (SERVER_HOST, SERVER_PORT))
            response, _ = client_socket.recvfrom(BUFFER_SIZE)
            client_socket.close()

            # Kiểm tra file có tồn tại không
            available_files = response.decode().split("\n")
            file_info = next((file for file in available_files if file.startswith(filename)), None)

            if file_info:
                _, file_size = file_info.split()
                download_file(filename, int(file_size))
            else:
                print(f"File {filename} không tồn tại trên server.")
        
        break  # Thực hiện tải một lần rồi dừng

if __name__ == "__main__":
    print("Client đang hoạt động...")
    process_input_file()
