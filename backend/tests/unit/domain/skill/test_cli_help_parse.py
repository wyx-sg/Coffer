"""Help text of the formats in common use, read into a node (spec
skill-manager "Serve required commands on REST and the web")."""

from __future__ import annotations

from coffer.domain.skill.cli_help import HelpNode
from coffer.domain.skill.cli_help_parse import parse_help

CLICK = """Usage: tool [OPTIONS] COMMAND [ARGS]...

  A tool that does things.

Options:
  --verbose / --quiet  Be loud.
  -n, --name TEXT      Your name  [required]
  -c, --count INTEGER  How many  [default: 3]
  --help               Show this message and exit.

Commands:
  init  Initialise
  run   Run it
"""

TYPER = """
 Usage: app [OPTIONS] COMMAND [ARGS]...

 A typer app.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ *  --name   -n      TEXT     Your name [required]                            │
│    --help                    Show this message and exit.                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ hello   Say hello                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
"""

ARGPARSE = """usage: prog [-h] [--count COUNT] {commit,add} ...

Does things.

positional arguments:
  {commit,add}
    commit      Record changes
    add         Add files
  name          Who

options:
  -h, --help    show this help message and exit
  -c COUNT, --count COUNT
                number of things (default: 3)
"""

COBRA = """Work seamlessly with GitHub.

Usage:
  gh <command> <subcommand> [flags]

Available Commands:
  pr          Manage pull requests
  repo        Manage repositories

Flags:
  -h, --help            help for gh
      --config string   path to config (default "x.yml")
      --version         Show version

Use "gh [command] --help" for more information about a command.
"""

CLAP = """A fast tool

Usage: fd [OPTIONS] [pattern] [path]...

Arguments:
  [pattern]  the search pattern
  [path]...  root dirs

Options:
  -H, --hidden           Search hidden files
  -e, --extension <ext>  Filter by ext [default: all]
  -h, --help             Print help
"""

COMMANDER = """Usage: pkg [options] [command]

Package things

Options:
  -V, --version             output the version number
  -d, --dir <path>          where to work
  -h, --help                display help for command

Commands:
  install [options] <name>  install a package
  help [command]            display help for command
"""

GH = """Work with GitHub.

USAGE
  gh <command> <subcommand> [flags]

CORE COMMANDS
  issue:       Manage issues
  pr:          Manage pull requests

FLAGS
  --help      Show help for command
"""

GIT = """usage: git [-v | --version] [-h | --help] <command> [<args>]

These are common Git commands used in various situations:

start a working area (see also: git help tutorial)
   clone     Clone a repository into a new directory
   init      Create an empty Git repository

work on the current change (see also: git help everyday)
   add       Add file contents to the index
"""


def _names(node: HelpNode) -> list[str]:
    return [s.name for s in node.subcommands]


def test_click_plain() -> None:
    node = parse_help(CLICK, ())
    assert node.structured and node.usage == "tool [OPTIONS] COMMAND [ARGS]..."
    assert node.description == "A tool that does things."
    assert [(s.name, s.summary) for s in node.subcommands] == [
        ("init", "Initialise"),
        ("run", "Run it"),
    ]
    by = {o.names: o for o in node.options}
    assert ("--verbose", "--quiet") in by and by[("--verbose", "--quiet")].description == "Be loud."
    name = by[("-n", "--name")]
    assert (name.metavar, name.required, name.description) == ("TEXT", True, "Your name")
    assert by[("-c", "--count")].default == "3"


def test_typer_rich_boxes() -> None:
    node = parse_help(TYPER, ("sub",))
    assert node.path == ("sub",)
    assert node.usage == "app [OPTIONS] COMMAND [ARGS]..."
    assert node.description == "A typer app."
    assert _names(node) == ["hello"]
    name = node.options[0]
    assert name.names == ("--name", "-n") and name.metavar == "TEXT" and name.required
    assert node.options[1].names == ("--help",) and not node.options[1].required


def test_argparse_with_subparsers() -> None:
    node = parse_help(ARGPARSE, ())
    assert node.usage and node.usage.startswith("prog [-h]")
    assert node.description == "Does things."
    assert [(s.name, s.summary) for s in node.subcommands] == [
        ("commit", "Record changes"),
        ("add", "Add files"),
    ]
    assert [(a.name, a.required) for a in node.arguments] == [("name", True)]
    count = next(o for o in node.options if "--count" in o.names)
    assert (count.names, count.metavar, count.default) == (("-c", "--count"), "COUNT", "3")
    assert count.description == "number of things"


def test_cobra() -> None:
    node = parse_help(COBRA, ())
    assert node.usage == "gh <command> <subcommand> [flags]"
    assert node.description == "Work seamlessly with GitHub."
    assert _names(node) == ["pr", "repo"]
    config = next(o for o in node.options if o.names == ("--config",))
    assert (config.metavar, config.default) == ("string", "x.yml")


def test_clap() -> None:
    node = parse_help(CLAP, ())
    assert [(a.name, a.required) for a in node.arguments] == [
        ("pattern", False),
        ("path", False),
    ]
    ext = next(o for o in node.options if "--extension" in o.names)
    assert (ext.metavar, ext.default) == ("ext", "all")
    assert node.description == "A fast tool"


def test_commander_takes_the_first_word_of_a_command() -> None:
    node = parse_help(COMMANDER, ())
    assert _names(node) == ["install", "help"]
    assert node.subcommands[0].summary == "install a package"
    directory = next(o for o in node.options if "--dir" in o.names)
    assert directory.metavar == "path"


def test_gh_capitalised_headings() -> None:
    node = parse_help(GH, ())
    assert _names(node) == ["issue", "pr"]
    assert node.subcommands[1].summary == "Manage pull requests"
    assert node.usage == "gh <command> <subcommand> [flags]"


def test_git_group_titles_do_not_end_the_command_list() -> None:
    node = parse_help(GIT, ())
    assert _names(node) == ["clone", "init", "add"]


def test_text_with_no_structure_is_kept_raw_and_unstructured() -> None:
    text = "This tool has no help to speak of.\nTry reading the manual.\n"
    node = parse_help(text, ("x",))
    assert not node.structured and node.raw == text
    assert node.subcommands == () and node.options == () and node.arguments == ()


def test_ansi_colour_codes_are_ignored() -> None:
    node = parse_help(
        "\x1b[1mUsage:\x1b[0m tool [OPTIONS]\n\n\x1b[1mOptions:\x1b[0m\n  -q  Quiet\n", ()
    )
    assert node.usage == "tool [OPTIONS]" and node.options[0].names == ("-q",)


def test_hostile_text_does_not_hang_or_raise() -> None:
    nasty = ("Options:\n" + "  " + "-" * 50_000 + " " * 50_000 + "x\n") * 3 + "│" * 100_000
    node = parse_help(nasty, ())
    assert node.raw == nasty
