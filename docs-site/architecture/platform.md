---
title: Platform port
description: Why Coffer keeps every operating-system difference in one place, what kinds of questions go through it, how a build gate protects the rule, and what to do when a new OS-dependent need appears.
---

# Platform port

Coffer ships for macOS only, but its foundation is not allowed to assume macOS. This page explains the idea that makes both true at once: exactly one part of the codebase knows which operating system Coffer runs on, and everything else asks it. Read it before writing anything whose behaviour would differ between operating systems. The decision itself, and the alternatives that were weighed, are recorded in the ADR [Platform Differences Live Behind One Platform Port](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/platform-differences-live-behind-one-platform-port.md).

## The problem

A local tool that manages files, processes and desktop applications touches the operating system all the time, and the answers differ from one OS to the next. Opening a file in the user's editor, revealing it in the file manager and showing a native folder picker are different programs on macOS, Linux and Windows. A skill is delivered to an agent as a symbolic link on macOS and Linux, but on Windows a symbolic link may need special privileges, so the fallback there is a directory junction or, failing that, a copy. Starting the daemon at login is a launchd agent on macOS and has no direct equivalent elsewhere. Even "which directories belong to the system and must never receive a skill" depends on the OS.

Left alone, each of these differences gets answered wherever it is first needed, as a small "if this is macOS" check. Coffer had accumulated such checks across both the application and the infrastructure layers. That has two costs:

- **Porting becomes archaeology.** Supporting a second operating system means finding every scattered check. A check that is missed does not fail loudly; it quietly does the macOS thing on the new OS.
- **Use cases stop being testable on their own.** A service that branches on the OS can only be tested by pretending to be each OS, and the test ends up proving the branch rather than the use case.

## The idea

One place knows the operating system; everything else asks it.

That place lives in the infrastructure layer, because answering OS questions is adapter work, the same kind of work as talking to the database or to an SDK. The application layer does not reach down into it. Instead, the application declares the questions it needs answered as a port, and the composition root hands it the one implementation that knows the host. This is the same shape every other adapter in Coffer follows (see [Layering and code layout](/architecture/layering)). The rest of the infrastructure layer is allowed to use the platform code directly, since it sits in the same layer.

The questions are deliberately small and answer-shaped: "which command opens this file here?", "which paths are the system's own?". They are not "go and do it". The application still decides whether a path is valid, spawns the process and turns failures into errors a user understands. The platform part only supplies the per-OS fact. That keeps the port easy to replace with a fixed answer in a test, so a use case can be tested once, independent of any OS. The platform part is tested separately, once per operating system.

Only the macOS answers are released. Where another OS already has a known, cheap answer, such as a junction or a copy on Windows, or the usual Linux desktop tools, that answer lives in the same place and is covered by unit tests, but it is not claimed as supported.

## What goes through it

Today the platform part answers these kinds of questions:

- **Identity.** Which OS this is, how to describe it to a person (for example on a machine's sync record), and the stable machine identifier the OS itself keeps.
- **System locations.** Which directories belong to the operating system, the exceptions inside them that are safe to use, and quirks of path comparison such as macOS reaching system folders through a hidden alias.
- **Desktop actions.** How to open a file or folder, open it in a chosen editor, reveal it in the file manager, show a native folder picker, and tell whether a given editor is installed.
- **Directory links.** How to link a directory with the best mechanism the OS offers (symbolic link, junction or copy), and how to recognise which kind is already on disk.
- **Processes and services.** What an executable is called, how to start a child process that outlives its parent, and whether a login-service manager such as launchd exists.

A few OS assumptions are not behind the port yet, because they never carried an explicit check: replacing a file atomically when another program holds it open, stopping processes with signals, the links Coffer creates for its own binaries, a shell snippet Coffer writes into one agent's configuration, and the conventions for Coffer's own home directory and each agent's default configuration directory. None of them changes behaviour on macOS. Moving them is the second part of the ADR.

## How the rule is protected

Import rules cannot enforce this. The standard library modules that reveal the OS are imported legitimately everywhere, and the telltale sign is reading an attribute, not importing a module. So Coffer has a dedicated build gate, run as part of `make lint` and therefore of every `make verify` and every pull request.

The gate reads the source code as a syntax tree instead of searching it as text. It fails the build when any code outside the platform part reads the OS name, calls one of the standard functions that identify the host, or imports those names under another name. Because it reads the syntax tree, it follows renamed imports, and it does not mistake an ordinary variable that happens to be called "platform" for the standard module. It applies to every layer, infrastructure included. Tests are exempt, because pretending to be a different OS is exactly how a test covers the per-OS answers.

When the gate fails, it names the file, the line and the expression it objected to.

## When a new OS-dependent need appears

When new code needs an answer that differs by operating system:

1. **Put the knowledge in the platform part.** Add the per-OS answer there, next to the others of its kind. Give the macOS answer exactly as the release needs it. Give Windows and Linux a real answer when one is cheap, and otherwise an explicit fallback, such as "no picker available" or "copy instead of link", that the caller can handle.
2. **If the caller is in the application layer, ask through the port.** Add one question to the port that matches what the use case needs to know, and answer it in the host implementation. Code in the infrastructure layer uses the platform part directly and skips this step.
3. **Receive it, never reach for it.** A service that needs the port takes it when it is constructed, and the composition root passes the one host implementation it already built.
4. **Test both halves separately.** Test the platform answer once per operating system, and test the use case with a fixed-answer stand-in for the port.

If the gate flags code you did not think of as an OS check, move it anyway: a value that depends on the operating system is an OS check, whatever it is used for.
