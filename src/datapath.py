from enum import Enum
from typing import List, Tuple


class MuxTdSel(Enum):
    DATA_READ = 0
    S_SHIFT = 1
    ALU_RESULT = 2
    NIR = 3


class MuxSSel(Enum):
    STACK_PREV = 0
    TD_SHIFT = 1


class MuxAluLeftSel(Enum):
    S = 0
    ZERO = 1


class MuxAluRightSel(Enum):
    TD = 0
    SR = 1


class MuxDataReadSel(Enum):
    RAM = 0
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


class DataPath:
    def __init__(self, mem_size: int, input_data: List[int]):
        self.memory: List[int] = [0] * mem_size
        self.data_stack: List[int] = [0 for _ in range(14)]
        self.input_buffer: List[int] = input_data
        self.output_buffer: List[int] = list()
        self.s: int = 0
        self.td: int = 0
        self.sr_v: bool = False
        self.sr_c: bool = False

    def _read_data_mux(self, sel: MuxDataReadSel) -> int:
        match sel:
            case MuxDataReadSel.RAM:
                return self.memory[self.td % len(self.memory)]
            case MuxDataReadSel.IO:
                if self.input_buffer:
                    return self.input_buffer.pop(0)
                raise Exception("Input buffer is empty")
            case _:
                raise Exception("Unknown DataReadMux selector")

    def _execute_alu(self, op: AluOp, left: int, right: int) -> Tuple[int, bool, bool]:
        left = left & 0xFFFFFFFF
        right = right & 0xFFFFFFFF
        res: int = 0
        v: bool = False
        c: bool = False

        def to_signed(val: int) -> int:
            return val - 0x100000000 if val & 0x80000000 else val

        match op:
            case AluOp.ADD:
                res = left + right
                c = res > 0xFFFFFFFF
                v = (
                    not (left & 0x80000000)
                    and not (right & 0x80000000)
                    and bool(res & 0x80000000)
                ) or (
                    bool(left & 0x80000000)
                    and bool(right & 0x80000000)
                    and not (res & 0x80000000)
                )
            case AluOp.SUB:
                res = left - right
                c = left < right
                v = (
                    not (left & 0x80000000)
                    and bool(right & 0x80000000)
                    and bool(res & 0x80000000)
                ) or (
                    bool(left & 0x80000000)
                    and not (right & 0x80000000)
                    and not (res & 0x80000000)
                )
            case AluOp.MUL:
                res = to_signed(left) * to_signed(right)
                v = res < -0x80000000 or res > 0x7FFFFFFF
            case AluOp.DIV:
                s_left = to_signed(left)
                s_right = to_signed(right)
                if s_right != 0:
                    res = int(s_left / s_right)
                    v = s_left == -0x80000000 and s_right == -1
                else:
                    res = 0
                    v = True
            case AluOp.NEG:
                res = -right
                c = right > 0
                v = right == 0x80000000
            case AluOp.AND:
                res = left & right
            case AluOp.OR:
                res = left | right
            case AluOp.XOR:
                res = left ^ right
            case AluOp.NOT:
                res = ~right
            case AluOp.SHLT:
                res = left << 1
                c = bool(left & 0x80000000)
            case AluOp.SHRT:
                res = left >> 1
                c = bool(left & 1)
            case AluOp.EQ | AluOp.GT | AluOp.LT | AluOp.GEQ | AluOp.LEQ:
                s_left = to_signed(left)
                s_right = to_signed(right)
                match op:
                    case AluOp.EQ:
                        cond = s_left == s_right
                    case AluOp.GT:
                        cond = s_left > s_right
                    case AluOp.LT:
                        cond = s_left < s_right
                    case AluOp.GEQ:
                        cond = s_left >= s_right
                    case AluOp.LEQ:
                        cond = s_left <= s_right
                res = 1 if cond else 0
                c = cond
            case _:
                raise Exception("Unknown ALU operation")

        return res & 0xFFFFFFFF, v, c

    def latch_td(
        self,
        sel: MuxTdSel,
        dr_sel: MuxDataReadSel = MuxDataReadSel.RAM,
        alu_op: AluOp = AluOp.ADD,
        ifetch_val: int = 0,
    ) -> None:
        left_mux: int = self.s if False else 0
        right_mux: int = self.td if False else 0
        alu_res, _, _ = self._execute_alu(alu_op, left_mux, right_mux)

        if sel == MuxTdSel.DATA_READ:
            self.td = self._read_data_mux(dr_sel)
        elif sel == MuxTdSel.S_SHIFT:
            self.td = self.s
        elif sel == MuxTdSel.ALU_RESULT:
            self.td = alu_res
        elif sel == MuxTdSel.NIR:
            self.td = ifetch_val & 0xFFFFFFFF

    def latch_s(self, sel: MuxSSel) -> None:
        if sel == MuxSSel.STACK_PREV:
            if self.data_stack:
                self.s = self.data_stack.pop()
            else:
                self.s = 0
        elif sel == MuxSSel.TD_SHIFT:
            self.s = self.td

    def latch_sr(
        self,
        sel: MuxSrSel,
        alu_op: AluOp = AluOp.ADD,
        alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S,
        alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD,
    ) -> None:
        left: int = self.s if alu_l_sel == MuxAluLeftSel.S else 0
        right: int = 0
        if alu_r_sel == MuxAluRightSel.TD:
            right = self.td
        elif alu_r_sel == MuxAluRightSel.SR:
            right = (1 if self.sr_v else 0) | (2 if self.sr_c else 0)

        alu_res, v, c = self._execute_alu(alu_op, left, right)

        if sel == MuxSrSel.ALU_RESULT:
            self.sr_v = bool(alu_res & 1)
            self.sr_c = bool(alu_res & 2)
        elif sel == MuxSrSel.ALU_FLAGS:
            self.sr_v = v
            self.sr_c = c

    def stack_push(self) -> None:
        self.data_stack.append(self.s)

    def write_memory(self) -> None:
        self.memory[self.td % len(self.memory)] = self.s

    def write_io(self) -> None:
        self.output_buffer.append(self.s)
