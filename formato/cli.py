import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formato",
        description="GitHub PR clipboard formatter for Slack",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Start the clipboard monitor (default)")
    sub.add_parser("install", help="Install as a launchd login agent")

    args = parser.parse_args()

    if args.command == "install":
        from formato.install import install
        install()
    else:
        from formato.core import run
        run()
