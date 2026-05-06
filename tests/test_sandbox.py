"""Tier 3: sandbox.run_python — output handling and error formatting.

The sandbox shells out to a Python subprocess. We mock `subprocess.run` so the
tests are fast and hermetic. The subprocess runner template itself is exercised
indirectly via the existing integration paths.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent import sandbox


def _result(stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_run_python_returns_stdout_on_success():
    with patch.object(subprocess, "run", return_value=_result(stdout="hello\n")):
        out = sandbox.run_python("print('hello')")
    assert out == "hello\n"


def test_run_python_no_output_message():
    with patch.object(subprocess, "run", return_value=_result(stdout="")):
        out = sandbox.run_python("x = 1")
    assert "No output" in out


def test_run_python_truncates_long_output():
    big = "a" * (sandbox.MAX_OUTPUT_CHARS + 500)
    with patch.object(subprocess, "run", return_value=_result(stdout=big)):
        out = sandbox.run_python("print('x')")
    assert out.endswith("...[truncated]")
    assert len(out) <= sandbox.MAX_OUTPUT_CHARS + len("\n...[truncated]")


def test_run_python_timeout_returns_error_string():
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=30)
    with patch.object(subprocess, "run", side_effect=boom):
        out = sandbox.run_python("while True: pass")
    assert "timed out" in out.lower()


def test_run_python_extracts_traceback_on_failure():
    stderr = (
        "Some unrelated warning\n"
        "Traceback (most recent call last):\n"
        '  File "<string>", line 1, in <module>\n'
        "ZeroDivisionError: division by zero\n"
    )
    with patch.object(subprocess, "run", return_value=_result(stderr=stderr, returncode=1)):
        out = sandbox.run_python("1/0")
    assert "Traceback" in out
    assert "ZeroDivisionError" in out


def test_run_python_includes_stdout_alongside_error():
    stderr = "Traceback (most recent call last):\nValueError: bad\n"
    with patch.object(
        subprocess, "run",
        return_value=_result(stdout="partial output\n", stderr=stderr, returncode=1),
    ):
        out = sandbox.run_python("print('partial output'); raise ValueError('bad')")
    assert "partial output" in out
    assert "ValueError" in out


def test_run_python_falls_back_when_no_traceback_in_stderr():
    stderr = "command not found"
    with patch.object(subprocess, "run", return_value=_result(stderr=stderr, returncode=1)):
        out = sandbox.run_python("garbage")
    assert "command not found" in out
