from enum import Enum, IntEnum
from typing import List
import re


class Opcode(Enum):
    mnemonic: str

    NOP = (0x0, "no_operation")
    HLT = (0x1, "halt")

    LFLG = (0x2, "load_flags")
    SFLG = (0x3, "store_flags")

    ADD = (0x4, "add")
    SUB = (0x5, "substract")
    MUL = (0x6, "multiply")
    DIV = (0x7, "divide")
    AND = (0x8, "and")
    OR = (0x9, "or")
    XOR = (0xA, "xor")
    SHLT = (0xB, "shift_left")
    SHRT = (0xC, "shift_right")
    INV = (0xD, "invert")
    NEG = (0xE, "negate")

    EQ = (0xF, "is_==")
    GT = (0x10, "is_>")
    LT = (0x11, "is_<")
    GEQ = (0x12, "is_>=")
    LEQ = (0x13, "is_<=")

    JMP = (0x14, "jump")
    JMPIF = (0x15, "jump_if")

    CALL = (0x16, "call")
    RET = (0x17, "ret")

    LOAD = (0x18, "load")
    STORE = (0x19, "store")
    IN = (0x1A, "in")
    OUT = (0x1B, "out")

    PUSH = (0x1C, "push")
    POP = (0x1D, "pop")
    DUP = (0x1E, "duplicate")
    SWAP = (0x1F, "swap")

    def __new__(cls, value: int, mnemonic: str):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.mnemonic = mnemonic
        return obj

    def __str__(self):
        return self.mnemonic


class Decoder:
    @staticmethod
    def _get_char(b: int) -> str:
        return chr(b) if 32 <= b <= 126 else "."

    @staticmethod
    def code_to_hex(code: bytes) -> str:
        hex_list: List[str] = list()
        pc: int = 0
        while pc < len(code):
            addr = str(pc).rjust(5)
            opcode = Opcode(code[pc])
            mnemonics: str = opcode.mnemonic
            hex_code: str = ""
            match opcode:
                case Opcode.PUSH | Opcode.JMPIF | Opcode.JMP | Opcode.CALL:
                    mnemonics += (
                        f" {int.from_bytes(code[pc + 1 : pc + 5], byteorder='little')}"
                    )
                    hex_code = code[pc : pc + 5].hex()
                    pc += 4
                case _:
                    hex_code = hex(code[pc])[2:].rjust(2, "0").ljust(10)
            hex_list.append(f"{addr} - 0x{hex_code} - {mnemonics}")
            pc += 1
        return "\n".join(hex_list)

    @staticmethod
    def data_to_hex(data: bytes) -> str:
        data_list: List[str] = list()
        pc: int = 0
        total_bytes = len(data)

        while pc < total_bytes:
            if data[pc] == 0:
                start = pc
                while pc < total_bytes and data[pc] == 0:
                    pc += 1
                end = pc - 1
                if start < end:
                    addr_range = f"{start}...{end}".rjust(13)
                    data_list.append(f"{addr_range} - 0x00 - .")
                else:
                    addr = str(start).rjust(13)
                    data_list.append(f"{addr} - 0x00 - .")
            else:
                addr = str(pc).rjust(13)
                hex_data = hex(data[pc])
                char_repr = Decoder._get_char(data[pc])
                data_list.append(f"{addr} - {hex_data} - {char_repr}")
                pc += 1
        return "\n".join(data_list)


class ArgType(IntEnum):
    DEC = 0
    HEX = 1
    LABEL = 2
    UNKNOWN = 3

    @staticmethod
    def get(raw_arg: str) -> "ArgType":
        if re.match(r"^0x\d+$", raw_arg):
            return ArgType.HEX
        if re.match(r"^_\w+$", raw_arg):
            return ArgType.LABEL
        if re.match(r"^\d+$", raw_arg):
            return ArgType.DEC
        return ArgType.UNKNOWN


class Label:
    pattern = r"_\w+"
    regex = re.compile(pattern)


class String:
    pattern = r"\"(.+)\""
    regex = re.compile(pattern)


class Numeral:
    pattern = r"0x\d+|-?\d+"
    regex = re.compile(pattern)


class Variable:
    pattern = r"[A-Za-z]\w*"
    regex = re.compile(pattern)


class Comment:
    pattern = r";.*"
    regex = re.compile(pattern)


class Macros:
    if_regex = re.compile(
        r"@if\s*\((.*?)\)\s*\{(.*?)\}"
        r"(?:\s*@elif\s*\((.*?)\)\s*\{(.*?)\})*"
        r"(?:\s*@else\s*\{(.*?)\})?",
        re.DOTALL,
    )
    macro_regex = re.compile(r"@macro\s+(\w+)\s*\((.*?)\)\s*\{(.*?)\}", re.DOTALL)
    def_regex = re.compile(r"@define\s+(\w+)\s+(.+)")


class Segment:
    data_regex = re.compile(r"\.data(?:@(0x\d+|\d+))?")
    text_regex = re.compile(r"\.text(?:@(0x\d+|\d+))?")
