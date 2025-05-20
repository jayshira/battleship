"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.

TODO: Fix the message synchronization issue using concurrency (Tier 1, item 1).
"""
import socket
import threading
import time
import zlib
HOST = '127.0.0.2'
PORT = 5000

# HINT: The current problem is that the client is reading from the socket,
# then waiting for user input, then reading again. This causes server
# messages to appear out of order.
#
# Consider using Python's threading module to separate the concerns:
# - One thread continuously reads from the socket and displays messages
# - The main thread handles user input and sends it to the server


class BattleshipClient:
    def __init__(self):
        self.running = True
        self.playing = True
        self.can_input = False
        self.stop_spam = False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))
        self.rfile = self.sock.makefile('r')
        self.wfile = self.sock.makefile('w')
        
        # Start receiver thread
        threading.Thread(target=self.receive_messages, daemon=True).start()
    
    def initialise_account(self):
        print()
    def allow_chat(self):
        self.stop_spam = False
    
    def receive_messages(self):
        while self.running:
            try:
                line = self.rfile.readline()
                if not line:
                    break
                
                line = line.strip()
                
                """ PHASE CONTROL MESSAGES """
                if line == "X":
                    self.can_input = False
                    self.running = False
                    print("You have been detected idle, and have been disconnected from the server, press ENTER to end session")
                # Grid
                elif line == "GRID":
                    self.print_board()
                # ACK
                elif line == "ACK":
                    # Send ACK back to indicate active
                    self.wfile.write("ACK\n")
                    self.wfile.flush()
                #Other
                else:
                    payload = line[9:]
                    checksum_rcv = int(line[:8], 16)
                    checksum_check = zlib.crc32(payload.encode())
                    if checksum_rcv == checksum_check:
                        self.wfile.write("ACK\n")
                        self.wfile.flush()
                        try:
                            if line[9] == '1': # can input
                                self.can_input = True
                            elif line[9] == '2': # cant input
                                self.can_input = False
                            elif line[9] == '4': # chat input detect to stop spam
                                print("yep")
                                self.stop_spam = True
                                t = threading.Timer(2, self.allow_chat)
                                t.start()
                            elif line[9] == '5': # client = player
                                self.can_input = False
                                self.playing = True
                            elif line[9] == '6': # client = spectator
                                self.can_input = False
                                self.playing = False

                            print("\n" + line[11:])
                            if line[9] == '3': # for messages that require more formatting
                                print() # add extra line so doesn't clump up
                        except:
                            pass
                    else:
                        self.wfile.write("NACK\n")
                        self.wfile.flush()
                    
            except ConnectionError:
                break

    # def send_chat_message(self, message):
    #     # Send a chat message to the server
    #     self.wfile.write(f"CHAT {message}\n")
    #     self.wfile.flush()
    

    def print_board(self):
        while True:
            line = self.rfile.readline().strip()
            if not line:
                break
            print(line)
    
    def run(self):
        try:
            while self.running:
                # Always allow quit, but only process game commands when allowed
                command = input()

                # make sure that malicious actor cant crash server with large input
                if len(command) > 100:
                    print("[NOTICE] Input cant be longer than 100 characters, please try again.")
                    continue

                if self.stop_spam:
                    print("[NOTICE] Your message is not sent, You are sending too much message, please do not spam")
                    continue

                
                # for the player clients, make sure to not send action out of turn order.
                if self.playing:
                    # quit allows to go through
                    if command.lower() == 'quit':
                        self.wfile.write('quit\n')
                        self.wfile.flush()
                        self.running = False
                        break

                    # chat allows to go through
                    if command.lower().startswith("chat "):
                        self.wfile.write(command + "\n")
                        self.wfile.flush()
                        continue
                    
                    # only allow input sending to server when prompted
                    if self.can_input:
                        self.wfile.write(command + '\n')
                        self.wfile.flush()
                        self.can_input = False # no double sending
                    else:
                        print("[NOTICE] Wait for server prompt before sending commands")

                # for the spectator clients allow anything
                else:
                    self.wfile.write(command + '\n')
                    self.wfile.flush()
                
        # exiting out the shell also counts as quit and notify the server           
        except KeyboardInterrupt:
            self.wfile.write('quit\n')
            self.wfile.flush()
            self.running = False
        finally:
            print("\n[NOTICE] You are disconnected, closing connection...")
            self.sock.close()

if __name__ == "__main__":
    client = BattleshipClient()
    client.run()