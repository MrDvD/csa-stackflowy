from isa import Opcode
from datapath import DataPath
from typing import List, Dict
from dataclasses import dataclass
from microcode import MicroInstruction, State
from mux import (
    MuxRStack,
    MuxTrSel,
    MuxIPrefetch,
    MuxMpcSel,
    MuxPcSel,
)


@dataclass
class CacheLine:
    valid: bool = False
    tag: int = 0
    data: int = 0


class ControlUnit:
    def __init__(
        self,
        mem_size: int,
        mprogram: List[MicroInstruction],
        state_decoder_map: Dict[State, int],
        data_path: DataPath,
    ):
        self.rom_instructions: List[int] = [0] * mem_size
        self.i_cache: List[CacheLine] = [CacheLine() for _ in range(16)]
        self.mprogram: List[MicroInstruction] = mprogram
        self.state_decoder_map: Dict[State, int] = state_decoder_map
        self.data_path: DataPath = data_path

        self.pc: int = 0
        self.tr: int = 0
        self.return_stack: List[int] = [0 for _ in range(15)]

        self.i_prefetch: List[int] = [0, 0, 0, 0]
        self.ir: int = 0

        self.mpc: int = 0
        self.mr: MicroInstruction = MicroInstruction()

        self.rom_countdown: int = 0
        self.rom_busy: bool = False

    def _read_i_memory(self, addr: int) -> int:
        base_pc = addr & ~3
        idx = base_pc % len(self.rom_instructions)
        four_bytes = self.rom_instructions[idx : idx + 4]
        return int.from_bytes(four_bytes, byteorder="little")

    def _get_prefetch_value(self) -> int:
        return int.from_bytes(self.i_prefetch, byteorder="little")

    def _is_cache_hit(self) -> bool:
        offset = self.pc & 0x3
        match self.mr.select_i_prefetch:
            case MuxIPrefetch.CACHE:
                pc = self.pc
            case MuxIPrefetch.CACHE_ARG:
                if offset == 0:
                    pc = self.pc
                else:
                    pc = self.pc + 4
            case _:
                return True
        index = (pc >> 2) & 0xF
        tag = pc >> 6
        line = self.i_cache[index]
        return line.valid and line.tag == tag

    def _decode_state(self) -> int:
        state = State(
            instruction=Opcode(self.ir), td_zero_bit=bool(self.data_path.td & 0x1)
        )
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
        return self.i_prefetch[0]

    def latch_mpc(self, sel: MuxMpcSel) -> int:
        match sel:
            case MuxMpcSel.MPC_PLUS_1:
                return self.mpc + 1
            case MuxMpcSel.STATE_DECODER:
                return self._decode_state()
            case MuxMpcSel.START:
                return 0
            case _:
                raise Exception("Unknown MuxMpc selector")

    def latch_mr(self) -> MicroInstruction:
        mpc = self.mpc
        return self.mprogram[mpc % len(self.mprogram)]

    def cache_write(self) -> None:
        offset = self.pc & 0x3
        match self.mr.select_i_prefetch:
            case MuxIPrefetch.CACHE:
                pc = self.pc
            case MuxIPrefetch.CACHE_ARG:
                if offset == 0:
                    pc = self.pc
                else:
                    pc = self.pc + 4
            case _:
                raise Exception("Incorrect state: cache is not requested")
        word = self._read_i_memory(pc)
        index = (pc >> 2) & 0xF
        tag = pc >> 6
        self.i_cache[index] = CacheLine(True, tag, word)

    def latch_i_prefetch(self, sel: MuxIPrefetch) -> List[int]:
        offset = self.pc & 0x3
        latches = [i < (4 - offset) for i in range(4)]
        next_i_prefetch = list(self.i_prefetch)
        match sel:
            case MuxIPrefetch.PREV:
                possible_i_prefetch = [*self.i_prefetch[1:], 0]
                for i in range(4):
                    if latches[i]:
                        next_i_prefetch[i] = possible_i_prefetch[i]
                return next_i_prefetch

            case MuxIPrefetch.CACHE:
                idx = (self.pc >> 2) & 0xF
                bytes_word = list(
                    (self.i_cache[idx].data & 0xFFFFFFFF).to_bytes(
                        4, byteorder="little"
                    )
                )
                for i in range(4):
                    if latches[i]:
                        next_i_prefetch[i] = bytes_word[offset + i]

                return next_i_prefetch
            case MuxIPrefetch.CACHE_ARG:
                # offset == 00 -> [1, 1, 1, 1], [0, 0, 0, 0]
                # offset == 01 -> [0, 1, 1, 1], [1, 0, 0, 0]
                # offset == 10 -> [0, 0, 1, 1], [1, 1, 0, 0]
                # offset == 11 -> [0, 0, 0, 1], [1, 1, 1, 0]
                if offset == 0:
                    idx = (self.pc >> 2) & 0xF
                    bytes_word = list(
                        (self.i_cache[idx].data & 0xFFFFFFFF).to_bytes(
                            4, byteorder="little"
                        )
                    )
                    for i in range(4):
                        if latches[i]:
                            next_i_prefetch[i] = bytes_word[offset + i]

                    return next_i_prefetch
                else:
                    base_idx = (self.pc >> 2) & 0xF
                    idx = (base_idx + 1) & 0xF
                    latches = [not latch for latch in latches]
                    bytes_word = list(
                        (self.i_cache[idx].data & 0xFFFFFFFF).to_bytes(
                            4, byteorder="little"
                        )
                    )
                    for i in range(4):
                        if latches[i]:
                            cache_idx = i - (4 - offset)
                            next_i_prefetch[i] = bytes_word[cache_idx]

                    return next_i_prefetch
            case _:
                raise Exception("Unknown MuxIPrefetch selector")

    def is_stall(self) -> bool:
        memory_i_output = not self._is_cache_hit()

        self.data_path.tick(
            ram_output=self.mr.memory_d_output,
            ram_write=self.mr.memory_d_write,
            io_output=self.mr.io_output,
            io_write=self.mr.io_write,
        )

        if memory_i_output and not self.rom_busy:
            self.rom_countdown = 10
            self.rom_busy = True
        elif self.rom_busy and self.rom_countdown > 0:
            self.rom_countdown -= 1

        if self.rom_busy:
            rom_ready = self.rom_countdown == 0
        else:
            rom_ready = True

        # Анализ линий заморозки (Hardware Stall / Clock Gating)
        rom_stalled = memory_i_output and not rom_ready
        ram_stalled = self.mr.memory_d_output and not self.data_path.data_memory.ready
        port_num: int = self.data_path.td & 0x3
        io_device = self.data_path.io_devices[port_num]
        io_stalled = self.mr.io_output and not io_device.ready

        # Если ХОТЯ БЫ ОДНО активное устройство занято — тактовый импульс до регистров CPU не доходит!
        if rom_stalled or ram_stalled or io_stalled:
            return True

        # сбрасываем триггер занятости Instruction ROM
        # (RAM и IO сбросятся внутри _read_data_mux в DataPath)
        if memory_i_output and rom_ready:
            self.cache_write()
            self.rom_busy = False
            return True

        return False

    def tick(self) -> bool:
        if self.mr.latch_mr and self.mr.micromem_output:
            self.mr = self.latch_mr()

        if self.is_stall():
            return True

        next_i_prefetch: List[int] = list(self.i_prefetch)
        if self.mr.latch_i_prefetch:
            next_i_prefetch = self.latch_i_prefetch(self.mr.select_i_prefetch)

        # не меняем сразу, чтобы симулировать параллельное распространение сигналов
        next_d_stack: List[int] = list(self.data_path.data_stack)
        if self.mr.latch_d_stack:
            next_d_stack = self.data_path.latch_d_stack(self.mr.select_s)

        next_td: int = self.data_path.td
        if self.mr.latch_td:
            next_td = self.data_path.latch_td(
                self.mr.select_td,
                self.mr.alu_l_sel,
                self.mr.alu_r_sel,
                self.mr.select_data_read,
                self.mr.memory_d_output,
                self.mr.io_output,
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
            self.data_path.data_memory.write(self.data_path.td, self.data_path.s)

        if self.mr.io_write:
            port_num: int = self.data_path.td & 0x3
            io_device = self.data_path.io_devices[port_num]
            io_device.write(self.data_path.s & 0xFF)

        next_pc: int = self.pc
        if self.mr.latch_pc:
            next_pc = self.latch_pc(self.mr.select_pc)

        next_tr: int = self.tr
        if self.mr.latch_tr:
            next_tr = self.latch_tr(self.mr.select_tr)

        next_r_stack: List[int] = list(self.return_stack)
        if self.mr.latch_r_stack:
            next_r_stack = self.latch_r_stack(self.mr.select_r_stack)

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
        self.i_prefetch = next_i_prefetch
        self.data_path.s = next_s
        self.data_path.data_stack = next_d_stack
        self.data_path.sr_v = next_sr_v
        self.data_path.sr_c = next_sr_c
        self.data_path.td = next_td
        return False

    def _to_str(self) -> str:
        return (
            f"PC: 0x{self.pc:08x} "
            f"IPF: 0x{self._get_prefetch_value():08x} "
            f"IR: {Opcode(self.ir).mnemonic[:5]:<5} "
            f"S: 0x{self.data_path.s:08x} "
            f"Td: 0x{self.data_path.td:08x}"
        )

    def __str__(self) -> str:
        return self._to_str()

    def __repr__(self) -> str:
        return self._to_str()
