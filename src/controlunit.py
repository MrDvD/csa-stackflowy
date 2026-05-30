from enum import Enum
from isa import Opcode
from datapath import (
    DataPath,
    MuxTdSel,
    MuxSSel,
    MuxAluLeftSel,
    MuxAluRightSel,
    MuxDataReadSel,
    MuxSrSel,
    AluOp,
)
from typing import List, Dict, Tuple
from dataclasses import dataclass


class MuxPcSel(Enum):
    I_PREFETCH = 0
    PC_PLUS_1 = 1
    PC_PLUS_4 = 2
    TR = 3


class MuxTrSel(Enum):
    PC = 0
    STACK_PREV = 1


class MuxMpcSel(Enum):
    MPC_PLUS_1 = 0
    STATE_DECODER = 1


class MuxIPrefetch(Enum):
    PREV = 0
    CACHE = 1


class MuxRStack(Enum):
    PREV = 0
    NEXT = 1


@dataclass
class MicroInstruction:
    alu_op: AluOp = AluOp.ADD
    alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S
    alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD
    latch_d_stack: bool = False
    latch_s: bool = False
    latch_td: bool = False
    select_s: MuxSSel = MuxSSel.NEXT
    select_td: MuxTdSel = MuxTdSel.ALU_RESULT
    latch_r_stack: bool = False
    latch_tr: bool = False
    select_r_stack: MuxRStack = MuxRStack.PREV
    select_tr: MuxTrSel = MuxTrSel.PC
    latch_pc: bool = False
    select_pc: MuxPcSel = MuxPcSel.PC_PLUS_1
    latch_sr: bool = False
    select_sr: MuxSrSel = MuxSrSel.ALU_RESULT
    memory_d_output: bool = False
    memory_i_output: bool = False
    memory_d_write: bool = False
    cache_i_write: bool = False
    io_output: bool = False
    io_write: bool = False
    select_data_read: MuxDataReadSel = MuxDataReadSel.MEM_DATA
    latch_ir: bool = False
    select_i_prefetch: MuxIPrefetch = MuxIPrefetch.PREV
    latch_mpc: bool = False
    latch_mr: bool = False
    micromem_output: bool = False
    select_mpc: MuxMpcSel = MuxMpcSel.MPC_PLUS_1


class ControlUnit:
    def __init__(
        self,
        mem_size: int,
        mprogram: List[MicroInstruction],
        state_decoder_map: Dict[Tuple[Opcode, int], int],
        data_path: DataPath,
    ):
        self.rom_instructions: List[int] = [0] * mem_size
        self.cache_instructions: Dict[int, int] = dict()
        self.mprogram: List[MicroInstruction] = mprogram
        self.state_decoder_map: Dict[Tuple[Opcode, int], int] = state_decoder_map
        self.data_path: DataPath = data_path

        self.pc: int = 0
        self.tr: int = 0
        self.return_stack: List[int] = [0 for _ in range(15)]

        self.prefetch_buffer: List[int] = [0, 0, 0, 0]
        self.ir: int = 0

        self.mpc: int = 0
        self.mr: MicroInstruction = MicroInstruction()

        self.model_tick: int = 0
        self.halted: bool = False

    def _read_instruction_rom(self, addr: int) -> int:
        return self.rom_instructions[addr % len(self.rom_instructions)]

    def _get_prefetch_value(self) -> int:
        return (
            self.prefetch_buffer[0]
            | (self.prefetch_buffer[1] << 8)
            | (self.prefetch_buffer[2] << 16)
            | (self.prefetch_buffer[3] << 24)
        )

    def _decode_state(self) -> int:
        state = (Opcode(self.ir), self.pc & 0x3)
        if state in self.state_decoder_map:
            return self.state_decoder_map[state]
        raise Exception("Unknown state occurred")
    
    def latch_r_stack(self, sel: MuxRStack) -> List[int]:
        next_r_stack: List[int] = list()
        match sel:
            case MuxRStack.NEXT:
                next_r_stack = self.return_stack[1:]
                next_r_stack.append(self.tr)
            case MuxRStack.PREV:
                next_r_stack = [self.return_stack[1], *self.return_stack]
                next_r_stack.pop()
            case _:
                raise Exception("Unknown MuxRStack selector")
        return next_r_stack
    
    def latch_tr(self, sel: MuxTrSel) -> int:
        match sel:
            case MuxTrSel.PC:
                return self.pc
            case MuxTrSel.STACK_PREV:
                return self.return_stack[-1]
            case _:
                raise Exception("Unknown MuxTr selector")
    
    def latch_pc(self, sel: MuxPcSel) -> int:
        match sel:
            case MuxPcSel.I_PREFETCH:
                return self._get_prefetch_value()
            case MuxPcSel.PC_PLUS_1:
                return self.pc + 1
            case MuxPcSel.PC_PLUS_4:
                return self.pc + 4
            case MuxPcSel.TR:
                return self.tr
            case _:
                raise Exception("Unknown MuxPC selector")
    
    def latch_ir(self) -> int:
        return self.prefetch_buffer[3]
    
    def latch_mpc(self, sel: MuxMpcSel) -> int:
        match sel:
            case MuxMpcSel.MPC_PLUS_1:
                return self.mpc + 1
            case MuxMpcSel.STATE_DECODER:
                return self._decode_state()
            case _:
                raise Exception("Unknown MuxMpc selector")
    
    def latch_mr(self) -> MicroInstruction:
        return self.mprogram[self.mpc % len(self.mprogram)]

    def tick(self) -> None:
        next_mr: MicroInstruction = self.mr
        if self.mr.latch_mr:
            next_mr = self.latch_mr()

        next_d_stack: List[int] = self.data_path.data_stack
        if self.mr.latch_d_stack:
            next_d_stack = self.data_path.latch_d_stack(self.mr.select_s)

        next_td: int = self.data_path.td
        if self.mr.latch_td:
            next_td = self.data_path.latch_td(
                self.mr.select_td,
                self.mr.alu_l_sel,
                self.mr.alu_r_sel,
                self.mr.select_data_read,
                self.mr.alu_op,
                self._get_prefetch_value(),
            )

        next_s: int = self.data_path.s
        if self.mr.latch_s:
            next_s = self.data_path.latch_s(self.mr.select_s)

        next_sr_v: bool = self.data_path.sr_v
        next_sr_c: bool = self.data_path.sr_c
        if self.mr.latch_sr:
            next_sr_v, next_sr_c = self.data_path.latch_sr(
                self.mr.select_sr, self.mr.alu_op, self.mr.alu_l_sel, self.mr.alu_r_sel
            )

        if self.mr.memory_d_write:
            self.data_path.memory_d_write()

        if self.mr.io_write:
            self.data_path.io_write()

        next_pc: int = self.pc
        if self.mr.latch_pc:
            next_pc = self.latch_pc(self.mr.select_pc)

        next_tr: int = self.tr
        if self.mr.latch_tr:
            next_tr = self.latch_tr(self.mr.select_tr)

        next_r_stack: List[int] = self.return_stack
        if self.mr.latch_r_stack:
            next_r_stack = self.latch_r_stack(self.mr.select_r_stack)

        if self.pc not in self.cache_instructions:
            self.cache_instructions[self.pc] = self._read_instruction_rom(self.pc)

        next_ir: int = self.ir
        if self.mr.latch_ir:
            next_ir = self.latch_ir()

        next_mpc: int = self.mpc
        if self.mr.latch_mpc:
            next_mpc = self.latch_mpc(self.mr.select_mpc)

        self.pc = next_pc
        self.tr = next_tr
        self.mpc = next_mpc
        self.return_stack = next_r_stack
        self.ir = next_ir
        self.mr = next_mr
        self.data_path.s = next_s
        self.data_path.data_stack = next_d_stack
        self.data_path.sr_v = next_sr_v
        self.data_path.sr_c = next_sr_c
        self.data_path.td = next_td
        self.model_tick += 1
