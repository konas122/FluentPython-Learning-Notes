import asyncio
import functools
import sys
from asyncio.trsock import TransportSocket
from typing import cast

from charindex import InvertedIndex, format_results 


CRLF = b'\r\n'
PROMPT = b'?>'


async def supervisor(index: InvertedIndex, host: str, port: int) -> None:
    # This `await` quickly gets an instance of `asyncio.Server`, a TCP socket server. `start_server` creates and starts the server. 
    server = await asyncio.start_server(    
        # THe first argument is `client_connected_cb`, a callback to run when a new client connection starts. 
        # The callback can be a function or a coroutine, but it must accept exactly two argument: 
        # an `asyncio.StreamReader` and an `asyncio.StreamWriter`. 
        functools.partial(finder, index),
        host, port)

    # THis `cast` is needed because typeshed has an outdated type hint for the `sockets` property of the `Server` class. 
    socket_list = cast(tuple[TransportSocket, ...], server.sockets)
    addr = socket_list[0].getsockname()
    print(f'Serving on {addr}. Hit CTRL-C to stop.')  
    await server.serve_forever() 
    # Although `start_server` already started the server as a concurrent task, 
    # I need to `await` on the `server_forever` method so that my `supervisor` is suspended here. 


async def finder(index: InvertedIndex,
                 reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter) -> None:
    # Get the remote client address to which the socket is connected. 
    client = writer.get_extra_info('peername')
    # This loop handles a dialog that lasts until a control character is received from the client. 
    while True:
        # Can't await! The `StreamWriter.write` method is not a coroutine, just a plain function. 
        writer.write(PROMPT)
        # Must await! `StreamWriter.drain` flushes the `writer` buffer; it is a coroutine, so it must be driven with `await`. 
        await writer.drain()
        # `StreamWriter.readline` is a coroutine that returns `bytes`. 
        data = await reader.readline()
        if not data:
            break
        try:
            # Decode the `bytes` to `str`, using the deafault UTF-8 encoding. 
            query = data.decode().strip()
        # A `UnicodeDecoderError` may happen when the user hits Ctrl-C and the Telnet client sends control bytes;
        # if that happens, replace the query with a null character, for simplicity. 
        except UnicodeDecodeError:
            query = '\x00'
        print(f' From {client}: {query!r}')
        if query:
            # Exit the loop if a control or null character was received. 
            if ord(query[:1]) < 32:
                break
            # Do actual `search`. 
            results = await search(query, index, writer)
            print(f'   To {client}: {results} results. ')
    
    writer.close()
    # Wait for the `StreamWriter` to close. 
    await writer.wait_closed()
    print(f'Close {client}. ')


async def search(query: str,
                 index: InvertedIndex,
                 writer: asyncio.StreamWriter) -> int:
    chars = index.search(query)
    lines = (line.encode() + CRLF for line
                in format_results(chars))
    # Surprisingly, `writer.writelines` is not a coroutine. 
    writer.writelines(lines)
    await writer.drain()
    status_line = f'{"-" * 66} {len(chars)} found'
    writer.write(status_line.encode() + CRLF)
    await writer.drain()
    return len(chars)


def main(host: str = '127.0.0.1', port_arg: str = '2323'):
    port = int(port_arg)
    print('Building index')
    index = InvertedIndex()
    try:
        asyncio.run(supervisor(index, host, port))
    except KeyboardInterrupt:
        print('\nServer shut down. ')


if __name__ == "__main__":
    main(*sys.argv[1:])

