"""Execute legacy suites with explicit unsupported discovery/coverage status."""

from pathlib import Path

from coverage_eval.models import Capabilities, Run
from coverage_eval.utils import command, environment, expand, variables


class CommandRunner:
    capabilities = Capabilities(False, False, False, False)

    def validate(self, suite):
        if not suite.command:
            raise ValueError(f"{suite.name}: command runner requires command")

    def discover(self, context, files, *, baseline=False):
        raise NotImplementedError("command runner cannot attribute individual cases")

    def run(self, context, cases=None):
        if cases is not None:
            return Run(None, "unsupported")
        values = variables(context.paths, repo=context.repo, output=context.output, suite=context.suite.name)
        code = command(expand(context.suite.command + context.suite.args, values), cwd=context.cwd,
                       env=environment(context), log=context.output.parent / (context.suite.name + ".log"))
        if context.suite.result_directory:
            source = Path(context.suite.result_directory.format_map(values))
            source.rename(context.output)
        return Run(code, "unsupported")
