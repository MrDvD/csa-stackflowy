from enum import Enum


class MuxPcSel(Enum):
    I_PREFETCH = 0
    PC_PLUS_1 = 1
    PC_PLUS_4 = 2
    TR = 3


class MuxTrSel(Enum):
    PC_PLUS_4 = 0
    STACK_PREV = 1


class MuxMpcSel(Enum):
    STATE_DECODER = 0
    MPC_PLUS_1 = 1
    START = 2


class MuxIPrefetch(Enum):
    PREV = 0
    CACHE = 1
    CACHE_ARG = 2


class MuxRStack(Enum):
    PREV = 0
    NEXT = 1


class MuxTdSel(Enum):
    DATA_READ = 0
    S = 1
    DATA_STACK = 2
    ALU_RESULT = 3
    I_PREFETCH = 4


class MuxSSel(Enum):
    PREV = 0
    NEXT = 1
    PREV_TWO = 2


class MuxAluLeftSel(Enum):
    S = 0
    ZERO = 1


class MuxAluRightSel(Enum):
    TD = 0
    SR = 1


class MuxDataReadSel(Enum):
    MEM_DATA = 0
    IO = 1


class MuxSrSel(Enum):
    ALU_RESULT = 0
    ALU_FLAGS = 1


class AluOp(Enum):
    ADD = 0x0
    SUB = 0x1
    MUL = 0x2
    DIV = 0x3
    NEG = 0x4
    AND = 0x5
    OR = 0x6
    XOR = 0x7
    NOT = 0x8
    SHLT = 0x9
    SHRT = 0xA
    EQ = 0xB
    GT = 0xC
    LT = 0xD
    GEQ = 0xE
    LEQ = 0xF
