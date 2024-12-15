import socket
import threading
import os
import time
from tqdm import tqdm

# Configurations
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 12345
BUFFER_SIZE = 1024
INPUT_FILE = 'input.txt'
DOWNLOAD_FOLDER = 'downloads'

non_existent_files = set()

def list_files():
    """Retrieve the list of available files from the server and display this information."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            client_socket.sendall(b"LIST")
            response = client_socket.recv(BUFFER_SIZE).decode()
            print("Available files on the server:")
            if response:
                print(response)
            else:
                print("No files available.")
    except Exception as e:
        print(f"Error retrieving file list: {e}")

def download_chunk(filename, part_num, offset, chunk_size, total_size, pbar_main, lock):
    """Downloads a chunk of a file."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((SERVER_HOST, SERVER_PORT))
            request = f"DOWNLOAD:{filename}:{offset}:{chunk_size}"
            client_socket.send(request.encode())
            received_data = b''
            bytes_received = 0

            pbar_part = tqdm(
                total=chunk_size,
                desc=f"Part {part_num + 1}",
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=False,
                position=part_num + 1,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
            )

            while bytes_received < chunk_size:
                chunk = client_socket.recv(min(BUFFER_SIZE, chunk_size - bytes_received))
                if not chunk:
                    break
                received_data += chunk
                bytes_received += len(chunk)
                pbar_part.update(len(chunk))
                with lock:
                    pbar_main.update(len(chunk))

            pbar_part.close()

            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{part_num}")
            with open(temp_file, 'wb') as f:
                f.write(received_data)

    except Exception as e:
        print(f"Error downloading part {part_num}: {e}")


def download_file(filename, file_size):
    """Manages the file download."""
    print(f"Starting download: {filename} ({file_size} bytes)")
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    num_chunks = 4
    chunk_size = file_size // num_chunks
    threads = []
    lock = threading.Lock()

    pbar_main = tqdm(
        total=file_size,
        desc=f"Downloading {filename}",
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        position=0,
        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
    )

    for i in range(num_chunks):
        offset = i * chunk_size
        size = chunk_size if i < num_chunks - 1 else file_size - offset
        thread = threading.Thread(
            target=download_chunk,
            args=(filename, i, offset, size, file_size, pbar_main, lock),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    pbar_main.close()

    output_file = os.path.join(DOWNLOAD_FOLDER, filename)
    with open(output_file, 'wb') as outfile:
        for i in range(num_chunks):
            temp_file = os.path.join(DOWNLOAD_FOLDER, f"{filename}.part{i}")
            with open(temp_file, 'rb') as infile:
                outfile.write(infile.read())
            os.remove(temp_file)
    print(f"\nDownload completed: {filename}\n")

def process_input_file():
    processed_files = set()
    global non_existent_files

    while True:
        try:
            with open(INPUT_FILE, 'r') as f:
                files_to_download = [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            files_to_download = []

        for filename in files_to_download:
            if filename not in processed_files:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                    client_socket.connect((SERVER_HOST, SERVER_PORT))
                    client_socket.send(b"LIST")
                    response = client_socket.recv(BUFFER_SIZE).decode()

                available_files = response.splitlines()
                file_info = next((file for file in available_files if file.startswith(filename)), None)
                
                if file_info:
                    _, file_size = file_info.split()
                    download_file(filename, int(file_size))
                    processed_files.add(filename)
                else:
                    if filename not in non_existent_files:
                        print(f"File {filename} không có trên Server.")
                        print()
                        non_existent_files.add(filename)

        time.sleep(5)

if __name__ == "__main__":
    print("Client start...")
    list_files()
    try:
        process_input_file()
    except KeyboardInterrupt:
        print("\nClient shutdown requested. Exiting...")
