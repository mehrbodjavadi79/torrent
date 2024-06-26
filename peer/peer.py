import argparse
import threading
import socket
import json
import time
import random

class Peer:
    def __init__(self, peer_id, tracker_ip='127.0.0.1', tracker_port=6771, listen_port=52611):
        self.peer_id = peer_id
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port
        self.listen_port = listen_port
        self.files = {}
        self.lock = threading.Lock()
        self.logs = []

    def start(self):
        threading.Thread(target=self.listen).start()
        threading.Thread(target=self.send_alive).start()

    def listen(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', self.listen_port))
            s.listen(5)
            print(f"Peer {self.peer_id} listening on 127.0.0.1:{self.listen_port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_request, args=(conn, addr)).start()

    def handle_request(self, conn, addr):
        data = conn.recv(1024).decode()
        filename, chunk_id = data.split(',')
        chunk_id = int(chunk_id)
        with self.lock:
            chunk = self.files[filename][chunk_id]
        conn.send(chunk)
        conn.close()

    def send_alive(self):
        while True:
            self.alive()
            time.sleep(5)

    def alive(self):
        message = json.dumps({
            'command': 'alive',
            'peer_id': self.peer_id,
        }).encode()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(message, (self.tracker_ip, self.tracker_port))

    def share(self, filename):
        chunks = []
        try:
            with open(f"data/{filename}", 'rb') as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except FileNotFoundError:
            print(f"Error: The file '{filename}' was not found in the 'data' directory.")
            return
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return
        with self.lock:
            self.files[filename.split('/')[-1]] = chunks

        message = json.dumps({
            'command': 'share',
            'filename': filename.split('/')[-1],
            'peer_id': self.peer_id,
            'peer_address': f'127.0.0.1:{self.listen_port}',
            'num_chunks': len(chunks),
        }).encode()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(message, (self.tracker_ip, self.tracker_port))

    def get(self, filename):
        if self.files.get(filename.split('/')[-1], None) != None:
            print("You already have the file with the same name!")
            return
        
        message = json.dumps({
            'command': 'get',
            'filename': filename,
            'peer_id': self.peer_id,
            'peer_address': f'127.0.0.1:{self.listen_port}'
        }).encode()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(message, (self.tracker_ip, self.tracker_port))
            data, _ = s.recvfrom(1024)
            if data == b"File not found":
                print("This file has not shared yet!")
                return
            result = json.loads(data.decode())

        chunks = []
        for chunk_id in range(result['num_chunks']):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                ip, port = random.choice(result['peers']).split(':')

                s.connect((ip, int(port)))
                s.send(f"{filename},{chunk_id}".encode())
                chunk = s.recv(1024)
                chunks.append(chunk)
                self.logs.append({
                    'filename': filename,
                    'chunk_id': chunk_id,
                    'peer_address': f"{ip}:{port}",
                    'timestamp': time.time(),
                    'status': 'success' if chunk else 'failure'
                })

        with open(f"./data/downloaded_{filename}", 'wb') as f:
            for chunk in chunks:
                f.write(chunk)

        self.share(filename)

    def show_logs(self):
        for log in self.logs:
            print(log)
            
    def exit(self):
        message = json.dumps({
            'command': 'exit',
            'peer_id': self.peer_id,
        }).encode()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(message, (self.tracker_ip, self.tracker_port))
        print(f"Peer {self.peer_id} exiting...")

def main():
    parser = argparse.ArgumentParser(description="P2P File Sharing")
    parser.add_argument("peer_id", type=str, help="The ID of the peer")
    parser.add_argument("--tracker_ip", type=str, default="127.0.0.1", help="Tracker IP address")
    parser.add_argument("--tracker_port", type=int, default=6771, help="Tracker port")
    parser.add_argument("--listen_port", type=int, default=52611, help="Listening port for this peer")

    args = parser.parse_args()

    if args.listen_port == 52611:
        args.listen_port = 52611 + int(args.peer_id)
    peer = Peer(peer_id=args.peer_id, tracker_ip=args.tracker_ip, tracker_port=args.tracker_port, listen_port=args.listen_port)
    peer.start()

    while True:
        command = input("Enter command (share <filename> / get <filename> / logs request / exit): ").strip().split()
        if not command:
            continue
        if command[0] == "share" and len(command) == 2:
            peer.share(command[1])
        elif command[0] == "get" and len(command) == 2:
            peer.get(command[1])
        elif command[0] == "logs" and command[1] == "request":
            peer.show_logs()
        elif command[0] == "exit":
            peer.exit()
            quit()
        else:
            print("Invalid command. Please use 'share <filename>', 'get <filename>', 'logs request', or 'exit'.")
    
if __name__ == "__main__":
    main()
