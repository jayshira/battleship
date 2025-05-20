
# Multiplayer Battleship Game (Python)

This is a Python-based implementation of the classic **Battleship** game designed for **multiplayer** gameplay over a network. The project includes both a **server** and a **client**, with support for **player reconnection**.


## 📁 Files

| File | Description |
|------|-------------|
| `server.py` | Runs the Battleship server, handles connections, game state, and reconnections. |
| `client.py` | Connects to the server as a Battleship player. Supports reconnection. |
| `battleship.py` | Shared game logic used by both client and server: board management, ship placement, shot validation, and win checking. |

## How to Run the Files

### Requirements

- Python 3
- Runs locally using the python built-in libraries (no third-party packages needed)

### 1. Start the Server
Run:
```bash
python3 server.py
```

The server will listen on `HOST:PORT` based on the HOST and PORT configuration made in the beginning of the server code.

### 2. Start the Clients (players)

In two separate terminals, run:
```bash
python3 client.py
```

You'll be prompted to enter your player name (used for reconnection), and then place your ships on a 10x10 board (`BOARD_SIZE = 10`).

### 2. Start the Clients (spectators)

For the rest of the terminals, you can run:

```bash
python3 client.py
```
to wait on the queue while spectating the current match. The queue follows the "First In First Out" algorithm. Hence, after the match ends, the first two players in the queue will start a new game.
## 🕹️ How to Play

- Player first sign in with their username and place their ships on wherever they desire.
- After all ships are placed, the game starts.
- Players take turns firing shots at each other’s hidden ship grid.
- Each turn:
  - The current player types coordinates to fire (e.g., `A3`).
  - The server responds with hit/miss and updates both players.
- The first player to sink all opponent ships wins.

### Ship Placement

Each player places:
- 1 ship of size 5
- 1 ship of size 4
- 2 ships of size 3
- 1 ship of size 2

Example input:  `A1 H`

## 🔄 Reconnection

If a player disconnects (e.g., closes the client or loses connection), they can **reconnect** by rerunning `python3 client.py` and entering the **same username**.

The server remembers their game state and resumes the session.

## Author
Christopher Chandra (23993402)
Jason Aradea Yulfan (24078797)

