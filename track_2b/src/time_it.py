import datetime
import inspect
import os
import time

from functools import lru_cache, wraps

def time_it(func):
    '''
    Decorator to measure and print the execution time of a synchronous function, including when an error is raised.
    '''
    source_file, first_line_number = _get_function_location(func, line_offset=1) # get line number of function definition AFTER line with decorator

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            _log_execution_time(start_time, func, source_file, first_line_number)

    return wrapper

def time_it_async(func):
    '''
    Decorator to measure and print the execution time of an asynchronous function, including when an error is raised.
    '''
    source_file, first_line_number = _get_function_location(func, line_offset=1) # get line number of function definition AFTER line with decorator

    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return await func(*args, **kwargs)
        finally:
            _log_execution_time(start_time, func, source_file, first_line_number)

    return wrapper

@lru_cache(maxsize=None)
def _get_function_location(func, line_offset: int) -> tuple[str, int]:
    try:
        source_file = os.path.basename(inspect.getsourcefile(func))
        first_line_number = inspect.getsourcelines(func)[1] + line_offset
        return source_file, first_line_number
    except OSError:
        return None, None

def _log_execution_time(start_time: float, func, source_file: str | None, first_line_number: int | None) -> None:
    end_time = time.time()
    execution_time = end_time - start_time
    timestamp = datetime.datetime.now().strftime('%d-%b-%y %H:%M:%S')
    message = f'[{func.__name__}] took {execution_time:.4f} sec'
    source_line_ref = f'{source_file}:{first_line_number}' if source_file and first_line_number else ''
    print(f'{timestamp} [TIME] {source_line_ref} - {message}')

if __name__ == '__main__':
    # test usage
    import asyncio

    async def _test():
        @time_it_async
        async def _test_async_func() -> None:
            await asyncio.sleep(1)

        await _test_async_func()

    asyncio.run(_test())

    @time_it
    def _test_sync_func() -> None:
        time.sleep(1)

    _test_sync_func()
