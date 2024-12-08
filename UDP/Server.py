import socket
import struct
import os

CHUNK_SIZE = 1024  # Kích thước mỗi chunk


def calculate_checksum(data):
    """Tính checksum đơn giản bằng tổng các byte"""
    return sum(data) % 256


def udp_server(server_host='localhost', server_port=12345):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_host, server_port))
    print(f"Server đang chạy tại {server_host}:{server_port}")

    allowed_client_addr = None  # Chỉ phục vụ duy nhất một client

    while True:
        try:
            # Nhận yêu cầu từ client
            data, client_addr = server_socket.recvfrom(1024)
            if allowed_client_addr is None:  # Chấp nhận client đầu tiên
                allowed_client_addr = client_addr
                print(f"Kết nối với client: {allowed_client_addr}")
            elif client_addr != allowed_client_addr:
                print(f"Client {client_addr} không được phép, bỏ qua.")
                continue

            file_name = data.decode().strip()
            print(f"Client yêu cầu tải file: {file_name}")

            if not os.path.exists(file_name):
                print(f"File {file_name} không tồn tại.")
                server_socket.sendto(b"ERROR: File not found", client_addr)
                continue

            # Gửi file cho client
            with open(file_name, "rb") as file:
                chunk_id = 0
                while True:
                    chunk = file.read(CHUNK_SIZE)
                    if not chunk:
                        # Gửi tín hiệu kết thúc
                        print("Đã gửi xong file, gửi tín hiệu kết thúc.")
                        end_packet = struct.pack("!I B", -1, 0)
                        server_socket.sendto(end_packet, client_addr)
                        break

                    checksum = calculate_checksum(chunk)
                    packet = struct.pack("!I B", chunk_id, checksum) + chunk
                    server_socket.sendto(packet, client_addr)

                    print(f"Đã gửi chunk {chunk_id}, chờ ACK...")
                    try:
                        ack_data, _ = server_socket.recvfrom(1024)
                        ack_chunk_id, ack_status = struct.unpack("!I B", ack_data)

                        if ack_status == 1 and ack_chunk_id == chunk_id:
                            print(f"ACK nhận thành công cho chunk {chunk_id}")
                            chunk_id += 1
                        else:
                            print(f"ACK lỗi hoặc không đúng chunk, gửi lại chunk {chunk_id}")
                    except socket.timeout:
                        print(f"Timeout, gửi lại chunk {chunk_id}")
                        continue

        except Exception as e:
            print(f"Lỗi server: {e}")
            break

    server_socket.close()


if __name__ == "__main__":
    udp_server()

