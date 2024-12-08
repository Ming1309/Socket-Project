import socket
import struct
import os

CHUNK_SIZE = 1024  # Kích thước mỗi chunk


def calculate_checksum(data):
    """Tính checksum đơn giản bằng tổng các byte"""
    return sum(data) % 256


def udp_client(server_host='localhost', server_port=12345):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Timeout để nhận gói tin
    server_addr = (server_host, server_port)

    file_name = input("Nhập tên file cần tải: ").strip()
    if not file_name:
        print("Tên file không được để trống.")
        return

    # Gửi yêu cầu file
    client_socket.sendto(file_name.encode(), server_addr)

    # Tạo file rỗng để ghi dữ liệu
    if os.path.exists(file_name):
        os.remove(file_name)  # Xóa file cũ nếu tồn tại
    open(file_name, "wb").close()

    # Nhận file từ server
    chunk_id = 0
    while True:
        try:
            packet, _ = client_socket.recvfrom(1024 + 10)
            header_size = struct.calcsize("!I B")
            received_chunk_id, checksum = struct.unpack("!I B", packet[:header_size])
            chunk = packet[header_size:]

            # Nếu nhận tín hiệu kết thúc
            if received_chunk_id == -1:
                print("Đã nhận đủ file, kết thúc.")
                break

            # Kiểm tra checksum
            if calculate_checksum(chunk) == checksum and received_chunk_id == chunk_id:
                # Ghi dữ liệu hợp lệ vào file
                with open(file_name, "ab") as file:
                    file.write(chunk)
                print(f"Nhận chunk {received_chunk_id} thành công!")

                # Gửi ACK
                ack = struct.pack("!I B", received_chunk_id, 1)
                client_socket.sendto(ack, server_addr)
                chunk_id += 1
            else:
                print(f"Chunk {received_chunk_id} lỗi checksum hoặc không đúng thứ tự!")
                nack = struct.pack("!I B", received_chunk_id, 0)
                client_socket.sendto(nack, server_addr)

        except socket.timeout:
            print("Timeout khi nhận chunk mới, kết thúc.")
            break

    client_socket.close()


if __name__ == "__main__":
    udp_client()
