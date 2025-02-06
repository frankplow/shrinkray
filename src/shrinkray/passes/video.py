from shrinkray.passes.definitions import ReductionProblem
from shrinkray.passes.patching import Cuts, apply_patches

def find_start_codes(data: bytes, start_code: bytes) -> list[int]:
    start_codes = [0]
    while (pos := data.find(start_code, start_codes[-1] + 1)) != -1:
        start_codes.append(pos)
    return start_codes

async def nalu_deletion(problem: ReductionProblem[bytes]) -> None:
    start_code_prefix = b"\x00\00\01"
    nalu_starts = find_start_codes(problem.current_test_case, start_code_prefix)
    nalu_ends = nalu_starts[1:] + [len(problem.current_test_case)]
    spans = zip(nalu_starts, nalu_ends)
    await apply_patches(problem, Cuts(), [[s] for s in spans])
