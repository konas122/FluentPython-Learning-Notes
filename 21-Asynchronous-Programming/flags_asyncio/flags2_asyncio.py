import argparse
import string
import sys
import time
from collections import Counter
from enum import Enum
from pathlib import Path

import asyncio
from collections import Counter
from http import HTTPStatus
from pathlib import Path

import httpx
import tqdm  # type: ignore


DownloadStatus = Enum('DownloadStatus', 'OK NOT_FOUND ERROR')

POP20_CC = ('CN IN US ID BR PK NG BD RU JP '
            'MX PH VN ET EG DE IR TR CD FR').split()

DEFAULT_CONCUR_REQ = 1
MAX_CONCUR_REQ = 1

SERVERS = {
    'REMOTE': 'https://www.fluentpython.com/data/flags',
    'LOCAL':  'http://localhost:8000/flags',
    'DELAY':  'http://localhost:8001/flags',
    'ERROR':  'http://localhost:8002/flags',
}
DEFAULT_SERVER = 'LOCAL'

DEST_DIR = Path('downloaded')
COUNTRY_CODES_FILE = Path('country_codes.txt')


def save_flag(img: bytes, filename: str) -> None:
    (DEST_DIR / filename).write_bytes(img)


def initial_report(cc_list: list[str],
                   actual_req: int,
                   server_label: str) -> None:
    if len(cc_list) <= 10:
        cc_msg = ', '.join(cc_list)
    else:
        cc_msg = f'from {cc_list[0]} to {cc_list[-1]}'
    print(f'{server_label} site: {SERVERS[server_label]}')
    plural = 's' if len(cc_list) != 1 else ''
    print(f'Searching for {len(cc_list)} flag{plural}: {cc_msg}')
    if actual_req == 1:
        print('1 connection will be used.')
    else:
        print(f'{actual_req} concurrent connections will be used.')


def final_report(cc_list: list[str],
                 counter: Counter[DownloadStatus],
                 start_time: float) -> None:
    elapsed = time.perf_counter() - start_time
    print('-' * 20)
    plural = 's' if counter[DownloadStatus.OK] != 1 else ''
    print(f'{counter[DownloadStatus.OK]:3} flag{plural} downloaded.')
    if counter[DownloadStatus.NOT_FOUND]:
        print(f'{counter[DownloadStatus.NOT_FOUND]:3} not found.')
    if counter[DownloadStatus.ERROR]:
        plural = 's' if counter[DownloadStatus.ERROR] != 1 else ''
        print(f'{counter[DownloadStatus.ERROR]:3} error{plural}.')
    print(f'Elapsed time: {elapsed:.2f}s')


def expand_cc_args(every_cc: bool,
                   all_cc: bool,
                   cc_args: list[str],
                   limit: int) -> list[str]:
    codes: set[str] = set()
    A_Z = string.ascii_uppercase
    if every_cc:
        codes.update(a+b for a in A_Z for b in A_Z)
    elif all_cc:
        text = COUNTRY_CODES_FILE.read_text()
        codes.update(text.split())
    else:
        for cc in (c.upper() for c in cc_args):
            if len(cc) == 1 and cc in A_Z:
                codes.update(cc + c for c in A_Z)
            elif len(cc) == 2 and all(c in A_Z for c in cc):
                codes.add(cc)
            else:
                raise ValueError('*** Usage error: each CC argument '
                                 'must be A to Z or AA to ZZ.')
    return sorted(codes)[:limit]


def process_args(default_concur_req):
    server_options = ', '.join(sorted(SERVERS))
    parser = argparse.ArgumentParser(
        description='Download flags for country codes. '
                    'Default: top 20 countries by population.')
    parser.add_argument(
        'cc', metavar='CC', nargs='*',
        help='country code or 1st letter (eg. B for BA...BZ)')
    parser.add_argument(
        '-a', '--all', action='store_true',
        help='get all available flags (AD to ZW)')
    parser.add_argument(
        '-e', '--every', action='store_true',
        help='get flags for every possible code (AA...ZZ)')
    parser.add_argument(
        '-l', '--limit', metavar='N', type=int, help='limit to N first codes',
        default=sys.maxsize)
    parser.add_argument(
        '-m', '--max_req', metavar='CONCURRENT', type=int,
        default=default_concur_req,
        help=f'maximum concurrent requests (default={default_concur_req})')
    parser.add_argument(
        '-s', '--server', metavar='LABEL', default=DEFAULT_SERVER,
        help=f'Server to hit; one of {server_options} '
             f'(default={DEFAULT_SERVER})')
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='output detailed progress info')
    args = parser.parse_args()
    if args.max_req < 1:
        print('*** Usage error: --max_req CONCURRENT must be >= 1')
        parser.print_usage()
        # "standard" exit status codes:
        # https://stackoverflow.com/questions/1101957/are-there-any-standard-exit-status-codes-in-linux/40484670#40484670
        sys.exit(2)  # command line usage error
    if args.limit < 1:
        print('*** Usage error: --limit N must be >= 1')
        parser.print_usage()
        sys.exit(2)  # command line usage error
    args.server = args.server.upper()
    if args.server not in SERVERS:
        print(f'*** Usage error: --server LABEL '
              f'must be one of {server_options}')
        parser.print_usage()
        sys.exit(2)  # command line usage error
    try:
        cc_list = expand_cc_args(args.every, args.all, args.cc, args.limit)
    except ValueError as exc:
        print(exc.args[0])
        parser.print_usage()
        sys.exit(2)  # command line usage error

    if not cc_list:
        cc_list = sorted(POP20_CC)[:args.limit]
    return args, cc_list


def main(download_many, default_concur_req, max_concur_req):
    args, cc_list = process_args(default_concur_req)
    actual_req = min(args.max_req, max_concur_req, len(cc_list))
    initial_report(cc_list, actual_req, args.server)
    base_url = SERVERS[args.server]
    DEST_DIR.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    counter = download_many(cc_list, base_url, args.verbose, actual_req)
    final_report(cc_list, counter, t0)


# low concurrency default to avoid errors from remote site,
# such as 503 - Service Temporarily Unavailable
DEFAULT_CONCUR_REQ = 5
MAX_CONCUR_REQ = 1000

async def get_flag(client: httpx.AsyncClient,  
                   base_url: str,
                   cc: str) -> bytes:
    url = f'{base_url}/{cc}/{cc}.gif'.lower()
    resp = await client.get(url, timeout=3.1, follow_redirects=True)   
    resp.raise_for_status()
    return resp.content

async def download_one(client: httpx.AsyncClient,
                       cc: str,
                       base_url: str,
                       semaphore: asyncio.Semaphore,
                       verbose: bool) -> DownloadStatus:
    try:
        async with semaphore:   
            # Use the `semaphore` as asynchronous context manger so that the program as a whole is not blocked;
            # only this coroutine is suspended when the semaphore counter is zero. 
            image = await get_flag(client, base_url, cc)
    except httpx.HTTPStatusError as exc:  
        res = exc.response
        if res.status_code == HTTPStatus.NOT_FOUND:
            status = DownloadStatus.NOT_FOUND
            msg = f'not found: {res.url}'
        else:
            raise
    else:
        # Saving the images is an I/O operation. To avoid blocking the event loop, run `save_flag` in a thread. 
        await asyncio.to_thread(save_flag, image, f'{cc}.gif') 
        status = DownloadStatus.OK
        msg = 'OK'
    if verbose and msg:
        print(cc, msg)
    return status


async def supervisor(cc_list: list[str],
                     base_url: str,
                     verbose: bool,
                     concur_req: int) -> Counter[DownloadStatus]:  
    counter: Counter[DownloadStatus] = Counter()
    semaphore = asyncio.Semaphore(concur_req)  
    async with httpx.AsyncClient() as client:
        to_do = [download_one(client, cc, base_url, semaphore, verbose)
                 for cc in sorted(cc_list)]  
        to_do_iter = asyncio.as_completed(to_do) 
        if not verbose:
            to_do_iter = tqdm.tqdm(to_do_iter, total=len(cc_list))  
        error: httpx.HTTPError | None = None  
        for coro in to_do_iter:  
            try:
                status = await coro 
            except httpx.HTTPStatusError as exc:
                error_msg = 'HTTP error {resp.status_code} - {resp.reason_phrase}'
                error_msg = error_msg.format(resp=exc.response)
                error = exc 
            except httpx.RequestError as exc:
                error_msg = f'{exc} {type(exc)}'.strip()
                error = exc  
            except KeyboardInterrupt:
                break

            if error:
                status = DownloadStatus.ERROR 
                if verbose:
                    url = str(error.request.url)  
                    cc = Path(url).stem.upper()  
                    print(f'{cc} error: {error_msg}')
            counter[status] += 1

    return counter

def download_many(cc_list: list[str],
                  base_url: str,
                  verbose: bool,
                  concur_req: int) -> Counter[DownloadStatus]:
    coro = supervisor(cc_list, base_url, verbose, concur_req)
    counts = asyncio.run(coro)  

    return counts

if __name__ == '__main__':
    main(download_many, DEFAULT_CONCUR_REQ, MAX_CONCUR_REQ)
