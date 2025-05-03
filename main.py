import berserk
import chess
import time
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.text import Text
from openai import OpenAI

# OpenAI client (for OpenRouter)
openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
)

# CONFIG
API_TOKEN = "lip_EUSd66E83bMdun8u0wU0"
USERNAME = "dzoomaster"
POLL_INTERVAL = 1  # seconds

console = Console()

# Lichess client
session = berserk.TokenSession(API_TOKEN)
lichess_client = berserk.Client(session)

def get_current_game(username):
    try:
        return list(lichess_client.games.get_ongoing(username))
    except berserk.exceptions.ResponseError:
        return []

def evaluate_position_material(fen):
    board = chess.Board(fen)
    piece_values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                    chess.ROOK: 5, chess.QUEEN: 9}
    white_material = sum(piece_values.get(piece.piece_type, 0)
                         for piece in board.piece_map().values() if piece.color == chess.WHITE)
    black_material = sum(piece_values.get(piece.piece_type, 0)
                         for piece in board.piece_map().values() if piece.color == chess.BLACK)
    return white_material - black_material

def evaluate_position_online(fen, depth=12):
    url = "https://stockfish.online/api/s/v2.php"
    params = {"fen": fen, "depth": depth}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("success"):
            eval_cp = data.get("evaluation")
            mate = data.get("mate")
            bestmove = data.get("bestmove")
            continuation = data.get("continuation")
            return eval_cp, mate, bestmove, continuation
        else:
            console.print(f"[bold red]⚠️ API error: {data.get('data')}")
            return None, None, None, None
    except Exception as e:
        console.print(f"[bold red]⚠️ API request failed: {e}")
        return None, None, None, None

def draw_eval_bar(eval_score, max_score=15):
    bar_length = 30
    eval_clamped = max(min(eval_score, max_score), -max_score)
    filled_length = int((eval_clamped + max_score) / (2 * max_score) * bar_length)
    bar = "█" * filled_length + " " * (bar_length - filled_length)
    color = "green" if eval_score > 0 else "red" if eval_score < 0 else "yellow"
    return f"[{color}]{bar}[/{color}]"

def print_game_pgn(game_id):
    try:
        pgn_data = lichess_client.games.export(game_id, as_pgn=True)
        console.rule("[bold blue]📄 Game PGN")
        console.print(pgn_data, highlight=False)

        # 🎯 AI analysis after game ends
        console.rule("[bold magenta]🤖 AI Coach Analysis of Full Game")
        completion = openai_client.chat.completions.create(
            extra_body={},
            model="qwen/qwen3-0.6b-04-28:free",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional chess coach. Given a PGN game, analyze it thoroughly. Highlight key moments, critical mistakes, brilliant moves, and suggest improvements."
                },
                {
                    "role": "user",
                    "content": f"Here is the PGN of the game:\n{pgn_data}"
                }
            ]
        )
        console.print(completion.choices[0].message.content)

    except berserk.exceptions.ResponseError as e:
        console.print(f"[bold red]⚠️ Failed to fetch PGN: {e}")

def main():
    console.rule(f"[bold cyan]🔍 Monitoring {USERNAME}'s Ongoing Game...")
    last_fen = None
    last_game_id = None
    game_active = False

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:

        while True:
            game_list = get_current_game(USERNAME)
            if game_list:
                game_active = True
                game = game_list[0]
                fen = game['fen']
                game_id = game['gameId']
                move_number = game.get('turns')
                if move_number is None:
                    board = chess.Board(fen)
                    move_number = board.fullmove_number

                last_game_id = game_id  # save last active game id

                if fen != last_fen:
                    eval_material = evaluate_position_material(fen)
                    eval_engine, mate, bestmove, continuation = evaluate_position_online(fen)

                    eval_bar_material = draw_eval_bar(eval_material)
                    eval_bar_engine = draw_eval_bar(eval_engine if eval_engine is not None else (1000 if mate and mate > 0 else -1000))

                    console.clear()
                    console.rule("[bold green]♟️ New Position Detected")
                    console.print(Panel.fit(f"[white]FEN:[/white] {fen}", title=f"Game ID: {game_id}"))

                    eval_text_material = Text(
                        f"Local Eval (material): {eval_material:+}",
                        style="bold green" if eval_material > 0 else "bold red" if eval_material < 0 else "bold yellow"
                    )
                    console.print(eval_text_material)
                    console.print(eval_bar_material)

                    if eval_engine is not None or mate is not None:
                        if mate is not None:
                            eval_text_engine = Text(f"Engine Eval: Mate in {mate}", style="bold magenta")
                        else:
                            eval_text_engine = Text(
                                f"Engine Eval: {eval_engine:+}",
                                style="bold green" if eval_engine > 0 else "bold red" if eval_engine < 0 else "bold yellow"
                            )
                        console.print(eval_text_engine)
                        console.print(eval_bar_engine)
                        console.print(f"[bold cyan]Best move: {bestmove}")
                        console.print(f"[grey]Line: {continuation}")
                    else:
                        console.print("[bold yellow]⚠️ Engine evaluation unavailable.")

                    console.print(f"[grey]Move number: {move_number}")
                    last_fen = fen

            else:
                if game_active and last_game_id:
                    console.print("[bold yellow]⚠️ No ongoing game found. Fetching PGN of last game...")
                    print_game_pgn(last_game_id)
                else:
                    console.print("[bold yellow]⚠️ No ongoing game found. Exiting.")
                break
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
