import socket
import threading
import os
import time

# Cấu hình
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 65432
BUFFER_SIZE = 4096
INPUT_FILE = 'input.txt'
DOWNLOAD_FOLDER = 'downloads'

# Tập hợp lưu trữ các file không tồn tại
non_existent_files = set()

# Hàm tải một chunk
def download_chunk(filename, offset, chunk_size, progress):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            request = f"DOWNLOAD:{filename}:{offset}:{chunk_size}"
            client_socket.send(request.encode())
            
            # Nhận dữ liệu chunk
            received_data = b''
            while len(received_data) < chunk_size:
                chunk = client_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                received_data += chunk
            
            # Ghi dữ liệu vào file tạm thời
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{offset}")
            with open(temp_file, 'wb') as f:
                f.write(received_data)
            
            # Cập nhật tiến độ
            progress['downloaded'] += len(received_data)
    except Exception as e:
        print(f"Lỗi khi tải chunk từ {offset}: {e}")

# Hiển thị tiến độ tải xuống
def display_progress(filename, progress, total_size):
    while progress['downloaded'] < total_size:
        percent = int((progress['downloaded'] / total_size) * 100)
        print(f"\rDownloading {filename}: {percent}%", end="")
        time.sleep(0.5)
    print(f"\rDownloading {filename}: 100%")

# Hàm tải file
def download_file(filename, file_size):
    print(f"Bắt đầu tải file: {filename} ({file_size} bytes)")
    
    # Tính toán chunk
    chunk_size = file_size // 4
    threads = []
    progress = {'downloaded': 0}
    
    # Tạo thư mục downloads nếu chưa có
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    # Khởi chạy tiến trình hiển thị tiến độ
    progress_thread = threading.Thread(target=display_progress, args=(filename, progress, file_size))
    progress_thread.start()
    
    # Tải 4 chunk song song
    for i in range(4):
        offset = i * chunk_size
        size = chunk_size if i < 3 else file_size - offset
        thread = threading.Thread(target=download_chunk, args=(filename, offset, size, progress))
        threads.append(thread)
        thread.start()
    
    # Chờ các thread hoàn thành
    for thread in threads:
        thread.join()
    
    # Dừng tiến trình hiển thị tiến độ
    progress_thread.join()
    
    # Ghép các chunk lại thành file hoàn chỉnh
    output_file = os.path.join(DOWNLOAD_FOLDER, filename)
    with open(output_file, 'wb') as outfile:
        for i in range(4):
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{i * chunk_size}")
            with open(temp_file, 'rb') as infile:
                outfile.write(infile.read())
            os.remove(temp_file)
    
    print(f"Tải xong file: {filename}")
    print()

# Duyệt file input.txt để tải file
def process_input_file():
    processed_files = set()
    global non_existent_files

    while True:
        try:
            with open(INPUT_FILE, 'r') as f:
                files_to_download = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            files_to_download = []

        # Kiểm tra file mới
        for filename in files_to_download:
            if filename not in processed_files:
                # Gửi yêu cầu lấy danh sách file từ Server
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                    client_socket.connect((SERVER_HOST, SERVER_PORT))
                    client_socket.send(b"LIST")
                    response = client_socket.recv(BUFFER_SIZE).decode()
                
                # Tìm file trong danh sách của Server
                available_files = response.splitlines()
                file_info = next((file for file in available_files if file.startswith(filename)), None)
                
                if file_info:
                    _, file_size = file_info.split()
                    download_file(filename, int(file_size))
                    processed_files.add(filename)
                else:
                    # Chỉ in thông báo một lần nếu file không tồn tại
                    if filename not in non_existent_files:
                        print(f"File {filename} không có trên Server.")
                        print()
                        non_existent_files.add(filename)

        time.sleep(5)

# Chương trình chính
if __name__ == "__main__":
    print("Client bắt đầu hoạt động...")
    try:
        process_input_file()
    except KeyboardInterrupt:
        print("\nClient kết thúc.")
