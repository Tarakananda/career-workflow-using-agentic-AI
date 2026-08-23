#!/usr/bin/env python3
"""Compare sequential vs parallel processing speed for Naukri job applications."""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.apply_new_sync import JobApplier
from src.ui import create_ui


def time_run(mode: str, max_jobs: int = 5, role_index: int = 0):
    """Run job processing in specified mode and return elapsed time."""
    ui = create_ui() if mode == "sequential" else None
    applier = JobApplier(ui=ui, max_parallel=3 if mode == "parallel" else 1)
    
    # Use single role for fair comparison
    original_roles = applier.profile.get("strict_roles", [])
    if not original_roles:
        print("No roles configured")
        return None
    applier.profile["strict_roles"] = [original_roles[role_index]]
    print(f"  Testing role: {original_roles[role_index]}")
    
    start = time.time()
    try:
        result = applier.run(max_jobs_per_role=max_jobs)
        elapsed = time.time() - start
        
        print(f"  {mode.upper()}: {elapsed:.1f}s | Applied: {len(result['applied'])} | "
              f"Skipped: {len(result['skipped'])} | Errors: {len(result['errors'])}")
        return elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"  {mode.upper()}: FAILED after {elapsed:.1f}s - {e}")
        return None


def main():
    print("=" * 60)
    print("TIMING TEST: Sequential vs Parallel Job Processing")
    print("=" * 60)
    print("Configuration: 5 jobs, single role, headless=false")
    print()
    
    # Test sequential first (baseline)
    seq_time = time_run("sequential", max_jobs=5)
    print()
    
    # Test parallel
    par_time = time_run("parallel", max_jobs=5)
    print()
    
    # Compare
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if seq_time and par_time:
        speedup = par_time / seq_time
        winner = "SEQUENTIAL" if seq_time < par_time else "PARALLEL"
        print(f"Sequential: {seq_time:.1f}s")
        print(f"Parallel:   {par_time:.1f}s")
        print(f"Winner:     {winner} ({speedup:.1f}x {'faster' if winner == 'SEQUENTIAL' else 'slower'})")
        
        if seq_time < par_time:
            print("\nSequential is faster - will disable parallel in Phase 0")
        else:
            print("\nParallel is faster - investigate before disabling")
    else:
        print("Test incomplete - check errors above")


if __name__ == "__main__":
    main()