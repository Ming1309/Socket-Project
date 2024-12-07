import socket
import threading
import os
import time
from tqdm import tqdm

# Configurations
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 65432
BUFFER_SIZE = 4096
INPUT_FILE = 'input.txt'
DOWNLOAD_FOLDER = 'downloads'

# Tập hợp lưu trữ các file không tồn tại
non_existent_files = set()

def list_files():
    """Retrieve the list of available files from the server and display this information."""
    try:
        # Tạo socket TCP và kết nối tới server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            
            # Gửi lệnh "LIST" đến server
            client_socket.sendall(b"LIST")
            
            # Nhận phản hồi từ server
            response = client_socket.recv(BUFFER_SIZE).decode()
            
            # Hiển thị danh sách file nhận được
            print("Available files on the server:")
            if response:
                print(response)
            else:
                print("No files available.")
    except Exception as e:
        print(f"Error retrieving file list: {e}")


# Function to download a chunk of a file
def download_chunk(filename, part_num, offset, chunk_size, progress, lock, progress_bars):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            
            # Send the request for the specific chunk
            request = f"DOWNLOAD:{filename}:{offset}:{chunk_size}"
            client_socket.send(request.encode())
            
            # Prepare the progress bar
            progress_bar = tqdm(
                total=chunk_size,
                position=part_num,
                desc=f"Part {part_num + 1}",
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=False
            )
            progress_bars[part_num] = progress_bar
            
            # Receive the chunk data
            received_data = b''
            bytes_received = 0
            
            while bytes_received < chunk_size:
                chunk = client_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                received_data += chunk
                bytes_received += len(chunk)
                
                # Update progress incrementally
                progress_bar.update(len(chunk))
                
                with lock:
                    progress[part_num] = int((bytes_received / chunk_size) * 100)
            
            # Close the progress bar when done
            progress_bar.close()
            
            # Save the received data to a temporary file
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{part_num}")
            with open(temp_file, 'wb') as f:
                f.write(received_data)
    except Exception as e:
        print(f"Error downloading part {part_num}: {e}")


# Function to display real-time download progress
def display_progress(filename, progress):
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')  # Clear the console
        print(f"Downloading {filename}:")
        all_done = True
        for part_num, percentage in progress.items():
            print(f"Part {part_num + 1} .... {percentage}%")
            if percentage < 100:
                all_done = False
        if all_done:
            break
        time.sleep(0.25)
    print(f"Download completed: {filename}")

# Function to manage the file download
def download_file(filename, file_size):
    print(f"Starting download: {filename} ({file_size} bytes)")
    
    # Create download directory if it doesn't exist
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    # Calculate chunk sizes
    chunk_size = file_size // 4
    threads = []
    progress = {i: 0 for i in range(4)}  # Track progress for each part
    progress_bars = {}  # Store progress bar objects
    lock = threading.Lock()
    
    # Start threads to download chunks
    for i in range(4):
        offset = i * chunk_size
        size = chunk_size if i < 3 else file_size - offset  # Ensure last chunk gets remaining bytes
        thread = threading.Thread(target=download_chunk, args=(filename, i, offset, size, progress, lock, progress_bars))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to finish
    for thread in threads:
        thread.join()
    
    # Merge chunks into a single file
    output_file = os.path.join(DOWNLOAD_FOLDER, filename)
    with open(output_file, 'wb') as outfile:
        for i in range(4):
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{i}")
            with open(temp_file, 'rb') as infile:
                outfile.write(infile.read())
            os.remove(temp_file)
    print(f"\nDownload completed: {filename}\n")

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
    print("Client Program - File List")
    print("==========================")
    list_files()
    try:
        process_input_file()
    except KeyboardInterrupt:
        print("\nClient kết thúc.")
