from typing import List, Tuple
from mux import (
    MuxDataReadSel,
    MuxAluLeftSel,
    MuxAluRightSel,
    MuxSrSel,
    MuxSSel,
    MuxTdSel,
    AluOp,
)


class IODevice:
    def __init__(self, input_buffer: List[int]) -> None:
        self.busy: bool = False
        self.countdown: int = 0
        self.input_buffer: List[int] = input_buffer
        self.output_buffer: List[int] = list()

    @property
    def ready(self) -> int:
        if self.busy:
            return self.countdown == 0
        return 0

    def write(self, data_in: int):
        self.output_buffer.append(data_in & 0xFF)

    def read(self) -> int:
        if len(self.input_buffer) == 0:
            raise Exception("Input buffer is empty!")
        return self.input_buffer.pop(0) & 0xFF

    def tick(self, output: bool, write: bool) -> None:
        if self.busy:
            if self.countdown > 0:
                self.countdown -= 1
        else:
            if output:
                self.countdown = 10
                self.busy = True
            elif write:
                self.countdown = 10
                self.busy = True


class Memory:
    def __init__(self, mem_size: int, delay: int) -> None:
        self.busy: bool = False
        self.countdown: int = 0
        self.memory: List[int] = [0] * mem_size
        self.delay = delay
        assert delay > 0, "Memory delay should be positive"

    @property
    def ready(self) -> int:
        if self.busy:
            return self.countdown == 0
        return 0

    def write(self, addr: int, data_in: int):
        addr = addr % len(self.memory)
        four_bytes = data_in.to_bytes(4, byteorder="big")
        for i, byte in enumerate(four_bytes):
            target_addr = (addr + i) % len(self.memory)
            self.memory[target_addr] = byte

    def read(self, addr: int) -> int:
        self.busy = False
        addr = addr % len(self.memory)
        four_bytes = bytearray(4)
        for i in range(4):
            four_bytes[i] = self.memory[(addr + i) % len(self.memory)]
        return int.from_bytes(four_bytes, byteorder="big")

    def tick(self, output: bool, write: bool) -> None:
        if self.busy:
            if self.countdown > 0:
                self.countdown -= 1
        else:
            if output:
                self.countdown = self.delay
                self.busy = True
            elif write:
                self.countdown = self.delay
                self.busy = True


class DataPath:
    def __init__(self, mem_size: int, input_data: List[List[int]]):
        self.data_memory: Memory = Memory(mem_size, 10)
        self.data_stack: List[int] = [0 for _ in range(14)]
        self.s: int = 0
        self.td: int = 0
        self.sr_v: bool = False
        self.sr_c: bool = False

        self.io_devices = {
            i: IODevice(input_buffer=input_data[i] if i < len(input_data) else list())
            for i in range(4)
        }

    def tick(
        self, ram_output: bool, ram_write: bool, io_output: bool, io_write: bool
    ) -> None:
        port_num = self.td % 0x3
        device = self.io_devices[port_num]
        device.tick(output=io_output, write=io_write)
        self.data_memory.tick(output=ram_output, write=ram_write)

    def _read_data_mux(
        self, sel: MuxDataReadSel, memory_d_output: bool, io_output: bool
    ) -> int:
        match sel:
            case MuxDataReadSel.MEM_DATA:
                if memory_d_output and self.data_memory.ready:
                    return self.data_memory.read(self.td)
                return 0
            case MuxDataReadSel.IO:
                port_num: int = self.td & 0x3
                device = self.io_devices[port_num]
                if io_output and device.ready:
                    return device.read()
                return 0
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
        memory_d_output: bool = False,
        io_output: bool = False,
        alu_op: AluOp = AluOp.ADD,
        ifetch_val: int = 0,
    ) -> int:
        left, right = self._execute_alu_operands(alu_l_sel, alu_r_sel)
        alu_res, _, _ = self._execute_alu(alu_op, left, right)

        match sel:
            case MuxTdSel.DATA_READ:
                return self._read_data_mux(dr_sel, memory_d_output, io_output)
            case MuxTdSel.S:
                return self.s
            case MuxTdSel.DATA_STACK:
                return self.data_stack[-1] & 0xFFFFFFFF
            case MuxTdSel.ALU_RESULT:
                return alu_res
            case MuxTdSel.I_PREFETCH:
                return ifetch_val & 0xFFFFFFFF
            case _:
                raise Exception("Unknown MuxTd selector")

    def latch_s(self, sel: MuxSSel) -> int:
        match sel:
            case MuxSSel.PREV:
                return self.data_stack[-1] & 0xFFFFFFFF
            case MuxSSel.NEXT:
                return self.td & 0xFFFFFFFF
            case MuxSSel.PREV_TWO:
                return self.data_stack[-2] & 0xFFFFFFFF
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
        next_d_stack: List[int] = list(self.data_stack)
        match sel:
            case MuxSSel.PREV:
                next_d_stack = [self.data_stack[1], *self.data_stack]
                next_d_stack.pop()
            case MuxSSel.PREV_TWO:
                next_d_stack = [
                    self.data_stack[1],
                    self.data_stack[1],
                    *self.data_stack,
                ]
                next_d_stack.pop()
                next_d_stack.pop()
            case MuxSSel.NEXT:
                next_d_stack = self.data_stack[1:]
                next_d_stack.append(self.s)
            case _:
                raise Exception("Unknown MuxS selector")
        return next_d_stack
