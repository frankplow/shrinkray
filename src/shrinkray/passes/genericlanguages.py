"""
Module of reduction passes designed for "things that look like programming languages".
"""

from functools import wraps
import re
from typing import Callable, AnyStr

from attr import define
from shrinkray.problem import (
    BasicReductionProblem,
    Format,
    ParseError,
    ReductionProblem,
)
from shrinkray.reducer import ReductionPass
import trio


@define(frozen=True)
class Substring(Format[AnyStr, AnyStr]):
    prefix: AnyStr
    suffix: AnyStr

    @property
    def name(self) -> str:
        return f"Substring({len(self.prefix)}, {len(self.suffix)})"

    def parse(self, input: AnyStr) -> AnyStr:
        if input.startswith(self.prefix) and input.endswith(self.suffix):
            return input[len(self.prefix) : len(input) - len(self.suffix)]
        else:
            raise ParseError()

    def dumps(self, input: AnyStr) -> AnyStr:
        return self.prefix + input + self.suffix


def regex_pass(
    pattern: AnyStr | re.Pattern[AnyStr],
) -> Callable[[ReductionPass[AnyStr]], ReductionPass[AnyStr]]:
    if not isinstance(pattern, re.Pattern):
        pattern = re.compile(pattern)  # type: ignore

    def inner(fn):
        @wraps(fn)
        async def reduction_pass(problem: ReductionProblem[AnyStr]) -> None:
            matching_regions = []

            i = 0
            while i < len(problem.current_test_case):
                search = pattern.search(problem.current_test_case, i)
                if search is None:
                    break

                u, v = search.span()
                matching_regions.append((u, v))

                i = v

            if not matching_regions:
                return

            initial = problem.current_test_case

            replacements = [initial[u:v] for u, v in matching_regions]

            def replace(i: int, s: AnyStr) -> AnyStr:
                empty = initial[:0]

                parts = []

                prev = 0
                for j, (u, v) in enumerate(matching_regions):
                    parts.append(initial[prev:u])
                    if j != i:
                        parts.append(replacements[j])
                    else:
                        parts.append(s)
                    prev = v

                parts.append(initial[prev:])

                return empty.join(parts)

            async with trio.open_nursery() as nursery:

                async def reduce_region(i):
                    async def is_interesting(s):
                        retries = 0
                        while True:
                            # Other tasks may have updated the test case, so when we
                            # check whether something is interesting but it doesn't update
                            # the test case, this means something has changed. Given that
                            # we found a promising reduction, it's likely to be worth trying
                            # again. In theory an uninteresting test case could also become
                            # interesting if the underlying test case changes, but that's
                            # not likely enough to be worth checking.
                            attempt = replace(i, s)
                            if not await problem.is_interesting(attempt):
                                return False
                            if replace(i, s) == attempt:
                                replacements[i] = s
                                return True
                            retries += 1

                            # If we've retried this many times then something has gone seriously
                            # wrong with our concurrency approach and it's probably a bug.
                            assert retries <= 100

                    subproblem = BasicReductionProblem(
                        replacements[i],
                        is_interesting,
                        work=problem.work,
                    )  # type: ignore

                    nursery.start_soon(fn, subproblem)

                for i in range(len(matching_regions)):
                    await reduce_region(i)

        return reduction_pass

    return inner


async def reduce_integer(problem: ReductionProblem[int]) -> None:
    assert problem.current_test_case >= 0

    if await problem.is_interesting(0):
        return

    lo = 0
    hi = problem.current_test_case

    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if await problem.is_interesting(mid):
            hi = mid
        else:
            lo = mid

        if await problem.is_interesting(hi - 1):
            hi -= 1

        if await problem.is_interesting(lo + 1):
            return
        else:
            lo += 1


class IntegerFormat(Format[bytes, int]):
    def parse(self, s: bytes) -> int:
        try:
            return int(s.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise ParseError()

    def dumps(self, i: int) -> bytes:
        return str(i).encode("ascii")


@regex_pass(b"[0-9]+")
async def reduce_integer_literals(problem):
    await reduce_integer(problem.view(IntegerFormat()))


@regex_pass(rb"[0-9]+ [*+-/] [0-9]+")
async def combine_expressions(problem):
    try:
        await problem.is_interesting(
            str(eval(problem.current_test_case)).encode("ascii")
        )
    except ArithmeticError:
        pass


def language_passes(problem: ReductionProblem[bytes]):
    yield reduce_integer_literals
    yield combine_expressions