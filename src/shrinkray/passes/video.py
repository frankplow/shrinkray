from shrinkray.passes.definitions import ReductionProblem
from shrinkray.passes.patching import Cuts, apply_patches

def find_start_codes(data: bytes, start_code: bytes) -> list[int]:
    """Return a list of indexes into data at which the given start_code occurs."""
    start_codes = [0]
    while (pos := data.find(start_code, start_codes[-1] + 1)) != -1:
        start_codes.append(pos)
    return start_codes

def find_nalus(data: bytes) -> list[int]:
    """Return a list of indexes into data which identify the start of NAL units.
       The start of a NALU is indicated by a start code.  The NAL unit may also
       have some leading whitespace."""
    start_code_prefix = b"\x00\00\01"
    nalu_starts = []
    for pos in find_start_codes(data, start_code_prefix)[1:]:
        while pos >= 0 and data[pos] == 0x00:
            pos -= 1
        pos += 1
        nalu_starts.append(pos)
    return nalu_starts

async def nalu_deletion(problem: ReductionProblem[bytes]) -> None:
    nalu_starts = find_nalus(problem.current_test_case)
    nalu_ends = nalu_starts[1:] + [len(problem.current_test_case)]
    nalus = zip(nalu_starts, nalu_ends)
    spans = [[nalu] for nalu in nalus]
    spans.reverse()
    await apply_patches(problem, Cuts(), spans)
