import time
from pathlib import Path
from typing import Callable

import asyncio
from httpx import AsyncClient  


POP20_CC = ('CN IN US ID BR PK NG BD RU JP '
            'MX PH VN ET EG DE IR TR CD FR').split() 

BASE_URL = 'https://www.fluentpython.com/data/flags'  
DEST_DIR = Path('downloaded')                        


def save_flag(img: bytes, filename: str) -> None:    
    (DEST_DIR / filename).write_bytes(img)


def main(downloader: Callable[[list[str]], int]) -> None: 
    DEST_DIR.mkdir(exist_ok=True)                        
    t0 = time.perf_counter()                             
    count = downloader(POP20_CC)
    elapsed = time.perf_counter() - t0
    print(f'\n{count} downloads in {elapsed:.2f}s')


def download_many(cc_list: list[str]) -> int:   
    return asyncio.run(supervisor(cc_list))     


async def supervisor(cc_list: list[str]) -> int:
    async with AsyncClient() as client:         
        to_do = [download_one(client, cc)
                 for cc in sorted(cc_list)]     
        # Wait for `asyncio.gather` coroutine, which accepts one or more awaitable arguments and waits for all of them to complete, 
        # returning a list of results for the given awaitable in the order they were submitted. 
        res = await asyncio.gather(*to_do)     

    return len(res)                             


async def download_one(client: AsyncClient, cc: str): 
    image = await get_flag(client, cc)
    save_flag(image, f'{cc}.gif')
    print(cc, end=' ', flush=True)
    return cc


async def get_flag(client: AsyncClient, cc: str) -> bytes: 
    url = f'{BASE_URL}/{cc}/{cc}.gif'.lower()
    resp = await client.get(url, timeout=6.1,
                                  follow_redirects=True)
    return resp.read()  


if __name__ == "__main__":
    main(download_many)
