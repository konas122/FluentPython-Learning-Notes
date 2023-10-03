"""
threads.py: shows that Python threads are slower
than sequential code for CPU-intensive work.
"""

import os
import sys
from queue import SimpleQueue
from time import perf_counter
from typing import NamedTuple
from threading import Thread

from primes import is_prime, NUMBERS

class PrimeResult(NamedTuple):
    n: int
    prime: bool
    elapsed: float

JobQueue = SimpleQueue[int] 
ResultQueue = SimpleQueue[PrimeResult]  


def check(n: int) -> PrimeResult: 
    t0 = perf_counter()
    res = is_prime(n)
    return PrimeResult(n, res, perf_counter() - t0)


def worker(jobs: JobQueue, results: ResultQueue) -> None: 
    while n := jobs.get(): 
        results.put(check(n)) 
    results.put(PrimeResult(0, False, 0.0))


def start_jobs(workers: int, jobs: JobQueue, results: ResultQueue) -> None:
    for n in NUMBERS:  
        jobs.put(n)
    for _ in range(workers):
        proc = Thread(target=worker, args=(jobs, results)) 
        proc.start() 
        jobs.put(0)  


def report(workers: int, results: ResultQueue) -> int:
    checked = 0
    workers_done = 0
    while workers_done < workers:
        n, prime, elapsed = results.get()
        if n == 0:
            workers_done += 1
        else:
            checked += 1
            label = 'P' if prime else ' '
            print(f'{n:16}  {label} {elapsed:9.6f}s')
    return checked


def main() -> None:
    if len(sys.argv) < 2:
        workers = os.cpu_count()
    else:
        workers = int(sys.argv[1])

    print(f'Checking {len(NUMBERS)} numbers with {workers} threads:')
    t0 = perf_counter()
    jobs: JobQueue = SimpleQueue()
    results: ResultQueue = SimpleQueue()
    start_jobs(workers, jobs, results)
    checked = report(workers, results)
    elapsed = perf_counter() - t0
    print(f'{checked} checks in {elapsed:.2f}s')


if __name__ == '__main__':
    main()

