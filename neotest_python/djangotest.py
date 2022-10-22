import inspect
import os
import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any, Dict, List, TextIO, Tuple, Optional
import django
from django.test import TestCase
from django.conf import settings
from django.test.runner import DiscoverRunner
from unittest import TestResult
from unittest.runner import TextTestResult

from .base import NeotestAdapter, NeotestResultStatus


class DjangoNeotestAdapter(NeotestAdapter):
    def id_to_unittest_args(self, case_id: str) -> List[str]:
        """Converts a neotest ID into test specifier for unittest"""
        path, *child_ids = case_id.split("::")
        if not child_ids:
            if os.path.isfile(path):
                # Test files can be passed directly to unittest
                relative_file = os.path.relpath(path, os.getcwd())
                relative_stem = os.path.splitext(relative_file)[0]
                relative_dotted = relative_stem.replace(os.sep, ".")
                return [relative_dotted]
            # Directories need to be run via the 'discover' argument
            return [case_id]

        # Otherwise, convert the ID into a dotted path, relative to current dir
        relative_file = os.path.relpath(path, os.getcwd())
        relative_stem = os.path.splitext(relative_file)[0]
        relative_dotted = relative_stem.replace(os.sep, ".")
        return [".".join([relative_dotted, *child_ids])]

    def run(self, args: List[str], stream) -> Dict:
        class NeotestTextTestResult(TextTestResult):
            def __init__(
                self, stream: TextIO, descriptions: bool, verbosity: int
            ) -> None:
                super().__init__(stream, descriptions, verbosity)
                self.neo_results = {}

            def case_file(self, case) -> str:
                return str(Path(inspect.getmodule(case).__file__).absolute())  # type: ignore

            def case_id_elems(self, case) -> List[str]:
                file = self.case_file(case)
                elems = [file, case.__class__.__name__]
                if isinstance(case, TestCase):
                    elems.append(case._testMethodName)
                return elems

            def case_id(self, case: "TestCase | TestSuite") -> str:
                return "::".join(self.case_id_elems(case))

            def addFailure(self, test: TestCase, err) -> None:
                super().addFailure(test, err)
                case_id = self.case_id(test)
                error_line = None
                case_file = self.case_file(test)
                trace = err[2]
                print(f"trace {trace}")
                summary = traceback.extract_tb(trace)
                error_line = next(
                    frame.lineno - 1
                    for frame in reversed(summary)
                    if frame.filename == case_file
                )
                self.neo_results[case_id] = {
                    "status": NeotestResultStatus.FAILED,
                    "errors": [{"message": None, "line": error_line}],
                    "short": None,
                }
                stream(case_id, self.neo_results[case_id])

            def addError(self, test: TestCase, err) -> None:
                super().addError(test, err)
                case_id = self.case_id(test)
                error_line = None
                case_file = self.case_file(test)
                trace = err[2]
                print(f"error trace {trace}")
                summary = traceback.extract_tb(trace)
                error_line = next(
                    frame.lineno - 1
                    for frame in reversed(summary)
                    if frame.filename == case_file
                )
                print(f"errprlins: {error_line}")
                self.neo_results[case_id] = {
                    "status": NeotestResultStatus.FAILED,
                    "errors": [{"message": None, "line": error_line}],
                    "short": None,
                }
                stream(case_id, self.neo_results[case_id])

            def addSuccess(self, test: TestCase) -> None:
                super().addSuccess(test)
                self.neo_results[self.case_id(test)] = {
                    "status": NeotestResultStatus.PASSED,
                }
                stream(self.case_id(test), self.neo_results[self.case_id(test)])

        class NeotestDjangoRunner(DiscoverRunner):
            def __init__(self, **kwargs):
                super().__init__(interactive=False, keepdb=True, **kwargs)

            def get_resultclass(self) -> NeotestTextTestResult:
                return NeotestTextTestResult

            def suite_result(self, suite, result, **kwargs):
                return result.neo_results

        # Make sure we can import relative to current path
        sys.path.insert(0, os.getcwd())
        # We only get a single case ID as the argument
        print(f"Args {args}")
        argv = sys.argv[0:1] + self.id_to_unittest_args(args[-1])
        django.setup()
        test_runner = NeotestDjangoRunner()
        result = test_runner.run_tests(test_labels=[argv[1]])
        return result
