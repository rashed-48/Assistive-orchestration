from app.web.server import create_app


app = create_app()


if __name__ == "__main__":
    try:
        app.run(host="127.0.0.1", port=5000, debug=False)
    finally:
        # Leave the broker cleanly when the server stops.
        app.runtime.shutdown()
