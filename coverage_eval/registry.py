"""Explicit built-in adapters. Add an implementation and one registry entry."""

from coverage_eval.readers.coverage_py import CoveragePyReader
from coverage_eval.readers.istanbul import IstanbulReader
from coverage_eval.runners.command import CommandRunner
from coverage_eval.runners.jest import JestRunner
from coverage_eval.runners.pytest import PytestRunner


RUNNERS = {"pytest": PytestRunner, "jest": JestRunner, "command": CommandRunner}
READERS = {"coverage_py": CoveragePyReader, "istanbul": IstanbulReader}
