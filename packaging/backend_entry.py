import os

from src.api import start_server


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    start_server(host="127.0.0.1", port=port, debug=False)
