"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.

TODO: For Tier 1, item 1, you don't need to modify this file much. 
The core issue is in how the client handles incoming messages.
However, if you want to support multiple clients (i.e. progress through further Tiers), you'll need concurrency here too.
"""
import socket
import threading
from collections import deque
import time
import zlib
import select
import random

from battleship import place_ships_multiplayer, run_multi_player_game_online

HOST = '127.0.0.2'
PORT = 5000
MAX_QUEUE_SIZE = 10

class GameServer:
    game_running = False

    def __init__(self):
        self.client_queue = deque()
        self.lock = threading.Lock()
        self.dced_player = None
        self.rced_player = None
    
    def packet_send(self, msg, rfile, wfile):
        msg = msg.strip()
        retry = 3
        while retry > 0:
            b_msg = msg.encode()
            checksum = zlib.crc32(b_msg)
            wfile.write(f"{checksum:08x};{msg}\n")
            wfile.flush()
            ready, _, _ = select.select([rfile], [], [], 30)
            if ready:
                message = rfile.readline().strip()
                if message == 'ACK':
                    return
            retry -= 1
        raise(BrokenPipeError)
        
    def broadcast_to_spectators(self, message, host="BROADCAST"):
        with self.lock:
            for client in self.client_queue:
                _, rfile, wfile, uname = client
                try:
                    if uname == host:
                        self.packet_send(f"4;You: {message}", rfile, wfile)
                    else:
                        self.packet_send(f"3;{host}: {message}", rfile, wfile)
                except (ConnectionResetError, BrokenPipeError):
                    continue
                
    def broadcast_board_to_spectators(self, board):
        with self.lock:
            for client in self.client_queue:
                _, _, wfile, _ = client
                try:
                    board.print_display_grid_mp(wfile)
                except (ConnectionResetError, BrokenPipeError):
                    continue
    
    def react_to_chatroom(self, conn, rfile, wfile, uname):
        try:
            self.packet_send("6;You are now in the queue's chat room", rfile, wfile)
            self.packet_send("0;You can send and read other people's messages", rfile, wfile)
            self.packet_send("0;Match status will also be broadcasted here", rfile, wfile)

            conn.setblocking(False)
            while self.game_running:
                time.sleep(0.5)
                message = rfile.readline().strip()
                if message:
                    self.broadcast_to_spectators(message, uname)
            
            self.packet_send("5;Temporarily closing chat room, you might play next!", rfile, wfile)
            conn.setblocking(True)
        except(BrokenPipeError, ConnectionResetError):
            conn.close()

    def handle_client(self, conn, addr):
        print(f"[INFO] Client connected from {addr}")
        with conn:
            rfile = conn.makefile('r')
            wfile = conn.makefile('w')
            with self.lock:
                if len(self.client_queue) < MAX_QUEUE_SIZE:
                    self.packet_send("1;Please enter your username:", rfile, wfile)
                    uname = rfile.readline().strip()
                    if uname == self.dced_player:
                        self.rced_player = (conn, rfile, wfile, uname)
                        return
                    self.client_queue.append((conn, rfile, wfile, uname))
                    self.packet_send("2;You're in queue. Waiting for match...", rfile, wfile)
                else:
                    self.packet_send("2;[NOTICE] Queue is full, please try again later.", rfile, wfile)
                    return
                
            # if game running join chat with other spectators
            if self.game_running:
                chat_thread = threading.Thread(
                    target=self.react_to_chatroom,
                    args=(conn, rfile, wfile, uname),
                    daemon=True)
                chat_thread.start()

            # Check if we can start a game
            while not self.game_running and len(self.client_queue) >= 2:
                self.game_running = True
                self.configure_game()
                print(f"[INFO] {len(self.client_queue)} players in queue")
            
    
    def client_reconnected(self, players):
        print("[INFO] Checking for reconnected players...")
        for i in range(60):
            if self.rced_player:
                for i in range(len(players)):
                    if players[i][3] == self.rced_player[3]:
                        players[i] = self.rced_player
                self.rced_player = None
                self.dced_player = None
                return True
            time.sleep(1)
        return False
    
    def configure_game(self):
        # Get two players make sure they aren't disconnected
        # print("before player 1")
        # for i in range(len(self.client_queue)):
            # print(self.client_queue[i][3])
        while True:
            if len(self.client_queue) < 2:
                print("[INFO] Not enough players to start a game, waiting...")
                self.game_running = False
                return
            try:
                player1 = self.client_queue.popleft()
                # print("after player 1")
                # for i in range(len(self.client_queue)):
                #     print(self.client_queue[i][3])
                player1[2].write("ACK\n")
                player1[2].flush()
                test = player1[1].readline().strip()
                # print(test)
                if test == "ACK":
                    break
            except (ConnectionResetError, BrokenPipeError):
                print("[ERROR] Player 1 disconnected, retrying...")

        # print("before player 2")
        # for i in range(len(self.client_queue)):
        #     print(self.client_queue[i][3])

        while True:
            if len(self.client_queue) < 1:
                print("[INFO] Not enough players to start a game, waiting...")
                self.client_queue.appendleft(player1) # Re-add player1 to the queue
                self.game_running = False
                return
            try:
                player2 = self.client_queue.popleft()
                # print("after player 2")
                # for i in range(len(self.client_queue)):
                #     print(self.client_queue[i][3])
                player2[2].write("ACK\n")
                player2[2].flush()
                test = player2[1].readline().strip()
                # print(test)
                if test == "ACK":
                    break
            except (ConnectionResetError, BrokenPipeError):
                print("[ERROR] Player 2 disconnected, retrying...")
        
        # Start game thread
        game_thread = threading.Thread(
            target=self.run_game,
            args=(player1, player2),
            daemon=True)
        game_thread.start()

        # Start chat thread
        for client in self.client_queue:
            chat_thread = threading.Thread(
                target=self.react_to_chatroom,
                args=(client[0], client[1], client[2], client[3]),
                daemon=True)
            chat_thread.start()

        game_thread.join()  # Wait for the game to finish
        self.game_running = False
        print("[INFO] Game thread finished, Players returned to queue")
        time.sleep(5)
    
    def place_ships(self, idx, conn, rfile, wfile, boards):
        try:
            boards[idx] = place_ships_multiplayer(conn, rfile, wfile)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            print(f"[ERROR] Player {idx} disconnected or timedout during ship placement")
            boards[idx] = None  # Indicates disconnection
        except Exception as e:
            print(f"[ERROR] Unexpected error during placement: {e}")
            boards[idx] = None
    
    def run_game(self, p1, p2):
        try:
            self.broadcast_to_spectators("New game started between two players.")
            print("[INFO] Starting game between two players")

            # WELCOME MESSAGE
            self.packet_send("5;Welcome to Battleship Multiplayer", p1[1], p1[2])
            self.packet_send("5;Welcome to Battleship Multiplayer", p2[1], p2[2])

            # PLACEMENT PHASE
            boards = [None, None]
            players = [p1, p2]
            placement_threads = []

            # SETBLOCKING TO FALSE SO CAN HEAR BOTH CONCURRENTLY
            players[0][0].setblocking(False)
            players[1][0].setblocking(False)

            for i, (conn, rfile, wfile, uname) in enumerate(players):
                thread = threading.Thread(
                    target=self.place_ships,
                    args=(i, conn, rfile, wfile, boards))
                thread.start()
                placement_threads.append(thread)
            
            for thread in placement_threads:
                thread.join()
            
            # Check for disconnections during placement
            if boards[0] is None or boards[1] is None:
                self.broadcast_board_to_spectators("player(s) timed out or disconnected match cancelled")
                self.broadcast_board_to_spectators("picking new players to start a match...")
                remaining_players = []
                for i, board in enumerate(boards):
                    if board is not None:
                        remaining_players.append(players[i])
                    else:
                        # Close the disconnected player's socket
                        players[i][0].close()
                # Add remaining players back to queue
                with self.lock:
                    for p in remaining_players:
                        self.packet_send("2;Other Player disconnected, looking for new opponent..", p[1], p[2])
                        p[0].setblocking(True)
                        self.client_queue.appendleft(p)
                return
            
            """ MAIN GAMEPLAY LOOP """

            # INITIALIZE GAMEPLAY
            current_player = random.randint(0, 1)
            opponent_boards = [boards[1], boards[0]]

            # make it so that if turn is skipped 2 times in a row, it will auto forfeit
            player1_skipped = False
            player2_skipped = False

            while True:
                # time.sleep(5) # Wait for a bit before the next turn
                
                # Spectator poggers
                self.broadcast_to_spectators(f"{players[current_player][3]}'s turn.")

                # setblocking stuff (commented for chaos mode)
                # players[current_player][0].setblocking(True)
                # players[1-current_player][0].setblocking(False)

                # CURRENT PLAYER DATA
                conn, rfile, wfile, uname = players[current_player]
                opp_board = opponent_boards[current_player]

                # OTHER PLAYER DATA
                other_conn, other_rfile, other_wfile, opp_name = players[1 - current_player]
                
                # RUN THE TURN
                result_data = run_multi_player_game_online(rfile, wfile, other_rfile, other_wfile, opp_board)
                result = result_data[0]

                """ TURN RESULTS ARE PAST THIS POINT """

                # GAME OVER
                if result == "game_finished":
                    self.broadcast_to_spectators(f"Game over! All ships sunk. {players[current_player][3]} wins!")
                    self.broadcast_to_spectators(f"{players[current_player][3]}'s board state:\n")
                    self.broadcast_board_to_spectators(boards[current_player])
                    self.broadcast_to_spectators(f"{players[1 - current_player][3]}'s board state:\n")
                    self.broadcast_board_to_spectators(boards[1 - current_player])
                    break
                
                # SOMEHOW BOTH DC SAME TIME
                elif result == "all_forfeit":
                    players.clear()
                    break
                
                # DC DURING THEIR TURN
                elif result == "player_dc":
                    self.dced_player = uname
                    if self.client_reconnected(players):
                        self.packet_send(f"5;Welcome back, {uname}", rfile, wfile)
                        continue # dont switch turns just let them continue the turn
                    else:
                        players.pop(current_player)
                        break
                
                # OTHER PLAYER DC DURING YOUR TURN
                elif result == "other_player_dc":
                    self.dced_player = opp_name
                    if self.client_reconnected(players):
                        self.packet_send(f"5;Welcome back, {opp_name}", other_rfile, other_wfile)
                        continue # dont switch turns just let whichever state it was continue
                    else:
                        players.pop(1 - current_player)
                        break
                
                # COMMAND SENT BUT GAME NOT OVER
                elif result == "turn_completed":
                    coord = result_data[1]
                    hit_result = result_data[2]
                    sunk_name = result_data[3]

                    # Broadcast action and result
                    message = f"{players[current_player][3]} fired at {coord}: {hit_result}"
                    if sunk_name:
                        message += f" (Sank {sunk_name})"
                    self.broadcast_to_spectators(message)

                    # Broadcast opponent's board state
                    self.broadcast_to_spectators(f"{players[1 - current_player][3]}'s board state:\n")
                    self.broadcast_board_to_spectators(opponent_boards[current_player])

                    # Reset if player's turn has been skipped before
                    if current_player ==  0:
                        player1_skipped = False
                    else:
                        player2_skipped = False
                
                # CHANGE PLAYERS
                current_player = 1 - current_player

                # TIMEOUT SKIP TURN OR DISCONNECT AFTER 2 IN A ROW
                if result == "timeout":
                    print("timeout")
                    self.broadcast_to_spectators(f"{uname} has timed out, their turn will be skipped")
                    
                    # logic reversed because change player is called prior
                    if current_player == 1:
                        if not player1_skipped:
                            player1_skipped = True
                            continue
                    else:
                        if not player2_skipped:
                            player2_skipped = True
                            continue

                    self.packet_send(f"0;GAME_OVER {uname} is AFK, immediate forfeit, You Win!", other_rfile, other_wfile)
                    wfile.write("X\n") # tell client that their session has been terminated
                    wfile.flush()
                    conn.close()
                    break
                
        # If there is an unexpected disconnect in the game we should end game:
        except (ConnectionResetError, BrokenPipeError) as e:
            print(f"[ERROR] Connection error during game: {e}")
        
        self.broadcast_to_spectators("Game ended. Waiting for next match.")

        # now append remaining players back to queue
        remaining_players = []
        for player in players:
            conn, rfile, wfile, uname = player
            try:
                # Check if socket is still connected
                conn.getpeername()
                remaining_players.append(player)
            except OSError:
                # Socket is closed, ensure it's closed
                conn.close()
        
        # Notify remaining players of disconnection
        if len(remaining_players) == 1:
            self.packet_send("2;[Opponent disconnected] You win!", remaining_players[0][1], remaining_players[0][2])
        
        # Add remaining players back to the queue
        with self.lock:
            for p in remaining_players:
                p[0].setblocking(True)
                self.packet_send("2;You're back in the queue, waiting for match..", p[1], p[2])
                self.client_queue.append(p)
        return    

def main():
    server = GameServer()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[INFO] Server listening on {HOST}:{PORT}")
        
        while True:
            conn, addr = s.accept()
            threading.Thread(
                target=server.handle_client,
                args=(conn, addr)).start()

if __name__ == "__main__":
    main()