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


class MuxICounterSel(Enum):
    ZERO = 0
    INC = 1


class MicroInstruction:
    def __init__(
        self,
        select_pc: MuxPcSel = MuxPcSel.PC_PLUS_1,
        latch_pc: bool = False,
        select_tr: MuxTrSel = MuxTrSel.PC,
        latch_tr: bool = False,
        latch_r_stack: bool = False,
        r_stack_push: bool = False,
        latch_ir: bool = False,
        select_mpc: MuxMpcSel = MuxMpcSel.MPC_PLUS_1,
        latch_mpc: bool = False,
        latch_mr: bool = False,
        latch_td: bool = False,
        select_td: MuxTdSel = MuxTdSel.ALU_RESULT,
        latch_s: bool = False,
        select_s: MuxSSel = MuxSSel.TD_SHIFT,
        latch_sr: bool = False,
        select_sr: MuxSrSel = MuxSrSel.ALU_RESULT,
        alu_op: AluOp = AluOp.ADD,
        alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S,
        alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD,
        select_data_read: MuxDataReadSel = MuxDataReadSel.RAM,
        data_stack_push: bool = False,
        write_memory: bool = False,
        write_io: bool = False,
    ):
        self.select_pc: MuxPcSel = select_pc
        self.latch_pc: bool = latch_pc
        self.select_tr: MuxTrSel = select_tr
        self.latch_tr: bool = latch_tr
        self.latch_r_stack: bool = latch_r_stack
        self.r_stack_push: bool = r_stack_push
        self.latch_ir: bool = latch_ir
        self.select_mpc: MuxMpcSel = select_mpc
        self.latch_mpc: bool = latch_mpc
        self.latch_mr: bool = latch_mr
        self.latch_td: bool = latch_td
        self.select_td: MuxTdSel = select_td
        self.latch_s: bool = latch_s
        self.select_s: MuxSSel = select_s
        self.latch_sr: bool = latch_sr
        self.select_sr: MuxSrSel = select_sr
        self.alu_op: AluOp = alu_op
        self.alu_l_sel: MuxAluLeftSel = alu_l_sel
        self.alu_r_sel: MuxAluRightSel = alu_r_sel
        self.select_data_read: MuxDataReadSel = select_data_read
        self.data_stack_push: bool = data_stack_push
        self.write_memory: bool = write_memory
        self.write_io: bool = write_io


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

    def tick(self) -> None:
        next_uinst: MicroInstruction = self.mprogram[self.mpc % len(self.mprogram)]

        if self.mr.latch_mpc:
            self.mr = next_uinst

        if self.mr.data_stack_push:
            self.data_path.stack_push()

        if self.mr.latch_td:
            self.data_path.latch_td(
                self.mr.select_td,
                self.mr.select_data_read,
                self.mr.alu_op,
                self._get_prefetch_value(),
            )

        if self.mr.latch_s:
            self.data_path.latch_s(self.mr.select_s)

        if self.mr.latch_sr:
            self.data_path.latch_sr(
                self.mr.select_sr, self.mr.alu_op, self.mr.alu_l_sel, self.mr.alu_r_sel
            )

        if self.mr.write_memory:
            self.data_path.write_memory()

        if self.mr.write_io:
            self.data_path.write_io()

        next_pc: int = self.pc
        if self.mr.latch_pc:
            match self.mr.select_pc:
                case MuxPcSel.I_PREFETCH:
                    next_pc = self._get_prefetch_value()
                case MuxPcSel.PC_PLUS_1:
                    next_pc = self.pc + 1
                case MuxPcSel.PC_PLUS_4:
                    next_pc = self.pc + 4
                case MuxPcSel.TR:
                    next_pc = self.tr
                case _:
                    raise Exception("Unknown MuxPC selector")

        next_tr: int = self.tr
        if self.mr.latch_tr:
            match self.mr.select_tr:
                case MuxTrSel.PC:
                    next_tr = self.pc
                case MuxTrSel.STACK_PREV:
                    next_tr = self.return_stack[-1]

        if self.mr.latch_r_stack:
            if self.mr.r_stack_push:
                self.return_stack = self.return_stack[1:]
                self.return_stack.append(self.tr)
            else:
                self.return_stack = [self.return_stack[1], *self.return_stack]
                self.return_stack.pop()

        if self.pc not in self.cache_instructions:
            self.cache_instructions[self.pc] = self._read_instruction_rom(self.pc)

        if self.mr.latch_ir:
            high_byte: int = self.prefetch_buffer[3]
            self.ir = high_byte

        next_mpc: int = self.mpc
        if self.mr.latch_mpc:
            match self.mr.select_mpc:
                case MuxMpcSel.MPC_PLUS_1:
                    next_mpc = self.mpc + 1
                case MuxMpcSel.STATE_DECODER:
                    next_mpc = self._decode_state()
                case _:
                    raise Exception("Unknown MuxMpc selector")

        self.pc = next_pc
        self.tr = next_tr
        self.mpc = next_mpc
        self.model_tick += 1
