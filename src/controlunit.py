from enum import Enum
from isa import Opcode
from typing import List, Dict, Tuple

class MuxPcSel(Enum):
  NIR = 0
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
    latch_ir_pipeline: bool = False,
    select_i_counter: MuxICounterSel = MuxICounterSel.ZERO,
    select_mpc: MuxMpcSel = MuxMpcSel.MPC_PLUS_1,
    latch_mpc: bool = False,
    latch_mr: bool = False,
    halt: bool = False
  ):
    self.select_pc: MuxPcSel = select_pc
    self.latch_pc: bool = latch_pc
    self.select_tr: MuxTrSel = select_tr
    self.latch_tr: bool = latch_tr
    self.latch_r_stack: bool = latch_r_stack
    self.r_stack_push: bool = r_stack_push
    self.latch_ir_pipeline: bool = latch_ir_pipeline
    self.select_i_counter: MuxICounterSel = select_i_counter
    self.select_mpc: MuxMpcSel = select_mpc
    self.latch_mpc: bool = latch_mpc
    self.latch_mr: bool = latch_mr
    self.halt: bool = halt

class ControlUnit:
  def __init__(self, mem_size: int, mprogram: List[MicroInstruction], state_decoder_map: Dict[Tuple[Opcode, int], int]):
    self.rom_instructions: List[int] = [0] * mem_size
    self.cache_instructions: Dict[int, int] = dict()
    self.mprogram: List[MicroInstruction] = mprogram
    self.state_decoder_map: Dict[Tuple[Opcode, int], int] = state_decoder_map
    
    self.pc: int = 0
    self.tr: int = 0
    self.return_stack: List[int] = []
    
    self.prefetch_buffer: List[int] = [0, 0, 0, 0]
    self.pipeline_i: List[int] = [0, 0, 0, 0]
    self.ir: int = 0
    self.i_counter: int = 0
    
    self.mpc: int = 0
    self.mr: MicroInstruction = MicroInstruction()
    
    self.model_tick: int = 0
    self.halted: bool = False

  def _read_instruction_rom(self, addr: int) -> int:
    if 0 <= addr < len(self.rom_instructions):
      return self.rom_instructions[addr]
    return 0

  def _get_nir_value(self) -> int:
    return (self.pipeline_i[3] << 24) | (self.pipeline_i[2] << 16) | (self.pipeline_i[1] << 8) | self.pipeline_i[0]

  def _decode_state(self) -> int:
    try:
      opcode_enum = Opcode(self.ir)
      return self.state_decoder_map.get((opcode_enum, self.i_counter), 0)
    except ValueError:
      return 0

  def tick(self) -> None:
    if self.halted:
      return

    current_uinst: MicroInstruction = self.mprogram[self.mpc] if self.mpc < len(self.mprogram) else MicroInstruction(halt=True)
    
    if current_uinst.halt:
      self.halted = True
      return

    next_pc: int = self.pc
    if current_uinst.latch_pc:
      if current_uinst.select_pc == MuxPcSel.NIR:
        next_pc = self._get_nir_value()
      elif current_uinst.select_pc == MuxPcSel.PC_PLUS_1:
        next_pc = self.pc + 1
      elif current_uinst.select_pc == MuxPcSel.PC_PLUS_4:
        next_pc = self.pc + 4
      elif current_uinst.select_pc == MuxPcSel.TR:
        next_pc = self.tr

    next_tr: int = self.tr
    if current_uinst.latch_tr:
      if current_uinst.select_tr == MuxTrSel.PC:
        next_tr = self.pc
      elif current_uinst.select_tr == MuxTrSel.STACK_PREV:
        if self.return_stack:
          next_tr = self.return_stack[-1]
        else:
          next_tr = 0

    if current_uinst.latch_r_stack:
      if current_uinst.r_stack_push:
        self.return_stack.append(self.tr)
      elif self.return_stack:
        self.return_stack.pop()

    if self.pc not in self.cache_instructions:
      self.cache_instructions[self.pc] = self._read_instruction_rom(self.pc)

    if current_uinst.latch_ir_pipeline:
      word_val: int = self.cache_instructions.get(self.pc, 0)
      self.prefetch_buffer[0] = word_val & 0xFF
      self.prefetch_buffer[1] = (word_val >> 8) & 0xFF
      self.prefetch_buffer[2] = (word_val >> 16) & 0xFF
      self.prefetch_buffer[3] = (word_val >> 24) & 0xFF

      high_byte: int = self.prefetch_buffer[3]
      self.ir = self.pipeline_i[0]
      self.pipeline_i[0] = self.pipeline_i[1]
      self.pipeline_i[1] = self.pipeline_i[2]
      self.pipeline_i[2] = self.pipeline_i[3]
      self.pipeline_i[3] = high_byte

    next_i_counter: int = self.i_counter
    if current_uinst.latch_ir_pipeline:
      if current_uinst.select_i_counter == MuxICounterSel.ZERO:
        next_i_counter = 0
      elif current_uinst.select_i_counter == MuxICounterSel.INC:
        next_i_counter = (self.i_counter + 1) & 0x03

    next_mpc: int = self.mpc
    if current_uinst.latch_mpc:
      if current_uinst.select_mpc == MuxMpcSel.MPC_PLUS_1:
        next_mpc = self.mpc + 1
      elif current_uinst.select_mpc == MuxMpcSel.STATE_DECODER:
        next_mpc = self._decode_state()

    if current_uinst.latch_mr:
      self.mr = current_uinst

    self.pc = next_pc
    self.tr = next_tr
    self.i_counter = next_i_counter
    self.mpc = next_mpc
    self.model_tick += 1