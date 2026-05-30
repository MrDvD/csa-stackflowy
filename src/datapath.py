from enum import Enum
from typing import List, Tuple


class MuxTdSel(Enum):
    DATA_READ = 0
    S_SHIFT = 1
    ALU_RESULT = 2
    I_PREFETCH = 3


class MuxSSel(Enum):
    PREV = 0
    NEXT = 1


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


class DataPath:
    def __init__(self, mem_size: int, input_data: List[int]):
        self.data_memory: List[int] = [0] * mem_size
        self.data_stack: List[int] = [0 for _ in range(14)]
        self.input_buffer: List[int] = input_data
        self.output_buffer: List[int] = list()
        self.s: int = 0
        self.td: int = 0
        self.sr_v: bool = False
        self.sr_c: bool = False

    def _read_data_mux(self, sel: MuxDataReadSel) -> int:
        match sel:
            case MuxDataReadSel.MEM_DATA:
                return self.data_memory[self.td % len(self.data_memory)]
            case MuxDataReadSel.IO:
                if self.input_buffer:
                    return self.input_buffer.pop(0)
                raise Exception("Input buffer is empty")
            case _:
                raise Exception("Unknown DataReadMux selector")

    def _read_sr(self) -> int:
        return (2 if self.sr_v else 0) | (1 if self.sr_c else 0)

    def _execute_alu_operands(
        self, alu_l_sel: MuxAluLeftSel, alu_r_sel: MuxAluRightSel
    ) -> Tuple[int, int]:
        match alu_l_sel:
            case MuxAluLeftSel.S:
                left = self.s
            case MuxAluLeftSel.ZERO:
                left = 0
            case _:
                raise Exception("Unknown MuxAluLeft selector")
        match alu_r_sel:
            case MuxAluRightSel.TD:
                right = self.td
            case MuxAluRightSel.SR:
                right = self._read_sr()
            case _:
                raise Exception("Unknown MuxAluRight selector")
        return left, right

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
        alu_l_sel: MuxAluLeftSel,
        alu_r_sel: MuxAluRightSel,
        dr_sel: MuxDataReadSel = MuxDataReadSel.MEM_DATA,
        alu_op: AluOp = AluOp.ADD,
        ifetch_val: int = 0,
    ) -> int:
        left, right = self._execute_alu_operands(alu_l_sel, alu_r_sel)
        alu_res, _, _ = self._execute_alu(alu_op, left, right)

        match sel:
            case MuxTdSel.DATA_READ:
                return self._read_data_mux(dr_sel)
            case MuxTdSel.S_SHIFT:
                return self.s
            case MuxTdSel.ALU_RESULT:
                return alu_res
            case MuxTdSel.I_PREFETCH:
                return ifetch_val & 0xFFFFFFFF
            case _:
                raise Exception("Unknown MuxTd selector")

    def latch_s(self, sel: MuxSSel) -> int:
        match sel:
            case MuxSSel.PREV:
                return self.data_stack[-1]
            case MuxSSel.NEXT:
                return self.td
            case _:
                raise Exception("Unknown MuxS selector")

    def latch_sr(
        self,
        sel: MuxSrSel,
        alu_op: AluOp = AluOp.ADD,
        alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S,
        alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD,
    ) -> Tuple[bool, bool]:
        left, right = self._execute_alu_operands(alu_l_sel, alu_r_sel)
        alu_res, v, c = self._execute_alu(alu_op, left, right)

        match sel:
            case MuxSrSel.ALU_RESULT:
                return bool(alu_res & 2), bool(alu_res & 1)
            case MuxSrSel.ALU_FLAGS:
                return v, c
            case _:
                raise Exception("Unknown MuxSr selector")

    def latch_d_stack(self, sel: MuxSSel) -> List[int]:
        next_d_stack: List[int] = self.data_stack
        match sel:
            case MuxSSel.PREV:
                next_d_stack = [self.data_stack[1], *self.data_stack]
                next_d_stack.pop()
            case MuxSSel.NEXT:
                next_d_stack = self.data_stack[1:]
                next_d_stack.append(self.s)
            case _:
                raise Exception("Unknown MuxS selector")
        return next_d_stack

    def memory_d_write(self) -> None:
        self.data_memory[self.td % len(self.data_memory)] = self.s

    def io_write(self) -> None:
        self.output_buffer.append(self.s)
