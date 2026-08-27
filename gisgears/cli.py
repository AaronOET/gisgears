#!/usr/bin/env python
"""
Top-level `gisgears` command. Running `gisgears -h` (or with no arguments)
prints the same information shown by `gisgears-info`. Running `gisgears -v`
prints the installed gisgears version.
"""

import sys

from . import __version__, describe


def _print_info(tool=None):
    argv_backup = sys.argv
    try:
        sys.argv = ['gisgears-info'] + ([tool] if tool else [])
        describe.main()
    finally:
        sys.argv = argv_backup


def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        _print_info()
        return

    if args[0] in ('-v', '--version'):
        print(f"gisgears {__version__}")
        return

    tool = args[0]
    if tool in describe.TOOL_DESCRIPTIONS:
        _print_info(tool)
        return

    print(f"Unknown option or tool: {tool}", file=sys.stderr)
    print("Run 'gisgears -h' to see available tools.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
