import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="vox2txt",
        description="Push-to-talk speech to text. Hold a key, speak, release, "
        "and the transcription is pasted into the focused window.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser(
        "setup",
        help="Prepare platform permissions where needed and optionally enable autostart",
    )
    sub.add_parser("config", help="Show the config file path, creating it if missing")
    sub.add_parser("doctor", help="Check configuration and platform prerequisites")

    args = parser.parse_args(argv)

    if args.command == "setup":
        from .setup_cmd import run_setup
        return run_setup()

    if args.command == "config":
        from .config import write_default_config
        print(write_default_config())
        return 0

    if args.command == "doctor":
        from .setup_cmd import run_doctor
        return run_doctor()

    from .app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
