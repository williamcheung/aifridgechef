# constants
UTF8_ENCODING = 'utf-8'

def load_prompt(prompt_file: str) -> str:
    with open(f'prompts/{prompt_file}', 'r', encoding=UTF8_ENCODING) as f:
        return f.read()

def yield_lines_from_file(file_path: str):
    with open(f'data/{file_path}', 'r', encoding=UTF8_ENCODING) as f:
        for line in f:
            if line: # includes newline
                yield line.strip()
