"""Local-only application entry point."""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="The Twins experimental console")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("twins.server:app", host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
