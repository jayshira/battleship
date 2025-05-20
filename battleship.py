"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""

import random
import threading
import select
import zlib
import time

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]


class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
      - Each player has their own Board instance.
      - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations; 
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True

    
    def place_ships_manually(self, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")

    
    def place_ships_manually_mp(self, conn, rfile, wfile, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        def recv():
            return rfile.readline().strip()
        def packet_send(msg):
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
        
        # Helper function to show instruction
        def send_instructions():
            packet_send(f"0;For Coordinate, enter row letter followed by number column")
            packet_send(f"0;For Orientation, enter 'H' (horizontal) or 'V' (vertical)")
            packet_send(f"1;Enter starting coordinate and orientation (e.g. A1 H):")
        
        def timeout():
            nonlocal timeout_bool
            timeout_bool = True

        packet_send("0;[Ship Placement] Enter coordinates as prompted:")
        packet_send("0;Please place your ships manually on the board.")

        timeout_bool = False
        t = threading.Timer(180, timeout)
        t.start()

        for ship_name, ship_size in ships:
            self.print_display_grid_mp(wfile, show_hidden_board=True)
            packet_send(f"0;Placing your {ship_name} (size {ship_size}).")
            send_instructions()
            while True:
                time.sleep(0.5)
                if timeout_bool:
                    wfile.write("X\n") # tell client that their session has been terminated
                    wfile.flush()
                    conn.close()
                    raise(TimeoutError)

                command = recv()
                if not command:
                    continue
                
                try:
                    coord_str, orientation_str = command.split(" ")
                    orientation_str = orientation_str.upper()
                except:
                    packet_send("0;[!] Invalid Input Format")
                    send_instructions()
                    continue

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    packet_send(f"0;[!] Invalid coordinate: {e}")
                    send_instructions()
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    packet_send("0;[!] Invalid orientation. Please enter 'H' or 'V'.")
                    send_instructions()
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    packet_send(f"0;[!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")
        
        t.cancel()
        self.print_display_grid_mp(wfile, show_hidden_board=True)
        packet_send("2;Placement finished. Here is your board. Waiting for opponent...")  # Signal end of placement

    def print_display_grid_mp(self, wfile, show_hidden_board=False):
        """
        Print the board as a 2D grid.
        
        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.
        
        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
    
        # Decide which grid to print
        display_grid = self.hidden_grid if show_hidden_board else self.display_grid

        wfile.write("GRID\n")
        wfile.write("+ " + " ".join(str(i + 1).rjust(2) for i in range(self.size)) + '\n')
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = "  ".join(display_grid[r][c] for c in range(self.size))
            wfile.write(f"{row_label:2} {row_str}\n")
        wfile.write('\n')
        wfile.flush()

    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
          - ('hit', None)          if it's a hit but not sunk
          - ('hit', <ship_name>)   if that shot causes the entire ship to sink
          - ('miss', None)         if no ship was there
          - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        cell = self.hidden_grid[row][col]
        if cell == 'S':
            # Mark a hit
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)  # A ship has just been sunk
            else:
                return ('hit', None)
        elif cell == '.':
            # Mark a miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.
        
        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.
        
        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")

    
    def get_display_grid_str(self, show_hidden_board=False):
        """
        This is just for Spectator mode.
        """
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid
        grid_str = "+ " + " ".join(str(i + 1).rjust(2) for i in range(self.size)) + "\n"
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = "  ".join(grid_to_print[r][c] for c in range(self.size))
            grid_str += f"{row_label:2} {row_str}\n"
        return grid_str


def parse_coordinate(coord_str):
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    HINT: you might want to add additional input validation here...
    """
    coord_str = coord_str.strip().upper()
    row_letter = coord_str[0]
    col_digits = coord_str[1:]

    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    return (row, col)


def place_ships_multiplayer(conn, rfile, wfile):
    """
    Place ships for the multiplayer game. This function is called in a separate thread for each client.
    """
    board = Board(BOARD_SIZE)
    board.place_ships_manually_mp(conn, rfile, wfile, SHIPS)
    return board

def run_multi_player_game_online(rfile, wfile, other_rfile, other_wfile, board):
    """
    DEFINITIONS:
    - PLAYING CLIENT: Currently their turn to shoot
    - WAITING CLIENT: waiting for other player to shoot
    """

    # SEND TO CURRENTLY PLAYING CLIENT
    def packet_send(msg):
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
    
    # RECEIVE FROM CURRENTLY PLAYING CLIENT
    def recv():
        return rfile.readline().strip()
    
    # SEND TO CURRENTLY WAITING CLIENT
    def other_packet_send(msg):
        msg = msg.strip()
        retry = 3
        while retry > 0:
            b_msg = msg.encode()
            checksum = zlib.crc32(b_msg)
            other_wfile.write(f"{checksum:08x};{msg}\n")
            other_wfile.flush()
            ready, _, _ = select.select([other_rfile], [], [], 30)
            if ready:
                message = other_rfile.readline().strip()
                if message == 'ACK':
                    return
            retry -= 1
        raise(BrokenPipeError)
    
    # RECEIVE FROM CURRENTLY WAITING CLIENT
    def recv_other():
        return other_rfile.readline().strip()

    def validate_coordinate(coord_str):
        try:
            row, col = parse_coordinate(coord_str)
            if 0 <= row < board.size and 0 <= col < board.size:
                return (row, col)
            return None
        except ValueError:
            return None

    def send_board(wfile=wfile, show_hidden_board=False):
        if show_hidden_board:
            display_grid = board.hidden_grid
            other_packet_send("0;[Your Board]")
        else:
            display_grid = board.display_grid
            packet_send("0;[Opponent's Board]")

        wfile.write("GRID\n")
        wfile.write("+ " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = "  ".join(display_grid[r][c] for c in range(board.size))
            wfile.write(f"{row_label:2} {row_str}\n")
        wfile.write('\n')
        wfile.flush()

    
    def skip():
        nonlocal timed_out
        timed_out = True
        return
    
    """ INITIALIZATION FOR THE TURN """
    # DISPLAY MESSAGES FOR BOTH PLAYERS
    other_packet_send("2;Waiting for opponent to fire...")
    send_board()
    packet_send("0;[Your turn!]")
    packet_send("1;Enter coordinate to fire (e.g. B5) or type \"quit\" to disconnect: ")

    # INITIALIZE TIMEOUT AND SKIPPING LOGIC
    t = threading.Timer(30, skip)
    t.start()
    timed_out = False

    """ TRIES TO GET COMMANDS FROM PLAYERS WITH TIMEOUT """ 
    while True:
        time.sleep(0.5) # checks for updates every 0.5 secs
        command = recv() # tries to receive message from playing client
        other_command = recv_other() # for chat messages and quit calls only

        # checks if it has timeout yet
        if timed_out:
            packet_send("2;Timeout occurred: Turn Skipped")
            other_packet_send("0;Enemy has timed out their turn is skipped")
            return 'timeout', None, None, None

        # if both quits at the same time, just clear client and reset
        if other_command.lower() == "quit" and command.lower() == "quit":
            return "all_forfeit", None, None, None
        
        # checks if waiting player has gotten command
        if other_command:
            if other_command.lower() == "quit": # waiting player disconnected
                packet_send("2;Attempting to reconnect opponent, please wait...")
                return "other_player_dc", None, None, None
            elif other_command.lower().startswith("chat "): # waiting player wants to chat
                packet_send(f"3;[CHAT] Opponent: {other_command[5:]}")
                other_packet_send(f"4;[CHAT] You: {other_command[5:]}")
        
        # checks if playing player has gotten command
        # if player gotten command, then can continue rest of function
        if not command:
            continue  # Empty input
        
        if command.lower() == "quit": # playing player disconnected
            other_packet_send("2;Attempting to reconnect opponent, please wait...")
            return "player_dc", None, None, None
        elif command.lower().startswith("chat "): # playing player wants to chat
            other_packet_send(f"3;[CHAT] Opponent: {command[5:]}")
            packet_send(f"4;[CHAT] You: {command[5:]}")
            continue
        
        # checking if it is a valid coordinate to fire to.
        # if not valid then must go through check process again
        coord = validate_coordinate(command)
        if coord:
            row, col = coord
            result, sunk_name = board.fire_at(row, col)
            if result == 'already_shot':
                packet_send("1;You already fired at this location. Try another target.")
                continue
            break
        packet_send("1;Invalid coordinate. Must be A-J followed by 1-10 (e.g. B5). Try again:")
    
    t.cancel() #stop timeout timer
    
    """ INPUT HAS BEEN VALIDATED, HANDLING SHOT """

    # SEND RESULT TO EACH PLAYER
    send_board()
    send_board(other_wfile, show_hidden_board=True)

    # PROCESS SHOT
    other_packet_send(f"0;Opponent fired an attack on ({chr(ord('A') + row)}{col + 1})")
    if result == 'hit': # hit
        if sunk_name: # sink
            packet_send(f"2;HIT! You sank the {sunk_name}!")
            other_packet_send(f"0;HIT! Opponent sunk your {sunk_name}!")
            if board.all_ships_sunk(): # game over
                packet_send("0;GAME_OVER All enemy ships sunk! You win!")
                other_packet_send("0;GAME_OVER You lost! All your ships are sunk.")
                return "game_finished", None, None, None
        else:
            other_packet_send("0;HIT! Opponent hit your ship!")
            packet_send("2;HIT!")
    elif result == 'miss': # miss
        other_packet_send("0;MISS! Opponent missed!")
        packet_send("2;MISS!")
    
    coord_label = str(chr(ord('A') + row)) + str((col + 1))

    # FINISH TURNS
    return "turn_completed", coord_label, result, sunk_name